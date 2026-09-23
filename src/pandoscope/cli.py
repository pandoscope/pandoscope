"""Command-line interface."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from pandoscope import __version__
from pandoscope.reinset.compose import Composition, compose
from pandoscope.reinset.order import validate_order
from pandoscope.stamp import TEMPLATE_URL, parse_data, stamp


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="pandoscope",
        description=(
            "Agentic engineering instrument: high-level commands to run a "
            "Pandoscope-powered project as a self-improving software factory."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"pandoscope {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    stamp_parser = subparsers.add_parser(
        "stamp", help=f"render the project scaffold ({TEMPLATE_URL})"
    )
    stamp_parser.add_argument(
        "directory", nargs="?", default=".", help="target directory (default: .)"
    )
    stamp_parser.add_argument(
        "-d",
        "--data",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="answer a template question (repeatable)",
    )
    stamp_parser.add_argument(
        "--defaults",
        action="store_true",
        help="use template defaults for unanswered questions",
    )
    stamp_parser.add_argument(
        "--vcs-ref", default=None, help="template branch, tag, or commit"
    )
    compose_parser = subparsers.add_parser(
        "compose",
        help="compose the session reinset from a SessionStart hook (skills#179)",
    )
    compose_parser.add_argument(
        "--session-root",
        default=None,
        help="directory holding the session's clones (default: $SESSION_ROOT, else .)",
    )
    order_parser = subparsers.add_parser(
        "order", help="waybill orders (pandoscope/waybill#1)"
    )
    order_sub = order_parser.add_subparsers(dest="order_command", required=True)
    check_parser = order_sub.add_parser(
        "check", help="validate order files against the order schema"
    )
    check_parser.add_argument("files", nargs="+", help="orders/<name>.yml files")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    if args.command == "stamp":
        try:
            data = parse_data(args.data)
        except ValueError as error:
            build_parser().error(str(error))
        stamp(
            args.directory,
            data,
            defaults=args.defaults,
            vcs_ref=args.vcs_ref,
        )
    if args.command == "compose":
        print(run_compose(args.session_root).render_text, end="")
    if args.command == "order":
        return run_order_check(args.files)
    return 0


def run_order_check(files: list[str]) -> int:
    """Validate each order file. Print every violation. Return 1 when any file fails."""
    failed = 0
    for name in files:
        path = Path(name)
        try:
            data = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as error:
            print(f"{path}: cannot read as YAML: {error}")
            failed += 1
            continue
        violations = validate_order(data, path.stem)
        if violations:
            failed += 1
            for violation in violations:
                print(f"{path}: {violation}")
        else:
            print(f"{path}: ok")
    return 1 if failed else 0


def run_compose(session_root: str | None) -> Composition:
    """
    Compose from the process environment.

    ``session_root`` falls back to ``$SESSION_ROOT``, then the working
    directory. Returns the composition. Raises what the composer raises.
    """
    root = Path(session_root or os.environ.get("SESSION_ROOT") or ".").resolve()
    path_dirs = [Path(entry) for entry in os.environ.get("PATH", "").split(os.pathsep)]
    return compose(os.environ, root, Path.home(), path_dirs)
