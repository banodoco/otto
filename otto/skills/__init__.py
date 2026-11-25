"""Configuration for Markdown document skill packaging."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class SkillConfig:
    """One workspace's skill namespace and checkout-relative source/output paths."""

    namespace: str
    source_root: Path
    output: Path

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*-", self.namespace):
            raise ValueError("skill namespace must be lowercase kebab-case with a trailing hyphen")
        for name in ("source_root", "output"):
            path = Path(getattr(self, name))
            if (path.is_absolute() or not path.parts or ".." in path.parts
                    or any(c in path.as_posix() for c in "\\\r\n")):
                raise ValueError(f"{name} must be a nonempty checkout-relative path")
            object.__setattr__(self, name, path)

    @property
    def marker(self) -> str:
        return f".{self.namespace}generated"

    @property
    def lock_name(self) -> str:
        return f".{self.namespace}skills-build.lock"

    @property
    def lock_content(self) -> bytes:
        return f"{self.namespace}skill-build-lock-v1\n".encode("ascii")

    @property
    def lock_stage_prefix(self) -> str:
        return f".{self.namespace}skills-lock-"

    @property
    def probe_stage_prefix(self) -> str:
        return f".{self.namespace}skills-probe-"

    @property
    def build_stage_prefix(self) -> str:
        return f".{self.namespace}skills-build-"

    @property
    def install_stage_prefix(self) -> str:
        return f".{self.namespace}stage-"

    @property
    def repo_link(self) -> str:
        return "../" * (len(self.output.parts) + 1)
