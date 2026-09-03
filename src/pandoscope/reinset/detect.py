"""The claude-code detector: harness signals to ``detected`` keys."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from pandoscope.reinset.principal import UNKNOWN, principal_id

TOOL_PROBES = ("ghx", "disambiguate", "prek", "uv", "node", "gh")
COPIER_ANSWERS = ".copier-answers.agentic.yml"
SALT_ENV = "REINSET_ORG_SALT"


def detect(
    env: Mapping[str, str],
    session_root: Path,
    home: Path,
    path_dirs: list[Path],
) -> dict[str, Any]:
    """
    Read every ``detected`` key from ``env`` and the filesystem.

    Returns the ``detected`` mapping of the answers file. Every value is a
    fact or ``unknown``; the email never enters the result, only its
    principal id. Raises nothing: an unreadable clone is skipped.
    """
    claude_code = env.get("CLAUDECODE") == "1"
    return {
        "harness": "claude-code" if claude_code else UNKNOWN,
        "harness_version": env.get("CLAUDE_CODE_VERSION") or UNKNOWN,
        "environment": _environment(env),
        "environment_variant": env.get("CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE")
        or UNKNOWN,
        "session_id": env.get("CLAUDE_CODE_SESSION_ID") or UNKNOWN,
        # D17: a Routine fire is the one measured spawn signal.
        "spawned": env.get("CLAUDE_CODE_ENTRYPOINT") == "remote_trigger",
        "identity": principal_id(env.get("CLAUDE_CODE_USER_EMAIL"), env.get(SALT_ENV)),
        # No measured source yet for either value (skills#179 §3.1).
        "model": {"configured": UNKNOWN, "served": UNKNOWN},
        "tools": _tools(session_root, home, path_dirs),
        "repos": _repos(session_root),
    }


def _environment(env: Mapping[str, str]) -> str:
    if env.get("CLAUDE_CODE_REMOTE") == "true":
        return "ccow"
    if env.get("GITHUB_ACTIONS") == "true":
        return "actions"
    return "local"


def _tools(session_root: Path, home: Path, path_dirs: list[Path]) -> list[str]:
    binaries = [
        name
        for name in TOOL_PROBES
        if any(os.access(directory / name, os.X_OK) for directory in path_dirs)
    ]
    skill_roots = [home / ".claude" / "skills"]
    skill_roots += [
        clone / ".claude" / "skills" for clone in sorted(session_root.iterdir())
    ]
    skills = sorted(
        {
            entry.name
            for root in skill_roots
            if root.is_dir()
            for entry in root.iterdir()
            if entry.is_dir()
        }
    )
    return sorted(binaries) + skills


def _repos(session_root: Path) -> list[dict[str, str]]:
    repos = []
    for clone in sorted(session_root.iterdir()):
        answers_file = clone / COPIER_ANSWERS
        if not answers_file.is_file():
            continue
        answers = yaml.safe_load(answers_file.read_text())
        if not isinstance(answers, dict):
            continue
        repos.append(
            {
                "path": str(clone),
                "slug": str(answers.get("agentic_project_slug", UNKNOWN)),
                "kind": str(answers.get("agentic_project_kind", UNKNOWN)),
                "forge": str(answers.get("agentic_forge", UNKNOWN)),
            }
        )
    return repos
