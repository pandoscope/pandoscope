"""`repo sync`'s first two steps: the repository exists, and main has a first commit (#71)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.org.plan import Repo
from pandoscope.org.reconcile import Outcome
from pandoscope.org.reposync import StepReport, reconcile_report, repo_sync
from pandoscope.org.seed import ANSWERS_FILE
from pandoscope.stamp import TEMPLATE_URL

from .fakes import FakeRun

APP = Repo(
    "app",
    "The app.",
    {"agentic_subtemplate": "template", "agentic_project_name": "App"},
)
PLAIN = Repo("notes", "Plain notes.", {})
NOT_FOUND = "command failed (exit 1): gh api repos/o/app\nstderr: gh: Not Found (HTTP 404)"
VIEW = ("gh", "api", "repos/o/app")
BRANCHES = ("gh", "api", "repos/o/app/branches")
HELPER = ("-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential")


class FakeStamp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str], str | None]] = []

    def __call__(
        self,
        directory: str,
        data: dict[str, str] | None = None,
        *,
        defaults: bool = False,
        vcs_ref: str | None = None,
    ) -> None:
        self.calls.append((directory, dict(data or {}), vcs_ref))
        Path(directory).mkdir(parents=True, exist_ok=True)  # as copier does
        (Path(directory) / ANSWERS_FILE).write_text("_commit: v5.0.2-3-gabc1234\n")


def sync(fake: FakeRun, stamp: FakeStamp, tmp_path: Path, repo: Repo = APP, *, dry_run: bool = False) -> dict[str, StepReport]:
    reports = repo_sync(
        "o", repo, tmp_path, run=fake, stamp=stamp, template_ref="v5.0.2", dry_run=dry_run
    )
    return {report.step: report for report in reports}


def test_an_absent_repo_is_created_and_stamped_as_main_s_first_commit(tmp_path: Path) -> None:
    fake, stamp = FakeRun(errors={VIEW: NOT_FOUND}), FakeStamp()
    reports = sync(fake, stamp, tmp_path)

    assert reports["exists"].state == "created"
    assert reports["first commit"].state == "stamped"
    commands = fake.commands()
    assert ("gh", "repo", "create", "o/app", "--private", "--description", "The app.") in commands
    checkout = tmp_path / "app"
    assert ("git", "init", "-b", "main", str(checkout)) in commands
    assert stamp.calls == [(str(checkout), APP.answers, "v5.0.2")]
    push = next(cmd for cmd in commands if "push" in cmd)
    assert push == ("git", *HELPER, "push", "https://github.com/o/app.git", "main")


def test_the_stamp_commit_names_the_template_commit_and_every_input(tmp_path: Path) -> None:
    fake, stamp = FakeRun(errors={VIEW: NOT_FOUND}), FakeStamp()
    sync(fake, stamp, tmp_path)

    commit = next(cmd for cmd in fake.commands() if cmd[:2] == ("git", "commit"))
    message = commit[commit.index("-m") + 1]
    assert f"{TEMPLATE_URL} at v5.0.2 (v5.0.2-3-gabc1234)" in message
    assert "agentic_subtemplate: template" in message
    assert "agentic_project_name: App" in message


def test_a_second_run_changes_nothing(tmp_path: Path) -> None:
    fake = FakeRun({VIEW: "app\n", BRANCHES: "main\n"})
    stamp = FakeStamp()
    reports = sync(fake, stamp, tmp_path)

    assert reports["exists"].state == "exists"
    assert reports["first commit"].state == "present"
    assert stamp.calls == []
    assert all(cmd[:3] in {VIEW, BRANCHES} for cmd in fake.commands())


def test_an_existing_empty_repo_gets_its_stamp(tmp_path: Path) -> None:
    fake, stamp = FakeRun({VIEW: "app\n", BRANCHES: ""}), FakeStamp()
    reports = sync(fake, stamp, tmp_path)

    assert reports["exists"].state == "exists"
    assert reports["first commit"].state == "stamped"
    assert not any(cmd[:3] == ("gh", "repo", "create") for cmd in fake.commands())


def test_a_repo_with_commits_but_no_main_is_reported_never_stamped(tmp_path: Path) -> None:
    fake, stamp = FakeRun({VIEW: "app\n", BRANCHES: "master\n"}), FakeStamp()
    reports = sync(fake, stamp, tmp_path)

    assert reports["first commit"].state == "MANUAL"
    assert "master" in " ".join(reports["first commit"].lines)
    assert stamp.calls == []


def test_dry_run_reports_every_change_and_makes_none(tmp_path: Path) -> None:
    fake, stamp = FakeRun(errors={VIEW: NOT_FOUND}), FakeStamp()
    reports = sync(fake, stamp, tmp_path, dry_run=True)

    assert reports["exists"].state == "would create"
    assert reports["first commit"].state == "would stamp"
    assert [cmd[:3] for cmd in fake.commands()] == [VIEW]
    assert stamp.calls == []


def test_a_plain_entry_is_created_with_a_readme_and_never_stamped(tmp_path: Path) -> None:
    view = ("gh", "api", "repos/o/notes")
    fake, stamp = FakeRun(errors={view: NOT_FOUND.replace("app", "notes")}), FakeStamp()
    reports = sync(fake, stamp, tmp_path, PLAIN)

    assert reports["exists"].state == "created"
    assert reports["first commit"].state == "not stamped"
    create = next(cmd for cmd in fake.commands() if cmd[:3] == ("gh", "repo", "create"))
    assert "--add-readme" in create
    assert stamp.calls == []


def test_a_forge_error_other_than_not_found_stops_the_run(tmp_path: Path) -> None:
    fake = FakeRun(errors={VIEW: "command failed (exit 1)\nstderr: HTTP 403"})
    with pytest.raises(RuntimeError, match="403"):
        sync(fake, FakeStamp(), tmp_path)


def test_a_lookup_that_names_no_repo_is_refused(tmp_path: Path) -> None:
    """Only the repo's own name proves it exists; anything else is a failure, not a guess."""
    fake = FakeRun({VIEW: ""})
    with pytest.raises(ValueError, match="o/app"):
        sync(fake, FakeStamp(), tmp_path)


SKIPPED = StepReport("reconcile", "skipped", ["no meta checkout"])


@pytest.mark.xfail(strict=True)
def test_a_fixed_reconcile_report_is_reported_as_it_is(tmp_path: Path) -> None:
    fake = FakeRun(errors={VIEW: NOT_FOUND})
    reports = repo_sync(
        "o", APP, tmp_path, run=fake, stamp=FakeStamp(), template_ref="v5.0.2",
        reconcile=SKIPPED, dry_run=True,
    )
    assert reports[-1] == SKIPPED


def test_the_reconcile_runs_after_the_first_commit(tmp_path: Path) -> None:
    """The rulesets protect main, and the stamp is a direct push to it."""
    events: list[str] = []
    fake, stamp = FakeRun(errors={VIEW: NOT_FOUND}), FakeStamp()

    def reconcile(repo: Repo) -> StepReport:
        events.append(f"reconcile after {len(stamp.calls)} stamp")
        return StepReport("reconcile", "converged")

    repo_sync("o", APP, tmp_path, run=fake, stamp=stamp, template_ref="v5.0.2", reconcile=reconcile)
    assert events == ["reconcile after 1 stamp"]


@pytest.mark.xfail(strict=True)
def test_a_dry_run_does_not_reconcile_a_repo_that_does_not_exist_yet(tmp_path: Path) -> None:
    """Its reconcilers would find nothing and read that as converged."""
    ran: list[str] = []

    def reconcile(repo: Repo) -> StepReport:
        ran.append(repo.name)
        return StepReport("reconcile", "converged")

    reports = repo_sync(
        "o", APP, tmp_path, run=FakeRun(errors={VIEW: NOT_FOUND}), stamp=FakeStamp(),
        template_ref="v5.0.2", reconcile=reconcile, dry_run=True,
    )
    assert ran == []
    assert reports[-1] == StepReport("reconcile", "would reconcile", ["the repo does not exist yet"])


@pytest.mark.xfail(strict=True)
@pytest.mark.parametrize(
    ("outcomes", "state", "lines"),
    [
        (
            [Outcome("settings", 0, []), Outcome("rulesets", 0, ["FIXED  app  protect-main"])],
            "converged",
            ["rulesets: FIXED  app  protect-main"],
        ),
        (
            [Outcome("settings", 1, ["MANUAL  install the app"]), Outcome("rulesets", 0, [])],
            "MANUAL",
            ["settings: MANUAL  install the app"],
        ),
        (
            [
                Outcome("settings", 1, ["MANUAL  install the app"]),
                Outcome("rulesets", 1, ["DRIFT  app  protect-main (would fix)"]),
            ],
            "DRIFT",
            ["settings: MANUAL  install the app", "rulesets: DRIFT  app  protect-main (would fix)"],
        ),
        ([Outcome("settings", 1, [])], "DRIFT", ["settings: exit 1 with no DRIFT or MANUAL line"]),
        (
            [Outcome("credentials", None, ["skipped: create the app"]), Outcome("settings", 0, [])],
            "converged",
            ["credentials: skipped: create the app"],
        ),
    ],
)
def test_the_reconcile_step_follows_the_reconcilers_exits(
    outcomes: list[Outcome], state: str, lines: list[str]
) -> None:
    assert reconcile_report(outcomes) == StepReport("reconcile", state, lines)
