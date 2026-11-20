from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.reinset.receive import OrderError, find_order

from .conftest import fire, write_waybill_order

NAME = "review_spec-fidelity_opus_pando26_1"
WAYBILL_FIRE = fire(NAME)
ORDER = f"""\
id: {NAME}
role: reviewer
pass: spec-fidelity
model_tier: opus
subject: pandoscope/pandoscope#26
checkouts:
  pandoscope/skills: claude/sk195-review-driver
tickets:
  - pandoscope/waybill#1
"""


def write_order(session_root: Path, text: str = ORDER, name: str = NAME) -> None:
    write_waybill_order(session_root, name, text)


def test_the_order_is_read_from_the_fired_branch(session_root: Path) -> None:
    write_order(session_root)
    order = find_order(WAYBILL_FIRE, session_root)
    assert order is not None
    assert order.subject == "pandoscope/pandoscope#26"
    assert (order.repo, order.code, order.number) == (
        "pandoscope/pandoscope",
        "pando",
        26,
    )
    assert order.data["role"] == "reviewer"
    assert (order.role, order.pass_, order.model_tier) == (
        "reviewer",
        "spec-fidelity",
        "opus",
    )
    assert order.path == session_root / "waybill" / "orders" / f"{NAME}.yml"
    assert order.tickets == ["pandoscope/waybill#1"]


def test_a_fire_from_another_repo_carries_no_order(session_root: Path) -> None:
    write_order(session_root)
    env = {**WAYBILL_FIRE, "CCR_TRIGGER_REPO": "pandoscope/skills"}
    assert find_order(env, session_root) is None
    assert find_order({}, session_root) is None


def test_a_branch_outside_order_slash_carries_no_order(session_root: Path) -> None:
    write_order(session_root)
    env = {**WAYBILL_FIRE, "CCR_TRIGGER_HEAD_REF": "probe/branch-fire"}
    assert find_order(env, session_root) is None


def test_a_missing_or_malformed_order_file_raises(session_root: Path) -> None:
    with pytest.raises(OrderError, match=rf"{NAME}\.yml"):
        find_order(WAYBILL_FIRE, session_root)
    write_order(session_root, "- not\n- a mapping\n")
    with pytest.raises(OrderError, match="mapping"):
        find_order(WAYBILL_FIRE, session_root)
    write_order(session_root, f"id: {NAME}\nsubject: 26\n")
    with pytest.raises(OrderError, match="subject"):
        find_order(WAYBILL_FIRE, session_root)


def test_an_order_off_the_schema_raises_naming_every_field(session_root: Path) -> None:
    # The schema is strict.
    # A model that misspells a key or writes the model tier in caps
    # gets a composer error, not a half-read order.
    write_order(
        session_root,
        f"id: {NAME}\nrole: reviewer\npass: spec-fidelity\nmodel_tier: Opus\n"
        "subject: pandoscope/pandoscope#26\ntickets: []\npull-request: x\n",
    )
    with pytest.raises(OrderError) as raised:
        find_order(WAYBILL_FIRE, session_root)
    assert "tier" in str(raised.value)
    assert "pull-request" in str(raised.value)


def test_an_order_whose_name_disagrees_with_its_fields_raises(
    session_root: Path,
) -> None:
    write_order(session_root, ORDER.replace("model_tier: opus", "model_tier: sonnet"))
    with pytest.raises(OrderError, match="the model_tier part"):
        find_order(WAYBILL_FIRE, session_root)


def test_an_order_without_the_waybills_shortcodes_raises(session_root: Path) -> None:
    write_order(session_root)
    (session_root / "waybill" / "shortcodes.json").unlink()
    with pytest.raises(OrderError, match=r"shortcodes\.json"):
        find_order(WAYBILL_FIRE, session_root)


def test_an_order_beside_a_second_shortcodes_file_raises(session_root: Path) -> None:
    write_order(session_root)
    (session_root / "waybill" / "orders" / "shortcodes.json").write_text("{}")
    with pytest.raises(OrderError, match=r"orders/shortcodes\.json"):
        find_order(WAYBILL_FIRE, session_root)


def test_the_receiver_knows_no_reference_channel() -> None:
    import pandoscope.reinset.receive as receive

    for gone in ("find_reference", "parse_reference", "REF_ENV", "PAYLOAD_BLOCK"):
        assert not hasattr(receive, gone)
