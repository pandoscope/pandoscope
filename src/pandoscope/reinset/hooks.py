"""
Render the role's hooks: the profile's hook entries, resolved to installed skills.

The CLI captures hook registration at startup (see meta's environment README),
so a role cannot register hooks live.
The environment registers one dispatcher per event instead.
This step renders the profile's hooks to the one file
that the dispatcher reads at every fire.
The file changes per role, and the registration stays the same.

The file also carries the role's tool gate under the key ``gate``
(meta#195, meta#197): ``{"role": <role>, "closed_tools": {<tool>: <group>}}``.
The file exists exactly when the session has a role,
so meta's tool gate reads a missing file as no role.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pandoscope.reinset.profiles import Profile

EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "PreCompact")


GATE_KEY = "gate"


def render_hooks(
    profile: Profile | None,
    home: Path,
    target: Path,
    gate: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """
    Write the hooks file for ``profile`` at ``target``; return it and the errors.

    Without a profile, the file holds no hook.
    With ``gate``, the file and the returned mapping carry it under ``gate``.

    Each profile entry is ``{event, command[, matcher]}``.
    Its ``command`` is ``<skill>/<script>`` under the installed skills.
    The rendered file maps each event to a list of ``{command[, matcher]}``
    with absolute commands.
    These entries are errors and stay out of the file:
    a skill outside the bundle, a script that resolves outside its skill,
    a script missing on disk and an unknown event.
    """
    skills_dir = home / ".claude" / "skills"
    data = profile.data if profile is not None else {}
    bundle = {str(name) for name in data.get("skills") or []}
    rendered: dict[str, list[dict[str, str]]] = {}
    errors: list[str] = []
    for entry in data.get("hooks") or []:
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
    written: dict[str, Any] = dict(rendered)
    if gate is not None:
        written = {GATE_KEY: gate, **written}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{json.dumps(written, indent=1)}\n")
    return written, errors
