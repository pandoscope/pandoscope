"""Render the session's CLAUDE.md from the composed answers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pandoscope.reinset.profiles import Profile

MARKER = "<!-- managedBy: pandoscope compose -->"


class UnmanagedTargetError(Exception):
    """The render target exists and was not written by the composer."""


def render(answers: dict[str, Any], profile: Profile, errors: list[str]) -> str:
    """
    Return the CLAUDE.md text for the composed session.

    Names the role and the winning profile layer, lists the profile's
    skills, prints every composer error and every mismatch. ``general``
    carries the UNCONFIGURED notice and the one-line orchestrator
    declaration, nothing else.
    """
    raise NotImplementedError


def write_render(target: Path, text: str) -> None:
    """
    Rewrite ``target`` whole, marker first.

    Raises UnmanagedTargetError when ``target`` exists without the marker.
    """
    raise NotImplementedError
