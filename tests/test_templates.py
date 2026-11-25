"""OT-11 template contract fixtures; all workspaces and package assets are temporary."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import tomllib
import unittest

from otto.config import load_workspace
from otto.ids import LocatedError, RecordRef, SourceLocation
from otto.records import load_records
from otto.templates import BasePack, check_pack_shape, discover_templates, select_template


CONFIG = '''version = 1
[workspace]
name = "example"
skill_namespace = "example-"
[paths]
items = "items"
[ids.project]
policy = "slug"
source = "parent"
[[record_kinds]]
name = "project"
root = "items"
files = ["*/plan.md"]
reader = "headers"
pack = true
'''
STANDARD = '''version = 1
name = "standard"
workstream = "guidance/workstreams/plan.md#procedure"
documents = []
'''
LOOP = '''version = 1
name = "loop"
workstream = "guidance/workstreams/iterate.md#procedure"

[[documents]]
path = "rounds.md"
source = "rounds.md"
headings = ["Baseline", "Method", "Stop rule", "Rounds"]
task_reference_field = "Standing task"
'''
PLAN = "# Project\n## Scope\n## Completion\n"
INPUTS = "# Inputs\n## Context\n## Decisions\n"
TASKS = "# Tasks\n\n| Task | State |\n| --- | --- |\n| **LOOP-1** standing | Open |\n"
ROUNDS = "# Rounds\n**Standing task:** LOOP-1\n## Baseline\nPending\n## Method\n## Stop rule\n## Rounds\n"
WORKSTREAM = "# Workstream\n## Procedure\nRead-only guidance.\n"
FENCE = chr(96) * 3
REF = RecordRef("project", "alpha")
PLAN_PATH = "items/alpha/plan.md"
ROUND_PATH = "items/alpha/rounds.md"
LOOP_MANIFEST = "templates/loop/template.toml"
STANDARD_MANIFEST = "templates/standard/template.toml"


class TemplateFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "workspace"
        self.package = self.root.parent / "package"
        self.root.mkdir()
        self.package.mkdir()
        (self.root / "items").mkdir()
        self.write("otto.toml", CONFIG)
        for name, text in (("plan.md", PLAN), ("inputs.md", INPUTS), ("tasks.md", TASKS)):
            self.write("templates/project/" + name, text, package=True)
        self.write(STANDARD_MANIFEST, STANDARD, package=True)
        self.write(LOOP_MANIFEST, LOOP, package=True)
        self.write("templates/loop/rounds.md", ROUNDS, package=True)
        self.write("guidance/workstreams/plan.md", WORKSTREAM, package=True)
        self.write("guidance/workstreams/iterate.md", WORKSTREAM, package=True)

    def write(self, path, text, *, package=False):
        target = (self.package if package else self.root) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def pack(self, folder="alpha", template=None, *, rounds=False):
        prefix = f"items/{folder}/"
        plan = PLAN if template is None else PLAN.replace("# Project\n", f"# Project\n**Template:** {template}\n")
        self.write(prefix + "plan.md", plan)
        self.write(prefix + "inputs.md", INPUTS)
        self.write(prefix + "tasks.md", TASKS)
        if rounds:
            self.write(prefix + "rounds.md", ROUNDS)

    def check(self, *, base=None, base_packs=None):
        workspace = load_workspace(self.root)
        return check_pack_shape(workspace, load_records(workspace), base=base,
                                package_root=self.package, base_packs=base_packs)

    def manifest_refuse(self, path, text, line, message):
        self.write(path, text, package=True)
        self.assertEqual(self.check(), [f"{path}:{line}: {message}"])

    def symlink(self, path, target, *, directory=False):
        try:
            path.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink not available: {exc}")


class SelectionTests(TemplateFixture):
    def test_standard_new_pack_no_loop_files(self):
        self.pack()
        self.assertEqual(self.check(base_packs={}), [])
        workspace = load_workspace(self.root)
        inventory = discover_templates(workspace, package_root=self.package)
        selection = select_template(PLAN, SourceLocation(PLAN_PATH, 1), inventory)
        self.assertEqual((selection.name, selection.explicit, selection.location),
                         ("standard", False, SourceLocation(PLAN_PATH, 1)))
        self.assertEqual(inventory["standard"].documents, ())
        self.assertEqual(inventory["loop"].documents[0].headings, ("Baseline", "Method", "Stop rule", "Rounds"))
        with self.assertRaises(TypeError):
            inventory["other"] = inventory["loop"]
        self.assertFalse((self.root / ROUND_PATH).exists())

    def test_explicit_loop_is_checked_without_base(self):
        self.pack(template="loop")
        self.assertEqual(self.check(), [
            f"{PLAN_PATH}:1: template loop: missing required document rounds.md"])
        self.write(ROUND_PATH, ROUNDS)
        self.assertEqual(self.check(), [])  # Pending baseline is deliberately valid.

    def test_selector_refusals_at_authored_lines(self):
        self.pack()
        for text, line, message in (
            ("# Project\n**Template:** missing\n## Scope\n## Completion\n", 2,
             "unknown project template 'missing'"),
            ("# Project\n**Template:**  \n## Scope\n## Completion\n", 2, "empty Template field"),
            ("# Project\n**Template:** loop\n**Template:** standard\n## Scope\n## Completion\n", 3,
             "duplicate Template field"),
            ("# Project\n## Scope\n**Template:** loop\n## Completion\n", 3,
             "Template must be in the project header"),
            (f"# Project\n{FENCE}md\n**Template:** loop\n{FENCE}\n## Scope\n## Completion\n", 3,
             "Template declaration is inside a fenced block"),
            ("# Project\n~~~\n**Template:** loop\n~~~\n## Scope\n## Completion\n", 3,
             "Template declaration is inside a fenced block"),
            ('# Project\n**Template:** "loop"\n## Scope\n## Completion\n', 2,
             'unknown project template \'"loop"\''),
            ("# Project\n**Template:** 'loop'\n## Scope\n## Completion\n", 2,
             "unknown project template ''loop''"),
            ("# Project\n**Template:** loop now\n## Scope\n## Completion\n", 2,
             "unknown project template 'loop now'"),
        ):
            with self.subTest(message=message):
                self.write(PLAN_PATH, text)
                self.assertEqual(self.check(), [f"{PLAN_PATH}:{line}: {message}"])

    def test_live_header_beats_examples_and_body_fences_do_not_select(self):
        self.pack(template="loop", rounds=True)
        self.write(PLAN_PATH, (
            f"# Project\n**Template:** loop\n{FENCE}md\n**Template:** missing\n"
            f"## Pretend\n{FENCE}\n## Scope\n**Template:** missing\n## Completion\n"))
        self.assertEqual(self.check(), [])
        self.write(PLAN_PATH, (
            f"# Project\n## Scope\n{FENCE}\n**Template:** missing\n{FENCE}\n## Completion\n"))
        self.assertEqual(self.check(base_packs={}), [])

    def test_existing_standard_not_retroactively_checked(self):
        self.pack()
        self.write(PLAN_PATH, "# Old project\n## Obsolete\n")
        history = {REF: BasePack(PLAN_PATH, PLAN)}
        self.assertEqual(self.check(base_packs=history), [])
        self.assertEqual(self.check(), [])
        self.assertEqual(self.check(base_packs={}), [
            f"{PLAN_PATH}:1: common pack: plan.md is missing heading '## Scope'"])

    def test_base_inventory_downgrade_and_deliberate_switch(self):
        self.pack(rounds=True)
        prior = PLAN.replace("# Project\n", "# Project\n**Template:** loop\n")
        history = {REF: BasePack("items/previous/plan.md", prior)}
        self.assertEqual(self.check(), [])  # snapshot cannot prove removal
        self.assertEqual(self.check(base_packs=history), [
            f"{PLAN_PATH}:1: explicit Template field removed from project:alpha; "
            "write **Template:** standard to select standard deliberately"])
        self.pack(template="standard")
        self.assertEqual(self.check(base_packs=history), [])
        self.assertEqual((self.root / ROUND_PATH).read_text(), ROUNDS)
        self.write(PLAN_PATH, "# Project\n**Template:** standard\n## Scope\n")
        self.assertEqual(self.check(base_packs=history), [
            f"{PLAN_PATH}:1: common pack: plan.md is missing heading '## Completion'"])

    def test_old_explicit_standard_may_remove_selector(self):
        self.pack()
        prior = PLAN.replace("# Project\n", "# Project\n**Template:** standard\n")
        self.write(PLAN_PATH, "# Old project\n")
        self.assertEqual(self.check(base_packs={REF: BasePack(PLAN_PATH, prior)}), [])

    def test_missing_default_is_not_silent_fallback_and_empty_inventory_passes(self):
        shutil.rmtree(self.package / "templates")
        self.assertEqual(self.check(base_packs={}), [])
        self.pack()
        self.assertEqual(self.check(), [])
        self.assertEqual(self.check(base_packs={}), [
            f"{PLAN_PATH}:1: unknown project template 'standard'"])


class ManifestTests(TemplateFixture):
    def test_closed_top_level_schema_types_and_version(self):
        for text, line, message in (
            (STANDARD + 'extends = "loop"\n', 5, "unknown key 'extends' in template"),
            (STANDARD.replace('version = 1\n', ''), 1, "missing required key 'version' in template"),
            (STANDARD.replace('name = "standard"\n', ''), 1, "missing required key 'name' in template"),
            (STANDARD.replace('workstream = "guidance/workstreams/plan.md#procedure"\n', ''), 1,
             "missing required key 'workstream' in template"),
            (STANDARD.replace('version = 1', 'version = true'), 1, "version must be an integer"),
            (STANDARD.replace('version = 1', 'version = 2'), 1,
             "unsupported declaration version 2; expected 1"),
            (STANDARD.replace('name = "standard"', 'name = 3'), 2, "name must be a string"),
            (STANDARD.replace('name = "standard"', 'name = ""'), 2, "name must be a nonempty string"),
            (STANDARD.replace('name = "standard"', 'name = "Bad Name"'), 2,
             "invalid template name 'Bad Name'; expected lowercase kebab-case"),
            (STANDARD.replace('name = "standard"', 'name = "other"'), 2,
             "template name 'other' does not match directory 'standard'"),
            (STANDARD.replace('workstream = "guidance/workstreams/plan.md#procedure"', 'workstream = false'), 3,
             "workstream must be a string"),
            (STANDARD.replace('documents = []', 'documents = 1'), 4,
             "documents must be an array of tables"),
            (STANDARD.replace('documents = []', 'documents = [1]'), 4,
             "documents must be an array of tables"),
        ):
            with self.subTest(message=message):
                self.manifest_refuse(STANDARD_MANIFEST, text, line, message)

    def test_syntax_uses_tomllib_parser_line(self):
        text = "version = @\n"
        with self.assertRaises(tomllib.TOMLDecodeError) as expected:
            tomllib.loads(text)
        self.manifest_refuse(STANDARD_MANIFEST, text, 1, f"invalid TOML: {expected.exception}")

    def test_documents_closed_schema_and_types(self):
        for text, line, message in (
            (LOOP + 'execute = "no"\n', 10, "unknown key 'execute' in documents"),
            (LOOP.replace('path = "rounds.md"\n', ''), 5, "missing required key 'path' in documents"),
            (LOOP.replace('source = "rounds.md"\n', ''), 5, "missing required key 'source' in documents"),
            (LOOP.replace('headings = ["Baseline", "Method", "Stop rule", "Rounds"]\n', ''), 5,
             "missing required key 'headings' in documents"),
            (LOOP.replace('path = "rounds.md"', 'path = 3'), 6, "documents.path must be a string"),
            (LOOP.replace('source = "rounds.md"', 'source = false'), 7, "documents.source must be a string"),
            (LOOP.replace('source = "rounds.md"', 'source = ""'), 7, "documents.source must be a nonempty string"),
            (LOOP.replace('task_reference_field = "Standing task"', 'task_reference_field = []'), 9,
             "documents.task_reference_field must be a string"),
            (LOOP.replace('task_reference_field = "Standing task"', 'task_reference_field = ""'), 9,
             "documents.task_reference_field must be a nonempty string"),
        ):
            with self.subTest(message=message):
                self.manifest_refuse(LOOP_MANIFEST, text, line, message)

    def test_headings_specific_precedence(self):
        original = 'headings = ["Baseline", "Method", "Stop rule", "Rounds"]'
        for value in ("[]", '["Baseline", "Baseline"]', '["Baseline", 3]', '[""]', '"Baseline"'):
            with self.subTest(value=value):
                self.manifest_refuse(LOOP_MANIFEST, LOOP.replace(original, "headings = " + value), 8,
                                     "template loop: headings must be nonempty unique strings")

    def test_document_path_collision_normalization_and_second_array_location(self):
        for value in ("plan.md", "./inputs.md", "tasks.md"):
            with self.subTest(value=value):
                normalized = Path(value).as_posix()
                self.manifest_refuse(LOOP_MANIFEST,
                                     LOOP.replace('path = "rounds.md"', f'path = "{value}"'), 6,
                                     f"template loop: duplicate or common document path '{normalized}'")
        extra = '\n[[documents]]\npath = "./rounds.md"\nsource = "rounds.md"\nheadings = ["Baseline"]\n'
        self.manifest_refuse(LOOP_MANIFEST, LOOP + extra, 12,
                             "template loop: duplicate or common document path 'rounds.md'")
        invalid = '\n[[documents]]\npath = "extra.md"\nsource = "rounds.md"\nheadings = ["Baseline"]\nunknown = true\n'
        self.manifest_refuse(LOOP_MANIFEST, LOOP + invalid, 15, "unknown key 'unknown' in documents")

    def test_workstream_target_anchor_and_markdown_type(self):
        original = 'workstream = "guidance/workstreams/iterate.md#procedure"'
        for value, message in (
            ("guidance/workstreams/missing.md", "workstream target does not exist: guidance/workstreams/missing.md"),
            ("guidance/workstreams/iterate.md#absent",
             "workstream anchor does not exist: guidance/workstreams/iterate.md#absent"),
            ("guidance/workstreams/iterate.md#", "workstream anchor does not exist: guidance/workstreams/iterate.md#"),
            ("guidance/workstreams/iterate.txt", "workstream must name a Markdown document"),
        ):
            with self.subTest(value=value):
                self.manifest_refuse(LOOP_MANIFEST, LOOP.replace(original, f'workstream = "{value}"'), 3,
                                     "template loop: " + message)
        self.write("guidance/workstreams/iterate.md", "# Guide\n~~~\n## Procedure\n~~~\n", package=True)
        self.manifest_refuse(LOOP_MANIFEST, LOOP, 3,
                             "template loop: workstream anchor does not exist: guidance/workstreams/iterate.md#procedure")

    def test_lexical_path_escape_all_manifest_path_fields(self):
        for value in ("../outside.md", "/outside.md", "C:/outside.md", "bad\\outside.md"):
            for field, old, line, label, root in (
                ("path", 'path = "rounds.md"', 6, "documents.path", "pack root"),
                ("source", 'source = "rounds.md"', 7, "documents.source", "manifest directory"),
                ("workstream", 'workstream = "guidance/workstreams/iterate.md#procedure"', 3,
                 "workstream", "package root"),
            ):
                with self.subTest(value=value, field=field):
                    text = LOOP.replace(old, f"{field} = {json.dumps(value)}")
                    self.manifest_refuse(LOOP_MANIFEST, text, line,
                                         f"template loop: {label} must resolve inside {root}")

    def test_source_missing_shape_and_order(self):
        self.manifest_refuse(LOOP_MANIFEST, LOOP.replace('source = "rounds.md"', 'source = "missing.md"'), 7,
                             "template loop: missing document source 'missing.md'")
        self.write("templates/loop/rounds.md", ROUNDS.replace("## Stop rule", "Stop rule"), package=True)
        self.manifest_refuse(LOOP_MANIFEST, LOOP, 7,
                             "template loop: document source rounds.md is missing heading '## Stop rule'")
        self.write("templates/loop/rounds.md", ROUNDS.replace("## Baseline\nPending\n## Method",
                                                            "## Method\n## Baseline\nPending"), package=True)
        self.manifest_refuse(LOOP_MANIFEST, LOOP, 7,
                             "template loop: document source rounds.md heading '## Method' is out of order")

    def test_source_symlink_escape_reports_authored_source_key(self):
        target = self.write("external.md", ROUNDS, package=True)
        example = self.package / "templates/loop/rounds.md"
        example.unlink()
        self.symlink(example, target)
        self.assertEqual(self.check(), [
            f"{LOOP_MANIFEST}:7: template loop: documents.source must resolve inside manifest directory"])

    def test_dangling_source_symlink_not_missing_source(self):
        example = self.package / "templates/loop/rounds.md"
        example.unlink()
        self.symlink(example, self.package / "templates/loop/absent.md")
        self.assertEqual(self.check(), [
            f"{LOOP_MANIFEST}:7: template loop: documents.source must resolve inside manifest directory"])

    def test_duplicate_workspace_manifest_cannot_override_package(self):
        self.write(LOOP_MANIFEST, LOOP)
        self.write("guidance/workstreams/iterate.md", WORKSTREAM)
        self.write("templates/loop/rounds.md", ROUNDS)
        self.assertEqual(self.check(), [f"{LOOP_MANIFEST}:2: duplicate template name 'loop'"])

    def test_nested_manifest_not_silently_ignored(self):
        nested = "templates/deep/child/template.toml"
        self.write(nested, STANDARD, package=True)
        self.assertEqual(self.check(), [
            f"{nested}:1: template manifests must be one level below the template root"])

    def test_root_manifest_not_silently_ignored(self):
        path = "templates/template.toml"
        self.write(path, STANDARD, package=True)
        self.assertEqual(self.check(), [
            f"{path}:1: template manifests must be one level below the template root"])

    def test_package_root_wrong_type_and_escape(self):
        shutil.rmtree(self.package / "templates")
        path = self.write("templates", "not a directory", package=True)
        self.assertEqual(self.check(), ["templates:1: template root must name a directory"])
        path.unlink()
        self.symlink(path, self.root, directory=True)
        self.assertEqual(self.check(), ["templates:1: template root must resolve inside package root"])

    def test_research_manifest_specimen_requires_no_new_feature(self):
        specimen = Path(__file__).parent / "fixtures/marketing/templates/research/template.toml"
        self.write("templates/research/template.toml", specimen.read_text(encoding="utf-8"))
        self.write("agent/shared/workstreams/research.md", WORKSTREAM)
        findings = "# Findings\n## Question\n## Sources\n## Findings\n## Next decision\n"
        self.write("templates/research/findings.md", findings)
        self.pack(template="research")
        self.assertEqual(self.check(), [
            f"{PLAN_PATH}:1: template research: missing required document findings.md"])
        self.write("items/alpha/findings.md", findings)
        self.assertEqual(self.check(), [])


class ShapeTests(TemplateFixture):
    def test_loop_missing_heading_and_heading_order_exact_location(self):
        self.pack(template="loop", rounds=True)
        self.write(ROUND_PATH, ROUNDS.replace("## Stop rule", "Stop rule"))
        self.assertEqual(self.check(), [
            f"{ROUND_PATH}:1: template loop: rounds.md is missing heading '## Stop rule'"])
        self.write(ROUND_PATH, ROUNDS.replace("## Baseline\nPending\n## Method",
                                            "## Method\n## Baseline\nPending"))
        self.assertEqual(self.check(), [
            f"{ROUND_PATH}:3: template loop: rounds.md heading '## Method' is out of order"])
        self.write(ROUND_PATH, ROUNDS.replace("## Stop rule", f"{FENCE}\n## Stop rule\n{FENCE}"))
        self.assertEqual(self.check(), [
            f"{ROUND_PATH}:1: template loop: rounds.md is missing heading '## Stop rule'"])
        self.write(ROUND_PATH, ROUNDS.replace("## Method", "## Extra\n## Method"))
        self.assertEqual(self.check(), [])

    def test_standing_task_requires_live_unique_real_row(self):
        self.pack(template="loop", rounds=True)
        message = "template loop: rounds.md needs **Standing task:** naming one existing task"
        self.write(ROUND_PATH, ROUNDS.replace("**Standing task:** LOOP-1\n", ""))
        self.assertEqual(self.check(), [f"{PLAN_PATH}:1: {message}"])
        self.write(ROUND_PATH, ROUNDS.replace("**Standing task:** LOOP-1\n",
                                            "**Standing task:** LOOP-1\n**Standing task:** LOOP-1\n"))
        self.assertEqual(self.check(), [f"{ROUND_PATH}:3: {message}"])
        self.write(ROUND_PATH, ROUNDS)
        for rows in ("", "| LOOP-2 | Open |\n", "| **LOOP-1** | Open |\n| LOOP-1 again | Open |\n",
                     "| LOOP-1? | Open |\n", "| **LOOP-1**suffix | Open |\n",
                     "| | LOOP-1 |\n", f"{FENCE}\n| LOOP-1 | Open |\n{FENCE}\n",
                     "\n| Other | Value |\n| --- | --- |\n| LOOP-1 | Open |\n"):
            with self.subTest(rows=rows):
                self.write("items/alpha/tasks.md", TASKS.split("| **LOOP-1**")[0] + rows)
                self.assertEqual(self.check(), [f"{ROUND_PATH}:2: {message}"])
        self.write("items/alpha/tasks.md", TASKS)
        self.write(ROUND_PATH, ROUNDS.replace("LOOP-1", "loop"))
        self.assertEqual(self.check(), [f"{ROUND_PATH}:2: {message}"])

    def test_task_id_syntax_and_enclosing_spans(self):
        self.pack(template="loop", rounds=True)
        for identifier, cell in (
            ("SL-4", "**SL-4** standing"), ("ER-L", "ER-L standing"),
            ("R.2", chr(96) + "R.2" + chr(96) + " standing"),
            ("A-01", "**A-01 standing**"), ("A", "A"),
        ):
            with self.subTest(identifier=identifier):
                self.write(ROUND_PATH, ROUNDS.replace("LOOP-1", identifier))
                self.write("items/alpha/tasks.md", TASKS.replace("**LOOP-1** standing", cell))
                self.assertEqual(self.check(), [])

    def test_actual_document_path_escape(self):
        self.pack(template="loop")
        outside = self.write("outside.md", ROUNDS)
        self.symlink(self.root / ROUND_PATH, outside)
        self.assertEqual(self.check(), [
            f"{ROUND_PATH}:1: template loop: rounds.md must resolve inside pack root"])

    def test_common_shape_headings_and_tasks_table(self):
        self.pack()
        self.write(PLAN_PATH, "# Project\n## Completion\n## Scope\n")
        self.assertEqual(self.check(base_packs={}), [
            f"{PLAN_PATH}:2: common pack: plan.md heading '## Completion' is out of order"])
        self.write(PLAN_PATH, PLAN)
        self.write("items/alpha/tasks.md", "# Tasks\nNo table\n")
        self.assertEqual(self.check(base_packs={}), [
            f"{PLAN_PATH}:1: common pack: no task table; start the file's first table with the template's header row."])
        self.write("items/alpha/tasks.md", TASKS.replace("| Task |", "| Other |"))
        self.assertEqual(self.check(base_packs={}), [
            "items/alpha/tasks.md:3: common pack: the first table's header row differs from the template's; copy it exactly."])
        self.write("items/alpha/tasks.md", TASKS)
        (self.root / "items/alpha/inputs.md").unlink()
        self.assertEqual(self.check(base_packs={}), [
            f"{PLAN_PATH}:1: common pack: missing required document inputs.md"])

    def test_fenced_task_header_is_not_the_first_live_table(self):
        self.pack()
        self.write("items/alpha/tasks.md", (
            f"# Tasks\n{FENCE}\n| Wrong | Shape |\n| --- | --- |\n{FENCE}\n" + TASKS))
        self.assertEqual(self.check(base_packs={}), [])

    def test_workspace_common_override_no_fallback(self):
        self.pack()
        self.write("otto.toml", CONFIG.replace('items = "items"\n',
                                               'items = "items"\npack_templates = "custom"\n'))
        self.write("custom/plan.md", "# Plan\n## Custom\n")
        self.write("custom/inputs.md", INPUTS)
        self.write("custom/tasks.md", TASKS)
        self.assertEqual(self.check(base_packs={}), [
            f"{PLAN_PATH}:1: common pack: plan.md is missing heading '## Custom'"])
        self.write(PLAN_PATH, "# Project\n## Custom\n")
        self.assertEqual(self.check(base_packs={}), [])
        (self.root / "custom/tasks.md").unlink()
        self.assertEqual(self.check(base_packs={}), [
            "otto.toml:7: common pack: missing template document tasks.md"])

    def test_package_common_missing_or_malformed_sources(self):
        self.pack()
        plan = self.package / "templates/project/plan.md"
        plan.unlink()
        self.assertEqual(self.check(base_packs={}), [
            "otto.toml:1: common pack: missing template document plan.md"])
        self.write("templates/project/plan.md", "# Plan\nNo headings\n", package=True)
        self.assertEqual(self.check(base_packs={}), [
            "templates/project/plan.md:1: common pack: template plan.md has no H2 headings"])
        self.write("templates/project/plan.md", PLAN, package=True)
        self.write("templates/project/tasks.md", "# Tasks\nNo table\n", package=True)
        self.assertEqual(self.check(base_packs={}), [
            "templates/project/tasks.md:1: common pack: template tasks.md has no task table"])


class GitHistoryTests(TemplateFixture):
    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True,
                                       stderr=subprocess.PIPE).rstrip("\n")

    def commit(self):
        self.git("add", "-A")
        self.git("-c", "commit.gpgsign=false", "commit", "-qm", "fixture base")
        return self.git("rev-parse", "HEAD")

    def init(self):
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.com")
        self.git("config", "core.autocrlf", "false")
        return self.commit()

    def test_unavailable_base_fails_even_without_opt_ins(self):
        self.pack()
        self.init()
        self.assertEqual(self.check(base="no-such-revision"), [
            "otto.toml:1: cannot compare template selection: base revision 'no-such-revision' is unavailable"])

    def test_new_committed_staged_untracked_and_old_unchanged(self):
        self.pack()
        self.write(PLAN_PATH, "# Legacy\n")
        base = self.init()
        for folder in ("committed", "staged", "untracked"):
            self.pack(folder)
            self.write(f"items/{folder}/plan.md", "# New\n## Scope\n")
            if folder == "committed":
                self.commit()
            elif folder == "staged":
                self.git("add", f"items/{folder}")
        self.write("items/staged/tasks.md", TASKS + "\nUnstaged edit\n")
        before_status = self.git("status", "--porcelain")
        before_diff = self.git("diff", "--cached", "--binary")
        before_index = (self.root / ".git/index").read_bytes()
        self.assertEqual(self.check(base=base), [
            f"items/{folder}/plan.md:1: common pack: plan.md is missing heading '## Completion'"
            for folder in ("committed", "staged", "untracked")])
        self.assertEqual((self.root / ".git/index").read_bytes(), before_index)
        self.assertEqual(self.git("status", "--porcelain"), before_status)
        self.assertEqual(self.git("diff", "--cached", "--binary"), before_diff)

    def test_same_path_removed_selector_and_explicit_switch(self):
        self.pack(template="loop", rounds=True)
        base = self.init()
        self.write(PLAN_PATH, PLAN)
        self.assertEqual(self.check(base=base), [
            f"{PLAN_PATH}:1: explicit Template field removed from project:alpha; "
            "write **Template:** standard to select standard deliberately"])
        self.pack(template="standard")
        self.assertEqual(self.check(base=base), [])
        self.assertTrue((self.root / ROUND_PATH).is_file())

    def test_stable_numeric_identity_survives_folder_rename(self):
        self.write("otto.toml", CONFIG.replace('policy = "slug"', 'policy = "NN-slug"'))
        self.pack("09-alpha", "loop", rounds=True)
        base = self.init()
        self.git("mv", "items/09-alpha", "items/09-renamed")
        self.write("items/09-renamed/plan.md", PLAN)
        self.assertEqual(self.check(base=base), [
            "items/09-renamed/plan.md:1: explicit Template field removed from project:09; "
            "write **Template:** standard to select standard deliberately"])

    def test_rename_and_rewritten_plan_uses_sibling_evidence(self):
        self.pack(template="loop", rounds=True)
        base = self.init()
        shutil.move(str(self.root / "items/alpha"), str(self.root / "items/renamed"))
        self.write("items/renamed/plan.md", "# Entirely rewritten\n## Scope\n## Completion\n")
        self.assertEqual(self.check(base=base), [
            "items/renamed/plan.md:1: explicit Template field removed from project:renamed; "
            "write **Template:** standard to select standard deliberately"])
        self.commit()
        self.assertEqual(self.check(base=base), [
            "items/renamed/plan.md:1: explicit Template field removed from project:renamed; "
            "write **Template:** standard to select standard deliberately"])

    def test_legacy_standard_rename_does_not_retroactively_validate(self):
        self.pack()
        self.write(PLAN_PATH, "# Old project\n")
        base = self.init()
        shutil.move(str(self.root / "items/alpha"), str(self.root / "items/renamed"))
        self.write("items/renamed/plan.md", "# Rewritten old project\n")
        self.assertEqual(self.check(base=base), [])

    def test_adapter_rename_never_executes_historical_adapter(self):
        config = CONFIG.replace('source = "parent"', 'source = "adapter"').replace(
            'reader = "headers"', 'reader = "adapter"')
        self.write("otto.toml", config + '\n[adapters]\nmodule = "reader.py"\nrecords = "read"\n')
        self.write("reader.py", "raise AssertionError('historical adapter must not execute')\n")
        self.pack(template="loop", rounds=True)
        base = self.init()
        self.write("reader.py", (
            "from otto.ids import RecordRef, SourceLocation\n"
            "from otto.records import Record, RecordBatch\n"
            "def read(workspace):\n"
            "    return RecordBatch(tuple(Record(RecordRef('project', 'stable'), SourceLocation(path, 2))\n"
            "                             for path in workspace.sources['project']))\n"))
        shutil.move(str(self.root / "items/alpha"), str(self.root / "items/renamed"))
        self.write("items/renamed/plan.md", "# Entirely rewritten\n## Scope\n## Completion\n")
        self.assertEqual(self.check(base=base), [
            "items/renamed/plan.md:1: explicit Template field removed from project:stable; "
            "write **Template:** standard to select standard deliberately"])


if __name__ == "__main__":
    unittest.main()
