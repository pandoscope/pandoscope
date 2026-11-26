from __future__ import annotations

from pandoscope.org.init import init_org
from pandoscope.org.plan import Repo
from pandoscope.org.reconcile import Outcome
from pandoscope.org.reposync import StepReport


PLAN = [
    Repo("meta", "Org docs.", {"agentic_subtemplate": "template"}),
    Repo("waybill", "Orders.", direct_pushes=True),
]


class Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []

    def reconcile(self, org: str, plan: list[Repo]) -> list[Outcome]:
        self.events.append(f"reconcile {[r.name for r in plan]}")
        return [Outcome("settings", 0, [])]


class SyncRecorder:
    """Stands in for repo sync: records each call, reports one step per repo."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __call__(self, repo: Repo) -> list[StepReport]:
        self.events.append(f"sync {repo.name}")
        return [StepReport("exists", "created")]


def test_init_runs_repo_sync_for_every_entry_before_the_reconcile() -> None:
    events: list[str] = []
    recorder = Recorder()
    recorder.events = events
    result = init_org(
        "o",
        PLAN,
        sync_repo=SyncRecorder(events),
        reconcile=recorder.reconcile,
    )
    assert events == ["sync meta", "sync waybill", "reconcile ['meta', 'waybill']"]
    assert result.repos == {
        "meta": [StepReport("exists", "created")],
        "waybill": [StepReport("exists", "created")],
    }
    assert result.outcomes == [Outcome("settings", 0, [])]
