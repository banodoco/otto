"""Configuration for Markdown document skill packaging."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


def _single_name(value: str, field_name: str) -> str:
    if (not isinstance(value, str) or not value or value in (".", "..")
            or not value.isprintable() or any(char in value for char in '/\\:<>"|?*')):
        raise ValueError(f"{field_name} must be a nonempty portable filename or prefix")
    return value


def _legacy_path(value: Path) -> Path:
    try:
        path = Path(value)
    except TypeError as exc:
        raise ValueError("legacy_owned_dirs entries must be checkout-relative paths") from exc
    if (path.is_absolute() or not path.parts or ".." in path.parts
            or not path.as_posix().isprintable()
            or any(char in path.as_posix() for char in "\\:")):
        raise ValueError("legacy_owned_dirs entries must be nonempty checkout-relative paths")
    return path


@dataclass(frozen=True)
class SkillConfig:
    """One workspace's skill namespace and checkout-relative source/output paths."""

    namespace: str
    source_root: Path
    output: Path

    # Compatibility settings are opt-in; the normal namespace rules stay strict.
    generated_header: str | None = field(default=None, kw_only=True)
    lock_name_override: str | None = field(default=None, kw_only=True)
    lock_stage_prefix_override: str | None = field(default=None, kw_only=True)
    probe_stage_prefix_override: str | None = field(default=None, kw_only=True)
    build_stage_prefix_override: str | None = field(default=None, kw_only=True)
    legacy_owned_dirs: tuple[Path, ...] = field(default=(), kw_only=True)
    legacy_retire_names: tuple[str, ...] = field(default=(), kw_only=True)
    path_based_link_ownership: bool = field(default=False, kw_only=True)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*-", self.namespace):
            raise ValueError("skill namespace must be lowercase kebab-case with a trailing hyphen")
        for name in ("source_root", "output"):
            path = Path(getattr(self, name))
            if (path.is_absolute() or not path.parts or ".." in path.parts
                    or any(c in path.as_posix() for c in "\\\r\n")):
                raise ValueError(f"{name} must be a nonempty checkout-relative path")
            object.__setattr__(self, name, path)
        header = self.generated_header
        if header is not None:
            if (not isinstance(header, str) or not header.isprintable()
                    or header.count("{source}") != 1
                    or any(c in header.replace("{source}", "") for c in "{}")):
                raise ValueError("generated_header must be one printable line with exactly one {source} placeholder")
        for name in ("lock_name_override", "lock_stage_prefix_override",
                     "probe_stage_prefix_override", "build_stage_prefix_override"):
            value = getattr(self, name)
            if value is not None:
                _single_name(value, name)
        for name, normalize in (("legacy_owned_dirs", _legacy_path),
                                ("legacy_retire_names", lambda value: _single_name(value, "legacy_retire_names"))):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)):
                raise ValueError(f"{name} must be a sequence of entries")
            object.__setattr__(self, name, tuple(normalize(value) for value in values))
        if not isinstance(self.path_based_link_ownership, bool):
            raise ValueError("path_based_link_ownership must be a bool")

    @property
    def marker(self) -> str:
        return f".{self.namespace}generated"

    @property
    def lock_name(self) -> str:
        return self.lock_name_override or f".{self.namespace}skills-build.lock"

    @property
    def lock_content(self) -> bytes:
        return f"{self.namespace}skill-build-lock-v1\n".encode("ascii")

    @property
    def lock_stage_prefix(self) -> str:
        return self.lock_stage_prefix_override or f".{self.namespace}skills-lock-"

    @property
    def probe_stage_prefix(self) -> str:
        return self.probe_stage_prefix_override or f".{self.namespace}skills-probe-"

    @property
    def build_stage_prefix(self) -> str:
        return self.build_stage_prefix_override or f".{self.namespace}skills-build-"

    @property
    def install_stage_prefix(self) -> str:
        return f".{self.namespace}stage-"

    @property
    def repo_link(self) -> str:
        return "../" * (len(self.output.parts) + 1)
