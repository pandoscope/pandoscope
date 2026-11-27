"""`org sync`: repo sync per entry, the org-wide reconcile, then the checks (#71)."""

from __future__ import annotations

import pytest

from pandoscope.org.orgsync import OrgResult, sync_org
from pandoscope.org.plan import Repo
from pandoscope.org.reconcile import Outcome
from pandoscope.org.reposync import StepReport

PLAN = [
    Repo("meta", "Org docs.", {"agentic_subtemplate": "template"}),
    Repo("app", "The app.", {"agentic_subtemplate": "template"}),
]


class Recorder:
    """Stands in for repo sync, the reconcile and the check; records their order."""

    def __init__(self, exists: str = "exists") -> None:
        self.events: list[str] = []
        self.exists = exists

    def sync(self, repo: Repo) -> list[StepReport]:
        self.events.append(f"sync {repo.name}")
        return [StepReport("exists", self.exists)]

    def reconcile(self, org: str, plan: list[Repo]) -> list[Outcome]:
        self.events.append(f"reconcile {org} {[repo.name for repo in plan]}")
        return [Outcome("settings", 0, [])]

    def check(self, repo: Repo) -> StepReport:
        self.events.append(f"check {repo.name}")
        return StepReport("check", "OK", [f"OK {repo.name}"])


@pytest.mark.xfail(strict=True)
def test_sync_runs_repo_sync_per_entry_then_the_reconcile_then_the_checks() -> None:
    recorder = Recorder()
    result = sync_org(
        "o", PLAN, sync_repo=recorder.sync, reconcile=recorder.reconcile, check=recorder.check
    )
    assert recorder.events == [
        "sync meta",
        "sync app",
        "reconcile o ['meta', 'app']",
        "check meta",
        "check app",
    ]
    assert result == OrgResult(
        {"meta": [StepReport("exists", "exists")], "app": [StepReport("exists", "exists")]},
        [Outcome("settings", 0, [])],
        {
            "meta": StepReport("check", "OK", ["OK meta"]),
            "app": StepReport("check", "OK", ["OK app"]),
        },
    )


@pytest.mark.xfail(strict=True)
def test_a_dry_run_checks_no_repo_it_found_absent() -> None:
    recorder = Recorder(exists="would create")
    result = sync_org(
        "o", PLAN, sync_repo=recorder.sync, reconcile=recorder.reconcile, check=recorder.check
    )
    assert not any(event.startswith("check") for event in recorder.events)
    assert result.checks["app"] == StepReport("check", "skipped", ["the repo does not exist yet"])


@pytest.mark.xfail(strict=True)
def test_without_a_check_there_are_no_checks() -> None:
    recorder = Recorder()
    result = sync_org("o", PLAN, sync_repo=recorder.sync, reconcile=recorder.reconcile)
    assert result.checks == {}
    assert recorder.events[-1] == "reconcile o ['meta', 'app']"
