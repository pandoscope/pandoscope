"""The composer entry point: detect, receive the order, write, render."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pandoscope.reinset.detect import detect
from pandoscope.reinset.principal import UNKNOWN
from pandoscope.reinset.profiles import load_profile
from pandoscope.reinset.receive import Order, OrderError, find_order
from pandoscope.reinset.render import render, write_render
from pandoscope.reinset.review import ReviewError, hydrate

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
    path_dirs: list[Path],
) -> Composition:
    """
    Run one composition and write the answers file and the render.

    The waybill order is the only receiver (skills#195, waybill#1). It
    arrives when the Routine fires from an order branch of the waybill
    repository.
    The order names the role, the pull request, the tickets,
    and for a reviewer the pass and model tier.
    Without an order the composer sets the role general
    and renders the loud UNCONFIGURED state.
    The composer renders its own errors and never raises them,
    because the session must hear them.
    They are an order that does not validate against the schema
    and any review error from hydrating the task.
    The render step raises UnmanagedTargetError.
    """
    detected = detect(env, session_root, home, path_dirs)
    errors: list[str] = []
    task: str | None = None
    order: Order | None = None
    try:
        order = find_order(env, session_root)
        if order is not None and order.role == "reviewer":
            task = hydrate(session_root, order)
    except (OrderError, ReviewError) as error:
        errors.append(str(error))
        order = None
    resolved = {
        "harness": detected.get("harness", UNKNOWN),
        "environment": detected.get("environment", UNKNOWN),
        "role": order.role if order is not None else "general",
        "principal": detected.get("identity", UNKNOWN),
        "model": detected.get("model", {}).get("served", UNKNOWN),
    }
    answers: dict[str, Any] = {
        "detected": detected,
        "resolved": resolved,
        "order": None
        if order is None
        else {
            "path": str(order.path.relative_to(session_root)),
            "role": order.role,
            "pass": order.pass_,
            "model_tier": order.model_tier,
            "pull_request": order.pull_request,
            "tickets": order.tickets,
        },
        "errors": errors,
    }
    answers_path = Path(
        env.get(ANSWERS_ENV)
        or home / ".claude" / "reinset" / f"{detected['session_id']}.yml"
    )
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    answers_path.write_text(yaml.safe_dump(answers, sort_keys=False))
    profile = load_profile(resolved["role"], session_root)
    text = render(answers, profile, errors, task=task)
    render_path = home / ".claude" / "CLAUDE.md"
    write_render(render_path, text)
    return Composition(answers, answers_path, render_path, text, errors)
