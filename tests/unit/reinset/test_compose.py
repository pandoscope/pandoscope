from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from pandoscope.reinset.compose import compose, declare
from pandoscope.reinset.principal import principal_id
from pandoscope.reinset.render import MARKER, NO_ROLE_HEADING, UnmanagedTargetError
from pandoscope.reinset.role import RoleRefused

from .conftest import (
    ENV_RUN5_UI,
    ENV_RUN7_FIRED,
    ORG_SALT,
    fire,
    pr_clone,
    write_waybill_order,
)


def test_no_source_writes_answers_and_renders_no_role(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    env = {**ENV_RUN5_UI, "REINSET_ORG_SALT": ORG_SALT}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers_path == home / ".claude" / "reinset" / "sess-fixture-0001.yml"
    on_disk = yaml.safe_load(result.answers_path.read_text())
    assert on_disk == result.answers
    assert on_disk["order"] is None
    assert on_disk["resolved"]["role"] is None
    assert on_disk["resolved"]["role_source"] is None
    assert result.role is None
    assert on_disk["resolved"]["principal"] == on_disk["detected"]["identity"]
    assert on_disk["errors"] == []
    assert on_disk["detected"]["identity"] == principal_id(
        "principal@example.test", ORG_SALT
    )
    assert result.render_path == home / ".claude" / "CLAUDE.md"
    assert result.render_path.read_text().startswith(MARKER)
    assert result.render_text.startswith(NO_ROLE_HEADING)
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


REVIEW_NAME = "review_spec-fidelity_sonnet_aet262_1"
IMPLEMENT_NAME = "implement_build_opus_aet261_1"
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
    assert result.answers["resolved"]["role_source"] == "order"
    assert result.render_text.startswith("# Role: reviewer")


def test_a_broken_order_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_pass_and_order(session_root, "- not a mapping\n")
    env = {**ENV_RUN7_FIRED, **WAYBILL_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert len(result.errors) == 1
    assert "mapping" in result.errors[0]
    assert result.answers["resolved"]["role"] is None
    assert "COMPOSER ERROR" in result.render_text
    assert "Correct the waybill order and fire it again" in result.render_text


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
    assert result.answers["resolved"]["role"] is None
    assert "COMPOSER ERROR" in result.render_text


# Ruling 2026-09-23 (skills#195), narrowed by meta#194: an order, REINSET_ROLE
# and a role line are the only sources. No other variable composes a role.
ORDER_IMPLEMENTER = (
    f"id: {IMPLEMENT_NAME}\nrole: implementer\npass: build\nmodel_tier: opus\n"
    "subject: pandoscope/aet#261\ntickets: [pandoscope/skills#195]\n"
)


def test_reinset_ref_is_not_a_channel(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    env = {**ENV_RUN7_FIRED, "REINSET_REF": "session-memory@0123abc:intents/x.yml"}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["resolved"]["role"] is None
    assert result.errors == []
    assert result.render_text.startswith(NO_ROLE_HEADING)
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


def test_a_fired_session_without_an_order_has_no_role(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    result = compose(ENV_RUN7_FIRED, session_root, home, path_dirs)
    assert result.render_text.startswith(NO_ROLE_HEADING)
    assert "WAITING" not in result.render_text


def test_the_order_carries_its_tickets_into_the_answers(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_pass_and_order(session_root, ORDER_IMPLEMENTER, IMPLEMENT_NAME)
    _bundles(session_root)
    env = {**ENV_RUN7_FIRED, **IMPLEMENT_FIRE}
    result = compose(env, session_root, home, path_dirs)
    assert result.answers["order"]["tickets"] == ["pandoscope/skills#195"]
    assert result.answers["resolved"]["role"] == "implementer"


@pytest.mark.parametrize("role", ["general", "orchestrator", "probe"])
def test_an_order_of_a_role_that_is_no_worker_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path], role: str
) -> None:
    # Decisions 135 and 143, meta#194: an order sets a worker role only.
    name = f"{role}_build_opus_aet261_1"
    write_pass_and_order(
        session_root,
        ORDER_IMPLEMENTER.replace("role: implementer", f"role: {role}").replace(
            IMPLEMENT_NAME, name
        ),
        name,
    )
    env = {**ENV_RUN7_FIRED, **fire(name)}
    result = compose(env, session_root, home, path_dirs)
    assert result.role is None
    assert len(result.errors) == 1, result.errors
    assert f"role: {role!r}" in result.errors[0]
    reply = next(
        line for line in result.render_text.splitlines() if line.startswith("> ")
    )
    assert f"role: {role!r}" in reply
    assert f"Role: {role}" not in result.render_text


def _skill(session_root: Path, name: str, *scripts: str) -> None:
    skill = session_root / "skills" / "original" / name
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
    for script in scripts:
        (skill / script).write_text("#!/bin/bash\n")


def _bundles(session_root: Path) -> None:
    """Every skill and hook script that the implementer and orchestrator name."""
    _skill(session_root, "thread-ledger")
    _skill(session_root, "grilling")
    _skill(session_root, "handing-off", "guard.sh", "verify.sh")


IMPLEMENTER_ORDER = (
    f"id: {IMPLEMENT_NAME}\nrole: implementer\npass: build\nmodel_tier: opus\n"
    "subject: pandoscope/aet#261\ntickets: []\n"
)


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


def test_missing_bundle_skill_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    write_pass_and_order(session_root, IMPLEMENTER_ORDER, IMPLEMENT_NAME)
    env = {**ENV_RUN7_FIRED, **IMPLEMENT_FIRE}
    result = compose(env, session_root, home, path_dirs)
    # meta#195: a composer error leaves the session without a role.
    assert result.answers["resolved"]["role"] is None
    assert any("handing-off" in error for error in result.errors)
    assert "COMPOSER ERROR" in result.render_text
    assert result.answers["errors"] == result.errors
    assert not result.hooks_path.exists()
    assert not (home / ".claude" / "skills" / "thread-ledger").exists()


def test_a_session_without_an_order_prunes_what_a_role_left(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    _bundles(session_root)
    write_pass_and_order(session_root, IMPLEMENTER_ORDER, IMPLEMENT_NAME)
    compose({**ENV_RUN7_FIRED, **IMPLEMENT_FIRE}, session_root, home, path_dirs)
    assert (home / ".claude" / "skills" / "handing-off").is_dir()
    # A fresh SessionStart with no source composes no role
    # and prunes what an earlier role left (meta#195).
    compose(ENV_RUN5_UI, session_root, home, path_dirs)
    assert not (home / ".claude" / "skills" / "handing-off").exists()


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


def test_a_session_without_a_role_has_no_hooks_file(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    # meta#195: the tool gate and the dispatcher read a missing file as no role.
    stale = home / ".claude" / "reinset" / "hooks.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}\n")
    result = compose(ENV_RUN5_UI, session_root, home, path_dirs)
    assert result.hooks_path == stale
    assert not stale.exists()


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
    assert result.role is None


# meta#194: the environment and a role line are sources besides the order.
PRINCIPAL = {**ENV_RUN5_UI, "CLAUDE_CODE_ENTRYPOINT": "remote_desktop"}


def _state(home: Path) -> dict[str, bytes]:
    """Every file the composer writes under ``home/.claude``, byte for byte."""
    claude = home / ".claude"
    return {
        str(path.relative_to(claude)): path.read_bytes()
        for path in sorted(claude.rglob("*"))
        if path.is_file()
    }


def test_the_environment_names_a_worker_role_from_session_start(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    _bundles(session_root)
    env = {**ENV_RUN5_UI, "REINSET_ROLE": "implementer"}
    result = compose(env, session_root, home, path_dirs)
    assert result.errors == []
    assert result.role == "implementer"
    assert result.answers["resolved"]["role_source"] == "environment"
    assert result.render_text.startswith("# Role: implementer")
    assert result.hooks_path.is_file()


def test_an_environment_naming_orchestrator_sets_no_role_and_says_why(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    _bundles(session_root)
    env = {**PRINCIPAL, "REINSET_ROLE": "orchestrator"}
    result = compose(env, session_root, home, path_dirs)
    assert result.role is None
    assert not result.hooks_path.exists()
    reply = next(
        line for line in result.render_text.splitlines() if line.startswith("> ")
    )
    assert "the environment names orchestrator" in reply
    assert "`role: implementer`" in reply


def test_a_declared_role_composes_with_the_source_declared(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    _bundles(session_root)
    compose(PRINCIPAL, session_root, home, path_dirs)
    result = declare("orchestrator", PRINCIPAL, session_root, home, path_dirs)
    assert result.errors == []
    assert result.role == "orchestrator"
    assert result.answers["resolved"]["role_source"] == "declared"
    assert (home / ".claude" / "skills" / "grilling" / "SKILL.md").is_file()
    assert json.loads(result.hooks_path.read_text())["PreCompact"]
    assert result.render_text.startswith("# Role: orchestrator")


def test_a_role_line_sets_the_role_again_over_the_environment(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    _bundles(session_root)
    env = {**PRINCIPAL, "REINSET_ROLE": "implementer"}
    compose(env, session_root, home, path_dirs)
    result = declare("orchestrator", env, session_root, home, path_dirs)
    assert result.role == "orchestrator"
    # The next SessionStart, a compaction's, keeps the declaration.
    again = compose(env, session_root, home, path_dirs)
    assert again.role == "orchestrator"
    assert again.answers["resolved"]["role_source"] == "declared"


def test_a_declaration_survives_the_composition_after_a_compaction(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    _bundles(session_root)
    declared = declare("implementer", ENV_RUN5_UI, session_root, home, path_dirs)
    before = _state(home)
    again = compose(ENV_RUN5_UI, session_root, home, path_dirs)
    assert again.role == "implementer"
    assert again.answers_path == declared.answers_path
    assert _state(home) == before


def test_another_session_id_does_not_inherit_a_declaration(
    session_root: Path, home: Path, path_dirs: list[Path], tmp_path: Path
) -> None:
    _bundles(session_root)
    answers = tmp_path / "answers.yml"
    env = {**ENV_RUN5_UI, "REINSET_ANSWERS": str(answers)}
    declare("implementer", env, session_root, home, path_dirs)
    other = {**env, "CLAUDE_CODE_SESSION_ID": "sess-fixture-0002"}
    assert compose(other, session_root, home, path_dirs).role is None


@pytest.mark.parametrize(
    ("role", "env", "reason"),
    [
        ("reviewer", ENV_RUN5_UI, "takes its pull request"),
        ("wizard", ENV_RUN5_UI, "declarable roles are orchestrator, implementer"),
        ("orchestrator", ENV_RUN5_UI, "only a session that the principal started"),
        ("implementer", {**ENV_RUN7_FIRED, **IMPLEMENT_FIRE}, "an order wins"),
    ],
)
def test_a_refused_role_line_changes_nothing(
    session_root: Path,
    home: Path,
    path_dirs: list[Path],
    role: str,
    env: dict[str, str],
    reason: str,
) -> None:
    _bundles(session_root)
    write_pass_and_order(session_root, ORDER_IMPLEMENTER, IMPLEMENT_NAME)
    compose(env, session_root, home, path_dirs)
    before = _state(home)
    with pytest.raises(RoleRefused, match=reason):
        declare(role, env, session_root, home, path_dirs)
    assert _state(home) == before


def test_a_role_line_in_an_order_session_without_a_role_opens_nothing(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    # meta#195: the principal corrects the order and fires it again.
    write_pass_and_order(session_root, "- not a mapping\n")
    env = {**ENV_RUN7_FIRED, **WAYBILL_FIRE}
    compose(env, session_root, home, path_dirs)
    with pytest.raises(RoleRefused, match="an order wins"):
        declare("implementer", env, session_root, home, path_dirs)
    assert not (home / ".claude" / "reinset" / "hooks.json").exists()


def test_setting_a_b_a_gives_the_state_of_the_first_a_byte_for_byte(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    # meta#194: setting a role is idempotent; B's skills, hooks and
    # instructions are gone once A is set again.
    _bundles(session_root)
    compose(PRINCIPAL, session_root, home, path_dirs)
    declare("implementer", PRINCIPAL, session_root, home, path_dirs)
    first_a = _state(home)
    declare("orchestrator", PRINCIPAL, session_root, home, path_dirs)
    assert _state(home) != first_a
    assert "skills/grilling/SKILL.md" in _state(home)
    declare("implementer", PRINCIPAL, session_root, home, path_dirs)
    assert _state(home) == first_a
