"""P95-SK: one authored skill configuration across generic and consumer callers."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, replace
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from otto import checks
from otto.cli import main
from otto.config import load_skill_config, load_workspace
from otto.ids import LocatedError
from otto.skills import SkillConfig
from otto.skills.builder import _build_lock, build_packages, check_packages


BASE = """version = 1

[workspace]
name = "example"
skill_namespace = "example-"
"""
CUSTOM_PATHS = """
[paths]
agent = "instructions"
skills_output = "artifacts/packages"
"""
OPTIONS = """
[skills]
generated_header = "<!-- Built from {source}; edit the source. -->"
lock_name_override = ".shared.lock"
lock_stage_prefix_override = ".shared-lock-"
probe_stage_prefix_override = ".shared-probe-"
build_stage_prefix_override = ".shared-build-"
legacy_owned_dirs = ["archive/skills", "legacy-alias"]
legacy_retire_names = ["old-start", "common", "foreign-old"]
path_based_link_ownership = true
"""
DEFAULT = SkillConfig("example-", Path("agent"), Path(".generated/skills"))
CUSTOM = SkillConfig(
    "example-", Path("instructions"), Path("artifacts/packages"),
    generated_header="<!-- Built from {source}; edit the source. -->",
    lock_name_override=".shared.lock",
    lock_stage_prefix_override=".shared-lock-",
    probe_stage_prefix_override=".shared-probe-",
    build_stage_prefix_override=".shared-build-",
    legacy_owned_dirs=(Path("archive/skills"), Path("legacy-alias")),
    legacy_retire_names=("old-start", "common", "foreign-old"),
    path_based_link_ownership=True,
)
SKILL = ("---\ndescription: A useful instruction.\nskill: true\n---\n\n"
         "# Alpha\n\nFollow the instruction.\n")


def snapshot(root):
    result = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[name] = ("link", os.readlink(path))
        elif path.is_dir():
            result[name] = ("dir", None)
        else:
            result[name] = ("file", path.read_bytes())
    return result


class WorkspaceSkillConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name).resolve()
        self.root = self.parent / "checkout"
        self.root.mkdir()
        self.destination = self.parent / "installed"
        self.destination.mkdir()
        self.declare(BASE)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def declare(self, text):
        self.write("otto.toml", text)

    def invoke(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            status = main(["--root", str(self.root), *args])
        return status, output.getvalue(), error.getvalue()

    def refuse(self, declaration, needle, message):
        self.declare(declaration)
        line = next(i for i, text in enumerate(declaration.splitlines(), 1)
                    if needle in text)
        for load in (load_workspace, load_skill_config):
            with self.subTest(loader=load.__name__):
                with self.assertRaises(LocatedError) as caught:
                    load(self.root)
                self.assertTrue(str(caught.exception).startswith(f"otto.toml:{line}: "),
                                str(caught.exception))
                self.assertIn(message, str(caught.exception))
        self.assertEqual((self.root / "otto.toml").read_text(), declaration)

    def configured(self):
        self.declare(BASE + CUSTOM_PATHS + OPTIONS)
        self.write("instructions/notes/alpha.md", SKILL)

    def test_absent_empty_and_partial_defaults_are_identical(self):
        for extra in ("", "\n[skills]\n",
                      "\n[skills]\nlegacy_owned_dirs = []\nlegacy_retire_names = []\n"
                      "path_based_link_ownership = false\n"):
            with self.subTest(extra=extra):
                self.declare(BASE + extra)
                workspace = load_workspace(self.root)
                self.assertEqual(workspace.skill_config, DEFAULT)
                self.assertIs(workspace.config.skills, workspace.skill_config)
                self.assertIs(checks.skill_config(workspace), workspace.skill_config)
                self.assertIs(checks.skill_config(workspace), checks.skill_config(workspace))
                self.assertEqual(load_skill_config(self.root), DEFAULT)
                self.assertEqual(workspace.skill_config.marker, ".example-generated")
                self.assertEqual(workspace.skill_config.lock_name, ".example-skills-build.lock")
                self.assertEqual(workspace.skill_config.lock_stage_prefix, ".example-skills-lock-")
                self.assertEqual(workspace.skill_config.probe_stage_prefix, ".example-skills-probe-")
                self.assertEqual(workspace.skill_config.build_stage_prefix, ".example-skills-build-")
                self.assertEqual(workspace.skill_config.install_stage_prefix, ".example-stage-")
                self.assertEqual(workspace.skill_config.lock_content, b"example-skill-build-lock-v1\n")
                self.assertEqual(workspace.skill_config.repo_link, "../../../")
        self.assertEqual({p.name for p in self.root.iterdir()}, {"otto.toml"})

    def test_each_option_is_independent_and_all_are_immutable(self):
        fields = (
            ("generated_header", CUSTOM.generated_header),
            ("lock_name_override", CUSTOM.lock_name_override),
            ("lock_stage_prefix_override", CUSTOM.lock_stage_prefix_override),
            ("probe_stage_prefix_override", CUSTOM.probe_stage_prefix_override),
            ("build_stage_prefix_override", CUSTOM.build_stage_prefix_override),
            ("legacy_owned_dirs", [p.as_posix() for p in CUSTOM.legacy_owned_dirs]),
            ("legacy_retire_names", list(CUSTOM.legacy_retire_names)),
            ("path_based_link_ownership", True),
        )
        for field, value in fields:
            with self.subTest(field=field):
                self.declare(BASE + "\n[skills]\n" + field + " = " + json.dumps(value) + "\n")
                self.assertEqual(load_skill_config(self.root), replace(DEFAULT, **{field: value}))
                self.assertEqual(checks.skill_config(load_workspace(self.root)),
                                 replace(DEFAULT, **{field: value}))
        self.configured()
        workspace = load_workspace(self.root)
        resolved = workspace.skill_config
        self.assertEqual(resolved, CUSTOM)
        self.assertIs(resolved, workspace.config.skills)
        self.assertIs(resolved, checks.skill_config(workspace))
        self.assertEqual(resolved.lock_content, DEFAULT.lock_content)
        self.assertEqual(resolved.marker, DEFAULT.marker)
        self.assertEqual(resolved.install_stage_prefix, DEFAULT.install_stage_prefix)
        self.assertEqual(resolved.repo_link, "../../../")
        self.assertIsInstance(resolved.legacy_owned_dirs, tuple)
        self.assertIsInstance(resolved.legacy_retire_names, tuple)
        with self.assertRaises(FrozenInstanceError):
            resolved.generated_header = None
        with self.assertRaises(FrozenInstanceError):
            workspace.skill_config = DEFAULT

    def test_wrong_table_unknown_keys_and_wrong_types(self):
        self.refuse("skills = true\n" + BASE, "skills = true", "skills must be a table")
        for field in ("namespace", "source_root", "output", "marker", "lock_content",
                      "repo_link", "install_stage_prefix", "destination", "unexpected"):
            with self.subTest(field=field):
                self.refuse(BASE + f'\n[skills]\n{field} = "x"\n', field + " =",
                            f"unknown key '{field}' in skills")
        for field in ("generated_header", "lock_name_override", "lock_stage_prefix_override",
                      "probe_stage_prefix_override", "build_stage_prefix_override"):
            for value in ("true", "1", "[]", "{}"):
                with self.subTest(field=field, value=value):
                    self.refuse(BASE + f"\n[skills]\n{field} = {value}\n",
                                field + " =", f"skills.{field} must be a string")
        for field in ("legacy_owned_dirs", "legacy_retire_names"):
            self.refuse(BASE + f'\n[skills]\n{field} = "archive"\n',
                        field + " =", f"skills.{field} must be an array of strings")
            self.refuse(BASE + f'\n[skills]\n{field} = [\n "archive",\n 17,\n]\n',
                        "17,", f"skills.{field} must be an array of strings")
        for value in ('"true"', "1", "[]", "{}"):
            self.refuse(BASE + f"\n[skills]\npath_based_link_ownership = {value}\n",
                        "path_based_link_ownership =", "must be a boolean")

    def test_header_name_and_legacy_path_safety_with_source_locations(self):
        for value in ("", "no placeholder", "{source}{source}", "{source!r}",
                      "{source} {}", "{source}\n", "{source}\x7f"):
            self.refuse(BASE + "\n[skills]\ngenerated_header = " + json.dumps(value) + "\n",
                        "generated_header =", "exactly one {source} placeholder")
        for field in ("lock_name_override", "lock_stage_prefix_override",
                      "probe_stage_prefix_override", "build_stage_prefix_override"):
            for value in ("", ".", "..", "/outside", "a/b", r"a\b", "C:lock",
                          "a\x00b", " ", "a. ", "a.", "NUL", "com1.txt", "LPT9",
                          'a"b', "a?b", "a|b"):
                with self.subTest(field=field, value=value):
                    self.refuse(BASE + f"\n[skills]\n{field} = {json.dumps(value)}\n",
                                field + " =", "portable filename or prefix")
        for field, invalid in (
            ("legacy_owned_dirs", ("", ".", "../escape", "a/../b", "/outside",
                                   "C:/outside", r"a\b", "a\x00b", "safe/NUL",
                                   "safe/a.", "safe//x", "safe/./x", "safe/a?b")),
            ("legacy_retire_names", ("", ".", "..", "a/b", r"a\b", "C:entry", "NUL.txt",
                                     "a. ", "a\x00b", "a?b")),
        ):
            for value in invalid:
                with self.subTest(field=field, value=value):
                    entry = json.dumps(value)
                    self.refuse(BASE + f'\n[skills]\n{field} = [\n "archive",\n {entry},\n]\n',
                                " " + entry + ",", field)

    def test_declared_lock_cannot_alias_a_protected_path(self):
        for lock_name in ("notes", "packages", "otto.toml"):
            declaration = (BASE + '\n[paths]\nagent = "notes/agent"\nskills_output = "packages"\n'
                           f'\n[skills]\nlock_name_override = "{lock_name}"\n')
            self.refuse(declaration, "lock_name_override =", "conflicts with a skill root or otto.toml")
        self.assertEqual({p.name for p in self.root.iterdir()}, {"otto.toml"})
        # Python-only callers retain the previously accepted grammar.
        self.assertEqual(replace(DEFAULT, lock_name_override="NUL").lock_name, "NUL")
        self.assertEqual(replace(DEFAULT, legacy_owned_dirs=("old/./skills",)).legacy_owned_dirs,
                         (Path("old/skills"),))

    def test_declaration_only_loader_skips_discovery_and_adapter_execution(self):
        declaration = BASE + CUSTOM_PATHS.replace(
            'skills_output = "artifacts/packages"', 'skills_output = "artifacts/packages"\nitems = "items"'
        ) + OPTIONS + """
[ids.item]
policy = "slug"
source = "stem"

[[record_kinds]]
name = "item"
root = "items"
files = ["*.md"]
reader = "headers"

[adapters]
module = "adapter.py"
records = "records"

[checks]
register = "register_checks"

[views]
register = "register_views"
"""
        self.declare(declaration)
        self.write("items/one.md", "# One\n")
        marker = self.root / "adapter-imported"
        self.write("adapter.py", """from pathlib import Path
from otto.config import load_skill_config
root = Path(__file__).resolve().parent
resolved = load_skill_config(root)
(root / "adapter-imported").write_text("imported", encoding="utf-8")
def config_value(): return resolved
def records(workspace): raise AssertionError("record loader must not run")
def register_checks(workspace): raise AssertionError("check factory must not run")
def register_views(workspace): raise AssertionError("view factory must not run")
""")
        with patch("otto.config._Validator.discover", side_effect=AssertionError("discovery")), \
             patch("otto.config._load_adapter", side_effect=AssertionError("adapter execution")):
            self.assertEqual(load_skill_config(self.root), CUSTOM)
        self.assertFalse(marker.exists())
        # Normal loading still imports the declared module once and validates
        # its exports; the module's own load_skill_config call cannot recurse.
        for validate_registrations in (True, False):
            with self.subTest(validate_registrations=validate_registrations):
                workspace = load_workspace(self.root, validate_registrations=validate_registrations)
                self.assertEqual(workspace.sources["item"], ("items/one.md",))
                self.assertEqual(workspace.export("config_value", declaration=("adapters", "module"))(),
                                 workspace.skill_config)
                self.assertEqual(marker.read_text(), "imported")
                marker.unlink()
        # Malformed skill settings fail before adapter code can execute.
        bad = declaration.replace("path_based_link_ownership = true", 'path_based_link_ownership = "true"')
        self.declare(bad)
        with self.assertRaises(LocatedError):
            load_workspace(self.root, validate_registrations=False)
        self.assertFalse(marker.exists())

    def test_declaration_only_loader_retains_path_validation(self):
        self.refuse(BASE + '\n[paths]\nagent = "../escape"\n', "agent =", "inside the workspace root")
        self.refuse(BASE + '\n[paths]\nagent = "agent"\nskills_output = "agent/generated"\n',
                    "skills_output =", "must not overlap")
        outside = self.parent / "foreign"
        outside.mkdir()
        (self.root / "alias").symlink_to(outside, target_is_directory=True)
        self.refuse(BASE + '\n[paths]\nskills_output = "alias/packages"\n',
                    "skills_output =", "must not be or pass through a symlink")

    def test_default_build_bytes_match_direct_default_config(self):
        self.write("agent/notes/alpha.md", SKILL)
        self.assertTrue(build_packages(self.root, DEFAULT))
        output = self.root / DEFAULT.output
        before = snapshot(output)
        self.assertEqual(self.invoke("skills", "build"), (0, "", ""))
        self.assertEqual(snapshot(output), before)
        self.assertEqual(self.invoke("skills", "check"), (0, "", ""))
        self.assertEqual(self.invoke("check"), (0, "", ""))
        self.assertEqual({p.name for p in output.parent.iterdir()},
                         {output.name, DEFAULT.lock_name})

    def test_cross_cli_build_check_stale_and_shared_build_lock(self):
        self.configured()
        # Consumer-resolved config and generic CLI write one and the same
        # output tree, lock location, header, ownership marker and repo link.
        consumer = load_skill_config(self.root)
        output = self.root / consumer.output
        self.assertTrue(build_packages(self.root, consumer))
        before = snapshot(output)
        package = output / "example-alpha"
        self.assertEqual((package / "SKILL.md").read_bytes(),
                         b'---\nname: example-alpha\ndescription: "A useful instruction."\n---\n\n'
                         b'<!-- Built from instructions/notes/alpha.md; edit the source. -->\n\n'
                         b'# Alpha\n\nFollow the instruction.\n')
        self.assertEqual((package / consumer.marker).read_bytes(), b"instructions/notes/alpha.md\n")
        self.assertEqual(os.readlink(package / "repo"), consumer.repo_link)
        self.assertEqual(self.invoke("skills", "check"), (0, "", ""))
        self.assertEqual(self.invoke("check"), (0, "", ""))

        with patch("otto.skills.builder.tempfile.mkstemp", wraps=tempfile.mkstemp) as lock_stage, \
             patch("otto.skills.builder.tempfile.TemporaryDirectory",
                   wraps=tempfile.TemporaryDirectory) as stages:
            self.assertEqual(self.invoke("skills", "build"), (0, "", ""))
        lock_stage.assert_called_once_with(prefix=consumer.lock_stage_prefix, dir=output.parent)
        self.assertEqual([(call.kwargs["prefix"], call.kwargs["dir"])
                          for call in stages.call_args_list],
                         [(consumer.probe_stage_prefix, output.parent),
                          (consumer.build_stage_prefix, output.parent)])
        self.assertEqual(check_packages(self.root, consumer), [])
        self.assertEqual(snapshot(output), before)
        lock = output.parent / consumer.lock_name
        self.assertEqual(lock.read_bytes(), consumer.lock_content)
        self.assertEqual({p.name for p in output.parent.iterdir()}, {output.name, lock.name})

        with _build_lock(output.parent, consumer):
            status, _, error = self.invoke("skills", "build")
            self.assertEqual(status, 1)
            self.assertIn("another skill build", error)
        self.assertEqual(snapshot(output), before)
        lock.write_bytes(b"foreign lock\n")
        status, _, error = self.invoke("skills", "build")
        self.assertEqual(status, 1)
        self.assertIn("foreign skill build lock", error)
        self.assertEqual(lock.read_bytes(), b"foreign lock\n")
        self.assertEqual(snapshot(output), before)
        lock.unlink()

        skill = package / "SKILL.md"
        skill.write_bytes(b"# Stale\n")
        wanted = "artifacts/packages/example-alpha/SKILL.md: example-alpha: generated SKILL.md is stale"
        self.assertEqual(self.invoke("skills", "check"), (1, wanted + "\n", ""))
        self.assertEqual(self.invoke("check"), (1, f"ERROR skill-packages-current: {wanted}\n", ""))
        self.assertEqual(skill.read_bytes(), b"# Stale\n")
        self.assertEqual(self.invoke("skills", "build")[0], 0)
        self.assertEqual(check_packages(self.root, consumer), [])
        self.assertEqual(snapshot(output), before)

    def test_temp_install_legacy_opt_in_never_grants_foreign_ownership(self):
        self.configured()
        self.assertEqual(self.invoke("skills", "build")[0], 0)
        legacy = self.root / "archive/skills/alpha"
        legacy.mkdir(parents=True)
        foreign = self.parent / "foreign"
        foreign.mkdir()
        (self.root / "legacy-alias").symlink_to(foreign, target_is_directory=True)
        (self.destination / "old-start").symlink_to(legacy, target_is_directory=True)
        (self.destination / "common").symlink_to(foreign, target_is_directory=True)
        (self.destination / "foreign-old").symlink_to(self.root / "legacy-alias",
                                                      target_is_directory=True)
        (self.destination / "example-manual").write_bytes(b"foreign file")
        desired = self.destination / "example-alpha"
        desired.symlink_to(self.root / "legacy-alias", target_is_directory=True)

        # Even explicit path mode must not take ownership through an escaped
        # legacy-root alias. Neither dry-run nor actual install may mutate.
        for dry in (("--dry-run",), ()):
            before = snapshot(self.destination)
            status, _, error = self.invoke("skills", "install", "--destination",
                                           str(self.destination), *dry)
            self.assertEqual(status, 1)
            self.assertIn("foreign symlink", error)
            self.assertEqual(snapshot(self.destination), before)
        desired.unlink()
        desired.symlink_to(legacy, target_is_directory=True)
        self.declare(BASE + CUSTOM_PATHS + OPTIONS.replace(
            "path_based_link_ownership = true", "path_based_link_ownership = false"))
        before = snapshot(self.destination)
        status, _, error = self.invoke("skills", "install", "--destination", str(self.destination))
        self.assertEqual(status, 1)
        self.assertIn("foreign symlink", error)
        self.assertEqual(snapshot(self.destination), before)

        self.declare(BASE + CUSTOM_PATHS + OPTIONS)
        self.assertEqual(self.invoke("skills", "check"), (0, "", ""))
        status, actions, error = self.invoke("skills", "install", "--destination",
                                             str(self.destination), "--dry-run")
        self.assertEqual((status, error), (0, ""))
        self.assertEqual(actions.splitlines(), [f"would-retarget {desired}",
                                               f"would-retire {self.destination / 'old-start'}"])
        self.assertEqual(snapshot(self.destination), before)
        status, actions, error = self.invoke("skills", "install", "--destination", str(self.destination))
        self.assertEqual((status, error), (0, ""))
        self.assertEqual(actions.splitlines(), [f"retargeted {desired}",
                                               f"retired {self.destination / 'old-start'}"])
        self.assertEqual(desired.resolve(), self.root / CUSTOM.output / "example-alpha")
        self.assertFalse((self.destination / "old-start").is_symlink())
        self.assertEqual((self.destination / "common").resolve(), foreign)
        self.assertEqual((self.destination / "foreign-old").resolve(), foreign)
        self.assertEqual((self.destination / "example-manual").read_bytes(), b"foreign file")

    def test_opt_in_keeps_generated_custody_checks(self):
        self.configured()
        self.assertEqual(self.invoke("skills", "build")[0], 0)
        output = self.root / CUSTOM.output
        package = output / "example-alpha"
        marker = package / CUSTOM.marker
        foreign = self.parent / "foreign-marker"
        foreign.write_bytes(marker.read_bytes())
        marker.unlink()
        marker.symlink_to(foreign)
        before = snapshot(output)
        status, _, error = self.invoke("skills", "build")
        self.assertEqual(status, 1)
        self.assertIn("refusing unmanaged generated package", error)
        status, _, error = self.invoke("skills", "install", "--destination", str(self.destination))
        self.assertEqual(status, 1)
        self.assertIn("refusing unmanaged generated package", error)
        self.assertEqual(snapshot(output), before)
        self.assertEqual(list(self.destination.iterdir()), [])
        self.assertEqual(foreign.read_bytes(), b"instructions/notes/alpha.md\n")


if __name__ == "__main__":
    unittest.main()
