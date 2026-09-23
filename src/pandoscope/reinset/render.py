"""Render the session's CLAUDE.md from the composed answers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pandoscope.reinset.profiles import Profile

MARKER = "<!-- managedBy: pandoscope compose -->"
UNCONFIGURED = (
    "SESSION UNCONFIGURED: no waybill order reached this session. The "
    "composer set no role and installed nothing. There is no default role. "
    "Tell the user at the start of your reply."
)
DECLARATION = (
    "To run with a role, open a pull request on the waybill repository from "
    "a branch order/<name>. Declare the role in orders/<name>.yml. The "
    "Routine then fires the session from that order."
)
DECLARED_GENERAL = (
    "Role: general, declared by the waybill order. The session is "
    "configured; nothing is installed beyond this render."
)


class UnmanagedTargetError(Exception):
    """The render target exists and was not written by the composer."""


def render(
    answers: dict[str, Any],
    profile: Profile,
    errors: list[str],
    task: str | None = None,
) -> str:
    """
    Return the CLAUDE.md text for the composed session.

    The text names the role and the winning profile layer. It lists
    the profile's skills. It prints every composer error. It ends with
    the session's task when the composer composed one. For ``general``
    the text carries the UNCONFIGURED notice or the one-line general
    declaration, nothing else.
    """
    lines: list[str] = [f"COMPOSER ERROR: {error}" for error in errors]
    if lines:
        lines.append("")
    if profile.role == "general":
        # D15 either way: nothing installed. An order that declares
        # general configures the session. No order is the loud state.
        if answers.get("order") is not None:
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
    if task:
        lines += ["", "## Task", "", task.rstrip()]
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
