from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from pandoscope.reinset.intent import IntentError, resolve_intent
from pandoscope.reinset.receive import Reference

from .conftest import INTENT_IMPLEMENTER, INTENT_NO_ROLE


def test_resolves_the_file_at_the_exact_commit(
    session_root: Path, commit_intent: Callable[[str, str], str]
) -> None:
    sha = commit_intent("intents/spawn-7b2d.yml", INTENT_IMPLEMENTER)
    commit_intent("intents/spawn-7b2d.yml", INTENT_IMPLEMENTER + "debug: true\n")
    passed = resolve_intent(
        Reference("session-memory", sha, "intents/spawn-7b2d.yml"), session_root
    )
    assert passed["role"] == "implementer"
    assert passed["spawn_id"] == "spawn-7b2d"
    assert passed["spawner"] == "p-4c1e9a7b02d3"
    assert passed["tickets"] == ["pandoscope/skills#130"]
    assert passed["debug"] is False


def test_reference_without_role_is_an_intent_error(
    session_root: Path, commit_intent: Callable[[str, str], str]
) -> None:
    sha = commit_intent("intents/spawn-7b2e.yml", INTENT_NO_ROLE)
    with pytest.raises(IntentError, match="role"):
        resolve_intent(
            Reference("session-memory", sha, "intents/spawn-7b2e.yml"), session_root
        )


def test_unknown_role_is_an_intent_error(
    session_root: Path, commit_intent: Callable[[str, str], str]
) -> None:
    sha = commit_intent("intents/x.yml", INTENT_NO_ROLE + "role: wizard\n")
    with pytest.raises(IntentError, match="wizard"):
        resolve_intent(Reference("session-memory", sha, "intents/x.yml"), session_root)


def test_missing_required_key_is_an_intent_error(
    session_root: Path, commit_intent: Callable[[str, str], str]
) -> None:
    sha = commit_intent("intents/x.yml", "spawn_id: s\nrole: probe\n")
    with pytest.raises(IntentError, match="spawner"):
        resolve_intent(Reference("session-memory", sha, "intents/x.yml"), session_root)


def test_session_id_as_spawner_is_an_intent_error(
    session_root: Path, commit_intent: Callable[[str, str], str]
) -> None:
    # D16: spawner is a principal id, never a session id.
    text = INTENT_IMPLEMENTER.replace("p-4c1e9a7b02d3", "session_014CUXJh1hKmW")
    sha = commit_intent("intents/x.yml", text)
    with pytest.raises(IntentError, match="spawner"):
        resolve_intent(Reference("session-memory", sha, "intents/x.yml"), session_root)


def test_unreachable_commit_is_an_intent_error(session_root: Path) -> None:
    ref = Reference("session-memory", "0" * 40, "intents/x.yml")
    with pytest.raises(IntentError, match="0000000"):
        resolve_intent(ref, session_root)


def test_absent_clone_is_an_intent_error(session_root: Path) -> None:
    ref = Reference("nowhere", "0" * 40, "intents/x.yml")
    with pytest.raises(IntentError, match="nowhere"):
        resolve_intent(ref, session_root)


def test_non_mapping_file_is_an_intent_error(
    session_root: Path, commit_intent: Callable[[str, str], str]
) -> None:
    sha = commit_intent("intents/x.yml", "- just\n- a list\n")
    with pytest.raises(IntentError, match="mapping"):
        resolve_intent(Reference("session-memory", sha, "intents/x.yml"), session_root)
