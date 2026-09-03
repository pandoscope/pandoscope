"""The claude-code detector: harness signals to ``detected`` keys."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

TOOL_PROBES = ("ghx", "disambiguate", "prek", "uv", "node", "gh")


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
    raise NotImplementedError
