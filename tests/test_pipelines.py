"""OT-9 declaration refusals and read-only query controls.

The committed TOML specimens remain unchanged. All planted invalid input and
synthetic record sources live in temporary workspaces.
"""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from otto.config import load_workspace
from otto.ids import LocatedError, RecordRef, SourceLocation
from otto.pipelines import (
    effective_bounds, list_pipelines, load_pipeline, load_pipeline_inventory,
    load_pipelines, show_pipeline, traverse,
)
from otto.records import Record, RecordBatch, RelationshipRow, load_records
from otto.relationships import RelationKind, Relationship, RelationshipIndex, RelationshipSchema


FIXTURES = Path(__file__).parent / "fixtures"
STRATEGY = (FIXTURES / "marketing/pipelines/strategy.toml").read_text(encoding="utf-8")
INTAKE = (FIXTURES / "marketing/pipelines/intake.toml").read_text(encoding="utf-8")
STRATEGY_PATH = "pipelines/strategy.toml"
STRATEGY_ROW = ("goal=goal:clear-example -> project=project:launch-note (serves, primary)"
                " -> campaign=campaign:sample-week (includes, included)\n")
STANDALONE_ROW = ("goal=goal:clear-example -> project=project:standalone-note (serves, primary)"
                  " -> campaign=-\n")
INTAKE_ROW = "intake=issue:clarify-heading -> project=project:launch-note (routes-to, primary)\n"


def line_of(text, needle, occurrence=1):
    lines = [i for i, line in enumerate(text.splitlines(), 1) if line.strip() == needle]
    return lines[occurrence - 1]


class FixtureWorkspace(unittest.TestCase):
    specimen = "marketing"

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        folder = FIXTURES / self.specimen
        shutil.copyfile(folder / "otto.toml", self.root / "otto.toml")
        config = tomllib.loads((folder / "otto.toml").read_text(encoding="utf-8"))
        for kind in config["record_kinds"]:
            (self.root / config["paths"][kind["root"]]).mkdir(parents=True, exist_ok=True)
        if "pack_templates" in config["paths"]:
            (self.root / config["paths"]["pack_templates"]).mkdir(parents=True, exist_ok=True)
        shutil.copytree(folder / "pipelines", self.root / "pipelines")
        self.adapter = config["adapters"]["module"]
        self.write(self.adapter,
                   "from otto.records import RecordBatch\n"
                   f"def {config['adapters']['records']}(workspace): return RecordBatch()\n"
                   f"def {config['checks']['register']}(workspace): return ()\n"
                   f"def {config['views']['register']}(workspace): return ((), [])\n")

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def workspace(self):
        return load_workspace(self.root)

    def schema(self):
        return RelationshipSchema.from_workspace(self.workspace())

    def refuse(self, operation, path, line, message):
        with self.assertRaises(LocatedError) as raised:
            operation()
        self.assertEqual(raised.exception.source, SourceLocation(path, line))
        self.assertEqual(raised.exception.message, message)
        self.assertEqual(str(raised.exception), f"{path}:{line}: {message}")

    def plant(self, text, message, needle=None, occurrence=1, *, line=None, schema=None):
        path = self.write(STRATEGY_PATH, text)
        if schema is None:
            schema = self.schema()
        if line is None:
            line = line_of(text, needle, occurrence)
        self.refuse(lambda: load_pipeline(path, schema, display_path=STRATEGY_PATH),
                    STRATEGY_PATH, line, message)

    def with_rule(self, name, **fields):
        schema = self.schema()
        rules = dict(schema.relation_kinds)
        rules[name] = replace(rules[name], **fields)
        return replace(schema, relation_kinds=rules)


class DeclarationTests(FixtureWorkspace):
    def test_positive_specimens_and_read_only_source_maps(self):
        workspace = self.workspace()
        loaded = load_pipelines(workspace)
        self.assertEqual(tuple(loaded), ("intake", "strategy"))
        strategy = loaded["strategy"]
        self.assertEqual(strategy.id, "strategy")
        self.assertEqual(tuple(s.id for s in strategy.stages), ("goal", "project", "campaign"))
        self.assertEqual(strategy.stages[1].kinds, frozenset({"project"}))
        self.assertEqual(strategy.stages[1].statuses,
                         ("queued", "active", "blocked", "paused", "done", "cancelled"))
        self.assertTrue(strategy.stages[2].optional)
        self.assertEqual([(l.from_stage, l.to_stage) for l in strategy.links],
                         [("project", "goal"), ("campaign", "project")])
        self.assertEqual(strategy.links[1].per_target, "one-or-more")
        self.assertEqual(effective_bounds("one-or-more", optional=True), (0, None))
        self.assertEqual(effective_bounds("at-most-one", optional=True), (0, 1))
        self.assertEqual(effective_bounds("one-or-more"), (1, None))
        self.assertEqual(strategy.source_map.location(("links", 1, "per_target")),
                         SourceLocation(STRATEGY_PATH, line_of(STRATEGY, 'per_target = "one-or-more"')))
        self.assertEqual(strategy.links[1].source,
                         SourceLocation(STRATEGY_PATH, line_of(STRATEGY, "[[links]]", 2)))
        with self.assertRaises(TypeError):
            loaded["other"] = strategy
        with self.assertRaises(FrozenInstanceError):
            strategy.stages[0].optional = True
        with self.assertRaises(TypeError):
            strategy.links[0].by_role["primary"]["per_source"] = "any"
        self.assertEqual((self.root / STRATEGY_PATH).read_text(encoding="utf-8"), STRATEGY)

    def test_id_mismatch_and_duplicate_inventory(self):
        self.plant(STRATEGY.replace('id = "strategy"', 'id = "other"'),
                   "pipeline id 'other' does not match filename 'strategy'", 'id = "other"')
        self.write(STRATEGY_PATH, STRATEGY)
        first = self.write("a/strategy.toml", STRATEGY)
        second = self.write("b/strategy.toml", "# second declaration\n" + STRATEGY)
        schema = self.schema()
        self.refuse(lambda: load_pipeline_inventory([second, first], schema, root=self.root),
                    "b/strategy.toml", 3, "duplicate pipeline id 'strategy'")

    def test_empty_chain(self):
        for value in ("[]", '[{id="goal", kinds=["goal"]}]'):
            with self.subTest(value=value):
                self.plant(f'version = 1\nid = "strategy"\nstages = {value}\nlinks = []\n',
                           "pipeline strategy requires at least two stages", line=3)

    def test_stage_id_duplicate_unknown_kind_empty_duplicate_kinds(self):
        cases = (
            ('id = "project"', 'id = "goal"', "pipeline strategy repeats stage 'goal'",
             'id = "goal"', 2),
            ('kinds = ["project"]', 'kinds = ["missing"]',
             "pipeline strategy stage project names unknown kind 'missing'", 'kinds = ["missing"]', 1),
            ('kinds = ["project"]', "kinds = []", "stages.kinds must be nonempty", "kinds = []", 1),
            ('kinds = ["project"]', 'kinds = ["project", "project"]',
             "stages.kinds contains duplicate 'project'", 'kinds = ["project", "project"]', 1),
        )
        for old, new, message, needle, occurrence in cases:
            with self.subTest(message=message):
                self.plant(STRATEGY.replace(old, new, 1), message, needle, occurrence)

    def test_multiline_and_escaped_source_map(self):
        text = STRATEGY.replace('kinds = ["project"]',
                                'kinds = [\n  "project",\n  "pro\\u006aect",\n]')
        self.plant(text, "stages.kinds contains duplicate 'project'", '"pro\\u006aect",')
        text = STRATEGY.replace('per_target = "one-or-more"', 'per_target = "t\\u0077o"')
        self.plant(text, "unknown cardinality 'two'", 'per_target = "t\\u0077o"')
        text = STRATEGY.replace('to = "project"', 'to = "missing"')
        self.plant(text, "pipeline strategy link names unknown stage 'missing'", 'to = "missing"')

    def test_status_list_specific_refusal(self):
        old = next(line for line in STRATEGY.splitlines() if line.startswith("statuses ="))
        for value in ('[]', '["active", "active"]', '[1]', '[""]', '[" "]', '"active"'):
            with self.subTest(value=value):
                new = f"statuses = {value}"
                self.plant(STRATEGY.replace(old, new),
                           "pipeline strategy stage project statuses must be nonempty unique strings", new)
        text = STRATEGY.replace(old, 'statuses = [\n "queued",\n 1,\n]')
        self.plant(text, "pipeline strategy stage project statuses must be nonempty unique strings", "1,")

    def test_link_relation_stage_direction(self):
        cases = (
            ('relation = "serves"', 'relation = "missing"',
             "pipeline strategy names unknown relation 'missing'", 'relation = "missing"'),
            ('from = "project"', 'from = "missing"',
             "pipeline strategy link names unknown stage 'missing'", 'from = "missing"'),
            ('to = "goal"', 'to = "missing"',
             "pipeline strategy link names unknown stage 'missing'", 'to = "missing"'),
            ('from = "project"\nto = "goal"', 'from = "goal"\nto = "project"',
             "pipeline strategy link serves endpoints do not match stages goal -> project", 'from = "goal"'),
        )
        for old, new, message, needle in cases:
            with self.subTest(message=message):
                self.plant(STRATEGY.replace(old, new, 1), message, needle)
        # Only target kinds are wrong; the target field owns the refusal.
        text = STRATEGY.replace('kinds = ["goal"]', 'kinds = ["issue"]')
        self.plant(text, "pipeline strategy link serves endpoints do not match stages project -> goal",
                   'to = "goal"')

    def test_topology_missing_repeated_nonadjacent_self(self):
        missing = STRATEGY.rsplit("[[links]]", 1)[0]
        self.plant(missing, "pipeline strategy requires exactly one link between adjacent stages project and campaign",
                   "[[links]]")
        repeat = STRATEGY + '\n[[links]]\nrelation = "serves"\nfrom = "project"\nto = "goal"\n'
        self.plant(repeat, "pipeline strategy requires exactly one link between adjacent stages goal and project",
                   'from = "project"', 2)
        nonadjacent = STRATEGY.replace('to = "project"', 'to = "goal"')
        self.plant(nonadjacent, "pipeline strategy requires exactly one link between adjacent stages goal and campaign",
                   'from = "campaign"')
        selflink = STRATEGY.replace('to = "goal"', 'to = "project"', 1)
        self.plant(selflink, "pipeline strategy requires exactly one link between adjacent stages project and project",
                   'from = "project"')

    def test_optional_total_one_at_both_ends(self):
        text = STRATEGY.replace('per_target = "one-or-more"', 'per_target = "exactly-one"')
        self.plant(text, "pipeline strategy: optional stage campaign conflicts with exactly-one per_target on includes",
                   'per_target = "exactly-one"')
        # The goal is the authored target of serves; projects count goals.
        text = STRATEGY.replace('kinds = ["goal"]', 'kinds = ["goal"]\noptional = true')
        text = text.replace('per_source = "one-or-more"', 'per_source = "exactly-one"', 1)
        self.plant(text, "pipeline strategy: optional stage goal conflicts with exactly-one per_source on serves",
                   'per_source = "exactly-one"')

    def test_optional_role_one_at_both_ends(self):
        text = STRATEGY + '\n[links.by_role.included]\nper_target = "exactly-one"\n'
        self.plant(text,
                   "pipeline strategy: optional stage campaign conflicts with exactly-one per_target for role included on includes",
                   'per_target = "exactly-one"')
        text = STRATEGY.replace('kinds = ["goal"]', 'kinds = ["goal"]\noptional = true')
        self.plant(text,
                   "pipeline strategy: optional stage goal conflicts with exactly-one per_source for role primary on serves",
                   'per_source = "exactly-one"')

    def test_optional_global_minimum_total_and_role(self):
        for changes in ({"per_target": "one-or-more"},
                        {"by_role": {"included": {"per_target": "one-or-more"}}}):
            with self.subTest(changes=changes):
                self.plant(STRATEGY,
                           "pipeline strategy: optional stage campaign conflicts with global minimum on includes",
                           "optional = true", schema=self.with_rule("includes", **changes))
        # An optional target conflicts with a global per-source minimum too.
        text = STRATEGY.replace('kinds = ["goal"]', 'kinds = ["goal"]\noptional = true')
        text = text.replace('per_source = "exactly-one"', 'per_source = "one-or-more"')
        self.plant(text, "pipeline strategy: optional stage goal conflicts with global minimum on serves",
                   "optional = true", schema=self.with_rule("serves", per_source="one-or-more"))

    def test_incompatible_intersected_role_and_total_bounds(self):
        # Both individually valid rule sets intersect to two required roles
        # with a total maximum of one; checking only total-vs-total misses it.
        text = STRATEGY.replace('[links.by_role.supporting]\nper_source = "any"',
                                '[links.by_role.supporting]\nper_source = "exactly-one"')
        self.plant(text, "pipeline strategy has incompatible bounds for serves at source",
                   'per_source = "one-or-more"', schema=self.with_rule("serves", per_source="at-most-one"))
        text = STRATEGY.replace('per_source = "one-or-more"', 'per_source = "at-most-one"', 1)
        schema = self.with_rule("serves", by_role={
            "primary": {"per_source": "exactly-one"},
            "supporting": {"per_source": "exactly-one"},
        })
        self.plant(text, "pipeline strategy has incompatible bounds for serves at source",
                   'per_source = "at-most-one"', schema=schema)
        text = STRATEGY.replace('per_target = "any"', 'per_target = "at-most-one"', 1)
        text = text.replace('[links.by_role.primary]\nper_source = "exactly-one"\nper_target = "any"',
                            '[links.by_role.primary]\nper_source = "exactly-one"\nper_target = "one-or-more"')
        text = text.replace('[links.by_role.supporting]\nper_source = "any"\nper_target = "any"',
                            '[links.by_role.supporting]\nper_source = "any"\nper_target = "one-or-more"')
        self.plant(text, "pipeline strategy has incompatible bounds for serves at target",
                   'per_target = "at-most-one"')

    def test_optional_role_lower_relaxes_before_intersection(self):
        text = STRATEGY + '\n[links.by_role.included]\nper_target = "one-or-more"\n'
        path = self.write(STRATEGY_PATH, text)
        schema = self.with_rule("includes", per_target="at-most-one")
        pipeline = load_pipeline(path, schema)
        self.assertEqual(pipeline.links[1].by_role["included"]["per_target"], "one-or-more")
        self.assertEqual(effective_bounds(pipeline.links[1].per_target, optional=True), (0, None))

    def test_unknown_cardinality_and_role(self):
        text = STRATEGY.replace('per_target = "one-or-more"', 'per_target = "two"')
        self.plant(text, "unknown cardinality 'two'", 'per_target = "two"')
        text = STRATEGY.replace('[links.by_role.primary]\nper_source = "exactly-one"',
                                '[links.by_role.primary]\nper_source = "two"')
        self.plant(text, "unknown cardinality 'two'", 'per_source = "two"')
        text = STRATEGY.replace("[links.by_role.primary]", "[links.by_role.secondary]")
        self.plant(text, "pipeline strategy link serves has cardinality for unknown role 'secondary'",
                   "[links.by_role.secondary]")

    def test_version_and_invalid_names(self):
        cases = (
            ("version = 1", "version = true", "version must be an integer"),
            ("version = 1", "version = 2", "unsupported declaration version 2; expected 1"),
            ('id = "strategy"', 'id = "Not A Name"',
             "invalid pipeline id 'Not A Name'; expected lowercase kebab-case"),
            ('id = "goal"', 'id = "Bad Stage"',
             "invalid stage id 'Bad Stage'; expected lowercase kebab-case"),
        )
        for old, new, message in cases:
            with self.subTest(message=message):
                self.plant(STRATEGY.replace(old, new, 1), message, new)

    def test_closed_root_stage_link_role_keys_and_types(self):
        # Inline arrays permit every field to be removed/retyped without
        # invalid TOML or unintentionally changing table ownership.
        first = '{id="goal", kinds=["goal"]}'
        second = '{id="project", kinds=["project"]}'
        link = '{relation="serves", from="project", to="goal"}'
        base = f'version = 1\nid = "strategy"\nstages = [{first}, {second}]\nlinks = [{link}]\n'
        schema = self.schema()
        for name, row, expected_line in (("version", "version = 1\n", 1),
                                         ("id", 'id = "strategy"\n', 1),
                                         ("stages", f"stages = [{first}, {second}]\n", 1),
                                         ("links", f"links = [{link}]\n", 1)):
            with self.subTest(missing=name):
                self.plant(base.replace(row, ""), f"missing required key '{name}' in pipeline",
                           line=expected_line, schema=schema)
        cases = (
            (base + "typo = 1\n", "unknown key 'typo' in pipeline", 5),
            (base.replace(first, '{id="goal", kinds=["goal"], typo=1}'), "unknown key 'typo' in stages", 3),
            (base.replace(first, '{kinds=["goal"]}'), "missing required key 'id' in stages", 3),
            (base.replace(first, '{id="goal"}'), "missing required key 'kinds' in stages", 3),
            (base.replace(first, '{id=1, kinds=["goal"]}'), "stages.id must be a string", 3),
            (base.replace(first, '{id="", kinds=["goal"]}'), "stages.id must be a nonempty string", 3),
            (base.replace(first, '{id="goal", kinds=1}'), "stages.kinds must be an array of strings", 3),
            (base.replace(first, '{id="goal", kinds=[1]}'), "stages.kinds must be an array of strings", 3),
            (base.replace(first, '{id="goal", kinds=[""]}'), "stages.kinds must be a nonempty string", 3),
            (base.replace(first, '{id="goal", kinds=["goal"], optional=1}'), "stages.optional must be a boolean", 3),
            (base.replace(first, "1"), "stages must be an array of tables", 3),
            (base.replace(f"[{first}, {second}]", '"bad"'), "stages must be an array of tables", 3),
            (base.replace('[{relation="serves", from="project", to="goal"}]', '"bad"'),
             "links must be an array of tables", 4),
            (base.replace(link, "1"), "links must be an array of tables", 4),
            (base.replace(link, '{relation="serves", from="project", to="goal", typo=1}'),
             "unknown key 'typo' in links", 4),
            (base.replace(link, '{from="project", to="goal"}'), "missing required key 'relation' in links", 4),
            (base.replace(link, '{relation="serves", to="goal"}'), "missing required key 'from' in links", 4),
            (base.replace(link, '{relation="serves", from="project"}'), "missing required key 'to' in links", 4),
            (base.replace('relation="serves"', "relation=1"), "links.relation must be a string", 4),
            (base.replace('from="project"', "from=1"), "links.from must be a string", 4),
            (base.replace('to="goal"', "to=1"), "links.to must be a string", 4),
            (base.replace(link, '{relation="serves", from="project", to="goal", per_source=1}'),
             "links.per_source must be a string", 4),
            (base.replace(link, '{relation="serves", from="project", to="goal", per_target=1}'),
             "links.per_target must be a string", 4),
            (base.replace(link, '{relation="serves", from="project", to="goal", by_role=1}'),
             "links.by_role must be a table", 4),
            (base.replace(link, '{relation="serves", from="project", to="goal", by_role={primary=1}}'),
             "links.by_role.primary must be a table", 4),
            (base.replace(link, '{relation="serves", from="project", to="goal", by_role={primary={extra=1}}}'),
             "unknown key 'extra' in links.by_role.primary", 4),
            (base.replace(link, '{relation="serves", from="project", to="goal", by_role={primary={per_source=1}}}'),
             "links.by_role.primary.per_source must be a string", 4),
            (base.replace(link, '{relation="serves", from="project", to="goal", by_role={primary={per_target=1}}}'),
             "links.by_role.primary.per_target must be a string", 4),
            (base.replace('id = "strategy"', "id = 1"), "id must be a string", 2),
        )
        for text, message, line in cases:
            with self.subTest(message=message):
                self.plant(text, message, line=line, schema=schema)

    def test_missing_nested_key_points_at_second_table_header(self):
        text = STRATEGY.replace('from = "campaign"\n', "")
        self.plant(text, "missing required key 'from' in links", "[[links]]", 2)

    def test_parser_error_line(self):
        text = 'version = 1\nid = "strategy"\nstages = "unclosed\nlinks = []\n'
        try:
            tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            message = f"invalid TOML: {error}"
        else:
            self.fail("negative TOML fixture unexpectedly parsed")
        self.plant(text, message, line=3)

    def test_links_sorted_in_display_order_keep_occurrence(self):
        prefix, first, second = STRATEGY.split("[[links]]")
        text = prefix + "[[links]]" + second + "[[links]]" + first
        path = self.write(STRATEGY_PATH, text)
        pipeline = load_pipeline(path, self.schema(), display_path=STRATEGY_PATH)
        self.assertEqual([link.relation for link in pipeline.links], ["serves", "includes"])
        self.assertEqual([link.key for link in pipeline.links], [("links", 1), ("links", 0)])
        self.assertEqual(pipeline.links[0].source.line, line_of(text, "[[links]]", 2))


class InventoryTests(FixtureWorkspace):
    def test_empty_inventory_shallow_and_no_record_loader(self):
        workspace = self.workspace()
        self.assertEqual(list_pipelines(workspace), "intake\nstrategy\n")
        self.write("pipelines/nested/bad.toml", "this is not TOML")
        self.write("pipelines/readme.md", "not a pipeline")
        with patch("otto.pipelines.load_records", side_effect=AssertionError("record read")):
            self.assertEqual(list_pipelines(workspace), "intake\nstrategy\n")
            (self.root / STRATEGY_PATH).unlink()
            self.assertEqual(list_pipelines(workspace), "intake\n")
            shutil.rmtree(self.root / "pipelines")
            self.assertEqual(list_pipelines(workspace), "")

    def test_child_not_file(self):
        workspace = self.workspace()
        (self.root / "pipelines/invalid.toml").mkdir()
        self.refuse(lambda: load_pipelines(workspace), "pipelines/invalid.toml", 1,
                    "pipeline declaration must name a file")

    def symlink(self, path, target, *, directory=False):
        try:
            path.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")

    def test_contained_child_alias(self):
        workspace = self.workspace()
        target = self.write("elsewhere/strategy.toml", STRATEGY)
        authored = self.root / STRATEGY_PATH
        authored.unlink()
        self.symlink(authored, target)
        loaded = load_pipelines(workspace)
        self.assertEqual(loaded["strategy"].source.path, STRATEGY_PATH)
        self.assertEqual(list_pipelines(workspace), "intake\nstrategy\n")

    def test_escaped_child(self):
        workspace = self.workspace()
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "bad.toml"
            target.write_text(STRATEGY, encoding="utf-8")
            self.symlink(self.root / "pipelines/bad.toml", target)
            self.refuse(lambda: load_pipelines(workspace), "pipelines/bad.toml", 1,
                        "pipeline declaration must resolve inside the workspace root")

    def test_dangling_child(self):
        workspace = self.workspace()
        target = self.root / "missing.toml"
        child = self.root / "pipelines/bad.toml"
        self.symlink(child, target)
        try:
            child.stat()
        except OSError as error:
            reason = error.strerror
        else:
            self.fail("dangling fixture unexpectedly exists")
        self.refuse(lambda: load_pipelines(workspace), "pipelines/bad.toml", 1,
                    f"cannot read pipelines/bad.toml: {reason}")

    def test_inventory_read_failure(self):
        workspace = self.workspace()
        with patch.object(Path, "iterdir", side_effect=PermissionError(13, "denied")):
            self.refuse(lambda: load_pipelines(workspace), "pipelines", 1,
                        "cannot read pipelines: denied")

    def test_root_type_changed_since_workspace_load(self):
        workspace = self.workspace()
        shutil.rmtree(self.root / "pipelines")
        self.write("pipelines", "not a directory")
        self.refuse(lambda: load_pipelines(workspace), "otto.toml",
                    line_of((self.root / "otto.toml").read_text(encoding="utf-8"),
                            'pipelines = "pipelines"'), "paths.pipelines must name a directory")

    def test_escaped_root_changed_since_workspace_load(self):
        workspace = self.workspace()
        shutil.rmtree(self.root / "pipelines")
        with tempfile.TemporaryDirectory() as outside:
            self.symlink(self.root / "pipelines", Path(outside), directory=True)
            self.refuse(lambda: load_pipelines(workspace), "otto.toml",
                        line_of((self.root / "otto.toml").read_text(encoding="utf-8"),
                                'pipelines = "pipelines"'),
                        "paths.pipelines must resolve inside the workspace root")


class MarketingQueries(FixtureWorkspace):
    def setUp(self):
        super().setUp()
        self.write("strategy.md", "# Example strategy\n\n## Goals\n\n| ID | Goal |\n"
                   "| --- | --- |\n| clear-example | Clear example |\n")
        self.write(self.adapter,
                   "from otto.ids import RecordRef, SourceLocation\n"
                   "from otto.records import Record, RecordBatch\n"
                   "def load_strategy_goals(workspace):\n"
                   "    return RecordBatch((Record(RecordRef('goal', 'clear-example'), "
                   "SourceLocation('strategy.md', 7), 'Clear example'),))\n"
                   "def register_checks(workspace): return ()\n"
                   "def register_views(workspace): return ((), [])\n")
        for id in ("launch-note", "try-message", "standalone-note"):
            self.write(f"projects/{id}/plan.md",
                       "# Example project\n\n**Status:** queued\n\n## Relationships\n\n"
                       "| Relation | Target | Role |\n| --- | --- | --- |\n"
                       "| serves | goal:clear-example | primary |\n")
            self.write(f"projects/{id}/tasks.md", "# Tasks\n\n- [ ] Example\n")
        self.write("campaigns/sample-week.md",
                   "# Example campaign\n\n## Relationships\n\n"
                   "| Relation | Target | Role |\n| --- | --- | --- |\n"
                   "| includes | project:launch-note | included |\n"
                   "| includes | project:try-message | included |\n")
        self.write("issues/clarify-heading.md",
                   "# Example issue\n\n## Relationships\n\n"
                   "| Relation | Target | Role |\n| --- | --- | --- |\n"
                   "| routes-to | project:launch-note | primary |\n")
        self.write("ideas/short-example.md", "---\nstatus: queued\n---\n# Example idea\n")
        self.ws = self.workspace()
        self.schema_obj = RelationshipSchema.from_workspace(self.ws)
        self.batch = load_records(self.ws)
        self.index = RelationshipIndex.from_batch(self.batch, schema=self.schema_obj)

    def show(self, pipeline, record=None, *, index=None):
        return show_pipeline(self.ws, pipeline, record, schema=self.schema_obj,
                             index=self.index if index is None else index)

    def test_exact_bytes_sorted_reverse_and_optional(self):
        expected = (STRATEGY_ROW + STANDALONE_ROW +
                    "goal=goal:clear-example -> project=project:try-message (serves, primary)"
                    " -> campaign=campaign:sample-week (includes, included)\n")
        self.assertEqual(list_pipelines(self.ws).encode(), b"intake\nstrategy\n")
        self.assertEqual(self.show("strategy", "project:launch-note").encode(), STRATEGY_ROW.encode())
        self.assertEqual(self.show("strategy", "standalone-note").encode(), STANDALONE_ROW.encode())
        self.assertEqual(self.show("strategy", "goal:clear-example").encode(), expected.encode())
        self.assertEqual(self.show("strategy").encode(), expected.encode())
        self.assertEqual(self.show("strategy", "goal:clear-example"), self.show("strategy", "goal:clear-example"))
        reversed_index = RelationshipIndex(reversed(self.batch.records), reversed(self.index.relationships),
                                           schema=self.schema_obj)
        self.assertEqual(self.show("strategy", "goal:clear-example", index=reversed_index), expected)
        self.assertEqual(self.show("intake", "launch-note"), INTAKE_ROW)
        self.assertEqual(self.show("intake", "idea:short-example"), "")
        self.assertEqual(self.show("intake", "project:standalone-note"), "")

    def test_default_load_and_prebuilt_index_same_output(self):
        self.assertEqual(show_pipeline(self.ws, "strategy", "launch-note"), STRATEGY_ROW)
        with patch("otto.pipelines.load_records", side_effect=AssertionError("record read")):
            self.assertEqual(self.show("strategy", "launch-note"), STRATEGY_ROW)

    def test_shared_project_identity_and_read_only_snapshot(self):
        pipeline = load_pipelines(self.ws)
        project = RecordRef("project", "launch-note")
        resolver = self.batch.resolver()
        source = resolver.source_for(project)
        task_path = (self.root / source.path).parent / "tasks.md"
        snapshot = {p.relative_to(self.root): p.read_bytes()
                    for p in self.root.rglob("*") if p.is_file()}
        before = (self.index.records, self.index.relationships)
        strategy = traverse(pipeline["strategy"], self.index, project)
        intake = traverse(pipeline["intake"], self.index, project)
        self.assertEqual(strategy[0].refs[1], intake[0].refs[1])
        self.assertEqual(strategy[0].refs[1], project)
        self.assertEqual(resolver.source_for(strategy[0].refs[1]), source)
        self.assertEqual(resolver.source_for(intake[0].refs[1]), source)
        self.assertEqual(sum(r.ref == project for r in self.batch.records), 1)
        self.assertEqual(source.path, "projects/launch-note/plan.md")
        self.assertEqual(task_path.read_text(encoding="utf-8"), "# Tasks\n\n- [ ] Example\n")
        self.assertEqual(self.show("strategy", "launch-note"), STRATEGY_ROW)
        self.assertEqual(self.show("intake", "launch-note"), INTAKE_ROW)
        self.assertEqual((self.index.records, self.index.relationships), before)
        self.assertEqual({p.relative_to(self.root): p.read_bytes()
                          for p in self.root.rglob("*") if p.is_file()}, snapshot)

    def test_query_unknown_and_ambiguous(self):
        self.assertEqual(self.show("strategy", "project:missing"), "Unknown record project:missing\n")
        self.assertEqual(self.show("strategy", "idea:short-example"), "Unknown record idea:short-example\n")
        refs = self.index.records | {RecordRef("goal", "shared"), RecordRef("project", "shared")}
        graph = RelationshipIndex(refs, self.index.relationships, schema=self.schema_obj)
        with self.assertRaises(ValueError) as error:
            self.show("strategy", "shared", index=graph)
        self.assertEqual(str(error.exception),
                         "ambiguous record id 'shared': goal:shared, project:shared")
        self.assertEqual(self.show("strategy", "goal:shared", index=graph), "")
        with self.assertRaises(ValueError) as error:
            self.show("missing", "launch-note")
        self.assertEqual(str(error.exception), "unknown pipeline 'missing'")

    def test_stage_status_is_not_a_traversal_filter(self):
        records = tuple(replace(r, status="published") if r.ref == RecordRef("project", "launch-note")
                        else r for r in self.batch.records)
        graph = RelationshipIndex(records, self.index.relationships, schema=self.schema_obj)
        self.assertEqual(self.show("strategy", "launch-note", index=graph), STRATEGY_ROW)

    def test_deleting_one_pipeline_keeps_records_and_other_query(self):
        (self.root / "pipelines/intake.toml").unlink()
        self.assertEqual(list_pipelines(self.ws), "strategy\n")
        self.assertEqual(self.show("strategy", "launch-note"), STRATEGY_ROW)
        self.assertEqual(self.batch, load_records(self.ws))

    def test_invalid_graph_stops_show_before_traversal(self):
        path = self.root / "projects/launch-note/plan.md"
        path.write_text(path.read_text(encoding="utf-8").replace("goal:clear-example", "goal:missing"),
                        encoding="utf-8")
        with patch("otto.pipelines.traverse", side_effect=AssertionError("invalid graph traversed")):
            with self.assertRaises(LocatedError):
                show_pipeline(self.ws, "strategy", "launch-note")


class DevQueries(FixtureWorkspace):
    specimen = "dev"

    def test_dev_delivery_issue_reverse_and_qualified_identity(self):
        ws = self.workspace()
        schema = RelationshipSchema.from_workspace(ws)
        goal = RecordRef("goal", "pillar:example/clear")
        gap = RecordRef("gap", "XX-001")
        project = RecordRef("project", "01")
        release = RecordRef("release", "1")
        issue = RecordRef("issue", "1")
        records = (goal, gap, project, release, issue)
        edges = (
            Relationship(gap, "measures", goal, "primary", "vision/gaps/XX-001.md", 2, schema=schema),
            Relationship(project, "addresses", gap, "primary", "plans/01-example/plan.md", 2, schema=schema),
            Relationship(release, "includes", project, "included", "releases/1.md", 2, schema=schema),
            Relationship(issue, "listed-in", release, "frozen", "releases/1.md", 3, schema=schema),
        )
        index = RelationshipIndex(records, edges, schema=schema)
        expected = ("goal=goal:pillar:example/clear -> gap=gap:XX-001 (measures, primary)"
                    " -> project=project:01 (addresses, primary) -> release=release:1 (includes, included)\n")
        self.assertEqual(list_pipelines(ws).encode(), b"delivery\nissue\n")
        for query in ("goal:pillar:example/clear", "pillar:example/clear", "project:01", "release:1"):
            with self.subTest(query=query):
                self.assertEqual(show_pipeline(ws, "delivery", query, schema=schema, index=index), expected)
        self.assertEqual(show_pipeline(ws, "issue", "issue:1", schema=schema, index=index),
                         "issue=issue:1 -> release=release:1 (listed-in, frozen)\n")
        self.assertEqual(show_pipeline(ws, "delivery", "goal:missing", schema=schema, index=index),
                         "Unknown record goal:missing\n")
        incomplete = RelationshipIndex(records, edges[:2], schema=schema)
        self.assertEqual(show_pipeline(ws, "delivery", str(goal), schema=schema, index=incomplete), "")


class CyclicAndOptionalTraversalTests(FixtureWorkspace):
    def graph(self, refs, pairs):
        schema = RelationshipSchema(frozenset({"node"}), {
            "connects": RelationKind("connects", frozenset({"node"}), frozenset({"node"}),
                                     frozenset({"edge"})),
        })
        edges = [Relationship(a, "connects", b, "edge", "example.md", i, schema=schema)
                 for i, (a, b) in enumerate(pairs, 1)]
        return schema, RelationshipIndex(refs, edges, schema=schema)

    def chain(self, schema, optional):
        rows = ['version = 1', 'id = "chain"']
        for i, value in enumerate(optional):
            rows.extend(("[[stages]]", f'id = "s{i}"', 'kinds = ["node"]',
                         f"optional = {str(value).lower()}"))
        for i in range(len(optional) - 1):
            rows.extend(("[[links]]", 'relation = "connects"',
                         f'from = "s{i}"', f'to = "s{i+1}"'))
        path = self.write("pipelines/chain.toml", "\n".join(rows) + "\n")
        return load_pipeline(path, schema)

    def test_cycle_repeated_kind_convergence_and_deduplication(self):
        a, b, c, d = (RecordRef("node", id) for id in "abcd")
        schema, graph = self.graph((a, b, c, d), ((a, b), (a, c), (b, d), (c, d), (d, a)))
        pipeline = self.chain(schema, (False, False, False, False))
        paths = traverse(pipeline, graph, a)
        # The same record at different slots is valid; every distinct complete
        # path containing a is emitted once despite multiple seed positions.
        expected = ((a, b, d, a), (a, c, d, a), (b, d, a, b), (b, d, a, c),
                    (c, d, a, b), (c, d, a, c), (d, a, b, d), (d, a, c, d))
        self.assertEqual(tuple(p.refs for p in paths), expected)
        self.assertEqual(traverse(pipeline, graph, a), paths)
        self.assertEqual(traverse(pipeline, graph), paths)
        self.assertEqual(len(graph.records), 4)
        self.assertEqual(len(graph.relationships), 5)
        self.assertTrue(all(len(p.edges) == 3 for p in paths))

    def test_consecutive_optional_suffix_and_prefix(self):
        a, b = (RecordRef("node", id) for id in "ab")
        schema, graph = self.graph((a, b), ((a, b),))
        pipeline = self.chain(schema, (True, True, False, True, True))
        actual = tuple(p.refs for p in traverse(pipeline, graph))
        self.assertEqual(actual, ((None, None, a, b, None), (None, a, b, None, None)))
        for path in traverse(pipeline, graph):
            self.assertEqual(sum(e is not None for e in path.edges), 1)

    def test_no_optional_bypass_and_no_absent_alternative_to_real_neighbor(self):
        a, b = (RecordRef("node", id) for id in "ab")
        schema, graph = self.graph((a, b), ((a, b),))
        pipeline = self.chain(schema, (False, True, False))
        self.assertEqual(traverse(pipeline, graph), ())
        pipeline = self.chain(schema, (False, True))
        self.assertEqual(tuple(p.refs for p in traverse(pipeline, graph, a)), ((a, b),))
        self.assertEqual(tuple(p.refs for p in traverse(pipeline, graph, b)), ((a, b), (b, None)))

    def test_all_optional_does_not_create_all_empty_path(self):
        a = RecordRef("node", "a")
        schema, graph = self.graph((a,), ())
        pipeline = self.chain(schema, (True, True))
        self.assertEqual(tuple(p.refs for p in traverse(pipeline, graph)), ((None, a), (a, None)))
        empty = RelationshipIndex((), (), schema=schema)
        self.assertEqual(traverse(pipeline, empty), ())


if __name__ == "__main__":
    unittest.main()
