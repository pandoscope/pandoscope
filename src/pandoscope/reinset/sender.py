"""The CCoW sender: attach an intent reference to a child the Routine mints."""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    raise NotImplementedError


def spawner_identity(answers: Mapping[str, Any] | None) -> tuple[str, str | None]:
    """
    Return ``(spawner, spawner_spawn)`` from the caller's answers file.

    ``spawner`` is ``detected.identity``; ``spawner_spawn`` is the caller's
    own ``passed.spawn_id`` when it was spawned. Raises SpawnError when the
    identity is ``unknown`` or the answers are missing: never guessed.
    """
    raise NotImplementedError


def render_intent(intent: Intent) -> str:
    """Return the intent file text: no session ids, no emails."""
    raise NotImplementedError


def write_intent(session_root: Path, intent: Intent) -> str:
    """
    Commit ``intents/<spawn_id>.yml`` to the store's main and push.

    Returns the reference ``session-memory@<sha>:intents/<spawn_id>.yml``.
    Raises SpawnError when the store clone is absent or the push fails.
    """
    raise NotImplementedError


def build_payload(reference: str, task: str) -> str:
    """Return the fire text: the ``reinset:`` line, a blank line, the task."""
    raise NotImplementedError


def fire(env: Mapping[str, str], payload: str, http: Http) -> str | None:
    """
    POST the payload to the Routine's fire endpoint.

    The token is read from ``env`` and travels only in the Authorization
    header. Returns the minted session URL when the response carries one.
    Raises SpawnError naming the variable when either is unset, or the
    HTTP status on a non-200 answer, never the token.
    """
    raise NotImplementedError


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
    raise NotImplementedError
