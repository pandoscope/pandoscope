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


@pytest.mark.xfail(strict=True)
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
    assert code == 0
    assert not any(cmd[:3] == ("gh", "repo", "create") for cmd in fake.commands())


@pytest.mark.xfail(strict=True)
def test_repo_sync_creates_and_stamps_the_repo_of_the_file(tmp_path: Path) -> None:
    path = tmp_path / "pandoscope.yml"
    path.write_text(ENTRY)
    fake = FakeRun()
    args = build_parser().parse_args(
        ["repo", "sync", str(path), "--workdir", str(tmp_path / "w"), "--template-ref", "main"]
    )

    run_repo_sync(args, run=fake, stamp_with=stamp_answers)

    commands = fake.commands()
    assert ("gh", "repo", "create", "someone/lean", "--private", "--description", "A trial project.") in commands
    push = next(cmd for cmd in commands if "push" in cmd)
    assert push[-2:] == ("https://github.com/someone/lean.git", "main")
