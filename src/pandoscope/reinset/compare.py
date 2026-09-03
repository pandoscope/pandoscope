"""Resolve effective scope values and report mismatches (§3.3, §3.4)."""

from __future__ import annotations

from typing import Any

SPAWNED_ORIGINS = frozenset({"spawner", "webhook", "poll"})


def compare(
    detected: dict[str, Any], passed: dict[str, Any] | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Return ``(resolved, mismatches)``.

    Facts resolve to ``detected``, intent to ``passed``. A mismatch is
    recorded for ``origin`` against ``detected.spawned`` and for
    ``principal`` against ``detected.identity``; it never blocks.
    """
    raise NotImplementedError
