"""Registry contract and runner for repository checks."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
import argparse
import json
import posixpath
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
        if not isinstance(self.id, str) or not self.id or any(c.isspace() for c in self.id):
            raise ValueError("check id must be a nonempty token")
        if self.trigger not in ("always", "pr"):
            raise ValueError("check trigger must be always or pr")
        if (not isinstance(self.description, str) or not self.description.strip()
                or "\n" in self.description or "\r" in self.description):
            raise ValueError("check description must be one nonempty line")
        if not callable(self.run):
            raise ValueError("check must be callable")


LINK = re.compile(r'(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)')


def read(root: Path, path: Path) -> str:
    return read_text(root, path)


_FENCE = re.compile(r"(?ms)^\s*```.*?^\s*```[^\n]*$")


def _live_links(root, path):
    text = read(root, path)
    # Keep offsets and line breaks while ignoring the same fences as the
    # compatibility checks.
    live = _FENCE.sub(lambda hit: re.sub(r"[^\n]", " ", hit.group()), text)
    for hit in LINK.finditer(live):
        yield text.count("\n", 0, hit.start()) + 1, hit.group(1)


def local_links(root: Path, path: Path, *, located=False) -> list[str]:
    """Check paths, not GitHub-generated anchor fragments or external URLs."""
    missing = []
    for line, value in _live_links(root, path):
        target = value.strip().split(' "', 1)[0].strip('<>')
        if target.startswith(('#', '/', '//')) or re.match(r'^[a-z][\w+.-]*:', target, re.I):
            continue
        target = unquote(target.split('#', 1)[0].split('?', 1)[0])
        if target and not (root / path.parent / target).exists():
            location = f"{path.as_posix()}:{line}" if located else str(path)
            missing.append(f'{location}: missing link target {target}')
    return missing


def _markdown_paths(root, excluded=None):
    return sorted(p.relative_to(root) for p in root.rglob("*.md")
                  if ".git" not in p.relative_to(root).parts
                  and ".generated" not in p.relative_to(root).parts
                  and (excluded is None or not p.is_relative_to(excluded)))


def _link_anchors(context, target_pattern=None, *, located=False, excluded=None):
    """A relative Markdown fragment must name a heading or a supported explicit id."""
    from .markdown import markdown_fragment_targets

    root = context.root

    def anchors(relative):
        return markdown_fragment_targets(read(root, relative))

    errors = []
    for path in _markdown_paths(root, excluded):
        for line, value in _live_links(root, path):
            address, _, fragment = value.strip().split(' "', 1)[0].strip("<>").partition("#")
            if not fragment or re.match(r"^([a-z][\w+.-]*:|/)", address, re.I):
                continue
            target = posixpath.normpath((path.parent / (address or path.name)).as_posix())
            if ((target.endswith(".md") if target_pattern is None else re.fullmatch(target_pattern, target)) and (root / target).is_file()
                    and fragment not in anchors(Path(target))):
                location = f"{path.as_posix()}:{line}" if located else path.as_posix()
                errors.append(f"{location}: link to {target}#{fragment} matches no heading in that file; point the link at a heading that exists")
    return errors


def _body(context):
    if context.body_file:
        return context.body_file.read_text(encoding='utf-8')
    if context.event:
        return json.loads(context.event.read_text(encoding='utf-8')).get('pull_request', {}).get('body') or ''
    return ''


def skill_config(workspace):
    """Return the workspace's single resolved immutable skill configuration."""
    return workspace.skill_config


def _skill_findings(workspace):
    from .skills.builder import check_packages
    config = skill_config(workspace)
    errors = check_packages(workspace.root, config)
    # The engine identifies the package and the affected file in these two
    # drift diagnostics. Attach that real path, never an invented line.
    located = []
    for message in errors:
        name, sep, detail = message.partition(": ")
        if sep and name.startswith(config.namespace) and re.fullmatch(r"[a-z0-9-]+", name):
            filename = {"generated SKILL.md is stale": "SKILL.md",
                        "ownership/source marker is stale": config.marker}.get(detail)
            if filename:
                message = f"{(config.output / name / filename).as_posix()}: {message}"
        located.append(message)
    return located


def _load_checks(workspace, generic_ids):
    registration = workspace.config.checks
    if registration is None:
        return ()
    declaration = ("checks", "register")
    error = lambda message: workspace.source_map.error(declaration, message)
    factory = workspace.export(registration.register, declaration=declaration)
    try:
        entries = factory(workspace)
    except ValueError as exc:
        if str(exc) in ("check id must be a nonempty token",
                       "check trigger must be always or pr",
                       "check description must be one nonempty line",
                       "check must be callable"):
            raise error(str(exc)) from exc
        raise error(f"cannot load adapter {workspace.config.adapters.module}: {exc}") from exc
    except Exception as exc:
        raise error(f"cannot load adapter {workspace.config.adapters.module}: {exc}") from exc
    invalid = f"adapter export {registration.register!r} returned an invalid check registry"
    if not isinstance(entries, tuple) or not all(isinstance(entry, Check) for entry in entries):
        raise error(invalid)
    ids = set(generic_ids)
    for entry in entries:
        if entry.id in ids:
            raise error(f"duplicate check id {entry.id!r}")
        ids.add(entry.id)
    return entries


def _ordered(messages):
    """Sort located findings by path and numerical line; retain unlocated bodies."""
    def key(message):
        match = re.match(r"^(.+?):([1-9]\d*): (.*)$", message, re.S)
        return (0, match[1], int(match[2]), match[3]) if match else (1, "", 0, message)
    return sorted(messages, key=key)


def workspace_registry(workspace, *, listing=False):
    """Assemble the fixed checks and local registrations around one workspace.

    Record and graph validation are lazy, shared between dependent checks, and
    report a failed upstream stage only at relationship-validity.
    """
    from . import views
    from .conformance import PIPELINE_CONFORMANCE, check_pipeline_conformance
    from .records import load_records
    from .relationships import RelationshipIndex, RelationshipSchema
    from .templates import check_pack_shape

    root = workspace.root
    excluded = workspace.paths["skills_output"]
    not_loaded = object()
    batch = schema = index = not_loaded
    record_errors = []
    graph_errors = []

    def records():
        nonlocal batch
        if batch is not_loaded:
            try:
                batch = load_records(workspace)
            except (OSError, ValueError) as exc:
                record_errors.append(str(exc))
                batch = None
        return batch

    def graph():
        nonlocal schema, index
        if index is not_loaded:
            current = records()
            if current is None:
                index = None
            else:
                try:
                    schema = RelationshipSchema.from_workspace(workspace)
                    index = RelationshipIndex.from_batch(current, schema=schema)
                except (OSError, ValueError) as exc:
                    graph_errors.append(str(exc))
                    index = None
        return index

    def pack(context):
        current = records()
        return [] if current is None else check_pack_shape(workspace, current, base=context.base)

    def relations(context):
        graph()
        return record_errors + graph_errors

    def conformance(context):
        current = graph()
        return [] if current is None else check_pipeline_conformance(
            workspace, schema=schema, batch=batch, index=current)

    def markdown_links(context):
        return [message for path in _markdown_paths(root, excluded)
                for message in local_links(root, path, located=True)]

    view_error = None
    declared_views, preflight = (), []
    try:
        declared_views, preflight = views.load_views(workspace)
    except ValueError as exc:
        if listing:
            raise
        view_error = str(exc)
    if listing and preflight:
        raise ValueError("; ".join(preflight))

    def generated_views(context):
        if view_error is not None:
            return [view_error]
        return views.check_registered(workspace, declared_views, preflight)

    generic = (
        Check("markdown-links", "always", "Check relative Markdown links", markdown_links),
        Check("link-anchors", "always", "Check relative Markdown headings",
              lambda context: _link_anchors(context, located=True, excluded=excluded)),
        Check("pack-shape", "always", "Check pack shape and templates", pack),
        Check("relationship-validity", "always", "Check declared relationships", relations),
        Check(PIPELINE_CONFORMANCE.id, PIPELINE_CONFORMANCE.trigger,
              PIPELINE_CONFORMANCE.description, conformance),
        Check("skill-packages-current", "always", "Check generated skill packages",
              lambda context: _skill_findings(workspace)),
        Check("generated-views", "always", "Check generated views", generated_views),
    )
    local = _load_checks(workspace, (entry.id for entry in generic))
    return generic + local


def list_registry(registry):
    for entry in registry:
        print(f"{entry.id} {entry.trigger} {entry.description}")
    return 0


def run_registry(context, registry, *, ordered=False):
    failed = False
    for entry in registry:
        if entry.trigger == "always" or context.base:
            try:
                messages = entry.run(context)
            except (OSError, ValueError) as exc:
                if not ordered:
                    raise
                messages = [str(exc)]
            for message in (_ordered(messages) if ordered else messages):
                print(f"ERROR {entry.id}: {message}")
                failed = True
    return int(failed)


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
        return list_registry(entries)
    if bool(args.base) != bool(args.event or args.body_file):
        parser.error("--base and one of --event or --body-file must be supplied together")
    context = Context(Path.cwd() if root is None else Path(root), args.base, args.event, args.body_file)
    return run_registry(context, entries)
