"""Generic Git record readers."""
from __future__ import annotations

import subprocess
from pathlib import Path


def git_result(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run Git in a repository and retain its status, stdout and stderr."""
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)


def git_output(root: Path, *args: str) -> str:
    """Run Git with check_output-style failure behavior."""
    return subprocess.check_output(["git", *args], cwd=root, text=True)


def git_show(root: Path, revision: str, path: str, *, missing: str = "error") -> str | None:
    """Read a Git blob; `missing='none'` deliberately collapses every failed show."""
    result = git_result(root, "show", f"{revision}:{path}")
    if result.returncode:
        if missing == "none":
            return None
        if missing != "error":
            raise ValueError(f"unknown missing-git-blob policy: {missing}")
        raise ValueError(result.stderr.strip())
    return result.stdout
