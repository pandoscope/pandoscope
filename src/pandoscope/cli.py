"""Command-line interface."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from pandoscope import __version__
from pandoscope.reinset.compose import Composition, compose
from pandoscope.reinset.order import (
    ShortcodeError,
    find_shortcodes,
    load_shortcodes,
    validate_order,
)
from pandoscope.reinset.order_name import name_pattern
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
    shortcodes_parser = subparsers.add_parser(
        "shortcodes", help="the waybill's shortcode map (pandoscope#59)"
    )
    shortcodes_sub = shortcodes_parser.add_subparsers(
        dest="shortcodes_command", required=True
    )
    shortcodes_check = shortcodes_sub.add_parser(
        "check", help="check a shortcodes.json alone, without an order"
    )
    shortcodes_check.add_argument("file", help="the waybill's shortcodes.json")
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
    if args.command == "shortcodes":
        return run_shortcodes_check(args.file)
    return 0


def run_shortcodes_check(file: str) -> int:
    """
    Check the waybill's shortcode map alone. Print what fails. Return 1 when it fails.

    ``file`` is ``<waybill>/shortcodes.json``.
    Runs the guard against a second map in the file's folder,
    then the loader: the schema and the loader's two rules.
    Prints ``<file>: ok`` and returns 0 when the map passes.
    """
    path = Path(file)
    try:
        find_shortcodes(path.resolve().parent)
        load_shortcodes(path)
    except ShortcodeError as error:
        print(f"{path}: {error}")
        return 1
    print(f"{path}: ok")
    return 0


def run_order_check(files: list[str]) -> int:
    """
    Validate each order file. Print every violation. Return 1 when any file fails.

    Each file is ``<waybill>/orders/<name>.yml``; the subject's shortcode
    comes from ``<waybill>/shortcodes.json``, and a file without it fails.
    An order whose role has no name pattern passes with a line that says
    its name went unchecked.
    """
    failed = 0
    for name in files:
        path = Path(name)
        try:
            data = yaml.safe_load(path.read_text())
            shortcodes = load_shortcodes(find_shortcodes(path.resolve().parent.parent))
        except (OSError, yaml.YAMLError, ShortcodeError) as error:
            print(f"{path}: cannot check: {error}")
            failed += 1
            continue
        violations = validate_order(data, path.stem, shortcodes)
        if violations:
            failed += 1
            for violation in violations:
                print(f"{path}: {violation}")
        elif name_pattern(data["role"]) is None:
            print(
                f"{path}: ok, but the role {data['role']!r} has no name pattern, "
                "so only its tier and the file name are checked"
            )
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
