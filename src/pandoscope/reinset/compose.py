"""The composer entry point: detect, receive, resolve, compare, write, render."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pandoscope.reinset.compare import compare
from pandoscope.reinset.detect import detect
from pandoscope.reinset.intent import IntentError, resolve_intent
from pandoscope.reinset.profiles import load_profile
from pandoscope.reinset.receive import find_reference, parse_reference
from pandoscope.reinset.render import render, write_render

ANSWERS_ENV = "REINSET_ANSWERS"


@dataclass
class Composition:
    """What one composer run produced."""

    answers: dict[str, Any]
    answers_path: Path
    render_path: Path
    render_text: str
    errors: list[str] = field(default_factory=list)


def compose(
    env: Mapping[str, str],
    session_root: Path,
    home: Path,
    prompt: str | None,
    path_dirs: list[Path],
) -> Composition:
    """
    Run one composition and write the answers file and the render.

    Returns the composition. Composer errors (a reference without a role,
    an unresolvable reference) are rendered, never raised: the session
    must hear them. Raises UnmanagedTargetError from the render step.
    """
    detected = detect(env, session_root, home, path_dirs)
    reference = find_reference(env, prompt)
    errors: list[str] = []
    passed: dict[str, Any] | None = None
    if reference is not None:
        try:
            passed = resolve_intent(parse_reference(reference), session_root)
        except (ValueError, IntentError) as error:
            errors.append(str(error))
    resolved, mismatches = compare(detected, passed)
    answers = {
        "detected": detected,
        "passed": passed,
        "resolved": resolved,
        "mismatches": mismatches,
        "reference": reference,
        "errors": errors,
    }
    answers_path = Path(
        env.get(ANSWERS_ENV)
        or home / ".claude" / "reinset" / f"{detected['session_id']}.yml"
    )
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    answers_path.write_text(yaml.safe_dump(answers, sort_keys=False))
    profile = load_profile(resolved["role"], session_root)
    text = render(answers, profile, errors)
    render_path = home / ".claude" / "CLAUDE.md"
    write_render(render_path, text)
    return Composition(answers, answers_path, render_path, text, errors)
