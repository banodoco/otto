"""Plan 72 relationship parity and configured graph refusal fixtures."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest

from otto.config import DeclarationSourceMap, load_workspace, read_declaration
from otto.ids import RecordRef as SharedRecordRef, SourceLocation
from otto.records import Record, RecordBatch, RelationshipRow
from otto.relationships import (
    EnablerRule, RecordRef, Relationship, RelationshipError, RelationshipIndex,
    RelationshipSchema, cardinality_bounds,
)


DEV = Path(__file__).parent / "fixtures" / "dev" / "otto.toml"
POLICY = EnablerRule("project", "addresses", "primary",
                     "foundational enabler must be an existing project")
DECLARATION, SOURCE_MAP = read_declaration(DEV, display_path="otto.toml")
SCHEMA = RelationshipSchema.from_declarations(
    (kind["name"] for kind in DECLARATION["record_kinds"]),
    DECLARATION["relation_kinds"], SOURCE_MAP, enablers=POLICY)

G = SCHEMA.ref("goal", "pillar:artistic-ambition/finish-a-work")
A = SCHEMA.ref("gap", "AA-001")
B = SCHEMA.ref("gap", "AA-002")
P = SCHEMA.ref("project", "72")
R = SCHEMA.ref("release", "15")
I = SCHEMA.ref("issue", "123")
S = "vision/gaps/AA-001.md"


def link(source=A, kind="measures", target=G, role="primary", path=S):
    return Relationship(source, kind, target, role, path, 1, schema=SCHEMA)


class RelationshipTests(unittest.TestCase):
    def test_canonical_namespaced_identity(self):
        self.assertEqual(str(G), "goal:pillar:artistic-ambition/finish-a-work")
        self.assertEqual({G, SCHEMA.ref("goal", G.id)}, {G})
        with self.assertRaisesRegex(RelationshipError, "unknown record kind"):
            SCHEMA.ref("widget", "a")
        for value in ("", " AA-001 ", "AA 001", "AA\n001"):
            with self.subTest(value=value), self.assertRaises(RelationshipError):
                SCHEMA.ref("gap", value)
        self.assertIs(RecordRef, SharedRecordRef)
        self.assertIs(type(G), SharedRecordRef)

    def test_endpoints_roles_and_provenance(self):
        with self.assertRaisesRegex(RelationshipError, "requires gap -> goal"):
            link(source=P)
        with self.assertRaisesRegex(RelationshipError, "invalid role"):
            link(role="included")
        with self.assertRaisesRegex(RelationshipError, "provenance"):
            link(path="../other.md")
        with self.assertRaisesRegex(RelationshipError, "unknown relationship"):
            link(kind="follows")

    def test_deterministic_forward_and_reverse_lookup(self):
        edges = [
            link(source=P, kind="addresses", target=A, path="plans/72/plan.md"),
            link(source=R, kind="includes", target=P, role="included", path="releases/15.md"),
            link(),
        ]
        records = [R, G, A, P]
        one = RelationshipIndex(records, edges, schema=SCHEMA)
        two = RelationshipIndex(reversed(records), reversed(edges), schema=SCHEMA)
        self.assertEqual(one.relationships, two.relationships)
        self.assertEqual(one.incoming(G, "measures"), (link(),))
        self.assertEqual(one.outgoing(P, "addresses")[0].target, A)
        self.assertEqual(len(one.incoming(P, "includes")), 1)
        self.assertEqual(one.incoming(P, "listed-in"), ())

    def test_duplicates_unknowns_and_missing_primary_fail_closed(self):
        with self.assertRaisesRegex(RelationshipError, "duplicate record identity"):
            RelationshipIndex([A, A], [link()], schema=SCHEMA)
        with self.assertRaisesRegex(RelationshipError, "unknown"):
            RelationshipIndex([A], [link()], schema=SCHEMA)
        with self.assertRaisesRegex(RelationshipError, "duplicate or contradictory"):
            RelationshipIndex([A, G], [link(), link(role="supporting")], schema=SCHEMA)
        with self.assertRaisesRegex(RelationshipError, "one primary"):
            RelationshipIndex([A, G], [link(role="supporting")], schema=SCHEMA)
        with self.assertRaisesRegex(RelationshipError, "one primary"):
            RelationshipIndex([A, B, G], [link()], schema=SCHEMA)

    def test_primary_per_domain_and_explicit_enabler(self):
        edges = [
            link(),
            link(source=P, kind="addresses", target=A, path="plans/72/plan.md"),
        ]
        self.assertEqual(len(RelationshipIndex([G, A, P], edges, schema=SCHEMA).relationships), 2)
        with self.assertRaisesRegex(RelationshipError, "one primary"):
            RelationshipIndex([G, A, P], [link()], schema=SCHEMA)
        enabler = RelationshipIndex([G, A, P], [link()], schema=SCHEMA, enablers=[P])
        self.assertIn(P, enabler.enablers)
        with self.assertRaisesRegex(RelationshipError, "foundational enabler"):
            RelationshipIndex([G, A], [link()], schema=SCHEMA, enablers=[P])

    def test_frozen_issue_release_link(self):
        edge = link(source=I, kind="listed-in", target=R, role="frozen",
                    path="releases/15.md")
        snap = RelationshipIndex([I, R], [edge], schema=SCHEMA)
        self.assertEqual(snap.outgoing(I), (edge,))
        with self.assertRaisesRegex(RelationshipError, "invalid role"):
            link(source=I, kind="listed-in", target=R, role="planned")


class LocatedAssertions(unittest.TestCase):
    def refuse(self, operation, path, line, message):
        with self.assertRaises(RelationshipError) as raised:
            operation()
        error = raised.exception
        self.assertEqual(error.source, SourceLocation(path, line))
        self.assertEqual(error.message, message)
        self.assertEqual(str(error), f"{path}:{line}: {message}")


class DevWorkspaceTests(LocatedAssertions):
    """Use the unchanged declaration and materialized roots, not a second schema.

    The stub adapter is the OT-7 export boundary. Synthetic authored records
    and rows represent the adapter's output; domain parsing remains local.
    """

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.raw = DEV.read_bytes()
        data = tomllib.loads(self.raw.decode())
        self.config = self.root / "otto.toml"
        shutil.copyfile(DEV, self.config)
        paths = data["paths"]
        for kind in data["record_kinds"]:
            (self.root / paths[kind["root"]]).mkdir(parents=True, exist_ok=True)
        if "pack_templates" in paths:
            (self.root / paths["pack_templates"]).mkdir(parents=True, exist_ok=True)
        adapter = self.root / data["adapters"]["module"]
        adapter.parent.mkdir(parents=True, exist_ok=True)
        adapter.write_text(
            "from otto.records import RecordBatch\n"
            + f"def {data['adapters']['records']}(workspace): return RecordBatch()\n"
            + f"def {data['checks']['register']}(workspace): return ()\n"
            + f"def {data['views']['register']}(workspace): return ((), [])\n",
            encoding="utf-8",
        )
        self.goal_path = "vision/pillars/artistic-ambition.md"
        self.gap_path = "vision/gaps/AA-001.md"
        self.project_path = "plans/72-example/plan.md"
        self.release_path = "releases/15.md"
        self.g2 = SCHEMA.ref("goal", "pillar:artistic-ambition/keep-edits")
        self.write(self.goal_path, "# Example\n## Finish a work\n\n## Keep edits\n")
        self.write(self.gap_path, "# AA-001\n\n## Relationships\n"
                   "| measures | goal:pillar:artistic-ambition/finish-a-work | primary |\n")
        self.write(self.project_path, "# Project\n\n## Relationships\n"
                   "| addresses | gap:AA-001 | primary |\n")
        self.write(self.release_path, "# Release 15\n\n"
                   "| includes | project:72 | included |\n"
                   "| issue:123 | listed-in | release:15 | frozen |\n")
        self.records = (
            Record(G, SourceLocation(self.goal_path, 2)),
            Record(self.g2, SourceLocation(self.goal_path, 4)),
            Record(A, SourceLocation(self.gap_path, 1)),
            Record(P, SourceLocation(self.project_path, 1)),
            Record(R, SourceLocation(self.release_path, 1)),
            Record(I, SourceLocation(self.release_path, 4)),
        )
        self.rows = (
            RelationshipRow(A, "measures", G, "primary", self.gap_path, 4),
            RelationshipRow(P, "addresses", A, "primary", self.project_path, 4),
            RelationshipRow(R, "includes", P, "included", self.release_path, 3),
            RelationshipRow(I, "listed-in", R, "frozen", self.release_path, 4),
        )

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def append(self, path, text):
        target = self.root / path
        original = target.read_text(encoding="utf-8")
        target.write_text(original + text + "\n", encoding="utf-8")
        return len(original.splitlines()) + 1

    def change_row(self, row, **changes):
        changed = replace(row, **changes)
        target = self.root / row.source_path
        lines = target.read_text(encoding="utf-8").splitlines()
        lines[row.source_line - 1] = (
            f"| {changed.kind} | {changed.target} | {changed.role} |")
        self.write(row.source_path, "\n".join(lines) + "\n")
        return (changed,) + self.rows[1:]

    def graph(self, records=None, rows=None, *, enablers=()):
        workspace = load_workspace(self.root)
        schema = RelationshipSchema.from_workspace(workspace, enablers=POLICY)
        return RelationshipIndex.from_batch(
            RecordBatch(self.records if records is None else records,
                        self.rows if rows is None else rows),
            schema=schema, enablers=enablers)

    def test_dev_positive_workspace(self):
        graph = self.graph()
        self.assertEqual(graph.records, frozenset(r.ref for r in self.records))
        self.assertEqual(len(graph.relationships), 4)
        self.assertEqual(graph.outgoing(A)[0].source_location,
                         SourceLocation(self.gap_path, 4))
        self.assertEqual(graph.incoming(R, "listed-in")[0].source, I)
        self.assertEqual(self.config.read_bytes(), self.raw)
        self.assertEqual(DEV.read_bytes(), self.raw)

    def test_graph_duplicate_record(self):
        path = "plans/72-other/plan.md"
        self.write(path, "\n# Other project\n")
        duplicate = Record(P, SourceLocation(path, 2))
        self.refuse(lambda: self.graph(records=self.records + (duplicate,)),
                    path, 2, "duplicate record identity")

    def test_graph_unknown_target(self):
        missing = SCHEMA.ref("goal", "pillar:artistic-ambition/missing")
        rows = self.change_row(self.rows[0], target=missing)
        self.refuse(lambda: self.graph(rows=rows), self.gap_path, 4,
                    f"{self.gap_path}: measures names unknown {missing}")

    def test_graph_wrong_endpoint_kind(self):
        rows = self.change_row(self.rows[0], target=P)
        self.refuse(lambda: self.graph(rows=rows), self.gap_path, 4,
                    "measures requires gap -> goal, got gap -> project")

    def test_dev_gap_two_primaries(self):
        line = self.append(self.gap_path, f"| measures | {self.g2} | primary |")
        second = replace(self.rows[0], target=self.g2, source_line=line)
        self.refuse(lambda: self.graph(rows=(second,) + self.rows),
                    self.gap_path, line,
                    "gap:AA-001: expected one primary measures relationship, found 2")

    def test_graph_contradictory_role(self):
        line = self.append(self.gap_path, f"| measures | {G} | supporting |")
        second = replace(self.rows[0], role="supporting", source_line=line)
        self.refuse(lambda: self.graph(rows=self.rows + (second,)),
                    self.gap_path, line,
                    f"{self.gap_path}: duplicate or contradictory measures {A} -> {G}")

    def test_graph_duplicate_same_role(self):
        line = self.append(self.gap_path, f"| measures | {G} | primary |")
        second = replace(self.rows[0], source_line=line)
        self.refuse(lambda: self.graph(rows=self.rows + (second,)),
                    self.gap_path, line,
                    f"{self.gap_path}: duplicate or contradictory measures {A} -> {G}")

    def test_graph_invalid_role(self):
        rows = self.change_row(self.rows[0], role="secondary")
        self.refuse(lambda: self.graph(rows=rows), self.gap_path, 4,
                    "measures: invalid role 'secondary'")

    def test_dev_project_missing_primary(self):
        self.write(self.project_path, "# Project\n")
        rows = self.rows[:1] + self.rows[2:]
        self.refuse(lambda: self.graph(rows=rows), self.project_path, 1,
                    "project:72: expected one primary addresses relationship, found 0")
        self.assertIn(P, self.graph(rows=rows, enablers=[P]).enablers)

    def test_dev_enabler_addresses(self):
        self.refuse(lambda: self.graph(enablers=[P]), self.project_path, 4,
                    f"{self.project_path}: enabler project:72 cannot declare addresses")

    def test_dev_invalid_enabler(self):
        self.refuse(lambda: self.graph(enablers=[A]), self.gap_path, 1,
                    "foundational enabler must be an existing project")

    def declaration_refusal(self, old, new, offending, message, *, occurrence=1):
        text = self.raw.decode().replace(old, new, 1)
        self.assertNotEqual(text, self.raw.decode())
        self.config.write_text(text, encoding="utf-8")
        line = [n for n, value in enumerate(text.splitlines(), 1)
                if offending in value][occurrence - 1]
        workspace = load_workspace(self.root)
        self.refuse(lambda: RelationshipSchema.from_workspace(workspace),
                    "otto.toml", line, message)

    def test_relation_duplicate_kind(self):
        self.declaration_refusal('name = "addresses"', 'name = "measures"',
                                 'name = "measures"', "duplicate relation kind 'measures'",
                                 occurrence=2)

    def test_relation_unknown_kind(self):
        for field, original in (("sources", "gap"), ("targets", "goal")):
            with self.subTest(field=field):
                self.declaration_refusal(f'{field} = ["{original}"]',
                                         f'{field} = [\n  "missing",\n]',
                                         '  "missing",',
                                         "relation measures names unknown record kind 'missing'")

    def test_relation_empty_endpoint(self):
        for field, original in (("sources", '["gap"]'), ("targets", '["goal"]'),
                                ("roles", '["primary", "supporting"]')):
            with self.subTest(field=field):
                self.declaration_refusal(f"{field} = {original}", f"{field} = []",
                                         f"{field} = []",
                                         f"relation measures requires nonempty {field}")

    def test_relation_duplicate_role(self):
        self.declaration_refusal('roles = ["primary", "supporting"]',
                                 'roles = ["primary", "supporting",\n  "primary",\n]',
                                 '  "primary",', "relation measures repeats role 'primary'")

    def test_relation_duplicate_source_or_target(self):
        for field, value, singular in (("sources", "gap", "source"),
                                       ("targets", "goal", "target")):
            with self.subTest(field=field):
                self.declaration_refusal(f'{field} = ["{value}"]',
                                         f'{field} = ["{value}",\n  "{value}",\n]',
                                         f'  "{value}",',
                                         f"relation measures repeats {singular} kind {value!r}")

    def test_relation_cardinality_token(self):
        self.declaration_refusal('per_source = "any"', 'per_source = "two"',
                                 'per_source = "two"', "unknown cardinality 'two'")
        self.declaration_refusal('[relation_kinds.by_role.primary]\nper_source = "exactly-one"',
                                 '[relation_kinds.by_role.primary]\nper_source = "two"',
                                 'per_source = "two"', "unknown cardinality 'two'")

    def test_relation_role_bound(self):
        self.declaration_refusal("[relation_kinds.by_role.supporting]",
                                 "[relation_kinds.by_role.secondary]",
                                 "[relation_kinds.by_role.secondary]",
                                 "relation measures has cardinality for unknown role 'secondary'")

    def test_relation_impossible_bounds(self):
        text = self.raw.decode().replace('per_source = "any"', 'per_source = "at-most-one"', 1)
        text = text.replace('[relation_kinds.by_role.supporting]\nper_source = "any"',
                            '[relation_kinds.by_role.supporting]\nper_source = "exactly-one"', 1)
        self.config.write_text(text, encoding="utf-8")
        line = text.splitlines().index('per_source = "at-most-one"') + 1
        workspace = load_workspace(self.root)
        self.refuse(lambda: RelationshipSchema.from_workspace(workspace),
                    "otto.toml", line,
                    "inconsistent cardinality bounds for relation measures at source")

    def test_relation_impossible_incoming_bounds(self):
        text = self.raw.decode().replace('per_target = "any"', 'per_target = "at-most-one"', 1)
        text = text.replace('[relation_kinds.by_role.primary]\nper_source = "exactly-one"\nper_target = "any"',
                            '[relation_kinds.by_role.primary]\nper_source = "exactly-one"\nper_target = "exactly-one"')
        text = text.replace('[relation_kinds.by_role.supporting]\nper_source = "any"\nper_target = "any"',
                            '[relation_kinds.by_role.supporting]\nper_source = "any"\nper_target = "exactly-one"')
        self.config.write_text(text, encoding="utf-8")
        line = text.splitlines().index('per_target = "at-most-one"') + 1
        workspace = load_workspace(self.root)
        self.refuse(lambda: RelationshipSchema.from_workspace(workspace),
                    "otto.toml", line,
                    "inconsistent cardinality bounds for relation measures at target")


def generic_schema(**bounds):
    return RelationshipSchema.from_declarations(
        ("note", "idea", "topic", "area", "other"),
        (dict(name="tags", sources=["note", "idea"], targets=["topic", "area"],
              roles=["owner", "observer"], **bounds),),
        DeclarationSourceMap("otto.toml", {}))


class GenericGraphTests(LocatedAssertions):
    def setUp(self):
        self.note = Record(RecordRef("note", "one"), SourceLocation("notes/one.md", 2))
        self.idea = Record(RecordRef("idea", "two"), SourceLocation("ideas/two.md", 3))
        self.topic = Record(RecordRef("topic", "alpha"), SourceLocation("topics/alpha.md", 1))
        self.area = Record(RecordRef("area", "beta"), SourceLocation("areas/beta.md", 1))
        self.records = (self.note, self.idea, self.topic, self.area)

    def edge(self, schema, source, target, role="owner", line=4):
        return Relationship(source.ref, "tags", target.ref, role, source.source.path,
                            line, schema=schema)

    def test_cardinality_vocabulary(self):
        self.assertEqual(cardinality_bounds("exactly-one"), (1, 1))
        self.assertEqual(cardinality_bounds("at-most-one"), (0, 1))
        self.assertEqual(cardinality_bounds("one-or-more"), (1, None))
        self.assertEqual(cardinality_bounds("any"), (0, None))
        with self.assertRaisesRegex(RelationshipError, "unknown cardinality 'two'"):
            cardinality_bounds("two")

    def test_defaults_cartesian_endpoints_and_immutable_snapshot(self):
        schema = generic_schema()
        edges = [self.edge(schema, s, t, "observer")
                 for s in (self.note, self.idea) for t in (self.topic, self.area)]
        one = RelationshipIndex(self.records, edges, schema=schema)
        two = RelationshipIndex(reversed(self.records), reversed(edges), schema=schema)
        self.assertEqual(one.relationships, two.relationships)
        self.assertEqual(len(one.outgoing(self.note.ref)), 2)
        self.assertEqual(len(one.incoming(self.topic.ref)), 2)
        self.assertEqual(schema.relation_kinds["tags"].per_source, "any")
        self.assertEqual(RelationshipIndex(self.records, [], schema=schema).relationships, ())
        with self.assertRaises(TypeError):
            schema.relation_kinds["another"] = schema.relation_kinds["tags"]
        with self.assertRaises(FrozenInstanceError):
            one.relationships = ()
        with self.assertRaises(FrozenInstanceError):
            edges[0].source_line = 20

    def test_schema_isolation_and_immediate_multi_endpoint_refusal(self):
        schema = generic_schema()
        self.refuse(lambda: Relationship(self.topic.ref, "tags", self.note.ref,
                                        "owner", "topics/alpha.md", 5, schema=schema),
                    "topics/alpha.md", 5,
                    "tags requires idea or note -> area or topic, got topic -> note")
        with self.assertRaisesRegex(RelationshipError, "unknown record kind: 'note'"):
            SCHEMA.ref("note", "one")
        self.assertEqual(schema.ref("note", "one"), self.note.ref)
        narrower = RelationshipSchema.from_declarations(
            schema.record_kinds,
            (dict(name="tags", sources=["idea"], targets=["topic"], roles=["owner"]),),
            DeclarationSourceMap("otto.toml", {}))
        edge = self.edge(schema, self.note, self.topic)
        self.refuse(lambda: RelationshipIndex(self.records, [edge], schema=narrower),
                    "notes/one.md", 4, "tags requires idea -> topic, got note -> topic")
        self.assertEqual(RelationshipIndex(self.records, [edge], schema=schema).relationships,
                         (edge,))

    def test_source_total_degree_excess_at_first_excess_row(self):
        schema = generic_schema(per_source="at-most-one")
        early = self.edge(schema, self.note, self.topic, line=5)
        excess = self.edge(schema, self.note, self.area, "observer", line=9)
        self.refuse(lambda: RelationshipIndex(self.records, [excess, early], schema=schema),
                    "notes/one.md", 9,
                    "note:one has 2 tags targets; expected at-most-one")
        self.assertEqual(len(RelationshipIndex(self.records, [early], schema=schema).relationships), 1)

    def test_target_total_degree_excess_uses_authored_path_order(self):
        schema = generic_schema(per_target="at-most-one")
        early = self.edge(schema, self.idea, self.topic, line=9)
        excess = self.edge(schema, self.note, self.topic, "observer", line=4)
        self.refuse(lambda: RelationshipIndex(self.records, [excess, early], schema=schema),
                    "notes/one.md", 4,
                    "topic:alpha has 2 incoming tags sources; expected at-most-one")

    def test_total_minimum_counts_zero_degree_records(self):
        schema = generic_schema(per_source="one-or-more")
        edge = self.edge(schema, self.note, self.topic)
        self.refuse(lambda: RelationshipIndex(self.records, [edge], schema=schema),
                    "ideas/two.md", 3,
                    "idea:two has 0 tags targets; expected one-or-more")
        incoming = generic_schema(per_target="exactly-one")
        edge = self.edge(incoming, self.note, self.topic)
        self.refuse(lambda: RelationshipIndex(self.records, [edge], schema=incoming),
                    "areas/beta.md", 1,
                    "area:beta has 0 incoming tags sources; expected exactly-one")

    def test_non_primary_role_source_bounds_and_unlisted_roles(self):
        schema = generic_schema(by_role={"owner": {"per_source": "exactly-one"}})
        owner = self.edge(schema, self.note, self.topic)
        observer = self.edge(schema, self.note, self.area, "observer", line=5)
        other = self.edge(schema, self.idea, self.topic)
        graph = RelationshipIndex(self.records, [owner, observer, other], schema=schema)
        self.assertEqual(len(graph.outgoing(self.note.ref)), 2)
        self.refuse(lambda: RelationshipIndex(self.records, [owner, observer], schema=schema),
                    "ideas/two.md", 3,
                    "idea:two has 0 owner tags targets; expected exactly-one")
        second_owner = self.edge(schema, self.note, self.area, line=5)
        self.refuse(lambda: RelationshipIndex(self.records, [second_owner, owner, other],
                                             schema=schema),
                    "notes/one.md", 5,
                    "note:one has 2 owner tags targets; expected exactly-one")
        with self.assertRaises(TypeError):
            schema.relation_kinds["tags"].by_role["owner"]["per_source"] = "any"

    def test_role_target_degree_and_total_both_apply(self):
        schema = generic_schema(per_target="one-or-more",
                                by_role={"owner": {"per_target": "at-most-one"}})
        first = self.edge(schema, self.idea, self.topic)
        second = self.edge(schema, self.note, self.topic, line=7)
        control = self.edge(schema, self.note, self.area, "observer", line=8)
        self.refuse(lambda: RelationshipIndex(self.records, [second, first, control], schema=schema),
                    "notes/one.md", 7,
                    "topic:alpha has 2 owner incoming tags sources; expected at-most-one")
        graph = RelationshipIndex(self.records, [
            first, self.edge(schema, self.note, self.topic, "observer", line=7), control
        ], schema=schema)
        self.assertEqual(len(graph.incoming(self.topic.ref)), 2)

    def test_legacy_unlocated_calls_and_explicit_line_validation(self):
        schema = generic_schema()
        edge = Relationship(self.note.ref, "tags", self.topic.ref, "owner",
                            "notes/one.md", schema=schema)
        self.assertIsNone(edge.source_location)
        with self.assertRaises(RelationshipError) as raised:
            RelationshipIndex([self.note.ref], [edge], schema=schema)
        self.assertIsNone(raised.exception.source)
        self.assertEqual(str(raised.exception), "notes/one.md: tags names unknown topic:alpha")
        for line in (0, -1, True, "2"):
            with self.subTest(line=line), self.assertRaises(RelationshipError) as raised:
                Relationship(self.note.ref, "tags", self.topic.ref, "owner",
                             "notes/one.md", line, schema=schema)
            self.assertEqual(str(raised.exception), f"tags: invalid source line {line!r}")

    def test_enablers_are_not_a_global_exception(self):
        schema = generic_schema()
        with self.assertRaisesRegex(RelationshipError, "enablers require an explicit schema rule"):
            RelationshipIndex(self.records, [], schema=schema, enablers=[self.note.ref])
        local = RelationshipSchema.from_declarations(
            schema.record_kinds,
            (dict(name="tags", sources=["note"], targets=["topic"], roles=["owner"],
                  per_source="exactly-one"),),
            DeclarationSourceMap("otto.toml", {}),
            enablers=EnablerRule("note", "tags", "owner", "not an existing note"))
        self.refuse(lambda: RelationshipIndex(self.records, [], schema=local,
                                             enablers=[self.note.ref]),
                    "notes/one.md", 2,
                    "note:one has 0 tags targets; expected exactly-one")

    def test_unknown_record_kind_at_authored_identity(self):
        schema = generic_schema()
        unexpected = Record(RecordRef("unknown", "one"), SourceLocation("notes/one.md", 2))
        self.refuse(lambda: RelationshipIndex([unexpected], [], schema=schema),
                    "notes/one.md", 2, "unknown record kind: 'unknown'")


if __name__ == "__main__":
    unittest.main()
