"""Template declarations and read-only project pack shape checks (OT-11).

The inventory is data, not executable guidance. The package root is injectable
for tests and for the distribution resource locator; workspace manifests never
override package manifests. Historical adapters are never imported.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import errno
from fnmatch import fnmatchcase
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import subprocess
import tempfile
from types import MappingProxyType
from typing import Iterable, Mapping

from . import markdown
from .checks import Context
from .config import Workspace, _path_reason, load_workspace, read_declaration
from .git import git_result
from .ids import LocatedError, RecordRef, SourceLocation, identity_from_path
from .records import Record, RecordBatch, _live_lines, _read_source, load_records


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
COMMON = ("plan.md", "inputs.md", "tasks.md")
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TASK_ID = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[.-][A-Za-z0-9]+)*")


@dataclass(frozen=True)
class DocumentRequirement:
    path: str
    source: Path
    headings: tuple[str, ...]
    task_reference_field: str | None = None


@dataclass(frozen=True)
class TemplateManifest:
    name: str
    workstream: Path
    anchor: str | None
    documents: tuple[DocumentRequirement, ...]
    location: SourceLocation


@dataclass(frozen=True)
class TemplateSelection:
    name: str
    explicit: bool
    location: SourceLocation


@dataclass(frozen=True)
class CommonShape:
    plan_headings: tuple[str, ...]
    inputs_headings: tuple[str, ...]
    task_header: tuple[str, ...]


@dataclass(frozen=True)
class BasePack:
    """Canonical plan path and its text at base, keyed by stable RecordRef."""

    path: str
    text: str


def _display(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _error(location: SourceLocation, message: str):
    raise LocatedError(location, message)


def _read_failure(location: SourceLocation, exc: BaseException):
    _error(location, f"cannot read {location.path}: {getattr(exc, 'strerror', None) or exc}")


def _contained(root: Path, path: Path, location: SourceLocation, message: str) -> Path:
    """Reject lexical/resolved escapes and dangling or cyclic input aliases."""
    try:
        if not path.is_relative_to(root) or not path.resolve().is_relative_to(root):
            _error(location, message)
        for component in (path, *path.parents):
            if component == root:
                break
            if component.is_symlink():
                try:
                    component.resolve(strict=True)
                except (FileNotFoundError, RuntimeError):
                    _error(location, message)
    except RuntimeError:
        _error(location, message)
    except OSError as exc:
        _read_failure(location, exc)
    return path


def _relative(root: Path, value: str, location: SourceLocation, message: str) -> Path:
    if _path_reason(value, allow_dot=False):
        _error(location, message)
    return _contained(root, root / value, location, message)


def _mode(path: Path, location: SourceLocation) -> int | None:
    try:
        return path.stat().st_mode
    except FileNotFoundError:
        return None
    except OSError as exc:
        _read_failure(location, exc)


def _file(path: Path, location: SourceLocation) -> bool:
    mode = _mode(path, location)
    return mode is not None and stat.S_ISREG(mode)


def _read(path: Path, location: SourceLocation) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        _read_failure(location, exc)


def _h2(text: str) -> list[tuple[str, int]]:
    return [(title, line) for line, value in enumerate(_live_lines(text), 1)
            for level, title, _ in markdown.markdown_heading_anchors(value)
            if level == 2]


def _h1(text: str) -> int:
    return next((line for line, value in enumerate(_live_lines(text), 1)
                 if any(level == 1 for level, _, _ in markdown.markdown_heading_anchors(value))), 1)


def _heading_problem(text: str, required: Iterable[str]) -> tuple[str, bool, int] | None:
    actual = _h2(text)
    titles = [title for title, _ in actual]
    cursor = 0
    for heading in required:
        try:
            cursor = titles.index(heading, cursor) + 1
        except ValueError:
            if heading in titles:
                return heading, True, actual[titles.index(heading)][1]
            return heading, False, _h1(text)
    return None


def _table(value, key, label, allowed, required, source):
    if not isinstance(value, dict):
        raise source.error(key, f"{label} must be a table")
    for name in value:
        if name not in allowed:
            raise source.error(key + (name,), f"unknown key {name!r} in {label}")
    for name in required:
        if name not in value:
            raise source.error(key, f"missing required key {name!r} in {label}")


def _string(value, key, label, source):
    if not isinstance(value, str):
        raise source.error(key, f"{label} must be a string")
    if not value.strip():
        raise source.error(key, f"{label} must be a nonempty string")
    return value


def load_manifest(path: Path, owner_root: Path, template_root: Path, *,
                  owner_label: str = "workspace root") -> TemplateManifest:
    """Load and validate one manifest and its referenced authored sources."""
    owner_root = Path(owner_root).resolve()
    template_root = Path(template_root)
    path = Path(path)
    if not path.is_absolute():
        path = owner_root / path
    if not template_root.is_absolute():
        template_root = owner_root / template_root
    location = SourceLocation(_display(owner_root, path) if path.is_relative_to(owner_root)
                              else "templates", 1)
    root_message = f"template root must resolve inside {owner_label}"
    _contained(owner_root, template_root, location, root_message)
    _contained(owner_root, path, location, root_message)
    if not path.is_relative_to(template_root):
        _error(location, root_message)
    _contained(template_root.resolve(), template_root.resolve() / path.relative_to(template_root),
               location, root_message)
    if len(path.relative_to(template_root).parts) != 2 or path.name != "template.toml":
        _error(location, "template manifests must be one level below the template root")
    data, source = read_declaration(path, display_path=location.path)
    _table(data, (), "template", {"version", "name", "workstream", "documents"},
           ("version", "name", "workstream"), source)
    if type(data["version"]) is not int:
        raise source.error(("version",), "version must be an integer")
    if data["version"] != 1:
        raise source.error(("version",), f"unsupported declaration version {data['version']}; expected 1")
    name = _string(data["name"], ("name",), "name", source)
    if not NAME.fullmatch(name):
        raise source.error(("name",), f"invalid template name {name!r}; expected lowercase kebab-case")
    if name != path.parent.name:
        raise source.error(("name",), f"template name {name!r} does not match directory {path.parent.name!r}")

    reference = _string(data["workstream"], ("workstream",), "workstream", source)
    address, separator, anchor = reference.partition("#")
    where = source.location(("workstream",))
    workstream = _relative(owner_root, address, where,
                           f"template {name}: workstream must resolve inside {owner_label}")
    if workstream.suffix != ".md":
        _error(where, f"template {name}: workstream must name a Markdown document")
    if not _file(workstream, where):
        _error(where, f"template {name}: workstream target does not exist: {reference}")
    if separator:
        text = _read(workstream, where)
        anchors = {value for _, _, value in markdown.markdown_heading_anchors("\n".join(_live_lines(text)))}
        if not anchor or anchor not in anchors:
            _error(where, f"template {name}: workstream anchor does not exist: {reference}")

    raw_documents = data.get("documents", [])
    if not isinstance(raw_documents, list):
        raise source.error(("documents",), "documents must be an array of tables")
    documents = []
    seen = set(COMMON)
    manifest_directory = path.parent.resolve()
    for index, entry in enumerate(raw_documents):
        key = ("documents", index)
        if not isinstance(entry, dict):
            raise source.error(key, "documents must be an array of tables")
        _table(entry, key, "documents", {"path", "source", "headings", "task_reference_field"},
               ("path", "source", "headings"), source)
        document_path = _string(entry["path"], key + ("path",), "documents.path", source)
        # A pack-relative path is validated lexically here and against the
        # actual pack's resolved root when the document is checked.
        if _path_reason(document_path, allow_dot=False):
            raise source.error(key + ("path",), f"template {name}: documents.path must resolve inside pack root")
        normalized = PurePosixPath(document_path).as_posix()
        if normalized in seen:
            raise source.error(key + ("path",), f"template {name}: duplicate or common document path {normalized!r}")
        seen.add(normalized)
        example = _string(entry["source"], key + ("source",), "documents.source", source)
        where = source.location(key + ("source",))
        example_path = _relative(manifest_directory, example, where,
                                 f"template {name}: documents.source must resolve inside manifest directory")
        required = entry["headings"]
        if (not isinstance(required, list) or not required
                or any(not isinstance(h, str) or not h.strip() for h in required)
                or len(set(required)) != len(required)):
            raise source.error(key + ("headings",), f"template {name}: headings must be nonempty unique strings")
        field = None
        if "task_reference_field" in entry:
            field = _string(entry["task_reference_field"], key + ("task_reference_field",),
                            "documents.task_reference_field", source)
        if not _file(example_path, where):
            _error(where, f"template {name}: missing document source {example!r}")
        problem = _heading_problem(_read(example_path, where), required)
        if problem:
            heading, out_of_order, _ = problem
            message = (f"heading '## {heading}' is out of order" if out_of_order
                       else f"is missing heading '## {heading}'")
            _error(where, f"template {name}: document source {example} {message}")
        documents.append(DocumentRequirement(normalized, example_path, tuple(required), field))
    return TemplateManifest(name, workstream, anchor if separator else None,
                            tuple(documents), source.location(("name",)))


def _manifest_paths(owner: Path, root: Path, label: str, location: SourceLocation):
    """Discover shallow manifests; detect deeper declarations and bad aliases."""
    message = f"template root must resolve inside {label}"
    _contained(owner, root, location, message)
    mode = _mode(root, location)
    if mode is None:
        return
    if not stat.S_ISDIR(mode):
        _error(location, "template root must name a directory")

    def walk(directory: Path, ancestors: frozenset[Path]):
        resolved = directory.resolve()
        if resolved in ancestors:
            _error(SourceLocation(_display(owner, directory), 1), message)
        try:
            entries = sorted(directory.iterdir())
        except OSError as exc:
            _read_failure(SourceLocation(_display(owner, directory), 1), exc)
        for path in entries:
            where = SourceLocation(_display(owner, path), 1)
            if path.name == "template.toml":
                _contained(owner, path, where, message)
                _contained(root.resolve(), root.resolve() / path.relative_to(root), where, message)
                if len(path.relative_to(root).parts) != 2:
                    _error(where, "template manifests must be one level below the template root")
                mode = _mode(path, where)
                if mode is not None and not stat.S_ISREG(mode):
                    code = errno.EISDIR if stat.S_ISDIR(mode) else errno.EINVAL
                    _read_failure(where, OSError(code, os.strerror(code)))
                yield path
            else:
                # Non-manifest files are validated at the key which actually
                # references them, not as anonymous inventory entries.
                mode = _mode(path, where)
                if mode is not None and stat.S_ISDIR(mode):
                    _contained(owner, path, where, message)
                    _contained(root.resolve(), root.resolve() / path.relative_to(root), where, message)
                    yield from walk(path, ancestors | {resolved})

    yield from walk(root, frozenset())


def discover_templates(workspace: Workspace, *, package_root: Path = PACKAGE_ROOT
                       ) -> Mapping[str, TemplateManifest]:
    package_root = Path(package_root).resolve()
    inventory = {}
    roots = (
        (package_root, package_root / "templates", "package root", SourceLocation("templates", 1)),
        (workspace.root, workspace.paths["templates"], "workspace root",
         workspace.source_map.location(("paths", "templates"))),
    )
    for owner, root, label, where in roots:
        for path in _manifest_paths(owner, root, label, where):
            manifest = load_manifest(path, owner, root, owner_label=label)
            if manifest.name in inventory:
                _error(manifest.location, f"duplicate template name {manifest.name!r}")
            inventory[manifest.name] = manifest
    return MappingProxyType(inventory)


def _field_rows(text: str, field: str):
    """Return live header, fenced header, and live body declarations."""
    pattern = re.compile(r"^ {0,3}\*\*" + re.escape(field) + r":\*\*[ \t]*(.*)$")
    live = _live_lines(text)
    first_h2 = next((line for _, line in _h2(text)), len(live) + 1)
    header, fenced, body = [], [], []
    for line, (raw, active) in enumerate(zip(text.splitlines(), live), 1):
        match = pattern.fullmatch(raw)
        if match:
            value = match[1].strip()
            if line < first_h2:
                (header if active else fenced).append((line, value))
            elif active:
                body.append((line, value))
    return header, fenced, body


def _selection(text: str, source: SourceLocation) -> TemplateSelection:
    header, fenced, body = _field_rows(text, "Template")
    if len(header) > 1:
        _error(SourceLocation(source.path, header[1][0]), "duplicate Template field")
    if header:
        line, value = header[0]
        location = SourceLocation(source.path, line)
        if not value:
            _error(location, "empty Template field")
        if not NAME.fullmatch(value):
            _error(location, f"unknown project template '{value}'")
        return TemplateSelection(value, True, location)
    if fenced:
        _error(SourceLocation(source.path, fenced[0][0]), "Template declaration is inside a fenced block")
    if body:
        _error(SourceLocation(source.path, body[0][0]), "Template must be in the project header")
    return TemplateSelection("standard", False, source)


def select_template(text: str, source: SourceLocation,
                    templates: Mapping[str, TemplateManifest]) -> TemplateSelection:
    selection = _selection(text, source)
    if selection.name not in templates:
        _error(selection.location, f"unknown project template {selection.name!r}")
    return selection


def _cells(line: str) -> tuple[str, ...] | None:
    line = line.strip()
    if "|" not in line:
        return None
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return tuple(cell.strip() for cell in line.split("|"))


def _separator(cells: tuple[str, ...] | None) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{1,}:?", cell) for cell in cells)


def _tables(text: str):
    """Yield live table headers, their authored lines, and consecutive data rows."""
    lines = _live_lines(text)
    index = 0
    while index + 1 < len(lines):
        header = _cells(lines[index])
        separator = _cells(lines[index + 1])
        if not header or _separator(header) or not _separator(separator) or len(header) != len(separator):
            index += 1
            continue
        header_line = index + 1
        index += 2
        rows = []
        while index < len(lines):
            cells = _cells(lines[index])
            if cells is None:
                break
            if (index + 1 < len(lines) and _separator(_cells(lines[index + 1]))
                    and len(cells) == len(_cells(lines[index + 1]))):
                break
            if len(cells) == len(header) and not _separator(cells) and cells != header:
                rows.append(cells)
            index += 1
        yield header, header_line, rows


def _task_ids(text: str, task_header: tuple[str, ...]) -> Counter:
    ids = Counter()
    for header, _, rows in _tables(text):
        if header != task_header:
            continue
        for row in rows:
            cell = row[0].strip()
            marker_match = re.match(r"^(\*\*|" + re.escape(chr(96)) + r"+)", cell)
            if marker_match:
                marker = marker_match[1]
                close = cell.find(marker, len(marker))
                tail = cell[close + len(marker):] if close != -1 else ""
                if close == -1 or (tail and not tail[0].isspace()):
                    continue
                cell = cell[len(marker):close]
            token = cell.split(maxsplit=1)[0] if cell.strip() else ""
            if TASK_ID.fullmatch(token):
                ids[token] += 1
    return ids


def common_shape(workspace: Workspace, *, package_root: Path = PACKAGE_ROOT) -> CommonShape:
    """The workspace common pack replaces, rather than inherits, the default."""
    if "pack_templates" in workspace.paths:
        owner = workspace.root
        directory = workspace.paths["pack_templates"]
        where = workspace.source_map.location(("paths", "pack_templates"))
    else:
        owner = Path(package_root).resolve()
        directory = owner / "templates" / "project"
        where = SourceLocation("otto.toml", 1)
    headings = []
    task_header = None
    for name in COMMON:
        path = directory / name
        _contained(owner, path, where, "template root must resolve inside " +
                   ("workspace root" if "pack_templates" in workspace.paths else "package root"))
        _contained(directory.resolve(), directory.resolve() / name, where,
                   "template root must resolve inside manifest directory")
        if not _file(path, where):
            _error(where, f"common pack: missing template document {name}")
        content = _read(path, SourceLocation(_display(owner, path), 1))
        location = SourceLocation(_display(owner, path), _h1(content))
        if name == "tasks.md":
            first = next(_tables(content), None)
            if first is None:
                _error(location, "common pack: template tasks.md has no task table")
            task_header = first[0]
        else:
            required = tuple(heading for heading, _ in _h2(content))
            if not required:
                _error(location, f"common pack: template {name} has no H2 headings")
            headings.append(required)
    return CommonShape(headings[0], headings[1], task_header)


def _base_commit(root: Path, base: str) -> str:
    result = git_result(root, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}")
    if result.returncode:
        _error(SourceLocation("otto.toml", 1),
               f"cannot compare template selection: base revision {base!r} is unavailable")
    return result.stdout.strip()


def _git(root: Path, *args: str) -> str:
    result = git_result(root, *args)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Git command failed")
    return result.stdout


def _matches(path: str, pattern: str) -> bool:
    parts = PurePosixPath(path).parts
    patterns = tuple(part for part in pattern.split("/") if part not in {"", "."})

    def match(i, j):
        if j == len(patterns):
            return i == len(parts)
        if patterns[j] == "**":
            return match(i, j + 1) or (i < len(parts) and match(i + 1, j))
        return i < len(parts) and fnmatchcase(parts[i], patterns[j]) and match(i + 1, j + 1)

    return match(0, 0)


def _rename_sources(root: Path, commit: str, roots: tuple[str, ...]) -> Mapping[str, set[str]]:
    """Plan-48-style rename evidence from an isolated index and object store.

    Includes committed, staged, unstaged and untracked changes, without
    updating the user's index or writing objects into their repository.
    """
    def git_path(name):
        value = Path(_git(root, "rev-parse", "--git-path", name).strip())
        return value if value.is_absolute() else root / value

    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        index = temporary / "index"
        real_index = git_path("index")
        if real_index.exists():
            shutil.copyfile(real_index, index)
        objects = temporary / "objects"
        objects.mkdir()
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(index)
        env["GIT_OBJECT_DIRECTORY"] = str(objects)
        alternates = [str(git_path("objects").resolve())]
        if env.get("GIT_ALTERNATE_OBJECT_DIRECTORIES"):
            alternates.append(env["GIT_ALTERNATE_OBJECT_DIRECTORIES"])
        env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = os.pathsep.join(alternates)

        def run(*args):
            result = subprocess.run(["git", "--literal-pathspecs", *args], cwd=root,
                                    env=env, text=True, capture_output=True, check=False)
            if result.returncode:
                raise ValueError(result.stderr.strip() or "Git comparison failed")
            return result.stdout

        run("add", "-A", "--", *roots)
        diff = run("diff", "--cached", "--relative", "-M20%", "--name-status", "-z",
                   commit, "--", *roots)

    renamed = {}
    fields = iter(diff.split("\0"))
    for status in fields:
        if not status:
            break
        old = PurePosixPath(next(fields))
        new = PurePosixPath(next(fields)) if status.startswith(("R", "C")) else old
        if (status.startswith("R") and old.parent != new.parent
                and old.name in COMMON and new.name in COMMON
                and not (root / old.parent).exists()):
            renamed.setdefault(new.parent.as_posix(), set()).add((old.parent / "plan.md").as_posix())
    return renamed


def _historical(workspace: Workspace, packs: tuple[Record, ...], commit: str
                ) -> Mapping[RecordRef, BasePack]:
    """Read base blobs, never a base checkout or historical executable adapter."""
    if not packs:
        return {}
    root = workspace.root
    prefix = _git(root, "rev-parse", "--show-prefix").rstrip("\n")
    tree = {}
    for entry in _git(root, "ls-tree", "-r", "-z", "--full-tree", commit).split("\0"):
        if not entry:
            continue
        metadata, path = entry.split("\t", 1)
        mode, kind, _ = metadata.split()
        if kind == "blob" and path.startswith(prefix):
            tree[path[len(prefix):]] = mode

    def base_path(path: str) -> str | None:
        original = path
        seen = set()
        while path not in seen:
            seen.add(path)
            parts = PurePosixPath(path).parts
            for i in range(1, len(parts) + 1):
                component = PurePosixPath(*parts[:i]).as_posix()
                if tree.get(component) == "120000":
                    target = _git(root, "show", f"{commit}:{prefix}{component}")
                    if target.startswith("/") or "\\" in target or re.match(r"^[A-Za-z]:", target):
                        raise ValueError(f"base source {component} escapes the workspace root")
                    path = posixpath.normpath(posixpath.join(posixpath.dirname(component), target, *parts[i:]))
                    if path == ".." or path.startswith("../"):
                        raise ValueError(f"base source {component} escapes the workspace root")
                    break
            else:
                if path in tree:
                    return path
                if original in tree and tree[original] == "120000":
                    raise ValueError(f"base source {original} is a dangling symlink")
                return None
        raise ValueError(f"base source {path} has a symlink cycle")

    kinds = {kind.name: kind for kind in workspace.record_kinds if kind.pack}
    roots = {name: workspace.paths[kind.root].relative_to(root).as_posix()
             for name, kind in kinds.items()}
    identities = {}
    for kind_name, kind in kinds.items():
        policy = workspace.ids[kind_name]
        if policy.source == "adapter":
            continue
        directory = PurePosixPath(roots[kind_name])
        for path in sorted(tree):
            relative = PurePosixPath(path)
            if relative.name != "plan.md" or not relative.is_relative_to(directory):
                continue
            if not any(_matches(relative.relative_to(directory).as_posix(), pattern)
                       for pattern in kind.files):
                continue
            try:
                ref = RecordRef(kind_name, identity_from_path(kind_name, policy, path))
            except LocatedError:
                continue  # not an eligible project under the configured locator
            identities.setdefault(ref, []).append(path)

    def choose(record, candidates):
        paths = sorted({path for path in candidates if base_path(path) is not None})
        if len(paths) > 1:
            raise ValueError(f"ambiguous base pack for {record.ref}: {', '.join(paths)}")
        if paths:
            path = paths[0]
            canonical = base_path(path)
            return BasePack(path, _git(root, "show", f"{commit}:{prefix}{canonical}"))
        return None

    found = {}
    unmatched = []
    for record in packs:
        # Stable configured identity wins over a path or similarity heuristic.
        prior = choose(record, identities.get(record.ref, ()))
        if prior is None:
            prior = choose(record, (record.source.path,))
        if prior is None:
            unmatched.append(record)
        else:
            found[record.ref] = prior
    if unmatched:
        renamed = _rename_sources(root, commit, tuple(sorted(set(roots.values()))))
        for record in unmatched:
            parent = PurePosixPath(record.source.path).parent.as_posix()
            prior = choose(record, renamed.get(parent, ()))
            if prior is not None:
                found[record.ref] = prior
    return found


def _pack_errors(workspace: Workspace, source: SourceLocation,
                 manifest: TemplateManifest, shape: CommonShape) -> list[LocatedError]:
    errors = []
    authored = PurePosixPath(source.path).parent
    pack = (workspace.root / authored).resolve()

    def document(name: str, common: bool):
        path = pack / name
        relative = (authored / name).as_posix()
        location = SourceLocation(relative, 1)
        prefix = "common pack" if common else f"template {manifest.name}"
        try:
            _contained(pack, path, location, f"template {manifest.name}: {name} must resolve inside pack root")
            if not _file(path, location):
                _error(source, f"{prefix}: missing required document {name}")
            return _read(path, location)
        except LocatedError as exc:
            errors.append(exc)
            return None

    def heading_errors(name, text, required, prefix):
        if text is None:
            return
        problem = _heading_problem(text, required)
        if problem:
            heading, out_of_order, line = problem
            message = (f"heading '## {heading}' is out of order" if out_of_order
                       else f"is missing heading '## {heading}'")
            errors.append(LocatedError(SourceLocation((authored / name).as_posix(), line),
                                       f"{prefix}: {name} {message}"))

    for name, required in (("plan.md", shape.plan_headings), ("inputs.md", shape.inputs_headings)):
        heading_errors(name, document(name, True), required, "common pack")
    tasks = document("tasks.md", True)
    if tasks is not None:
        header = next(_tables(tasks), None)
        if header is None:
            errors.append(LocatedError(source, "common pack: no task table; start the file's first table with the template's header row."))
        elif header[0] != shape.task_header:
            errors.append(LocatedError(SourceLocation((authored / "tasks.md").as_posix(), header[1]),
                                       "common pack: the first table's header row differs from the template's; copy it exactly."))

    ids = _task_ids(tasks, shape.task_header) if tasks is not None else Counter()
    for requirement in manifest.documents:
        name = requirement.path
        text = document(name, False)
        if text is None:
            continue
        prefix = f"template {manifest.name}"
        heading_errors(name, text, requirement.headings, prefix)
        field = requirement.task_reference_field
        if field is not None:
            header, _, _ = _field_rows(text, field)
            if len(header) != 1 or ids[header[0][1]] != 1:
                where = (SourceLocation((authored / name).as_posix(), header[min(1, len(header) - 1)][0])
                         if header else source)
                errors.append(LocatedError(where, f"{prefix}: {name} needs **{field}:** naming one existing task"))
    return errors


def check_pack_shape(workspace: Workspace, records: RecordBatch | Iterable[Record], *,
                     base: str | None = None, package_root: Path = PACKAGE_ROOT,
                     base_packs: Mapping[RecordRef, BasePack] | None = None) -> list[str]:
    """Check explicit opt-ins and new packs. A snapshot makes no history claim.

    A supplied base_packs is the complete prior inventory from a fixture or
    trusted adapter. In PR context the Git revision must still be available.
    """
    kinds = {kind.name for kind in workspace.record_kinds if kind.pack}
    packs = tuple(record for record in (records.records if isinstance(records, RecordBatch) else records)
                  if record.ref.kind in kinds)
    errors: list[LocatedError] = []
    try:
        commit = _base_commit(workspace.root, base) if base is not None else None
        history = base_packs if base_packs is not None else (
            _historical(workspace, packs, commit) if commit is not None else None)
    except LocatedError as exc:
        return [str(exc)]
    except (OSError, ValueError) as exc:
        return [str(LocatedError(SourceLocation("otto.toml", 1), f"cannot compare template selection: {exc}"))]
    try:
        templates = discover_templates(workspace, package_root=package_root)
    except LocatedError as exc:
        return [str(exc)]

    selected = []
    for record in packs:
        try:
            text = _read_source(workspace, record.source.path)
            source = SourceLocation(record.source.path, _h1(text))
            selection = _selection(text, source)
            previous = history.get(record.ref) if history is not None else None
            if not selection.explicit and previous is not None:
                old = _selection(previous.text, SourceLocation(previous.path, _h1(previous.text)))
                if old.explicit and old.name != "standard":
                    _error(source, f"explicit Template field removed from {record.ref}; write **Template:** standard to select standard deliberately")
            if selection.explicit or (history is not None and previous is None):
                if selection.name not in templates:
                    _error(selection.location, f"unknown project template {selection.name!r}")
                selected.append((source, templates[selection.name]))
        except LocatedError as exc:
            errors.append(exc)

    if selected:
        try:
            shape = common_shape(workspace, package_root=package_root)
        except LocatedError as exc:
            errors.append(exc)
        else:
            for source, manifest in selected:
                errors.extend(_pack_errors(workspace, source, manifest, shape))
    errors.sort(key=lambda error: (error.source.path, error.source.line, error.message))
    return [str(error) for error in errors]


def pack_shape(context: Context) -> list[str]:
    """Check runner entry point; register as always so explicit opt-ins run."""
    try:
        workspace = load_workspace(context.root)
        return check_pack_shape(workspace, load_records(workspace), base=context.base)
    except (OSError, ValueError) as exc:
        return [str(exc)]
