"""The forge side of org init: list and create repos through the gh CLI."""

from __future__ import annotations

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


def find_board(org: str, run: Run) -> tuple[str | None, str]:
    """
    Return the URL of ``org``'s project board and how it was found, creating none.

    A recorded board is kept ("recorded");
    without one, the org's only open project is adopted ("adopted");
    with no open project there is no board (None, "none").
    Raises ValueError listing the open projects when there are several,
    and what ``run`` raises.
    """
    raise NotImplementedError


def ensure_board(org: str, run: Run, *, dry_run: bool) -> tuple[str | None, str]:
    """
    Return the URL of ``org``'s project board and how it was found.

    The org variable PROJECT_BOARD_URL records the board the workflows file into.
    A recorded board is kept ("recorded").
    Without one, the org's only open project is adopted ("adopted").
    An org with no open project gets one titled after the org:
    "created", or "would create" under ``dry_run``, with no URL yet.
    Raises ValueError listing the open projects when there are several,
    because choosing between them is the principal's call.
    Raises what ``run`` raises.
    """
    recorded = run(
        [
            "gh",
            "api",
            f"orgs/{org}/actions/variables",
            "--paginate",
            "--jq",
            '.variables[] | select(.name == "PROJECT_BOARD_URL") | .value',
        ],
        None,
    ).strip()
    if recorded:
        return recorded, "recorded"
    projects = run(
        [
            "gh",
            "project",
            "list",
            "--owner",
            org,
            "--limit",
            "100",
            "--format",
            "json",
            "--jq",
            '.projects[] | select(.closed | not) | "\\(.url)\\t\\(.title)"',
        ],
        None,
    ).splitlines()
    if len(projects) == 1:
        return projects[0].split("\t")[0], "adopted"
    if len(projects) > 1:
        listing = "\n".join(f"  {line}" for line in projects)
        msg = (
            f"org={org!r} has no recorded board and {len(projects)} open projects;"
            f" pass --board-url with one of them:\n{listing}"
        )
        raise ValueError(msg)
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


def repo_present(owner: str, name: str, run: Run) -> bool:
    """
    Return whether ``owner/name`` exists on the forge; ``owner`` is an org or a user.

    Raises what ``run`` raises for any answer but "not found",
    so a missing permission is never read as an absent repo,
    and ValueError when the lookup answers with anything but the repo's name.
    """
    try:
        out = run(["gh", "api", f"repos/{owner}/{name}", "--jq", ".name"], None)
    except RuntimeError as error:
        if "HTTP 404" in str(error):
            return False
        raise
    if out.strip().lower() != name.lower():
        msg = f"looking up {owner}/{name} answered {out.strip()!r}, not the repo's name"
        raise ValueError(msg)
    return True


def branches(owner: str, name: str, run: Run) -> list[str]:
    """Return the names of ``owner/name``'s branches; an empty repo has none."""
    out = run(
        ["gh", "api", f"repos/{owner}/{name}/branches", "--paginate", "--jq", ".[].name"],
        None,
    )
    return [line for line in out.splitlines() if line]
