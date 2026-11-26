"""OT-14 end-to-end controls for the actual committed synthetic fixtures."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from otto.cli import main
from otto.config import load_workspace
from otto.records import load_records
from otto.templates import discover_templates


FIXTURES = Path(__file__).parent / "fixtures"
GENERIC = (
    "markdown-links", "link-anchors", "pack-shape", "relationship-validity",
    "pipeline-conformance", "skill-packages-current", "generated-views",
)
LAUNCH = "projects/launch-note/plan.md"
CAMPAIGN = "campaigns/sample-week.md"
ISSUE = "issues/clarify-heading.md"
VIEW = "projects/index.md"
SKILL = ".generated/skills/demo-marketing-draft-note/SKILL.md"
SERVES = "| serves | goal:clear-example | primary |\n"
ROUTE = "| routes-to | project:try-message | primary |"


class FixtureWorkspaceTests(unittest.TestCase):
    def copy_fixture(self, name):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve() / name
        shutil.copytree(FIXTURES / name, self.root)
        return self.root

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                status = main(["--root", str(self.root), *args])
            except SystemExit as exc:
                status = exc.code
        return status, out.getvalue(), err.getvalue()

    def assert_clean(self):
        self.assertEqual(self.invoke("check"), (0, "", ""))

    def assert_registry(self, expected):
        status, output, stderr = self.invoke("list")
        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(tuple(line.split()[0] for line in output.splitlines()), expected)
        self.assertTrue(all(line.split()[1] == "always" for line in output.splitlines()))

    def prepare_marketing(self):
        self.copy_fixture("marketing")
        self.assertFalse((self.root / ".generated").exists())
        status, output, stderr = self.invoke("skills", "build")
        self.assertEqual((status, stderr), (0, ""))
        self.assertIn("created demo-marketing-draft-note\n", output)
        self.assertTrue((self.root / SKILL).is_file())
        self.assert_clean()

    def read(self, path):
        return (self.root / path).read_text(encoding="utf-8")

    def write(self, path, text):
        (self.root / path).write_text(text, encoding="utf-8")

    @contextmanager
    def plant(self, *paths):
        originals = {path: (self.root / path).read_bytes() for path in paths}
        self.assert_clean()
        try:
            yield
        finally:
            for path, original in originals.items():
                (self.root / path).write_bytes(original)
            self.assert_clean()

    def assert_finding(self, check, message):
        self.assertEqual(self.invoke("check"), (1, f"ERROR {check}: {message}\n", ""))

    def row_location(self, path, row):
        lines = self.read(path).splitlines()
        self.assertEqual(lines.count(row), 1)
        return f"{path}:{lines.index(row) + 1}"

    def test_blank_workspace(self):
        self.copy_fixture("blank")
        workspace = load_workspace(self.root)
        self.assertEqual(workspace.record_kinds, ())
        self.assertEqual(workspace.relation_kinds, ())
        self.assertEqual(load_records(workspace).records, ())
        self.assertEqual(self.invoke("pipeline", "list"), (0, "", ""))
        self.assert_registry(GENERIC)
        self.assert_clean()

    def test_fresh_copy_requires_skill_generation(self):
        self.copy_fixture("marketing")
        self.assertFalse((self.root / ".generated").exists())
        self.assert_finding("skill-packages-current", "generated skill packages are missing")
        status, output, stderr = self.invoke("skills", "build")
        self.assertEqual((status, stderr), (0, ""))
        self.assertIn("created demo-marketing-draft-note\n", output)
        self.assert_clean()

    def test_marketing_corpus_and_shared_project(self):
        self.prepare_marketing()
        self.assert_registry(GENERIC + ("example-title-length",))
        self.assertEqual(self.invoke("pipeline", "list"), (0, "intake\nstrategy\n", ""))
        workspace = load_workspace(self.root)
        self.assertEqual(workspace.skill_namespace, "demo-marketing-")
        batch = load_records(workspace)
        self.assertEqual({str(record.ref) for record in batch.records}, {
            "goal:clear-example", "project:launch-note", "project:try-message",
            "project:standalone-note", "campaign:sample-week",
            "issue:clarify-heading", "idea:short-example",
        })
        self.assertEqual(len(batch.records), 7)
        self.assertEqual({(str(row.source), row.kind, str(row.target), row.role)
                          for row in batch.relationships}, {
            ("project:launch-note", "serves", "goal:clear-example", "primary"),
            ("project:try-message", "serves", "goal:clear-example", "primary"),
            ("project:standalone-note", "serves", "goal:clear-example", "primary"),
            ("campaign:sample-week", "includes", "project:launch-note", "included"),
            ("campaign:sample-week", "includes", "project:try-message", "included"),
            ("issue:clarify-heading", "routes-to", "project:launch-note", "primary"),
        })
        self.assertEqual(len(batch.relationships), 6)
        goal = next(record for record in batch.records if record.ref.kind == "goal")
        self.assertEqual((goal.title, goal.source.path, goal.source.line),
                         ("Make the example clear", "strategy.md", 7))
        projects = {record.ref.id: record for record in batch.records if record.ref.kind == "project"}
        self.assertEqual({record.status for record in projects.values()}, {"queued"})
        self.assertEqual({name: record.fields["Template"] for name, record in projects.items()},
                         {"launch-note": "standard", "try-message": "loop",
                          "standalone-note": "standard"})
        self.assertEqual(set(discover_templates(workspace)), {"standard", "loop", "research"})
        self.assertEqual({path.parent.name for path in (self.root / "projects").glob("*/rounds.md")},
                         {"try-message"})
        self.assertEqual(self.invoke("views", "generate"), (0, "", ""))
        self.assertEqual(self.invoke("skills", "check"), (0, "", ""))

        for pipeline, expected in (
            ("strategy", "goal=goal:clear-example -> project=project:launch-note (serves, primary)"
                         " -> campaign=campaign:sample-week (includes, included)"),
            ("intake", "intake=issue:clarify-heading -> project=project:launch-note (routes-to, primary)"),
        ):
            with self.subTest(pipeline=pipeline):
                status, output, stderr = self.invoke("pipeline", "show", pipeline, "project:launch-note")
                self.assertEqual((status, stderr), (0, ""))
                self.assertEqual(output.splitlines(), [expected])
        self.assertEqual(projects["launch-note"].source.path, LAUNCH)
        task_lists = sorted(path.relative_to(self.root).as_posix()
                            for path in self.root.rglob("tasks.md"))
        self.assertEqual(task_lists, [
            "projects/launch-note/tasks.md",
            "projects/standalone-note/tasks.md",
            "projects/try-message/tasks.md",
        ])

    def test_no_primary_goal(self):
        self.prepare_marketing()
        with self.plant(LAUNCH):
            original = self.read(LAUNCH)
            self.assertEqual(original.count(SERVES), 1)
            self.write(LAUNCH, original.replace(SERVES, ""))
            self.assert_finding("pipeline-conformance",
                                f"{LAUNCH}:1: pipeline strategy: project:launch-note"
                                " has no required goal through serves")

    def test_second_primary_goal(self):
        self.prepare_marketing()
        row = "| serves | goal:second-example | primary |"
        with self.plant("strategy.md", LAUNCH):
            self.write("strategy.md", self.read("strategy.md") + "| second-example | Another example |\n")
            self.write(LAUNCH, self.read(LAUNCH) + row + "\n")
            self.assert_finding("pipeline-conformance",
                                f"{self.row_location(LAUNCH, row)}: pipeline strategy: project:launch-note"
                                " has 2 primary serves targets; expected exactly-one")

    def test_empty_campaign(self):
        self.prepare_marketing()
        with self.plant(CAMPAIGN):
            original = self.read(CAMPAIGN)
            rows = [line for line in original.splitlines() if line.startswith("| includes |")]
            self.assertEqual(len(rows), 2)
            self.write(CAMPAIGN, "".join(line for line in original.splitlines(keepends=True)
                                         if not line.startswith("| includes |")))
            self.assert_finding("pipeline-conformance",
                                f"{CAMPAIGN}:1: pipeline strategy: campaign:sample-week"
                                " has no required project through includes")

    def test_two_primary_routes(self):
        self.prepare_marketing()
        with self.plant(ISSUE):
            self.write(ISSUE, self.read(ISSUE) + ROUTE + "\n")
            self.assert_finding("pipeline-conformance",
                                f"{self.row_location(ISSUE, ROUTE)}: pipeline intake: issue:clarify-heading"
                                " has 2 primary routes-to targets; expected at-most-one")

    def test_long_project_title(self):
        self.prepare_marketing()
        with self.plant(LAUNCH, VIEW):
            lines = self.read(LAUNCH).splitlines(keepends=True)
            self.assertEqual(lines[0], "# Launch note\n")
            lines[0] = "# " + "x" * 81 + "\n"
            self.write(LAUNCH, "".join(lines))
            # The changed title is a view source; keep the view current to
            # isolate the local title rule, rather than ignoring other findings.
            self.assertEqual(self.invoke("views", "generate"), (0, VIEW + "\n", ""))
            self.assert_finding("example-title-length",
                                f"{LAUNCH}:1: project:launch-note title exceeds 80 characters")

    def test_stale_view(self):
        self.prepare_marketing()
        with self.plant(VIEW):
            self.write(VIEW, self.read(VIEW) + "\nUnapproved edit.\n")
            self.assert_finding("generated-views",
                                "view project-catalog: the generated part of projects/index.md"
                                " does not match its sources; edit projects/*/plan.md instead"
                                " and undo your change to that part; then regenerate the view")

    def test_stale_skill_package(self):
        self.prepare_marketing()
        with self.plant(SKILL):
            self.write(SKILL, "# Stale\n")
            self.assert_finding("skill-packages-current",
                                f"{SKILL}: demo-marketing-draft-note: generated SKILL.md is stale")

    def test_fixture_vocabulary_and_no_committed_skill_output(self):
        forbidden = re.compile(r"astrid|banodoco|plans/|\bdev\b|\brelease\b", re.IGNORECASE)
        for name in ("marketing", "blank"):
            fixture = FIXTURES / name
            self.assertFalse((fixture / ".generated").exists())
            for path in sorted(fixture.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    with self.subTest(path=path.relative_to(fixture)):
                        self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
