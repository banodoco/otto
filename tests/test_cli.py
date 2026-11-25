"""Tests for the initial Otto command-line contract."""

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

    def assert_stub(self, *args):
        self.assertEqual(
            self.invoke(*args),
            (2, "", f"not implemented yet: {' '.join(args)}\n"),
        )

    def test_check(self):
        self.assert_stub("check")

    def test_views_generate(self):
        self.assert_stub("views", "generate")

    def test_skills_build(self):
        self.assert_stub("skills", "build")

    def test_skills_check(self):
        self.assert_stub("skills", "check")

    def test_skills_install(self):
        self.assert_stub("skills", "install")

    def test_pipeline_list(self):
        self.assert_stub("pipeline", "list")

    def test_pipeline_show(self):
        self.assert_stub("pipeline", "show")

    def test_version(self):
        self.assertEqual(__version__, "0.0.0")
        self.assertEqual(self.invoke("--version"), (0, "otto 0.0.0\n", ""))

    def test_list_without_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path.cwd()
            try:
                os.chdir(directory)
                self.assertEqual(self.invoke("list"), (0, "", "no otto.toml found\n"))
            finally:
                os.chdir(original)

    def test_list_with_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path.cwd()
            try:
                os.chdir(directory)
                Path("otto.toml").write_text("", encoding="utf-8")
                self.assertEqual(self.invoke("list"), (0, "", ""))
            finally:
                os.chdir(original)

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
