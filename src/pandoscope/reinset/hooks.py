"""Render the role's hooks: the profile's hook entries, resolved to installed skills."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pandoscope.reinset.profiles import Profile

EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "PreCompact")


def render_hooks(profile: Profile, home: Path, target: Path) -> tuple[dict[str, Any], list[str]]:
    """Write the hooks file for ``profile`` at ``target``; return it and the errors."""
    raise NotImplementedError
