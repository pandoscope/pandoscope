"""
Render the session's CLAUDE.md from the composed answers.

The render opens with one line that names the role, ``# Role: <role>``,
or says that the session has none, ``# No role`` (meta#195).
The instruction file that every repository checks in
tells a session without that line in its context to do no work.
meta's prompt hook relays this render to the model at every turn
while the session has no role, and on the turn that sets one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pandoscope.reinset.profiles import Profile
from pandoscope.reinset.role import DECLARABLE

MARKER = "<!-- managedBy: pandoscope compose -->"
NO_ROLE_HEADING = "# No role"
NO_SOURCE = "no waybill order, no environment role and no role line named a role"
DECLARE_HINT = "Declare one: send a message whose first line is " + " or ".join(
    f"`role: {role}`" for role in DECLARABLE
)
ORDER_HINT = "Correct the waybill order and fire it again"


class UnmanagedTargetError(Exception):
    """The render target exists and was not written by the composer."""


def render(
    answers: dict[str, Any],
    profile: Profile | None,
    errors: list[str],
    task: str | None = None,
    *,
    order_session: bool = False,
) -> str:
    """
    Return the CLAUDE.md text for the composed session.

    With a ``profile``, the text names the role, its source and the winning
    profile layer, lists the profile's skills,
    and ends with the session's task when the composer composed one.
    Without one, the text is the no-role reply that ``no_role_reply`` builds.
    """
    if profile is None:
        return no_role_reply(errors, order_session=order_session)
    source = answers.get("resolved", {}).get("role_source")
    lines = [
        f"# Role: {profile.role}",
        "",
        f"Source: {source}. Profile: {profile.path} (layer: {profile.layer}).",
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


def no_role_reply(errors: list[str], *, order_session: bool) -> str:
    """
    Return the render of a session without a role.

    It says that every tool but the one that reads notifications is closed,
    prints every composer error,
    and asks for one fixed reply that names the reason.
    The reply shows the declaration line,
    or, in a session that an order started, asks for a corrected order:
    there a role line opens nothing (meta#195).
    """
    reason = "; ".join(errors) if errors else NO_SOURCE
    hint = ORDER_HINT if order_session else DECLARE_HINT
    lines = [NO_ROLE_HEADING, ""]
    lines += [f"COMPOSER ERROR: {error}" for error in errors]
    if errors:
        lines.append("")
    lines += [
        "This session has no role. Every tool except the one that reads "
        "notifications is closed, so the session does no work.",
        "",
        "Reply to every message with the text below and nothing else, "
        "until a role is set:",
        "",
        f"> This session has no role and does no work. Reason: {reason}. {hint}.",
        "",
    ]
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
