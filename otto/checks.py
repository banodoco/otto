"""Registry contract and runner for repository checks."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
import argparse
import re
from urllib.parse import unquote

from .markdown import read_text, markdown_heading_anchors


@dataclass(frozen=True)
class Context:
    root: Path
    base: str | None = None
    event: Path | None = None
    body_file: Path | None = None


@dataclass(frozen=True)
class Check:
    id: str
    trigger: Literal["always", "pr"]
    description: str
    run: Callable[[Context], list[str]]

    def __post_init__(self):
        if not self.id or any(c.isspace() for c in self.id):
            raise ValueError("check id must be a nonempty token")
        if self.trigger not in ("always", "pr"):
            raise ValueError("check trigger must be always or pr")
        if not self.description.strip() or "\n" in self.description or "\r" in self.description:
            raise ValueError("check description must be one nonempty line")
        if not callable(self.run):
            raise ValueError("check must be callable")


LINK = re.compile(r'(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)')


def read(root: Path, path: Path) -> str:
    return read_text(root, path)


def local_links(root: Path, path: Path) -> list[str]:
    """Check paths, not GitHub-generated anchor fragments or external URLs."""
    text = read(root, path)
    text = re.sub(r'(?ms)^\s*```.*?^\s*```[^\n]*$', '', text)
    missing = []
    for hit in LINK.finditer(text):
        target = hit.group(1).strip().split(' "', 1)[0].strip('<>')
        if target.startswith(('#', '/', '//')) or re.match(r'^[a-z][\w+.-]*:', target, re.I):
            continue
        target = unquote(target.split('#', 1)[0].split('?', 1)[0])
        if target and not (root / path.parent / target).exists():
            missing.append(f'{path}: missing link target {target}')
    return missing


def _link_anchors(context, target_pattern=None):
    """A relative Markdown link with a fragment must name a heading in its target."""
    import posixpath
    root, fence = context.root, r"(?ms)^\s*```.*?^\s*```[^\n]*$"

    def anchors(relative):
        return {anchor for _, _, anchor in markdown_heading_anchors(read(root, relative))}

    errors = []
    for path in sorted(p.relative_to(root) for p in root.rglob("*.md") if ".git" not in p.relative_to(root).parts and ".generated" not in p.relative_to(root).parts):
        for hit in LINK.finditer(re.sub(fence, "", read(root, path))):
            address, _, fragment = hit.group(1).strip().split(' "', 1)[0].strip("<>").partition("#")
            if not fragment or re.match(r"^([a-z][\w+.-]*:|/)", address, re.I):
                continue
            target = posixpath.normpath((path.parent / (address or path.name)).as_posix())
            if ((target.endswith(".md") if target_pattern is None else re.fullmatch(target_pattern, target)) and (root / target).is_file()
                    and fragment not in anchors(Path(target))):
                errors.append(f"{path.as_posix()}: link to {target}#{fragment} matches no heading in that file; point the link at a heading that exists")
    return errors


def main(argv=None, *, root=None, registry=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List each check's id, trigger and description")
    check = commands.add_parser("check", help="Run applicable checks")
    check.add_argument("--base")
    body = check.add_mutually_exclusive_group()
    body.add_argument("--event", type=Path)
    body.add_argument("--body-file", type=Path)
    args = parser.parse_args(argv)
    entries = () if registry is None else registry
    if args.command == "list":
        for entry in entries:
            print(f"{entry.id} {entry.trigger} {entry.description}")
        return 0
    if bool(args.base) != bool(args.event or args.body_file):
        parser.error("--base and one of --event or --body-file must be supplied together")
    context = Context(Path.cwd() if root is None else Path(root), args.base, args.event, args.body_file)
    failed = False
    for entry in entries:
        if entry.trigger == "always" or args.base:
            for message in entry.run(context):
                print(f"ERROR {entry.id}: {message}")
                failed = True
    return int(failed)
