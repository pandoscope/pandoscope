from __future__ import annotations

import json
from pathlib import Path

import pytest

from pandoscope.reinset.receive import find_order
from pandoscope.reinset.review import ReviewError, hydrate, pull_refs

from .conftest import commit, git, pr_clone

PROMPT = """\
Review {{ repo }}#{{ n }} ({{ pass }}, tier {{ model_tier }}):
base {{ base }}, head {{ head }}.
Tickets: {{ tickets }}.
"""

ORDER = (
    "id: probe-4\nrole: reviewer\npass: spec-fidelity\nmodel_tier: opus\n"
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
        "Review pandoscope/aet#262 (spec-fidelity, tier opus):\n"
        f"base feature, head {head}.\n"
        "Tickets: pandoscope/skills#179, pandoscope/aet#261.\n"
    )


def test_an_unfilled_placeholder_is_a_review_error(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    write(session_root, "Review {{ n }} by {{ deadline }}.\n")
    order = find_order(FIRE, session_root)
    assert order is not None
    with pytest.raises(ReviewError, match="deadline"):
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
    write(
        session_root, "# Task\n\nReview {{ repo }}#{{ n }}.\n\n```sh\ngit fetch\n```\n"
    )
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


def test_the_task_is_a_jinja_template(session_root: Path) -> None:
    # Found by the opus review of pandoscope#31 (F002):
    # markup in angle brackets is text,
    # and only a template variable is a placeholder.
    pr_clone(session_root, "aet", 262)
    write(session_root, "Review {{ repo }}#{{ n }}.<br> <details>\n")
    order = find_order(FIRE, session_root)
    assert order is not None
    assert hydrate(session_root, order) == "Review pandoscope/aet#262.<br> <details>\n"


def test_an_undefined_template_variable_is_a_review_error(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    write(session_root, "Review {{ n }} with {{ tiker }}.\n")
    order = find_order(FIRE, session_root)
    assert order is not None
    with pytest.raises(ReviewError, match="tiker"):
        hydrate(session_root, order)


SCHEMA = {
    "type": "object",
    "required": ["pr", "findings"],
    "properties": {
        "pr": {"type": "string", "description": "the pull request"},
        "findings": {
            "type": "array",
            "description": "the findings, worst first",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer", "description": "the line"},
                    "finding_basis": {
                        "enum": ["decided", "judged"],
                        "description": "whether the rule settles it",
                    },
                },
            },
        },
    },
}


def test_findings_contract_renders_the_schema_in_plain_terms(
    session_root: Path,
) -> None:
    # The schema is the one home of the findings contract (skills#225).
    pr_clone(session_root, "aet", 262)
    write(session_root, "Fields:\n\n{{ findings_contract }}\n")
    review = session_root / "skills" / "original" / "thread-ledger" / "review"
    (review / "findings.schema.json").write_text(json.dumps(SCHEMA))
    order = find_order(FIRE, session_root)
    assert order is not None
    assert hydrate(session_root, order) == (
        "Fields:\n\n"
        "- `pr` (string): the pull request\n"
        "- `findings` (array): the findings, worst first. Each item:\n"
        "  - `line` (integer): the line\n"
        "  - `finding_basis` (`decided` or `judged`): whether the rule settles it\n"
    )


def test_hydrate_switches_the_clone_to_the_review_branch_at_the_head(
    session_root: Path,
) -> None:
    # The reviewer runs no git steps (skills#224).
    head = pr_clone(session_root, "aet", 262)
    write(session_root)
    order = find_order(FIRE, session_root)
    assert order is not None
    hydrate(session_root, order)
    clone = session_root / "aet"
    assert git(clone, "branch", "--show-current") == (
        "claude/review-spec-fidelity-opus-pr262"
    )
    assert git(clone, "rev-parse", "HEAD") == head


def test_pull_refs_finds_main_after_main_moved_on(session_root: Path) -> None:
    head = pr_clone(session_root, "aet", 262, on_main=True)
    assert pull_refs(session_root / "aet", 262) == ("main", head)


def stub_check(session_root: Path, body: str) -> None:
    """Install a writing-prose check.sh that runs ``body``, as the skills clone does."""
    check = session_root / "skills" / "original" / "writing-prose" / "check.sh"
    check.parent.mkdir(parents=True)
    check.write_text(f"#!/usr/bin/env bash\n{body}\n")


@pytest.mark.xfail(strict=True)
def test_candidates_are_the_prose_check_hits_on_the_changed_files(
    session_root: Path,
) -> None:
    # The composer runs the check; the reviewer never executes it (skills#220).
    pr_clone(session_root, "aet", 262)
    write(session_root, "Candidates:\n{{ candidates }}\n")
    stub_check(
        session_root,
        'echo "$2:1: H hedging: cut it ($1)"\necho "M rule to judge"\nexit 1',
    )
    order = find_order(FIRE, session_root)
    assert order is not None
    assert hydrate(session_root, order) == (
        "Candidates:\npr-1:1: H hedging: cut it (comment)\n"
    )


@pytest.mark.xfail(strict=True)
def test_no_candidates_render_none(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    write(session_root, "Candidates: {{ candidates }}\n")
    stub_check(session_root, "exit 0")
    order = find_order(FIRE, session_root)
    assert order is not None
    assert hydrate(session_root, order) == "Candidates: none\n"


@pytest.mark.xfail(strict=True)
def test_a_failing_prose_check_is_a_review_error(session_root: Path) -> None:
    # A crashed check must not read as no candidates.
    pr_clone(session_root, "aet", 262)
    write(session_root, "Candidates: {{ candidates }}\n")
    stub_check(session_root, "echo broken >&2\nexit 2")
    order = find_order(FIRE, session_root)
    assert order is not None
    with pytest.raises(ReviewError, match="broken"):
        hydrate(session_root, order)


@pytest.mark.xfail(strict=True)
def test_candidates_without_the_prose_check_is_a_review_error(
    session_root: Path,
) -> None:
    pr_clone(session_root, "aet", 262)
    write(session_root, "Candidates: {{ candidates }}\n")
    order = find_order(FIRE, session_root)
    assert order is not None
    with pytest.raises(ReviewError, match=r"check\.sh"):
        hydrate(session_root, order)
