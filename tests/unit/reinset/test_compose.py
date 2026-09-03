from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from pandoscope.reinset.compose import compose
from pandoscope.reinset.principal import principal_id
from pandoscope.reinset.render import MARKER, UnmanagedTargetError

from .conftest import (
    ENV_RUN5_UI,
    ENV_RUN7_FIRED,
    INTENT_IMPLEMENTER,
    INTENT_NO_ROLE,
    ORG_SALT,
)


def test_no_reference_writes_answers_and_renders_general(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    env = {**ENV_RUN5_UI, "REINSET_ORG_SALT": ORG_SALT}
    result = compose(env, session_root, home, None, path_dirs)
    assert result.answers_path == home / ".claude" / "reinset" / "sess-fixture-0001.yml"
    on_disk = yaml.safe_load(result.answers_path.read_text())
    assert on_disk == result.answers
    assert on_disk["passed"] is None
    assert on_disk["resolved"]["role"] == "general"
    assert on_disk["mismatches"] == []
    assert on_disk["errors"] == []
    assert on_disk["detected"]["identity"] == principal_id(
        "principal@example.test", ORG_SALT
    )
    assert result.render_path == home / ".claude" / "CLAUDE.md"
    assert result.render_path.read_text().startswith(MARKER)
    assert "UNCONFIGURED" in result.render_text
    assert result.errors == []


def test_answers_env_var_is_the_contract(
    session_root: Path, home: Path, path_dirs: list[Path], tmp_path: Path
) -> None:
    target = tmp_path / "elsewhere" / "answers.yml"
    env = {**ENV_RUN5_UI, "REINSET_ANSWERS": str(target)}
    result = compose(env, session_root, home, None, path_dirs)
    assert result.answers_path == target
    assert target.exists()


def test_reference_from_env_composes_the_role(
    session_root: Path,
    home: Path,
    path_dirs: list[Path],
    commit_intent: Callable[[str, str], str],
) -> None:
    sha = commit_intent("intents/spawn-7b2d.yml", INTENT_IMPLEMENTER)
    ref = f"session-memory@{sha}:intents/spawn-7b2d.yml"
    env = {**ENV_RUN7_FIRED, "REINSET_ORG_SALT": ORG_SALT, "REINSET_REF": ref}
    result = compose(env, session_root, home, None, path_dirs)
    assert result.answers["passed"]["role"] == "implementer"
    assert result.answers["resolved"]["role"] == "implementer"
    assert result.answers["reference"] == ref
    assert result.answers["mismatches"] == []
    assert "implementer" in result.render_text
    assert "UNCONFIGURED" not in result.render_text
    text = result.answers_path.read_text()
    assert "example.test" not in text.lower()


def test_reference_from_the_payload_block_composes_the_role(
    session_root: Path,
    home: Path,
    path_dirs: list[Path],
    commit_intent: Callable[[str, str], str],
) -> None:
    sha = commit_intent("intents/spawn-7b2d.yml", INTENT_IMPLEMENTER)
    prompt = (
        "<routine-fire-payload>\n"
        f"    reinset: session-memory@{sha}:intents/spawn-7b2d.yml\n"
        "    Message from the spawner.\n"
        "</routine-fire-payload>\n"
    )
    result = compose(ENV_RUN7_FIRED, session_root, home, prompt, path_dirs)
    assert result.answers["resolved"]["role"] == "implementer"


def test_ui_session_with_a_reference_reports_the_origin_mismatch(
    session_root: Path,
    home: Path,
    path_dirs: list[Path],
    commit_intent: Callable[[str, str], str],
) -> None:
    sha = commit_intent("intents/spawn-7b2d.yml", INTENT_IMPLEMENTER)
    env = {**ENV_RUN5_UI, "REINSET_REF": f"session-memory@{sha}:intents/spawn-7b2d.yml"}
    result = compose(env, session_root, home, None, path_dirs)
    assert [m["key"] for m in result.answers["mismatches"]] == ["origin"]
    assert "MISMATCH" in result.render_text
    assert result.answers["resolved"]["role"] == "implementer"


def test_reference_without_role_is_a_composer_error_rendering_general(
    session_root: Path,
    home: Path,
    path_dirs: list[Path],
    commit_intent: Callable[[str, str], str],
) -> None:
    sha = commit_intent("intents/spawn-7b2e.yml", INTENT_NO_ROLE)
    env = {
        **ENV_RUN7_FIRED,
        "REINSET_REF": f"session-memory@{sha}:intents/spawn-7b2e.yml",
    }
    result = compose(env, session_root, home, None, path_dirs)
    assert len(result.errors) == 1
    assert "role" in result.errors[0]
    assert result.answers["errors"] == result.errors
    assert result.answers["passed"] is None
    assert result.answers["resolved"]["role"] == "general"
    assert "COMPOSER ERROR" in result.render_text
    assert "UNCONFIGURED" in result.render_text


def test_unresolvable_reference_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    env = {**ENV_RUN7_FIRED, "REINSET_REF": f"session-memory@{'0' * 40}:intents/x.yml"}
    result = compose(env, session_root, home, None, path_dirs)
    assert len(result.errors) == 1
    assert result.answers["resolved"]["role"] == "general"


def test_malformed_reference_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    env = {**ENV_RUN7_FIRED, "REINSET_REF": "session-memory@main:intents/x.yml"}
    result = compose(env, session_root, home, None, path_dirs)
    assert len(result.errors) == 1
    assert "reinset reference" in result.errors[0]


def test_unmanaged_claude_md_is_refused(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    (home / ".claude" / "CLAUDE.md").write_text("hand-written\n")
    with pytest.raises(UnmanagedTargetError):
        compose(ENV_RUN5_UI, session_root, home, None, path_dirs)
    assert (home / ".claude" / "CLAUDE.md").read_text() == "hand-written\n"


def test_reference_declaring_general_renders_declared_general(
    session_root: Path,
    home: Path,
    path_dirs: list[Path],
    commit_intent: Callable[[str, str], str],
) -> None:
    sha = commit_intent(
        "intents/spawn-r0a4.yml", INTENT_IMPLEMENTER.replace("implementer", "general")
    )
    env = {
        **ENV_RUN7_FIRED,
        "REINSET_REF": f"session-memory@{sha}:intents/spawn-r0a4.yml",
    }
    result = compose(env, session_root, home, None, path_dirs)
    assert result.answers["resolved"]["role"] == "general"
    assert "UNCONFIGURED" not in result.render_text
    assert "Role: general" in result.render_text
