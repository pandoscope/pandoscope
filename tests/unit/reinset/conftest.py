"""Fixtures: measured CCoW environment dumps and a sandboxed session root."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Measured 2026-09-03 (skills#179 §3.1).
# Values that are ids, emails or URLs are stand-ins: the dumps record
# them as <set>. Run 7 is a Routine-fired session, run 5 a UI-created one.
MEASURED_COMMON = {
    "CLAUDECODE": "1",
    "CLAUDE_CODE_CHILD_SESSION": "1",
    "CLAUDE_CODE_REMOTE": "true",
    "CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE": "cloud_default",
    "CLAUDE_CODE_VERSION": "2.1.42",
    "CLAUDE_CODE_SESSION_ID": "sess-fixture-0001",
    "CLAUDE_CODE_REMOTE_SESSION_ID": "sess-fixture-0001",
    "CLAUDE_CODE_USER_EMAIL": "Principal@Example.test",
    "CLAUDE_EFFORT": "high",
    "SESSION_MEMORY_URL": "https://forge.example.test/org/session-memory.git",
}
ENV_RUN7_FIRED = {**MEASURED_COMMON, "CLAUDE_CODE_ENTRYPOINT": "remote_trigger"}
ENV_RUN5_UI = {**MEASURED_COMMON, "CLAUDE_CODE_ENTRYPOINT": "remote"}
ORG_SALT = "fixture-org-salt"


def git(cwd: Path, *args: str) -> str:
    """Run git in ``cwd`` and return stdout, raising on failure."""
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(cwd), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def session_root(tmp_path: Path) -> Path:
    """A session root with a session-memory clone and two stamped clones."""
    root = tmp_path / "session"
    root.mkdir()
    store = root / "session-memory"
    store.mkdir()
    git(store, "init", "-q", "-b", "main")
    git(store, "config", "user.email", "test@example.test")
    git(store, "config", "user.name", "test")
    (store / "README.md").write_text("session-memory\n")
    git(store, "add", "-A")
    git(store, "commit", "-q", "-m", "chore: seed")
    for slug, kind in (("skills", "skills"), ("meta", "ops")):
        clone = root / slug
        clone.mkdir()
        (clone / ".copier-answers.agentic.yml").write_text(
            f"agentic_project_slug: {slug}\n"
            f"agentic_project_kind: {kind}\n"
            "agentic_forge: github\n"
        )
    return root


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A sandboxed HOME."""
    path = tmp_path / "home"
    (path / ".claude").mkdir(parents=True)
    return path


@pytest.fixture
def path_dirs(tmp_path: Path) -> list[Path]:
    """A PATH holding two of the probed tools and one stranger."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("uv", "node", "stranger"):
        tool = bin_dir / name
        tool.write_text("#!/bin/sh\n")
        tool.chmod(0o755)
    return [bin_dir]


def commit(cwd: Path, name: str) -> str:
    """Commit one new file in ``cwd`` and return the commit sha."""
    (cwd / name).write_text(f"{name}\n")
    git(cwd, "add", "-A")
    git(cwd, "commit", "-q", "-m", f"chore: {name}")
    return git(cwd, "rev-parse", "HEAD")


def pr_clone(
    session_root: Path, name: str, number: int, *, on_main: bool = False
) -> str:
    """
    Clone a repository whose pull request ``number`` stacks on ``feature``.

    The origin holds ``main``, ``feature`` one commit above it,
    a stale ``old`` below ``main``,
    and ``refs/pull/<n>/head`` one commit above ``feature``.
    The clone lands at ``<session_root>/<name>``.
    Returns the head sha.
    With ``on_main`` the pull request forks from ``main`` instead,
    ``main`` then moves on, and ``feature`` merges into it.
    """
    work = session_root.parent / f"{name}-origin-work"
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    git(work, "config", "user.email", "test@example.test")
    git(work, "config", "user.name", "test")
    commit(work, "seed")
    git(work, "branch", "old")
    commit(work, "main-2")
    git(work, "switch", "-q", "-c", "feature")
    commit(work, "feature-1")
    if on_main:
        git(work, "switch", "-q", "-c", "pr", "main")
    head = commit(work, "pr-1")
    git(work, "update-ref", f"refs/pull/{number}/head", head)
    git(work, "reset", "-q", "--hard", "HEAD~1")
    git(work, "switch", "-q", "main")
    if on_main:
        git(work, "branch", "-q", "-D", "pr")
        commit(work, "main-3")
        git(work, "merge", "-q", "--no-edit", "feature")
    origin = session_root.parent / f"{name}-origin.git"
    git(session_root.parent, "clone", "-q", "--mirror", str(work), str(origin))
    git(session_root, "clone", "-q", str(origin), name)
    # The clone names its forge repository, as a session clone does;
    # git fetches from the local mirror in its place.
    forge = f"https://github.com/pandoscope/{name}"
    git(session_root / name, "remote", "set-url", "origin", forge)
    git(session_root / name, "config", f"url.{origin}.insteadOf", forge)
    # A session clone carries no origin/HEAD (measured 2026-09-24).
    git(session_root / name, "remote", "set-head", "origin", "-d")
    return head
