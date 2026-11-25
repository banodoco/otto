"""OT-12: qualify the authored built-ins and the workspace-only extension seam."""
from pathlib import Path
import tempfile
import unittest

from otto.config import load_workspace
from otto.records import load_records
from otto.templates import (
    PACKAGE_ROOT,
    check_pack_shape,
    common_shape,
    discover_templates,
)

CONFIG = """version = 1
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
"""
RESEARCH = """version = 1
name = "research"
workstream = "workstreams/research.md#procedure"

[[documents]]
path = "findings.md"
source = "findings.md"
headings = ["Question", "Sources", "Findings", "Next decision"]
"""
FINDINGS = """# Findings
## Question
What would clarify the example?
## Sources
Pending.
## Findings
No observation yet.
## Next decision
Gather evidence.
"""
RESEARCH_MANIFEST = "templates/research/template.toml"
RESEARCH_SOURCE = "templates/research/findings.md"
PLAN_PATH = "items/sample/plan.md"
TASK_PATH = "items/sample/tasks.md"
ROUND_PATH = "items/sample/rounds.md"
FINDINGS_PATH = "items/sample/findings.md"


class BuiltinTemplateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.write("otto.toml", CONFIG)
        (self.root / "items").mkdir()

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def asset(self, path):
        return (PACKAGE_ROOT / "templates" / path).read_text(encoding="utf-8")

    def pack(self, template=None):
        # Use the actual source assets rather than a second invented common shape.
        plan = self.asset("project/plan.md")
        if template is not None:
            title, body = plan.split("\n", 1)
            plan = f"{title}\n\n**Template:** {template}\n{body}"
        self.write(PLAN_PATH, plan)
        self.write("items/sample/inputs.md", self.asset("project/inputs.md"))
        self.write(TASK_PATH, self.asset("project/tasks.md"))

    def add_research(self):
        self.write(RESEARCH_MANIFEST, RESEARCH)
        self.write(RESEARCH_SOURCE, FINDINGS)
        self.write("workstreams/research.md", "# Research\n\n## Procedure\nCollect evidence.\n")

    def inventory(self):
        return discover_templates(load_workspace(self.root))

    def check(self):
        workspace = load_workspace(self.root)
        records = load_records(workspace)
        self.assertEqual([str(record.ref) for record in records.records], ["project:sample"])
        # Empty prior inventory means a new pack, even without a live selector.
        return check_pack_shape(workspace, records, base_packs={})

    def test_shipped_manifests_and_common_shape(self):
        inventory = self.inventory()
        self.assertEqual(set(inventory), {"standard", "loop"})
        self.assertEqual(inventory["standard"].documents, ())
        self.assertEqual(inventory["standard"].workstream,
                         PACKAGE_ROOT / "guidance/workstreams/plan.md")
        self.assertEqual(inventory["standard"].anchor, "procedure")
        loop = inventory["loop"]
        self.assertEqual(loop.workstream, PACKAGE_ROOT / "guidance/workstreams/iterate.md")
        self.assertEqual(loop.anchor, "live-loops")
        self.assertEqual(len(loop.documents), 1)
        rounds = loop.documents[0]
        self.assertEqual(rounds.path, "rounds.md")
        self.assertEqual(rounds.source, PACKAGE_ROOT / "templates/loop/rounds.md")
        self.assertEqual(rounds.headings, ("Baseline", "Method", "Stop rule", "Rounds"))
        self.assertEqual(rounds.task_reference_field, "Standing task")
        shape = common_shape(load_workspace(self.root))
        self.assertEqual(shape.plan_headings, (
            "Outcome and scope", "Existing work and decision", "Sequence and readiness",
            "Interfaces and handoff", "Completion",
        ))
        self.assertEqual(shape.inputs_headings, (
            "Planning evidence", "Owner decisions", "Source identities", "References",
        ))
        self.assertEqual(shape.task_header, (
            "Task / outcome", "Route", "Depends on", "Scope", "Focused proof", "Progress",
        ))

    def test_new_standard_pack_has_no_loop_document(self):
        self.pack()
        self.assertFalse((self.root / ROUND_PATH).exists())
        self.assertEqual(self.check(), [])
        self.pack("standard")
        self.assertEqual(self.check(), [])

    def test_draft_loop_with_pending_baseline_and_real_standing_task(self):
        self.pack("loop")
        self.assertEqual(self.check(), [
            f"{PLAN_PATH}:1: template loop: missing required document rounds.md",
        ])
        rounds = self.asset("loop/rounds.md")
        self.assertIn("## Baseline\n\nPending", rounds)
        self.assertIn("**Standing task:** LOOP-1", rounds)
        self.write(ROUND_PATH, rounds)
        message = "template loop: rounds.md needs **Standing task:** naming one existing task"
        self.assertEqual(self.check(), [f"{ROUND_PATH}:3: {message}"])
        tasks = self.asset("project/tasks.md").replace(
            "| | | | | | |",
            "| **LOOP-1** Observe | N | — | Example | Record observation | [ ] |",
        )
        self.write(TASK_PATH, tasks)
        self.assertEqual(self.check(), [])
        self.write(ROUND_PATH, rounds.replace("## Stop rule", "Stop rule"))
        self.assertEqual(self.check(), [
            f"{ROUND_PATH}:1: template loop: rounds.md is missing heading '## Stop rule'",
        ])

    def test_research_extends_the_real_inventory_with_no_code_change(self):
        self.pack("research")
        self.assertEqual(self.check(), [
            f"{PLAN_PATH}:3: unknown project template 'research'",
        ])
        self.add_research()
        inventory = self.inventory()
        self.assertEqual(set(inventory), {"standard", "loop", "research"})
        research = inventory["research"]
        self.assertEqual(research.workstream, self.root / "workstreams/research.md")
        self.assertEqual(research.anchor, "procedure")
        self.assertEqual(len(research.documents), 1)
        self.assertEqual(research.documents[0].headings, (
            "Question", "Sources", "Findings", "Next decision",
        ))
        self.assertEqual(self.check(), [
            f"{PLAN_PATH}:1: template research: missing required document findings.md",
        ])
        self.write(FINDINGS_PATH, FINDINGS)
        self.assertEqual(self.check(), [])
        self.assertFalse((self.root / ROUND_PATH).exists())
        self.write(FINDINGS_PATH, FINDINGS.replace("## Sources", "Sources"))
        self.assertEqual(self.check(), [
            f"{FINDINGS_PATH}:1: template research: findings.md is missing heading '## Sources'",
        ])

    def test_malformed_workspace_manifest_refusals(self):
        self.pack("research")
        self.add_research()
        self.write(FINDINGS_PATH, FINDINGS)
        for manifest, line, message in (
            (RESEARCH.replace('name = "research"', 'name = "other"'), 2,
             "template name 'other' does not match directory 'research'"),
            (RESEARCH.replace("#procedure", "#absent"), 3,
             "template research: workstream anchor does not exist: workstreams/research.md#absent"),
            (RESEARCH.replace("workstreams/research.md", "workstreams/missing.md"), 3,
             "template research: workstream target does not exist: workstreams/missing.md#procedure"),
            (RESEARCH.replace('source = "findings.md"', 'source = "missing.md"'), 7,
             "template research: missing document source 'missing.md'"),
            (RESEARCH.replace('source = "findings.md"', 'source = "../findings.md"'), 7,
             "template research: documents.source must resolve inside manifest directory"),
            (RESEARCH + 'execute = "no"\n', 9, "unknown key 'execute' in documents"),
            (RESEARCH.replace('path = "findings.md"', 'path = "plan.md"'), 6,
             "template research: duplicate or common document path 'plan.md'"),
        ):
            with self.subTest(message=message):
                self.write(RESEARCH_MANIFEST, manifest)
                self.assertEqual(self.check(), [f"{RESEARCH_MANIFEST}:{line}: {message}"])
        self.write(RESEARCH_MANIFEST, RESEARCH)
        self.write(RESEARCH_SOURCE, FINDINGS.replace("## Findings", "Findings"))
        self.assertEqual(self.check(), [
            f"{RESEARCH_MANIFEST}:7: template research: document source findings.md "
            "is missing heading '## Findings'",
        ])

    def test_workspace_cannot_override_a_shipped_name(self):
        self.pack()
        self.add_research()
        self.write("templates/loop/template.toml", (
            'version = 1\nname = "loop"\n'
            'workstream = "workstreams/research.md#procedure"\ndocuments = []\n'
        ))
        self.assertEqual(self.check(), [
            "templates/loop/template.toml:2: duplicate template name 'loop'",
        ])


if __name__ == "__main__":
    unittest.main()
