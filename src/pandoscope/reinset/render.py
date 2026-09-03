"""Render the session's CLAUDE.md from the composed answers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pandoscope.reinset.profiles import Profile

MARKER = "<!-- managedBy: pandoscope compose -->"
UNCONFIGURED = (
    "SESSION UNCONFIGURED: no intent reference reached this session, so no "
    "role is set and nothing is installed. There is no default role. Tell "
    "the user at the start of your reply."
)
DECLARATION = (
    "To run as orchestrator, start a fresh session with REINSET_REF set to "
    "an intent reference (<repo>@<sha>:<path>) whose file declares "
    "`role: orchestrator`."
)


DECLARED_GENERAL = (
    "Role: general, declared by the intent reference. This session is "
    "configured and nothing is installed beyond this render."
)


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
    lines: list[str] = []
    for error in errors:
        lines.append(f"COMPOSER ERROR: {error}")
    for mismatch in answers.get("mismatches", []):
        lines.append(
            f"MISMATCH {mismatch['key']}: passed={mismatch['passed']} "
            f"detected={mismatch['detected']} resolved_to={mismatch['resolved_to']}"
        )
    if lines:
        lines.append("")
    if profile.role == "general":
        # D15 either way: nothing installed. Declared general (a reference
        # arrived) is configured; no reference is the loud state.
        if answers.get("passed") is not None:
            lines += ["# Role: general", "", DECLARED_GENERAL, ""]
        else:
            lines += ["# UNCONFIGURED", "", UNCONFIGURED, "", DECLARATION, ""]
        return "\n".join(lines)
    lines += [
        f"# Role: {profile.role}",
        "",
        f"Profile: {profile.path} (layer: {profile.layer}).",
    ]
    summary = profile.data.get("summary")
    if summary:
        lines += ["", str(summary)]
    skills = profile.data.get("skills") or []
    if skills:
        lines += ["", "## Skills", ""]
        lines += [f"- {skill}" for skill in skills]
    prose = profile.data.get("prose")
    if prose:
        lines += ["", str(prose).rstrip()]
    lines.append("")
    return "\n".join(lines)


def write_render(target: Path, text: str) -> None:
    """
    Rewrite ``target`` whole, marker first.

    Raises UnmanagedTargetError when ``target`` exists without the marker.
    """
    if target.exists() and MARKER not in target.read_text():
        msg = (
            f"{target} exists and is not managed by pandoscope compose "
            "— not overwriting"
        )
        raise UnmanagedTargetError(msg)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{MARKER}\n{text}")
