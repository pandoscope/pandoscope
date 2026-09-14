from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pandoscope.reinset.compose import compose
from pandoscope.reinset.principal import principal_id
from pandoscope.reinset.render import MARKER, UnmanagedTargetError

from .conftest import ENV_RUN5_UI, ENV_RUN7_FIRED, ORG_SALT


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
```text
PANDO-REVIEW: spec-fidelity tier=<tier>

Review pull request <n> as tier <tier>.
```
"""


WAYBILL_FIRE = {
    "CCR_TRIGGER_SOURCE": "github",
    "CCR_TRIGGER_EVENT": "pull_request.opened",
    "CCR_TRIGGER_REPO": "pandoscope/waybill",
    "CCR_TRIGGER_PR_NUMBER": "5",
    "CCR_TRIGGER_HEAD_REF": "order/probe-4",
    "CCR_TRIGGER_BASE_REF": "main",
    "CCR_TRIGGER_HEAD_SHA": "3cb001e",
}


def write_pass_and_order(session_root: Path, order: str | None) -> None:
    target = session_root / "skills" / "original" / "thread-ledger" / "review"
    target.mkdir(parents=True)
    (target / "spec-fidelity.md").write_text(REVIEW_PROMPT_FILE)
    # The reviewer profile names thread-ledger; the bundle installs it.
    (target.parent / "SKILL.md").write_text("---\nname: thread-ledger\n---\n")
    if order is not None:
        orders = session_root / "waybill" / "orders"
        orders.mkdir(parents=True)
        (orders / "probe-4.yml").write_text(order)


def test_a_waybill_order_composes_the_reviewer(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_pass_and_order(
        session_root,
        "id: probe-4\nrole: reviewer\npass: spec-fidelity\ntier: sonnet\n"
        "pull_request: pandoscope/aet#262\ntickets: []\n",
    )
    env = {**ENV_RUN7_FIRED, **WAYBILL_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["resolved"]["role"] == "reviewer"
    assert result.answers["order"] == {
        "path": "waybill/orders/probe-4.yml",
        "role": "reviewer",
        "pass": "spec-fidelity",
        "tier": "sonnet",
        "pull_request": 262,
        "tickets": [],
    }
    assert result.errors == []
    assert "# Role: reviewer" in result.render_text
    assert "Review pull request 262 as tier sonnet." in result.render_text
    assert "PANDO-REVIEW" not in result.render_text
    assert "UNCONFIGURED" not in result.render_text


def test_an_order_for_another_role_composes_that_role_without_a_task(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_pass_and_order(
        session_root,
        "id: probe-4\nrole: implementer\n"
        "pull_request: pandoscope/aet#262\ntickets: []\n",
    )
    env = {**ENV_RUN7_FIRED, **WAYBILL_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["resolved"]["role"] == "implementer"
    assert result.answers["order"]["pass"] is None
    assert "# Task" not in result.render_text


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


def test_an_order_without_the_pass_file_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    orders = session_root / "waybill" / "orders"
    orders.mkdir(parents=True)
    (orders / "probe-4.yml").write_text(
        "id: probe-4\nrole: reviewer\npass: spec-fidelity\ntier: sonnet\n"
        "pull_request: pandoscope/aet#262\ntickets: []\n"
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
    "id: probe-4\nrole: implementer\n"
    "pull_request: pandoscope/aet#262\ntickets: [pandoscope/skills#195]\n"
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
    ]


def test_a_fired_session_without_an_order_shouts(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    result = compose(ENV_RUN7_FIRED, session_root, home, path_dirs)
    assert "UNCONFIGURED" in result.render_text
    assert "WAITING" not in result.render_text


def test_the_order_carries_its_tickets_into_the_answers(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_pass_and_order(session_root, ORDER_IMPLEMENTER)
    env = {**ENV_RUN7_FIRED, **WAYBILL_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["order"]["tickets"] == ["pandoscope/skills#195"]
    assert result.answers["resolved"]["role"] == "implementer"


def test_an_order_declaring_general_renders_declared_general(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_pass_and_order(
        session_root, ORDER_IMPLEMENTER.replace("implementer", "general")
    )
    env = {**ENV_RUN7_FIRED, **WAYBILL_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["resolved"]["role"] == "general"
    assert "UNCONFIGURED" not in result.render_text
    assert "Role: general" in result.render_text


def _skill(session_root: Path, name: str) -> None:
    skill = session_root / "skills" / "original" / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n")


IMPLEMENTER_ORDER = (
    "id: probe-4\nrole: implementer\npull_request: pandoscope/aet#262\ntickets: []\n"
)


def test_role_install_follows_the_profile(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    # The shipped implementer profile names thread-ledger and handing-off.
    for name in ("thread-ledger", "handing-off", "grilling"):
        _skill(session_root, name)
    write_pass_and_order(session_root, IMPLEMENTER_ORDER)
    env = {**ENV_RUN7_FIRED, **WAYBILL_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.errors == []
    assert result.answers["installed"] == ["thread-ledger", "handing-off"]
    assert (home / ".claude" / "skills" / "handing-off" / "SKILL.md").is_file()
    assert not (home / ".claude" / "skills" / "grilling").exists()
    assert "- handing-off" in result.render_text


def test_missing_bundle_skill_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_pass_and_order(session_root, IMPLEMENTER_ORDER)
    env = {**ENV_RUN7_FIRED, **WAYBILL_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["resolved"]["role"] == "implementer"
    assert any("handing-off" in error for error in result.errors)
    assert "COMPOSER ERROR" in result.render_text
    assert result.answers["errors"] == result.errors


def test_a_session_without_an_order_prunes_what_a_role_left(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    for name in ("thread-ledger", "handing-off"):
        _skill(session_root, name)
    write_pass_and_order(session_root, IMPLEMENTER_ORDER)
    compose({**ENV_RUN7_FIRED, **WAYBILL_FIRE}, session_root, home, path_dirs)
    assert (home / ".claude" / "skills" / "handing-off").is_dir()
    # A fresh SessionStart with no order composes general and prunes
    # what an earlier role left (D15).
    compose(ENV_RUN5_UI, session_root, home, path_dirs)
    assert not (home / ".claude" / "skills" / "handing-off").exists()
