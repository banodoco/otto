"""Read-only pipeline declarations and traversal over the shared record graph."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Iterable, Iterator, Mapping

from .config import DeclarationSourceMap, KeyPath, Workspace, _Validator, _inside, read_declaration
from .ids import RecordRef, SourceLocation
from .records import load_records
from .relationships import (
    RelationKind, Relationship, RelationshipError, RelationshipIndex,
    RelationshipSchema, cardinality_bounds,
)


_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_ENDS = ("per_source", "per_target")
Bounds = tuple[int, int | None]


@dataclass(frozen=True)
class Stage:
    id: str
    kinds: frozenset[str]
    source: SourceLocation
    key: KeyPath
    optional: bool = False
    statuses: tuple[str, ...] | None = None


@dataclass(frozen=True)
class PipelineLink:
    relation: str
    from_stage: str
    to_stage: str
    source: SourceLocation
    key: KeyPath
    per_source: str
    per_target: str
    by_role: Mapping[str, Mapping[str, str]]

    def __post_init__(self):
        object.__setattr__(self, "by_role", MappingProxyType({
            role: MappingProxyType(dict(bounds))
            for role, bounds in self.by_role.items()
        }))


@dataclass(frozen=True)
class Pipeline:
    id: str
    stages: tuple[Stage, ...]
    links: tuple[PipelineLink, ...]  # adjacent display order, not arrow order
    source: SourceLocation
    source_map: DeclarationSourceMap


@dataclass(frozen=True)
class PipelinePath:
    """Stage-slot identities and original edges between adjacent slots."""

    refs: tuple[RecordRef | None, ...]
    edges: tuple[Relationship | None, ...]


class _Declaration(_Validator):
    """Use the workspace reader's structural checks with a pipeline root label."""

    @staticmethod
    def label(key: KeyPath) -> str:
        return ".".join(str(part) for part in key if not isinstance(part, int)) or "pipeline"

    def name(self, value, key: KeyPath, label: str) -> str:
        value = self.string(value, key)
        if not _NAME.fullmatch(value):
            self.fail(key, f"invalid {label} {value!r}; expected lowercase kebab-case")
        return value

    def token(self, value, key: KeyPath) -> str:
        value = self.string(value, key)
        try:
            cardinality_bounds(value)
        except RelationshipError as exc:
            self.fail(key, exc.message)
        return value

    def stage(self, raw, key: KeyPath, pipeline: str,
              schema: RelationshipSchema) -> Stage:
        self.table(raw, key, {"id", "kinds", "optional", "statuses"}, ("id", "kinds"))
        id = self.name(raw["id"], key + ("id",), "stage id")
        values = self.strings(raw["kinds"], key + ("kinds",))
        if not values:
            self.fail(key + ("kinds",), "stages.kinds must be nonempty")
        seen = set()
        for i, value in enumerate(values):
            where = key + ("kinds", i)
            if value in seen:
                self.fail(where, f"stages.kinds contains duplicate {value!r}")
            if value not in schema.record_kinds:
                self.fail(where, f"pipeline {pipeline} stage {id} names unknown kind {value!r}")
            seen.add(value)

        optional = self.boolean(raw.get("optional", False), key + ("optional",))
        statuses = None
        if "statuses" in raw:
            status_key = key + ("statuses",)
            message = f"pipeline {pipeline} stage {id} statuses must be nonempty unique strings"
            items = raw["statuses"]
            if not isinstance(items, list) or not items:
                self.fail(status_key, message)
            used = set()
            for i, item in enumerate(items):
                if not isinstance(item, str) or not item.strip() or item in used:
                    self.fail(status_key + (i,), message)
                used.add(item)
            statuses = tuple(items)
        return Stage(id, frozenset(seen), self.source.location(key), key, optional, statuses)

    def link(self, raw, key: KeyPath, pipeline: str,
             schema: RelationshipSchema, stages: Mapping[str, Stage],
             positions: Mapping[str, int]) -> tuple[int, PipelineLink]:
        self.table(raw, key, {"relation", "from", "to", *_ENDS, "by_role"},
                   ("relation", "from", "to"))
        relation = self.string(raw["relation"], key + ("relation",))
        rule = schema.relation_kinds.get(relation)
        if rule is None:
            self.fail(key + ("relation",), f"pipeline {pipeline} names unknown relation {relation!r}")
        endpoints = {}
        for end in ("from", "to"):
            name = self.string(raw[end], key + (end,))
            if name not in stages:
                self.fail(key + (end,), f"pipeline {pipeline} link names unknown stage {name!r}")
            endpoints[end] = stages[name]
        source, target = endpoints["from"], endpoints["to"]
        a, b = sorted((positions[source.id], positions[target.id]))
        if b != a + 1:
            names = sorted((source.id, target.id), key=positions.__getitem__)
            self.fail(key + ("from",), _topology(pipeline, *names))
        for end, stage, allowed in (("from", source, rule.sources), ("to", target, rule.targets)):
            if not stage.kinds <= allowed:
                self.fail(key + (end,),
                          f"pipeline {pipeline} link {relation} endpoints do not match "
                          f"stages {source.id} -> {target.id}")

        totals = {end: self.token(raw.get(end, "any"), key + (end,)) for end in _ENDS}
        by_role = {}
        if "by_role" in raw:
            roles = self.table(raw["by_role"], key + ("by_role",))
            for role, bounds in roles.items():
                role_key = key + ("by_role", role)
                if role not in rule.roles:
                    self.fail(role_key, f"pipeline {pipeline} link {relation} has "
                                        f"cardinality for unknown role {role!r}")
                self.table(bounds, role_key, set(_ENDS))
                by_role[role] = {end: self.token(token, role_key + (end,))
                                 for end, token in bounds.items()}
        link = PipelineLink(relation, source.id, target.id, self.source.location(key),
                            key, totals["per_source"], totals["per_target"], by_role)
        self.bounds(pipeline, raw, link, rule, source, target)
        return a, link

    def bounds(self, pipeline: str, raw: dict, link: PipelineLink, rule: RelationKind,
               source: Stage, target: Stage) -> None:
        # The opposite stage is the population counted by each end.
        facing = (("per_source", target), ("per_target", source))
        for end, stage in facing:
            if not stage.optional:
                continue
            if getattr(link, end) == "exactly-one":
                self.fail(link.key + (end,), f"pipeline {pipeline}: optional stage {stage.id} "
                          f"conflicts with exactly-one {end} on {link.relation}")
            for role, bounds in link.by_role.items():
                if bounds.get(end) == "exactly-one":
                    self.fail(link.key + ("by_role", role, end),
                              f"pipeline {pipeline}: optional stage {stage.id} conflicts with "
                              f"exactly-one {end} for role {role} on {link.relation}")
            if (cardinality_bounds(getattr(rule, end))[0] > 0
                    or any(cardinality_bounds(bounds.get(end, "any"))[0] > 0
                           for bounds in rule.by_role.values())):
                self.fail(stage.key + ("optional",),
                          f"pipeline {pipeline}: optional stage {stage.id} "
                          f"conflicts with global minimum on {link.relation}")

        # Intersect totals and each role independently, then ensure the
        # summed role intervals can actually realize the resulting total.
        for end, stage in facing:
            direction = end.removeprefix("per_")
            message = f"pipeline {pipeline} has incompatible bounds for {link.relation} at {direction}"

            def intersect(local: str, global_: str, where: KeyPath) -> Bounds:
                value = _intersection(effective_bounds(local, optional=stage.optional),
                                      cardinality_bounds(global_))
                if value[1] is not None and value[0] > value[1]:
                    self.fail(where, message)
                return value

            total = intersect(getattr(link, end), getattr(rule, end), link.key + (end,))
            role_ranges = [
                intersect(link.by_role.get(role, {}).get(end, "any"),
                          rule.by_role.get(role, {}).get(end, "any"),
                          link.key + ("by_role", role, end))
                for role in sorted(rule.roles)
            ]
            role_sum = (sum(lo for lo, _ in role_ranges),
                        None if any(hi is None for _, hi in role_ranges)
                        else sum(hi for _, hi in role_ranges))
            low, high = _intersection(total, role_sum)
            if high is not None and low > high:
                # If the total is implicit, point at a contributing authored
                # role bound rather than a nonexistent total key.
                where = link.key + (end,)
                if end not in raw:
                    for role, bounds in link.by_role.items():
                        if end in bounds:
                            where = link.key + ("by_role", role, end)
                            break
                self.fail(where, message)


def effective_bounds(token: str, *, optional: bool = False) -> Bounds:
    """A validated pipeline bound, relaxed only at the optional-facing end."""
    low, high = cardinality_bounds(token)
    return (0 if optional else low), high


def _intersection(left: Bounds, right: Bounds) -> Bounds:
    highs = [hi for hi in (left[1], right[1]) if hi is not None]
    return max(left[0], right[0]), min(highs) if highs else None


def _topology(id: str, a: str, b: str) -> str:
    return f"pipeline {id} requires exactly one link between adjacent stages {a} and {b}"


def load_pipeline(path: Path, schema: RelationshipSchema, *,
                  display_path: str | None = None) -> Pipeline:
    """Read and validate one declaration, with its exact authored locations."""
    path = Path(path)
    raw, source = read_declaration(path, display_path=display_path)
    v = _Declaration(path.parent, raw, source)
    v.table(raw, (), {"version", "id", "stages", "links"},
            ("version", "id", "stages", "links"))
    version = raw["version"]
    if type(version) is not int:
        v.fail(("version",), "version must be an integer")
    if version != 1:
        v.fail(("version",), f"unsupported declaration version {version}; expected 1")
    id = v.name(raw["id"], ("id",), "pipeline id")
    if id != path.stem:
        v.fail(("id",), f"pipeline id {id!r} does not match filename {path.stem!r}")

    entries = v.tables(raw["stages"], ("stages",))
    if len(entries) < 2:
        v.fail(("stages",), f"pipeline {id} requires at least two stages")
    stages = {}
    for i, entry in enumerate(entries):
        stage = v.stage(entry, ("stages", i), id, schema)
        if stage.id in stages:
            v.fail(stage.key + ("id",), f"pipeline {id} repeats stage {stage.id!r}")
        stages[stage.id] = stage
    positions = {name: i for i, name in enumerate(stages)}
    links = {}
    for i, entry in enumerate(v.tables(raw["links"], ("links",))):
        pair, link = v.link(entry, ("links", i), id, schema, stages, positions)
        if pair in links:
            names = tuple(stages)
            v.fail(link.key + ("from",), _topology(id, names[pair], names[pair + 1]))
        links[pair] = link
    names = tuple(stages)
    for i, (a, b) in enumerate(zip(names, names[1:])):
        if i not in links:
            v.fail(("links",), _topology(id, a, b))
    return Pipeline(id, tuple(stages.values()), tuple(links[i] for i in sorted(links)),
                    source.location(("id",)), source)


def _read_error(source: SourceLocation, exc: BaseException):
    from .ids import LocatedError
    return LocatedError(source, f"cannot read {source.path}: {getattr(exc, 'strerror', None) or exc}")


def load_pipeline_inventory(paths: Iterable[Path], schema: RelationshipSchema, *,
                            root: Path | None = None) -> Mapping[str, Pipeline]:
    """Load explicit paths (also the duplicate-ID seam); never coalesce IDs."""
    result = {}
    for path in sorted(map(Path, paths)):
        display = path.as_posix() if root is None else path.relative_to(root).as_posix()
        location = SourceLocation(display, 1)
        source = DeclarationSourceMap(display, {(): 1})
        if root is not None:
            _inside(root, path, source=source, key=(), label="pipeline declaration")
        try:
            mode = path.stat().st_mode
        except OSError as exc:
            raise _read_error(location, exc) from exc
        if not stat.S_ISREG(mode):
            raise source.error((), "pipeline declaration must name a file")
        pipeline = load_pipeline(path, schema, display_path=display)
        if pipeline.id in result:
            raise pipeline.source_map.error(("id",), f"duplicate pipeline id {pipeline.id!r}")
        result[pipeline.id] = pipeline
    return MappingProxyType(dict(sorted(result.items())))


def load_pipelines(workspace: Workspace, *,
                   schema: RelationshipSchema | None = None) -> Mapping[str, Pipeline]:
    """Discover only the configured shallow inventory, not record sources."""
    if schema is None:
        schema = RelationshipSchema.from_workspace(workspace)
    directory = workspace.paths["pipelines"]
    key = ("paths", "pipelines")
    _inside(workspace.root, directory, source=workspace.source_map,
            key=key, label="paths.pipelines")
    try:
        mode = directory.stat().st_mode
    except FileNotFoundError:
        return MappingProxyType({})
    except OSError as exc:
        raise _read_error(workspace.source_map.location(key), exc) from exc
    if not stat.S_ISDIR(mode):
        raise workspace.source_map.error(key, "paths.pipelines must name a directory")
    try:
        paths = [path for path in directory.iterdir() if path.suffix == ".toml"]
    except OSError as exc:
        location = SourceLocation(directory.relative_to(workspace.root).as_posix(), 1)
        raise _read_error(location, exc) from exc
    return load_pipeline_inventory(paths, schema, root=workspace.root)


def _extensions(pipeline: Pipeline, index: RelationshipIndex, start: int,
                record: RecordRef, step: int
                ) -> Iterator[tuple[tuple[RecordRef | None, ...], tuple[Relationship | None, ...]]]:
    """Extend one side of an anchored path, using only authored edges."""
    count = len(pipeline.stages)
    stack = [(start, (record,), ())]
    while stack:
        pos, refs, edges = stack.pop()
        neighbor = pos + step
        if not 0 <= neighbor < count:
            yield refs, edges
            continue
        link = pipeline.links[min(pos, neighbor)]
        current = refs[-1]
        if pipeline.stages[pos].id == link.from_stage:
            candidates = ((e.target, e) for e in index.outgoing(current, link.relation))
        else:
            candidates = ((e.source, e) for e in index.incoming(current, link.relation))
        visited = {(start + step * i, ref) for i, ref in enumerate(refs)}
        options = [(ref, edge) for ref, edge in candidates
                   if ref.kind in pipeline.stages[neighbor].kinds
                   and (neighbor, ref) not in visited]
        if options:
            for ref, edge in options:
                stack.append((neighbor, refs + (ref,), edges + (edge,)))
        else:
            remaining = tuple(range(neighbor, count if step == 1 else -1, step))
            if all(pipeline.stages[i].optional for i in remaining):
                absent = (None,) * len(remaining)
                yield refs + absent, edges + absent


def _path_key(path: PipelinePath):
    return (tuple("-" if ref is None else str(ref) for ref in path.refs),
            tuple(("", "") if edge is None else (edge.role, edge.kind)
                  for edge in path.edges))


def traverse(pipeline: Pipeline, index: RelationshipIndex,
             record: RecordRef | None = None) -> tuple[PipelinePath, ...]:
    """Return distinct complete paths, sorted by stage slots then edge roles/kinds.

    Each query is anchored at every participating position of its record.
    For an unanchored enumeration a required stage is sufficient as a seed;
    with no required stages use every position, never an all-empty path.
    """
    positions = range(len(pipeline.stages))
    if record is None:
        required = next((i for i in positions if not pipeline.stages[i].optional), None)
        if required is not None:
            positions = (required,)
    candidates = index.records if record is None else (
        (record,) if record in index.records else ())
    found = {}
    for pos in positions:
        for ref in sorted(candidates):
            if ref.kind not in pipeline.stages[pos].kinds:
                continue
            for left_refs, left_edges in _extensions(pipeline, index, pos, ref, -1):
                for right_refs, right_edges in _extensions(pipeline, index, pos, ref, 1):
                    path = PipelinePath(tuple(reversed(left_refs)) + right_refs[1:],
                                        tuple(reversed(left_edges)) + right_edges)
                    found[_path_key(path)] = path
    return tuple(found[key] for key in sorted(found))


def _resolve_record(pipeline: Pipeline, index: RelationshipIndex, value: str) -> RecordRef | None:
    kinds = frozenset(kind for stage in pipeline.stages for kind in stage.kinds)
    prefix, colon, id = value.partition(":")
    candidates = sorted((ref for ref in index.records if ref.kind in kinds
                         and ((ref.kind == prefix and ref.id == id)
                              if colon and prefix in kinds else ref.id == value)), key=str)
    if len(candidates) > 1:
        raise ValueError(f"ambiguous record id {value!r}: {', '.join(map(str, candidates))}")
    return candidates[0] if candidates else None


def _render(pipeline: Pipeline, path: PipelinePath) -> str:
    slots = []
    for i, (stage, ref) in enumerate(zip(pipeline.stages, path.refs)):
        slot = f"{stage.id}={'-' if ref is None else ref}"
        if i and path.edges[i - 1] is not None:
            edge = path.edges[i - 1]
            slot += f" ({edge.kind}, {edge.role})"
        slots.append(slot)
    return " -> ".join(slots)


def list_pipelines(workspace: Workspace) -> str:
    """Return sorted IDs, one per line, or empty text."""
    return "".join(f"{id}\n" for id in load_pipelines(workspace))


def show_pipeline(workspace: Workspace, id: str, record_id: str | None = None, *,
                  schema: RelationshipSchema | None = None,
                  index: RelationshipIndex | None = None) -> str:
    """Return query text; an unknown record is a successful empty lookup."""
    if schema is None:
        schema = RelationshipSchema.from_workspace(workspace)
    pipeline = load_pipelines(workspace, schema=schema).get(id)
    if pipeline is None:
        raise ValueError(f"unknown pipeline {id!r}")
    if index is None:
        index = RelationshipIndex.from_batch(load_records(workspace), schema=schema)
    ref = None
    if record_id is not None:
        ref = _resolve_record(pipeline, index, record_id)
        if ref is None:
            return f"Unknown record {record_id}\n"
    return "".join(_render(pipeline, path) + "\n" for path in traverse(pipeline, index, ref))
