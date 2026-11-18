from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from pandoscope.reinset.compose import compose
from pandoscope.reinset.principal import principal_id
from pandoscope.reinset.render import MARKER, UnmanagedTargetError

from .conftest import (
    ENV_RUN5_UI,
    ENV_RUN7_FIRED,
    ORG_SALT,
    fire,
    pr_clone,
    write_waybill_order,
)


def test_no_order_writes_answers_and_renders_general(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    env = {**ENV_RUN5_UI, "REINSET_ORG_SALT": ORG_SALT}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers_path == home / ".claude" / "reinset" / "sess-fixture-0001.yml"
    on_disk = yaml.safe_load(result.answers_path.read_text())
    assert on_disk == result.answers
    assert on_disk["order"] is None
    assert on_disk["resolved"]["role"] == "general"
    assert on_disk["resolved"]["principal"] == on_disk["detected"]["identity"]
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
    result = compose(env, session_root, home, path_dirs)
    assert result.answers_path == target
    assert target.exists()


def test_unmanaged_claude_md_is_refused(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    (home / ".claude" / "CLAUDE.md").write_text("hand-written\n")
    with pytest.raises(UnmanagedTargetError):
        compose(ENV_RUN5_UI, session_root, home, path_dirs)
    assert (home / ".claude" / "CLAUDE.md").read_text() == "hand-written\n"


REVIEW_PROMPT_FILE = """\
Review pull request {{ n }} as tier {{ model_tier }}.
Base {{ base }}, head {{ head }}.
"""


REVIEW_NAME = "review-spec-fidelity-sonnet-aet262-1"
IMPLEMENT_NAME = "implement-opus-aet261-1"
WAYBILL_FIRE = fire(REVIEW_NAME)
IMPLEMENT_FIRE = fire(IMPLEMENT_NAME)


def write_pass_and_order(
    session_root: Path, order: str | None, name: str = REVIEW_NAME
) -> None:
    target = session_root / "skills" / "original" / "thread-ledger" / "review"
    target.mkdir(parents=True)
    (target / "spec-fidelity.md").write_text(REVIEW_PROMPT_FILE)
    # The reviewer profile names thread-ledger; the bundle installs it.
    (target.parent / "SKILL.md").write_text("---\nname: thread-ledger\n---\n")
    if order is not None:
        write_waybill_order(session_root, name, order)
        # An implementer order's subject must have a clone (pandoscope#57).
        if not (session_root / "aet").exists():
            pr_clone(session_root, "aet", 262)


@pytest.mark.xfail(strict=True)
def test_a_waybill_order_composes_the_reviewer(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    head = pr_clone(session_root, "aet", 262)
    write_pass_and_order(
        session_root,
        f"id: {REVIEW_NAME}\nrole: reviewer\npass: spec-fidelity\n"
        "model_tier: sonnet\nsubject: pandoscope/aet#262\nbase: feature\n"
        "tickets: []\n",
    )
    env = {**ENV_RUN7_FIRED, **WAYBILL_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["resolved"]["role"] == "reviewer"
    assert result.answers["order"] == {
        "path": f"waybill/orders/{REVIEW_NAME}.yml",
        "role": "reviewer",
        "pass": "spec-fidelity",
        "model_tier": "sonnet",
        "subject": "pandoscope/aet#262",
        "tickets": [],
    }
    assert result.errors == []
    assert "# Role: reviewer" in result.render_text
    assert "Review pull request 262 as tier sonnet." in result.render_text
    assert f"Base feature, head {head}." in result.render_text
    assert "UNCONFIGURED" not in result.render_text


def test_a_broken_order_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_pass_and_order(session_root, "- not a mapping\n")
    env = {**ENV_RUN7_FIRED, **WAYBILL_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert len(result.errors) == 1
    assert "mapping" in result.errors[0]
    assert result.answers["resolved"]["role"] == "general"
    assert "COMPOSER ERROR" in result.render_text


@pytest.mark.xfail(strict=True)
def test_an_order_without_the_pass_file_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_waybill_order(
        session_root,
        REVIEW_NAME,
        f"id: {REVIEW_NAME}\nrole: reviewer\npass: spec-fidelity\n"
        "model_tier: sonnet\nsubject: pandoscope/aet#262\ntickets: []\n",
    )
    env = {**ENV_RUN7_FIRED, **WAYBILL_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert len(result.errors) == 1
    assert "spec-fidelity.md" in result.errors[0]
    assert result.answers["resolved"]["role"] == "general"
    assert "COMPOSER ERROR" in result.render_text


# Ruling 2026-09-23 (skills#195): the order is the only receiver. No
# environment variable and no prompt line composes a role.
ORDER_IMPLEMENTER = (
    f"id: {IMPLEMENT_NAME}\nrole: implementer\nmodel_tier: opus\n"
    "subject: pandoscope/aet#261\ntickets: [pandoscope/skills#195]\n"
)


def test_reinset_ref_is_not_a_channel(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    env = {**ENV_RUN7_FIRED, "REINSET_REF": "session-memory@0123abc:intents/x.yml"}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["resolved"]["role"] == "general"
    assert result.errors == []
    assert "UNCONFIGURED" in result.render_text
    for gone in ("reference", "passed", "mismatches"):
        assert gone not in result.answers


def test_no_order_writes_a_null_order(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    result = compose(ENV_RUN5_UI, session_root, home, path_dirs)
    assert result.answers["order"] is None
    assert list(result.answers) == [
        "detected",
        "resolved",
        "order",
        "errors",
        "installed",
        "hooks",
    ]


def test_a_fired_session_without_an_order_shouts(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    result = compose(ENV_RUN7_FIRED, session_root, home, path_dirs)
    assert "UNCONFIGURED" in result.render_text
    assert "WAITING" not in result.render_text


@pytest.mark.xfail(strict=True)
def test_the_order_carries_its_tickets_into_the_answers(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_pass_and_order(session_root, ORDER_IMPLEMENTER, IMPLEMENT_NAME)
    env = {**ENV_RUN7_FIRED, **IMPLEMENT_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["order"]["tickets"] == ["pandoscope/skills#195"]
    assert result.answers["resolved"]["role"] == "implementer"


@pytest.mark.xfail(strict=True)
def test_an_order_declaring_general_renders_declared_general(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_pass_and_order(
        session_root,
        ORDER_IMPLEMENTER.replace("implementer", "general"),
        IMPLEMENT_NAME,
    )
    env = {**ENV_RUN7_FIRED, **IMPLEMENT_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["resolved"]["role"] == "general"
    assert "UNCONFIGURED" not in result.render_text
    assert "Role: general" in result.render_text


def _skill(session_root: Path, name: str) -> None:
    skill = session_root / "skills" / "original" / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n")


IMPLEMENTER_ORDER = (
    f"id: {IMPLEMENT_NAME}\nrole: implementer\nmodel_tier: opus\n"
    "subject: pandoscope/aet#261\ntickets: []\n"
)


@pytest.mark.xfail(strict=True)
def test_role_install_follows_the_profile(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    # The shipped implementer profile names thread-ledger and handing-off.
    for name in ("thread-ledger", "handing-off", "grilling"):
        _skill(session_root, name)
    for script in ("guard.sh", "verify.sh"):
        (session_root / "skills" / "original" / "handing-off" / script).write_text(
            "#!/bin/bash\n"
        )
    write_pass_and_order(session_root, IMPLEMENTER_ORDER, IMPLEMENT_NAME)
    env = {**ENV_RUN7_FIRED, **IMPLEMENT_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.errors == []
    assert result.answers["installed"] == ["thread-ledger", "handing-off"]
    assert (home / ".claude" / "skills" / "handing-off" / "SKILL.md").is_file()
    assert not (home / ".claude" / "skills" / "grilling").exists()
    assert "- handing-off" in result.render_text


@pytest.mark.xfail(strict=True)
def test_missing_bundle_skill_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_pass_and_order(session_root, IMPLEMENTER_ORDER, IMPLEMENT_NAME)
    env = {**ENV_RUN7_FIRED, **IMPLEMENT_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["resolved"]["role"] == "implementer"
    assert any("handing-off" in error for error in result.errors)
    assert "COMPOSER ERROR" in result.render_text
    assert result.answers["errors"] == result.errors


@pytest.mark.xfail(strict=True)
def test_a_session_without_an_order_prunes_what_a_role_left(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    for name in ("thread-ledger", "handing-off"):
        _skill(session_root, name)
    write_pass_and_order(session_root, IMPLEMENTER_ORDER, IMPLEMENT_NAME)
    compose({**ENV_RUN7_FIRED, **IMPLEMENT_FIRE}, session_root, home, path_dirs)
    assert (home / ".claude" / "skills" / "handing-off").is_dir()
    # A fresh SessionStart with no order composes general
    # and prunes what an earlier role left (D15).
    compose(ENV_RUN5_UI, session_root, home, path_dirs)
    assert not (home / ".claude" / "skills" / "handing-off").exists()


@pytest.mark.xfail(strict=True)
def test_role_hooks_render_beside_the_answers(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    # The shipped implementer profile carries the handing-off hooks.
    for name in ("thread-ledger", "handing-off"):
        _skill(session_root, name)
    for script in ("guard.sh", "verify.sh"):
        (session_root / "skills" / "original" / "handing-off" / script).write_text(
            "#!/bin/bash\n"
        )
    write_pass_and_order(session_root, IMPLEMENTER_ORDER, IMPLEMENT_NAME)
    hooks_path = home / "elsewhere" / "hooks.json"
    env = {**ENV_RUN7_FIRED, **IMPLEMENT_FIRE, "REINSET_HOOKS": str(hooks_path)}
    result = compose(env, session_root, home, path_dirs)
    assert result.errors == []
    assert result.hooks_path == hooks_path
    hooks = json.loads(hooks_path.read_text())
    guard = str(home / ".claude" / "skills" / "handing-off" / "guard.sh")
    assert hooks["PreCompact"] == [{"command": guard}]
    assert hooks["SessionStart"][0]["matcher"] == "compact"
    assert result.answers["hooks"] == hooks


def test_unconfigured_session_renders_no_hooks(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    result = compose(ENV_RUN5_UI, session_root, home, path_dirs)
    assert result.hooks_path == home / ".claude" / "reinset" / "hooks.json"
    assert json.loads(result.hooks_path.read_text()) == {}


def test_another_harness_installs_no_claude_code_bundle(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    # resolved.harness selects the skill format (skills#179 §4).
    # Only Claude Code's is known.
    # Any other harness gets no bundle and an error that names the harness.
    for name in ("thread-ledger", "handing-off"):
        _skill(session_root, name)
    write_pass_and_order(session_root, IMPLEMENTER_ORDER, IMPLEMENT_NAME)
    env = {"CLAUDE_CODE_SESSION_ID": "sess-other-0001", **IMPLEMENT_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["resolved"]["harness"] != "claude-code"
    assert not (home / ".claude" / "skills" / "handing-off").exists()
    assert result.answers["installed"] == []
    assert any("harness" in error for error in result.errors)
