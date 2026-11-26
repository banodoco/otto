"""OT-13 integration coverage using only disposable synthetic workspaces."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from otto.checks import Context, _body
from otto.cli import main
from otto.views import _index_parts


BASE = 'version = 1\n[workspace]\nname = "example"\nskill_namespace = "example-"\n'
REGISTER = (
    '\n[adapters]\nmodule = "adapter.py"\n'
    '[checks]\nregister = "register_checks"\n'
    '[views]\nregister = "register_views"\n'
    'marker_prefix = "<!-- Example view: "\nhint = "run views generate"\n'
)
ADAPTER = """from otto.checks import Check, _body
from otto.views import View

def register_checks(workspace):
    return (
        Check("example-title", "always", "Check example title",
              lambda ctx: ["source.md:1: bad title"] if
              (ctx.root / "source.md").read_text().startswith("# Bad") else []),
        Check("example-pr", "pr", "Check example PR",
              lambda ctx: [] if _body(ctx) == "approved" else ["missing approval"]),
    )

def register_views(workspace):
    return ((View("example", ("source.md",), "output.md",
                  lambda root: (root / "source.md").read_text()),), [])
"""
SKILL = "---\ndescription: An example instruction.\nskill: true\n---\n# Example\n\nFollow the instructions.\n"


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.write("otto.toml", BASE)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                status = main(["--root", str(self.root), *args])
            except SystemExit as exc:
                status = exc.code
        return status, out.getvalue(), err.getvalue()

    def register(self, adapter=ADAPTER):
        self.write("otto.toml", BASE + REGISTER)
        self.write("adapter.py", adapter)
        self.write("source.md", "# Good\n")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def test_registered_checks_and_views_use_configured_marker_and_hint(self):
        self.register()
        status, output, stderr = self.invoke("list")
        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(output.splitlines()[-2:], [
            "example-title always Check example title",
            "example-pr pr Check example PR",
        ])
        self.assertEqual(self.invoke("views", "generate"), (0, "output.md\n", ""))
        target = self.root / "output.md"
        self.assertEqual(target.read_text(),
                         "<!-- Example view: example; sources: source.md. Do not edit. -->\n# Good\n")
        self.assertEqual(self.invoke("views", "generate"), (0, "", ""))
        self.assertEqual(self.invoke("check"), (0, "", ""))
        self.write("source.md", "# Bad\n")
        before = target.read_bytes()
        status, output, stderr = self.invoke("check")
        self.assertEqual((status, stderr), (1, ""))
        self.assertIn("ERROR example-title: source.md:1: bad title\n", output)
        self.assertIn("ERROR generated-views: view example: the generated part of output.md", output)
        self.assertIn("then run views generate", output)
        self.assertEqual(target.read_bytes(), before)

    def test_registration_refusals_and_command_boundaries(self):
        cases = (
            ("def register_checks(w): return []\n",
             "adapter export 'register_checks' returned an invalid check registry"),
            ("from otto.checks import Check\n"
             "def register_checks(w): return (Check('markdown-links','always','Local',lambda c: []),)\n",
             "duplicate check id 'markdown-links'"),
            ("from otto.checks import Check\n"
             "def register_checks(w): return (Check('example','bad','Local',lambda c: []),)\n",
             "check trigger must be always or pr"),
            ("def register_checks(w): raise RuntimeError('fixture failure')\n",
             "cannot load adapter adapter.py: fixture failure"),
            ("register_checks = None\n",
             "adapter export 'register_checks' is missing or not callable"),
        )
        for source, message in cases:
            with self.subTest(message=message):
                self.register(source + "def register_views(w): return ((), [])\n")
                status, output, stderr = self.invoke("list")
                self.assertEqual((status, output), (1, ""))
                line = (BASE + REGISTER).splitlines().index('register = "register_checks"') + 1
                self.assertEqual(stderr, f"otto.toml:{line}: {message}\n")
                self.assertEqual(self.invoke("pipeline", "list"), (0, "", ""))
                self.assertEqual(self.invoke("skills", "check"), (0, "", ""))
                self.assertEqual(self.invoke("views", "generate"), (0, "", ""))
                self.assertEqual(self.invoke("check"), (1, "", stderr))

    def test_view_errors_fail_closed_and_do_not_stop_independent_checks(self):
        self.register("def register_checks(w): return ()\nregister_views = None\n")
        self.write("source.md", "# Good\n\n[bad](missing.md)\n")
        line = (BASE + REGISTER).splitlines().index('register = "register_views"') + 1
        wanted = f"otto.toml:{line}: adapter export 'register_views' is missing or not callable"
        self.assertEqual(self.invoke("list"), (1, "", wanted + "\n"))
        self.assertEqual(self.invoke("views", "generate"), (1, "", wanted + "\n"))
        self.assertEqual(self.invoke("pipeline", "list"), (0, "", ""))
        self.assertEqual(self.invoke("skills", "check"), (0, "", ""))
        self.assertEqual(self.invoke("check"), (
            1, "ERROR markdown-links: source.md:3: missing link target missing.md\n"
            f"ERROR generated-views: {wanted}\n", ""))

    def test_view_duplicate_shape_and_preflight_never_write(self):
        cases = (
            ("return ([], [])", "returned an invalid view registry"),
            ("return ((v, v), [])", "duplicate view name 'example'"),
            ("return ((v,), ['one preflight error', 'another preflight error'])", "one preflight error"),
        )
        for result, message in cases:
            with self.subTest(message=message):
                self.register("from otto.views import View\n"
                              "def register_checks(w): return ()\n"
                              "def register_views(w):\n"
                              "    v = View('example', ('source.md',), 'output.md', lambda r: '# Output\\n')\n"
                              f"    {result}\n")
                self.write("output.md", "unchanged\n")
                status, output, stderr = self.invoke("views", "generate")
                self.assertEqual((status, output), (1, ""))
                self.assertIn(message, stderr)
                self.assertEqual((self.root / "output.md").read_text(), "unchanged\n")
                self.assertEqual(self.invoke("list")[0], 1)

    def test_view_check_uses_generation_target_guard(self):
        self.register("from otto.views import View\n"
                      "def register_checks(w): return ()\n"
                      "def render(root): raise AssertionError('must not render')\n"
                      "def register_views(w): return ((View('example', ('source.md',), '../escape.md', render),), [])\n")
        status, output, stderr = self.invoke("check")
        self.assertEqual((status, stderr), (1, ""))
        self.assertIn("ERROR generated-views: view example: unsafe target outside repository: ../escape.md", output)
        status, output, stderr = self.invoke("views", "generate")
        self.assertEqual((status, output), (1, ""))
        self.assertIn("unsafe target outside repository", stderr)

    def test_pr_selection_and_body_helpers(self):
        self.register()
        self.assertEqual(self.invoke("views", "generate")[0], 0)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        base = self.git("rev-parse", "HEAD")
        self.assertEqual(self.invoke("check"), (0, "", ""))
        body = self.write("pr.txt", "denied")
        self.assertEqual(self.invoke("check", "--base", base, "--body-file", str(body)),
                         (1, "ERROR example-pr: missing approval\n", ""))
        event = self.write("event.json", '{"pull_request":{"body":"approved"}}')
        self.assertEqual(self.invoke("check", "--base", base, "--event", str(event)), (0, "", ""))
        self.assertEqual(_body(Context(self.root, event=event)), "approved")
        self.assertEqual(_body(Context(self.root, body_file=body)), "denied")
        self.assertEqual(_body(Context(self.root)), "")
        self.assertEqual(self.invoke("check", "--base", base)[0], 2)
        self.assertEqual(self.invoke("check", "--event", str(event))[0], 2)
        self.assertEqual(self.invoke("check", "--base", base, "--event", str(event),
                                     "--body-file", str(body))[0], 2)
        text = "before<!-- summary:start -->inside<!-- summary:end -->after"
        self.assertEqual(_index_parts(text, "target.md", "summary"), ("before", "after"))
        with self.assertRaisesRegex(ValueError, "expected exactly one ordered"):
            _index_parts(text + "<!-- summary:end -->", "target.md", "summary")

    def test_link_locations_and_configured_output_exclusion(self):
        self.write("otto.toml", BASE + '\n[paths]\nskills_output = "artifacts/skills"\n')
        self.write("target.md", "# Target\n")
        self.write("source.md", "# Source\n\n" + chr(96) * 3 + "\n[ignored](absent.md)\n"
                   + chr(96) * 3 + "\n\n[bad](absent.md)\n[bad anchor](target.md#missing)\n")
        self.write("artifacts/skills/ignore.md", "[ignored](absent.md)\n")
        status, output, stderr = self.invoke("check")
        self.assertEqual((status, stderr), (1, ""))
        self.assertIn("ERROR markdown-links: source.md:7: missing link target absent.md\n", output)
        self.assertIn("ERROR link-anchors: source.md:8: link to target.md#missing matches no heading", output)
        self.assertNotIn("ignore.md:1:", output)

    def test_skills_build_check_install_and_drift(self):
        self.write("agent/example.md", SKILL)
        status, output, stderr = self.invoke("skills", "build")
        self.assertEqual((status, stderr), (0, ""))
        self.assertIn("created example-example\n", output)
        self.assertEqual(self.invoke("skills", "check"), (0, "", ""))
        self.assertEqual(self.invoke("check"), (0, "", ""))
        destination = self.root / "destination"
        destination.mkdir()
        link = destination / "example-example"
        target = self.root / ".generated/skills/example-example"
        self.assertEqual(self.invoke("skills", "install", "--destination", str(destination), "--dry-run"),
                         (0, f"would-link {link}\n", ""))
        self.assertFalse(link.exists())
        self.assertEqual(self.invoke("skills", "install", "--destination", str(destination)),
                         (0, f"linked {link}\n", ""))
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), target)
        self.write(".generated/skills/example-example/SKILL.md", "# Stale\n")
        wanted = ".generated/skills/example-example/SKILL.md: example-example: generated SKILL.md is stale"
        self.assertEqual(self.invoke("skills", "check"), (1, wanted + "\n", ""))
        self.assertEqual(self.invoke("check"), (1, f"ERROR skill-packages-current: {wanted}\n", ""))
        self.assertEqual((target / "SKILL.md").read_text(), "# Stale\n")

    def graph_fixture(self):
        specimen = Path(__file__).parent / "fixtures/marketing"
        shutil.copyfile(specimen / "otto.toml", self.root / "otto.toml")
        shutil.copytree(specimen / "pipelines", self.root / "pipelines")
        for path in ("projects", "campaigns", "issues", "ideas"):
            (self.root / path).mkdir()
        self.write("strategy.md", "# Example goal\n")
        self.write("scripts/workspace.py", """from otto.ids import RecordRef, SourceLocation
from otto.records import Record, RecordBatch
from otto.checks import Check

def load_strategy_goals(workspace):
    return RecordBatch((Record(RecordRef("goal", "clear-example"),
                               SourceLocation("strategy.md", 1), "Example goal"),))
def register_checks(workspace):
    return (Check("example-local", "always", "Check local data",
                  lambda c: ["strategy.md:1: local finding"] if
                  (c.root / "local-failure").exists() else []),)
def register_views(workspace):
    return ((), [])
""")
        self.project("goal:clear-example")

    def project(self, target):
        self.write("projects/launch-note/plan.md", "# Example project\n\n**Status:** queued\n\n"
                   "## Relationships\n\n| Relation | Target | Role |\n| --- | --- | --- |\n"
                   f"| serves | {target} | primary |\n")

    def test_pipeline_bytes_and_invalid_graph_skip(self):
        self.graph_fixture()
        self.assertEqual(self.invoke("pipeline", "list"), (0, "intake\nstrategy\n", ""))
        self.assertEqual(self.invoke("pipeline", "show", "strategy", "goal:clear-example"),
                         (0, "goal=goal:clear-example -> project=project:launch-note (serves, primary) -> campaign=-\n", ""))
        self.assertEqual(self.invoke("pipeline", "show", "strategy", "unknown"),
                         (0, "Unknown record unknown\n", ""))
        self.assertEqual(self.invoke("check"), (0, "", ""))
        self.project("goal:missing")
        self.write("local-failure", "")
        status, output, stderr = self.invoke("check")
        self.assertEqual((status, stderr), (1, ""))
        self.assertIn("ERROR relationship-validity: projects/launch-note/plan.md:9:", output)
        self.assertIn("names unknown goal:missing", output)
        self.assertNotIn("ERROR pipeline-conformance:", output)
        self.assertIn("ERROR example-local: strategy.md:1: local finding\n", output)
        self.assertEqual(output.count("names unknown goal:missing"), 1)

    def test_record_read_failure_reported_once(self):
        self.graph_fixture()
        self.write("projects/launch-note/plan.md", "no heading\n")
        status, output, stderr = self.invoke("check")
        self.assertEqual((status, stderr), (1, ""))
        self.assertIn("ERROR relationship-validity: projects/launch-note/plan.md:1:", output)
        self.assertEqual(output.count("record document must start with a nonempty # title"), 1)
        self.assertNotIn("ERROR pack-shape:", output)
        self.assertNotIn("ERROR pipeline-conformance:", output)


if __name__ == "__main__":
    unittest.main()
