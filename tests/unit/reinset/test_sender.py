from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from pandoscope.reinset.sender import (
    Intent,
    SpawnError,
    build_payload,
    fire,
    mint_spawn_id,
    render_intent,
    spawn,
    spawner_identity,
    write_intent,
)

from .conftest import git

ANSWERS_PRINCIPAL: dict[str, Any] = {
    "detected": {"identity": "p-40be564147c6", "spawned": False},
    "passed": None,
}
ANSWERS_SPAWNED: dict[str, Any] = {
    "detected": {"identity": "p-40be564147c6", "spawned": True},
    "passed": {"spawn_id": "spawn-r0a1", "role": "orchestrator"},
}
TOKEN = "fixture-token-never-printed"  # noqa: S105
ENV = {"REINSET_SPAWN_ROUTINE": "trig_fixture", "REINSET_SPAWN_TOKEN": TOKEN}


class FakeHttp:
    def __init__(self, status: int = 200, body: dict[str, Any] | None = None) -> None:
        self.status = status
        self.body = body or {"claude_code_session_url": "https://claude.ai/code/x"}
        self.calls: list[tuple[str, dict[str, str], bytes]] = []

    def __call__(
        self, url: str, headers: dict[str, str], data: bytes
    ) -> tuple[int, bytes]:
        self.calls.append((url, headers, data))
        return self.status, json.dumps(self.body).encode()


@pytest.fixture
def store_with_origin(session_root: Path) -> Path:
    """The session-memory clone gets a bare origin so a push can land."""
    store = session_root / "session-memory"
    origin = session_root.parent / "origin.git"
    git(session_root, "init", "-q", "--bare", "-b", "main", str(origin))
    git(store, "remote", "add", "origin", str(origin))
    git(store, "push", "-q", "-u", "origin", "main")
    return origin


def test_spawn_id_shape() -> None:
    assert mint_spawn_id(lambda n: "ab12") == "spawn-ab12"


def test_spawner_is_the_callers_identity() -> None:
    assert spawner_identity(ANSWERS_PRINCIPAL) == ("p-40be564147c6", None)


def test_spawned_caller_adds_its_own_spawn_id() -> None:
    assert spawner_identity(ANSWERS_SPAWNED) == ("p-40be564147c6", "spawn-r0a1")


def test_unknown_identity_is_refused_never_guessed() -> None:
    with pytest.raises(SpawnError, match="REINSET_ORG_SALT"):
        spawner_identity({"detected": {"identity": "unknown"}, "passed": None})
    with pytest.raises(SpawnError, match="answers"):
        spawner_identity(None)


def test_intent_file_carries_the_passed_block_only() -> None:
    intent = Intent(
        spawn_id="spawn-ab12",
        spawner="p-40be564147c6",
        role="implementer",
        principal="p-40be564147c6",
        spawner_spawn="spawn-r0a1",
        thread="per-session-agent-config",
        tickets=["pandoscope/skills#179"],
    )
    data = yaml.safe_load(render_intent(intent))
    assert data == {
        "spawn_id": "spawn-ab12",
        "spawner": "p-40be564147c6",
        "spawner_spawn": "spawn-r0a1",
        "origin": "spawner",
        "role": "implementer",
        "principal": "p-40be564147c6",
        "thread": "per-session-agent-config",
        "tickets": ["pandoscope/skills#179"],
        "dojo": False,
        "debug": False,
        "overrides": [],
    }


def test_unspawned_caller_writes_no_spawner_spawn_key() -> None:
    intent = Intent("spawn-ab12", "p-40be564147c6", "probe", "p-40be564147c6")
    assert "spawner_spawn" not in yaml.safe_load(render_intent(intent))


def test_write_intent_commits_to_main_and_returns_the_sha_reference(
    session_root: Path, store_with_origin: Path
) -> None:
    intent = Intent("spawn-ab12", "p-40be564147c6", "probe", "p-40be564147c6")
    reference = write_intent(session_root, intent)
    sha = git(session_root / "session-memory", "rev-parse", "HEAD")
    assert reference == f"session-memory@{sha}:intents/spawn-ab12.yml"
    # Landed on the origin's main, where a child unshallows from (D3).
    assert git(session_root, "-C", str(store_with_origin), "rev-parse", "main") == sha
    shown = git(
        session_root / "session-memory", "show", f"{sha}:intents/spawn-ab12.yml"
    )
    assert yaml.safe_load(shown)["spawn_id"] == "spawn-ab12"


def test_write_intent_without_a_store_clone_is_refused(tmp_path: Path) -> None:
    intent = Intent("spawn-ab12", "p-40be564147c6", "probe", "p-40be564147c6")
    with pytest.raises(SpawnError, match="session-memory"):
        write_intent(tmp_path, intent)


def test_payload_leads_with_the_reference_line() -> None:
    text = build_payload("session-memory@abc1234:intents/spawn-ab12.yml", "Do X.")
    assert text.startswith("reinset: session-memory@abc1234:intents/spawn-ab12.yml\n\n")
    assert text.endswith("Do X.")


def test_fire_posts_to_the_routine_with_the_token_in_the_header_only() -> None:
    http = FakeHttp()
    url = fire(ENV, "reinset: r\n\ntask", http)
    assert url == "https://claude.ai/code/x"
    ((posted_url, headers, data),) = http.calls
    assert (
        posted_url
        == "https://api.anthropic.com/v1/claude_code/routines/trig_fixture/fire"
    )
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["anthropic-beta"] == "experimental-cc-routine-2026-04-01"
    assert json.loads(data) == {"text": "reinset: r\n\ntask"}
    assert TOKEN not in posted_url
    assert TOKEN not in data.decode()


def test_fire_without_the_variables_names_them_never_values() -> None:
    with pytest.raises(SpawnError, match="REINSET_SPAWN_TOKEN"):
        fire({"REINSET_SPAWN_ROUTINE": "trig_fixture"}, "x", FakeHttp())
    with pytest.raises(SpawnError, match="REINSET_SPAWN_ROUTINE"):
        fire({"REINSET_SPAWN_TOKEN": TOKEN}, "x", FakeHttp())


def test_fire_failure_reports_the_status_never_the_token() -> None:
    with pytest.raises(SpawnError, match="403") as excinfo:
        fire(ENV, "x", FakeHttp(status=403, body={"error": "nope"}))
    assert TOKEN not in str(excinfo.value)


def test_spawn_end_to_end(session_root: Path, store_with_origin: Path) -> None:
    http = FakeHttp()
    result = spawn(
        ENV,
        session_root,
        ANSWERS_SPAWNED,
        {"role": "implementer", "thread": "per-session-agent-config"},
        "Do X.",
        http,
    )
    assert result.spawn_id.startswith("spawn-")
    assert result.reference.startswith("session-memory@")
    assert result.session_url == "https://claude.ai/code/x"
    ((_, _, data),) = http.calls
    assert json.loads(data)["text"].startswith(f"reinset: {result.reference}\n\n")
    shown = git(
        session_root / "session-memory", "show", f"HEAD:intents/{result.spawn_id}.yml"
    )
    intent = yaml.safe_load(shown)
    assert intent["spawner"] == "p-40be564147c6"
    assert intent["spawner_spawn"] == "spawn-r0a1"
    assert intent["principal"] == "p-40be564147c6"
    assert intent["role"] == "implementer"


def test_spawn_dry_run_writes_and_fires_nothing(session_root: Path) -> None:
    http = FakeHttp()
    before = git(session_root / "session-memory", "rev-parse", "HEAD")
    result = spawn(
        ENV,
        session_root,
        ANSWERS_PRINCIPAL,
        {"role": "probe"},
        "Do X.",
        http,
        dry_run=True,
    )
    assert http.calls == []
    assert git(session_root / "session-memory", "rev-parse", "HEAD") == before
    assert result.session_url is None
    assert "role: probe" in result.reference


def test_spawn_with_an_unknown_role_is_refused(session_root: Path) -> None:
    with pytest.raises(SpawnError, match="wizard"):
        spawn(ENV, session_root, ANSWERS_PRINCIPAL, {"role": "wizard"}, "x", FakeHttp())
