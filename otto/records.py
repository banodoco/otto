"""Generic Markdown readers and the trusted workspace record-loader boundary."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from types import MappingProxyType
from typing import Mapping

from . import markdown
from .config import DeclarationSourceMap, RecordKind, Workspace, _inside
from .ids import IdResolver, LocatedError, RecordRef, SourceLocation, identity_from_path, validate_identity


@dataclass(frozen=True)
class Record:
    ref: RecordRef
    source: SourceLocation
    title: str | None = None
    status: str | None = None
    fields: Mapping[str, str] = field(default_factory=dict)
    field_locations: Mapping[str, SourceLocation] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        object.__setattr__(self, "field_locations", MappingProxyType(dict(self.field_locations)))

    @property
    def status_location(self) -> SourceLocation | None:
        if self.status is None:
            return None
        return self.field_locations.get("status", self.field_locations.get("Status", self.source))

    @property
    def template_location(self) -> SourceLocation | None:
        return self.field_locations.get("Template")


@dataclass(frozen=True)
class RelationshipRow:
    """An authored row, before OT's configured graph semantics are applied."""

    source: RecordRef
    kind: str
    target: RecordRef
    role: str
    source_path: str
    source_line: int


@dataclass(frozen=True)
class RecordBatch:
    records: tuple[Record, ...] = ()
    relationships: tuple[RelationshipRow, ...] = ()

    def resolver(self) -> IdResolver:
        return IdResolver((record.ref, record.source) for record in self.records)


def _live_lines(text: str) -> list[str]:
    """Mask fenced examples, retaining exactly one slot per original line."""
    result = []
    fence = None
    width = 0
    for line in text.splitlines():
        if fence is not None:
            if re.fullmatch(r" {0,3}" + re.escape(fence) + "{" + str(width) + r",}[ \t]*", line):
                fence, width = None, 0
            result.append("")
            continue
        opening = re.match(r"^ {0,3}(" + re.escape(chr(96)) + r"{3,}|~{3,})", line)
        if opening:
            marker = opening[1]
            fence, width = marker[0], len(marker)
            result.append("")
        else:
            result.append(line)
    return result


def _frontmatter_error_line(text: str, message: str) -> int:
    """Locate the precise field responsible for the existing helper's refusal."""
    if message.startswith(("missing frontmatter", "unclosed frontmatter")):
        return 1
    seen = set()
    for index, line in enumerate(text.splitlines()[1:], 2):
        if line.strip() == "---":
            break
        match = re.fullmatch(r"([a-z][a-z0-9_-]*):[ ]+([^\r\n]+)", line)
        if not match or not match[2].strip() or match[1] in seen:
            return index
        seen.add(match[1])
    return 1


def _frontmatter(text: str, path: str) -> tuple[dict[str, str], dict[str, SourceLocation], int]:
    try:
        fields, _ = markdown.frontmatter(text)
    except ValueError as exc:
        message = str(exc)
        line = _frontmatter_error_line(text, message)
        if message == "duplicate frontmatter field 'status'":
            message = "duplicate status field"
        raise LocatedError(SourceLocation(path, line), message) from exc
    # The frontmatter reader permits only one-line values and one closing
    # delimiter. Count through that delimiter, including any blank body lines.
    offset = next(i + 1 for i, line in enumerate(text.splitlines()[1:], 1)
                  if line.strip() == "---")
    locations = {key: SourceLocation(path, index)
                 for index, key in enumerate(fields, 2)}
    return fields, locations, offset


def _title(live: list[str], offset: int, path: str) -> tuple[str, int]:
    index = next((i for i in range(offset, len(live)) if live[i].strip()), None)
    if index is None:
        raise LocatedError(SourceLocation(path, offset + 1 if offset < len(live) else max(1, len(live))),
                           "record document must start with a nonempty # title")
    headings = markdown.markdown_heading_anchors(live[index])
    title = headings[0][1] if headings and headings[0][0] == 1 else None
    if not title or not re.search(r"[^\s#]", title):
        raise LocatedError(SourceLocation(path, index + 1),
                           "record document must start with a nonempty # title")
    return title, index


def _header_fields(live: list[str], title_index: int, path: str,
                   fields: dict[str, str], locations: dict[str, SourceLocation]):
    """Expose bold header fields without treating body examples as metadata."""
    status_seen = "status" in fields
    for index in range(title_index + 1, len(live)):
        line = live[index]
        if any(level == 2 for level, _, _ in markdown.markdown_heading_anchors(line)):
            break
        key, separator, value = next(iter(markdown.key_value_lines(line, style="bold")), ("", "", ""))
        if not separator:
            continue
        if key == "Status":
            if status_seen:
                raise LocatedError(SourceLocation(path, index + 1), "duplicate status field")
            status_seen = True
        # Only status duplicates belong to the record reader. The template
        # loader checks the original source (including duplicate selectors).
        if key not in fields:
            fields[key] = value
            locations[key] = SourceLocation(path, index + 1)


def _relationship_rows(text: str, live: list[str], path: str, ref: RecordRef,
                       title_index: int) -> tuple[RelationshipRow, ...]:
    headings = [(i, title) for i in range(title_index + 1, len(live))
                for level, title, _ in markdown.markdown_heading_anchors(live[i]) if level == 2]
    sections = [index for index, name in headings if name == "Relationships"]

    def fail(index, suffix):
        raise LocatedError(SourceLocation(path, index + 1), f"invalid Relationships table: {suffix}")

    if not sections:
        return ()
    if len(sections) != 1:
        fail(sections[1], "duplicate Relationships section")
    start = sections[0]
    stop = next((index for index, _ in headings if index > start), len(live))
    # Deliberately use original content: a live Relationships section may
    # contain only its table, not prose or a nested fenced example.
    lines = [(i, line.strip()) for i, line in enumerate(text.splitlines())
             if start < i < stop and line.strip()]
    if not lines:
        fail(start, "expected Relation | Target | Role header")
    header = ["Relation", "Target", "Role"]

    def cells(index, line):
        if not (line.startswith("|") and line.endswith("|")):
            fail(index, "non-table content")
        raw = [cell.strip() for cell in line[1:-1].split("|")]
        if len(raw) != 3:
            fail(index, "expected exactly three cells")
        if not all(raw):
            fail(index, "blank cell")
        return markdown.split_table_row(line)

    if cells(*lines[0]) != header:
        fail(lines[0][0], "expected Relation | Target | Role header")
    if len(lines) < 2:
        fail(lines[0][0], "invalid separator row")
    separator_index, separator = lines[1]
    if (not separator.startswith("|") or not separator.endswith("|")
            or len(separator[1:-1].split("|")) != 3
            or any(not re.fullmatch(r":?-{3,}:?", value.strip())
                   for value in separator[1:-1].split("|"))):
        fail(separator_index, "invalid separator row")
    result = []
    for index, line in lines[2:]:
        values = cells(index, line)
        if values == header:
            fail(index, "expected Relation | Target | Role header")
        if all(re.fullmatch(r":?-{3,}:?", value) for value in values):
            fail(index, "invalid separator row")
        relation, target, role = values
        try:
            target_ref = RecordRef.parse(target)
        except ValueError:
            fail(index, "invalid typed target reference")
        result.append(RelationshipRow(ref, relation, target_ref, role, path, index + 1))
    return tuple(result)


def _read_source(workspace: Workspace, path: str) -> str:
    # Discovery checked containment; recheck before opening, since the working
    # tree can change between workspace discovery and record loading.
    root = workspace.root
    source_map = DeclarationSourceMap(path, MappingProxyType({(): 1}))
    relative = root / path
    _inside(root, relative, source=source_map, key=(), label=path)
    try:
        return markdown.read_text(root, relative)
    except (OSError, UnicodeError) as exc:
        raise LocatedError(SourceLocation(path, 1),
                           f"cannot read {path}: {getattr(exc, 'strerror', None) or exc}") from exc


def read_record(workspace: Workspace, kind: RecordKind, path: str) -> RecordBatch:
    """Read one discovered generic record, with line-addressed fields and rows."""
    if kind.reader == "adapter" or path not in workspace.sources.get(kind.name, ()):
        raise ValueError("read_record requires a discovered generic source")
    text = _read_source(workspace, path)
    live = _live_lines(text)
    fields: dict[str, str] = {}
    locations: dict[str, SourceLocation] = {}
    offset = 0
    if kind.reader == "frontmatter":
        fields, locations, offset = _frontmatter(text, path)
        live[:offset] = [""] * offset
    title, title_index = _title(live, offset, path)
    identity = identity_from_path(kind.name, workspace.ids[kind.name], path, line=title_index + 1)
    ref = RecordRef(kind.name, identity)
    _header_fields(live, title_index, path, fields, locations)
    status = fields.get("status" if kind.reader == "frontmatter" else "Status") or None
    record = Record(ref, SourceLocation(path, title_index + 1), title, status, fields, locations)
    rows = _relationship_rows(text, live, path, ref, title_index)
    return RecordBatch((record,), rows)


def _adapter_records(workspace: Workspace) -> RecordBatch:
    registration = workspace.config.adapters
    if not registration or not registration.records:
        return RecordBatch()
    name = registration.records
    key = ("adapters", "records")
    source_map = workspace.source_map

    def invalid_batch():
        raise source_map.error(key, f"adapter export {name!r} returned an invalid RecordBatch")

    def invalid_location(ref):
        raise source_map.error(key, f"adapter export {name!r} returned invalid source location for {ref}")

    try:
        loader = workspace.export(name, declaration=key)
        result = loader(workspace)
    except LocatedError:
        raise
    except ValueError as exc:
        # RecordRef enforces its lexical identity at construction. An adapter
        # may fail there before it can return its canonical source location.
        if re.match(r"^invalid .+ identity: ", str(exc)):
            raise source_map.error(key, str(exc)) from exc
        raise source_map.error(key, f"cannot load adapter {registration.module}: {exc}") from exc
    except Exception as exc:
        raise source_map.error(key, f"cannot load adapter {registration.module}: {exc}") from exc

    if (not isinstance(result, RecordBatch) or not isinstance(result.records, tuple)
            or not isinstance(result.relationships, tuple)):
        invalid_batch()

    adapter_kinds = {kind.name for kind in workspace.record_kinds if kind.reader == "adapter"}
    all_paths = {path for paths in workspace.sources.values() for path in paths}
    line_counts = {}

    def valid_location(location, allowed):
        if (not isinstance(location, SourceLocation) or not isinstance(location.path, str)
                or location.path not in allowed or type(location.line) is not int
                or location.line < 1
                or (location.anchor is not None and
                    (not isinstance(location.anchor, str) or not location.anchor.strip()))):
            return False
        if location.path not in line_counts:
            line_counts[location.path] = len(_read_source(workspace, location.path).splitlines())
        return location.line <= line_counts[location.path]

    for record in result.records:
        if (not isinstance(record, Record) or not isinstance(record.ref, RecordRef)
                or not isinstance(record.ref.kind, str) or record.ref.kind not in adapter_kinds
                or (record.title is not None and not isinstance(record.title, str))
                or (record.status is not None and not isinstance(record.status, str))
                or any(not isinstance(k, str) or not isinstance(v, str)
                       for k, v in record.fields.items())):
            invalid_batch()
        paths = workspace.sources[record.ref.kind]
        if not valid_location(record.source, paths):
            invalid_location(record.ref)
        for key_name in record.fields:
            if key_name not in record.field_locations:
                invalid_location(record.ref)
        for location in record.field_locations.values():
            if not valid_location(location, paths):
                invalid_location(record.ref)
        validate_identity(record.ref.kind, workspace.ids[record.ref.kind], record.ref.id, record.source)
    for row in result.relationships:
        if (not isinstance(row, RelationshipRow) or not isinstance(row.source, RecordRef)
                or not isinstance(row.target, RecordRef) or not isinstance(row.kind, str)
                or not isinstance(row.source.kind, str) or not isinstance(row.target.kind, str)
                or not isinstance(row.role, str)):
            invalid_batch()
        if not valid_location(SourceLocation(row.source_path, row.source_line), all_paths):
            invalid_location(row.source)
    return result


def load_records(workspace: Workspace) -> RecordBatch:
    """Combine generic sources and one adapter batch, without graph semantics."""
    records = []
    relationships = []
    for kind in workspace.record_kinds:
        if kind.reader == "adapter":
            continue
        for path in workspace.sources[kind.name]:
            batch = read_record(workspace, kind, path)
            records.extend(batch.records)
            relationships.extend(batch.relationships)
    adapter = _adapter_records(workspace)
    records.extend(adapter.records)
    relationships.extend(adapter.relationships)
    result = RecordBatch(tuple(records), tuple(relationships))
    # Identity uniqueness is required by the bidirectional resolver. Do not
    # check graph endpoints, roles, degrees or duplicate edges in this layer.
    result.resolver()
    return result
