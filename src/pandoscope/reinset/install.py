"""Install the role's bundle: the profile's skills, rendered into ~/.claude/skills."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pandoscope.reinset.profiles import Profile

MARKER_FILE = ".pandoscope-compose"


@dataclass
class InstallReport:
    """What one install pass did."""

    installed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def find_skill(name: str, session_root: Path, repos: list[dict[str, Any]]) -> Path | None:
    """Return the source directory for ``name``, or None when no layer has it."""
    raise NotImplementedError


def install_bundle(
    profile: Profile,
    session_root: Path,
    home: Path,
    repos: list[dict[str, Any]],
    *,
    prune: bool,
) -> InstallReport:
    """Render the profile's skills into ``home/.claude/skills``."""
    raise NotImplementedError
