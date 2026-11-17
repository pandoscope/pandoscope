from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pandoscope.cli import DECLARATION_REFUSED, main


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
    assert out.startswith("# No role")
    assert yaml.safe_load(answers.read_text())["detected"]["environment"] == "ccow"
    assert (home / ".claude" / "CLAUDE.md").exists()


@pytest.fixture
def cli_env(
    session_root: Path, home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """The process environment of a hand-started session; returns the answers path."""
    answers = tmp_path / "answers.yml"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SESSION_ROOT", str(session_root))
    monkeypatch.setenv("REINSET_ANSWERS", str(answers))
    monkeypatch.setenv("REINSET_HOOKS", str(tmp_path / "hooks.json"))
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-cli-0001")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "remote")
    for name in ("thread-ledger", "handing-off"):
        skill = session_root / "skills" / "original" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
    for script in ("guard.sh", "verify.sh"):
        (session_root / "skills" / "original" / "handing-off" / script).write_text("")
    return answers


def test_declare_prints_the_render_of_the_role(
    cli_env: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["compose", "--declare", "implementer"]) == 0
    assert capsys.readouterr().out.startswith("# Role: implementer")
    assert yaml.safe_load(cli_env.read_text())["resolved"]["role_source"] == "declared"
    assert (tmp_path / "hooks.json").is_file()


@pytest.mark.parametrize(
    ("role", "reason"),
    [
        ("reviewer", "a reviewer takes its pull request"),
        ("wizard", "the declarable roles are orchestrator, implementer"),
        ("orchestrator", "the entry point 'remote' is not one of"),
    ],
)
def test_a_refused_declaration_exits_3_with_one_line_naming_the_reason(
    cli_env: Path, capsys: pytest.CaptureFixture[str], role: str, reason: str
) -> None:
    assert main(["compose", "--declare", role]) == DECLARATION_REFUSED == 3
    out = capsys.readouterr().out
    assert out.startswith("ROLE LINE REFUSED: ")
    assert reason in out
    assert out.count("\n") == 1
    assert not cli_env.exists()
