"""Declared generated views, their sources, and stale-view diagnostics."""
from dataclasses import dataclass
from pathlib import Path
import subprocess
import os
import re
from typing import Callable


from .markdown import markdown_heading_anchors


@dataclass(frozen=True)
class View:
    name: str
    sources: tuple[str, ...]
    target: str
    render: Callable[[Path], str]
    region: str | None = None
    marker_prefix: str | None = None

    @property
    def _marker_prefix(self) -> str:
        return "<!-- Generated view: " if self.marker_prefix is None else self.marker_prefix

    @property
    def marker(self) -> str:
        return f"{self._marker_prefix}{self.name}; sources: {', '.join(self.sources)}. Do not edit. -->"


def _with_marker(view: View, content: str) -> str:
    if isinstance(view.region, str) and view.region.startswith("block:"):
        name = view.region.removeprefix("block:")
        regions = _block_regions(content, view.target)
        if ("block", name) not in regions:
            raise ValueError(f"view {view.name}: {view.target} must contain one <!-- block:{name}:start --> and one <!-- block:{name}:end --> line; restore them")
        _, body_start, body_end, _ = regions[("block", name)]
        body = content[body_start:body_end]
        if view.marker in body:
            return content
        generated = "\n".join(line for line in body.strip("\n").splitlines() if not line.startswith(view._marker_prefix))
        return content[:body_start] + "\n" + view.marker + "\n" + generated + "\n" + content[body_end:]
    if view.region:
        region = view.region
        start = f"<!-- {region}:start -->"
        end = f"<!-- {region}:end -->"
        if content.count(start) != 1 or content.count(end) != 1:
            raise ValueError(f"view {view.name}: target must contain exactly one {start} line and one {end} line; restore them in {view.target}")
        if content.count(view.marker) == 1:
            return content
        before, rest = content.split(start, 1)
        _, after = rest.split(end, 1)
        generated = rest.split(end, 1)[0].lstrip("\n").rstrip("\n")
        generated = "\n".join(line for line in generated.splitlines() if not line.startswith(view._marker_prefix))
        return before + start + "\n" + view.marker + "\n" + generated + "\n" + end + after
    if content.startswith(view.marker + "\n"):
        return content
    if content.startswith(view._marker_prefix):
        content = content.split("\n", 1)[1]
    return view.marker + "\n" + content


def expected(view: View, root: Path) -> str:
    return _with_marker(view, view.render(root))


def touched(view: View, root: Path, base: str) -> bool:
    """Compare the generated part at the merge base with the working tree."""
    root = root.resolve()
    try:
        merge_base = subprocess.check_output(
            ["git", "merge-base", base, "HEAD"], cwd=root, text=True,
            stderr=subprocess.PIPE).strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"view {view.name}: cannot find merge base for {base}: {exc}") from exc

    def region_content(text: str, revision: str, *, baseline: bool = False) -> str | None:
        if not view.region:
            return text
        if isinstance(view.region, str) and view.region.startswith("block:"):
            try:
                found = _block_regions(text, view.target).get(("block", view.region.removeprefix("block:")))
            except ValueError:
                found = None
            if found is None and not baseline:
                raise ValueError(f"view {view.name}: {view.target} must contain one {view.region} marker pair ({revision})")
            return None if found is None else text[found[1]:found[2]]
        region = view.region
        start = f"<!-- {region}:start -->"
        end = f"<!-- {region}:end -->"
        if text.count(start) != 1 or text.count(end) != 1:
            if baseline:
                return None
            raise ValueError(f"view {view.name}: {view.target} must contain exactly one {start} and {end} marker pair ({revision})")
        before, remainder = text.split(start, 1)
        content, after = remainder.split(end, 1)
        if after.find(start) >= 0 or before.find(end) >= 0:
            if baseline:
                return None
            raise ValueError(f"view {view.name}: invalid {region} marker order in {view.target} ({revision})")
        return content

    try:
        baseline = subprocess.check_output(
            ["git", "show", f"{merge_base}:{view.target}"], cwd=root,
            stderr=subprocess.PIPE).decode("utf-8")
    except subprocess.CalledProcessError:
        baseline = None
    try:
        current = (root / view.target).read_text(encoding="utf-8")
    except FileNotFoundError:
        current = None
    if baseline is None or current is None:
        if current is not None:
            # Validate a present region even when the target is new.
            region_content(current, "working tree")
        return baseline != current
    baseline_content = region_content(baseline, merge_base, baseline=True)
    current_content = region_content(current, "working tree")
    return baseline_content is None or baseline_content != current_content


def check_view(view: View, root: Path, hint: str = "regenerate the view") -> list[str]:
    try:
        actual = (root / view.target).read_text(encoding="utf-8")
        wanted = expected(view, root)
        if actual != wanted:
            return [f"view {view.name}: the generated part of {view.target} does not match its sources; "
                    f"edit {', '.join(view.sources)} instead and undo your change to that part; "
                    f"it refreshes itself on main after merge"]
    except ValueError as exc:
        detail = str(exc).removeprefix(f"view {view.name}: ")
        return [f"view {view.name}: cannot check {view.target}: {detail}; "
                f"then {hint}"]
    except (OSError, subprocess.CalledProcessError) as exc:
        return [f"view {view.name}: cannot check {view.target}: {exc}; "
                f"{view.target} is generated from {', '.join(view.sources)}, so fix any error there, "
                f"then {hint}"]
    return []


def check(root: Path, declarations=()) -> list[str]:
    declared, errors = views_for(root, declarations)
    return [*errors, *(message for view in declared for message in check_view(view, root))]


def sync(root: Path, declarations=()) -> list[str]:
    root = root.resolve()
    declared, errors = views_for(root, declarations)
    if errors:
        raise ValueError("shared blocks: " + "; ".join(errors))
    targets = []
    for view in declared:
        target_name = Path(view.target)
        if target_name.is_absolute() or ".." in target_name.parts:
            raise ValueError(f"view {view.name}: unsafe target outside repository: {view.target}")
        target = root / target_name
        current = target
        while current != root and current != current.parent:
            if current.is_symlink():
                raise ValueError(f"view {view.name}: target path contains symlink: {view.target}")
            current = current.parent
        if not target.resolve().is_relative_to(root):
            raise ValueError(f"view {view.name}: target outside repository: {view.target}")
        targets.append(target)

    changed = []
    changed_targets = set()
    for view, target in zip(declared, targets):
        content = expected(view, root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")
            if view.target not in changed_targets:
                changed.append(view.target)
                changed_targets.add(view.target)
    return changed


def rebase_links(value: str, from_dir: Path, to_dir: Path) -> str:
    """Re-base relative Markdown link targets between source directories."""
    def replace(match):
        target = match.group(2)
        if re.match(r"^(?:[a-z][a-z0-9+.-]*:|//|/|#)", target, re.I):
            return match.group(0)
        path, sep, fragment = target.partition("#")
        relative = os.path.relpath(from_dir / path, to_dir)
        return f"[{match.group(1)}]({relative}{sep}{fragment})"
    return re.sub(r"(?<!!)\[([^]\n]+)\]\(([^)\n]+)\)", replace, value)


BLOCK_MARKER = re.compile(r"(?m)^<!-- (block-source|block):([a-z0-9-]+):(start|end) -->[ \t]*$")
_FENCE = re.compile(r"(?ms)^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$")


def _blank_fences(text: str) -> str:
    """Blank fenced code (``` or ~~~) with spaces, keeping every offset and newline."""
    return _FENCE.sub(lambda hit: re.sub(r"[^\n]", " ", hit.group(0)), text)


def _block_regions(text: str, path: str) -> dict[tuple[str, str], tuple[int, int, int, int]]:
    """Return {(kind, name): (start marker begin, body begin, body end, end marker end)} offsets in `text`.

    Markers inside code fences are ignored. Unpaired or repeated markers are an error.
    """
    seen: dict[tuple[str, str], list[tuple[str, int, int]]] = {}
    for hit in BLOCK_MARKER.finditer(_blank_fences(text)):
        seen.setdefault((hit.group(1), hit.group(2)), []).append((hit.group(3), hit.start(), hit.end()))
    regions = {}
    for (kind, name), marks in seen.items():
        if [edge for edge, _, _ in marks] != ["start", "end"]:
            raise ValueError(f"{path}: {kind}:{name} needs exactly one start marker followed by one end marker "
                             f"(found {', '.join(edge for edge, _, _ in marks)}); fix the markers")
        regions[(kind, name)] = (marks[0][1], marks[0][2], marks[1][1], marks[1][2])
    return regions


def _owner_body(text: str, name: str, path: str) -> tuple[str, str, str]:
    """Return the owner's body, its nearest heading title and that heading's anchor."""
    begin, body_start, body_end, _ = _block_regions(text, path)[("block-source", name)]
    body = text[body_start:body_end].strip("\n")
    headings = markdown_heading_anchors(text[:begin])
    if not headings:
        return body, "", ""
    _, title, anchor = headings[-1]
    return body, re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", title).replace("`", ""), anchor


def _render_block(root: Path, name: str, owner: str, target: str) -> str:
    body, title, anchor = _owner_body((root / owner).read_text(encoding="utf-8"), name, owner)
    owner_dir, target_dir = Path(owner).parent, Path(target).parent
    # A same-file #anchor link must keep pointing at the owner once copied elsewhere.
    body = re.sub(r"(?<!!)(\[[^\]\n]+\])\(#([^)\n]*)\)", lambda hit: f"{hit.group(1)}({Path(owner).name}#{hit.group(2)})", body)
    body = rebase_links(body, owner_dir, target_dir)
    link = os.path.relpath(owner, target_dir)
    link = f"{link}#{anchor}" if anchor else link
    note = f"*From [{title or Path(owner).name}]({link}); edit it there.*"
    text = (root / target).read_text(encoding="utf-8")
    regions = _block_regions(text, target)
    if ("block", name) not in regions:
        raise ValueError(f"view block-{name}-{target}: {target} must contain one <!-- block:{name}:start --> and one <!-- block:{name}:end --> line; restore them")
    _, body_start, body_end, _ = regions[("block", name)]
    return text[:body_start] + "\n" + body + "\n\n" + note + "\n" + text[body_end:]


def views_for(root: Path, declarations=()) -> tuple[tuple[View, ...], list[str]]:
    """Return the workspace-provided view declarations."""
    return tuple(declarations), []
