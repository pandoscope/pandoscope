"""`pandoscope repo sync FILE`: one repository from its repo-mode file (#71)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.cli import build_parser
from pandoscope.org.command import run_repo_sync
from pandoscope.org.seed import ANSWERS_FILE

from .fakes import FakeRun
from .test_command import BOT, credentials_conf
from .test_reconcile import FakeExec, narrowing_meta
from .test_repo_entry import ENTRY


def stamp_answers(directory: str, data: object = None, **_: object) -> None:
    Path(directory).mkdir(parents=True, exist_ok=True)
    (Path(directory) / ANSWERS_FILE).write_text("_commit: v5.0.2\n")


def test_dry_run_reports_every_step_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "pandoscope.yml"
    path.write_text(ENTRY)
    fake = FakeRun()
    args = build_parser().parse_args(["repo", "sync", str(path), "--dry-run"])

    code = run_repo_sync(args, run=fake, stamp_with=stamp_answers)

    out = capsys.readouterr().out
    assert "someone/lean: exists would create" in out
    assert "someone/lean: first commit would stamp" in out
    assert "someone/lean: reconcile skipped (no meta checkout)" in out
    assert "someone/lean: check skipped (the repo does not exist yet)" in out
    assert code == 0
    assert not any(cmd[:3] == ("gh", "repo", "create") for cmd in fake.commands())


def test_repo_sync_creates_and_stamps_the_repo_of_the_file(tmp_path: Path) -> None:
    path = tmp_path / "pandoscope.yml"
    path.write_text(ENTRY)
    meta = ("gh", "api", "repos/someone/lean", "--jq", '"\\(.visibility) \\(.default_branch)"')
    fake = FakeRun(
        {
            meta: "private main\n",
            ("gh", "api", "repos/someone/lean/collaborators/helper-bot/permission"): "write\n",
        },
        errors={("gh", "api", "repos/someone/lean/rulesets"): "Upgrade to GitHub Pro (HTTP 403)"},
    )
    args = build_parser().parse_args(
        ["repo", "sync", str(path), "--workdir", str(tmp_path / "w"), "--template-ref", "main"]
    )

    run_repo_sync(args, run=fake, stamp_with=stamp_answers)

    commands = fake.commands()
    assert ("gh", "repo", "create", "someone/lean", "--private", "--description", "A trial project.") in commands
    push = next(cmd for cmd in commands if "push" in cmd)
    assert push[-2:] == ("https://github.com/someone/lean.git", "main")


def test_sync_refuses_a_file_without_an_agent(tmp_path: Path) -> None:
    """The wizard asks for the agent; sync needs the field filled in."""
    path = tmp_path / "pandoscope.yml"
    path.write_text(ENTRY.replace("agent: helper-bot\n", ""))
    args = build_parser().parse_args(["repo", "sync", str(path), "--dry-run"])
    with pytest.raises(ValueError, match="agent"):
        run_repo_sync(args, run=FakeRun(), stamp_with=stamp_answers)


def test_a_missing_point_fails_the_run_and_a_manual_one_does_not(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "pandoscope.yml"
    path.write_text(ENTRY)
    view = ("gh", "api", "repos/someone/lean", "--jq", ".name")
    meta = ("gh", "api", "repos/someone/lean", "--jq", '"\\(.visibility) \\(.default_branch)"')
    fake = FakeRun(
        {
            view: "lean\n",
            ("gh", "api", "repos/someone/lean/branches"): "main\n",
            meta: "private main\n",
            ("gh", "api", "repos/someone/lean/collaborators/helper-bot/permission"): "triage\n",
        },
        errors={("gh", "api", "repos/someone/lean/rulesets"): "Upgrade to GitHub Pro (HTTP 403)"},
    )
    args = build_parser().parse_args(["repo", "sync", str(path)])

    assert run_repo_sync(args, run=fake, stamp_with=stamp_answers) == 1
    out = capsys.readouterr().out
    assert "MISSING helper-bot" in out
    assert "MANUAL" in out


def existing_repo() -> FakeRun:
    """A forge where someone/lean exists, stamped, private, with the agent able to push."""
    view = ("gh", "api", "repos/someone/lean", "--jq", ".name")
    meta = ("gh", "api", "repos/someone/lean", "--jq", '"\\(.visibility) \\(.default_branch)"')
    return FakeRun(
        {
            view: "lean\n",
            ("gh", "api", "repos/someone/lean/branches"): "main\n",
            meta: "private main\n",
            ("gh", "api", "repos/someone/lean/collaborators/helper-bot/permission"): "write\n",
        },
        errors={("gh", "api", "repos/someone/lean/rulesets"): "Upgrade to GitHub Pro (HTTP 403)"},
    )


def with_meta(tmp_path: Path, *extra: str) -> list[str]:
    """`repo sync` argv for the entry, with a meta checkout and its secrets dir."""
    path = tmp_path / "pandoscope.yml"
    path.write_text(ENTRY)
    meta = narrowing_meta(tmp_path)
    secrets = tmp_path / "s"
    secrets.mkdir(exist_ok=True)
    return ["repo", "sync", str(path), "--meta", str(meta), "--secrets", str(secrets), *extra]


@pytest.mark.xfail(strict=True)
def test_with_meta_every_reconciler_runs_for_this_repo_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_exec = FakeExec()
    args = build_parser().parse_args(with_meta(tmp_path, *BOT))

    code = run_repo_sync(args, run=existing_repo(), exec_=fake_exec, stamp_with=stamp_answers)

    assert fake_exec.scripts() == [
        "sync-gh-repo-settings.sh",
        "sync-gh-repo-rulesets.sh",
        "sync-gh-actions-credentials.sh",
        "sync-gh-repo-collaborators.sh",
    ]
    assert all(env["SYNC_REPOS"] == "only:lean" for _, env in fake_exec.calls)
    assert '"var|BOT_MERGE_ENABLED|only:lean|true"' in credentials_conf(fake_exec)
    assert "someone/lean: reconcile converged" in capsys.readouterr().out
    assert code == 0


@pytest.mark.xfail(strict=True)
def test_dry_run_passes_dry_run_to_every_reconciler(tmp_path: Path) -> None:
    fake_exec = FakeExec()
    args = build_parser().parse_args(with_meta(tmp_path, "--dry-run"))
    run_repo_sync(args, run=existing_repo(), exec_=fake_exec, stamp_with=stamp_answers)
    assert len(fake_exec.calls) == 3
    assert all(cmd[-1] == "--dry-run" for cmd, _ in fake_exec.calls)


@pytest.mark.xfail(strict=True)
def test_a_dry_run_for_a_repo_that_does_not_exist_runs_no_reconciler(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_exec = FakeExec()
    args = build_parser().parse_args(with_meta(tmp_path, "--dry-run"))
    run_repo_sync(args, run=FakeRun(), exec_=fake_exec, stamp_with=stamp_answers)
    assert fake_exec.calls == []
    assert "someone/lean: reconcile would reconcile (the repo does not exist yet)" in (
        capsys.readouterr().out
    )


@pytest.mark.xfail(strict=True)
def test_drift_fails_the_run_and_prints_its_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_exec = FakeExec({"sync-gh-repo-rulesets.sh": 1}, "DRIFT   lean  protect-main (would fix)\n")
    args = build_parser().parse_args(with_meta(tmp_path, "--dry-run"))

    code = run_repo_sync(args, run=existing_repo(), exec_=fake_exec, stamp_with=stamp_answers)

    out = capsys.readouterr().out
    assert "someone/lean: reconcile DRIFT\n  rulesets: DRIFT   lean  protect-main (would fix)" in out
    assert code == 1


@pytest.mark.xfail(strict=True)
def test_a_manual_reconciler_line_does_not_fail_the_run(tmp_path: Path) -> None:
    fake_exec = FakeExec({"sync-gh-repo-settings.sh": 1}, "MANUAL  plan lacks a setting\n")
    args = build_parser().parse_args(with_meta(tmp_path))
    assert run_repo_sync(args, run=existing_repo(), exec_=fake_exec, stamp_with=stamp_answers) == 0


@pytest.mark.xfail(strict=True)
def test_a_meta_without_sync_repos_is_refused_before_any_forge_call(tmp_path: Path) -> None:
    argv = with_meta(tmp_path)
    (tmp_path / "meta" / "scripts" / "lib" / "scope.sh").write_text("scope_valid() { :; }\n")
    fake, fake_exec = FakeRun(), FakeExec()
    with pytest.raises(ValueError, match="sync_repos_scope"):
        run_repo_sync(build_parser().parse_args(argv), run=fake, exec_=fake_exec, stamp_with=stamp_answers)
    assert fake.commands() == []
    assert fake_exec.calls == []


@pytest.mark.xfail(strict=True)
def test_a_missing_secrets_dir_is_refused_before_any_forge_call(tmp_path: Path) -> None:
    """org init seeds a dir it finds missing; repo sync making it would skip that seed."""
    path = tmp_path / "pandoscope.yml"
    path.write_text(ENTRY)
    meta = narrowing_meta(tmp_path)
    fake = FakeRun()
    args = build_parser().parse_args(["repo", "sync", str(path), "--meta", str(meta)])
    with pytest.raises(ValueError, match="org init"):
        run_repo_sync(args, run=fake, exec_=FakeExec(), stamp_with=stamp_answers)
    assert fake.commands() == []
    assert not (meta / ".secrets").exists()


@pytest.mark.xfail(strict=True)
def test_secrets_default_to_the_owners_dir_in_meta(tmp_path: Path) -> None:
    path = tmp_path / "pandoscope.yml"
    path.write_text(ENTRY)
    meta = narrowing_meta(tmp_path)
    (meta / ".secrets" / "orgs" / "someone").mkdir(parents=True)
    fake_exec = FakeExec()
    args = build_parser().parse_args(["repo", "sync", str(path), "--meta", str(meta), *BOT])
    run_repo_sync(args, run=existing_repo(), exec_=fake_exec, stamp_with=stamp_answers)
    creds_env = fake_exec.calls[2][1]
    assert creds_env["SYNC_CREDENTIALS_SECRETS_DIR"] == str(meta / ".secrets" / "orgs" / "someone")


@pytest.mark.xfail(strict=True)
def test_the_board_url_goes_into_the_credentials(tmp_path: Path) -> None:
    board = "https://github.com/orgs/someone/projects/3"
    fake_exec = FakeExec()
    args = build_parser().parse_args(with_meta(tmp_path, *BOT, "--board-url", board))
    run_repo_sync(args, run=existing_repo(), exec_=fake_exec, stamp_with=stamp_answers)
    assert f'"var|PROJECT_BOARD_URL|all|{board}"' in credentials_conf(fake_exec)
