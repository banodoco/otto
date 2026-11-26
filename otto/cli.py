"""Command-line entry point for Otto."""

import argparse
from pathlib import Path
import sys

from . import __version__, checks, views
from .config import load_workspace
from .pipelines import list_pipelines, show_pipeline
from .skills.builder import build_packages
from .skills.installer import install_packages


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="otto",
        description="An importable framework for Markdown-first organisations.",
        epilog=(
            "Commands: list, check, views generate, skills build, "
            "skills check, skills install, pipeline list, pipeline show."
        ),
    )
    parser.add_argument("--version", action="store_true", help="show Otto's version")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="workspace root")
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("list", help="list workspace contents")
    check = commands.add_parser("check", help="check the workspace")
    check.add_argument("--base")
    body = check.add_mutually_exclusive_group()
    body.add_argument("--event", type=Path)
    body.add_argument("--body-file", type=Path)

    for group, description, children in (
        ("views", "manage views", ("generate",)),
        ("skills", "manage skills", ("build", "check", "install")),
        ("pipeline", "inspect pipelines", ("list", "show")),
    ):
        group_parser = commands.add_parser(group, help=description)
        subcommands = group_parser.add_subparsers(dest="subcommand", required=True)
        for child in children:
            command = subcommands.add_parser(child)
            if group == "skills" and child == "install":
                command.add_argument("--destination", type=Path, action="append")
                command.add_argument("--dry-run", action="store_true")
            if group == "pipeline" and child == "show":
                command.add_argument("pipeline")
                command.add_argument("record")

    return parser


def _dispatch(args, workspace) -> int:
    if args.command == "list":
        return checks.list_registry(checks.workspace_registry(workspace, listing=True))
    if args.command == "check":
        entries = checks.workspace_registry(workspace)
        context = checks.Context(workspace.root, args.base, args.event, args.body_file)
        return checks.run_registry(context, entries, ordered=True)
    if args.command == "views":
        declared, errors = views.load_views(workspace)
        if errors:
            for message in errors:
                print(message, file=sys.stderr)
            return 1
        for target in views.sync(workspace.root, declared):
            print(target)
        return 0
    if args.command == "skills":
        config = checks.skill_config(workspace)
        if args.subcommand == "check":
            errors = checks._skill_findings(workspace)
            for message in errors:
                print(message)
            return int(bool(errors))
        if args.subcommand == "build":
            actions = build_packages(workspace.root, config)
        else:
            actions = install_packages(workspace.root, config, args.destination,
                                       dry_run=args.dry_run)
        for action in actions:
            print(action)
        return 0
    if args.command == "pipeline":
        output = (list_pipelines(workspace) if args.subcommand == "list"
                  else show_pipeline(workspace, args.pipeline, args.record))
        print(output, end="")
        return 0
    raise AssertionError("unhandled command")


def main(argv: list[str] | None = None) -> int:
    """Dispatch an Otto command and return its exit status."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.version:
        print(f"otto {__version__}")
        return 0
    if args.command is None:
        parser.error("a command is required")
    if args.command == "check" and bool(args.base) != bool(args.event or args.body_file):
        parser.error("--base and one of --event or --body-file must be supplied together")
    try:
        if args.command == "list" and args.root.is_dir():
            try:
                (args.root / "otto.toml").lstat()
            except FileNotFoundError:
                print("no otto.toml found", file=sys.stderr)
                return 0
        workspace = load_workspace(args.root)
        return _dispatch(args, workspace)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
