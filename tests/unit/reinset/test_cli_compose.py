from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pandoscope.cli import main


def test_main_compose_prints_the_render_and_writes_the_file(
    session_root: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    answers = tmp_path / "answers.yml"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SESSION_ROOT", str(session_root))
    monkeypatch.setenv("REINSET_ANSWERS", str(answers))
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "remote")
    assert main(["compose"]) == 0
    out = capsys.readouterr().out
    assert "UNCONFIGURED" in out
    assert yaml.safe_load(answers.read_text())["detected"]["environment"] == "ccow"
    assert (home / ".claude" / "CLAUDE.md").exists()


def test_main_compose_reads_the_prompt_file(
    session_root: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(
        "<routine-fire-payload>\nreinset: nope@main:x\n</routine-fire-payload>\n"
    )
    answers = tmp_path / "answers.yml"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("REINSET_ANSWERS", str(answers))
    assert (
        main(
            [
                "compose",
                "--session-root",
                str(session_root),
                "--prompt-file",
                str(prompt),
            ]
        )
        == 0
    )
    on_disk = yaml.safe_load(answers.read_text())
    assert on_disk["errors"] and "reinset reference" in on_disk["errors"][0]
