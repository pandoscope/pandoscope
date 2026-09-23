from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.cli import main

GOOD = """\
id: review-spec-fidelity-opus-pr26
role: reviewer
pass: spec-fidelity
tier: opus
pull_request: pandoscope/pandoscope#26
tickets:
  - pandoscope/skills#195
"""


def test_order_check_passes_a_valid_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    order = tmp_path / "orders" / "review-spec-fidelity-opus-pr26.yml"
    order.parent.mkdir()
    order.write_text(GOOD)
    assert main(["order", "check", str(order)]) == 0
    assert "ok" in capsys.readouterr().out


def test_order_check_names_every_violation_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    order = tmp_path / "orders" / "review-spec-fidelity-opus-pr26.yml"
    order.parent.mkdir()
    order.write_text(
        GOOD.replace("tier: opus", "tier: Opus").replace("id: review", "id: x-review")
    )
    assert main(["order", "check", str(order)]) == 1
    out = capsys.readouterr().out
    assert "tier" in out
    assert "id" in out
    assert str(order) in out
