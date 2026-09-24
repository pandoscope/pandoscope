"""
Render the role's hooks: the profile's hook entries, resolved to installed skills.

Hook registration is captured at CLI startup (measured, meta
environment README), so a role cannot register hooks live. The profile
declares them and this step renders them to one file the environment's
dispatcher reads at fire time; the dispatcher is registered once per
event by the environment, the file changes per role.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pandoscope.reinset.profiles import Profile

EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "PreCompact")


def render_hooks(
    profile: Profile, home: Path, target: Path
) -> tuple[dict[str, Any], list[str]]:
    """
    Write the hooks file for ``profile`` at ``target``; return it and the errors.

    Each profile entry is ``{event, command[, matcher]}`` with ``command``
    as ``<skill>/<script>`` under the installed skills. The rendered
    file maps event to a list of ``{command[, matcher]}`` with absolute
    commands. An entry whose skill is not in the bundle, whose script is
    absent, or whose event is unknown is an error and is left out.
    """
    skills_dir = home / ".claude" / "skills"
    bundle = {str(name) for name in profile.data.get("skills") or []}
    rendered: dict[str, list[dict[str, str]]] = {}
    errors: list[str] = []
    for entry in profile.data.get("hooks") or []:
        event = str(entry.get("event", ""))
        command = str(entry.get("command", ""))
        skill, _, script = command.partition("/")
        if event not in EVENTS:
            errors.append(f"hook {command!r}: unknown event {event!r}; one of {EVENTS}")
            continue
        if skill not in bundle:
            errors.append(f"hook {command!r}: {skill!r} is not in the role's bundle")
            continue
        path = skills_dir / skill / script
        if not path.resolve().is_relative_to((skills_dir / skill).resolve()):
            errors.append(f"hook {command!r}: the script lies outside {skill!r}")
            continue
        if not script or not path.is_file():
            errors.append(f"hook {command!r}: {path} is not installed")
            continue
        hook = {"command": str(path)}
        if entry.get("matcher"):
            hook = {"matcher": str(entry["matcher"]), **hook}
        rendered.setdefault(event, []).append(hook)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{json.dumps(rendered, indent=1)}\n")
    return rendered, errors
