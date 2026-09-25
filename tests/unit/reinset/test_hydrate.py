from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.reinset.receive import find_order
from pandoscope.reinset.review import ReviewError, hydrate, pull_refs

from .conftest import commit, git, pr_clone

PROMPT = """\
Review <repo>#<n> (<pass>, tier <tier>): base <base>, head <head>.
Tickets: <tickets>.
"""

ORDER = (
    "id: probe-4\nrole: reviewer\npass: spec-fidelity\ntier: opus\n"
    "pull_request: pandoscope/aet#262\nbase: feature\n"
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


def review_branch_on(session_root: Path, head: str) -> None:
    """Push a branch built on the pull request head, as a reviewer does."""
    work = session_root.parent / "aet-origin-work"
    git(work, "switch", "-q", "-c", "claude/review-x-pr262", head)
    commit(work, "findings")
    git(work, "push", "-q", str(session_root.parent / "aet-origin.git"), "HEAD")
    git(work, "switch", "-q", "main")


def test_pull_refs_takes_the_orders_base(session_root: Path) -> None:
    # A review branch built on the pull request head is not its base.
    # The order's base holds against it (measured 2026-09-24).
    head = pr_clone(session_root, "aet", 262)
    review_branch_on(session_root, head)
    assert pull_refs(session_root / "aet", 262, "feature") == ("feature", head)


def test_pull_refs_without_a_base_takes_the_default_branch(
    session_root: Path,
) -> None:
    head = pr_clone(session_root, "aet", 262)
    assert pull_refs(session_root / "aet", 262) == ("main", head)


def test_an_unknown_base_is_a_review_error(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    with pytest.raises(ReviewError, match="nope"):
        pull_refs(session_root / "aet", 262, "nope")


def test_pull_refs_without_the_clone_is_a_review_error(session_root: Path) -> None:
    with pytest.raises(ReviewError, match="aet"):
        pull_refs(session_root / "aet", 262)


def test_pull_refs_without_the_pull_ref_is_a_review_error(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    with pytest.raises(ReviewError, match="pull/263/head"):
        pull_refs(session_root / "aet", 263)


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


def test_an_unfilled_placeholder_is_a_review_error(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    write(session_root, "Review <n> by <deadline>.\n")
    order = find_order(FIRE, session_root)
    assert order is not None
    with pytest.raises(ReviewError, match="<deadline>"):
        hydrate(session_root, order)


def test_missing_pass_file_is_a_review_error(session_root: Path) -> None:
    write(session_root)
    (session_root / "skills/original/thread-ledger/review/spec-fidelity.md").unlink()
    order = find_order(FIRE, session_root)
    assert order is not None
    with pytest.raises(ReviewError, match=r"spec-fidelity\.md"):
        hydrate(session_root, order)


def test_the_whole_pass_file_is_the_task(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    write(session_root, "# Task\n\nReview <repo>#<n>.\n\n```sh\ngit fetch\n```\n")
    order = find_order(FIRE, session_root)
    assert order is not None
    assert hydrate(session_root, order) == (
        "# Task\n\nReview pandoscope/aet#262.\n\n```sh\ngit fetch\n```\n"
    )


def test_a_clone_of_another_repository_is_a_review_error(session_root: Path) -> None:
    # Found by the opus review of pandoscope#31 (F001).
    pr_clone(session_root, "aet", 262)
    git(
        session_root / "aet",
        "remote",
        "set-url",
        "origin",
        "https://github.com/acme/aet",
    )
    write(session_root)
    order = find_order(FIRE, session_root)
    assert order is not None
    with pytest.raises(ReviewError, match="acme/aet"):
        hydrate(session_root, order)


def test_pull_refs_finds_main_after_main_moved_on(session_root: Path) -> None:
    head = pr_clone(session_root, "aet", 262, on_main=True)
    assert pull_refs(session_root / "aet", 262) == ("main", head)
