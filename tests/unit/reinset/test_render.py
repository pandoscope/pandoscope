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


def answers(role: str) -> dict[str, Any]:
    return {
        "detected": {"harness": "claude-code"},
        "resolved": {"role": role},
        "order": None,
    }


def test_general_is_the_loud_unconfigured_state() -> None:
    text = render(answers("general"), GENERAL, [])
    assert "UNCONFIGURED" in text
    # Nothing is installed (D15).
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
    error = "order waybill/orders/x.yml is off the schema: role: 'x' is not one of"
    text = render(answers("general"), GENERAL, [error])
    assert "COMPOSER ERROR" in text
    assert error in text
    assert "UNCONFIGURED" in text


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


def test_a_task_is_rendered_after_the_profile() -> None:
    reviewer = Profile(
        "reviewer", "pandoscope", Path("reviewer.yml"), {"role": "reviewer"}
    )
    text = render(answers("reviewer"), reviewer, [], task="Review it.\n")
    assert text.endswith("## Task\n\nReview it.\n")
    assert text.index("# Role: reviewer") < text.index("## Task")


def test_the_unconfigured_declaration_points_at_the_order() -> None:
    text = render(answers("general"), GENERAL, [])
    assert "REINSET_REF" not in text
    declaration = [line for line in text.splitlines() if "order/" in line]
    assert len(declaration) == 1
    assert "waybill" in declaration[0]


def test_general_declared_by_an_order_is_configured() -> None:
    declared = answers("general")
    declared["order"] = {"role": "general", "pull_request": 1}
    text = render(declared, GENERAL, [])
    assert "UNCONFIGURED" not in text
    assert "Role: general" in text
    assert "nothing is installed" in text


def test_a_fired_session_without_an_order_shouts() -> None:
    fired = answers("general")
    fired["detected"] = {"harness": "claude-code", "spawned": True}
    text = render(fired, GENERAL, [])
    assert "WAITING" not in text
    assert "UNCONFIGURED" in text
