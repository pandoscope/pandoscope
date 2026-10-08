"""The forge side of org init: list and create repos through the gh CLI."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from pandoscope.org.plan import Repo

Run = Callable[[Sequence[str], Path | None], str]


def run(cmd: Sequence[str], cwd: Path | None = None) -> str:
    """
    Run ``cmd`` in ``cwd`` and return its stdout.

    Raises RuntimeError naming the command, directory, exit code and stderr
    when the command exits non-zero.
    """
    try:
        done = subprocess.run(  # noqa: S603 - commands are built here, not from input
            list(cmd), cwd=cwd, check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as error:
        msg = (
            f"command failed (exit {error.returncode}) in cwd={cwd}: "
            f"{' '.join(cmd)}\nstderr: {error.stderr.strip()}"
        )
        raise RuntimeError(msg) from error
    return done.stdout


def existing_repos(org: str, run: Run) -> set[str]:
    """Return the names of the repos ``org`` already holds."""
    out = run(
        [
            "gh",
            "repo",
            "list",
            org,
            "--limit",
            "1000",
            "--json",
            "name",
            "--jq",
            ".[].name",
        ],
        None,
    )
    return {line for line in out.splitlines() if line}


def create_repo(org: str, repo: Repo, run: Run) -> None:
    """
    Create ``repo`` under ``org``.

    A stamped repo starts empty, so its stamp is the first commit on main.
    An unstamped repo gets a README, so it has a main branch at all.
    """
    cmd = [
        "gh",
        "repo",
        "create",
        f"{org}/{repo.name}",
        "--private" if repo.private else "--public",
        "--description",
        repo.purpose,
    ]
    if not repo.stamped:
        cmd.append("--add-readme")
    run(cmd, None)


def ensure_board(org: str, run: Run, *, dry_run: bool) -> tuple[str | None, str]:
    """
    Return the URL of ``org``'s project board and what happened to it.

    The event is "exists", "created" or, under ``dry_run``, "would create";
    a board that would be created has no URL yet.
    Raises what ``run`` raises.
    """
    # DECISION:SCOPE — the org's board is the open project titled after
    # the org; other projects the org holds are neither reused nor counted.
    title = json.dumps(org)
    found = run(
        [
            "gh",
            "project",
            "list",
            "--owner",
            org,
            "--format",
            "json",
            "--jq",
            f".projects[] | select(.title == {title} and (.closed | not)) | .url",
        ],
        None,
    ).splitlines()
    if found:
        return found[0], "exists"
    if dry_run:
        return None, "would create"
    created = run(
        [
            "gh",
            "project",
            "create",
            "--owner",
            org,
            "--title",
            org,
            "--format",
            "json",
            "--jq",
            ".url",
        ],
        None,
    )
    return created.strip(), "created"
