from __future__ import annotations

import json
from pathlib import Path

import pytest

from pandoscope.cli import main

SHORTCODES = {
    "_comment": "the waybill's own comment key",
    "pando": "pandoscope/pandoscope",
    "sk": "pandoscope/skills",
}
GOOD = """\
id: review-spec-fidelity-opus-pando26-1
role: reviewer
pass: spec-fidelity
model_tier: opus
subject: pandoscope/pandoscope#26
tickets:
  - pandoscope/skills#195
"""
# The four review orders open in pandoscope/waybill on 2026-11-18
# (waybill#68 to #71), with the changes a placer now makes:
# `pull_request` is `subject`, the name ends in the step number,
# and the name writes the waybill's shortcode `sk`.
IN_USE = {
    "review-spec-fidelity-opus-sk274-4": "opus",
    "review-spec-fidelity-sonnet-sk274-4": "sonnet",
    "review-spec-fidelity-opus-sk274-4b": "opus",
    "review-spec-fidelity-opus-sk274-6": "opus",
}
IN_USE_ORDER = """\
id: {name}
role: reviewer
pass: spec-fidelity
model_tier: {tier}
subject: pandoscope/skills#274
checkouts:
  pandoscope/skills: main
tickets:
  - pandoscope/skills#267
"""


def waybill(tmp_path: Path) -> Path:
    """A waybill checkout with its shortcodes file and an empty orders folder."""
    (tmp_path / "shortcodes.json").write_text(json.dumps(SHORTCODES))
    orders = tmp_path / "orders"
    orders.mkdir()
    return orders


def test_order_check_passes_a_valid_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    order = waybill(tmp_path) / "review-spec-fidelity-opus-pando26-1.yml"
    order.write_text(GOOD)
    assert main(["order", "check", str(order)]) == 0
    assert "ok" in capsys.readouterr().out


def test_the_review_orders_in_use_pass_in_the_new_form(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    orders = waybill(tmp_path)
    files = []
    for name, tier in IN_USE.items():
        path = orders / f"{name}.yml"
        path.write_text(IN_USE_ORDER.format(name=name, tier=tier))
        files.append(str(path))
    assert main(["order", "check", *files]) == 0, capsys.readouterr().out


@pytest.mark.xfail(strict=True)
def test_an_implementer_order_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    order = waybill(tmp_path) / "implement-build-opus-pando57-1.yml"
    order.write_text(
        "id: implement-build-opus-pando57-1\nrole: implementer\npass: build\n"
        "model_tier: opus\n"
        "subject: pandoscope/pandoscope#57\ntickets: []\n"
    )
    assert main(["order", "check", str(order)]) == 0, capsys.readouterr().out


def test_order_check_names_every_violation_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    order = waybill(tmp_path) / "review-spec-fidelity-opus-pando26-1.yml"
    order.write_text(
        GOOD.replace("model_tier: opus", "model_tier: Opus").replace(
            "id: review", "id: x-review"
        )
    )
    assert main(["order", "check", str(order)]) == 1
    out = capsys.readouterr().out
    assert "tier" in out
    assert "id" in out
    assert str(order) in out


def test_order_check_without_the_shortcodes_file_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    order = waybill(tmp_path) / "review-spec-fidelity-opus-pando26-1.yml"
    order.write_text(GOOD)
    (tmp_path / "shortcodes.json").unlink()
    assert main(["order", "check", str(order)]) == 1
    out = capsys.readouterr().out
    assert "shortcodes.json" in out
    assert "ok" not in out


@pytest.mark.xfail(strict=True)
def test_order_check_tells_a_role_without_a_name_pattern(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # DECISION:FALLBACK in order_name.py: the person placing it is told here.
    order = waybill(tmp_path) / "probe-opus-4.yml"
    order.write_text(
        "id: probe-opus-4\nrole: probe\npass: look\nmodel_tier: opus\n"
        "subject: pandoscope/pandoscope#57\ntickets: []\n"
    )
    assert main(["order", "check", str(order)]) == 0
    assert "no name pattern" in capsys.readouterr().out


def test_order_check_run_inside_orders_finds_the_shortcodes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A bare file name has `.` for its parent (F4).
    orders = waybill(tmp_path)
    (orders / "review-spec-fidelity-opus-pando26-1.yml").write_text(GOOD)
    monkeypatch.chdir(orders)
    assert main(["order", "check", "review-spec-fidelity-opus-pando26-1.yml"]) == 0
    assert "ok" in capsys.readouterr().out


def test_order_check_with_a_second_shortcodes_file_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    order = waybill(tmp_path) / "review-spec-fidelity-opus-pando26-1.yml"
    order.write_text(GOOD)
    (tmp_path / "repo-codes.json").write_text("{}")
    assert main(["order", "check", str(order)]) == 1
    assert "repo-codes.json" in capsys.readouterr().out
