from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from pandoscope.cli import build_parser
from pandoscope.org.command import run_org_init

from .fakes import FakeRun
from .test_reconcile import FakeExec, fake_meta


def args(meta: Path, *extra: str) -> argparse.Namespace:
    return build_parser().parse_args(
        [
            "org",
            "init",
            "o",
            "--project",
            "app",
            "--description",
            "The app.",
            "--approver",
            "human",
            "--meta",
            str(meta),
            *extra,
        ]
    )


def test_dry_run_prints_the_plan_and_every_reconciler(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meta = fake_meta(tmp_path)
    fake = FakeRun({("gh", "repo", "list"): "meta\n"})
    code = run_org_init(
        args(meta, "--dry-run", "--secrets", str(tmp_path / "s")),
        run=fake,
        exec_=FakeExec(),
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "o/meta: exists" in out
    assert "o/app: would create" in out
    assert "settings: converged" in out
    assert "credentials: skipped" in out


def test_drift_makes_the_command_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meta = fake_meta(tmp_path)
    code = run_org_init(
        args(meta, "--dry-run", "--secrets", str(tmp_path / "s")),
        run=FakeRun(),
        exec_=FakeExec({"sync-gh-repo-rulesets.sh": 1}, "DRIFT  meta  protect-main\n"),
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "rulesets: exit 1" in out
    assert "  DRIFT  meta  protect-main" in out


def test_secrets_default_to_the_orgs_dir_in_meta(tmp_path: Path) -> None:
    meta = fake_meta(tmp_path)
    fake_exec = FakeExec()
    run_org_init(
        args(
            meta,
            "--dry-run",
            "--release-bot-app",
            "o-bot",
            "--release-bot-client-id",
            "Iv1",
        ),
        run=FakeRun(),
        exec_=fake_exec,
    )
    creds_env = fake_exec.calls[2][1]
    assert creds_env["SYNC_CREDENTIALS_SECRETS_DIR"] == str(
        meta / ".secrets" / "orgs" / "o"
    )


def test_meta_without_reconcilers_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"sync-gh-repo-settings\.sh"):
        run_org_init(args(tmp_path), run=FakeRun(), exec_=FakeExec())


def test_app_without_client_id_is_refused(tmp_path: Path) -> None:
    meta = fake_meta(tmp_path)
    with pytest.raises(ValueError, match=r"--release-bot-client-id"):
        run_org_init(
            args(meta, "--release-bot-app", "o-bot"), run=FakeRun(), exec_=FakeExec()
        )


def test_repos_are_stamped_with_the_stamp_run_org_init_is_given(
    tmp_path: Path,
) -> None:
    stamped: list[str] = []

    def fake_stamp(directory: str, data: object = None, **_: object) -> None:
        stamped.append(Path(directory).name)

    run_org_init(
        args(fake_meta(tmp_path), "--workdir", str(tmp_path / "w")),
        run=FakeRun(),
        exec_=FakeExec(),
        stamp_with=fake_stamp,
    )
    assert stamped == [
        "meta",
        "app",
        "session-memory",
        "decision-memory",
        "evidence-memory",
    ]


BOARD = "https://github.com/orgs/o/projects/7"
BOT = ("--release-bot-app", "o-bot", "--release-bot-client-id", "Iv1")


def no_stamp(directory: str, data: object = None, **_: object) -> None:
    """Stamp nothing: these tests are about the board."""


def credentials_conf(fake_exec: FakeExec) -> str:
    env = next(env for _, env in fake_exec.calls if "SYNC_CREDENTIALS_CONF" in env)
    return Path(env["SYNC_CREDENTIALS_CONF"]).read_text()


def test_org_without_a_board_gets_one_and_its_url_in_the_credentials(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_exec = FakeExec()
    run_org_init(
        args(fake_meta(tmp_path), *BOT, "--secrets", str(tmp_path / "s")),
        run=FakeRun({("gh", "project", "create"): f"{BOARD}\n"}),
        exec_=fake_exec,
        stamp_with=no_stamp,
    )
    assert f"board: created {BOARD}" in capsys.readouterr().out
    assert f'"var|PROJECT_BOARD_URL|all|{BOARD}"' in credentials_conf(fake_exec)


def test_a_board_url_the_principal_passes_is_used_as_given(tmp_path: Path) -> None:
    fake, fake_exec = FakeRun(), FakeExec()
    run_org_init(
        args(fake_meta(tmp_path), *BOT, "--board-url", BOARD, "--dry-run"),
        run=fake,
        exec_=fake_exec,
    )
    looked_up = [
        cmd
        for cmd in fake.commands()
        if cmd[:2] == ("gh", "project")
        or cmd[:3] == ("gh", "api", "orgs/o/actions/variables")
    ]
    assert looked_up == []
    assert f'"var|PROJECT_BOARD_URL|all|{BOARD}"' in credentials_conf(fake_exec)


def test_dry_run_reports_the_board_it_would_create(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_org_init(
        args(fake_meta(tmp_path), "--dry-run"), run=FakeRun(), exec_=FakeExec()
    )
    assert "board: would create" in capsys.readouterr().out


PLAN_FILE = """\
org: o
approvers: [human]
repos:
  - {name: meta, title: Meta, kind: docs, purpose: Org-level docs.}
  - {name: app, kind: code, purpose: The app.}
  - {name: helper, kind: code, purpose: The helper.}
"""


def plan_args(meta: Path, plan: Path, *extra: str) -> argparse.Namespace:
    return build_parser().parse_args(
        ["org", "init", "o", "--meta", str(meta), "--plan", str(plan), *extra]
    )


@pytest.mark.xfail(strict=True)
def test_a_plan_file_brings_every_repo_it_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meta = fake_meta(tmp_path)
    plan = tmp_path / "org.yml"
    plan.write_text(PLAN_FILE)
    fake = FakeRun({("gh", "repo", "list"): "meta\n"})
    code = run_org_init(
        plan_args(meta, plan, "--dry-run", "--secrets", str(tmp_path / "s")),
        run=fake,
        exec_=FakeExec(),
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "o/meta: exists" in out
    assert "o/app: would create" in out
    assert "o/helper: would create" in out
    assert "session-memory" not in out


@pytest.mark.xfail(strict=True)
def test_without_a_plan_file_the_plan_flags_are_required(tmp_path: Path) -> None:
    meta = fake_meta(tmp_path)
    argv = ["org", "init", "o", "--meta", str(meta), "--project", "app"]
    with pytest.raises(ValueError, match="--plan"):
        run_org_init(build_parser().parse_args(argv), run=FakeRun(), exec_=FakeExec())
