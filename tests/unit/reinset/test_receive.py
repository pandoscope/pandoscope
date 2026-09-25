from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.reinset.receive import OrderError, find_order

# When the Routine fires on waybill (waybill#1), the harness sets the
# trigger in the environment. It also checks out the order's pull
# request head. The order file is therefore on disk under the waybill
# clone.
WAYBILL_FIRE = {
    "CCR_TRIGGER_SOURCE": "github",
    "CCR_TRIGGER_EVENT": "pull_request.opened",
    "CCR_TRIGGER_REPO": "pandoscope/waybill",
    "CCR_TRIGGER_PR_NUMBER": "5",
    "CCR_TRIGGER_HEAD_REF": "order/probe-4",
    "CCR_TRIGGER_BASE_REF": "main",
    "CCR_TRIGGER_HEAD_SHA": "3cb001e",
}
ORDER = """\
id: probe-4
role: reviewer
pass: spec-fidelity
model_tier: opus
pull_request: pandoscope/pandoscope#26
checkouts:
  pandoscope/skills: claude/sk195-review-driver
tickets:
  - pandoscope/waybill#1
"""


def write_order(session_root: Path, text: str = ORDER, name: str = "probe-4") -> None:
    orders = session_root / "waybill" / "orders"
    orders.mkdir(parents=True, exist_ok=True)
    (orders / f"{name}.yml").write_text(text)


def test_the_order_is_read_from_the_fired_branch(session_root: Path) -> None:
    write_order(session_root)
    order = find_order(WAYBILL_FIRE, session_root)
    assert order is not None
    assert order.pull_request == 26
    assert order.data["role"] == "reviewer"
    assert (order.role, order.pass_, order.model_tier) == (
        "reviewer",
        "spec-fidelity",
        "opus",
    )
    assert order.path == session_root / "waybill" / "orders" / "probe-4.yml"
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
    with pytest.raises(OrderError, match=r"probe-4\.yml"):
        find_order(WAYBILL_FIRE, session_root)
    write_order(session_root, "- not\n- a mapping\n")
    with pytest.raises(OrderError, match="mapping"):
        find_order(WAYBILL_FIRE, session_root)
    write_order(session_root, "id: probe-4\npull_request: 26\n")
    with pytest.raises(OrderError, match="pull_request"):
        find_order(WAYBILL_FIRE, session_root)


def test_an_order_off_the_schema_raises_naming_every_field(session_root: Path) -> None:
    # The schema is strict.
    # A model that misspells a key or writes the model tier in caps
    # gets a composer error, not a half-read order.
    write_order(
        session_root,
        "id: probe-4\nrole: reviewer\npass: spec-fidelity\nmodel_tier: Opus\n"
        "pull_request: pandoscope/pandoscope#26\ntickets: []\npull-request: x\n",
    )
    with pytest.raises(OrderError) as raised:
        find_order(WAYBILL_FIRE, session_root)
    assert "tier" in str(raised.value)
    assert "pull-request" in str(raised.value)


def test_the_receiver_knows_no_reference_channel() -> None:
    import pandoscope.reinset.receive as receive

    for gone in ("find_reference", "parse_reference", "REF_ENV", "PAYLOAD_BLOCK"):
        assert not hasattr(receive, gone)
