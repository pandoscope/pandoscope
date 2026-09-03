"""Command-line interface."""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from pandoscope import __version__
from pandoscope.reinset.compose import ANSWERS_ENV, Composition, compose
from pandoscope.reinset.sender import Spawned, spawn
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
    compose_parser.add_argument(
        "--prompt-file",
        default=None,
        help="file holding the session's initial prompt, '-' for stdin",
    )
    spawn_parser = subparsers.add_parser(
        "spawn", help="spawn a worker session with an intent reference (skills#179)"
    )
    spawn_parser.add_argument("--role", required=True, help="the child's role")
    spawn_parser.add_argument(
        "--task-file", required=True, help="file holding the task text, '-' for stdin"
    )
    spawn_parser.add_argument("--thread", default=None, help="work-ledger thread")
    spawn_parser.add_argument(
        "--ticket", action="append", default=[], help="owner/repo#n (repeatable)"
    )
    spawn_parser.add_argument("--principal", default=None, help="principal id")
    spawn_parser.add_argument("--dojo", action="store_true")
    spawn_parser.add_argument("--debug", action="store_true")
    spawn_parser.add_argument("--session-root", default=None)
    spawn_parser.add_argument(
        "--dry-run", action="store_true", help="mint and render, write and fire nothing"
    )
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
        print(run_compose(args.session_root, args.prompt_file).render_text, end="")
    if args.command == "spawn":
        result = run_spawn(args)
        print(f"{result.spawn_id} {result.reference}")
        if result.session_url:
            print(result.session_url)
    return 0


def run_spawn(args: argparse.Namespace) -> Spawned:
    """
    Spawn from the process environment and the caller's answers file.

    Reads ``$REINSET_ANSWERS`` for the spawner identity, the task from
    ``--task-file`` (``-`` for stdin). Returns the spawn result; raises
    SpawnError from the sender.
    """
    root = Path(args.session_root or os.environ.get("SESSION_ROOT") or ".").resolve()
    answers_path = os.environ.get(ANSWERS_ENV)
    answers = None
    if answers_path and Path(answers_path).is_file():
        answers = yaml.safe_load(Path(answers_path).read_text())
    task = (
        sys.stdin.read() if args.task_file == "-" else Path(args.task_file).read_text()
    )
    fields = {
        "role": args.role,
        "principal": args.principal,
        "thread": args.thread,
        "tickets": args.ticket,
        "dojo": args.dojo,
        "debug": args.debug,
    }
    return spawn(
        os.environ, root, answers, fields, task, http_post, dry_run=args.dry_run
    )


def http_post(url: str, headers: dict[str, str], data: bytes) -> tuple[int, bytes]:
    """POST ``data`` to ``url``; returns (status, body) without raising on 4xx/5xx."""
    if not url.startswith("https://"):
        msg = f"refusing a non-https fire URL: {url}"
        raise ValueError(msg)
    request = urllib.request.Request(  # noqa: S310 — https checked above
        url, data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310 — https literal
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def run_compose(session_root: str | None, prompt_file: str | None) -> Composition:
    """
    Compose from the process environment.

    ``session_root`` falls back to ``$SESSION_ROOT``, then the working
    directory; ``prompt_file`` is read whole, ``-`` meaning stdin.
    Returns the composition; raises what the composer raises.
    """
    root = Path(session_root or os.environ.get("SESSION_ROOT") or ".").resolve()
    prompt = None
    if prompt_file == "-":
        prompt = sys.stdin.read()
    elif prompt_file is not None:
        prompt = Path(prompt_file).read_text()
    path_dirs = [Path(entry) for entry in os.environ.get("PATH", "").split(os.pathsep)]
    return compose(os.environ, root, Path.home(), prompt, path_dirs)
