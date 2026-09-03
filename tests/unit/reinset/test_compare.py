from __future__ import annotations

from typing import Any

from pandoscope.reinset.compare import compare

DETECTED: dict[str, Any] = {
    "harness": "claude-code",
    "environment": "ccow",
    "spawned": False,
    "identity": "p-4c1e9a7b02d3",
    "model": {"configured": "unknown", "served": "unknown"},
}
PASSED: dict[str, Any] = {
    "spawn_id": "spawn-7b2d",
    "spawner": "p-4c1e9a7b02d3",
    "origin": "spawner",
    "role": "implementer",
}


def test_no_intent_resolves_facts_and_general() -> None:
    resolved, mismatches = compare(DETECTED, None)
    assert resolved == {
        "harness": "claude-code",
        "environment": "ccow",
        "role": "general",
        "principal": "p-4c1e9a7b02d3",
        "model": "unknown",
    }
    assert mismatches == []


def test_intent_resolves_role_and_defaults_principal_to_identity() -> None:
    resolved, _ = compare({**DETECTED, "spawned": True}, PASSED)
    assert resolved["role"] == "implementer"
    assert resolved["principal"] == "p-4c1e9a7b02d3"


def test_ui_session_steered_by_a_routine_is_the_first_measured_mismatch() -> None:
    # Principal-origin by detection, spawner-origin by intent (§3.4).
    _, mismatches = compare(DETECTED, PASSED)
    assert mismatches == [
        {
            "key": "origin",
            "passed": "spawner",
            "detected": "principal",
            "resolved_to": "spawner",
        }
    ]


def test_principal_mismatch_resolves_to_passed() -> None:
    passed = {**PASSED, "principal": "p-000000000000"}
    resolved, mismatches = compare({**DETECTED, "spawned": True}, passed)
    assert resolved["principal"] == "p-000000000000"
    assert mismatches == [
        {
            "key": "principal",
            "passed": "p-000000000000",
            "detected": "p-4c1e9a7b02d3",
            "resolved_to": "p-000000000000",
        }
    ]


def test_unknown_facts_never_mismatch() -> None:
    detected = {**DETECTED, "identity": "unknown", "spawned": True}
    _, mismatches = compare(detected, {**PASSED, "principal": "p-000000000000"})
    assert mismatches == []
