"""Namespace separation, ownership and publication failure fixtures."""
from pathlib import Path
from tempfile import TemporaryDirectory
import errno
import os
import unittest
from unittest.mock import patch

from otto.skills import SkillConfig
from otto.skills.builder import build_packages, check_packages
from otto.skills.installer import install_packages, PartialInstallationError


SOURCE = """---
description: Start an independently useful assignment.
skill: true
---

# Start

Begin with the accepted task.
"""


class NamespaceOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.dest = self.root / "installed"
        self.dest.mkdir()
        self.first = SkillConfig("alpha-", Path("guidance/alpha"), Path(".generated/alpha/skills"))
        # Deliberately overlapping prefixes and one destination; a prefix
        # alone must not let the first workspace retire the second's links.
        self.second = SkillConfig("alpha-tools-", Path("guidance/other"), Path(".generated/other/skills"))
        self.write_source(self.first, "start")
        build_packages(self.root, self.first)

    def write_source(self, config, stem, text=SOURCE):
        path = self.root / config.source_root / f"{stem}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def package(self, config, stem):
        return self.root / config.output / (config.namespace + stem)

    def test_two_namespaces_share_destination_and_retire_independently(self):
        self.write_source(self.second, "start")
        build_packages(self.root, self.second)
        self.assertEqual(check_packages(self.root, self.first), [])
        self.assertEqual(check_packages(self.root, self.second), [])
        for config in (self.first, self.second):
            install_packages(self.root, config, [self.dest])
            package = self.package(config, "start")
            self.assertEqual((package / config.marker).read_text(encoding="utf-8"),
                             (config.source_root / "start.md").as_posix() + "\n")
            self.assertEqual(os.readlink(package / "repo"), "../../../../")
            self.assertEqual((package / "repo").resolve(), self.root)
            self.assertIn(f"name: {config.namespace}start", (package / "SKILL.md").read_text())
        self.assertNotEqual(self.first.lock_name, self.second.lock_name)
        first_link = self.dest / "alpha-start"
        second_link = self.dest / "alpha-tools-start"
        self.assertEqual({p.name for p in self.dest.iterdir()}, {first_link.name, second_link.name})

        for retiring, survivor in ((self.first, self.second), (self.second, self.first)):
            with self.subTest(retiring=retiring.namespace):
                self.write_source(retiring, "start", SOURCE.replace("skill: true\n", ""))
                build_packages(self.root, retiring)
                survivor_link = self.dest / (survivor.namespace + "start")
                survivor_raw = survivor_link.readlink()
                survivor_manifest = (survivor_link / "SKILL.md").read_bytes()
                retired_link = self.dest / (retiring.namespace + "start")
                self.assertTrue(retired_link.is_symlink())
                self.assertFalse(retired_link.exists())
                self.assertIn(f"retired {retired_link}",
                              install_packages(self.root, retiring, [self.dest]))
                self.assertFalse(retired_link.is_symlink())
                self.assertEqual(survivor_link.readlink(), survivor_raw)
                self.assertEqual((survivor_link / "SKILL.md").read_bytes(), survivor_manifest)
                self.assertEqual(check_packages(self.root, survivor), [])
                self.write_source(retiring, "start")
                build_packages(self.root, retiring)
                install_packages(self.root, retiring, [self.dest])
                self.assertTrue((retired_link / "SKILL.md").is_file())

    def test_foreign_marker_refuses_build_and_install_without_mutation(self):
        install_packages(self.root, self.first, [self.dest])
        package = self.package(self.first, "start")
        marker = package / self.first.marker
        foreign = package / self.second.marker
        marker.rename(foreign)
        original = foreign.read_bytes()
        skill = (package / "SKILL.md").read_bytes()
        link = self.dest / "alpha-start"
        raw = link.readlink()

        self.assertTrue(any("refusing unmanaged generated package" in error
                            for error in check_packages(self.root, self.first)))
        with self.assertRaisesRegex(ValueError, "refusing unmanaged generated package"):
            build_packages(self.root, self.first)
        with self.assertRaisesRegex(ValueError, "build/check skills before installing"):
            install_packages(self.root, self.first, [self.dest])
        self.assertEqual(foreign.read_bytes(), original)
        self.assertEqual((package / "SKILL.md").read_bytes(), skill)
        self.assertFalse(marker.exists())
        self.assertEqual(link.readlink(), raw)

    def test_unmarked_legacy_links_and_inexact_dangling_links_are_not_owned(self):
        old = self.root / "skills" / "alpha-obsolete"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text("foreign instructions\n")
        obsolete = self.dest / "alpha-obsolete"
        obsolete.symlink_to(old)
        mismatch = self.dest / "alpha-mismatch"
        mismatch.symlink_to(self.package(self.first, "not-mismatch"))
        exact = self.dest / "alpha-gone"
        exact.symlink_to(self.package(self.first, "gone"))
        result = install_packages(self.root, self.first, [self.dest])
        self.assertIn(f"retired {exact}", result)
        self.assertFalse(exact.is_symlink())
        self.assertEqual(obsolete.resolve(), old.resolve())
        self.assertTrue(mismatch.is_symlink())
        self.assertEqual(mismatch.readlink(), self.package(self.first, "not-mismatch"))
        desired = self.dest / "alpha-start"
        desired.unlink()
        desired.symlink_to(old)
        with self.assertRaisesRegex(ValueError, "foreign symlink"):
            install_packages(self.root, self.first, [self.dest])
        self.assertEqual(desired.readlink(), old)
        self.assertEqual((old / "SKILL.md").read_text(), "foreign instructions\n")

    def prepare_retarget(self, dest=None):
        if dest is None:
            dest = self.dest
        self.write_source(self.first, "worker", SOURCE.replace("# Start", "# Worker"))
        build_packages(self.root, self.first)
        old = self.package(self.first, "worker")
        link = dest / "alpha-start"
        link.symlink_to(old, target_is_directory=True)
        return link, old

    def test_owned_marked_retarget_preserves_target_and_uses_namespace_staging(self):
        link, old = self.prepare_retarget()
        old_bytes = (old / "SKILL.md").read_bytes()
        with patch("otto.skills.installer.tempfile.TemporaryDirectory",
                   wraps=TemporaryDirectory) as staged:
            result = install_packages(self.root, self.first, [self.dest])
        staged.assert_called_once_with(prefix=".alpha-stage-", dir=self.dest)
        self.assertEqual(result, [f"retargeted {link}", f"linked {self.dest / 'alpha-worker'}"])
        self.assertEqual(link.resolve(), self.package(self.first, "start"))
        self.assertEqual((old / "SKILL.md").read_bytes(), old_bytes)
        self.assertEqual((self.dest / "alpha-worker").resolve(), old)

    def test_staging_and_atomic_retarget_failures_preserve_previous_owned_link(self):
        link, old = self.prepare_retarget()
        previous = link.readlink()
        old_bytes = (old / "SKILL.md").read_bytes()
        for operation in ("stage", "replace"):
            with self.subTest(operation=operation):
                failure = OSError(errno.EIO, "injected")
                context = (patch.object(Path, "symlink_to", side_effect=failure)
                           if operation == "stage"
                           else patch("otto.skills.installer.os.replace", side_effect=failure))
                with context:
                    with self.assertRaisesRegex(ValueError, "previous owned link was preserved") as caught:
                        install_packages(self.root, self.first, [self.dest])
                self.assertNotIsInstance(caught.exception, PartialInstallationError)
                self.assertEqual(link.readlink(), previous)
                self.assertEqual((link / "SKILL.md").read_bytes(), old_bytes)
                self.assertEqual(list(self.dest.iterdir()), [link])
        self.assertIn(f"retargeted {link}", install_packages(self.root, self.first, [self.dest]))

    def test_retarget_cleanup_failure_reports_committed_change_and_retry(self):
        link, old = self.prepare_retarget()

        class FailAfterCleanup:
            def __init__(self, *args, **kwargs):
                self.inner = TemporaryDirectory(*args, **kwargs)

            def __enter__(self):
                return self.inner.__enter__()

            def __exit__(self, *args):
                self.inner.__exit__(*args)
                raise OSError(errno.EIO, "injected post-commit cleanup failure")

        with patch("otto.skills.installer.tempfile.TemporaryDirectory", FailAfterCleanup):
            with self.assertRaises(PartialInstallationError) as caught:
                install_packages(self.root, self.first, [self.dest])
        error = caught.exception
        self.assertIn("new link is installed", str(error))
        self.assertEqual(error.completed_changes, (f"retargeted {link}",))
        self.assertEqual(error.failed_link, link)
        self.assertEqual(link.resolve(), self.package(self.first, "start"))
        self.assertNotEqual(link.resolve(), old)
        self.assertTrue((link / "SKILL.md").is_file())
        self.assertEqual(list(self.dest.iterdir()), [link])
        self.assertIn(f"already-linked {link}", install_packages(self.root, self.first, [self.dest]))

    def test_foreign_replacement_during_retarget_staging_is_not_overwritten(self):
        link, _ = self.prepare_retarget()
        foreign = self.root / "foreign"
        foreign.mkdir()
        (foreign / "SKILL.md").write_text("foreign instructions\n")
        original_symlink = Path.symlink_to
        destination = self.dest

        def inject(path, target, *args, **kwargs):
            result = original_symlink(path, target, *args, **kwargs)
            if path.name == "package" and path.parent.parent == destination:
                link.unlink()
                original_symlink(link, foreign, target_is_directory=True)
            return result

        with patch.object(Path, "symlink_to", inject):
            with self.assertRaisesRegex(ValueError, "changed during staged retarget"):
                install_packages(self.root, self.first, [self.dest])
        self.assertEqual(link.resolve(), foreign)
        self.assertEqual((link / "SKILL.md").read_text(), "foreign instructions\n")
        self.assertEqual(list(self.dest.iterdir()), [link])
        with self.assertRaisesRegex(ValueError, "foreign symlink"):
            install_packages(self.root, self.first, [self.dest])
        self.assertEqual(link.resolve(), foreign)

    def test_partial_install_reports_only_published_changes_and_keeps_stale_link(self):
        self.write_source(self.first, "worker", SOURCE.replace("# Start", "# Worker"))
        build_packages(self.root, self.first)
        obsolete = self.dest / "alpha-gone"
        obsolete.symlink_to(self.package(self.first, "gone"))
        start = self.dest / "alpha-start"
        worker = self.dest / "alpha-worker"
        original_symlink = Path.symlink_to

        def fail_worker(path, target, *args, **kwargs):
            if path == worker:
                raise OSError(errno.EIO, "injected later failure")
            return original_symlink(path, target, *args, **kwargs)

        with patch.object(Path, "symlink_to", fail_worker):
            with self.assertRaises(PartialInstallationError) as caught:
                install_packages(self.root, self.first, [self.dest])
        self.assertEqual(caught.exception.failed_link, worker)
        self.assertEqual(caught.exception.completed_changes, (f"linked {start}",))
        self.assertIn("retry skills install", str(caught.exception))
        self.assertTrue((start / "SKILL.md").is_file())
        self.assertFalse(worker.is_symlink())
        self.assertTrue(obsolete.is_symlink())
        result = install_packages(self.root, self.first, [self.dest])
        self.assertEqual(result, [f"already-linked {start}", f"linked {worker}", f"retired {obsolete}"])
        self.assertFalse(obsolete.is_symlink())
        self.assertTrue((worker / "SKILL.md").is_file())

    def test_later_destination_failure_reports_earlier_changes_and_retry(self):
        second = self.root / "second-install"
        second.mkdir()
        link, old = self.prepare_retarget(second)
        first_start = self.dest / "alpha-start"
        first_worker = self.dest / "alpha-worker"
        original_replace = os.replace

        def fail_second(source, target):
            if target == link:
                raise OSError(errno.EIO, "injected second-destination failure")
            return original_replace(source, target)

        with patch("otto.skills.installer.os.replace", side_effect=fail_second):
            with self.assertRaises(PartialInstallationError) as caught:
                install_packages(self.root, self.first, [self.dest, second])
        self.assertEqual(caught.exception.failed_link, link)
        self.assertEqual(caught.exception.completed_changes,
                         (f"linked {first_start}", f"linked {first_worker}"))
        self.assertEqual(link.resolve(), old)
        self.assertTrue((first_start / "SKILL.md").is_file())
        self.assertTrue((first_worker / "SKILL.md").is_file())
        self.assertIn(f"retargeted {link}",
                      install_packages(self.root, self.first, [self.dest, second]))
        self.assertEqual(link.resolve(), self.package(self.first, "start"))


if __name__ == "__main__":
    unittest.main()
