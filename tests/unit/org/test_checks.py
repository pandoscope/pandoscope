"""`repo sync`'s check step (#71): one line per point, MISSING fails, MANUAL does not."""

from __future__ import annotations

import pytest

from pandoscope.org.checks import check_repo
from pandoscope.org.plan import Repo

from .fakes import FakeRun

APP = Repo("app", "The app.", {"agentic_subtemplate": "template"}, private=False)
STORE = Repo("ledger", "Store.", {"agentic_subtemplate": "session-memory"}, direct_pushes=True, private=False)
META = ("gh", "api", "repos/o/app", "--jq", '"\\(.visibility) \\(.default_branch)"')
RULESETS = ("gh", "api", "repos/o/app/rulesets", "--jq", ".[].name")
AGENT = ("gh", "api", "repos/o/app/collaborators/bot/permission", "--jq", ".permission")
ALL_THREE = "verified-signatures\nprotect-main\nrequire-ci-ok\nprotect-release-tags\n"
FREE_PLAN = "gh: Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)"


def converged(**over: str) -> dict[tuple[str, ...], str]:
    answers = {META: "public main\n", RULESETS: ALL_THREE, AGENT: "write\n"}
    answers.update({key: value for key, value in zip((META, RULESETS, AGENT), over.values(), strict=False)})
    return answers


def test_a_converged_repo_reports_ok_on_every_point() -> None:
    report = check_repo("o", APP, "bot", FakeRun(converged()))

    assert report.step == "check"
    assert report.state == "OK"
    assert all(line.startswith("OK") for line in report.lines)
    assert len(report.lines) == 6


def test_every_gap_is_a_missing_line_that_names_it() -> None:
    fake = FakeRun(
        {META: "private master\n", RULESETS: "verified-signatures\n", AGENT: "read\n"}
    )
    report = check_repo("o", APP, "bot", fake)

    assert report.state == "MISSING"
    missing = [line for line in report.lines if line.startswith("MISSING")]
    text = "\n".join(missing)
    assert "public" in text
    assert "master" in text
    assert "protect-main" in text
    assert "require-ci-ok" in text
    assert "bot" in text and "read" in text


def test_a_repo_that_takes_direct_pushes_needs_only_signed_commits() -> None:
    meta = ("gh", "api", "repos/o/ledger", "--jq", '"\\(.visibility) \\(.default_branch)"')
    rulesets = ("gh", "api", "repos/o/ledger/rulesets", "--jq", ".[].name")
    agent = ("gh", "api", "repos/o/ledger/collaborators/bot/permission", "--jq", ".permission")
    fake = FakeRun({meta: "public main\n", rulesets: "verified-signatures\n", agent: "admin\n"})

    assert check_repo("o", STORE, "bot", fake).state == "OK"


def test_rulesets_the_plan_cannot_hold_are_manual_not_missing() -> None:
    private = Repo("app", "The app.", {"agentic_subtemplate": "template"})
    fake = FakeRun({META: "private main\n", AGENT: "write\n"}, errors={RULESETS: FREE_PLAN})
    report = check_repo("o", private, "bot", fake)

    assert report.state == "MANUAL"
    manual = [line for line in report.lines if line.startswith("MANUAL")]
    assert len(manual) == 1
    assert "plan" in manual[0]


def test_any_other_forge_error_stops_the_check() -> None:
    fake = FakeRun({META: "public main\n"}, errors={RULESETS: "gh: Bad credentials (HTTP 401)"})
    with pytest.raises(RuntimeError, match="401"):
        check_repo("o", APP, "bot", fake)


def test_without_an_agent_the_agent_line_is_missing() -> None:
    report = check_repo("o", APP, None, FakeRun(converged()))

    assert report.state == "MISSING"
    assert any(line.startswith("MISSING") and "agent" in line for line in report.lines)
