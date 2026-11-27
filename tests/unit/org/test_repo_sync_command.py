"""`pandoscope repo sync FILE`: one repository from its repo-mode file (#71)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.cli import build_parser
from pandoscope.org.command import run_repo_sync
from pandoscope.org.seed import ANSWERS_FILE

from .fakes import FakeRun
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
