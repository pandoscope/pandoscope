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
id: review_spec-fidelity_opus_pando26_1
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
# the name writes the waybill's shortcode `sk`,
# and an underscore separates its parts (decision 155).
IN_USE = {
    "review_spec-fidelity_opus_sk274_4": "opus",
    "review_spec-fidelity_sonnet_sk274_4": "sonnet",
    "review_spec-fidelity_opus_sk274_4b": "opus",
    "review_spec-fidelity_opus_sk274_6": "opus",
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
    order = waybill(tmp_path) / "review_spec-fidelity_opus_pando26_1.yml"
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


def test_an_implementer_order_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    order = waybill(tmp_path) / "implement_build_opus_pando57_1.yml"
    order.write_text(
        "id: implement_build_opus_pando57_1\nrole: implementer\npass: build\n"
        "model_tier: opus\n"
        "subject: pandoscope/pandoscope#57\ntickets: []\n"
    )
    assert main(["order", "check", str(order)]) == 0, capsys.readouterr().out


def test_order_check_names_every_violation_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    order = waybill(tmp_path) / "review_spec-fidelity_opus_pando26_1.yml"
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
    order = waybill(tmp_path) / "review_spec-fidelity_opus_pando26_1.yml"
    order.write_text(GOOD)
    (tmp_path / "shortcodes.json").unlink()
    assert main(["order", "check", str(order)]) == 1
    out = capsys.readouterr().out
    assert "shortcodes.json" in out
    assert "ok" not in out


def test_order_check_fails_an_order_of_a_role_that_is_no_worker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Decision 135: a probe is a subagent or a session, never an order.
    order = waybill(tmp_path) / "probe_look_opus_pando57_1.yml"
    order.write_text(
        "id: probe_look_opus_pando57_1\nrole: probe\npass: look\n"
        "model_tier: opus\nsubject: pandoscope/pandoscope#57\ntickets: []\n"
    )
    assert main(["order", "check", str(order)]) == 1
    out = capsys.readouterr().out
    assert "role:" in out
    assert "'probe'" in out


def test_order_check_run_inside_orders_finds_the_shortcodes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A bare file name has `.` for its parent (F4).
    orders = waybill(tmp_path)
    (orders / "review_spec-fidelity_opus_pando26_1.yml").write_text(GOOD)
    monkeypatch.chdir(orders)
    assert main(["order", "check", "review_spec-fidelity_opus_pando26_1.yml"]) == 0
    assert "ok" in capsys.readouterr().out


def test_order_check_with_a_second_shortcodes_file_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    order = waybill(tmp_path) / "review_spec-fidelity_opus_pando26_1.yml"
    order.write_text(GOOD)
    (tmp_path / "repo-codes.json").write_text("{}")
    assert main(["order", "check", str(order)]) == 1
    assert "repo-codes.json" in capsys.readouterr().out
