from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.reinset.receive import find_order
from pandoscope.reinset.review import ReviewError, hydrate, pull_refs

from .conftest import pr_clone

PROMPT = """\
```text
Review <repo>#<n> (<pass>, tier <tier>): base <base>, head <head>.
Tickets: <tickets>.
```
"""

ORDER = (
    "id: probe-4\nrole: reviewer\npass: spec-fidelity\ntier: opus\n"
    "pull_request: pandoscope/aet#262\n"
    "tickets: [pandoscope/skills#179, pandoscope/aet#261]\n"
)

FIRE = {
    "CCR_TRIGGER_REPO": "pandoscope/waybill",
    "CCR_TRIGGER_HEAD_REF": "order/probe-4",
}


def write(session_root: Path, prompt: str = PROMPT, order: str = ORDER) -> None:
    review = session_root / "skills" / "original" / "thread-ledger" / "review"
    review.mkdir(parents=True)
    (review / "spec-fidelity.md").write_text(prompt)
    orders = session_root / "waybill" / "orders"
    orders.mkdir(parents=True)
    (orders / "probe-4.yml").write_text(order)


@pytest.mark.xfail(strict=True)
def test_pull_refs_reads_the_stacked_base_and_the_head(session_root: Path) -> None:
    head = pr_clone(session_root, "aet", 262)
    assert pull_refs(session_root / "aet", 262) == ("feature", head)


@pytest.mark.xfail(strict=True)
def test_pull_refs_without_the_clone_is_a_review_error(session_root: Path) -> None:
    with pytest.raises(ReviewError, match="aet"):
        pull_refs(session_root / "aet", 262)


@pytest.mark.xfail(strict=True)
def test_pull_refs_without_the_pull_ref_is_a_review_error(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    with pytest.raises(ReviewError, match="pull/263/head"):
        pull_refs(session_root / "aet", 263)


@pytest.mark.xfail(strict=True)
def test_hydrate_fills_every_placeholder_from_order_and_clone(
    session_root: Path,
) -> None:
    head = pr_clone(session_root, "aet", 262)
    write(session_root)
    order = find_order(FIRE, session_root)
    assert order is not None
    assert hydrate(session_root, order) == (
        "Review pandoscope/aet#262 (spec-fidelity, tier opus): "
        f"base feature, head {head}.\n"
        "Tickets: pandoscope/skills#179, pandoscope/aet#261.\n"
    )


@pytest.mark.xfail(strict=True)
def test_an_unfilled_placeholder_is_a_review_error(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    write(session_root, "```text\nReview <n> by <deadline>.\n```\n")
    order = find_order(FIRE, session_root)
    assert order is not None
    with pytest.raises(ReviewError, match="<deadline>"):
        hydrate(session_root, order)
