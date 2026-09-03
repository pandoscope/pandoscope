"""Resolve effective scope values and report mismatches (§3.3, §3.4)."""

from __future__ import annotations

from typing import Any

from pandoscope.reinset.principal import UNKNOWN

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
    identity = detected.get("identity", UNKNOWN)
    intent = passed or {}
    principal = intent.get("principal", identity)
    resolved = {
        "harness": detected.get("harness", UNKNOWN),
        "environment": detected.get("environment", UNKNOWN),
        "role": intent.get("role", "general"),
        "principal": principal,
        "model": detected.get("model", {}).get("served", UNKNOWN),
    }
    mismatches: list[dict[str, Any]] = []
    if passed is None:
        return resolved, mismatches
    detected_origin = "spawner" if detected.get("spawned") else "principal"
    passed_origin = passed.get("origin")
    if (passed_origin in SPAWNED_ORIGINS) != (detected_origin == "spawner"):
        mismatches.append(
            {
                "key": "origin",
                "passed": passed_origin,
                "detected": detected_origin,
                "resolved_to": passed_origin,
            }
        )
    if identity != UNKNOWN and principal != identity:
        mismatches.append(
            {
                "key": "principal",
                "passed": principal,
                "detected": identity,
                "resolved_to": principal,
            }
        )
    return resolved, mismatches
