from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.reinset import implement
from pandoscope.reinset.compose import compose
from pandoscope.reinset.implement import PASS_DIR, ImplementError, implementer_task
from pandoscope.reinset.profiles import load_profile
from pandoscope.reinset.receive import Order, find_order

from .conftest import ENV_RUN7_FIRED, fire, git, pr_clone, write_waybill_order

# pr_clone makes pull request 262; 261 is no pull request, so an issue.
BUILD = "implement_build_opus_aet261_1"
BUILD_ORDER = (
    f"id: {BUILD}\nrole: implementer\npass: build\nmodel_tier: opus\n"
    "subject: pandoscope/aet#261\ntickets: [pandoscope/skills#195]\n"
)
FIX = "implement_fix_opus_aet262_3"
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


def test_a_first_build_states_its_tickets_and_its_branch(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    task = implementer_task(session_root, order_of(session_root, BUILD, BUILD_ORDER))
    assert "pandoscope/aet#261" in task
    assert "pandoscope/skills#195" in task
    assert "`claude/aet261-implement-1`" in task
    assert "`origin/main`" in task
    assert "pull request" in task
    assert "dispositions" not in task


@pytest.mark.parametrize(
    ("name", "text", "number"),
    [(BUILD, BUILD_ORDER, 261), (FIX, FIX_ORDER, 262)],
)
def test_the_task_is_the_pass_file_that_the_pass_names(
    session_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    text: str,
    number: int,
) -> None:
    # Decision 137: for every role, the pass names its pass file.
    head = pr_clone(session_root, "aet", 262)
    pr_branch(session_root, head)
    dispositions(session_root)
    passes = tmp_path / "passes"
    passes.mkdir()
    for pass_ in ("build", "fix"):
        (passes / f"{pass_}.md.j2").write_text(f"{pass_}: {{{{ subject }}}}\n")
    monkeypatch.setattr(implement, "PASS_DIR", passes)
    order = order_of(session_root, name, text)
    task = implementer_task(session_root, order)
    assert task == f"{order.pass_}: pandoscope/aet#{number}\n"


def test_a_pass_without_its_pass_file_is_an_error(
    session_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pr_clone(session_root, "aet", 262)
    monkeypatch.setattr(implement, "PASS_DIR", tmp_path)
    order = order_of(session_root, BUILD, BUILD_ORDER)
    with pytest.raises(ImplementError, match="no implementer pass file at"):
        implementer_task(session_root, order)


@pytest.mark.parametrize(
    ("pass_", "other"),
    [
        ("build", ["fix round", "finding", "disposition", "status"]),
        ("fix", ["first build", "Create the branch", "Open one pull request", "base"]),
    ],
)
def test_a_pass_file_reads_nothing_of_the_other_pass(
    pass_: str, other: list[str]
) -> None:
    # Decision 137: "a role should only read its own pass's instructions".
    text = (PASS_DIR / f"{pass_}.md.j2").read_text()
    for word in other:
        assert word not in text, word


def test_a_composed_pass_without_its_pass_file_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    pr_clone(session_root, "aet", 262)
    name = "implement_refactor_opus_aet261_1"
    write_waybill_order(
        session_root,
        name,
        BUILD_ORDER.replace(BUILD, name).replace("pass: build", "pass: refactor"),
    )
    result = compose({**ENV_RUN7_FIRED, **fire(name)}, session_root, home, path_dirs)
    assert len(result.errors) == 1, result.errors
    assert "no implementer pass file at" in result.errors[0]
    assert str(PASS_DIR / "refactor.md.j2") in result.errors[0]
    assert "## Task" not in result.render_text


def test_a_pass_file_whose_subject_the_composer_does_not_know_is_an_error(
    session_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The composer alone states which subject each pass works on.
    pr_clone(session_root, "aet", 262)
    (tmp_path / "refactor.md.j2").write_text("{{ subject }}\n")
    monkeypatch.setattr(implement, "PASS_DIR", tmp_path)
    name = "implement_refactor_opus_aet261_1"
    text = BUILD_ORDER.replace(BUILD, name).replace("pass: build", "pass: refactor")
    order = order_of(session_root, name, text)
    with pytest.raises(ImplementError, match="'refactor'"):
        implementer_task(session_root, order)


def test_a_first_build_takes_the_orders_base(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    order = order_of(session_root, BUILD, BUILD_ORDER + "base: feature\n")
    assert "`origin/feature`" in implementer_task(session_root, order)


def test_a_repeat_run_gets_a_branch_of_its_own(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    name = "implement_build_opus_aet261_1b"
    order = order_of(session_root, name, BUILD_ORDER.replace(BUILD, name))
    assert "`claude/aet261-implement-1b`" in implementer_task(session_root, order)


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


def test_a_fix_round_without_a_branch_at_the_head_is_an_error(
    session_root: Path,
) -> None:
    pr_clone(session_root, "aet", 262)
    dispositions(session_root)
    order = order_of(session_root, FIX, FIX_ORDER)
    with pytest.raises(ImplementError, match="no branch"):
        implementer_task(session_root, order)


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


def test_a_fix_round_without_the_dispositions_is_an_error(session_root: Path) -> None:
    head = pr_clone(session_root, "aet", 262)
    pr_branch(session_root, head)
    order = order_of(session_root, FIX, FIX_ORDER)
    with pytest.raises(ImplementError, match="dispositions"):
        implementer_task(session_root, order)


def test_a_subject_without_a_clone_is_an_error(session_root: Path) -> None:
    order = order_of(session_root, BUILD, BUILD_ORDER)
    with pytest.raises(ImplementError, match="aet"):
        implementer_task(session_root, order)


def test_a_clone_of_another_repository_is_an_error(session_root: Path) -> None:
    pr_clone(session_root, "aet", 262)
    git(session_root / "aet", "remote", "set-url", "origin", "https://x.test/acme/aet")
    order = order_of(session_root, BUILD, BUILD_ORDER)
    with pytest.raises(ImplementError, match="acme/aet"):
        implementer_task(session_root, order)


# The rules that the composed instructions state after pandoscope#58,
# split by the pass they hold for (pandoscope#60, decision 137).
EVERY_PASS_RULES = (
    "Your first reply names your role and your task",
    "Build what the ticket says",
    "Every acceptance criterion gets a test",
    "fails on the old code",
    "or carries a `DECISION:FALLBACK` marker",
    'List it in the PR body as "needs a run"',
    "The PR body names every ticket",
    # pandoscope#60: the build task named the tickets in the body a second time.
    "every ticket",
    "Commit as you go",
    "Never force-push a pushed branch",
    "Do not review your own work",
    "Never skip a check",
    "goes to the principal in your last reply",
    "Your last reply lists",
)
BUILD_RULES = ("Stub, red, green", "Before you open the PR, fold the branch")
FIX_RULES = (
    "commit per finding",
    "No failing test possible: decline the finding",
    "one line per finding",
)


def composed(session_root: Path, home: Path, path_dirs: list[Path], pass_: str) -> str:
    head = pr_clone(session_root, "aet", 262)
    pr_branch(session_root, head)
    dispositions(session_root)
    name, text = {"build": (BUILD, BUILD_ORDER), "fix": (FIX, FIX_ORDER)}[pass_]
    write_waybill_order(session_root, name, text)
    result = compose({**ENV_RUN7_FIRED, **fire(name)}, session_root, home, path_dirs)
    assert not [e for e in result.errors if "aet" in e], result.errors
    return result.render_text


@pytest.mark.parametrize(
    ("pass_", "own", "other"),
    [("build", BUILD_RULES, FIX_RULES), ("fix", FIX_RULES, BUILD_RULES)],
)
def test_the_composed_instructions_state_each_rule_of_their_pass_once(
    session_root: Path,
    home: Path,
    path_dirs: list[Path],
    pass_: str,
    own: tuple[str, ...],
    other: tuple[str, ...],
) -> None:
    text = composed(session_root, home, path_dirs, pass_)
    assert "# Role: implementer" in text
    assert "## Task" in text
    for rule in EVERY_PASS_RULES + own:
        assert text.count(rule) == 1, rule
    for rule in other:
        assert rule not in text, rule


def sentences(text: str) -> set[str]:
    """The lines of a text that carry words, without list markers."""
    lines = (line.strip().removeprefix("- ").strip() for line in text.splitlines())
    return {line for line in lines if line and not line.startswith("#")}


@pytest.mark.parametrize("pass_", ["build", "fix"])
def test_no_sentence_stands_in_both_the_profile_and_a_pass_file(
    session_root: Path, pass_: str
) -> None:
    prose = load_profile("implementer", session_root).data["prose"]
    shared = sentences(prose) & sentences((PASS_DIR / f"{pass_}.md.j2").read_text())
    assert shared == set(), shared


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
    name = f"implement_{pass_}_opus_aet{number}_1"
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


def test_a_composed_build_on_a_pull_request_is_a_composer_error(
    session_root: Path, home: Path, path_dirs: list[Path]
) -> None:
    pr_clone(session_root, "aet", 262)
    name = "implement_build_opus_aet262_1"
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
