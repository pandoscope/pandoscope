"""--drag: no browser is opened; the owner drags the manifest page into the window they choose."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from pandoscope.org import command
from pandoscope.org.command import run_org_release_bot
from pandoscope.org.releasebot import KEY_FILE

from .test_release_bot_command import CONVERSION, Flow, bot_args


@pytest.mark.xfail(strict=True, reason="--drag is a stub")
def test_drag_shows_the_page_and_opens_no_browser(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    revealed: list[Path] = []

    def reveal(path: Path) -> None:
        revealed.append(path)
        flow.page = path.read_text()

    assert (
        run_org_release_bot(
            bot_args(tmp_path, "--drag"),  # type: ignore[arg-type]
            fetch=flow.fetch,
            browse=flow.browse,
            reveal=reveal,
            ask=flow.ask,
        )
        == 0
    )
    assert flow.opened == []
    (page,) = revealed
    assert not page.exists()
    out = capsys.readouterr().out
    assert f"Drag {page}" in out
    assert "https://github.com/apps/o-release-bot/installations/new" in out
    assert (tmp_path / ".secrets" / "orgs" / "o" / KEY_FILE).read_text() == CONVERSION["pem"]


@pytest.mark.xfail(strict=True, reason="no Finder reveal yet")
def test_the_page_is_shown_in_finder_on_macos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kwargs: calls.append(cmd))
    command.reveal_in_finder(tmp_path / "page.html")
    assert calls == [["open", "-R", str(tmp_path / "page.html")]]
