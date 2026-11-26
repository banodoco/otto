"""P95-PK: qualify the source and installed resource layouts without a build."""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

from otto.config import load_workspace
from otto.records import load_records
from otto.skills import SkillConfig
from otto.skills.builder import expected_packages
from otto.templates import (
    PACKAGE_ROOT, _resource_root, check_pack_shape, common_shape,
    discover_templates,
)


SOURCE = Path(__file__).resolve().parents[1]
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
SKILLS = SkillConfig("otto-", Path("guidance"), Path(".generated/skills"))


def snapshot(workspace_root: Path) -> dict:
    """Exercise the default resource paths, including import-time defaults."""
    workspace = load_workspace(workspace_root)
    inventory = discover_templates(workspace)
    shape = common_shape(workspace)
    return {
        "manifests": {
            name: {
                "workstream": manifest.workstream.relative_to(PACKAGE_ROOT).as_posix(),
                "anchor": manifest.anchor,
                "documents": [
                    [doc.path, doc.source.relative_to(PACKAGE_ROOT).as_posix(),
                     list(doc.headings), doc.task_reference_field]
                    for doc in manifest.documents
                ],
            }
            for name, manifest in inventory.items()
        },
        "common_shape": [list(shape.plan_headings), list(shape.inputs_headings),
                         list(shape.task_header)],
        "errors": check_pack_shape(workspace, load_records(workspace), base_packs={}),
        "skills": {name: list(package) for name, package in
                   expected_packages(PACKAGE_ROOT, SKILLS).items()},
    }


class PackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def asset_paths(self):
        with (SOURCE / "pyproject.toml").open("rb") as stream:
            settings = tomllib.load(stream)["tool"]["setuptools"]
        self.assertFalse(settings["include-package-data"])
        self.assertEqual(settings["package-dir"]["otto._assets"], ".")
        self.assertIn("otto._assets", settings["packages"])
        patterns = settings["package-data"]["otto._assets"]
        found = set()
        for pattern in patterns:
            matches = {p.relative_to(SOURCE) for p in SOURCE.glob(pattern) if p.is_file()}
            self.assertTrue(matches, pattern)
            found.update(matches)
        expected = {p.relative_to(SOURCE)
                    for folder in ("templates", "guidance")
                    for p in (SOURCE / folder).rglob("*") if p.is_file()}
        expected.add(Path("docs/contract.md"))
        self.assertEqual(found, expected)
        return found

    def test_locator_distinguishes_checkout_and_installed_package(self):
        checkout = self.root / "checkout"
        module = self.write(checkout / "otto/templates.py", "")
        self.write(checkout / "pyproject.toml", '[project]\nname = "banodoco-otto"\n')
        self.assertEqual(_resource_root(module), checkout)
        assets = checkout / "otto/_assets"
        assets.mkdir()
        self.assertEqual(_resource_root(module), assets)

        foreign = self.root / "site-packages"
        module = self.write(foreign / "otto/templates.py", "")
        self.write(foreign / "templates/standard/template.toml", "unrelated")
        self.write(foreign / "guidance/workstreams/plan.md", "unrelated")
        self.assertEqual(_resource_root(module), foreign / "otto/_assets")
        self.write(foreign / "pyproject.toml", '[project]\nname = "other"\n')
        self.assertEqual(_resource_root(module), foreign / "otto/_assets")
        self.write(foreign / "pyproject.toml", "invalid TOML")
        self.assertEqual(_resource_root(module), foreign / "otto/_assets")

    def test_wheel_shaped_tree_uses_same_default_readers_and_skill_rendering(self):
        self.assertEqual(PACKAGE_ROOT, SOURCE)
        site = self.root / "site-packages"
        assets = site / "otto/_assets"
        # Model the wheel's filesystem layout from its declared data patterns;
        # actual setuptools build/install is a separate clean-venv proof.
        paths = self.asset_paths()
        for relative in paths:
            target = assets / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        self.assertEqual({p.relative_to(assets) for p in assets.rglob("*") if p.is_file()},
                         paths)
        for relative in paths:
            self.assertEqual((assets / relative).read_bytes(), (SOURCE / relative).read_bytes())
        for source in (SOURCE / "otto").rglob("*.py"):
            target = site / source.relative_to(SOURCE)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

        # A separate workspace contains two real packs and misleading sibling
        # assets. Neither the CWD nor site-packages' root may replace built-ins.
        workspace = self.root / "workspace"
        self.write(workspace / "otto.toml", CONFIG)
        self.write(site / "templates/standard/template.toml", "not a manifest")
        self.write(site / "guidance/workstreams/plan.md", "not guidance")
        for name in ("standard", "loop"):
            pack = workspace / "items" / name
            for document in ("plan.md", "inputs.md", "tasks.md"):
                content = (SOURCE / "templates/project" / document).read_text(encoding="utf-8")
                if document == "plan.md":
                    title, rest = content.split("\n", 1)
                    content = f"{title}\n\n**Template:** {name}\n{rest}"
                if document == "tasks.md" and name == "loop":
                    content = content.replace(
                        "| | | | | | |",
                        "| **LOOP-1** Observe | N | — | Example | Record observation | [ ] |",
                    )
                self.write(pack / document, content)
            if name == "loop":
                shutil.copyfile(SOURCE / "templates/loop/rounds.md", pack / "rounds.md")

        source_snapshot = snapshot(workspace)
        self.assertEqual(set(source_snapshot["manifests"]), {"standard", "loop"})
        self.assertEqual(source_snapshot["errors"], [])
        self.assertIn("otto-stand-up", source_snapshot["skills"])
        self.assertIn("repo/docs/contract.md#", source_snapshot["skills"]["otto-stand-up"][0])
        self.assertIn("otto-iterate", source_snapshot["skills"])

        # Start a new interpreter so all default arguments bind to the
        # installed resource root. -I prevents the source tree or PYTHONPATH
        # from accidentally satisfying imports. No package is built here.
        script = """
import json, runpy, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from otto.templates import PACKAGE_ROOT
assert PACKAGE_ROOT == Path(sys.argv[1]) / "otto/_assets", PACKAGE_ROOT
snapshot = runpy.run_path(sys.argv[2])["snapshot"]
print(json.dumps(snapshot(Path(sys.argv[3]))))
"""
        result = subprocess.run(
            [sys.executable, "-I", "-c", script, str(site),
             str(Path(__file__).resolve()), str(workspace)],
            cwd=workspace, capture_output=True, text=True, encoding="utf-8", check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), source_snapshot)


if __name__ == "__main__":
    unittest.main()
