"""Resolve an intent reference to the ``passed`` block."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

from pandoscope.reinset.receive import Reference

ROLES = ("orchestrator", "implementer", "reviewer", "general", "probe")
ORIGINS = ("principal", "spawner", "webhook", "poll")
REQUIRED = ("spawn_id", "spawner", "origin")


class IntentError(Exception):
    """A reference that cannot become a valid ``passed`` block."""


def resolve_intent(reference: Reference, session_root: Path) -> dict[str, Any]:
    """
    Read ``<session_root>/<repo>`` at ``<commit>:<path>`` via git show.

    Returns the parsed ``passed`` mapping. Raises IntentError when the
    clone is absent, the object is unreachable, the file is not a mapping,
    a required key is missing, or ``role`` is absent or unknown.
    """
    text = _git_show(reference, session_root)
    passed = yaml.safe_load(text)
    where = f"{reference.repo}@{reference.commit}:{reference.path}"
    if not isinstance(passed, dict):
        msg = f"intent file is not a mapping ({where})"
        raise IntentError(msg)
    for key in REQUIRED:
        if key not in passed:
            msg = f"intent file lacks required key {key!r} ({where})"
            raise IntentError(msg)
    if "role" not in passed:
        msg = f"reinset reference names no role ({where})"
        raise IntentError(msg)
    if passed["role"] not in ROLES:
        msg = f"unknown role {passed['role']!r}, expected one of {ROLES} ({where})"
        raise IntentError(msg)
    if passed["origin"] not in ORIGINS:
        msg = (
            f"unknown origin {passed['origin']!r}, expected one of {ORIGINS} ({where})"
        )
        raise IntentError(msg)
    spawner = str(passed["spawner"])
    # D16: a principal id or a spawn id, never a session id or an email.
    if not (spawner.startswith("p-") or spawner.startswith("spawn-")):
        msg = (
            "spawner must be a principal id (p-…) or spawn id (spawn-…), "
            f"got {spawner!r} ({where})"
        )
        raise IntentError(msg)
    return passed


def _git_show(reference: Reference, session_root: Path) -> str:
    clone = session_root / reference.repo
    if not (clone / ".git").exists():
        msg = f"no clone for {reference.repo!r} under {session_root}"
        raise IntentError(msg)
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "git",
            "-C",
            str(clone),
            "show",
            f"{reference.commit}:{reference.path}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = (
            f"git show {reference.commit}:{reference.path} failed in "
            f"{clone}: {result.stderr.strip()}"
        )
        raise IntentError(msg)
    return result.stdout
