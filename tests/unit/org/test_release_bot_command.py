from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest

from pandoscope.cli import build_parser
from pandoscope.org.command import run_org_release_bot
from pandoscope.org.releasebot import KEY_FILE, RECORD_FILE

from .fakes import FakeRun

CONVERSION = {
    "id": 4711,
    "slug": "o-release-bot",
    "client_id": "Iv23abc",
    "client_secret": "not-kept",
    "name": "o-release-bot",
    "owner": {"login": "o", "type": "Organization"},
    "permissions": {
        "actions": "read",
        "contents": "write",
        "issues": "read",
        "metadata": "read",
        "pull_requests": "write",
        "workflows": "write",
    },
    "pem": "synthetic key material\n",
}
EXCHANGE = ("gh", "api", "--method", "POST", "app-manifests/abc123/conversions")


class FakeCallback:
    """Stands in for the browser's round trip: returns a code, keeps the page."""

    url = "http://127.0.0.1:9"

    def __init__(self) -> None:
        self.page = ""

    def wait(self, page: str) -> str:
        self.page = page
        return "abc123"


class Flow:
    def __init__(self) -> None:
        self.states: list[str] = []
        self.callback = FakeCallback()
        self.opened: list[str] = []
        self.run = FakeRun({EXCHANGE: json.dumps(CONVERSION)})

    def listen(self, state: str) -> FakeCallback:
        self.states.append(state)
        return self.callback

    def browse(self, url: str) -> bool:
        self.opened.append(url)
        return True

    def manifest(self) -> dict[str, object]:
        value = re.search(r'name="manifest" value="([^"]*)"', self.callback.page)
        assert value is not None
        parsed: dict[str, object] = json.loads(html.unescape(value.group(1)))
        return parsed


def bot_args(meta: Path, *extra: str) -> object:
    return build_parser().parse_args(["org", "release-bot", "o", "--meta", str(meta), *extra])


def go(flow: Flow, meta: Path, *extra: str) -> int:
    return run_org_release_bot(
        bot_args(meta, *extra),  # type: ignore[arg-type]
        run=flow.run,
        listen=flow.listen,
        browse=flow.browse,
    )


def test_the_flow_creates_the_app_and_keeps_its_key_in_the_orgs_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    assert go(flow, tmp_path) == 0
    secrets = tmp_path / ".secrets" / "orgs" / "o"
    assert (secrets / KEY_FILE).read_text() == CONVERSION["pem"]
    assert json.loads((secrets / RECORD_FILE).read_text())["client_id"] == "Iv23abc"
    out = capsys.readouterr().out
    assert "Iv23abc" in out
    assert "https://github.com/apps/o-release-bot/installations/new" in out
    assert "synthetic key material" not in out
    assert "not-kept" not in out


def test_the_browser_gets_the_manifest_page_then_the_install_page(tmp_path: Path) -> None:
    flow = Flow()
    go(flow, tmp_path)
    assert flow.opened == [
        "http://127.0.0.1:9/",
        "https://github.com/apps/o-release-bot/installations/new",
    ]
    app = flow.manifest()
    assert app["name"] == "o-release-bot"
    assert app["redirect_url"] == "http://127.0.0.1:9/callback"
    assert len(flow.states[0]) >= 22


def test_the_name_flag_names_the_app(tmp_path: Path) -> None:
    flow = Flow()
    named = {**CONVERSION, "name": "ada-release-bot", "slug": "ada-release-bot"}
    flow.run = FakeRun({EXCHANGE: json.dumps(named)})
    go(flow, tmp_path, "--name", "ada-release-bot")
    assert flow.manifest()["name"] == "ada-release-bot"


def test_an_existing_key_stops_the_flow_before_anything_happens(tmp_path: Path) -> None:
    secrets = tmp_path / "s"
    secrets.mkdir()
    (secrets / KEY_FILE).write_text("the key in use\n")
    flow = Flow()
    with pytest.raises(FileExistsError, match=KEY_FILE):
        go(flow, tmp_path, "--secrets", str(secrets))
    assert flow.states == []
    assert flow.opened == []
    assert flow.run.commands() == []


@pytest.mark.parametrize(
    ("change", "named"),
    [
        ({"owner": {"login": "attacker", "type": "User"}}, "attacker"),
        ({"name": "someone-elses-app"}, "someone-elses-app"),
        ({"permissions": {**CONVERSION["permissions"], "administration": "write"}}, "administration"),  # type: ignore[dict-item]
    ],
    ids=["foreign-owner", "other-name", "other-permissions"],
)
def test_an_app_that_is_not_the_one_asked_for_is_refused_and_nothing_kept(
    tmp_path: Path, change: dict[str, object], named: str
) -> None:
    flow = Flow()
    flow.run = FakeRun({EXCHANGE: json.dumps({**CONVERSION, **change})})
    with pytest.raises(ValueError, match=named):
        go(flow, tmp_path)
    secrets = tmp_path / ".secrets" / "orgs" / "o"
    assert not (secrets / KEY_FILE).exists()
    assert not (secrets / RECORD_FILE).exists()
    assert flow.opened == ["http://127.0.0.1:9/"]


@pytest.mark.xfail(strict=True)
def test_a_seeded_directory_with_an_empty_key_placeholder_is_filled(tmp_path: Path) -> None:
    secrets = tmp_path / ".secrets" / "orgs" / "o"
    secrets.mkdir(parents=True)
    (secrets / KEY_FILE).write_text("")
    flow = Flow()
    assert go(flow, tmp_path) == 0
    assert (secrets / KEY_FILE).read_text() == CONVERSION["pem"]
