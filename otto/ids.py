"""Stable textual identities and bidirectional, discovered-source resolution."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Iterable


@dataclass(frozen=True)
class SourceLocation:
    """A workspace-relative authored location (one-based line)."""

    path: str
    line: int
    anchor: str | None = None


class LocatedError(ValueError):
    """A diagnostic with its exact authored location and unmodified body."""

    def __init__(self, source: SourceLocation, message: str):
        self.source = source
        self.message = message
        super().__init__(f"{source.path}:{source.line}: {message}")


def _lexical_identity(identity: str) -> bool:
    return (isinstance(identity, str) and bool(identity)
            and identity == identity.strip()
            and not any(c.isspace() or ord(c) < 32 or 127 <= ord(c) <= 159
                        for c in identity))


@dataclass(frozen=True, order=True)
class RecordRef:
    """Schema-independent typed identity; graph membership is checked separately."""

    kind: str
    id: str

    def __post_init__(self):
        if not _lexical_identity(self.id):
            raise ValueError(f"invalid {self.kind} identity: {self.id!r}")

    def __str__(self) -> str:
        return f"{self.kind}:{self.id}"

    @classmethod
    def parse(cls, reference: str) -> RecordRef:
        """Split only the first colon; identity may itself contain colon/slash."""
        kind, separator, identity = reference.partition(":")
        if not separator or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", kind):
            raise ValueError(f"invalid typed reference {reference!r}")
        return cls(kind, identity)


@dataclass(frozen=True)
class IdPolicy:
    policy: str
    source: str
    pattern: str | None = None


_COMPONENT_PATTERNS = {
    "NN-slug": r"(\d{2,})-[a-z0-9-]+",
    "XX-NNN": r"([A-Z]{1,3}-\d{3})(?:-[a-z0-9-]+)?",
    "slug": r"[a-z0-9]+(?:-[a-z0-9]+)*",
}
_IDENTITY_PATTERNS = {
    "NN-slug": r"\d{2,}",
    "XX-NNN": r"[A-Z]{1,3}-\d{3}",
    "slug": _COMPONENT_PATTERNS["slug"],
}
ID_PRESETS = frozenset((*_IDENTITY_PATTERNS, "regex"))
ID_SOURCES = ("parent", "stem", "adapter")


def validate_identity(kind: str, policy: IdPolicy, identity: str,
                      source: SourceLocation) -> str:
    """Validate an already extracted identity, including adapter-supplied IDs."""
    pattern = policy.pattern if policy.policy == "regex" else _IDENTITY_PATTERNS[policy.policy]
    if not _lexical_identity(identity) or not re.fullmatch(pattern, identity):
        raise LocatedError(source, f"invalid {kind} identity: {identity!r}")
    return identity


def identity_from_path(kind: str, policy: IdPolicy, path: str, *, line: int = 1) -> str:
    """Extract the configured locator component, preserving its textual identity."""
    location = SourceLocation(str(path), line)
    source = PurePosixPath(path)
    if policy.source == "parent":
        component = source.parent.name
    elif policy.source == "stem":
        component = source.stem
    else:
        raise LocatedError(location, f"ID source {policy.source!r} is incompatible with reader 'headers'")
    pattern = policy.pattern if policy.policy == "regex" else _COMPONENT_PATTERNS[policy.policy]
    match = re.fullmatch(pattern, component)
    if not match or not _lexical_identity(component):
        raise LocatedError(location,
                           f"invalid {kind} identity component {component!r} for policy {policy.policy}")
    identity = match.group(1) if policy.policy in {"NN-slug", "XX-NNN"} else component
    return validate_identity(kind, policy, identity, location)


class IdResolver:
    """Index actual canonical locations, never invent filenames from identities."""

    def __init__(self, entries: Iterable[tuple[RecordRef, SourceLocation]]):
        forward: dict[RecordRef, SourceLocation] = {}
        reverse: dict[str, list[tuple[RecordRef, SourceLocation]]] = {}
        for ref, source in entries:
            if ref in forward:
                raise LocatedError(source, "duplicate record identity")
            forward[ref] = source
            reverse.setdefault(source.path, []).append((ref, source))
        self._forward = MappingProxyType(forward)
        self._reverse = MappingProxyType({
            path: tuple(sorted(items, key=lambda item: (
                item[1].line, item[1].anchor or "", item[0])))
            for path, items in reverse.items()
        })

    def source_for(self, ref: RecordRef) -> SourceLocation:
        return self._forward[ref]

    def refs_at(self, path: str, *, anchor: str | None = None,
                line: int | None = None) -> tuple[RecordRef, ...]:
        """Return every matching identity in authored order, not an arbitrary one."""
        return tuple(ref for ref, source in self._reverse.get(str(path), ())
                     if (anchor is None or source.anchor == anchor)
                     and (line is None or source.line == line))
