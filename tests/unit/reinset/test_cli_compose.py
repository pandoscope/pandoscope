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
