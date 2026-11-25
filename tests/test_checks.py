"""Contract and legacy-rule coverage for the check command."""
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from otto import checks

def invoke(args, **kwargs):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = checks.main(args, **kwargs)
    return code, output.getvalue()


class ContractTests(unittest.TestCase):
    def test_check_selection_messages_and_context(self):
        calls = []
        def run(name, messages):
            def check(context):
                calls.append((name, context))
                return messages
            return check
        entries = [checks.Check("a", "always", "First check", run("a", ["old message", "second"])),
                   checks.Check("b", "pr", "PR check", run("b", ["PR message"])),
                   checks.Check("c", "always", "Last check", run("c", []))]
        root = Path("/fixture")
        code, output = invoke(["check"], root=root, registry=entries)
        self.assertEqual((code, output), (1, "ERROR a: old message\nERROR a: second\n"))
        self.assertEqual([name for name, _ in calls], ["a", "c"])
        for option in ("--body-file", "--event"):
            calls.clear()
            code, output = invoke(["check", "--base", "abc", option, "input"], root=root, registry=entries)
            self.assertEqual(code, 1)
            self.assertEqual(output, "ERROR a: old message\nERROR a: second\nERROR b: PR message\n")
            self.assertEqual([name for name, _ in calls], ["a", "b", "c"])
            self.assertEqual(calls[1][1].root, root)
            self.assertEqual(calls[1][1].base, "abc")
            self.assertEqual(getattr(calls[1][1], "body_file" if option == "--body-file" else "event"), Path("input"))

    def test_success_list_and_invalid_arguments(self):
        entries = [checks.Check("one", "always", "A check", lambda _: []),
                   checks.Check("two", "pr", "Another check", lambda _: [])]
        self.assertEqual(invoke(["list"], registry=entries), (0, "one always A check\ntwo pr Another check\n"))
        self.assertEqual(invoke(["check"], registry=entries), (0, ""))
        for args in (["check", "--base", "abc"], ["check", "--event", "e"],
                     ["check", "--base", "abc", "--event", "e", "--body-file", "b"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                invoke(args, registry=entries)
            self.assertEqual(exc.exception.code, 2)

    def test_definition_validation(self):
        for args in (("", "always", "description", lambda _: []),
                     ("id", "other", "description", lambda _: []),
                     ("id", "pr", "two\nlines", lambda _: []),
                     ("id", "pr", "description", None)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                checks.Check(*args)


class LinkAnchorTests(unittest.TestCase):
    def run_rule(self, files):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative, text in files.items():
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_text(text, encoding="utf-8")
            entry = checks.Check("link-anchors", "always", "Validate links to headings",
                                 lambda context: checks._link_anchors(context, target_pattern=r"(?:agent|templates)/.+\.md|docs/[^/]+\.md"))
            self.assertEqual(entry.trigger, "always")
            return entry.run(checks.Context(root))

    def test_good_link_passes_and_missing_heading_fails(self):
        self.assertEqual(self.run_rule({
            "docs/guide.md": "# Guide\n\n## Set up\n",
            "skills/a/SKILL.md": "See [setup](../../docs/guide.md#set-up).\n"}), [])
        self.assertEqual(self.run_rule({
            "docs/guide.md": "## Set up\n",
            "skills/a/SKILL.md": "See [setup](../../docs/guide.md#install).\n"}), [
            "skills/a/SKILL.md: link to docs/guide.md#install matches no heading in that file; point the link at a heading that exists"])
        self.assertEqual(self.run_rule({
            "templates/t.md": "## Set up\n\n[bad](#install)\n"}), [
            "templates/t.md: link to templates/t.md#install matches no heading in that file; point the link at a heading that exists"])

    def test_repeated_heading_resolves_with_numeric_suffix(self):
        self.assertEqual(self.run_rule({
            "docs/guide.md": "## Step\n\n## Step\n\n## Step\n",
            "skills/a/SKILL.md": "[a](../../docs/guide.md#step) [b](../../docs/guide.md#step-1) "
                                 "[c](../../docs/guide.md#step-2)\n"}), [])
        self.assertEqual(self.run_rule({
            "docs/guide.md": "## Step\n",
            "skills/a/SKILL.md": "[d](../../docs/guide.md#step-1)\n"}), [
            "skills/a/SKILL.md: link to docs/guide.md#step-1 matches no heading in that file; point the link at a heading that exists"])

    def test_heading_with_link_or_backticks_resolves(self):
        self.assertEqual(self.run_rule({
            "docs/guide.md": "## Use `check` and [sync](sync.md)\n",
            "skills/a/SKILL.md": "[x](../../docs/guide.md#use-check-and-sync)\n"}), [])

    def test_canonical_agent_fragments_are_checked_and_derived_packages_excluded(self):
        files = {
            "agent/roles/manager.md": "# Manager\n\n## Steps\n",
            "agent/start.md": "[steps](roles/manager.md#steps)\n",
            ".generated/skills/astrid-dev-manager/SKILL.md":
                "[stale](../../../agent/roles/manager.md#missing)\n",
        }
        self.assertEqual(self.run_rule(files), [])
        files["agent/start.md"] = "[missing](roles/manager.md#missing)\n"
        self.assertEqual(self.run_rule(files), [
            "agent/start.md: link to agent/roles/manager.md#missing matches no heading in that file; point the link at a heading that exists"])

    def test_fragment_into_plans_is_not_reported(self):
        self.assertEqual(self.run_rule({
            "plans/20-x/plan.md": "## Real\n",
            "docs/guide.md": "[p](../plans/20-x/plan.md#missing)\n",
            "skills/a/SKILL.md": "[p](../../plans/20-x/plan.md#missing)\n"}), [])
