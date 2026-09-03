from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pandoscope.reinset.profiles import Profile
from pandoscope.reinset.render import (
    MARKER,
    UnmanagedTargetError,
    render,
    write_render,
)

GENERAL = Profile(
    "general", "pandoscope", Path("general.yml"), {"role": "general", "skills": []}
)
IMPLEMENTER = Profile(
    "implementer",
    "meta",
    Path("implementer.yml"),
    {"role": "implementer", "skills": ["tdd", "thread-ledger"], "prose": "Ship."},
)


def answers(
    role: str, mismatches: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "detected": {"harness": "claude-code"},
        "passed": None,
        "resolved": {"role": role},
        "mismatches": mismatches or [],
    }


def test_general_is_the_loud_unconfigured_state() -> None:
    text = render(answers("general"), GENERAL, [])
    assert "UNCONFIGURED" in text
    # The one concession (D15): one line that declares orchestrator.
    declaration = [line for line in text.splitlines() if "REINSET_REF" in line]
    assert len(declaration) == 1
    assert "orchestrator" in declaration[0]
    # Nothing else is installed.
    assert "skill" not in text.lower()
    assert not text.lstrip().startswith("# Role")


def test_role_render_names_role_layer_and_skills() -> None:
    text = render(answers("implementer"), IMPLEMENTER, [])
    assert "implementer" in text
    assert "meta" in text
    assert "- tdd" in text
    assert "- thread-ledger" in text
    assert "Ship." in text
    assert "UNCONFIGURED" not in text


def test_composer_errors_are_rendered_loudly() -> None:
    error = "reinset reference names no role (session-memory@abc:intents/x.yml)"
    text = render(answers("general"), GENERAL, [error])
    assert "COMPOSER ERROR" in text
    assert error in text
    assert "UNCONFIGURED" in text


def test_mismatches_are_rendered() -> None:
    mismatch = {
        "key": "origin",
        "passed": "spawner",
        "detected": "principal",
        "resolved_to": "spawner",
    }
    text = render(answers("implementer", [mismatch]), IMPLEMENTER, [])
    assert "MISMATCH" in text
    assert "origin" in text
    assert "passed=spawner" in text
    assert "detected=principal" in text


def test_write_render_puts_the_marker_first_and_rewrites_whole(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    write_render(target, "first render\n")
    write_render(target, "second render\n")
    lines = target.read_text().splitlines()
    assert lines[0] == MARKER
    assert "first render" not in lines
    assert "second render" in lines


def test_write_render_refuses_an_unmanaged_file(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    target.write_text("hand-written user instructions\n")
    with pytest.raises(UnmanagedTargetError, match=str(target)):
        write_render(target, "render\n")
    assert target.read_text() == "hand-written user instructions\n"


def test_declared_general_is_configured_and_installs_nothing() -> None:
    # Measured 2026-09-03 (role test r0a4): a reference declaring
    # `role: general` rendered the unconfigured notice, which says no
    # reference arrived. A declared general is a configured session
    # that installs nothing; the render must say that, not deny the
    # reference.
    declared = answers("general")
    declared["passed"] = {"spawn_id": "spawn-r0a4", "role": "general"}
    text = render(declared, GENERAL, [])
    assert "UNCONFIGURED" not in text
    assert "no intent reference" not in text
    assert "Role: general" in text
    assert "nothing is installed" in text
    assert "skill" not in text.lower()


def test_spawned_session_without_reference_waits_instead_of_shouting() -> None:
    # D21 (2026-09-03): a spawned session's reference arrives with the
    # first prompt, one step after SessionStart. Its SessionStart pass
    # renders a waiting state, not the loud notice.
    waiting = answers("general")
    waiting["detected"] = {"harness": "claude-code", "spawned": True}
    text = render(waiting, GENERAL, [])
    assert "UNCONFIGURED" not in text
    assert "WAITING" in text
    assert "first prompt" in text
    assert "skill" not in text.lower()


def test_unspawned_session_without_reference_still_shouts() -> None:
    plain = answers("general")
    plain["detected"] = {"harness": "claude-code", "spawned": False}
    assert "UNCONFIGURED" in render(plain, GENERAL, [])
