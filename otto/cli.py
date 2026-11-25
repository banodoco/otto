"""Command-line entry point for Otto."""

import argparse
from pathlib import Path
import sys

from . import __version__


def _list_workspace() -> int:
    if not Path("otto.toml").is_file():
        print("no otto.toml found", file=sys.stderr)
    return 0


def _stub(command: str) -> int:
    print(f"not implemented yet: {command}", file=sys.stderr)
    return 2


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
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("list", help="list workspace contents")
    commands.add_parser("check", help="check the workspace")

    for group, description, children in (
        ("views", "manage views", ("generate",)),
        ("skills", "manage skills", ("build", "check", "install")),
        ("pipeline", "inspect pipelines", ("list", "show")),
    ):
        group_parser = commands.add_parser(group, help=description)
        subcommands = group_parser.add_subparsers(dest="subcommand", required=True)
        for child in children:
            subcommands.add_parser(child)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch an Otto command and return its exit status."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.version:
        print(f"otto {__version__}")
        return 0
    if args.command is None:
        parser.error("a command is required")
    if args.command == "list":
        return _list_workspace()

    subcommand = getattr(args, "subcommand", None)
    name = f"{args.command} {subcommand}" if subcommand else args.command
    return _stub(name)


if __name__ == "__main__":
    sys.exit(main())
