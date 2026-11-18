from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.reinset.compose import compose
from pandoscope.reinset.implement import ImplementError, implementer_task
from pandoscope.reinset.receive import Order, find_order

from .conftest import ENV_RUN7_FIRED, fire, git, pr_clone, write_waybill_order

# pr_clone makes pull request 262; 261 is no pull request, so an issue.
BUILD = "implement-build-opus-aet261-1"
BUILD_ORDER = (
    f"id: {BUILD}\nrole: implementer\npass: build\nmodel_tier: opus\n"
    "subject: pandoscope/aet#261\ntickets: [pandoscope/skills#195]\n"
)
FIX = "implement-fix-opus-aet262-3"
FIX_ORDER = (
    f"id: {FIX}\nrole: implementer\npass: fix\nmodel_tier: opus\n"
    "subject: pandoscope/aet#262\ntickets: [pandoscope/aet#261]\n"
)
PR_BRANCH = "claude/aet261-feature"


def order_of(session_root: Path, name: str, text: str) -> Order:
    write_waybill_order(session_root, name, text)
    order = find_order(fire(name), session_root)
    assert order is not None
    return order


def pr_branch(session_root: Path, head: str) -> None:
    """Point the branch of pull request 262 at its head, as the forge does."""
    origin = session_root.parent / "aet-origin.git"
    git(origin, "update-ref", f"refs/heads/{PR_BRANCH}", head)


def dispositions(session_root: Path) -> Path:
    path = session_root / "waybill" / "dispositions"
    path.mkdir(parents=True)
    (path / "README.md").write_text("# Disposition files\n")
    return path


@pytest.mark.xfail(strict=True)
def test_a_first_build_states_its_tickets_and_its_branch(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    task = implementer_task(session_root, order_of(session_root, BUILD, BUILD_ORDER))
    assert "pandoscope/aet#261" in task
    assert "pandoscope/skills#195" in task
    assert "`claude/aet261-implement-1`" in task
    assert "`origin/main`" in task
    assert "pull request" in task
    assert "dispositions" not in task


@pytest.mark.xfail(strict=True)
def test_a_first_build_takes_the_orders_base(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    order = order_of(session_root, BUILD, BUILD_ORDER + "base: feature\n")
    assert "`origin/feature`" in implementer_task(session_root, order)


@pytest.mark.xfail(strict=True)
def test_a_repeat_run_gets_a_branch_of_its_own(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    name = "implement-build-opus-aet261-1b"
    order = order_of(session_root, name, BUILD_ORDER.replace(BUILD, name))
    assert "`claude/aet261-implement-1b`" in implementer_task(session_root, order)


@pytest.mark.xfail(strict=True)
def test_a_fix_round_works_on_the_pull_requests_branch_and_its_dispositions(
    session_root: Path,
) -> None:
    head = pr_clone(session_root, "aet", 262)
    pr_branch(session_root, head)
    folder = dispositions(session_root)
    task = implementer_task(session_root, order_of(session_root, FIX, FIX_ORDER))
    assert f"`{PR_BRANCH}`" in task
    assert "pandoscope/aet#262" in task
    assert "pandoscope/aet#261" in task
    assert str(folder) in task
    assert "`status: open`" in task
    assert "`owner`" in task
    assert "implement-1" not in task


@pytest.mark.xfail(strict=True)
def test_a_fix_round_without_a_branch_at_the_head_is_an_error(
    session_root: Path,
) -> None:
    pr_clone(session_root, "aet", 262)
    dispositions(session_root)
    order = order_of(session_root, FIX, FIX_ORDER)
    with pytest.raises(ImplementError, match="no branch"):
        implementer_task(session_root, order)


@pytest.mark.xfail(strict=True)
def test_a_fix_round_with_two_branches_at_the_head_is_an_error(
    session_root: Path,
) -> None:
    head = pr_clone(session_root, "aet", 262)
    pr_branch(session_root, head)
    git(session_root.parent / "aet-origin.git", "update-ref", "refs/heads/copy", head)
    dispositions(session_root)
    order = order_of(session_root, FIX, FIX_ORDER)
    with pytest.raises(ImplementError, match="copy"):
        implementer_task(session_root, order)


@pytest.mark.xfail(strict=True)
def test_a_fix_round_without_the_dispositions_is_an_error(session_root: Path) -> None:
    head = pr_clone(session_root, "aet", 262)
    pr_branch(session_root, head)
    order = order_of(session_root, FIX, FIX_ORDER)
    with pytest.raises(ImplementError, match="dispositions"):
        implementer_task(session_root, order)


@pytest.mark.xfail(strict=True)
def test_a_subject_without_a_clone_is_an_error(session_root: Path) -> None:
    order = order_of(session_root, BUILD, BUILD_ORDER)
    with pytest.raises(ImplementError, match="aet"):
        implementer_task(session_root, order)


@pytest.mark.xfail(strict=True)
def test_a_clone_of_another_repository_is_an_error(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    git(session_root / "aet", "remote", "set-url", "origin", "https://x.test/acme/aet")
    order = order_of(session_root, BUILD, BUILD_ORDER)
    with pytest.raises(ImplementError, match="acme/aet"):
        implementer_task(session_root, order)


@pytest.mark.xfail(strict=True)
def test_the_composed_implementer_holds_its_task_and_the_standing_rules(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    pr_clone(session_root, "aet", 262)
    write_waybill_order(session_root, BUILD, BUILD_ORDER)
    result = compose({**ENV_RUN7_FIRED, **fire(BUILD)}, session_root, home, path_dirs)
    text = result.render_text
    assert "# Role: implementer" in text
    assert "## Task" in text
    assert "`claude/aet261-implement-1`" in text
    for rule in (
        "fails on the old code",
        "one commit per finding",
        "DECISION:FALLBACK",
        "Build what the ticket says",
        "Do not review your own work",
        "Your last reply lists",
        "Your first reply names your role and your task",
    ):
        assert rule in text, rule
    assert not [e for e in result.errors if "aet" in e], result.errors


@pytest.mark.xfail(strict=True)
def test_a_composed_fix_round_without_a_branch_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    pr_clone(session_root, "aet", 262)
    dispositions(session_root)
    write_waybill_order(session_root, FIX, FIX_ORDER)
    result = compose({**ENV_RUN7_FIRED, **fire(FIX)}, session_root, home, path_dirs)
    assert any("no branch" in error for error in result.errors), result.errors
    assert "COMPOSER ERROR" in result.render_text
    assert "## Task" not in result.render_text


@pytest.mark.xfail(strict=True)
@pytest.mark.parametrize(
    ("pass_", "number", "kind"),
    [("build", 262, "pull request"), ("fix", 261, "issue")],
)
def test_a_pass_that_disagrees_with_its_subject_is_an_error(
    session_root: Path, pass_: str, number: int, kind: str
) -> None:
    # The pass decides; a first build on a pull request
    # or a fix round on an issue fails (decision 109).
    head = pr_clone(session_root, "aet", 262)
    pr_branch(session_root, head)
    dispositions(session_root)
    name = f"implement-{pass_}-opus-aet{number}-1"
    text = (
        f"id: {name}\nrole: implementer\npass: {pass_}\nmodel_tier: opus\n"
        f"subject: pandoscope/aet#{number}\ntickets: []\n"
    )
    order = order_of(session_root, name, text)
    with pytest.raises(ImplementError) as raised:
        implementer_task(session_root, order)
    message = str(raised.value)
    assert f"'{pass_}'" in message, message
    assert f"pandoscope/aet#{number}" in message, message
    assert kind in message, message


@pytest.mark.xfail(strict=True)
def test_a_composed_build_on_a_pull_request_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    pr_clone(session_root, "aet", 262)
    name = "implement-build-opus-aet262-1"
    write_waybill_order(
        session_root,
        name,
        BUILD_ORDER.replace(BUILD, name).replace("aet#261", "aet#262"),
    )
    result = compose({**ENV_RUN7_FIRED, **fire(name)}, session_root, home, path_dirs)
    assert any(
        "'build'" in error and "pandoscope/aet#262" in error and "pull request" in error
        for error in result.errors
    ), result.errors
    assert "## Task" not in result.render_text
