"""Small reusable Markdown structure rules, independent of document purpose.

Callers own their section names, allowed fields, and any semantic rules.
The helpers enforce shape and order; they do not judge the quality of prose.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Pattern


def _heading_spans(text: str, level: int) -> list[tuple[str, int, int]]:
    """Find real Markdown headings, not examples inside backtick/tilde fences."""
    if level < 1 or level > 6:
        raise ValueError("heading level must be 1..6")
    found: list[tuple[str, int, int]] = []
    fence: str | None = None
    fence_size = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        plain = line.rstrip("\r\n")
        if fence is not None:
            if re.fullmatch(r"[ ]{0,3}" + re.escape(fence) + "{" + str(fence_size) + r",}[ \t]*", plain):
                fence, fence_size = None, 0
        else:
            opening = re.match(r"^[ ]{0,3}(" + re.escape(chr(96)) + r"{3,}|~{3,})", plain)
            if opening:
                marker = opening.group(1)
                fence, fence_size = marker[0], len(marker)
            else:
                match = re.fullmatch(re.escape("#" * level) + r" (.+)", plain)
                if match:
                    found.append((match.group(1).strip(), offset, offset + len(line)))
        offset += len(line)
    return found


def headings(text: str, level: int = 2) -> list[str]:
    """Return actual Markdown headings at one level, ignoring fenced examples."""
    return [title for title, _, _ in _heading_spans(text, level)]


def markdown_heading_anchors(text: str) -> list[tuple[int, str, str]]:
    """Return heading level, title and GitHub anchor, preserving duplicate suffixes."""
    fence = r"(?ms)^\s*```.*?^\s*```[^\n]*$"
    seen: dict[str, int] = {}
    found = []
    for match in re.finditer(r"(?m)^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$", re.sub(fence, "", text)):
        title = match.group(2)
        label = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", title).replace("`", "").lower()
        slug = "".join(c for c in label if c.isalnum() or c in " -_").replace(" ", "-")
        seen[slug] = seen.get(slug, -1) + 1
        anchor = slug if seen[slug] == 0 else f"{slug}-{seen[slug]}"
        found.append((len(match.group(1)), title, anchor))
    return found


def ordered_heading_error(actual: list[str], required: list[str], *, level: int = 2) -> str | None:
    """Give the first missing or out-of-order required heading, allowing extras."""
    cursor = 0
    for item in required:
        try:
            cursor = actual.index(item, cursor) + 1
        except ValueError:
            if item in actual:
                return f"heading '{'#' * level} {item}' is out of order; move it to where the template puts it"
            return f"missing heading '{'#' * level} {item}'; add it where the template puts it"
    return None


def frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse the intentionally small, one-line YAML-frontmatter subset we author."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing frontmatter; the first line must be '---'")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise ValueError("unclosed frontmatter; add a closing '---'") from exc
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        match = re.fullmatch(r"([a-z][a-z0-9_-]*):[ ]+([^\r\n]+)\r?\n?", line)
        if not match or not match.group(2).strip():
            raise ValueError("frontmatter fields must be nonempty single-line 'key: value' entries")
        key, value = match.group(1), match.group(2)
        if key in fields:
            raise ValueError(f"duplicate frontmatter field {key!r}")
        fields[key] = value
    return fields, "".join(lines[end + 1:])


def section(text: str, name: str, *, level: int = 2) -> str:
    """Find exactly one real Markdown section, stopping at the next peer."""
    matches = _heading_spans(text, level)
    positions = [i for i, (title, _, _) in enumerate(matches) if title == name]
    if len(positions) != 1:
        raise ValueError(f"expected exactly one '{'#' * level} {name}' section")
    index = positions[0]
    start = matches[index][2]
    end = matches[index + 1][1] if index + 1 < len(matches) else len(text)
    return text[start:end].strip()


def ordered_bold_fields(block: str, required: tuple[str, ...]) -> dict[str, str]:
    """Require one substantive, single-line **Label:** value for each field, in order."""
    # The compact contract's first paragraph is its machine-readable interface.
    # Further prose may elaborate within the section without duplicating the fields.
    first, _, remainder = block.partition("\n\n")
    rows = [line.strip() for line in first.splitlines() if line.strip()]
    # Supporting prose is permitted, but not a second version of any contract
    # field after the first blank line. There is one canonical value per field.
    names = "|".join(re.escape(name) for name in required)
    duplicate = re.search(r"(?m)^\s*\*\*(" + names + r"):\*\*", remainder)
    if duplicate:
        raise ValueError(f"duplicate contract field {duplicate.group(1)!r} after the field block")
    actual: list[str] = []
    values: dict[str, str] = {}
    for line in rows:
        hit = re.fullmatch(r"\*\*([^*:\n]+):\*\* ([^\n]+)", line)
        if not hit:
            raise ValueError("contract must contain only single-line '**Field:** value' entries")
        key, value = hit.group(1), hit.group(2)
        if key in values:
            raise ValueError(f"duplicate contract field {key!r}")
        if len(value.strip()) < 12 or value != value.strip() or value in ("TBD", "TODO"):
            raise ValueError(f"contract field {key!r} needs substantive one-line content")
        actual.append(key)
        values[key] = value
    if actual != list(required):
        raise ValueError(f"contract fields must be {', '.join(required)}, in that order; found {', '.join(actual) or 'none'}")
    return values


def read_text(root: Path, path: Path, *, encoding: str = "utf-8") -> str:
    """Read a working-tree file, retaining Path.read_text's missing-file errors."""
    return (root / path).read_text(encoding=encoding)


def _search(pattern: str | Pattern[str], text: str, flags: int) -> re.Match[str] | None:
    return pattern.search(text) if hasattr(pattern, "search") else re.search(pattern, text, flags)


def _finditer(pattern: str | Pattern[str], text: str, flags: int) -> list[re.Match[str]]:
    return list(pattern.finditer(text)) if hasattr(pattern, "finditer") else list(re.finditer(pattern, text, flags))


def heading(text: str, prefix: str = "# ", *, missing: str = "error") -> str | None:
    """Return the first matching heading's stripped title or apply missing policy."""
    match = re.search(rf"^{re.escape(prefix)}(.+)$", text, re.M)
    if match:
        return match.group(1).strip()
    if missing == "none":
        return None
    if missing == "empty":
        return ""
    if missing == "error":
        raise ValueError(f"missing heading: {prefix}")
    raise ValueError(f"unknown missing-heading policy: {missing}")


def heading_present(text: str, pattern: str | Pattern[str], *, flags: int = re.M) -> bool:
    return _search(pattern, text, flags) is not None


def section_by_heading(
    text: str,
    title: str,
    *,
    missing: str = "empty",
    boundary: str | Pattern[str] = r"^## ",
    strip: bool = True,
    flags: int = re.M,
) -> str | None:
    """Extract an exact H2 section; callers choose missing, boundary and trim policy."""
    start = re.search(r"^## " + re.escape(title) + r"\s*$", text, flags)
    if start is None:
        if missing == "none":
            return None
        if missing == "empty":
            return ""
        if missing == "error":
            raise ValueError(f"missing section: {title}")
        raise ValueError(f"unknown missing-section policy: {missing}")
    return section_after_match(text, start, boundary=boundary, strip=strip, flags=flags)


def section_after_match(
    text: str,
    match: re.Match[str],
    *,
    boundary: str | Pattern[str],
    strip: bool = False,
    flags: int = re.M,
) -> str:
    tail = text[match.end():]
    end = _search(boundary, tail, flags)
    value = tail[:end.start()] if end else tail
    return value.strip() if strip else value


def matching_sections(text: str, pattern: str | Pattern[str], *, flags: int = re.M) -> list[re.Match[str]]:
    return _finditer(pattern, text, flags)


def field_match(
    text: str,
    key: str,
    *,
    style: str = "plain",
    value_pattern: str = r"(.+)",
    flags: int = re.M,
) -> re.Match[str] | None:
    """Find the first `Key: value` or `**Key:** value` line by its key."""
    escaped = re.escape(key)
    if style == "plain":
        prefix = rf"^{escaped}:\s*"
    elif style == "bold":
        prefix = rf"^\*\*{escaped}:\*\*\s*"
    else:
        raise ValueError(f"unknown field style: {style}")
    return re.search(prefix + value_pattern + r"$", text, flags)


def named_field_matches(
    text: str,
    keys: tuple[str, ...] | list[str],
    *,
    style: str = "bold",
    value_pattern: str = r"(.+)",
    flags: int = re.M,
) -> list[re.Match[str]]:
    """Find labeled fields while leaving ordering and duplicate handling to callers."""
    if style not in {"plain", "bold"}:
        raise ValueError(f"unknown field style: {style}")
    # Caller labels are exact and may contain spaces; escape each before alternation.
    alternatives = "|".join(re.escape(key) for key in keys)
    if style == "plain":
        pattern = r"^(" + alternatives + r"):\s*" + value_pattern + r"$"
    else:
        pattern = r"^\*\*(" + alternatives + r"):\*\*\s*" + value_pattern + r"$"
    return _finditer(pattern, text, flags)


def key_value_lines(text: str, *, style: str = "plain") -> list[tuple[str, str, str]]:
    """Parse header lines as (key, separator, value), retaining malformed lines."""
    if style not in {"plain", "bold"}:
        raise ValueError(f"unknown field style: {style}")
    parsed = []
    for line in text.splitlines():
        if style == "plain":
            key, separator, value = line.partition(":")
        else:
            match = re.fullmatch(r"\*\*(.+?):\*\*(.*)", line)
            if not match:
                parsed.append((line.strip(), "", ""))
                continue
            key, value = match.groups()
            separator = ":"
        parsed.append((key.strip(), separator, value.strip()))
    return parsed


def split_table_row(line: str) -> list[str]:
    """Split the repository's simple pipe table rows, matching existing callers."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_placeholder(
    value: str,
    tokens: frozenset[str] | set[str],
    *,
    trim: str | None = " .-",
    empty: bool = True,
) -> bool:
    """Compare one exact normalized placeholder; trim=None preserves punctuation."""
    normalized = value.strip().lower()
    if trim is not None:
        normalized = normalized.strip(trim)
    return (empty and not normalized) or normalized in tokens
