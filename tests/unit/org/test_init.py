from __future__ import annotations

from pathlib import Path

from pandoscope.org.init import init_org
from pandoscope.org.plan import Repo
from pandoscope.org.reconcile import Outcome

from .fakes import FakeRun

PLAN = [
    Repo("meta", "Org docs.", {"agentic_subtemplate": "template"}),
    Repo("waybill", "Orders.", direct_pushes=True),
]


class Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []

    def stamp_repo(
        self, org: str, repo: Repo, workdir: Path, run: object, stamp: object
    ) -> bool:
        self.events.append(f"stamp {repo.name}")
        return repo.stamped

    def reconcile(self, org: str, plan: list[Repo]) -> list[Outcome]:
        self.events.append(f"reconcile {[r.name for r in plan]}")
        return [Outcome("settings", 0, [])]


def test_init_creates_missing_repos_then_stamps_then_reconciles(
    tmp_path: Path,
) -> None:
    fake = FakeRun({("gh", "repo", "list"): "waybill\n"})
    recorder = Recorder()
    result = init_org(
        "o",
        PLAN,
        tmp_path,
        run=fake,
        stamp=lambda *a, **k: None,
        stamp_repo=recorder.stamp_repo,
        reconcile=recorder.reconcile,
    )
    created = [cmd for cmd in fake.commands() if cmd[:3] == ("gh", "repo", "create")]
    assert [cmd[3] for cmd in created] == ["o/meta"]
    assert recorder.events == [
        "stamp meta",
        "stamp waybill",
        "reconcile ['meta', 'waybill']",
    ]
    assert result.repos == {
        "meta": ["created", "stamped"],
        "waybill": ["exists"],
    }
    assert result.outcomes == [Outcome("settings", 0, [])]


def test_rerun_on_a_finished_org_creates_and_stamps_nothing(tmp_path: Path) -> None:
    fake = FakeRun({("gh", "repo", "list"): "meta\nwaybill\n"})
    result = init_org(
        "o",
        PLAN,
        tmp_path,
        run=fake,
        stamp=lambda *a, **k: None,
        stamp_repo=lambda *a: False,
        reconcile=lambda org, plan: [],
    )
    assert result.repos == {"meta": ["exists"], "waybill": ["exists"]}


def test_dry_run_creates_and_stamps_nothing_but_still_reconciles(
    tmp_path: Path,
) -> None:
    fake = FakeRun({("gh", "repo", "list"): "waybill\n"})
    recorder = Recorder()
    result = init_org(
        "o",
        PLAN,
        tmp_path,
        run=fake,
        stamp=lambda *a, **k: None,
        stamp_repo=recorder.stamp_repo,
        reconcile=recorder.reconcile,
        dry_run=True,
    )
    assert [cmd for cmd in fake.commands() if cmd[:3] == ("gh", "repo", "create")] == []
    assert recorder.events == ["reconcile ['meta', 'waybill']"]
    assert result.repos == {"meta": ["would create"], "waybill": ["exists"]}
