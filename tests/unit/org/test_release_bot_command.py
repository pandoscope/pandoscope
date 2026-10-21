from __future__ import annotations

import html
import json
import re
import stat
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
EXCHANGE = (
    "env", "-u", "GH_DEBUG", "-u", "DEBUG",
    "gh", "api", "--method", "POST", "app-manifests/abc123/conversions",
)
APPS = "https://github.com/organizations/o/settings/apps"
REDIRECTED = APPS + "?code=abc123&state={state}"


class FakeCallback:
    """Stands in for GitHub's redirect: returns a code, records its closing."""

    url = "http://127.0.0.1:9"

    def __init__(self) -> None:
        self.closed = False

    def wait(self) -> str:
        return "abc123"

    def close(self) -> None:
        self.closed = True


class Flow:
    def __init__(self) -> None:
        self.states: list[str] = []
        self.callback = FakeCallback()
        self.opened: list[str] = []
        self.page = ""
        self.page_mode = 0
        self.page_path: Path | None = None
        self.run = FakeRun({EXCHANGE: json.dumps(CONVERSION)})
        self.pastes = [REDIRECTED]
        self.prompts: list[str] = []

    def listen(self, state: str) -> FakeCallback:
        self.states.append(state)
        return self.callback

    def browse(self, url: str) -> bool:
        self.opened.append(url)
        if url.startswith("file://"):
            self.page_path = Path(url.removeprefix("file://"))
            self.page = self.page_path.read_text()
            self.page_mode = stat.S_IMODE(self.page_path.stat().st_mode)
        return True

    def no_listen(self, state: str) -> FakeCallback:
        """A flow that pastes never waits for a callback."""
        self.states.append(state)
        callback = FakeCallback()

        def waited() -> str:
            raise AssertionError("the flow waited for a local callback")

        callback.wait = waited  # type: ignore[method-assign]
        return callback

    def ask(self, prompt: str) -> str:
        """Paste the next address, with the state the manifest page sent GitHub."""
        self.prompts.append(prompt)
        state = re.search(r"[?&]amp;state=([^\"&]*)|[?&]state=([^\"&]*)", self.page)
        assert state is not None
        return self.pastes.pop(0).format(state=state.group(1) or state.group(2))

    def manifest(self) -> dict[str, object]:
        value = re.search(r'name="manifest" value="([^"]*)"', self.page)
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


def paste(flow: Flow, meta: Path, *extra: str) -> int:
    return run_org_release_bot(
        bot_args(meta, *extra),  # type: ignore[arg-type]
        run=flow.run,
        listen=flow.no_listen,
        browse=flow.browse,
        ask=flow.ask,
    )


@pytest.mark.xfail(strict=True, reason="the command still waits for a local callback")
def test_the_pasted_redirect_is_exchanged_and_the_key_kept(tmp_path: Path) -> None:
    flow = Flow()
    assert paste(flow, tmp_path) == 0
    assert flow.run.commands() == [EXCHANGE]
    assert (tmp_path / ".secrets" / "orgs" / "o" / KEY_FILE).read_text() == CONVERSION["pem"]
    assert flow.manifest()["redirect_url"] == APPS
    assert len(flow.prompts) == 1


@pytest.mark.xfail(strict=True, reason="the command still waits for a local callback")
def test_a_paste_that_is_not_the_redirect_is_asked_for_again(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    flow.pastes = ["https://github.com.evil.example/x?code=abc123&state={state}", REDIRECTED]
    assert paste(flow, tmp_path) == 0
    assert len(flow.prompts) == 2
    assert flow.run.commands() == [EXCHANGE]


@pytest.mark.xfail(strict=True, reason="the command still waits for a local callback")
def test_three_wrong_pastes_end_the_flow_and_point_at_the_orgs_apps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    flow.pastes = [APPS + "?code=abc123&state=forged"] * 3
    with pytest.raises(ValueError, match="redirect"):
        paste(flow, tmp_path)
    assert flow.run.commands() == []
    assert APPS in capsys.readouterr().out
    assert flow.page_path is not None
    assert not flow.page_path.parent.exists()


@pytest.mark.xfail(strict=True, reason="the command still waits for a local callback")
def test_input_that_ends_points_at_the_orgs_apps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()

    def ended(prompt: str) -> str:
        raise EOFError

    flow.ask = ended  # type: ignore[method-assign]
    with pytest.raises(EOFError):
        paste(flow, tmp_path)
    assert APPS in capsys.readouterr().out
    assert flow.run.commands() == []


@pytest.mark.xfail(strict=True, reason="the command still waits for a local callback")
def test_a_failed_exchange_points_at_the_orgs_apps_and_never_shows_the_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()

    def refused(cmd: object, cwd: object) -> str:
        # What forge.run raises: the command, with the code in its API path.
        msg = f"command failed (exit 1) in cwd=None: {' '.join(EXCHANGE)}\nstderr: abc123 expired"
        raise RuntimeError(msg)

    flow.run = refused  # type: ignore[assignment]
    with pytest.raises(RuntimeError) as error:
        paste(flow, tmp_path)
    out = capsys.readouterr().out
    assert APPS in out
    assert "abc123" not in str(error.value) + out
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


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


def test_the_browser_gets_the_manifest_page_from_a_private_file_then_the_install_page(
    tmp_path: Path,
) -> None:
    flow = Flow()
    go(flow, tmp_path)
    assert flow.opened[0].startswith("file://")
    assert flow.opened[1:] == ["https://github.com/apps/o-release-bot/installations/new"]
    assert flow.page_mode == 0o600
    assert flow.page_path is not None
    assert not flow.page_path.exists()
    assert flow.callback.closed
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
    assert len(flow.opened) == 1
    assert flow.callback.closed


def test_a_seeded_directory_with_an_empty_key_placeholder_is_filled(tmp_path: Path) -> None:
    secrets = tmp_path / ".secrets" / "orgs" / "o"
    secrets.mkdir(parents=True)
    (secrets / KEY_FILE).write_text("")
    flow = Flow()
    assert go(flow, tmp_path) == 0
    assert (secrets / KEY_FILE).read_text() == CONVERSION["pem"]


def test_a_refused_conversion_shows_no_key_material(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    flow.run = FakeRun({EXCHANGE: json.dumps({**CONVERSION, "slug": "x$(touch pwned)"})})
    with pytest.raises(ValueError) as error:
        go(flow, tmp_path)
    shown = str(error.value) + capsys.readouterr().out
    assert "synthetic key material" not in shown
    assert "not-kept" not in shown


def test_a_refusal_after_the_exchange_points_at_the_orgs_new_app(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    odd = {**CONVERSION, "owner": {"login": "o"}, "permissions": {"contents": "write"}}
    flow.run = FakeRun({EXCHANGE: json.dumps(odd)})
    with pytest.raises(ValueError):
        go(flow, tmp_path)
    out = capsys.readouterr().out
    assert "https://github.com/organizations/o/settings/apps/o-release-bot" in out
    assert "synthetic key material" not in out


def test_a_key_that_appears_during_the_wait_points_at_the_new_app(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    secrets = tmp_path / ".secrets" / "orgs" / "o"

    def second_run_won() -> str:
        secrets.mkdir(parents=True, mode=0o700, exist_ok=True)
        (secrets / KEY_FILE).write_text("another run's key\n")
        return "abc123"

    flow.callback.wait = second_run_won  # type: ignore[method-assign]
    with pytest.raises(FileExistsError):
        go(flow, tmp_path)
    assert "https://github.com/organizations/o/settings/apps/o-release-bot" in capsys.readouterr().out
    assert (secrets / KEY_FILE).read_text() == "another run's key\n"


@pytest.mark.parametrize(
    ("org", "extra", "named"),
    [("../escape", (), "org"), ("o", ("--name", 'bot"><x'), "name"), ("o", ("--name", "x" * 35), "name")],
    ids=["org", "name-chars", "name-length"],
)
def test_odd_org_or_name_is_refused_before_the_flow(
    tmp_path: Path, org: str, extra: tuple[str, ...], named: str
) -> None:
    flow = Flow()
    args = build_parser().parse_args(["org", "release-bot", org, "--meta", str(tmp_path), *extra])
    with pytest.raises(ValueError, match=named):
        run_org_release_bot(args, run=flow.run, listen=flow.listen, browse=flow.browse)
    assert flow.states == []
