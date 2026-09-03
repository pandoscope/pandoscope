from __future__ import annotations

from pathlib import Path

from pandoscope.reinset.detect import detect
from pandoscope.reinset.principal import principal_id

from .conftest import ENV_RUN5_UI, ENV_RUN7_FIRED, ORG_SALT


def test_fired_session_run7(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    env = {**ENV_RUN7_FIRED, "REINSET_ORG_SALT": ORG_SALT}
    detected = detect(env, session_root, home, path_dirs)
    assert detected["harness"] == "claude-code"
    assert detected["harness_version"] == "2.1.42"
    assert detected["environment"] == "ccow"
    assert detected["environment_variant"] == "cloud_default"
    assert detected["session_id"] == "sess-fixture-0001"
    assert detected["spawned"] is True
    assert detected["identity"] == principal_id("principal@example.test", ORG_SALT)


def test_ui_created_session_run5_is_not_spawned(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    # CLAUDE_CODE_CHILD_SESSION=1 is set here too and carries no signal
    # (skills#180); the entrypoint is the detector (D17).
    detected = detect(ENV_RUN5_UI, session_root, home, path_dirs)
    assert detected["spawned"] is False


def test_email_never_enters_the_result(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    env = {**ENV_RUN7_FIRED, "REINSET_ORG_SALT": ORG_SALT}
    detected = detect(env, session_root, home, path_dirs)
    assert "example.test" not in repr(detected).lower()


def test_identity_without_salt_is_unknown(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    detected = detect(ENV_RUN7_FIRED, session_root, home, path_dirs)
    assert detected["identity"] == "unknown"


def test_outside_claude_code_everything_is_unknown_or_local(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    detected = detect({}, session_root, home, path_dirs)
    assert detected["harness"] == "unknown"
    assert detected["harness_version"] == "unknown"
    assert detected["environment"] == "local"
    assert detected["environment_variant"] == "unknown"
    assert detected["session_id"] == "unknown"
    assert detected["spawned"] is False
    assert detected["identity"] == "unknown"


def test_github_actions_environment(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    detected = detect({"GITHUB_ACTIONS": "true"}, session_root, home, path_dirs)
    assert detected["environment"] == "actions"


def test_model_is_unknown_until_measured(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    detected = detect(ENV_RUN7_FIRED, session_root, home, path_dirs)
    assert detected["model"] == {"configured": "unknown", "served": "unknown"}


def test_tools_are_probed_binaries_and_skill_dirs(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    (home / ".claude" / "skills" / "grilling").mkdir(parents=True)
    (session_root / "skills" / ".claude" / "skills" / "thread-ledger").mkdir(
        parents=True
    )
    detected = detect(ENV_RUN7_FIRED, session_root, home, path_dirs)
    assert detected["tools"] == ["node", "uv", "grilling", "thread-ledger"]


def test_repos_come_from_each_clones_copier_answers(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    detected = detect(ENV_RUN7_FIRED, session_root, home, path_dirs)
    assert detected["repos"] == [
        {
            "path": str(session_root / "meta"),
            "slug": "meta",
            "kind": "ops",
            "forge": "github",
        },
        {
            "path": str(session_root / "skills"),
            "slug": "skills",
            "kind": "skills",
            "forge": "github",
        },
    ]
