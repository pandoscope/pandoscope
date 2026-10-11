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
