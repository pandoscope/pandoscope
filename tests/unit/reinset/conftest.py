"""Fixtures: measured CCoW environment dumps and a sandboxed session root."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

# Measured 2026-09-03 (skills#179 §3.1, intents/ on session-memory main).
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

INTENT_IMPLEMENTER = """\
spawn_id: spawn-7b2d
spawner: p-4c1e9a7b02d3
origin: spawner
role: implementer
thread: per-session-agent-config
tickets: [pandoscope/skills#130]
dojo: false
debug: false
overrides: []
"""

INTENT_NO_ROLE = """\
spawn_id: spawn-7b2e
spawner: p-4c1e9a7b02d3
origin: spawner
thread: per-session-agent-config
"""


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
def commit_intent(session_root: Path) -> Callable[[str, str], str]:
    """Commit an intent file to the session-memory clone; returns the sha."""

    def _commit(path: str, text: str) -> str:
        store = session_root / "session-memory"
        target = store / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        git(store, "add", "-A")
        git(store, "commit", "-q", "-m", f"intent: {path}")
        return git(store, "rev-parse", "HEAD")

    return _commit


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
