"""Focused installation safety tests for generated skill packages."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from otto.skills import SkillConfig
from otto.skills.builder import build_packages
from otto.skills.installer import install_packages

CONFIG = SkillConfig("astrid-dev-", Path("agent"), Path(".generated/skills"))


ROLE = """---
description: Lead work within the granted authority.
skill: true
---

# Leader

## Responsibility
Own the task.

## Authority
Follow the owner's grant.

## Responsibilities
Check the proof.

## Handoff
Report the result.
"""


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        role = self.root / "agent/roles/leader.md"
        role.parent.mkdir(parents=True)
        role.write_text(ROLE, encoding="utf-8")
        self.dest = self.root / "target/skills"
        self.dest.mkdir(parents=True)
        build_packages(self.root, CONFIG)

    def test_dry_run_is_inert_and_actual_install_is_idempotent(self):
        self.assertTrue(any("would-link" in x for x in
                            install_packages(self.root, CONFIG, [self.dest], dry_run=True)))
        self.assertEqual(list(self.dest.iterdir()), [])
        self.assertTrue(any("linked" in x for x in
                            install_packages(self.root, CONFIG, [self.dest])))
        link = self.dest / "astrid-dev-leader"
        self.assertTrue(link.is_symlink())
        self.assertTrue((link / "SKILL.md").is_file())
        self.assertTrue(any("already-linked" in x for x in
                            install_packages(self.root, CONFIG, [self.dest])))

    def test_retire_only_owned_symlinks(self):
        old = self.dest / "astrid-dev-old"
        old.symlink_to(self.root / CONFIG.output / "astrid-dev-old",
                       target_is_directory=True)
        foreign = self.dest / "elsewhere"
        foreign.symlink_to(self.root / "unrelated", target_is_directory=True)
        install_packages(self.root, CONFIG, [self.dest])
        self.assertFalse(old.is_symlink())
        self.assertTrue(foreign.is_symlink())

    def test_foreign_file_and_symlink_are_never_overwritten(self):
        file = self.dest / "astrid-dev-leader"
        file.write_text("foreign", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "foreign installation entry"):
            install_packages(self.root, CONFIG, [self.dest])
        self.assertEqual(file.read_text(), "foreign")
        file.unlink()
        file.symlink_to(self.root / "another-tool")
        with self.assertRaisesRegex(ValueError, "foreign symlink"):
            install_packages(self.root, CONFIG, [self.dest])
        self.assertTrue(file.is_symlink())

    def test_foreign_desired_entry_does_not_retire_existing_owned_link(self):
        old = self.dest / "astrid-dev-old"
        old.symlink_to(self.root / CONFIG.output / "astrid-dev-old")
        conflict = self.dest / "astrid-dev-leader"
        conflict.write_text("foreign", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "foreign installation entry"):
            install_packages(self.root, CONFIG, [self.dest])
        self.assertTrue(old.is_symlink())
        self.assertEqual(conflict.read_text(), "foreign")

    def test_later_destination_foreign_collision_preserves_earlier_destinations(self):
        old = self.dest / "astrid-dev-old"
        old.symlink_to(self.root / CONFIG.output / "astrid-dev-old")
        second = self.root / "second/skills"
        second.mkdir(parents=True)
        conflict = second / "astrid-dev-leader"
        conflict.write_text("foreign", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "foreign installation entry"):
            install_packages(self.root, CONFIG, [self.dest, second])
        self.assertTrue(old.is_symlink())
        self.assertFalse((self.dest / "astrid-dev-leader").exists())
        self.assertEqual(conflict.read_text(), "foreign")

    def test_missing_destination_is_refused(self):
        with self.assertRaisesRegex(ValueError, "must already be a real directory"):
            install_packages(self.root, CONFIG, [self.root / "not-created"])

    def test_flag_removed_retires_owned_install_after_rebuild(self):
        install_packages(self.root, CONFIG, [self.dest])
        role = self.root / "agent/roles/leader.md"
        role.write_text(ROLE.replace("skill: true\n", ""), encoding="utf-8")
        build_packages(self.root, CONFIG)
        self.assertTrue(any("retired" in x for x in
                            install_packages(self.root, CONFIG, [self.dest])))
        self.assertFalse((self.dest / "astrid-dev-leader").is_symlink())


    def test_obsolete_prefixed_foreign_symlink_is_not_retired(self):
        with TemporaryDirectory() as directory:
            outside = Path(directory)
            foreign = self.dest / "astrid-dev-obsolete"
            foreign.symlink_to(outside, target_is_directory=True)
            raw = foreign.readlink()

            install_packages(self.root, CONFIG, [self.dest])

            self.assertTrue(foreign.is_symlink())
            self.assertEqual(foreign.readlink(), raw)
            self.assertEqual(foreign.resolve(), outside.resolve())
            self.assertTrue((self.dest / "astrid-dev-leader/SKILL.md").is_file())

    def test_relative_traversal_foreign_desired_symlink_blocks_retirement(self):
        from os.path import relpath

        old = self.dest / "astrid-dev-old"
        old.symlink_to(self.root / CONFIG.output / "astrid-dev-old")
        with TemporaryDirectory() as directory:
            outside = Path(directory)
            raw = Path(relpath(outside, self.dest))
            self.assertIn("..", raw.parts)
            desired = self.dest / "astrid-dev-leader"
            desired.symlink_to(raw, target_is_directory=True)
            before = {p.name: p.readlink() for p in self.dest.iterdir()}

            with self.assertRaisesRegex(ValueError, "foreign symlink"):
                install_packages(self.root, CONFIG, [self.dest])

            self.assertEqual({p.name: p.readlink() for p in self.dest.iterdir()}, before)
            self.assertEqual(desired.resolve(), outside.resolve())

    def test_missing_generated_manifest_refuses_before_link_mutation(self):
        install_packages(self.root, CONFIG, [self.dest])
        old = self.dest / "astrid-dev-old"
        old.symlink_to(self.root / CONFIG.output / "astrid-dev-old")
        before = {p.name: p.readlink() for p in self.dest.iterdir()}
        skill = self.root / ".generated/skills/astrid-dev-leader/SKILL.md"
        skill.unlink()

        with self.assertRaisesRegex(ValueError, r"build/check skills before installing: .*SKILL\.md"):
            install_packages(self.root, CONFIG, [self.dest])

        self.assertEqual({p.name: p.readlink() for p in self.dest.iterdir()}, before)
        self.assertFalse(skill.exists())

    def test_unexpected_generated_output_package_blocks_link_mutation(self):
        install_packages(self.root, CONFIG, [self.dest])
        old = self.dest / "astrid-dev-old"
        old.symlink_to(self.root / CONFIG.output / "astrid-dev-old")
        before = {p.name: p.readlink() for p in self.dest.iterdir()}
        extra = self.root / ".generated/skills/astrid-dev-extra"
        extra.mkdir()
        (extra / "SKILL.md").write_text("unmanaged extra", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "generated skill names differ"):
            install_packages(self.root, CONFIG, [self.dest])

        self.assertEqual({p.name: p.readlink() for p in self.dest.iterdir()}, before)
        self.assertEqual((extra / "SKILL.md").read_text(encoding="utf-8"), "unmanaged extra")

    def test_symlinked_destination_alias_is_refused_before_mutation(self):
        old = self.dest / "astrid-dev-old"
        old.symlink_to(self.root / CONFIG.output / "astrid-dev-old")
        before = {p.name: p.readlink() for p in self.dest.iterdir()}
        alias = self.root / "destination-alias"
        alias.symlink_to(self.dest, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "destination must already be a real directory"):
            install_packages(self.root, CONFIG, [alias])

        self.assertEqual({p.name: p.readlink() for p in self.dest.iterdir()}, before)
        self.assertEqual(alias.readlink(), self.dest)

    def test_generated_manifest_drift_refuses_before_link_mutation(self):
        install_packages(self.root, CONFIG, [self.dest])
        old = self.dest / "astrid-dev-old"
        old.symlink_to(self.root / CONFIG.output / "astrid-dev-old")
        before = {p.name: p.readlink() for p in self.dest.iterdir()}
        skill = self.root / ".generated/skills/astrid-dev-leader/SKILL.md"
        tampered = skill.read_bytes() + b"\nUnapproved local change.\n"
        skill.write_bytes(tampered)

        with self.assertRaisesRegex(ValueError, r"astrid-dev-leader: generated SKILL\.md is stale"):
            install_packages(self.root, CONFIG, [self.dest])

        self.assertEqual({p.name: p.readlink() for p in self.dest.iterdir()}, before)
        self.assertEqual(skill.read_bytes(), tampered)

    def test_foreign_collision_dry_run_and_install_leave_whole_destination_unchanged(self):
        unrelated = self.dest / "user-file"
        unrelated.write_bytes(b"user bytes\n")
        desired = self.dest / "astrid-dev-leader"
        desired.write_bytes(b"foreign bytes\n")

        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run, kind="file"):
                with self.assertRaisesRegex(ValueError, "foreign installation entry"):
                    install_packages(self.root, CONFIG, [self.dest], dry_run=dry_run)
                self.assertEqual({p.name: p.read_bytes() for p in self.dest.iterdir()},
                                 {"user-file": b"user bytes\n", desired.name: b"foreign bytes\n"})

        desired.unlink()
        desired.symlink_to(self.root / "another-repository", target_is_directory=True)
        raw = desired.readlink()
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run, kind="symlink"):
                with self.assertRaisesRegex(ValueError, "foreign symlink"):
                    install_packages(self.root, CONFIG, [self.dest], dry_run=dry_run)
                self.assertEqual({p.name for p in self.dest.iterdir()}, {unrelated.name, desired.name})
                self.assertEqual(unrelated.read_bytes(), b"user bytes\n")
                self.assertEqual(desired.readlink(), raw)



if __name__ == "__main__":
    unittest.main()
