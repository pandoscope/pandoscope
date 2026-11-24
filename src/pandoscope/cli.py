"""Command-line interface."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from pandoscope import __version__
from pandoscope.reinset.compose import Composition, compose, declare
from pandoscope.reinset.order import (
    ShortcodeError,
    find_shortcodes,
    guard_one_map,
    load_shortcodes,
    validate_order,
)
from pandoscope.reinset.role import RoleRefused
from pandoscope.stamp import TEMPLATE_URL, parse_data, stamp

# `pandoscope compose --declare` exits with this code when the role line
# sets nothing. meta's prompt hook reads it (environment/hooks/role-gate-prompt.sh).
DECLARATION_REFUSED = 3


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
    compose_parser.add_argument(
        "--declare",
        default=None,
        metavar="ROLE",
        help=(
            "compose ROLE for a role line in a prompt (meta#194); "
            f"exit {DECLARATION_REFUSED} and print the reason "
            "when the line sets nothing"
        ),
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
        if args.declare is None:
            print(run_compose(args.session_root).render_text, end="")
            return 0
        try:
            composition = run_declare(args.declare, args.session_root)
        except RoleRefused as refusal:
            print(f"ROLE LINE REFUSED: {refusal}")
            return DECLARATION_REFUSED
        print(composition.render_text, end="")
    if args.command == "order":
        return run_order_check(args.files)
    if args.command == "shortcodes":
        return run_shortcodes_check(args.file)
    return 0


def run_shortcodes_check(file: str) -> int:
    """
    Check the waybill's shortcode map alone. Print what fails. Return 1 when it fails.

    ``file`` is the map under any name: ``<waybill>/shortcodes.json``,
    or a candidate that is to replace it.
    Runs the loader first: the schema and the loader's two rules.
    Then the guard against a second map in the file's folder,
    with ``file`` as the one source.
    Prints ``<file>: ok`` and returns 0 when the map passes.
    """
    path = Path(file)
    try:
        load_shortcodes(path)
        guard_one_map(path.resolve().parent, path)
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
        else:
            print(f"{path}: ok")
    return 1 if failed else 0


def run_compose(session_root: str | None) -> Composition:
    """
    Compose from the process environment.

    ``session_root`` falls back to ``$SESSION_ROOT``, then the working
    directory. Returns the composition. Raises what the composer raises.
    """
    root, path_dirs = _session(session_root)
    return compose(os.environ, root, Path.home(), path_dirs)


def run_declare(role: str, session_root: str | None) -> Composition:
    """
    Compose ``role`` for a role line, from the process environment.

    ``session_root`` resolves as in ``run_compose``. Returns the composition.
    Raises RoleRefused, with nothing changed, when the line sets nothing.
    """
    root, path_dirs = _session(session_root)
    return declare(role, os.environ, root, Path.home(), path_dirs)


def _session(session_root: str | None) -> tuple[Path, list[Path]]:
    root = Path(session_root or os.environ.get("SESSION_ROOT") or ".").resolve()
    path_dirs = [Path(entry) for entry in os.environ.get("PATH", "").split(os.pathsep)]
    return root, path_dirs
