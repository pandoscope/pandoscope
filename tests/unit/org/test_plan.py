from __future__ import annotations

import pytest

from pandoscope.org.plan import Repo, default_plan


def plan() -> list[Repo]:
    return default_plan(
        "somnus-app",
        project="somnus",
        description="Battery wake diagnosis for Android.",
        approvers=["pando-genet"],
    )


def test_plan_names_the_org_repos_and_the_project() -> None:
    names = [repo.name for repo in plan()]
    assert names == [
        "meta",
        "somnus",
        "session-memory",
        "decision-memory",
        "evidence-memory",
        "waybill",
    ]


def test_every_repo_is_private_and_has_a_purpose() -> None:
    for repo in plan():
        assert repo.private
        assert repo.purpose


def test_meta_is_a_docs_stamp_owned_by_the_org() -> None:
    meta = plan()[0]
    assert meta.answers["agentic_subtemplate"] == "template"
    assert meta.answers["agentic_project_kind"] == "docs"
    assert meta.answers["agentic_repo_owner"] == "somnus-app"
    assert meta.answers["agentic_merge_approvers"] == "pando-genet"


def test_project_is_a_code_stamp_with_its_description() -> None:
    project = plan()[1]
    assert project.answers["agentic_project_kind"] == "code"
    assert project.answers["agentic_project_slug"] == "somnus"
    assert project.answers["agentic_project_description"] == (
        "Battery wake diagnosis for Android."
    )


def test_stores_use_their_subtemplate_and_no_project_questions() -> None:
    stores = {repo.name: repo for repo in plan()[2:5]}
    for name, repo in stores.items():
        assert repo.answers["agentic_subtemplate"] == name
        assert "agentic_project_name" not in repo.answers


def test_session_memory_takes_no_approval_answers() -> None:
    session = plan()[2]
    assert "agentic_merge_approvers" not in session.answers


def test_direct_push_repos_are_session_memory_and_waybill() -> None:
    direct = [repo.name for repo in plan() if repo.direct_pushes]
    assert direct == ["session-memory", "waybill"]


def test_waybill_is_not_stamped() -> None:
    waybill = plan()[-1]
    assert waybill.answers == {}
    assert not waybill.stamped


def test_every_stamped_repo_pins_the_runner() -> None:
    for repo in plan():
        if repo.stamped:
            assert repo.answers["agentic_actions_runner"] == "ubuntu-latest"


def test_plan_requires_an_approver() -> None:
    with pytest.raises(ValueError, match="approvers"):
        default_plan("o", project="p", description="d", approvers=[])


def test_project_named_like_an_org_repo_is_refused() -> None:
    with pytest.raises(ValueError, match="project='meta'"):
        default_plan("o", project="meta", description="d", approvers=["a"])
