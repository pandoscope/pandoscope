from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pandoscope.reinset.profiles import Profile
from pandoscope.reinset.render import (
    MARKER,
    NO_ROLE_HEADING,
    UnmanagedTargetError,
    render,
    write_render,
)

IMPLEMENTER = Profile(
    "implementer",
    "meta",
    Path("implementer.yml"),
    {"role": "implementer", "skills": ["tdd", "thread-ledger"], "prose": "Ship."},
)


def answers(role: str | None, source: str | None = None) -> dict[str, Any]:
    return {
        "detected": {"harness": "claude-code"},
        "resolved": {"role": role, "role_source": source},
        "order": None,
    }


def test_a_role_render_opens_with_the_line_that_names_the_role() -> None:
    # meta#195, second level: the repositories' rule looks for this line.
    text = render(answers("implementer", "declared"), IMPLEMENTER, [])
    assert text.splitlines()[0] == "# Role: implementer"
    assert "Source: declared." in text


def test_role_render_names_role_layer_and_skills() -> None:
    text = render(answers("implementer", "order"), IMPLEMENTER, [])
    assert "meta" in text
    assert "- tdd" in text
    assert "- thread-ledger" in text
    assert "Ship." in text
    assert NO_ROLE_HEADING not in text


def test_no_role_render_opens_with_its_line_and_asks_for_the_fixed_reply() -> None:
    text = render(answers(None), None, [])
    lines = text.splitlines()
    assert lines[0] == NO_ROLE_HEADING
    assert not any(line.startswith("# Role") for line in lines)
    # Decision 143, answer 4: no role is named general.
    assert "general" not in text
    assert "Every tool except the one that reads notifications is closed" in text
    reply = [line for line in lines if line.startswith("> ")]
    assert len(reply) == 1
    assert "This session has no role and does no work." in reply[0]
    assert "no waybill order, no environment role and no role line" in reply[0]
    assert "`role: implementer`" in reply[0]
    assert "`role: orchestrator`" in reply[0]


def test_the_fixed_reply_names_every_composer_error() -> None:
    error = "order waybill/orders/x.yml is off the schema: role: 'x' is not one of"
    text = render(answers(None), None, [error])
    assert f"COMPOSER ERROR: {error}" in text
    reply = next(line for line in text.splitlines() if line.startswith("> "))
    assert error in reply


def test_in_an_order_session_the_reply_asks_for_a_corrected_order() -> None:
    # meta#195: in a session that an order started, a declaration opens nothing.
    text = render(
        answers(None), None, ["order x is off the schema"], order_session=True
    )
    reply = next(line for line in text.splitlines() if line.startswith("> "))
    assert "Correct the waybill order and fire it again" in reply
    assert "role: implementer" not in reply


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
    text = render(answers("reviewer", "order"), reviewer, [], task="Review it.\n")
    assert text.endswith("## Task\n\nReview it.\n")
    assert text.index("# Role: reviewer") < text.index("## Task")
