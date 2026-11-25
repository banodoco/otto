"""Immutable typed links governed by a workspace's explicit declarations.

The graph reads no files and owns no facts. Its source locations refer back
to the authored record or relationship; a caller may bind an optional local
enabler policy without giving any record kind a universal special meaning.
"""
from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping

from .config import DeclarationSourceMap, Workspace
from .ids import LocatedError, RecordRef, SourceLocation
from .records import Record, RecordBatch, RelationshipRow


class RelationshipError(LocatedError):
    """A structurally invalid record identity or authored link.

    Location-less in-memory/compatibility calls retain the legacy error text.
    Authored calls expose that same body separately from the location prefix.
    """

    def __init__(self, message: str, source: SourceLocation | None = None):
        if source is None:
            self.source = None
            self.message = message
            ValueError.__init__(self, message)
        else:
            super().__init__(source, message)


def cardinality_bounds(token: str) -> tuple[int, int | None]:
    """Return the inclusive lower and upper bounds; None means unbounded."""
    try:
        return {
            "exactly-one": (1, 1),
            "at-most-one": (0, 1),
            "one-or-more": (1, None),
            "any": (0, None),
        }[token]
    except KeyError:
        raise RelationshipError(f"unknown cardinality {token!r}") from None


@dataclass(frozen=True)
class RelationKind:
    name: str
    sources: frozenset[str]
    targets: frozenset[str]
    roles: frozenset[str]
    per_source: str = "any"
    per_target: str = "any"
    by_role: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def __post_init__(self):
        for key in ("sources", "targets", "roles"):
            object.__setattr__(self, key, frozenset(getattr(self, key)))
        object.__setattr__(self, "by_role", MappingProxyType({
            role: MappingProxyType(dict(bounds))
            for role, bounds in self.by_role.items()
        }))


@dataclass(frozen=True)
class EnablerRule:
    """A trusted adapter's explicit exception and ordinary-record constraint."""

    source_kind: str
    relation_kind: str
    role: str
    invalid_enabler_message: str


@dataclass(frozen=True)
class RelationshipSchema:
    record_kinds: frozenset[str]
    relation_kinds: Mapping[str, RelationKind]
    enablers: EnablerRule | None = None

    def __post_init__(self):
        object.__setattr__(self, "record_kinds", frozenset(self.record_kinds))
        object.__setattr__(self, "relation_kinds",
                           MappingProxyType(dict(self.relation_kinds)))

    @classmethod
    def from_workspace(cls, workspace: Workspace, *,
                       enablers: EnablerRule | None = None) -> RelationshipSchema:
        return cls.from_declarations(
            (kind.name for kind in workspace.record_kinds),
            workspace.relation_kinds, workspace.source_map, enablers=enablers)

    @classmethod
    def from_declarations(
        cls, record_kinds: Iterable[str], relation_kinds: Iterable[Mapping],
        source_map: DeclarationSourceMap, *, enablers: EnablerRule | None = None,
    ) -> RelationshipSchema:
        """Bind the frozen declaration data, without requiring a full workspace.

        The configuration reader owns the closed structural/type checks.
        This boundary owns semantic checks, using its exact declaration map.
        """
        known = frozenset(record_kinds)
        relations = {}

        def refuse(key, message):
            raise RelationshipError(message, source_map.location(key))

        def token_at(value, key):
            try:
                cardinality_bounds(value)
            except RelationshipError as exc:
                refuse(key, exc.message)
            return value

        for i, raw in enumerate(relation_kinds):
            key = ("relation_kinds", i)
            name = raw["name"]
            if name in relations:
                refuse(key + ("name",), f"duplicate relation kind {name!r}")

            lists = {}
            for attr, singular in (("sources", "source kind"),
                                   ("targets", "target kind"), ("roles", "role")):
                values = raw[attr]
                if not values:
                    refuse(key + (attr,), f"relation {name} requires nonempty {attr}")
                seen = set()
                for j, value in enumerate(values):
                    where = key + (attr, j)
                    if attr != "roles" and value not in known:
                        refuse(where, f"relation {name} names unknown record kind {value!r}")
                    if value in seen:
                        refuse(where, f"relation {name} repeats {singular} {value!r}")
                    seen.add(value)
                lists[attr] = frozenset(seen)

            totals = {end: token_at(raw.get(end, "any"), key + (end,))
                      for end in ("per_source", "per_target")}
            by_role = {}
            for role, bounds in raw.get("by_role", {}).items():
                role_key = key + ("by_role", role)
                if role not in lists["roles"]:
                    refuse(role_key,
                           f"relation {name} has cardinality for unknown role {role!r}")
                by_role[role] = {
                    end: token_at(bounds.get(end, "any"), role_key + (end,))
                    for end in ("per_source", "per_target")
                }

            # Every edge has exactly one role. Total degree must intersect
            # the interval obtained by summing all role intervals.
            for end, direction in (("per_source", "source"), ("per_target", "target")):
                low, high = cardinality_bounds(totals[end])
                role_ranges = [cardinality_bounds(by_role.get(role, {}).get(end, "any"))
                               for role in lists["roles"]]
                role_low = sum(lo for lo, _ in role_ranges)
                role_high = (None if any(hi is None for _, hi in role_ranges)
                             else sum(hi for _, hi in role_ranges))
                if ((high is not None and role_low > high)
                        or (role_high is not None and low > role_high)):
                    refuse(key + (end,),
                           f"inconsistent cardinality bounds for relation {name} at {direction}")

            relations[name] = RelationKind(name, **lists, **totals, by_role=by_role)
        return cls(known, relations, enablers)

    def _check_kind(self, kind: str, source: SourceLocation | None = None) -> None:
        if kind not in self.record_kinds:
            raise RelationshipError(f"unknown record kind: {kind!r}", source)

    def ref(self, kind: str, id: str, *,
            source: SourceLocation | None = None) -> RecordRef:
        """Validate membership immediately and return the one shared identity."""
        self._check_kind(kind, source)
        try:
            return RecordRef(kind, id)
        except ValueError as exc:
            raise RelationshipError(str(exc), source) from exc


@dataclass(frozen=True)
class Relationship:
    source: RecordRef
    kind: str
    target: RecordRef
    role: str
    source_path: str
    source_line: int | None = None
    schema: InitVar[RelationshipSchema] = field(kw_only=True)

    def __post_init__(self, schema: RelationshipSchema) -> None:
        self._validate(schema)

    @property
    def source_location(self) -> SourceLocation | None:
        if type(self.source_line) is int and self.source_line >= 1:
            return SourceLocation(self.source_path, self.source_line)
        return None

    def _validate(self, schema: RelationshipSchema) -> None:
        location = self.source_location
        rule = schema.relation_kinds.get(self.kind)
        if rule is None:
            raise RelationshipError(f"unknown relationship kind: {self.kind!r}", location)
        schema._check_kind(self.source.kind, location)
        schema._check_kind(self.target.kind, location)
        if self.source.kind not in rule.sources or self.target.kind not in rule.targets:
            sources = " or ".join(sorted(rule.sources))
            targets = " or ".join(sorted(rule.targets))
            raise RelationshipError(
                f"{self.kind} requires {sources} -> {targets}, "
                f"got {self.source.kind} -> {self.target.kind}", location)
        if self.role not in rule.roles:
            raise RelationshipError(f"{self.kind}: invalid role {self.role!r}", location)
        if (not self.source_path or self.source_path.startswith("/")
                or "\\" in self.source_path
                or ".." in self.source_path.split("/")
                or any(ord(c) < 32 for c in self.source_path)):
            raise RelationshipError(f"{self.kind}: invalid provenance {self.source_path!r}",
                                    location)
        if self.source_line is not None and self.source_location is None:
            raise RelationshipError(f"{self.kind}: invalid source line {self.source_line!r}")

    @classmethod
    def from_row(cls, row: RelationshipRow, *, schema: RelationshipSchema) -> Relationship:
        return cls(row.source, row.kind, row.target, row.role, row.source_path,
                   row.source_line, schema=schema)

    def identity(self) -> tuple[RecordRef, str, RecordRef]:
        """Role is intentionally excluded: primary+supporting is a conflict."""
        return self.source, self.kind, self.target


def _degree(
    ref: RecordRef, link_kind: str, edges: Iterable[Relationship], token: str,
    *, direction: str, role: str | None, source: SourceLocation | None,
) -> None:
    low, high = cardinality_bounds(token)
    edges = tuple(edges)
    count = len(edges)
    if low <= count and (high is None or count <= high):
        return
    if high is not None and count > high:
        # Sort by authored provenance, rather than target identity or input
        # iteration order; diagnose the first excess edge, not the first edge.
        excess = sorted(edges, key=lambda e: (e.source_path, e.source_line or 0,
                                              e.source, e.target, e.role))[high]
        source = excess.source_location
    if direction == "source" and role == "primary" and token == "exactly-one":
        # Compatibility wording only: the configured bounds, not the role's
        # name, determine whether a constraint exists.
        raise RelationshipError(
            f"{ref}: expected one primary {link_kind} relationship, found {count}", source)
    role_label = f"{role} " if role is not None else ""
    links = (f"{role_label}{link_kind} targets" if direction == "source"
             else f"{role_label}incoming {link_kind} sources")
    raise RelationshipError(f"{ref} has {count} {links}; expected {token}", source)


@dataclass(frozen=True, init=False)
class RelationshipIndex:
    """Deterministic read-only snapshot; never a secondary canonical registry."""

    records: frozenset[RecordRef]
    relationships: tuple[Relationship, ...]
    enablers: frozenset[RecordRef]

    def __init__(
        self,
        records: Iterable[Record | RecordRef],
        relationships: Iterable[Relationship],
        *,
        schema: RelationshipSchema,
        enablers: Iterable[RecordRef] = (),
    ) -> None:
        locations = {}
        for record in records:
            ref, source = ((record.ref, record.source) if isinstance(record, Record)
                           else (record, None))
            schema._check_kind(ref.kind, source)
            if ref in locations:
                raise RelationshipError("duplicate record identity", source)
            locations[ref] = source
        object.__setattr__(self, "records", frozenset(locations))
        accepted_enablers = frozenset(enablers)
        policy = schema.enablers
        if accepted_enablers and policy is None:
            raise RelationshipError("enablers require an explicit schema rule")
        if policy is not None:
            for ref in sorted(accepted_enablers):
                if ref.kind != policy.source_kind or ref not in self.records:
                    raise RelationshipError(policy.invalid_enabler_message, locations.get(ref))
        object.__setattr__(self, "enablers", accepted_enablers)

        links = tuple(relationships)
        identities: set[tuple[RecordRef, str, RecordRef]] = set()
        for link in links:
            link._validate(schema)
            # The adapter decides which records qualify; never infer an
            # exemption from an absence of links.
            if (policy is not None and link.source in accepted_enablers
                    and link.kind == policy.relation_kind):
                raise RelationshipError(
                    f"{link.source_path}: enabler {link.source} cannot declare {link.kind}",
                    link.source_location)
            if link.source not in self.records or link.target not in self.records:
                missing = link.source if link.source not in self.records else link.target
                raise RelationshipError(
                    f"{link.source_path}: {link.kind} names unknown {missing}",
                    link.source_location)
            if link.identity() in identities:
                raise RelationshipError(
                    f"{link.source_path}: duplicate or contradictory {link.kind} "
                    f"{link.source} -> {link.target}", link.source_location)
            identities.add(link.identity())
        object.__setattr__(self, "relationships", tuple(sorted(
            links,
            key=lambda e: (e.source.kind, e.source.id, e.kind,
                           e.target.kind, e.target.id, e.role, e.source_path,
                           e.source_line or 0))))

        for rule in schema.relation_kinds.values():
            for direction, kinds, token in (
                ("source", rule.sources, rule.per_source),
                ("target", rule.targets, rule.per_target),
            ):
                for ref in sorted(self.records):
                    if ref.kind not in kinds:
                        continue
                    edges = (self.outgoing(ref, rule.name) if direction == "source"
                             else self.incoming(ref, rule.name))
                    _degree(ref, rule.name, edges, token, direction=direction,
                            role=None, source=locations[ref])
                    for role in sorted(rule.roles):
                        role_token = rule.by_role.get(role, {}).get(f"per_{direction}", "any")
                        _degree(ref, rule.name, (e for e in edges if e.role == role),
                                role_token, direction=direction, role=role,
                                source=locations[ref])

        # Local policy is independent of global declaration cardinality.
        if policy is not None:
            for ref in sorted(self.records):
                if ref.kind != policy.source_kind or ref in accepted_enablers:
                    continue
                primary = [e for e in self.relationships
                           if e.source == ref and e.kind == policy.relation_kind
                           and e.role == policy.role]
                _degree(ref, policy.relation_kind, primary, "exactly-one",
                        direction="source", role=policy.role, source=locations[ref])

    @classmethod
    def from_batch(cls, batch: RecordBatch, *, schema: RelationshipSchema,
                   enablers: Iterable[RecordRef] = ()) -> RelationshipIndex:
        return cls(batch.records,
                   (Relationship.from_row(row, schema=schema) for row in batch.relationships),
                   schema=schema, enablers=enablers)

    def outgoing(self, source: RecordRef, kind: str | None = None) -> tuple[Relationship, ...]:
        return tuple(edge for edge in self.relationships
                     if edge.source == source and (kind is None or edge.kind == kind))

    def incoming(self, target: RecordRef, kind: str | None = None) -> tuple[Relationship, ...]:
        return tuple(edge for edge in self.relationships
                     if edge.target == target and (kind is None or edge.kind == kind))
