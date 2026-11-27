"""`pandoscope org sync ORG`: repo sync for every entry of the org file, then the org (#71)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.cli import build_parser, main
from pandoscope.org.command import run_org_sync

from .fakes import FakeRun
from .test_command import BOT, answered, credentials_conf
from .test_reconcile import FakeExec, fake_meta

ORG_FILE = """\
org: o
agent: helper-bot
approvers: [human]
repos:
  - {name: meta, title: Meta, kind: docs, purpose: Org-level docs.}
  - {name: app, kind: code, purpose: The app.}
"""
BOARD = "https://github.com/orgs/o/projects/7"
RECORDED = ("gh", "api", "orgs/o/actions/variables")


def org_meta(tmp_path: Path, text: str = ORG_FILE) -> Path:
    """A fake meta holding the org file and the secrets dir org init made."""
    meta = fake_meta(tmp_path)
    (meta / "org.yml").write_text(text)
    (meta / ".secrets" / "orgs" / "o").mkdir(parents=True)
    return meta


def sync_args(meta: Path, *extra: str) -> list[str]:
    return ["org", "sync", "o", "--meta", str(meta), *extra]


def stamp_answers(directory: str, data: object = None, **_: object) -> None:
    answered(directory)


def stamped_org() -> FakeRun:
    """A forge where o/meta and o/app exist, stamped and private, and the agent can push."""
    answers: dict[tuple[str, ...], str] = {RECORDED: f"{BOARD}\n"}
    errors: dict[tuple[str, ...], str] = {}
    for name in ("meta", "app"):
        answers[("gh", "api", f"repos/o/{name}", "--jq", ".name")] = f"{name}\n"
        answers[("gh", "api", f"repos/o/{name}/branches")] = "main\n"
        answers[
            ("gh", "api", f"repos/o/{name}", "--jq", '"\\(.visibility) \\(.default_branch)"')
        ] = "private main\n"
        answers[("gh", "api", f"repos/o/{name}/collaborators/helper-bot/permission")] = "write\n"
        errors[("gh", "api", f"repos/o/{name}/rulesets")] = "Upgrade to GitHub Pro (HTTP 403)"
    return FakeRun(answers, errors)


def test_a_dry_run_reports_every_repo_every_reconciler_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake, fake_exec = FakeRun(), FakeExec()
    code = run_org_sync(
        build_parser().parse_args(sync_args(org_meta(tmp_path), "--dry-run")),
        run=fake,
        exec_=fake_exec,
        stamp_with=stamp_answers,
    )
    out = capsys.readouterr().out
    assert "o/meta: exists would create; first commit would stamp" in out
    assert "o/app: exists would create; first commit would stamp" in out
    assert "settings: converged" in out
    assert "o/app: check skipped (the repo does not exist yet)" in out
    assert code == 0
    assert all(cmd[-1] == "--dry-run" for cmd, _ in fake_exec.calls)
    assert not any(cmd[:3] in {("gh", "repo", "create"), ("gh", "project", "create")} for cmd in fake.commands())


def test_the_reconcile_runs_once_for_the_whole_org(tmp_path: Path) -> None:
    fake_exec = FakeExec()
    run_org_sync(
        build_parser().parse_args(sync_args(org_meta(tmp_path), *BOT)),
        run=stamped_org(),
        exec_=fake_exec,
        stamp_with=stamp_answers,
    )
    assert fake_exec.scripts() == [
        "sync-gh-repo-settings.sh",
        "sync-gh-repo-rulesets.sh",
        "sync-gh-actions-credentials.sh",
        "sync-gh-repo-collaborators.sh",
    ]
    assert not any("SYNC_REPOS" in env for _, env in fake_exec.calls)
    assert '"var|BOT_MERGE_ENABLED|only:meta,app|true"' in credentials_conf(fake_exec)


def test_every_repo_is_checked_after_the_reconcile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_org_sync(
        build_parser().parse_args(sync_args(org_meta(tmp_path))),
        run=stamped_org(),
        exec_=FakeExec(),
        stamp_with=stamp_answers,
    )
    out = capsys.readouterr().out
    assert out.index("collaborators: converged") < out.index("o/meta: check MANUAL")
    assert "  OK helper-bot has write on o/app" in out
    assert code == 0


def test_a_missing_check_point_fails_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = stamped_org()
    fake.answers[("gh", "api", "repos/o/app/collaborators/helper-bot/permission")] = "read\n"
    code = run_org_sync(
        build_parser().parse_args(sync_args(org_meta(tmp_path))),
        run=fake,
        exec_=FakeExec(),
        stamp_with=stamp_answers,
    )
    assert "MISSING helper-bot" in capsys.readouterr().out
    assert code == 1


def test_sync_keeps_the_recorded_board_and_creates_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake, fake_exec = FakeRun(), FakeExec()
    run_org_sync(
        build_parser().parse_args(sync_args(org_meta(tmp_path), *BOT, "--dry-run")),
        run=fake,
        exec_=fake_exec,
        stamp_with=stamp_answers,
    )
    assert "board: none (org init creates one)" in capsys.readouterr().out
    assert "PROJECT_BOARD_URL" not in credentials_conf(fake_exec)
    assert ("gh", "project", "create") not in [cmd[:3] for cmd in fake.commands()]

    fake_exec = FakeExec()
    run_org_sync(
        build_parser().parse_args(sync_args(org_meta(tmp_path / "x"), *BOT, "--dry-run")),
        run=FakeRun({RECORDED: f"{BOARD}\n"}),
        exec_=fake_exec,
        stamp_with=stamp_answers,
    )
    assert f"board: recorded {BOARD}" in capsys.readouterr().out
    assert f'"var|PROJECT_BOARD_URL|all|{BOARD}"' in credentials_conf(fake_exec)


def test_the_org_file_must_name_the_agent(tmp_path: Path) -> None:
    meta = org_meta(tmp_path, ORG_FILE.replace("agent: helper-bot\n", ""))
    fake = FakeRun()
    with pytest.raises(ValueError, match="agent"):
        run_org_sync(build_parser().parse_args(sync_args(meta)), run=fake, exec_=FakeExec())
    assert fake.commands() == []


def test_a_secrets_dir_org_init_has_not_made_is_refused_before_any_forge_call(
    tmp_path: Path,
) -> None:
    """Sync never seeds: that is org init's, on a dir it finds missing."""
    meta = fake_meta(tmp_path)
    (meta / "org.yml").write_text(ORG_FILE)
    fake, fake_exec = FakeRun(), FakeExec()
    with pytest.raises(ValueError, match="org init"):
        run_org_sync(build_parser().parse_args(sync_args(meta)), run=fake, exec_=fake_exec)
    assert fake.commands() == []
    assert fake_exec.calls == []
    assert not (meta / ".secrets").exists()


def test_plan_names_an_org_file_outside_meta(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    meta = org_meta(tmp_path)
    plan = tmp_path / "elsewhere.yml"
    plan.write_text(ORG_FILE.replace("{name: app, kind: code, purpose: The app.}", "{name: lib, kind: code, purpose: The lib.}"))
    run_org_sync(
        build_parser().parse_args(sync_args(meta, "--plan", str(plan), "--dry-run")),
        run=FakeRun(),
        exec_=FakeExec(),
        stamp_with=stamp_answers,
    )
    assert "o/lib: exists would create" in capsys.readouterr().out


def test_the_cli_routes_org_sync(tmp_path: Path) -> None:
    """org sync takes no --project: the org file is its only plan."""
    meta = fake_meta(tmp_path)
    with pytest.raises(FileNotFoundError, match="org.yml"):
        main(sync_args(meta))
