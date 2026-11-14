from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from pandoscope.cli import build_parser, main
from pandoscope.org.command import run_org_init
from pandoscope.org.plan import default_plan
from pandoscope.org.planfile import read_plan

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


def test_without_a_plan_file_the_plan_flags_are_required(tmp_path: Path) -> None:
    meta = fake_meta(tmp_path)
    argv = ["org", "init", "o", "--meta", str(meta), "--project", "app"]
    with pytest.raises(ValueError, match="--plan"):
        run_org_init(build_parser().parse_args(argv), run=FakeRun(), exec_=FakeExec())


def test_org_plan_prints_the_default_plan_as_a_file_init_reads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "org",
        "plan",
        "o",
        "--project",
        "app",
        "--description",
        "The app.",
        "--approver",
        "human",
    ]
    assert main(argv) == 0
    plan = tmp_path / "org.yml"
    plan.write_text(capsys.readouterr().out)
    assert read_plan(plan, "o") == default_plan(
        "o", project="app", description="The app.", approvers=["human"]
    )


PREFIXED_PLAN = """\
org: o
approvers: [human]
repos:
  - {name: meta, title: Meta, kind: docs, purpose: Org-level docs.}
  - {name: app, kind: code, purpose: The app.}
  - {name: helper, kind: code, purpose: The helper.}
  - name: pando-session-memory
    kind: store
    store: session-memory
    purpose: Sessions.
    direct_pushes: true
  - {name: pando-waybill, kind: plain, purpose: Orders., direct_pushes: true}
"""


def test_prefixed_stores_are_created_stamped_and_reconciled_by_their_names(
    tmp_path: Path,
) -> None:
    stamped: list[str] = []

    def fake_stamp(directory: str, data: object = None, **_: object) -> None:
        stamped.append(Path(directory).name)

    plan = tmp_path / "org.yml"
    plan.write_text(PREFIXED_PLAN)
    fake, fake_exec = FakeRun(), FakeExec()
    run_org_init(
        plan_args(
            fake_meta(tmp_path),
            plan,
            "--workdir",
            str(tmp_path / "w"),
            "--secrets",
            str(tmp_path / "s"),
            *BOT,
        ),
        run=fake,
        exec_=fake_exec,
        stamp_with=fake_stamp,
    )
    created = [cmd[3] for cmd in fake.commands() if cmd[:3] == ("gh", "repo", "create")]
    assert created == [
        "o/meta",
        "o/app",
        "o/helper",
        "o/pando-session-memory",
        "o/pando-waybill",
    ]
    assert stamped == ["meta", "app", "helper", "pando-session-memory"]
    env = next(env for _, env in fake_exec.calls if "SYNC_RULESETS_CONF" in env)
    rulesets = Path(env["SYNC_RULESETS_CONF"]).read_text()
    assert '"p.json|except:pando-session-memory,pando-waybill"' in rulesets
    assert '"var|SESSION_MEMORY_REPO|all|o/pando-session-memory"' in credentials_conf(
        fake_exec
    )


def test_missing_plan_flags_are_refused_before_any_forge_call(tmp_path: Path) -> None:
    meta = fake_meta(tmp_path)
    fake = FakeRun()
    argv = ["org", "init", "o", "--meta", str(meta), "--project", "app"]
    with pytest.raises(ValueError, match="--plan"):
        run_org_init(build_parser().parse_args(argv), run=fake, exec_=FakeExec())
    assert fake.commands() == []


def test_without_bot_flags_org_init_uses_the_recorded_release_bot(tmp_path: Path) -> None:
    secrets = tmp_path / "s"
    secrets.mkdir()
    (secrets / "release-bot.json").write_text(
        '{"org": "o", "slug": "o-release-bot", "app_id": 4711, "client_id": "Iv23rec"}\n'
    )
    plan = tmp_path / "org.yml"
    plan.write_text(PLAN_FILE)
    fake_exec = FakeExec()
    run_org_init(
        plan_args(fake_meta(tmp_path), plan, "--dry-run", "--secrets", str(secrets)),
        run=FakeRun(),
        exec_=fake_exec,
    )
    conf = credentials_conf(fake_exec)
    assert '"o-release-bot"' in conf
    assert '"var|RELEASE_BOT_CLIENT_ID|all|Iv23rec"' in conf


@pytest.mark.parametrize(
    ("extra", "named"),
    [
        (("--release-bot-app", 'x$(touch pwned)', "--release-bot-client-id", "Iv1"), "release-bot-app"),
        (("--release-bot-app", "x", "--release-bot-client-id", 'Iv1"; rm -rf ~'), "client"),
        (("--board-url", "https://evil.example/x\"$(id)"), "board"),
    ],
    ids=["app", "client-id", "board-url"],
)
def test_odd_flag_values_are_refused_before_any_forge_call(
    tmp_path: Path, extra: tuple[str, ...], named: str
) -> None:
    plan = tmp_path / "org.yml"
    plan.write_text(PLAN_FILE)
    fake = FakeRun()
    with pytest.raises(ValueError, match=named):
        run_org_init(
            plan_args(fake_meta(tmp_path), plan, "--dry-run", *extra),
            run=fake,
            exec_=FakeExec(),
            stamp_with=no_stamp,
        )
    assert fake.commands() == []


@pytest.mark.parametrize("org", ["../escape", 'o"x', "dash-", "o/sub"])
def test_an_org_that_is_no_github_login_is_refused(tmp_path: Path, org: str) -> None:
    argv = ["org", "init", org, "--meta", str(fake_meta(tmp_path)), "--dry-run"]
    argv += ["--project", "app", "--description", "d", "--approver", "h"]
    fake = FakeRun()
    with pytest.raises(ValueError, match="org"):
        run_org_init(
            build_parser().parse_args(argv), run=fake, exec_=FakeExec(), stamp_with=no_stamp
        )
    assert fake.commands() == []
