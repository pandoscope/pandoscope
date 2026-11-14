"""org init reports a release bot that lacks a permission, with the pages an org owner clicks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pandoscope.org.botcheck import permission_gaps
from pandoscope.org.command import run_org_init
from pandoscope.org.releasebot import PERMISSIONS

from .fakes import FakeRun
from .test_command import PLAN_FILE, plan_args
from .test_reconcile import FakeExec, fake_meta

LOOKUP = ("gh", "api", "--paginate", "orgs/o/installations")
PAGES = "https://github.com/organizations/o/settings"


def gaps(answer: str) -> list[str]:
    return permission_gaps("o", "o-release-bot", FakeRun({LOOKUP: answer}))


def test_a_bot_holding_every_permission_has_no_gap() -> None:
    assert gaps(json.dumps(PERMISSIONS) + "\n") == []


def test_write_covers_read() -> None:
    assert gaps(json.dumps({**PERMISSIONS, "issues": "write", "checks": "read"}) + "\n") == []


@pytest.mark.parametrize("held", [None, "read"], ids=["missing", "read-only"])
def test_a_permission_below_its_level_names_both_pages(held: str | None) -> None:
    permissions = {k: v for k, v in PERMISSIONS.items() if k != "organization_projects"}
    if held:
        permissions["organization_projects"] = held
    (line,) = gaps(json.dumps(permissions) + "\n")
    assert line.startswith("MANUAL")
    assert "organization_projects: write" in line
    assert f"{PAGES}/apps/o-release-bot/permissions" in line
    assert f"{PAGES}/installations" in line


def test_a_bot_that_is_not_installed_names_the_install_page() -> None:
    (line,) = gaps("")
    assert line.startswith("MANUAL")
    assert "not installed" in line
    assert "https://github.com/apps/o-release-bot/installations/new" in line


def recorded_bot(tmp_path: Path) -> Path:
    secrets = tmp_path / "s"
    secrets.mkdir()
    (secrets / "release-bot.json").write_text(
        '{"org": "o", "slug": "o-release-bot", "app_id": 4711, "client_id": "Iv23rec"}\n'
    )
    return secrets


def test_org_init_reports_a_permission_gap_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    secrets = recorded_bot(tmp_path)
    plan = tmp_path / "org.yml"
    plan.write_text(PLAN_FILE)
    lacking = {k: v for k, v in PERMISSIONS.items() if k != "organization_projects"}
    code = run_org_init(
        plan_args(fake_meta(tmp_path), plan, "--dry-run", "--secrets", str(secrets)),
        run=FakeRun({LOOKUP: json.dumps(lacking) + "\n"}),
        exec_=FakeExec(),
    )
    out = capsys.readouterr().out
    assert "release bot:" in out
    assert "organization_projects: write" in out
    assert code == 1


def test_org_init_says_the_bot_is_in_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    secrets = recorded_bot(tmp_path)
    plan = tmp_path / "org.yml"
    plan.write_text(PLAN_FILE)
    code = run_org_init(
        plan_args(fake_meta(tmp_path), plan, "--dry-run", "--secrets", str(secrets)),
        run=FakeRun({LOOKUP: json.dumps(PERMISSIONS) + "\n"}),
        exec_=FakeExec(),
    )
    assert "release bot: converged" in capsys.readouterr().out
    assert code == 0
