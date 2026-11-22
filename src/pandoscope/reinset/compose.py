"""The composer entry point: detect, resolve the role, install, write, render."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pandoscope.reinset.detect import detect
from pandoscope.reinset.hooks import render_hooks
from pandoscope.reinset.implement import ImplementError, implementer_task
from pandoscope.reinset.install import install_bundle, remove_bundle
from pandoscope.reinset.principal import UNKNOWN
from pandoscope.reinset.profiles import Profile, load_profile
from pandoscope.reinset.receive import Order, OrderError, find_order, order_name
from pandoscope.reinset.render import render, write_render
from pandoscope.reinset.review import ReviewError, hydrate
from pandoscope.reinset.role import (
    DECLARED,
    ENVIRONMENT,
    ORDER,
    RoleRefused,
    check_declaration,
    environment_role,
    tool_gate,
)

ANSWERS_ENV = "REINSET_ANSWERS"
CLAUDE_CODE = "claude-code"
HOOKS_ENV = "REINSET_HOOKS"


@dataclass
class Composition:
    """What one composer run produced. ``role`` is None when the session has no role."""

    answers: dict[str, Any]
    answers_path: Path
    hooks_path: Path
    render_path: Path
    render_text: str
    role: str | None
    errors: list[str] = field(default_factory=list)


def declare(
    role: str,
    env: Mapping[str, str],
    session_root: Path,
    home: Path,
    path_dirs: list[Path],
) -> Composition:
    """
    Compose ``role`` for a role line in a prompt (meta#194).

    Returns the composition, as ``compose`` does.
    Raises RoleRefused, before anything changes on disk,
    when the role line may not set ``role``; ``check_declaration`` says when.
    """
    check_declaration(role, env, order_session=order_name(env) is not None)
    return compose(env, session_root, home, path_dirs, declared=role)


def compose(
    env: Mapping[str, str],
    session_root: Path,
    home: Path,
    path_dirs: list[Path],
    declared: str | None = None,
) -> Composition:
    """
    Run one composition and write the answers file and the render.

    The role comes from one of three sources (meta#194), first match wins:
    the waybill order that the Routine fired from,
    the role ``declared`` by a role line (``declare`` checks it),
    a role that a role line declared earlier in this session,
    and the worker role that the environment names.
    In a session that an order started, only the order counts.
    Without a role the composer composes nothing (meta#195):
    it installs no skill, removes what an earlier role installed,
    deletes the hooks file and renders the no-role reply.
    A composer error leaves the session without a role.
    The errors are an order off the schema, a review or implementer error
    from composing the task,
    an environment that names a role it may not set,
    a bundle skill or hook with no source, and a harness with no skill format.
    The composer renders its errors and never raises them,
    because the session must hear them.
    The render step raises UnmanagedTargetError.
    """
    detected = detect(env, session_root, home, path_dirs)
    answers_path = Path(
        env.get(ANSWERS_ENV)
        or home / ".claude" / "reinset" / f"{detected['session_id']}.yml"
    )
    hooks_path = Path(env.get(HOOKS_ENV) or home / ".claude" / "reinset" / "hooks.json")
    errors: list[str] = []
    task: str | None = None
    order: Order | None = None
    order_session = order_name(env) is not None
    role: str | None = None
    source: str | None = None
    if order_session:
        try:
            order = find_order(env, session_root)
            if order is not None and order.role == "reviewer":
                task = hydrate(session_root, order)
            if order is not None and order.role == "implementer":
                task = implementer_task(session_root, order)
        except (OrderError, ReviewError, ImplementError) as error:
            errors.append(str(error))
            order = None
        if order is not None:
            role, source = order.role, ORDER
    elif declared is not None:
        role, source = declared, DECLARED
    else:
        role = _earlier_declaration(answers_path, detected)
        source = DECLARED if role is not None else None
        if role is None:
            try:
                role = environment_role(env)
            except RoleRefused as refusal:
                errors.append(str(refusal))
            source = ENVIRONMENT if role is not None else None
    harness = detected.get("harness", UNKNOWN)
    installed: list[str] = []
    hooks: dict[str, Any] = {}
    profile: Profile | None = None
    if role is not None:
        profile = load_profile(role, session_root)
        installed, hooks = _install(
            profile, harness, session_root, home, detected, hooks_path, errors
        )
    if errors:
        # meta#195: a composer error leaves the session without a role.
        role, source, profile, installed, hooks = None, None, None, [], {}
    if role is None:
        remove_bundle(home)
        hooks_path.unlink(missing_ok=True)
    answers: dict[str, Any] = {
        "detected": detected,
        "resolved": {
            "harness": harness,
            "environment": detected.get("environment", UNKNOWN),
            "role": role,
            "role_source": source,
            "principal": detected.get("identity", UNKNOWN),
            "model": detected.get("model", {}).get("served", UNKNOWN),
        },
        "order": _order_answers(order, session_root),
        "errors": errors,
        "installed": installed,
        "hooks": hooks,
    }
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    answers_path.write_text(yaml.safe_dump(answers, sort_keys=False))
    text = render(answers, profile, errors, task=task, order_session=order_session)
    render_path = home / ".claude" / "CLAUDE.md"
    write_render(render_path, text)
    return Composition(
        answers, answers_path, hooks_path, render_path, text, role, errors
    )


def _install(
    profile: Profile,
    harness: str,
    session_root: Path,
    home: Path,
    detected: dict[str, Any],
    hooks_path: Path,
    errors: list[str],
) -> tuple[list[str], dict[str, Any]]:
    """
    Install the role's bundle and render its hooks and gate.

    Appends each error to ``errors``.
    Returns the installed skill names and the rendered hooks file.
    """
    # resolved.harness selects the skill format (skills#179 §4).
    # Claude Code's is the only one known, so another harness gets no bundle.
    gate = tool_gate(profile.role)
    if harness != CLAUDE_CODE:
        if profile.data.get("skills") or profile.data.get("hooks"):
            errors.append(
                f"harness {harness!r} has no known skill format; "
                "the role's bundle is not installed"
            )
            return [], {}
        hooks, hook_errors = render_hooks(profile, home, hooks_path, gate)
        errors += hook_errors
        return [], hooks
    report = install_bundle(profile, session_root, home, detected["repos"], prune=True)
    errors += report.errors
    hooks, hook_errors = render_hooks(profile, home, hooks_path, gate)
    errors += hook_errors
    return report.installed, hooks


def _earlier_declaration(answers_path: Path, detected: dict[str, Any]) -> str | None:
    """
    Return the role that a role line set earlier in this session, or None.

    Every SessionStart composes again, a compaction's included.
    The answers file of the same session id keeps a declared role across it.
    An unknown session id matches nothing.
    """
    session_id = detected.get("session_id", UNKNOWN)
    # DECISION:FALLBACK — missing: CLAUDE_CODE_SESSION_ID. Instead: no
    # earlier declaration carries over, so after a compaction the session
    # has the role of its other sources, or none. The session is told by
    # the render, which then names no declared role. Test:
    # test_an_unknown_session_id_carries_no_declaration.
    if session_id == UNKNOWN or not answers_path.is_file():
        return None
    earlier = yaml.safe_load(answers_path.read_text())
    if not isinstance(earlier, dict):
        return None
    resolved = earlier.get("resolved") or {}
    if earlier.get("detected", {}).get("session_id") != session_id:
        return None
    if resolved.get("role_source") != DECLARED:
        return None
    role = resolved.get("role")
    return str(role) if role else None


def _order_answers(order: Order | None, session_root: Path) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "path": str(order.path.relative_to(session_root)),
        "role": order.role,
        "pass": order.pass_,
        "model_tier": order.model_tier,
        "subject": order.subject,
        "tickets": order.tickets,
    }
