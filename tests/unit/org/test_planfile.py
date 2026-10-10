from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.org.plan import Repo
from pandoscope.org.planfile import read_plan

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


@pytest.mark.xfail(strict=True)
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
