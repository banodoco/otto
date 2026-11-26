"""Opt-in compatibility seams; the original namespace rules remain the default."""
from dataclasses import replace
import errno
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from otto.skills import SkillConfig
from otto.skills.builder import (
    _build_lock, build_packages, check_packages, render_skill,
)
from otto.skills.documents import parse_document
from otto.skills.installer import install_packages, PartialInstallationError


DEFAULT = SkillConfig("demo-", Path("agent"), Path(".generated/skills"))
COMPAT = replace(
    DEFAULT,
    generated_header="<!-- Built from {source}; edit the source instead. -->",
    lock_name_override=".skills-build.lock",
    lock_stage_prefix_override=".skills-lock-",
    probe_stage_prefix_override=".skills-probe-",
    build_stage_prefix_override=".skills-build-",
    legacy_owned_dirs=(Path("skills"),),
    legacy_retire_names=("old-start", "common"),
    path_based_link_ownership=True,
)

# Digest of the default build of the fixed fixture below, measured on the
# unchanged baseline fcf5addcff6f3fbdb9ba0b4b659aaa483501dc3a (before any seam
# existed). A change here means Otto's default output moved.
EXPECTED_DEFAULT_TREE_SHA256 = "f6d1c5fcd8b76a54d9182c9b4e5f963dde8c9850a81ddd585c34e82aaade3e74"
FIXED_DOCUMENTS = {
    "agent/notes/alpha.md": (
        "---\ndescription: Start the work and report what you find.\nskill: true\n---\n\n"
        "# Alpha\n\nRead [the sibling](beta.md) first, then [the guide](../../docs/guide.md#steps).\n"),
    "agent/notes/beta.md": (
        "---\ndescription: Keep the record while the work runs.\nskill: true\n---\n\n"
        "# Beta\n\nBack to [Alpha](alpha.md#alpha).\n"),
    "docs/guide.md": "# Guide\n\n## Steps\n\nDo them.\n",
}


def _tree_snapshot(output: Path) -> dict[str, tuple[str, bytes]]:
    entries = {}
    for path in sorted(output.rglob("*")):
        name = path.relative_to(output).as_posix()
        if path.is_symlink():
            entries[name] = ("L", os.readlink(path).encode("utf-8"))
        elif path.is_dir():
            entries[name] = ("D", b"")
        else:
            entries[name] = ("F", path.read_bytes())
    return entries


def _tree_sha256(entries: dict[str, tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, (kind, payload) in sorted(entries.items()):
        payload_hash = hashlib.sha256(payload).hexdigest()
        digest.update(f"{name}\0{kind}\0{payload_hash}\n".encode("utf-8"))
    return digest.hexdigest()


class SkillSeamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "checkout"
        self.root.mkdir()
        self.destination = self.root.parent / "installed"
        self.destination.mkdir()
        self.output = self.root / DEFAULT.output

    def source(self, stem):
        path = self.root / DEFAULT.source_root / "notes" / f"{stem}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ndescription: A useful instruction.\nskill: true\n---\n\n"
            f"# {stem.title()}\n\nFollow the instruction.\n",
            encoding="utf-8",
        )
        return path

    def legacy(self, relative):
        path = self.root / "skills" / relative
        path.mkdir(parents=True, exist_ok=True)
        (path / "SKILL.md").write_bytes(b"Previous local instructions.\n")
        return path

    def test_config_defaults_validation_and_independent_overrides(self):
        self.assertIsNone(DEFAULT.generated_header)
        self.assertEqual(DEFAULT.legacy_owned_dirs, ())
        self.assertEqual(DEFAULT.legacy_retire_names, ())
        self.assertIs(DEFAULT.path_based_link_ownership, False)
        fields = (
            ("lock_name_override", "lock_name", ".demo-skills-build.lock", ".skills-build.lock"),
            ("lock_stage_prefix_override", "lock_stage_prefix", ".demo-skills-lock-", ".skills-lock-"),
            ("probe_stage_prefix_override", "probe_stage_prefix", ".demo-skills-probe-", ".skills-probe-"),
            ("build_stage_prefix_override", "build_stage_prefix", ".demo-skills-build-", ".skills-build-"),
        )
        for override, prop, default, configured in fields:
            with self.subTest(field=override):
                self.assertIsNone(getattr(DEFAULT, override))
                self.assertEqual(getattr(DEFAULT, prop), default)
                self.assertEqual(getattr(COMPAT, prop), configured)
                isolated = replace(DEFAULT, **{override: configured})
                for other, other_prop, other_default, _ in fields:
                    self.assertEqual(getattr(isolated, other_prop),
                                     configured if other == override else other_default)
                for invalid in ("", ".", "..", "a/b", "a\\b", "C:name", "a\nb", "a\0b", 3):
                    with self.assertRaisesRegex(ValueError, override):
                        replace(DEFAULT, **{override: invalid})
        self.assertEqual(COMPAT.marker, DEFAULT.marker)
        self.assertEqual(COMPAT.repo_link, DEFAULT.repo_link)
        self.assertEqual(COMPAT.lock_content, b"demo-skill-build-lock-v1\n")
        self.assertEqual(COMPAT.lock_content, DEFAULT.lock_content)
        self.assertEqual(COMPAT.install_stage_prefix, DEFAULT.install_stage_prefix)
        with self.assertRaises(TypeError):
            SkillConfig("demo-", Path("agent"), Path(".generated/skills"), "{source}")
        for invalid in ("", "no placeholder", "{source}{source}", "{source!r}",
                        "{source}/{}", "{source}\n", "{source}\x7f", 1):
            with self.subTest(header=invalid), self.assertRaisesRegex(ValueError, "generated_header"):
                replace(DEFAULT, generated_header=invalid)
        for invalid in ("", ".", "../skills", "a/../b", "/skills", "C:/skills", "a\\b",
                        "a\nb", "a\0b", None):
            with self.subTest(path=invalid), self.assertRaisesRegex(ValueError, "legacy_owned_dirs"):
                replace(DEFAULT, legacy_owned_dirs=(invalid,))
        for invalid in ("", ".", "..", "a/b", "a\\b", "a\nb", "a\0b", 1):
            with self.subTest(name=invalid), self.assertRaisesRegex(ValueError, "legacy_retire_names"):
                replace(DEFAULT, legacy_retire_names=(invalid,))
        for field in ("legacy_owned_dirs", "legacy_retire_names"):
            for invalid in ("skills", None, 3):
                with self.assertRaisesRegex(ValueError, field):
                    replace(DEFAULT, **{field: invalid})
        for invalid in (None, 1, "true"):
            with self.assertRaisesRegex(ValueError, "path_based_link_ownership"):
                replace(DEFAULT, path_based_link_ownership=invalid)
        normalized = replace(DEFAULT, legacy_owned_dirs=["old/skills"], legacy_retire_names=["old"])
        self.assertEqual(normalized.legacy_owned_dirs, (Path("old/skills"),))
        self.assertEqual(normalized.legacy_retire_names, ("old",))

    def test_header_exact_bytes_default_and_opt_in(self):
        source = self.source("alpha")
        doc = parse_document(self.root, source, DEFAULT)
        front = b'---\nname: demo-alpha\ndescription: "A useful instruction."\n---\n\n'
        body = b"# Alpha\n\nFollow the instruction.\n"
        header = b"<!-- Built from agent/notes/alpha.md; edit the source instead. -->\n\n"
        self.assertEqual(render_skill(doc, self.root).encode(), front + body)
        for config, expected in ((DEFAULT, front + body), (COMPAT, front + header + body),
                                 (DEFAULT, front + body)):
            with self.subTest(header=config.generated_header):
                build_packages(self.root, config)
                package = self.output / "demo-alpha"
                self.assertEqual((package / "SKILL.md").read_bytes(), expected)
                self.assertEqual((package / config.marker).read_bytes(), b"agent/notes/alpha.md\n")
                self.assertEqual(os.readlink(package / "repo"), "../../../")
                self.assertEqual(check_packages(self.root, config), [])
                self.assertEqual(build_packages(self.root, config), [])

    def test_lock_and_all_scratch_names_are_used_by_real_builder(self):
        self.source("alpha")
        for config in (DEFAULT, COMPAT):
            with self.subTest(config=config):
                with patch("otto.skills.builder.tempfile.mkstemp", wraps=tempfile.mkstemp) as lock_stage, \
                     patch("otto.skills.builder.tempfile.TemporaryDirectory",
                           wraps=tempfile.TemporaryDirectory) as directories:
                    build_packages(self.root, config)
                lock_stage.assert_called_once_with(prefix=config.lock_stage_prefix, dir=self.output.parent)
                self.assertEqual(
                    [(call.kwargs["prefix"], call.kwargs["dir"]) for call in directories.call_args_list],
                    [(config.probe_stage_prefix, self.output.parent),
                     (config.build_stage_prefix, self.output.parent)],
                )
                self.assertEqual((self.output.parent / config.lock_name).read_bytes(),
                                 b"demo-skill-build-lock-v1\n")
                self.assertEqual(check_packages(self.root, config), [])
        self.assertEqual({path.name for path in self.output.parent.iterdir()},
                         {"skills", ".demo-skills-build.lock", ".skills-build.lock"})

    def test_unprefixed_lock_contention_and_foreign_lock_fail_closed(self):
        self.source("alpha")
        build_packages(self.root, COMPAT)
        before = _tree_snapshot(self.output)
        lock = self.output.parent / ".skills-build.lock"
        with _build_lock(self.output.parent, COMPAT):
            with self.assertRaisesRegex(RuntimeError, "another skill build"):
                build_packages(self.root, COMPAT)
        self.assertEqual(_tree_snapshot(self.output), before)
        lock.write_bytes(b"foreign lock\n")
        with self.assertRaisesRegex(ValueError, "foreign skill build lock"):
            build_packages(self.root, COMPAT)
        self.assertEqual(lock.read_bytes(), b"foreign lock\n")
        self.assertEqual(_tree_snapshot(self.output), before)
        lock.unlink()
        build_packages(self.root, COMPAT)
        self.assertEqual(check_packages(self.root, COMPAT), [])

    def test_second_update_in_overridden_build_stage_keeps_live_tree(self):
        sources = [self.source(stem) for stem in ("alpha", "beta")]
        build_packages(self.root, COMPAT)
        before = _tree_snapshot(self.output)
        for source in sources:
            source.write_bytes(source.read_bytes() + b"\nChanged.\n")
        original_replace = os.replace
        writes = []

        def fail_second(src, dst):
            dst = Path(dst)
            if dst.name == "SKILL.md" and any(part.startswith(".skills-build-") for part in dst.parts):
                writes.append(dst.parent.name)
                if len(writes) == 2:
                    raise PermissionError("injected second staged update failure")
            return original_replace(src, dst)

        with patch("otto.skills.builder.os.replace", side_effect=fail_second):
            with self.assertRaisesRegex(PermissionError, "second staged update"):
                build_packages(self.root, COMPAT)
        self.assertEqual(writes, ["demo-alpha", "demo-beta"])
        self.assertEqual(_tree_snapshot(self.output), before)
        build_packages(self.root, COMPAT)
        self.assertEqual(check_packages(self.root, COMPAT), [])
        for name in ("demo-alpha", "demo-beta"):
            self.assertIn(b"Changed.", (self.output / name / "SKILL.md").read_bytes())

    def test_default_and_legacy_names_alone_do_not_relax_ownership(self):
        self.source("alpha")
        build_packages(self.root, DEFAULT)
        legacy = self.legacy("old/alpha")
        desired = self.destination / "demo-alpha"
        obsolete = self.destination / "old-start"
        inexact = self.destination / "demo-old"
        obsolete.symlink_to(legacy, target_is_directory=True)
        inexact.symlink_to(self.output / "no-such-package" / "nested", target_is_directory=True)
        desired.symlink_to(legacy, target_is_directory=True)
        configured_but_strict = replace(DEFAULT, legacy_owned_dirs=COMPAT.legacy_owned_dirs,
                                        legacy_retire_names=COMPAT.legacy_retire_names)
        for config in (DEFAULT, configured_but_strict):
            with self.subTest(config=config):
                before = _tree_snapshot(self.destination)
                with self.assertRaisesRegex(ValueError, "foreign symlink"):
                    install_packages(self.root, config, [self.destination])
                self.assertEqual(_tree_snapshot(self.destination), before)
        desired.unlink()
        for config in (DEFAULT, configured_but_strict):
            install_packages(self.root, config, [self.destination])
            self.assertEqual(obsolete.resolve(), legacy)
            self.assertTrue(inexact.is_symlink())
        self.assertEqual(desired.resolve(), self.output / "demo-alpha")

    def test_legacy_path_mode_retargets_and_retires_after_publication(self):
        self.source("alpha")
        build_packages(self.root, COMPAT)
        old = self.legacy("nested/alpha")
        desired = self.destination / "demo-alpha"
        desired.symlink_to(old, target_is_directory=True)
        common_source = self.legacy("references/common")
        obsolete = {
            "old-start": old,
            "common": common_source,
            "demo-obsolete": self.root / "skills" / "missing",
            "demo-inexact": self.output / "missing" / "nested",
            "demo-root": self.output,
        }
        for name, target in obsolete.items():
            (self.destination / name).symlink_to(target, target_is_directory=True)
        foreign = self.root.parent / "other"
        foreign.mkdir()
        keep = {
            "unlisted": old,
            "demo-foreign": foreign,
        }
        for name, target in keep.items():
            (self.destination / name).symlink_to(target, target_is_directory=True)
        before = _tree_snapshot(self.destination)
        dry = install_packages(self.root, COMPAT, [self.destination], dry_run=True)
        self.assertEqual(dry, [f"would-retarget {desired}"] +
                         [f"would-retire {self.destination / name}" for name in sorted(obsolete)])
        self.assertEqual(_tree_snapshot(self.destination), before)
        original_unlink = Path.unlink
        retired = []

        def observe(path, *args, **kwargs):
            if path.parent == self.destination and path.name in obsolete:
                self.assertEqual(desired.resolve(), self.output / "demo-alpha")
                self.assertTrue((desired / "SKILL.md").is_file())
                retired.append(path.name)
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", observe):
            actions = install_packages(self.root, COMPAT, [self.destination])
        self.assertEqual(retired, sorted(obsolete))
        self.assertEqual(actions, [f"retargeted {desired}"] +
                         [f"retired {self.destination / name}" for name in sorted(obsolete)])
        for name in obsolete:
            self.assertFalse((self.destination / name).is_symlink())
        for name, target in keep.items():
            self.assertEqual((self.destination / name).resolve(), target)
        self.assertEqual((old / "SKILL.md").read_bytes(), b"Previous local instructions.\n")
        self.assertEqual((common_source / "SKILL.md").read_bytes(), b"Previous local instructions.\n")
        self.assertEqual(install_packages(self.root, COMPAT, [self.destination]),
                         [f"already-linked {desired}"])

    def test_symlinked_checkout_is_resolved_but_legacy_root_alias_cannot_expand_ownership(self):
        self.source("alpha")
        build_packages(self.root, COMPAT)
        alias = self.root.parent / "checkout-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        old = self.legacy("nested/alpha")
        desired = self.destination / "demo-alpha"
        desired.symlink_to(alias / old.relative_to(self.root), target_is_directory=True)
        outside = self.root.parent / "foreign"
        outside.mkdir()
        escaped = outside / "alpha"
        escaped.mkdir()
        (self.root / "legacy-alias").symlink_to(outside, target_is_directory=True)
        (self.root / "skills" / "escape").symlink_to(outside, target_is_directory=True)
        foreign = self.destination / "demo-foreign"
        foreign.symlink_to(self.root / "skills" / "escape" / "alpha", target_is_directory=True)
        unprefixed = self.destination / "common"
        unprefixed.symlink_to(self.root / "legacy-alias" / "alpha", target_is_directory=True)
        config = replace(COMPAT, legacy_owned_dirs=(Path("skills"), Path("legacy-alias")))
        self.assertEqual(install_packages(alias, config, [self.destination]),
                         [f"retargeted {desired}"])
        self.assertEqual(desired.resolve(), self.output / "demo-alpha")
        self.assertEqual(foreign.resolve(), escaped)
        self.assertEqual(unprefixed.resolve(), escaped)

    def test_foreign_desired_symlink_blocks_all_destinations_in_dry_run_and_install(self):
        self.source("alpha")
        build_packages(self.root, COMPAT)
        old = self.legacy("alpha")
        obsolete = self.destination / "old-start"
        obsolete.symlink_to(old, target_is_directory=True)
        second = self.root.parent / "second"
        second.mkdir()
        foreign = self.root.parent / "outside"
        foreign.mkdir()
        conflict = second / "demo-alpha"
        raw = os.path.relpath(foreign, second)
        self.assertIn("..", Path(raw).parts)
        conflict.symlink_to(raw, target_is_directory=True)
        before = (_tree_snapshot(self.destination), _tree_snapshot(second))
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                with self.assertRaisesRegex(ValueError, "foreign symlink"):
                    install_packages(self.root, COMPAT, [self.destination, second], dry_run=dry_run)
                self.assertEqual((_tree_snapshot(self.destination), _tree_snapshot(second)), before)

    def test_partial_legacy_install_reports_completed_retarget_and_retries(self):
        for stem in ("alpha", "beta"):
            self.source(stem)
        build_packages(self.root, COMPAT)
        old = self.legacy("alpha")
        obsolete_source = self.legacy("entry")
        first = self.destination / "demo-alpha"
        second = self.destination / "demo-beta"
        obsolete = self.destination / "old-start"
        first.symlink_to(old, target_is_directory=True)
        obsolete.symlink_to(obsolete_source, target_is_directory=True)
        original_symlink = Path.symlink_to

        def fail_second(path, target, *args, **kwargs):
            if path == second:
                raise OSError(errno.EIO, "injected later publication failure")
            return original_symlink(path, target, *args, **kwargs)

        with patch.object(Path, "symlink_to", fail_second):
            with self.assertRaises(PartialInstallationError) as caught:
                install_packages(self.root, COMPAT, [self.destination])
        error = caught.exception
        self.assertEqual(error.completed_changes, (f"retargeted {first}",))
        self.assertEqual(error.failed_link, second)
        self.assertIn("partial skill installation: 1 changes completed", str(error))
        self.assertIn("retry skills install", str(error))
        self.assertEqual(first.resolve(), self.output / first.name)
        self.assertFalse(second.is_symlink())
        self.assertEqual(obsolete.resolve(), obsolete_source)
        self.assertEqual((old / "SKILL.md").read_bytes(), b"Previous local instructions.\n")
        self.assertEqual(install_packages(self.root, COMPAT, [self.destination]),
                         [f"already-linked {first}", f"linked {second}", f"retired {obsolete}"])
        self.assertFalse(obsolete.is_symlink())
        self.assertTrue((second / "SKILL.md").is_file())

    def test_failed_atomic_legacy_retarget_keeps_previous_link(self):
        self.source("alpha")
        build_packages(self.root, COMPAT)
        old = self.legacy("alpha")
        desired = self.destination / "demo-alpha"
        desired.symlink_to(old, target_is_directory=True)
        before = _tree_snapshot(self.destination)
        with patch("otto.skills.installer.os.replace", side_effect=OSError(errno.EIO, "injected")):
            with self.assertRaisesRegex(ValueError, "previous owned link was preserved") as caught:
                install_packages(self.root, COMPAT, [self.destination])
        self.assertNotIsInstance(caught.exception, PartialInstallationError)
        self.assertEqual(_tree_snapshot(self.destination), before)
        self.assertEqual((old / "SKILL.md").read_bytes(), b"Previous local instructions.\n")
        self.assertEqual(install_packages(self.root, COMPAT, [self.destination]),
                         [f"retargeted {desired}"])


class DefaultTreeGoldenTests(unittest.TestCase):
    def test_default_build_of_a_fixed_fixture_is_unchanged(self):
        config = SkillConfig("demo-", Path("agent"), Path(".generated/skills"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative, text in FIXED_DOCUMENTS.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            build_packages(root, config)
            self.assertEqual(check_packages(root, config), [])
            output = root / config.output
            entries = _tree_snapshot(output)
            self.assertEqual(set(entries), {
                entry for name in ("demo-alpha", "demo-beta")
                for entry in (name, f"{name}/SKILL.md", f"{name}/{config.marker}", f"{name}/repo")
            })
            self.assertEqual(entries["demo-alpha/repo"], ("L", b"../../../"))
            self.assertEqual(_tree_sha256(entries), EXPECTED_DEFAULT_TREE_SHA256)


if __name__ == "__main__":
    unittest.main()
