"""Tests for the Otto command-line contract."""

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest

from otto import __version__
from otto.cli import main


class CliTests(unittest.TestCase):
    def invoke(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                status = main(list(args))
            except SystemExit as exc:
                status = exc.code
        return status, stdout.getvalue(), stderr.getvalue()

    def workspace(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "otto.toml").write_text(
            'version = 1\n[workspace]\nname = "example"\nskill_namespace = "example-"\n',
            encoding="utf-8")
        return root

    def in_workspace(self, root, *args):
        return self.invoke("--root", str(root), *args)

    def test_check(self):
        self.assertEqual(self.in_workspace(self.workspace(), "check"), (0, "", ""))

    def test_views_generate(self):
        self.assertEqual(self.in_workspace(self.workspace(), "views", "generate"), (0, "", ""))

    def test_skills_build(self):
        root = self.workspace()
        self.assertEqual(self.in_workspace(root, "skills", "build"), (0, "", ""))
        self.assertTrue((root / ".generated/skills").is_dir())

    def test_skills_check(self):
        self.assertEqual(self.in_workspace(self.workspace(), "skills", "check"), (0, "", ""))

    def test_skills_install(self):
        root = self.workspace()
        destination = root / "destination"
        destination.mkdir()
        (root / ".generated/skills").mkdir(parents=True)
        self.assertEqual(self.in_workspace(root, "skills", "install", "--destination",
                                           str(destination)), (0, "", ""))
        self.assertEqual(list(destination.iterdir()), [])

    def test_pipeline_list(self):
        self.assertEqual(self.in_workspace(self.workspace(), "pipeline", "list"), (0, "", ""))

    def test_pipeline_show(self):
        root = self.workspace()
        self.assertEqual(self.in_workspace(root, "pipeline", "show", "missing", "record"),
                         (1, "", "unknown pipeline 'missing'\n"))
        status, stdout, stderr = self.in_workspace(root, "pipeline", "show", "missing")
        self.assertEqual((status, stdout), (2, ""))
        self.assertIn("record", stderr)

    def test_version(self):
        self.assertEqual(self.invoke("--version"), (0, f"otto {__version__}\n", ""))

    def test_list_without_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path.cwd()
            try:
                os.chdir(directory)
                self.assertEqual(self.invoke("list"), (0, "", "no otto.toml found\n"))
            finally:
                os.chdir(original)

    def test_list_with_workspace(self):
        root = self.workspace()
        self.assertEqual(self.in_workspace(root, "list"), (
            0,
            "markdown-links always Check relative Markdown links\n"
            "link-anchors always Check relative Markdown headings\n"
            "pack-shape always Check pack shape and templates\n"
            "relationship-validity always Check declared relationships\n"
            "pipeline-conformance always Check declared pipeline constraints\n"
            "skill-packages-current always Check generated skill packages\n"
            "generated-views always Check generated views\n",
            ""))

    def test_malformed_toml_fails_closed(self):
        root = self.workspace()
        (root / "otto.toml").write_text("version = [\n", encoding="utf-8")
        status, stdout, stderr = self.in_workspace(root, "list")
        self.assertEqual((status, stdout), (1, ""))
        self.assertIn("otto.toml:", stderr)

    def test_help_names_every_command(self):
        status, stdout, stderr = self.invoke("--help")
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        words = " ".join(stdout.split())
        for command in (
            "list", "check", "views generate", "skills build", "skills check",
            "skills install", "pipeline list", "pipeline show",
        ):
            with self.subTest(command=command):
                self.assertIn(command, words)

    def test_nested_help(self):
        for group, children in (
            ("views", ("generate",)),
            ("skills", ("build", "check", "install")),
            ("pipeline", ("list", "show")),
        ):
            with self.subTest(group=group):
                status, stdout, stderr = self.invoke(group, "--help")
                self.assertEqual(status, 0)
                self.assertEqual(stderr, "")
                for child in children:
                    self.assertIn(child, stdout)


if __name__ == "__main__":
    unittest.main()
