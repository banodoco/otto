"""Read the closed workspace declaration and retain its authored source locations.

This layer validates declaration shape and discovers contained source files.
Relation semantics, pipeline traversal, template validation and check/view
factory assembly belong to their respective consumers, not to configuration.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
import errno
from fnmatch import fnmatchcase
import importlib.util
import keyword
import os
from pathlib import Path
import re
import stat
import sys
import tomllib
from uuid import uuid4
from types import MappingProxyType, ModuleType
from typing import Callable, Mapping

from .ids import ID_PRESETS, ID_SOURCES, IdPolicy, LocatedError, SourceLocation
from .skills import (
    SkillConfig, _checkout_relative_path, _legacy_path, _single_name,
    _validate_generated_header,
)

KeyPath = tuple[str | int, ...]
_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_NAMESPACE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*-")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_DEFAULT_PATHS = {
    "agent": "agent",
    "skills_output": ".generated/skills",
    "pipelines": "pipelines",
    "templates": "templates",
}
_RESERVED_PATHS = frozenset((*_DEFAULT_PATHS, "pack_templates"))


@dataclass(frozen=True)
class DeclarationSourceMap:
    """Full structural key paths, including zero-based array-table occurrences."""

    path: str
    locations: Mapping[KeyPath, int]

    def line(self, key_path: KeyPath) -> int:
        """Absent keys point to the closest containing declaration."""
        while key_path not in self.locations and key_path:
            key_path = key_path[:-1]
        return self.locations.get(key_path, 1)

    def location(self, key_path: KeyPath) -> SourceLocation:
        return SourceLocation(self.path, self.line(key_path))

    def error(self, key_path: KeyPath, message: str) -> LocatedError:
        return LocatedError(self.location(key_path), message)


@dataclass(frozen=True)
class _Token:
    text: str
    line: int


def _tokens(text: str) -> list[_Token]:
    """Lex positions only, after tomllib has accepted the complete document.

    Quoted strings (including multiline strings), comments and line breaks
    are kept distinct from the structural delimiters inside them. Scalar
    TOML values are not interpreted here; tomllib is the only value parser.
    """
    newlines = [match.start() for match in re.finditer("\n", text)]
    result = []
    i = 0
    while i < len(text):
        start = i
        char = text[i]
        if char in " \t\r":
            i += 1
            continue
        if char == "#":
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        if char in "\"'":
            width = 3 if text.startswith(char * 3, i) else 1
            i += width
            while i < len(text):
                if char == '"' and text[i] == "\\":
                    i += 2
                    continue
                if text.startswith(char * width, i):
                    i += width
                    if width == 3:
                        while i < len(text) and text[i] == char:
                            i += 1
                    break
                i += 1
        elif char in "\n[]{}=,.":
            i += 1
        else:
            i += 1
            while i < len(text) and text[i] not in " \t\r\n[]{}=,.#\"'":
                i += 1
        result.append(_Token(text[start:i], bisect_right(newlines, start - 1) + 1))
    return result


class _SourceIndexer:
    """Walk the structure of an already valid TOML document."""

    def __init__(self, text: str):
        self.tokens = _tokens(text)
        self.i = 0
        self.locations: dict[KeyPath, int] = {(): 1}
        self.latest: dict[KeyPath, int] = {}

    def peek(self) -> str:
        return self.tokens[self.i].text if self.i < len(self.tokens) else ""

    def pop(self) -> _Token:
        token = self.tokens[self.i]
        self.i += 1
        return token

    def skip_lines(self):
        while self.peek() == "\n":
            self.pop()

    def key(self) -> list[tuple[str, int]]:
        parts = []
        while True:
            token = self.pop()
            # Decode quoted/escaped keys using the same parser as the document.
            name = (next(iter(tomllib.loads(token.text + " = 0")))
                    if token.text.startswith(("'", '"')) else token.text)
            parts.append((name, token.line))
            if self.peek() != ".":
                return parts
            self.pop()

    def assignment(self, parent: KeyPath):
        parts = self.key()
        path = parent
        for name, line in parts:
            path += (name,)
            self.locations.setdefault(path, line)
        self.pop()  # =
        self.skip_lines()
        self.value(path)

    def value(self, path: KeyPath):
        if self.peek() == "[":
            self.pop()
            self.skip_lines()
            index = 0
            while self.peek() != "]":
                child = path + (index,)
                self.locations[child] = self.tokens[self.i].line
                self.value(child)
                self.skip_lines()
                if self.peek() == ",":
                    self.pop()
                    self.skip_lines()
                index += 1
            self.pop()
        elif self.peek() == "{":
            self.pop()
            self.skip_lines()
            while self.peek() != "}":
                self.assignment(path)
                self.skip_lines()
                if self.peek() == ",":
                    self.pop()
                    self.skip_lines()
            self.pop()
        else:
            # A scalar may have multiple lexical tokens (e.g. a float or
            # a local datetime). Its delimiters are outside quoted strings.
            while self.peek() not in {"", "\n", ",", "]", "}"}:
                self.pop()

    def header(self) -> KeyPath:
        opening = self.pop()
        array = self.peek() == "["
        if array:
            self.pop()
        parts = self.key()
        self.pop()
        if array:
            self.pop()
        path: KeyPath = ()
        for index, (name, line) in enumerate(parts):
            path += (name,)
            self.locations.setdefault(path, line)
            last = index == len(parts) - 1
            if last and array:
                occurrence = self.latest.get(path, -1) + 1
                self.latest[path] = occurrence
                path += (occurrence,)
            elif path in self.latest:
                path += (self.latest[path],)
        self.locations[path] = opening.line
        return path

    def index(self) -> Mapping[KeyPath, int]:
        parent: KeyPath = ()
        self.skip_lines()
        while self.peek():
            if self.peek() == "[":
                parent = self.header()
            else:
                self.assignment(parent)
            self.skip_lines()
        return MappingProxyType(self.locations)


def read_declaration(path: Path, *, display_path: str | None = None
                     ) -> tuple[dict, DeclarationSourceMap]:
    """Parse TOML and map semantic diagnostics to original key/table lines.

    For Python versions without TOMLDecodeError.lineno, its documented
    message carries the parser line; an EOF error belongs to the EOF line.
    """
    path = Path(path)
    display = display_path if display_path is not None else path.as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise LocatedError(SourceLocation(display, 1),
                           f"cannot read {display}: {getattr(exc, 'strerror', None) or exc}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        line = getattr(exc, "lineno", None)
        if line is None:
            position = re.search(r"\(at line (\d+), column \d+\)$", str(exc))
            line = int(position[1]) if position else text.count("\n") + 1
        raise LocatedError(SourceLocation(display, line), f"invalid TOML: {exc}") from exc
    return data, DeclarationSourceMap(display, _SourceIndexer(text).index())


@dataclass(frozen=True)
class RecordKind:
    name: str
    root: str
    files: tuple[str, ...]
    reader: str
    pack: bool = False


@dataclass(frozen=True)
class Pin:
    commit: str
    tag: str | None = None


@dataclass(frozen=True)
class AdapterRegistration:
    module: str
    records: str | None = None


@dataclass(frozen=True)
class CheckRegistration:
    register: str


@dataclass(frozen=True)
class ViewRegistration:
    register: str
    marker_prefix: str | None = None
    hint: str = "regenerate the view"


@dataclass(frozen=True)
class WorkspaceConfig:
    name: str
    skill_namespace: str
    paths: Mapping[str, Path]
    ids: Mapping[str, IdPolicy]
    record_kinds: tuple[RecordKind, ...]
    relation_kinds: tuple[Mapping, ...]
    otto: Pin | None = None
    adapters: AdapterRegistration | None = None
    checks: CheckRegistration | None = None
    views: ViewRegistration | None = None
    skills: SkillConfig | None = None


@dataclass(frozen=True)
class Workspace:
    """Resolved root, immutable declaration, and sorted discovered sources.

    Paths in config.paths are resolved absolute paths. The absence of
    pack_templates means the package default (owned by the template loader).
    Sources retain root-relative authored paths, including contained aliases.
    """
    root: Path
    config: WorkspaceConfig
    source_map: DeclarationSourceMap
    sources: Mapping[str, tuple[str, ...]]
    _module: ModuleType | None = field(default=None, repr=False, compare=False)
    skill_config: SkillConfig = field(init=False, repr=False)

    def __post_init__(self):
        # Loaded declarations already contain the resolved value. Preserve the
        # positional constructor for callers assembling a workspace directly.
        resolved = self.config.skills
        if resolved is None:
            resolved = SkillConfig(
                self.config.skill_namespace,
                self.config.paths["agent"].relative_to(self.root),
                self.config.paths["skills_output"].relative_to(self.root),
            )
        object.__setattr__(self, "skill_config", resolved)

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def skill_namespace(self) -> str:
        return self.config.skill_namespace

    @property
    def paths(self) -> Mapping[str, Path]:
        return self.config.paths

    @property
    def ids(self) -> Mapping[str, IdPolicy]:
        return self.config.ids

    @property
    def record_kinds(self) -> tuple[RecordKind, ...]:
        return self.config.record_kinds

    @property
    def relation_kinds(self) -> tuple[Mapping, ...]:
        return self.config.relation_kinds

    def export(self, name: str, *, declaration: KeyPath) -> Callable:
        """Resolve a callable in the already loaded, explicitly named module."""
        try:
            value = getattr(self._module, name, None)
        except Exception as exc:
            module = self.config.adapters.module if self.config.adapters else ''
            raise self.source_map.error(declaration, f"cannot load adapter {module}: {exc}") from exc
        if not callable(value):
            raise self.source_map.error(declaration,
                                        f"adapter export {name!r} is missing or not callable")
        return value


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _path_reason(value: str, *, allow_dot: bool) -> str | None:
    if not value.strip():
        return "empty path"
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        return "absolute paths are not allowed"
    if "\\" in value:
        return "backslashes are not allowed"
    if _CONTROL.search(value):
        return "control characters are not allowed"
    if ".." in value.split("/"):
        return "parent components are not allowed"
    if not allow_dot and all(part in {"", "."} for part in value.split("/")):
        return "must name a path below the root"
    return None


def _portable_skill_name(value: str, field_name: str) -> str:
    """TOML-only filename safety; direct SkillConfig callers keep their grammar."""
    _single_name(value, field_name)
    # A declaration is portable across checkout hosts, including Windows.
    # Do not accept a name that aliases a device or loses a trailing character.
    device = value.split(".", 1)[0].rstrip(" ")
    if (not value.strip() or value.endswith((".", " "))
            or re.fullmatch(r"(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])",
                            device, re.IGNORECASE)):
        raise ValueError(f"{field_name} must be a nonempty portable filename or prefix")
    return value


def _read_error(source: DeclarationSourceMap, key: KeyPath, path: str,
                exc: BaseException) -> LocatedError:
    return source.error(key, f"cannot read {path}: {getattr(exc, 'strerror', None) or exc}")


def _inside(root: Path, path: Path, *, source: DeclarationSourceMap,
            key: KeyPath, label: str, output: bool = False) -> Path:
    """Check resolved containment and dangling aliases, with strict output paths."""
    try:
        for parent in reversed((path, *path.parents)):
            if parent == root or root not in parent.parents:
                continue
            if parent.is_symlink():
                if output:
                    raise source.error(key, f"{label} must not be or pass through a symlink")
                resolved = parent.resolve(strict=False)
                if not resolved.is_relative_to(root):
                    raise source.error(key, f"{label} must resolve inside the workspace root")
                # Do not silently treat dangling aliases as absent optional paths.
                try:
                    parent.stat()
                except OSError as exc:
                    raise _read_error(source, key, parent.relative_to(root).as_posix(), exc) from exc
        resolved = path.resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise source.error(key, f"{label} must resolve inside the workspace root")
        return resolved
    except (OSError, RuntimeError) as exc:
        raise _read_error(source, key, str(path), exc) from exc


def _directory(root: Path, path: Path, *, required: bool,
               source: DeclarationSourceMap, key: KeyPath, label: str):
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        if required:
            raise source.error(key, f"{label} must name a directory") from None
        return
    except OSError as exc:
        raise _read_error(source, key, path.relative_to(root).as_posix(), exc) from exc
    if not stat.S_ISDIR(mode):
        raise source.error(key, f"{label} must name a directory")
    try:
        # Probe the directory without creating it or treating permission
        # failures as empty inventories (Path.glob can suppress such errors).
        with os.scandir(path) as entries:
            next(entries, None)
    except OSError as exc:
        raise _read_error(source, key, path.relative_to(root).as_posix(), exc) from exc


class _Validator:
    def __init__(self, root: Path, data: dict, source: DeclarationSourceMap):
        self.root, self.data, self.source = root, data, source

    def fail(self, key: KeyPath, message: str):
        raise self.source.error(key, message)

    @staticmethod
    def label(key: KeyPath) -> str:
        return ".".join(str(part) for part in key if not isinstance(part, int)) or "otto.toml"

    def table(self, value, key: KeyPath, allowed=None, required=()) -> dict:
        label = self.label(key)
        if not isinstance(value, dict):
            self.fail(key, f"{label} must be a table")
        if allowed is not None:
            for name in value:
                if name not in allowed:
                    self.fail(key + (name,), f"unknown key {name!r} in {label}")
        for name in required:
            if name not in value:
                self.fail(key, f"missing required key {name!r} in {label}")
        return value

    def tables(self, value, key: KeyPath) -> list[dict]:
        if not isinstance(value, list):
            self.fail(key, f"{self.label(key)} must be an array of tables")
        for index, entry in enumerate(value):
            if not isinstance(entry, dict):
                self.fail(key + (index,), f"{self.label(key)} must be an array of tables")
        return value

    def string(self, value, key: KeyPath, *, nonempty: bool = True) -> str:
        label = self.label(key)
        if not isinstance(value, str):
            self.fail(key, f"{label} must be a string")
        if nonempty and not value.strip():
            self.fail(key, f"{label} must be a nonempty string")
        return value

    def strings(self, value, key: KeyPath, *, nonempty: bool = True) -> tuple[str, ...]:
        if not isinstance(value, list):
            self.fail(key, f"{self.label(key)} must be an array of strings")
        for index, item in enumerate(value):
            if not isinstance(item, str):
                self.fail(key + (index,), f"{self.label(key)} must be an array of strings")
            if nonempty and not item.strip():
                self.fail(key + (index,), f"{self.label(key)} must be a nonempty string")
        return tuple(value)

    def boolean(self, value, key: KeyPath) -> bool:
        if not isinstance(value, bool):
            self.fail(key, f"{self.label(key)} must be a boolean")
        return value

    def path(self, value, key: KeyPath, *, output=False, allow_dot=True) -> Path:
        value = self.string(value, key)
        label = self.label(key)
        if _path_reason(value, allow_dot=allow_dot):
            self.fail(key, f"{label} must resolve inside the workspace root")
        return _inside(self.root, self.root / value, source=self.source,
                       key=key, label=label, output=output)

    def records(self, raw) -> tuple[RecordKind, ...]:
        result = []
        seen = set()
        for i, value in enumerate(self.tables(raw, ("record_kinds",))):
            key = ("record_kinds", i)
            self.table(value, key, {"name", "root", "files", "reader", "pack"},
                       ("name", "root", "files", "reader"))
            name = self.string(value["name"], key + ("name",))
            if not _NAME.fullmatch(name):
                self.fail(key + ("name",),
                          f"invalid record kind name {name!r}; expected lowercase kebab-case")
            if name in seen:
                self.fail(key + ("name",), f"duplicate record kind {name!r}")
            seen.add(name)
            root = self.string(value["root"], key + ("root",))
            files = self.strings(value["files"], key + ("files",), nonempty=False)
            if not files:
                self.fail(key + ("files",), f"record kind {name} requires at least one source pattern")
            for j, pattern in enumerate(files):
                reason = _path_reason(pattern, allow_dot=False)
                if reason is None and any("**" in part and part != "**" for part in pattern.split("/")):
                    reason = "'**' must be a complete path component"
                if reason:
                    self.fail(key + ("files", j), f"invalid source pattern {pattern!r}: {reason}")
            reader = self.string(value["reader"], key + ("reader",), nonempty=False)
            if reader not in {"headers", "frontmatter", "adapter"}:
                self.fail(key + ("reader",),
                          f"unknown reader {reader!r}; expected headers, frontmatter or adapter")
            pack = self.boolean(value.get("pack", False), key + ("pack",))
            result.append(RecordKind(name, root, tuple(dict.fromkeys(files)), reader, pack))
        return tuple(result)

    def ids(self, raw, kinds: tuple[RecordKind, ...]) -> Mapping[str, IdPolicy]:
        self.table(raw, ("ids",))
        known = {kind.name: kind for kind in kinds}
        policies = {}
        for name, value in raw.items():
            key = ("ids", name)
            if name not in known:
                self.fail(key, f"ID policy names unknown kind {name!r}")
            self.table(value, key, {"policy", "source", "pattern"}, ("policy", "source"))
            policy = self.string(value["policy"], key + ("policy",), nonempty=False)
            if policy not in ID_PRESETS:
                self.fail(key + ("policy",), f"unknown ID policy {policy!r}")
            source = self.string(value["source"], key + ("source",), nonempty=False)
            if source not in ID_SOURCES:
                self.fail(key + ("source",),
                          f"unknown ID source {source!r}; expected {', '.join(ID_SOURCES)}")
            reader = known[name].reader
            if (source == "adapter") != (reader == "adapter"):
                self.fail(key + ("source",),
                          f"ID source {source!r} is incompatible with reader {reader!r}")
            pattern = None
            if policy == "regex":
                self.table(value, key, required=("pattern",))
                pattern = self.string(value["pattern"], key + ("pattern",), nonempty=False)
                try:
                    re.compile(pattern)
                except re.error as exc:
                    self.fail(key + ("pattern",), f"invalid ID regex for {name}: {exc}")
            elif "pattern" in value:
                self.fail(key + ("pattern",), "pattern is only valid for regex ID policy")
            policies[name] = IdPolicy(policy, source, pattern)
        for index, kind in enumerate(kinds):
            if kind.name not in policies:
                self.fail(("record_kinds", index, "name"), f"missing ID policy for kind {kind.name}")
        return MappingProxyType(policies)

    def relations(self, raw) -> tuple[Mapping, ...]:
        """Check the closed declaration structure; OT-8 binds its semantics."""
        result = []
        for i, value in enumerate(self.tables(raw, ("relation_kinds",))):
            key = ("relation_kinds", i)
            self.table(value, key,
                       {"name", "sources", "targets", "roles", "per_source", "per_target", "by_role"},
                       ("name", "sources", "targets", "roles"))
            self.string(value["name"], key + ("name",))
            for name in ("sources", "targets", "roles"):
                self.strings(value[name], key + (name,))
            for name in ("per_source", "per_target"):
                if name in value:
                    self.string(value[name], key + (name,))
            if "by_role" in value:
                by_role = self.table(value["by_role"], key + ("by_role",))
                for role, rule in by_role.items():
                    role_key = key + ("by_role", role)
                    self.string(role, role_key)
                    self.table(rule, role_key, {"per_source", "per_target"})
                    for name, token in rule.items():
                        self.string(token, role_key + (name,))
            result.append(_freeze(value))
        return tuple(result)

    def pin(self, raw) -> Pin:
        key = ("otto",)
        self.table(raw, key, {"commit", "tag"})
        if "tag" in raw and "commit" not in raw:
            self.fail(key + ("tag",), "otto.tag requires otto.commit")
        self.table(raw, key, required=("commit",))
        commit = self.string(raw["commit"], key + ("commit",), nonempty=False)
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            self.fail(key + ("commit",), "otto.commit must be 40 lowercase hex characters")
        tag = None
        if "tag" in raw:
            tag = self.string(raw["tag"], key + ("tag",), nonempty=False)
            if not tag.strip():
                self.fail(key + ("tag",), "otto.tag must be nonempty")
        return Pin(commit, tag)

    def export_name(self, value, key: KeyPath) -> str:
        name = self.string(value, key, nonempty=False)
        if not name.isidentifier() or keyword.iskeyword(name):
            self.fail(key, f"adapter export name {name!r} must be a bare identifier")
        return name

    def registrations(self, kinds):
        data = self.data
        adapters = checks = views = None
        adapter_path = None
        if "adapters" in data:
            key = ("adapters",)
            raw = self.table(data["adapters"], key, {"module", "records"})
            if "module" not in raw:
                if any(kind.reader == "adapter" for kind in kinds):
                    self.fail(key, "adapter record kinds require adapters.module and adapters.records")
                if "records" in raw or "checks" in data or "views" in data:
                    self.fail(key, "registrations require adapters.module")
                self.table(raw, key, required=("module",))
            module = self.string(raw["module"], key + ("module",))
            adapter_path = self.path(module, key + ("module",), allow_dot=False)
            if Path(module).suffix != ".py" or adapter_path.suffix != ".py":
                self.fail(key + ("module",), "adapters.module must name a .py file inside the workspace")
            records = (self.export_name(raw["records"], key + ("records",))
                       if "records" in raw else None)
            adapters = AdapterRegistration(module, records)
        if any(kind.reader == "adapter" for kind in kinds) and (not adapters or not adapters.records):
            self.fail(("adapters",), "adapter record kinds require adapters.module and adapters.records")
        if "checks" in data:
            key = ("checks",)
            raw = self.table(data["checks"], key, {"register"}, ("register",))
            checks = CheckRegistration(self.export_name(raw["register"], key + ("register",)))
            if not adapters:
                self.fail(key + ("register",), "registrations require adapters.module")
        if "views" in data:
            key = ("views",)
            raw = self.table(data["views"], key, {"register", "marker_prefix", "hint"}, ("register",))
            views = ViewRegistration(
                self.export_name(raw["register"], key + ("register",)),
                self.string(raw["marker_prefix"], key + ("marker_prefix",), nonempty=False)
                if "marker_prefix" in raw else None,
                self.string(raw["hint"], key + ("hint",), nonempty=False)
                if "hint" in raw else "regenerate the view")
            if not adapters:
                self.fail(key + ("register",), "registrations require adapters.module")
        return adapters, adapter_path, checks, views

    def paths(self, raw, kinds):
        self.table(raw, ("paths",))
        used = {kind.root for kind in kinds}
        for i, kind in enumerate(kinds):
            if kind.root not in raw:
                self.fail(("record_kinds", i, "root"),
                          f"record kind {kind.name} names unknown root {kind.root!r}")
        for name in raw:
            if name not in _RESERVED_PATHS and name not in used:
                self.fail(("paths", name), f"unused record root {name!r}")
        declared = {**_DEFAULT_PATHS, **raw}
        resolved = {}
        authored = {}
        for name, value in declared.items():
            key = ("paths", name)
            output = name == "skills_output"
            path = self.path(value, key, output=output, allow_dot=not output)
            resolved[name] = path
            authored[name] = self.root / value
            _directory(self.root, path, required=name in used or name == "pack_templates",
                       source=self.source, key=key, label=self.label(key))
        source, output = resolved["agent"], resolved["skills_output"]
        if source.is_relative_to(output) or output.is_relative_to(source):
            key = ("paths", "skills_output" if "skills_output" in raw else "agent")
            self.fail(key, "skill source and output roots must not overlap")
        return MappingProxyType(resolved), authored

    def skills(self, raw, namespace: str, paths: Mapping[str, Path]) -> SkillConfig:
        key = ("skills",)
        names = ("lock_name_override", "lock_stage_prefix_override",
                 "probe_stage_prefix_override", "build_stage_prefix_override")
        self.table(raw, key, {*names, "generated_header", "legacy_owned_dirs",
                              "legacy_retire_names", "path_based_link_ownership"})
        values = {}

        def checked(location, validate, *args):
            try:
                return validate(*args)
            except ValueError as exc:
                raise self.source.error(location, str(exc)) from exc

        if "generated_header" in raw:
            location = key + ("generated_header",)
            header = self.string(raw["generated_header"], location, nonempty=False)
            checked(location, _validate_generated_header, header)
            values["generated_header"] = header
        for name in names:
            if name in raw:
                location = key + (name,)
                value = self.string(raw[name], location, nonempty=False)
                values[name] = checked(location, _portable_skill_name, value, name)

        for name in ("legacy_owned_dirs", "legacy_retire_names"):
            if name not in raw:
                continue
            location = key + (name,)
            entries = self.strings(raw[name], location)
            normalized = []
            for index, value in enumerate(entries):
                item = location + (index,)
                if name == "legacy_owned_dirs":
                    path = checked(item, _legacy_path, value)
                    # Keep legacy ownership roots lexical. In particular,
                    # resolving a symlink here could grant foreign ownership.
                    for part in value.split("/"):
                        checked(item, _portable_skill_name, part, name)
                    normalized.append(path)
                else:
                    normalized.append(checked(item, _portable_skill_name, value, name))
            values[name] = tuple(normalized)
        if "path_based_link_ownership" in raw:
            name = "path_based_link_ownership"
            values[name] = self.boolean(raw[name], key + (name,))

        source_root = checked(("paths", "agent"), _checkout_relative_path,
                              paths["agent"].relative_to(self.root), "source_root")
        output = checked(("paths", "skills_output"), _checkout_relative_path,
                          paths["skills_output"].relative_to(self.root), "output")
        config = SkillConfig(namespace, source_root, output, **values)
        if config.lock_name_override is not None:
            lock = paths["skills_output"].parent / config.lock_name
            # Do not create/open anything here or follow an existing lock
            # symlink. The builder independently validates lock identity.
            protected = (paths["agent"], paths["skills_output"],
                         self.root / "otto.toml", (self.root / "otto.toml").resolve())
            if any(path.is_relative_to(lock) or lock.is_relative_to(path)
                   for path in protected):
                self.fail(key + ("lock_name_override",),
                          "skills.lock_name_override conflicts with a skill root or otto.toml")
        return config

    def discover(self, kinds, authored) -> Mapping[str, tuple[str, ...]]:
        sources = {}
        for i, kind in enumerate(kinds):
            matches: set[str] = set()
            directory = authored[kind.root]
            # Recover the actual occurrence for a deduplicated pattern.
            raw_patterns = self.data["record_kinds"][i]["files"]
            for pattern in kind.files:
                key = ("record_kinds", i, "files", raw_patterns.index(pattern))
                label = f"paths.{kind.root}"
                for path in _discover_pattern(self.root, directory, pattern,
                                              self.source, key, label):
                    relative = path.relative_to(self.root).as_posix()
                    if kind.pack and path.name != "plan.md":
                        self.fail(key, f"record kind {kind.name} sets pack = true but its pattern matched {relative!r}, which is not named plan.md")
                    matches.add(relative)
            sources[kind.name] = tuple(sorted(matches))
        return MappingProxyType(sources)

    def declaration(self):
        """Resolve the declaration without discovery or executing adapters."""
        data = self.table(self.data, (), {
            "version", "otto", "workspace", "paths", "ids", "record_kinds",
            "relation_kinds", "adapters", "checks", "views", "skills"}, ("version", "workspace"))
        if type(data["version"]) is not int:
            self.fail(("version",), "version must be an integer")
        if data["version"] != 1:
            self.fail(("version",), f"unsupported declaration version {data['version']}; expected 1")
        key = ("workspace",)
        workspace = self.table(data["workspace"], key, {"name", "skill_namespace"},
                               ("name", "skill_namespace"))
        name = self.string(workspace["name"], key + ("name",), nonempty=False)
        if not _NAME.fullmatch(name):
            self.fail(key + ("name",),
                      f"invalid workspace name {name!r}; expected lowercase kebab-case")
        namespace = self.string(workspace["skill_namespace"], key + ("skill_namespace",), nonempty=False)
        if not _NAMESPACE.fullmatch(namespace):
            self.fail(key + ("skill_namespace",),
                      "skill namespace must be lowercase kebab-case with a trailing hyphen")
        pin = self.pin(data["otto"]) if "otto" in data else None
        kinds = self.records(data.get("record_kinds", []))
        ids = self.ids(data.get("ids", {}), kinds)
        paths, authored = self.paths(data.get("paths", {}), kinds)
        relations = self.relations(data.get("relation_kinds", []))
        adapters, adapter_path, checks, views = self.registrations(kinds)
        skills = self.skills(data.get("skills", {}), namespace, paths)
        config = WorkspaceConfig(name, namespace, paths, ids, kinds, relations,
                                 pin, adapters, checks, views, skills)
        return config, authored, adapter_path

    def validate(self, *, validate_registrations=True) -> Workspace:
        config, authored, adapter_path = self.declaration()
        sources = self.discover(config.record_kinds, authored)
        adapters, checks, views = config.adapters, config.checks, config.views
        module = (_load_adapter(self.root, adapter_path, adapters.module, self.source)
                  if adapters else None)
        result = Workspace(self.root, config, self.source, sources, module)
        if adapters and adapters.records:
            result.export(adapters.records, declaration=("adapters", "records"))
        if validate_registrations and checks:
            result.export(checks.register, declaration=("checks", "register"))
        if validate_registrations and views:
            result.export(views.register, declaration=("views", "register"))
        return result


def _discover_pattern(root: Path, directory: Path, pattern: str,
                      source: DeclarationSourceMap, key: KeyPath, label: str):
    """Walk relative glob components, surfacing errors instead of hiding them.

    Contained symlink aliases are permitted for input, but recursion cannot
    revisit an ancestor through a symlink. Only matching source paths are read.
    """
    parts = tuple(part for part in pattern.split("/") if part not in {"", "."})

    def entries(path):
        try:
            return sorted(path.iterdir())
        except OSError as exc:
            raise _read_error(source, key, path.relative_to(root).as_posix(), exc) from exc

    def contained(path):
        return _inside(root, path, source=source, key=key, label=label)

    def mode(path):
        try:
            return path.stat().st_mode
        except OSError as exc:
            raise _read_error(source, key, path.relative_to(root).as_posix(), exc) from exc

    def walk(path, index, ancestors):
        if index == len(parts):
            contained(path)
            if not stat.S_ISREG(mode(path)):
                code = errno.EISDIR if path.is_dir() else errno.EINVAL
                raise _read_error(source, key, path.relative_to(root).as_posix(),
                                  OSError(code, os.strerror(code)))
            yield path
            return
        part = parts[index]
        if part == "**":
            # A terminal ** matches files under this directory, not the
            # containing directories. Other ** components can match zero dirs.
            if index + 1 < len(parts):
                yield from walk(path, index + 1, ancestors)
            for child in entries(path):
                actual = contained(child)
                child_mode = mode(child)
                if stat.S_ISDIR(child_mode):
                    if actual in ancestors:
                        raise source.error(key, f"invalid source pattern {pattern!r}: recursive symlink cycle")
                    yield from walk(child, index, ancestors | {actual})
                elif index + 1 == len(parts):
                    yield from walk(child, index + 1, ancestors)
            return
        for child in entries(path):
            if not fnmatchcase(child.name, part):
                continue
            actual = contained(child)
            if index + 1 == len(parts):
                yield from walk(child, index + 1, ancestors)
            elif stat.S_ISDIR(mode(child)):
                yield from walk(child, index + 1, ancestors | {actual})

    yield from walk(directory, 0, {contained(directory)})


def _load_adapter(root: Path, path: Path, declared: str,
                  source: DeclarationSourceMap) -> ModuleType:
    key = ("adapters", "module")
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        raise source.error(key, f"adapter module does not exist: {declared}") from None
    except OSError as exc:
        raise _read_error(source, key, declared, exc) from exc
    if not stat.S_ISREG(mode):
        raise source.error(key, "adapters.module must name a .py file inside the workspace")
    try:
        code = compile(path.read_bytes(), str(path), "exec")
    except OSError as exc:
        raise _read_error(source, key, declared, exc) from exc
    except Exception as exc:
        raise source.error(key, f"cannot load adapter {declared}: {exc}") from exc
    # Execute the exact file rather than searching sys.path or using a stale
    # bytecode cache. Avoid writing __pycache__ for this module. Workspace
    # code and its own imports are trusted, not sandboxed.
    name = f"_otto_workspace_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        exec(code, module.__dict__)
    except Exception as exc:
        sys.modules.pop(name, None)
        raise source.error(key, f"cannot load adapter {declared}: {exc}") from exc
    return module


def _read_validator(root: Path | str) -> _Validator:
    root = Path(root)
    try:
        if not root.is_dir():
            raise ValueError(f"workspace root is not an existing directory: {root}")
        root = root.resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"cannot read {root}: {getattr(exc, 'strerror', None) or exc}") from exc
    path = root / "otto.toml"
    try:
        path.lstat()
    except FileNotFoundError:
        raise ValueError(f"no otto.toml found in {root}") from None
    except OSError as exc:
        raise LocatedError(SourceLocation("otto.toml", 1),
                           f"cannot read otto.toml: {exc.strerror or exc}") from exc
    # The declaration itself must belong to the selected workspace.
    preliminary = DeclarationSourceMap("otto.toml", MappingProxyType({(): 1}))
    _inside(root, path, source=preliminary, key=(), label="otto.toml")
    data, source = read_declaration(path, display_path="otto.toml")
    return _Validator(root, data, source)


def load_skill_config(root: Path | str) -> SkillConfig:
    """Resolve skill settings without discovering records or importing adapters.

    Consumer modules may call this during adapter import. It uses the same
    declaration and path validation as load_workspace, but never executes
    a workspace module or its registration factories.
    """
    config, _, _ = _read_validator(root).declaration()
    assert config.skills is not None
    return config.skills


def load_workspace(root: Path | str, *, validate_registrations=True) -> Workspace:
    """Select exactly this root; validate the declaration and its contained inputs."""
    return _read_validator(root).validate(validate_registrations=validate_registrations)
