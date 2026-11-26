"""OT-10: located conformance failures and independent, read-only pipelines.

Use the committed TOML specimens unchanged and materialize only synthetic
Markdown and adapters in temporary directories; no production data is needed.
"""
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from otto.checks import Context
from otto.config import load_workspace
from otto.conformance import (
    PIPELINE_CONFORMANCE, check_pipeline_conformance, evaluate_pipeline,
    pipeline_conformance,
)
from otto.ids import LocatedError
from otto.pipelines import load_pipelines
from otto.records import RecordBatch, load_records
from otto.relationships import RelationshipIndex, RelationshipSchema


FIXTURES = Path(__file__).parent / "fixtures"
STRATEGY = "pipelines/strategy.toml"
INTAKE = "pipelines/intake.toml"
LAUNCH = "projects/launch-note/plan.md"
ISSUE = "issues/clarify-heading.md"
IDEA = "ideas/short-example.md"
CAMPAIGN = "campaigns/sample-week.md"

GOAL_EDGE = ("serves", "goal:clear-example", "primary")
ROUTE_EDGE = ("routes-to", "project:launch-note", "primary")
CAMPAIGN_EDGES = (
    ("includes", "project:launch-note", "included"),
    ("includes", "project:try-message", "included"),
)


class WorkspaceFixture(unittest.TestCase):
    specimen = "marketing"

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        fixture = FIXTURES / self.specimen
        shutil.copyfile(fixture / "otto.toml", self.root / "otto.toml")
        config = tomllib.loads((fixture / "otto.toml").read_text(encoding="utf-8"))
        for kind in config["record_kinds"]:
            (self.root / config["paths"][kind["root"]]).mkdir(parents=True, exist_ok=True)
        if "pack_templates" in config["paths"]:
            (self.root / config["paths"]["pack_templates"]).mkdir(parents=True, exist_ok=True)
        shutil.copytree(fixture / "pipelines", self.root / "pipelines")
        self.adapter = config["adapters"]["module"]

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def replace(self, name, old, new):
        text = (self.root / name).read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.write(name, text.replace(old, new, 1))

    def verdict(self):
        return PIPELINE_CONFORMANCE.run(Context(self.root))

    def snapshot(self):
        workspace = load_workspace(self.root)
        schema = RelationshipSchema.from_workspace(workspace)
        batch = load_records(workspace)
        index = RelationshipIndex.from_batch(batch, schema=schema)
        return workspace, schema, batch, index

    def record_bytes(self):
        ws = load_workspace(self.root)
        paths = {path for sources in ws.sources.values() for path in sources}
        paths.update(path.relative_to(self.root).as_posix()
                     for path in self.root.rglob("tasks.md"))
        return {path: (self.root / path).read_bytes() for path in paths}


class MarketingConformance(WorkspaceFixture):
    def setUp(self):
        super().setUp()
        self.write(self.adapter, """from otto.ids import RecordRef, SourceLocation
from otto.records import Record, RecordBatch

def load_strategy_goals(workspace):
    records = []
    for number, row in enumerate(
            (workspace.root / "strategy.md").read_text(encoding="utf-8").splitlines(), 1):
        if number < 7:
            continue
        identity, title = (cell.strip() for cell in row.strip("|").split("|"))
        records.append(Record(RecordRef("goal", identity),
                              SourceLocation("strategy.md", number), title))
    return RecordBatch(tuple(records))

def register_checks(workspace): return ()
def register_views(workspace): return ((), [])
""")
        self.goals()
        for identity in ("launch-note", "try-message", "standalone-note"):
            self.project(identity)
            self.write(f"projects/{identity}/tasks.md", "# Tasks\n- [ ] Example\n")
        self.campaign()
        self.issue()
        self.idea()

    def goals(self, *extra):
        self.write("strategy.md", "# Example strategy\n\n## Goals\n\n"
                   "| ID | Goal |\n| --- | --- |\n"
                   + "".join(f"| {identity} | Example goal |\n"
                             for identity in ("clear-example", *extra)))

    def document(self, path, title, edges, *, status=None, frontmatter=False):
        lines = ["---", f"status: {status}", "---"] if frontmatter else []
        lines.extend([f"# {title}", ""])
        if not frontmatter and status is not None:
            lines.extend([f"**Status:** {status}", ""])
        lines.extend(["## Relationships", "", "| Relation | Target | Role |",
                      "| --- | --- | --- |"])
        lines.extend(f"| {relation} | {target} | {role} |"
                     for relation, target, role in edges)
        self.write(path, "\n".join(lines) + "\n")

    def project(self, identity="launch-note", *, edges=(GOAL_EDGE,), status="queued"):
        self.document(f"projects/{identity}/plan.md", "Example project", edges, status=status)

    def campaign(self, identity="sample-week", edges=CAMPAIGN_EDGES):
        self.document(f"campaigns/{identity}.md", "Example campaign", edges)

    def issue(self, edges=(ROUTE_EDGE,)):
        self.document(ISSUE, "Example issue", edges)

    def idea(self, edges=()):
        self.document(IDEA, "Example idea", edges, status="queued", frontmatter=True)

    def narrow_source(self):
        self.replace(INTAKE, 'kinds = ["issue", "idea"]', 'kinds = ["issue"]')

    def broaden_targets(self):
        self.replace("otto.toml",
                     'name = "routes-to"\nsources = ["issue", "idea"]\ntargets = ["project"]',
                     'name = "routes-to"\nsources = ["issue", "idea"]\ntargets = ["project", "goal"]')

    def test_clean_marketing_and_registry_shape(self):
        self.assertEqual(PIPELINE_CONFORMANCE.id, "pipeline-conformance")
        self.assertEqual(PIPELINE_CONFORMANCE.trigger, "always")
        self.assertIs(PIPELINE_CONFORMANCE.run, pipeline_conformance)
        before = self.record_bytes()
        self.assertEqual(self.verdict(), [])
        self.assertEqual(self.record_bytes(), before)

    def test_degree_source_max(self):
        # The second authored row is deliberately first by target ID.
        self.issue((("routes-to", "project:try-message", "primary"),
                    ("routes-to", "project:launch-note", "supporting")))
        self.replace(INTAKE, 'per_source = "any"', 'per_source = "at-most-one"')
        self.assertEqual(self.verdict(), [
            f"{ISSUE}:8: pipeline intake: issue:clarify-heading has 2 routes-to targets; expected at-most-one"
        ])

    def test_degree_target_max(self):
        self.campaign("z-extra", (CAMPAIGN_EDGES[0],))
        self.replace(STRATEGY, 'per_target = "one-or-more"', 'per_target = "at-most-one"')
        self.assertEqual(self.verdict(), [
            "campaigns/z-extra.md:7: pipeline strategy: project:launch-note has 2 incoming includes sources; expected at-most-one"
        ])

    def test_required_stage_absent(self):
        self.project(edges=())
        self.assertEqual(self.verdict(), [
            f"{LAUNCH}:1: pipeline strategy: project:launch-note has no required goal through serves"
        ])

    def test_optional_stage_absent(self):
        (self.root / CAMPAIGN).unlink()
        self.assertEqual(self.verdict(), [])

    def test_optional_stage_present_empty(self):
        self.campaign(edges=())
        self.assertEqual(self.verdict(), [
            f"{CAMPAIGN}:1: pipeline strategy: campaign:sample-week has no required project through includes"
        ])

    def test_role_two_primaries(self):
        self.goals("another-goal")
        self.project(edges=(GOAL_EDGE, ("serves", "goal:another-goal", "primary")))
        self.assertEqual(self.verdict(), [
            f"{LAUNCH}:10: pipeline strategy: project:launch-note has 2 primary serves targets; expected exactly-one"
        ])

    def test_role_supporting_valid(self):
        self.goals("another-goal", "third-goal")
        self.project(edges=(GOAL_EDGE, ("serves", "goal:another-goal", "supporting"),
                            ("serves", "goal:third-goal", "supporting")))
        self.assertEqual(self.verdict(), [])

    def test_stage_source_kind(self):
        self.idea((ROUTE_EDGE,))
        self.assertEqual(self.verdict(), [])
        self.narrow_source()
        self.assertEqual(self.verdict(), [
            f"{IDEA}:10: pipeline intake: routes-to source idea:short-example is not allowed in stage intake"
        ])

    def test_stage_target_kind_global_graph_failure(self):
        self.campaign(edges=(("includes", "goal:clear-example", "included"),))
        # The same graph error, not a pipeline-specific duplicate or a missing
        # stage inferred from a partial graph.
        self.project(status="published", edges=())
        self.assertEqual(self.verdict(), [
            f"{CAMPAIGN}:7: includes requires campaign -> project, got campaign -> goal"
        ])

    def test_stage_target_kind_pipeline_narrowing_and_secondary_absence(self):
        self.broaden_targets()
        self.issue((("routes-to", "goal:clear-example", "primary"),))
        self.replace(INTAKE, 'per_source = "any"', 'per_source = "one-or-more"')
        self.narrow_source()
        self.assertEqual(self.verdict(), [
            f"{ISSUE}:1: pipeline intake: issue:clarify-heading has no required project through routes-to",
            f"{ISSUE}:7: pipeline intake: routes-to target goal:clear-example is not allowed in stage project",
        ])

    def test_both_endpoints_wrong_same_row(self):
        self.broaden_targets()
        self.narrow_source()
        self.idea((("routes-to", "goal:clear-example", "primary"),))
        self.assertEqual(self.verdict(), [
            f"{IDEA}:10: pipeline intake: routes-to source idea:short-example is not allowed in stage intake",
            f"{IDEA}:10: pipeline intake: routes-to target goal:clear-example is not allowed in stage project",
        ])

    def test_stage_status(self):
        self.project(status="published")
        self.assertEqual(self.verdict(), [
            f"{LAUNCH}:3: pipeline strategy: project:launch-note status 'published' is not allowed in stage project"
        ])

    def test_stage_status_missing(self):
        self.project(status=None)
        self.assertEqual(self.verdict(), [
            f"{LAUNCH}:1: pipeline strategy: project:launch-note has no status for stage project"
        ])

    def test_zero_degree_record_counted(self):
        self.project("new-project", edges=())
        self.assertEqual(self.verdict(), [
            "projects/new-project/plan.md:1: pipeline strategy: project:new-project has no required goal through serves"
        ])

    def test_wrong_status_does_not_filter_membership(self):
        self.project(status="Queued", edges=())
        self.assertEqual(self.verdict(), [
            f"{LAUNCH}:1: pipeline strategy: project:launch-note has no required goal through serves",
            f"{LAUNCH}:3: pipeline strategy: project:launch-note status 'Queued' is not allowed in stage project",
        ])

    def test_role_only_minimum_absence_and_nonzero_wrong_role(self):
        self.replace(STRATEGY, 'per_source = "one-or-more"', 'per_source = "any"')
        self.project(edges=())
        self.assertEqual(self.verdict(), [
            f"{LAUNCH}:1: pipeline strategy: project:launch-note has no required goal through serves"
        ])
        self.project(edges=(("serves", "goal:clear-example", "supporting"),))
        self.assertEqual(self.verdict(), [
            f"{LAUNCH}:1: pipeline strategy: project:launch-note has 0 primary serves targets; expected exactly-one"
        ])

    def test_incoming_role_degree(self):
        self.idea((ROUTE_EDGE,))
        self.replace(INTAKE, 'per_source = "at-most-one"\nper_target = "any"',
                     'per_source = "at-most-one"\nper_target = "at-most-one"')
        # idea path sorts before issue path: the latter is the first excess.
        self.assertEqual(self.verdict(), [
            f"{ISSUE}:7: pipeline intake: project:launch-note has 2 primary incoming routes-to sources; expected at-most-one"
        ])

    def test_independent_total_and_role_maxima(self):
        self.replace(INTAKE, 'per_source = "any"', 'per_source = "at-most-one"')
        self.issue((ROUTE_EDGE, ("routes-to", "project:try-message", "primary")))
        self.assertEqual(self.verdict(), [
            f"{ISSUE}:8: pipeline intake: issue:clarify-heading has 2 primary routes-to targets; expected at-most-one",
            f"{ISSUE}:8: pipeline intake: issue:clarify-heading has 2 routes-to targets; expected at-most-one",
        ])

    def test_optional_source_relaxes_incoming_role_minimum_only(self):
        text = (self.root / STRATEGY).read_text(encoding="utf-8")
        self.write(STRATEGY, text + '\n[links.by_role.included]\n'
                   'per_source = "one-or-more"\nper_target = "one-or-more"\n')
        self.assertEqual(self.verdict(), [])
        (self.root / CAMPAIGN).unlink()
        self.assertEqual(self.verdict(), [])
        self.campaign(edges=())
        self.assertEqual(self.verdict(), [
            f"{CAMPAIGN}:1: pipeline strategy: campaign:sample-week has no required project through includes"
        ])

    def test_optional_target_relaxes_outgoing_role_minimum_only(self):
        self.replace(STRATEGY, 'kinds = ["goal"]', 'kinds = ["goal"]\noptional = true')
        self.replace(STRATEGY, 'per_source = "exactly-one"', 'per_source = "one-or-more"')
        for identity in ("launch-note", "try-message", "standalone-note"):
            self.project(identity, edges=())
        self.assertEqual(self.verdict(), [])
        # Upper bounds remain enforced even when the counted stage is optional.
        self.replace(STRATEGY, '[links.by_role.primary]\nper_source = "one-or-more"',
                     '[links.by_role.primary]\nper_source = "at-most-one"')
        self.goals("another-goal")
        self.project(edges=(GOAL_EDGE, ("serves", "goal:another-goal", "primary")))
        self.assertEqual(self.verdict(), [
            f"{LAUNCH}:10: pipeline strategy: project:launch-note has 2 primary serves targets; expected at-most-one"
        ])

    def test_no_hidden_minimum_and_optional_source_upper(self):
        # Both intake stages were required and total bounds any; there is no
        # hidden degree obligation. Making the source optional cannot weaken
        # its opposite-facing incoming maximum.
        self.issue(edges=())
        self.assertEqual(self.verdict(), [])
        self.replace(INTAKE, 'kinds = ["issue", "idea"]',
                     'kinds = ["issue", "idea"]\noptional = true')
        self.replace(INTAKE, 'per_source = "at-most-one"\nper_target = "any"',
                     'per_source = "at-most-one"\nper_target = "at-most-one"')
        self.issue()
        self.idea((ROUTE_EDGE,))
        self.assertEqual(self.verdict(), [
            f"{ISSUE}:7: pipeline intake: project:launch-note has 2 primary incoming routes-to sources; expected at-most-one"
        ])

    def test_global_sort_numeric_lines_and_shared_snapshot(self):
        self.goals("another-goal")
        self.project(edges=(GOAL_EDGE, ("serves", "goal:another-goal", "primary")),
                     status="published")
        self.replace(INTAKE, 'kinds = ["project"]', 'kinds = ["project"]\nstatuses = ["queued"]')
        ws, schema, batch, index = self.snapshot()
        before = self.record_bytes()
        expected = [
            f"{LAUNCH}:3: pipeline intake: project:launch-note status 'published' is not allowed in stage project",
            f"{LAUNCH}:3: pipeline strategy: project:launch-note status 'published' is not allowed in stage project",
            f"{LAUNCH}:10: pipeline strategy: project:launch-note has 2 primary serves targets; expected exactly-one",
        ]
        pipelines = load_pipelines(ws, schema=schema)
        self.assertEqual(evaluate_pipeline(pipelines["strategy"], batch, index), expected[1:])
        self.assertEqual(self.verdict(), expected)
        reverse = RecordBatch(tuple(reversed(batch.records)), tuple(reversed(batch.relationships)))
        reverse_index = RelationshipIndex.from_batch(reverse, schema=schema)
        with patch("otto.conformance.load_records", side_effect=AssertionError("snapshot reloaded")), \
                patch("otto.conformance.RelationshipIndex.from_batch",
                      side_effect=AssertionError("graph rebuilt")):
            self.assertEqual(check_pipeline_conformance(
                ws, schema=schema, batch=reverse, index=reverse_index), expected)
        self.assertEqual(self.record_bytes(), before)
        self.assertEqual(self.verdict(), expected)

    def test_delete_one_pipeline_keeps_records_and_other_verdicts(self):
        self.project(status="published")
        self.issue((ROUTE_EDGE, ("routes-to", "project:try-message", "primary")))
        ws, schema, batch, index = self.snapshot()
        before = self.record_bytes()
        self.assertEqual(self.verdict(), [
            f"{ISSUE}:8: pipeline intake: issue:clarify-heading has 2 primary routes-to targets; expected at-most-one",
            f"{LAUNCH}:3: pipeline strategy: project:launch-note status 'published' is not allowed in stage project",
        ])
        (self.root / INTAKE).unlink()
        self.assertEqual(self.verdict(), [
            f"{LAUNCH}:3: pipeline strategy: project:launch-note status 'published' is not allowed in stage project",
        ])
        _, _, after, after_index = self.snapshot()
        self.assertEqual(batch, after)
        self.assertEqual(index.records, after_index.records)
        self.assertEqual(index.relationships, after_index.relationships)
        self.assertEqual(self.record_bytes(), before)

    def test_no_pipelines_no_graph_load(self):
        _, _, batch, index = self.snapshot()
        before = self.record_bytes()
        (self.root / STRATEGY).unlink()
        (self.root / INTAKE).unlink()
        with patch("otto.conformance.load_records", side_effect=AssertionError("records loaded")):
            self.assertEqual(self.verdict(), [])
        _, _, after, after_index = self.snapshot()
        self.assertEqual(batch, after)
        self.assertEqual(index.relationships, after_index.relationships)
        self.assertEqual(index.records, after_index.records)
        self.assertEqual(self.record_bytes(), before)

    def test_invalid_pipeline_preserves_declaration_error(self):
        self.replace(INTAKE, 'id = "intake"', 'id = "different"')
        ws = load_workspace(self.root)
        with self.assertRaises(LocatedError) as error:
            load_pipelines(ws)
        with patch("otto.conformance.load_records", side_effect=AssertionError("invalid declaration")):
            self.assertEqual(check_pipeline_conformance(ws), [str(error.exception)])
        self.assertEqual(self.verdict(), [
            f"{INTAKE}:4: pipeline id 'different' does not match filename 'intake'"
        ])

    def test_invalid_configuration_preserves_located_error(self):
        self.replace("otto.toml", "version = 1", "version = 2")
        with self.assertRaises(LocatedError) as error:
            load_workspace(self.root)
        with patch("otto.conformance.load_pipelines", side_effect=AssertionError("invalid config")):
            self.assertEqual(self.verdict(), [str(error.exception)])

    def test_invalid_graph_stops_all_pipeline_evaluation(self):
        self.issue((("routes-to", "project:missing", "primary"),))
        self.project(status="published", edges=())
        with patch("otto.conformance._evaluate", side_effect=AssertionError("invalid graph")):
            self.assertEqual(self.verdict(), [
                f"{ISSUE}:7: {ISSUE}: routes-to names unknown project:missing"
            ])


class DevConformance(WorkspaceFixture):
    specimen = "dev"

    def test_clean_dev_and_release_less_project(self):
        # The specimen deliberately delegates Dev domain-specific policy to its
        # adapter. This synthetic adapter supplies authored, located rows.
        self.write("vision/pillars/example.md", "# Example pillar\n## Clear\n")
        self.write("vision/gaps/XX-001.md", "# XX-001\nPrimary: clear\n")
        self.write("plans/01-example/plan.md", "# Example project\nPrimary: XX-001\n")
        self.write("plans/02-enabler/plan.md", "# Example enabler\n**Vision role:** Foundational enabler\n")
        self.write("releases/1.md", "# Release 1\nProject: 01\nIssue: 1\n")
        self.write(self.adapter, """from otto.ids import RecordRef, SourceLocation
from otto.records import Record, RecordBatch, RelationshipRow

def load_dev_records(workspace):
    goal = RecordRef("goal", "pillar:example/clear")
    gap = RecordRef("gap", "XX-001")
    project = RecordRef("project", "01")
    enabler = RecordRef("project", "02")
    release = RecordRef("release", "1")
    issue = RecordRef("issue", "1")
    records = (
        Record(goal, SourceLocation("vision/pillars/example.md", 2)),
        Record(gap, SourceLocation("vision/gaps/XX-001.md", 1)),
        Record(project, SourceLocation("plans/01-example/plan.md", 1)),
        Record(enabler, SourceLocation("plans/02-enabler/plan.md", 1)),
        Record(release, SourceLocation("releases/1.md", 1)),
        Record(issue, SourceLocation("releases/1.md", 3)),
    )
    rows = (
        RelationshipRow(gap, "measures", goal, "primary", "vision/gaps/XX-001.md", 2),
        RelationshipRow(project, "addresses", gap, "primary", "plans/01-example/plan.md", 2),
        RelationshipRow(release, "includes", project, "included", "releases/1.md", 2),
        RelationshipRow(issue, "listed-in", release, "frozen", "releases/1.md", 3),
    )
    return RecordBatch(records, rows)

def register_dev_checks(workspace): return ()
def register_dev_views(workspace): return ((), [])
""")
        before = self.record_bytes()
        ws, schema, batch, index = self.snapshot()
        self.assertEqual(len(batch.records), 6)
        self.assertEqual(len(index.relationships), 4)
        self.assertEqual(set(load_pipelines(ws, schema=schema)), {"delivery", "issue"})
        self.assertEqual(self.verdict(), [])
        self.assertEqual(self.record_bytes(), before)


if __name__ == "__main__":
    unittest.main()
