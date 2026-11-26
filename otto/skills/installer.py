"""Install only owned generated skill packages into agent skill roots."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

from . import SkillConfig
from .builder import _assert_package_dir, check_packages


class CommittedRetargetCleanupError(ValueError):
    """Retarget succeeded; the cleanup failure occurred after publication."""


class PartialInstallationError(ValueError):
    """A later failure left earlier owned link changes installed.

    The completed list contains only operations that actually returned
    successfully. This records a retryable partial state, not a transaction.
    """

    def __init__(self, completed_changes: list[str], failed_link: Path, cause: Exception):
        self.completed_changes = tuple(completed_changes)
        self.failed_link = failed_link
        changed = "; ".join(completed_changes)
        super().__init__(
            f"partial skill installation: {len(completed_changes)} changes completed "
            f"before failure at {failed_link}: {cause}; "
            f"completed links: {changed}; "
            "inspect the destinations and retry skills install"
        )


def default_destinations() -> list[Path]:
    home = Path.home()
    return [path for path in (home / ".claude/skills", home / ".codex/skills",
                              home / ".agents/skills") if path.is_dir() and not path.is_symlink()]


def _target_of(link: Path) -> Path:
    raw = Path(os.readlink(link))
    return (raw if raw.is_absolute() else link.parent / raw).resolve()


def _owned_link(link: Path, root: Path, config: SkillConfig) -> bool:
    if not link.is_symlink():
        return False
    if not config.path_based_link_ownership and not link.name.startswith(config.namespace):
        return False
    target = _target_of(link)
    output = root / config.output
    if config.path_based_link_ownership:
        # root and the target are resolved by the caller and _target_of.
        # Do not resolve legacy roots: a symlinked root must not grant
        # ownership of a target outside the checkout.
        return (target.is_relative_to(output)
                or any(target.is_relative_to(root / path) for path in config.legacy_owned_dirs))
    if target.parent != output or not target.name.startswith(config.namespace):
        return False
    if not target.exists():
        # A retired generated package has no marker left to inspect. Only
        # its exact namespace-qualified former target proves ownership.
        return target == output / link.name
    try:
        _assert_package_dir(target, config, stale=True)
    except (OSError, UnicodeError, ValueError):
        return False
    return True


def _identity(path: Path) -> tuple | None:
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_mode,
            os.readlink(path) if path.is_symlink() else None)


def _retarget_owned_link(link: Path, source: Path, expected_identity: tuple,
                         config: SkillConfig) -> None:
    """Prepare the new symlink first and replace one owned link in one operation.

    Failure to create the staged symlink or replace the destination preserves
    the old symlink. This is per-entry only: the entire install set is not a
    transaction, and an uncooperative writer can still race after preflight.
    """
    replaced = False
    try:
        # The private same-filesystem directory ensures staging cannot replace
        # an unrelated entry and is normally removed on success or failure.
        with tempfile.TemporaryDirectory(prefix=config.install_stage_prefix, dir=link.parent) as tmp:
            staged = Path(tmp) / "package"
            staged.symlink_to(source, target_is_directory=True)
            # Preflight and the per-item check ran before staging. Recheck
            # after staging too, so an intervening foreign replacement is not
            # silently overwritten by our atomic publication. This does not
            # eliminate a hostile race between this check and os.replace.
            if _identity(link) != expected_identity:
                raise ValueError(f"installation entry changed during staged retarget: {link}")
            os.replace(staged, link)
            replaced = True
    except OSError as exc:
        if replaced:
            # TemporaryDirectory cleanup may fail AFTER os.replace committed.
            # Do not claim the old link survived; report the actual new target.
            raise CommittedRetargetCleanupError(
                f"retargeted skill directory symlink {link}, but staging cleanup failed: "
                f"{exc}; the new link is installed"
            ) from exc
        raise ValueError(
            f"could not retarget skill directory symlink {link}: {exc}; "
            "the previous owned link was preserved"
        ) from exc


def install_packages(root: Path, config: SkillConfig, destinations: list[Path] | None = None,
                     *, dry_run: bool = False) -> list[str]:
    """Link named packages; never replace other repositories' files or links.

    By default only this workspace's marked packages and exact former
    generated targets are owned. A workspace can opt into path-based legacy
    ownership and explicitly named retirement candidates. This is not a
    general cleanup tool.
    """
    root = Path(root).resolve()
    failures = check_packages(root, config)
    if failures:
        raise ValueError("build/check skills before installing: " + "; ".join(failures))
    package_root = root / config.output
    desired = {
        path.name: path for path in package_root.iterdir()
        if path.is_dir() and not path.is_symlink()
    }
    explicit = destinations is not None
    targets = list(destinations) if explicit else default_destinations()
    if not targets:
        raise ValueError("no installed skill destinations found; pass --destination")
    planned = []
    target_identities = {}
    for target in targets:
        target = Path(target).expanduser()
        if target.is_symlink() or not target.is_dir():
            raise ValueError(f"destination must already be a real directory: {target}")
        canonical = target.resolve()
        if canonical in target_identities:
            raise ValueError(f"duplicate skill destination: {target}")
        target_identities[canonical] = (target, _identity(target))
        for item in sorted(target.iterdir()):
            if (item.name in desired or (not item.name.startswith(config.namespace)
                                        and item.name not in config.legacy_retire_names)):
                continue
            if _owned_link(item, root, config):
                planned.append(("retire", item, None, _identity(item)))
        for name, source in sorted(desired.items()):
            link = target / name
            if link.is_symlink():
                if _target_of(link) == source.resolve():
                    planned.append(("already", link, source, _identity(link)))
                    continue
                if not _owned_link(link, root, config):
                    raise ValueError(f"foreign symlink, leaving untouched: {link}")
                planned.append(("retarget", link, source, _identity(link)))
            elif link.exists():
                raise ValueError(f"foreign installation entry, leaving untouched: {link}")
            else:
                planned.append(("link", link, source, None))
    # Inspect every destination before mutating any; recheck each entry just
    # before use. Unexpected concurrent changes still cannot be made atomic.
    for target, identity in target_identities.values():
        if _identity(target) != identity:
            raise ValueError(f"destination changed during preflight: {target}")
    for _, link, _, identity in planned:
        if _identity(link) != identity:
            raise ValueError(f"installation entry changed during preflight: {link}")
    # Publish/retarget requested packages before retiring obsolete names. If
    # adding a new skill fails, legacy entry points remain available.
    planned.sort(key=lambda entry: entry[0] == "retire")
    actions = []
    completed_changes = []
    for operation, link, source, identity in planned:
        try:
            target_identity = next(identity for target, identity in target_identities.values()
                                   if target == link.parent)
            if _identity(link.parent) != target_identity:
                raise ValueError(f"destination changed during installation: {link.parent}")
            if _identity(link) != identity:
                raise ValueError(f"installation entry changed during preflight: {link}")
            if operation == "already":
                actions.append(f"already-linked {link}")
                continue
            status = {"retire": "retired", "retarget": "retargeted", "link": "linked"}
            label = f"{'would-' + operation if dry_run else status[operation]} {link}"
            if dry_run:
                actions.append(label)
                continue
            if operation == "retire":
                link.unlink()
            elif operation == "retarget":
                _retarget_owned_link(link, source, identity, config)
            elif operation == "link":
                try:
                    link.symlink_to(source, target_is_directory=True)
                except OSError as exc:
                    raise ValueError(
                        f"could not create skill directory symlink {link}: {exc}; "
                        "confirm link privileges on this platform"
                    ) from exc
            # Count an operation only after it actually returned successfully.
            actions.append(label)
            completed_changes.append(label)
        except (OSError, ValueError) as exc:
            if not dry_run and isinstance(exc, CommittedRetargetCleanupError):
                # The replace already committed. Include this entry in the
                # actual mutation list instead of under-reporting progress.
                completed_changes.append(label)
            if not dry_run and completed_changes:
                raise PartialInstallationError(completed_changes, link, exc) from exc
            raise
    return actions
