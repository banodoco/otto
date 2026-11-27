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


def markdown_fragment_targets(text: str) -> set[str]:
    """Keep legacy heading slugs and recognize a bounded explicit-anchor form.

    Only empty paired a/id tags with a quoted literal ASCII token are added.
    This is a conservative context mask, not an HTML or Markdown renderer:
    code, comments, link syntax, raw HTML and uncertain containers cannot
    supply explicit targets. Existing heading behavior is intentionally separate.
    """
    targets = {anchor for _, _, anchor in markdown_heading_anchors(text)}
    anchor = re.compile(
        r"""<a[ \t\n]+id[ \t\n]*=[ \t\n]*(["'])([a-z0-9_][a-z0-9_.:-]*)\1[ \t\n]*></a[ \t\n]*>""",
        re.ASCII | re.IGNORECASE,
    )
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not anchor.search(text):
        return targets

    from bisect import bisect_left, bisect_right
    from string import punctuation

    fence_open = re.compile(r" {0,3}(\x60{3,}|~{3,})(.*)")
    container = re.compile(r" {0,3}(>|(?:[-+*]|\d{1,9}[.)])(?:[ \t]+|$))")
    heading_line = re.compile(r" {0,3}#{1,6}(?:[ \t]|$)")
    rule_line = re.compile(r" {0,3}(?:(?:[-*_][ \t]*){3,}|=+[ \t]*|-+[ \t]*)$")
    definition = re.compile(r" {0,3}\[(?:\\.|[^\\\]\n])+\]:[ \t]*")
    tag_start = re.compile(r"</?([a-z][a-z0-9-]*)(?=[ \t\n/>])", re.ASCII | re.I)
    tag = re.compile(r"""</?([a-z][a-z0-9-]*)(?=[ \t\n/>])(?:[^<>"']|"[^"]*"|'[^']*')*>""",
                     re.ASCII | re.I)
    raw_names = {"script", "style", "pre", "textarea"}
    void_names = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                  "link", "meta", "param", "source", "track", "wbr"}
    block_names = set(("address article aside base basefont blockquote body caption center col "
                       "colgroup dd details dialog dir div dl dt fieldset figcaption figure "
                       "footer form frame frameset h1 h2 h3 h4 h5 h6 head header hr html iframe "
                       "legend li link main menu menuitem nav noframes ol optgroup option p "
                       "param search section summary table tbody td tfoot th thead title tr "
                       "track ul").split())

    def opener(line):
        hit = fence_open.fullmatch(line)
        if hit and (hit[1][0] == "~" or chr(96) not in hit[2]):
            return hit[1]
        return None

    # Inline code/link spans cannot cross a paragraph/block boundary. Table
    # cells are separate inline contexts as well. Index boundaries and runs
    # once, rather than repeatedly looking ahead through the document.
    lines = text.split("\n")
    starts = []
    by_start = {}
    offset = 0
    cuts = {len(text)}
    for line in lines:
        starts.append(offset)
        by_start[offset] = line
        end = offset + len(line)
        if not line.strip() or opener(line) or container.match(line) or rule_line.fullmatch(line):
            cuts.add(offset)
        if heading_line.match(line):
            cuts.update((offset, end))
        offset = end + 1

    def pipes(line):
        return [hit.end() - 1 for hit in re.finditer(r"(?<!\\)(?:\\\\)*\|", line)]

    def cells(line):
        points = pipes(line)
        parts = [line[a + 1:b].strip() for a, b in zip([-1, *points], [*points, len(line)])]
        if points and not parts[0]:
            parts.pop(0)
        if points and parts and not parts[-1]:
            parts.pop()
        return parts

    # Only treat an actual header/separator pair as a table, not an arbitrary
    # pipe in an ordinary paragraph or code span.
    for n in range(1, len(lines)):
        separator = cells(lines[n])
        header = lines[n - 1]
        if (not pipes(lines[n]) or not separator
                or not all(re.fullmatch(r":?-+:?", part) for part in separator)
                or not pipes(header) or len(cells(header)) != len(separator)
                or (n > 1 and lines[n - 2].strip()
                    and not heading_line.match(lines[n - 2])
                    and not rule_line.fullmatch(lines[n - 2]))):
            continue
        for k in range(n - 1, len(lines)):
            row = lines[k]
            if not pipes(row) or container.match(row) or opener(row):
                break
            cuts.update((starts[k], starts[k] + len(row)))
            cuts.update(starts[k] + p for p in pipes(row))
    cuts = sorted(cuts)
    runs = {}
    for hit in re.finditer(r"\x60+", text):
        runs.setdefault(len(hit[0]), []).append(hit.start())

    def inline_end(at):
        index = bisect_right(cuts, at)
        return cuts[index] if index < len(cuts) else len(text)

    def line_end(at):
        end = text.find("\n", at)
        return len(text) if end < 0 else end

    def delimited(at, limit, closer):
        """Skip a quoted/angle token; ambiguous unclosed tokens grant nothing."""
        while at < limit:
            if text[at] == "\\" and at + 1 < limit and text[at + 1] in punctuation:
                at += 2
            elif text[at] == closer:
                return at + 1
            else:
                at += 1
        return limit

    def link_end(at, limit):
        # Called after ](. Parenthesized destinations/titles can nest; a quote
        # after whitespace or initial angle destination shields parentheses.
        depth = 1
        first = True
        while at < limit:
            ch = text[at]
            if ch == "\\" and at + 1 < limit and text[at + 1] in punctuation:
                at += 2
            elif first and ch == "<":
                at = delimited(at + 1, limit, ">")
            elif ch in "\"'" and at > 0 and text[at - 1].isspace():
                at = delimited(at + 1, limit, ch)
            elif ch == "(":
                depth += 1
                at += 1
            elif ch == ")":
                depth -= 1
                at += 1
                if not depth:
                    return at
            else:
                at += 1
                if first and ch.isspace():
                    continue
            first = False
        return limit

    def reference_end(at, limit):
        # Definitions may place the destination or a quoted title on the
        # following line. Do not swallow the next ordinary prose line.
        while at < limit and text[at].isspace():
            at += 1
        if at < limit and text[at] == "<":
            at = delimited(at + 1, limit, ">")
        else:
            while at < limit and not text[at].isspace():
                at += 1
        end = min(line_end(at), limit)
        while at < limit and text[at].isspace():
            at += 1
        if at < limit and text[at] in "\"'(":
            closer = ")" if text[at] == "(" else text[at]
            end = min(line_end(delimited(at + 1, limit, closer)), limit)
        return min(end + 1, len(text))

    i = 0
    # A leading YAML-like metadata block is not rendered prose.
    if lines[0] == "---" and len(lines) > 1 and re.match(r"[a-zA-Z_][\w-]*:", lines[1]):
        closing = next((n for n in range(2, len(lines)) if lines[n] in {"---", "..."}), None)
        i = len(text) if closing is None else starts[closing] + len(lines[closing]) + 1

    fence = None
    container_indent = None
    after_blank = False
    raw_stack = []
    raw_block = False
    bracket_depth = 0
    inline_boundary = -1
    while i < len(text):
        if i in by_start:
            line = by_start[i]
            next_line = i + len(line) + 1
            if fence:
                if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*", line):
                    fence = None
                i = next_line
                continue
            if not line.strip():
                raw_block = False
                after_blank = True
                bracket_depth = 0
                i = next_line
                continue
            if not raw_stack and not raw_block:
                marker = container.match(line)
                indent = len(line) - len(line.lstrip(" \t"))
                if marker:
                    container_indent = 0 if marker[1] == ">" else marker.end()
                    after_blank = False
                    i = next_line
                    continue
                if container_indent is not None:
                    if ((container_indent and indent >= container_indent)
                            or (not after_blank and not opener(line)
                                and not heading_line.match(line) and not rule_line.fullmatch(line))):
                        # Includes lazy continuation and nested container code.
                        i = next_line
                        continue
                    container_indent = None
                after_blank = False
                fence = opener(line)
                if fence or indent >= 4 or "\t" in line[:indent] or heading_line.match(line):
                    i = next_line
                    continue
                ref = definition.match(line)
                if ref:
                    i = reference_end(i + ref.end(), inline_end(i))
                    continue

        limit = inline_end(i)
        if limit != inline_boundary:
            bracket_depth = 0
            inline_boundary = limit

        # Raw-text contents are not Markdown; only the matching closing tag
        # ends this mask. Other HTML tokens below are masked, never interpreted
        # as a source of ids.
        if raw_stack and raw_stack[-1] in raw_names:
            close = re.search(r"</" + raw_stack[-1] + r"[ \t\n]*>", text[i:], re.ASCII | re.I)
            if close is None:
                break
            i += close.end()
            raw_stack.pop()
            continue

        ch = text[i]
        if not raw_stack and not raw_block:
            if ch == "\\" and i + 1 < limit and text[i + 1] in punctuation:
                i += 2
                continue
            if ch == chr(96):
                end = i + 1
                while end < limit and text[end] == ch:
                    end += 1
                matches = runs.get(end - i, [])
                k = bisect_left(matches, end)
                i = (matches[k] + end - i if k < len(matches)
                     and matches[k] + end - i <= limit else end)
                continue
            if ch == "[":
                bracket_depth += 1
            elif ch == "]":
                bracket_depth = max(0, bracket_depth - 1)
                if text.startswith("](", i):
                    i = link_end(i + 2, limit)
                    continue

        if ch == "<":
            if text.startswith("<!--", i):
                end = text.find("-->", i + 4)
                i = len(text) if end < 0 else end + 3
                continue
            for prefix, closer in (("<![CDATA[", "]]>"), ("<?", "?>"), ("<!", ">")):
                if text.startswith(prefix, i):
                    end = text.find(closer, i + len(prefix))
                    i = len(text) if end < 0 else end + len(closer)
                    break
            else:
                hit = anchor.match(text, i, limit)
                if hit:
                    if not raw_stack and not raw_block and not bracket_depth:
                        targets.add(hit[2])
                    i = hit.end()
                    continue
                start = tag_start.match(text, i, limit)
                if start:
                    name = start[1].lower()
                    token = tag.match(text, i, limit)
                    if not token:
                        # Malformed/ambiguous tag syntax cannot lend its
                        # attribute contents to the anchor recognizer.
                        i = limit
                        continue
                    line_start = text.rfind("\n", 0, i) + 1
                    if (not text[line_start:i].strip() and name not in raw_names
                            and (name in block_names or not text[token.end():line_end(token.end())].strip())):
                        raw_block = True
                    if text.startswith("</", i):
                        if name in raw_stack:
                            while raw_stack.pop() != name:
                                pass
                    elif name not in void_names:
                        raw_stack.append(name)
                    i = token.end()
                    continue
                i += 1
            continue
        i += 1
    return targets


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
