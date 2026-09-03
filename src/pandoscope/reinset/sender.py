"""The CCoW sender: attach an intent reference to a child the Routine mints."""

from __future__ import annotations

import json
import secrets
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pandoscope.reinset.intent import ROLES
from pandoscope.reinset.principal import UNKNOWN

ROUTINE_ENV = "REINSET_SPAWN_ROUTINE"
TOKEN_ENV = "REINSET_SPAWN_TOKEN"  # noqa: S105 — the variable's name, never its value
FIRE_URL = "https://api.anthropic.com/v1/claude_code/routines/{routine}/fire"
BETA_HEADER = "experimental-cc-routine-2026-04-01"
STORE = "session-memory"

Http = Callable[[str, dict[str, str], bytes], tuple[int, bytes]]


class SpawnError(Exception):
    """A spawn that cannot proceed; the message never carries the token."""


@dataclass(frozen=True)
class Intent:
    """The ``passed`` block the spawner writes (skills#179 §3.2, D16)."""

    spawn_id: str
    spawner: str
    role: str
    principal: str
    origin: str = "spawner"
    spawner_spawn: str | None = None
    thread: str | None = None
    tickets: list[str] = field(default_factory=list)
    dojo: bool = False
    debug: bool = False


@dataclass(frozen=True)
class Spawned:
    """What one spawn produced."""

    spawn_id: str
    reference: str
    session_url: str | None


def mint_spawn_id(token_hex: Callable[[int], str] = secrets.token_hex) -> str:
    """Return ``spawn-<4 hex>``."""
    return f"spawn-{token_hex(2)}"


def spawner_identity(answers: Mapping[str, Any] | None) -> tuple[str, str | None]:
    """
    Return ``(spawner, spawner_spawn)`` from the caller's answers file.

    ``spawner`` is ``detected.identity``; ``spawner_spawn`` is the caller's
    own ``passed.spawn_id`` when it was spawned. Raises SpawnError when the
    identity is ``unknown`` or the answers are missing: never guessed.
    """
    if answers is None:
        msg = "no answers file: the spawner identity comes from $REINSET_ANSWERS"
        raise SpawnError(msg)
    identity = answers.get("detected", {}).get("identity", UNKNOWN)
    if identity == UNKNOWN:
        msg = "spawner identity is unknown (REINSET_ORG_SALT unset?); never guessed"
        raise SpawnError(msg)
    passed = answers.get("passed") or {}
    return str(identity), passed.get("spawn_id")


def render_intent(intent: Intent) -> str:
    """Return the intent file text: no session ids, no emails."""
    data: dict[str, Any] = {"spawn_id": intent.spawn_id, "spawner": intent.spawner}
    if intent.spawner_spawn:
        data["spawner_spawn"] = intent.spawner_spawn
    data["origin"] = intent.origin
    data["role"] = intent.role
    data["principal"] = intent.principal
    if intent.thread:
        data["thread"] = intent.thread
    data["tickets"] = list(intent.tickets)
    data["dojo"] = intent.dojo
    data["debug"] = intent.debug
    data["overrides"] = []
    return yaml.safe_dump(data, sort_keys=False)


def write_intent(session_root: Path, intent: Intent) -> str:
    """
    Commit ``intents/<spawn_id>.yml`` to the store's main and push.

    Returns the reference ``session-memory@<sha>:intents/<spawn_id>.yml``.
    Raises SpawnError when the store clone is absent or the push fails.
    """
    store = session_root / STORE
    if not (store / ".git").exists():
        msg = f"no {STORE} clone under {session_root}: the intent has nowhere to live"
        raise SpawnError(msg)
    path = Path("intents") / f"{intent.spawn_id}.yml"
    (store / path).parent.mkdir(exist_ok=True)
    (store / path).write_text(render_intent(intent))
    _git(store, "add", str(path))
    _git(store, "commit", "-q", "-m", f"intent: {intent.spawn_id} ({intent.role})")
    _git(store, "push", "-q", "origin", "HEAD:main")
    sha = _git(store, "rev-parse", "HEAD")
    return f"{STORE}@{sha}:{path.as_posix()}"


def build_payload(reference: str, task: str) -> str:
    """Return the fire text: the ``reinset:`` line, a blank line, the task."""
    return f"reinset: {reference}\n\n{task}"


def fire(env: Mapping[str, str], payload: str, http: Http) -> str | None:
    """
    POST the payload to the Routine's fire endpoint.

    The token is read from ``env`` and travels only in the Authorization
    header. Returns the minted session URL when the response carries one.
    Raises SpawnError naming the variable when either is unset, or the
    HTTP status on a non-200 answer, never the token.
    """
    for name in (ROUTINE_ENV, TOKEN_ENV):
        if not env.get(name):
            msg = f"{name} is not set in the environment"
            raise SpawnError(msg)
    headers = {
        "Authorization": f"Bearer {env[TOKEN_ENV]}",
        "anthropic-beta": BETA_HEADER,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    status, body = http(
        FIRE_URL.format(routine=env[ROUTINE_ENV]),
        headers,
        json.dumps({"text": payload}).encode(),
    )
    if status != 200:
        detail = body.decode(errors="replace")[:200]
        msg = f"routine fire answered HTTP {status}: {detail}"
        raise SpawnError(msg)
    answer = json.loads(body or b"{}")
    url = answer.get("claude_code_session_url")
    return str(url) if url else None


def spawn(
    env: Mapping[str, str],
    session_root: Path,
    answers: Mapping[str, Any] | None,
    intent_fields: dict[str, Any],
    task: str,
    http: Http,
    *,
    dry_run: bool = False,
) -> Spawned:
    """
    Mint, write, fire.

    ``intent_fields`` carries role, principal, thread, tickets, dojo, debug.
    A dry run mints and renders but writes and fires nothing; its reference
    is the rendered intent text and ``session_url`` is None.
    """
    role = intent_fields.get("role")
    if role not in ROLES:
        msg = f"unknown role {role!r}, expected one of {ROLES}"
        raise SpawnError(msg)
    spawner, spawner_spawn = spawner_identity(answers)
    intent = Intent(
        spawn_id=mint_spawn_id(),
        spawner=spawner,
        role=str(role),
        principal=str(intent_fields.get("principal") or spawner),
        spawner_spawn=spawner_spawn,
        thread=intent_fields.get("thread"),
        tickets=list(intent_fields.get("tickets") or []),
        dojo=bool(intent_fields.get("dojo")),
        debug=bool(intent_fields.get("debug")),
    )
    if dry_run:
        return Spawned(intent.spawn_id, render_intent(intent), None)
    reference = write_intent(session_root, intent)
    url = fire(env, build_payload(reference, task), http)
    return Spawned(intent.spawn_id, reference, url)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(cwd), *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = f"git {args[0]} in {cwd} failed: {result.stderr.strip()}"
        raise SpawnError(msg)
    return result.stdout.strip()
