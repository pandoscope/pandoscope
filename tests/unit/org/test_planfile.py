from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.org.plan import Repo, default_plan
from pandoscope.org.planfile import read_plan, render_plan

TWO_PROJECTS = """\
org: o
approvers: [human]
repos:
  - name: meta
    title: Meta
    kind: docs
    purpose: Org-level docs.
  - name: app
    kind: code
    purpose: The app.
  - name: helper
    kind: code
    purpose: The helper.
"""


def plan_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "org.yml"
    path.write_text(text)
    return path


def by_name(plan: list[Repo]) -> dict[str, Repo]:
    return {repo.name: repo for repo in plan}


def test_every_code_and_docs_entry_becomes_a_stamped_repo_of_the_org(
    tmp_path: Path,
) -> None:
    repos = by_name(read_plan(plan_file(tmp_path, TWO_PROJECTS), "o"))
    assert list(repos) == ["meta", "app", "helper"]
    assert repos["meta"].answers["agentic_project_kind"] == "docs"
    assert repos["meta"].answers["agentic_project_name"] == "Meta"
    assert repos["helper"].answers["agentic_project_kind"] == "code"
    assert repos["helper"].answers["agentic_project_slug"] == "helper"
    assert repos["helper"].answers["agentic_project_description"] == "The helper."
    assert repos["helper"].answers["agentic_repo_owner"] == "o"
    assert repos["helper"].answers["agentic_merge_approvers"] == "human"
    assert repos["helper"].purpose == "The helper."
    assert repos["helper"].private

STORES = """\
org: o
approvers: [human]
repos:
  - name: pando-session-memory
    kind: store
    store: session-memory
    purpose: Session store.
    direct_pushes: true
  - name: pando-decision-memory
    kind: store
    store: decision-memory
    purpose: Decision store.
"""


def test_a_store_entry_is_stamped_from_its_store_subtemplate_under_its_own_name(
    tmp_path: Path,
) -> None:
    repos = by_name(read_plan(plan_file(tmp_path, STORES), "o"))
    session = repos["pando-session-memory"]
    decision = repos["pando-decision-memory"]
    assert session.answers["agentic_subtemplate"] == "session-memory"
    assert decision.answers["agentic_subtemplate"] == "decision-memory"
    assert "agentic_project_name" not in decision.answers
    assert decision.answers["agentic_merge_approvers"] == "human"


def test_a_direct_push_entry_takes_no_approval_answers(tmp_path: Path) -> None:
    session = by_name(read_plan(plan_file(tmp_path, STORES), "o"))[
        "pando-session-memory"
    ]
    assert session.direct_pushes
    assert "agentic_merge_approval_gate" not in session.answers


def test_a_plain_entry_is_created_but_not_stamped(tmp_path: Path) -> None:
    text = """\
org: o
approvers: [human]
repos:
  - name: pando-waybill
    kind: plain
    purpose: Orders.
    direct_pushes: true
    private: false
"""
    (waybill,) = read_plan(plan_file(tmp_path, text), "o")
    assert not waybill.stamped
    assert not waybill.private


def one_repo(entry: str, org: str = "o") -> str:
    return f"org: {org}\napprovers: [human]\nrepos:\n{entry}"


@pytest.mark.parametrize(
    ("text", "named"),
    [
        (one_repo("  - {name: a, kind: code, purpose: p}\n", org="other"), "other"),
        (one_repo("  - {name: a, kind: library, purpose: p}\n"), "library"),
        (one_repo("  - {name: a, kind: store, purpose: p}\n"), "store"),
        (
            one_repo("  - {name: a, kind: store, store: ledger, purpose: p}\n"),
            "ledger",
        ),
        (
            one_repo(
                "  - {name: twin, kind: code, purpose: p}\n"
                "  - {name: twin, kind: docs, purpose: q}\n"
            ),
            "twin",
        ),
    ],
    ids=["other-org", "unknown-kind", "store-without-store", "unknown-store", "dup"],
)
def test_an_invalid_plan_file_is_refused_naming_the_value(
    tmp_path: Path, text: str, named: str
) -> None:
    with pytest.raises(ValueError, match=named):
        read_plan(plan_file(tmp_path, text), "o")


@pytest.mark.xfail(strict=True)
def test_the_rendered_default_plan_reads_back_as_the_same_plan(
    tmp_path: Path,
) -> None:
    plan = default_plan(
        "o", project="app", description="The app.", approvers=["human", "second"]
    )
    text = render_plan("o", ["human", "second"], plan)
    assert read_plan(plan_file(tmp_path, text), "o") == plan
