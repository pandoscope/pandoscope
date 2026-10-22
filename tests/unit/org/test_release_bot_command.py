from __future__ import annotations

import builtins

import email.message
import getpass
import html
import inspect
import json
import re
import stat
import urllib.error
from collections.abc import Callable
from pathlib import Path

import pytest

from pandoscope.cli import build_parser
from pandoscope.org.command import run_org_release_bot
from pandoscope.org.releasebot import KEY_FILE, RECORD_FILE

from .fakes import FakeFetch

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
CONVERT = ("POST", "https://api.github.com/app-manifests/abc123/conversions")
PROBE = ("GET", "https://api.github.com/zen")
LOOKUP = ("GET", "https://api.github.com/apps/o-release-bot")
APPS = "https://github.com/organizations/o/settings/apps"
REDIRECTED = APPS + "?code=abc123&state={state}"


class AppsUnknown(FakeFetch):
    """GitHub's API without a public app of any name the tests use, unless the table says so."""

    def __call__(self, method: str, url: str) -> bytes:
        if method == "GET" and url.startswith("https://api.github.com/apps/") and (method, url) not in self.answers:
            self.calls.append((method, url))
            raise urllib.error.HTTPError(url, 404, "Not Found", email.message.Message(), None)
        return super().__call__(method, url)


class Flow:
    def __init__(self) -> None:
        self.opened: list[str] = []
        self.page = ""
        self.page_mode = 0
        self.page_path: Path | None = None
        self.fetch = AppsUnknown({CONVERT: json.dumps(CONVERSION).encode(), PROBE: b"ok"})
        self.pastes = [REDIRECTED]
        self.prompts: list[str] = []
        self.on_browse: Callable[[], None] = lambda: None

    def browse(self, url: str) -> bool:
        self.on_browse()
        self.opened.append(url)
        if url.startswith("file://"):
            self.page_path = Path(url.removeprefix("file://"))
            self.page = self.page_path.read_text()
            self.page_mode = stat.S_IMODE(self.page_path.stat().st_mode)
        return True

    def state(self) -> str:
        """The state the manifest page sends GitHub."""
        found = re.search(r"[?&](?:amp;)?state=([^\"&]*)", self.page)
        assert found is not None
        return found.group(1)

    def ask(self, prompt: str) -> str:
        """Paste the next address, with the state the manifest page sent GitHub."""
        self.prompts.append(prompt)
        return self.pastes.pop(0).format(state=self.state())

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
        fetch=flow.fetch,
        browse=flow.browse,
        ask=flow.ask,
    )


def test_the_pasted_redirect_is_exchanged_and_the_key_kept(tmp_path: Path) -> None:
    flow = Flow()
    assert go(flow, tmp_path) == 0
    assert flow.fetch.calls == [PROBE, LOOKUP, CONVERT]
    assert (tmp_path / ".secrets" / "orgs" / "o" / KEY_FILE).read_text() == CONVERSION["pem"]
    assert flow.manifest()["redirect_url"] == APPS
    assert len(flow.prompts) == 1


def test_a_paste_that_is_not_the_redirect_is_asked_for_again(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    flow.pastes = ["https://github.com.evil.example/x?code=abc123&state={state}", REDIRECTED]
    assert go(flow, tmp_path) == 0
    assert len(flow.prompts) == 2
    assert flow.fetch.calls == [PROBE, LOOKUP, CONVERT]


def test_three_wrong_pastes_end_the_flow_and_point_at_the_orgs_apps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    flow.pastes = [APPS + "?code=abc123&state=forged"] * 3
    with pytest.raises(ValueError, match="redirect"):
        go(flow, tmp_path)
    assert flow.fetch.calls == [PROBE, LOOKUP]
    assert APPS in capsys.readouterr().out
    assert flow.page_path is not None
    assert not flow.page_path.parent.exists()


def test_input_that_ends_points_at_the_orgs_apps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()

    def ended(prompt: str) -> str:
        raise EOFError

    flow.ask = ended  # type: ignore[method-assign]
    with pytest.raises(EOFError):
        go(flow, tmp_path)
    assert APPS in capsys.readouterr().out
    assert flow.fetch.calls == [PROBE, LOOKUP]


def test_a_failed_exchange_points_at_the_orgs_apps_and_never_shows_the_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()

    # An error that carries the code, as one naming the URL would.
    flow.fetch.answers[CONVERT] = urllib.error.URLError(f"{CONVERT[1]}: abc123 expired")
    with pytest.raises(RuntimeError) as error:
        go(flow, tmp_path)
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
    app = flow.manifest()
    assert app["name"] == "o-release-bot"
    assert app["redirect_url"] == APPS
    assert len(flow.state()) >= 22


def test_the_name_flag_names_the_app(tmp_path: Path) -> None:
    flow = Flow()
    named = {**CONVERSION, "name": "ada-release-bot", "slug": "ada-release-bot"}
    flow.fetch.answers[CONVERT] = (json.dumps(named)).encode()
    go(flow, tmp_path, "--name", "ada-release-bot")
    assert flow.manifest()["name"] == "ada-release-bot"


def test_an_existing_key_stops_the_flow_before_anything_happens(tmp_path: Path) -> None:
    secrets = tmp_path / "s"
    secrets.mkdir()
    (secrets / KEY_FILE).write_text("the key in use\n")
    flow = Flow()
    with pytest.raises(FileExistsError, match=KEY_FILE):
        go(flow, tmp_path, "--secrets", str(secrets))
    assert flow.prompts == []
    assert flow.opened == []
    assert flow.fetch.calls == []


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
    flow.fetch.answers[CONVERT] = (json.dumps({**CONVERSION, **change})).encode()
    with pytest.raises(ValueError, match=named):
        go(flow, tmp_path)
    secrets = tmp_path / ".secrets" / "orgs" / "o"
    assert not (secrets / KEY_FILE).exists()
    assert not (secrets / RECORD_FILE).exists()
    assert len(flow.opened) == 1


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
    flow.fetch.answers[CONVERT] = (json.dumps({**CONVERSION, "slug": "x$(touch pwned)"})).encode()
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
    flow.fetch.answers[CONVERT] = (json.dumps(odd)).encode()
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

    def second_run_won(prompt: str) -> str:
        secrets.mkdir(parents=True, mode=0o700, exist_ok=True)
        (secrets / KEY_FILE).write_text("another run's key\n")
        return REDIRECTED.format(state=flow.state())

    flow.ask = second_run_won  # type: ignore[method-assign]
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
        run_org_release_bot(args, fetch=flow.fetch, browse=flow.browse, ask=flow.ask)
    assert flow.prompts == []
    assert flow.opened == []


def test_before_the_browser_opens_the_owner_learns_what_github_must_show(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    told: list[str] = []
    flow.on_browse = lambda: told.append(capsys.readouterr().out) if not told else None
    go(flow, tmp_path)
    before = told[0]
    assert "o-release-bot" in before
    assert "for o" in before
    assert APPS in before
    assert "do not paste" in before


def test_the_paste_is_read_without_echo() -> None:
    assert inspect.signature(run_org_release_bot).parameters["ask"].default is getpass.getpass


def test_a_stopped_flow_says_to_delete_the_app_not_to_generate_a_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    flow.pastes = [APPS + "?code=abc123&state=forged"] * 3
    with pytest.raises(ValueError):
        go(flow, tmp_path)
    out = capsys.readouterr().out
    assert "delete" in out
    assert "generate" not in out.lower()


def test_a_stray_file_in_the_page_directory_does_not_lose_the_code(tmp_path: Path) -> None:
    flow = Flow()

    def paste_and_litter(prompt: str) -> str:
        assert flow.page_path is not None
        (flow.page_path.parent / ".DS_Store").write_text("")
        return REDIRECTED.format(state=flow.state())

    flow.ask = paste_and_litter  # type: ignore[method-assign]
    assert go(flow, tmp_path) == 0
    assert flow.fetch.calls == [PROBE, LOOKUP, CONVERT]
    assert flow.page_path is not None
    assert not flow.page_path.parent.exists()


@pytest.mark.parametrize(
    "answer",
    ['["synthetic key material"]', '"synthetic key material"', json.dumps({**CONVERSION, "owner": "o"}), json.dumps({**CONVERSION, "owner": [1]})],
    ids=["list", "string", "owner-string", "owner-list"],
)
def test_a_conversion_of_another_shape_is_refused_with_the_apps_note(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], answer: str
) -> None:
    flow = Flow()
    flow.fetch.answers[CONVERT] = (answer).encode()
    with pytest.raises(ValueError):
        go(flow, tmp_path)
    out = capsys.readouterr().out
    assert APPS in out
    assert "synthetic key material" not in out
    assert not (tmp_path / ".secrets" / "orgs" / "o" / KEY_FILE).exists()


def test_a_browser_that_fails_to_open_prints_no_app_note(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()

    def no_browser() -> None:
        raise OSError("no browser")

    flow.on_browse = no_browser
    with pytest.raises(OSError, match="no browser"):
        go(flow, tmp_path)
    assert "If GitHub created" not in capsys.readouterr().out


def test_a_secrets_directory_others_can_write_stops_the_flow_before_github(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    flow = Flow()
    with pytest.raises(ValueError, match="writable"):
        go(flow, tmp_path, "--secrets", str(shared))
    assert flow.opened == []
    assert flow.fetch.calls == []


def test_an_interrupt_while_storing_still_points_at_the_new_app(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("pandoscope.org.releasebot._place", interrupted)
    flow = Flow()
    with pytest.raises(KeyboardInterrupt):
        go(flow, tmp_path)
    assert "https://github.com/organizations/o/settings/apps/o-release-bot" in capsys.readouterr().out


def test_a_key_kept_by_another_run_meanwhile_is_never_to_be_overwritten(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    secrets = tmp_path / ".secrets" / "orgs" / "o"

    def another_run_kept_its_key(prompt: str) -> str:
        secrets.mkdir(parents=True, mode=0o700, exist_ok=True)
        (secrets / KEY_FILE).write_text("another run's key\n")
        return REDIRECTED.format(state=flow.state())

    flow.ask = another_run_kept_its_key  # type: ignore[method-assign]
    with pytest.raises(FileExistsError):
        go(flow, tmp_path)
    out = capsys.readouterr().out
    assert "save it as" not in out
    assert "delete" in out


@pytest.mark.parametrize(
    "change",
    [{"permissions": {**CONVERSION["permissions"], "administration": "write"}}, {"owner": {"login": "attacker"}}],  # type: ignore[dict-item]
    ids=["in-org", "foreign-owner"],
)
def test_a_refused_app_is_to_be_deleted_never_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: dict[str, object]
) -> None:
    flow = Flow()
    flow.on_browse = lambda: capsys.readouterr() and None  # only what comes after counts
    flow.fetch.answers[CONVERT] = (json.dumps({**CONVERSION, **change})).encode()
    with pytest.raises(ValueError):
        go(flow, tmp_path)
    out = capsys.readouterr().out
    assert APPS in out
    assert "delete" in out.lower()
    assert "generate" not in out.lower()
    assert "save it as" not in out


def test_an_app_whose_slug_is_not_its_names_is_refused_and_not_installed(tmp_path: Path) -> None:
    flow = Flow()
    flow.fetch.answers[CONVERT] = (json.dumps({**CONVERSION, "slug": "evil-public-app"})).encode()
    with pytest.raises(ValueError, match="slug"):
        go(flow, tmp_path)
    assert len(flow.opened) == 1
    assert not (tmp_path / ".secrets" / "orgs" / "o" / KEY_FILE).exists()


def test_an_interrupt_after_the_key_landed_says_it_is_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from pandoscope.org import secretsdir

    real_sync = secretsdir.full_sync
    calls: list[int] = []

    def sync_then_interrupt(fd: int) -> None:
        calls.append(fd)
        real_sync(fd)
        if len(calls) == 4:  # record file, record dir, key file, then the key's directory
            raise KeyboardInterrupt

    monkeypatch.setattr(secretsdir, "full_sync", sync_then_interrupt)
    flow = Flow()
    with pytest.raises(KeyboardInterrupt):
        go(flow, tmp_path)
    assert (tmp_path / ".secrets" / "orgs" / "o" / KEY_FILE).read_text() == CONVERSION["pem"]
    out = capsys.readouterr().out
    assert "not kept" not in out
    assert "https://github.com/apps/o-release-bot/installations/new" in out


@pytest.mark.parametrize("where", ["ask", "exchange"])
def test_an_interrupt_before_the_key_is_in_hand_names_the_apps_page_and_cleans_up(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], where: str
) -> None:
    flow = Flow()
    flow.on_browse = lambda: capsys.readouterr() and None  # only what comes after counts

    def interrupt(*args: object) -> str:
        raise KeyboardInterrupt

    if where == "ask":
        flow.ask = interrupt  # type: ignore[method-assign]
    else:
        flow.fetch.answers[CONVERT] = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        go(flow, tmp_path)
    assert APPS in capsys.readouterr().out
    assert flow.page_path is not None
    assert not flow.page_path.parent.exists()


def test_the_code_reaches_no_command_line(tmp_path: Path) -> None:
    flow = Flow()
    assert go(flow, tmp_path) == 0
    assert flow.fetch.calls == [PROBE, LOOKUP, CONVERT]
    assert (tmp_path / ".secrets" / "orgs" / "o" / KEY_FILE).read_text() == CONVERSION["pem"]


def test_an_unreachable_github_api_stops_the_flow_before_the_browser(tmp_path: Path) -> None:
    flow = Flow()
    flow.fetch.answers[PROBE] = urllib.error.URLError("certificate verify failed")
    with pytest.raises(RuntimeError, match="api.github.com"):
        go(flow, tmp_path)
    assert flow.opened == []


def test_a_failed_in_process_exchange_never_shows_the_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    flow.on_browse = lambda: capsys.readouterr() and None  # only what comes after counts
    flow.fetch.answers[CONVERT] = urllib.error.HTTPError(
        CONVERT[1], 500, "abc123 broke", email.message.Message(), None
    )
    with pytest.raises(RuntimeError) as error:
        go(flow, tmp_path)
    out = capsys.readouterr().out
    assert APPS in out
    assert "abc123" not in str(error.value) + out
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


def test_an_interrupt_before_the_app_is_checked_says_delete_without_blaming_the_app(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(*args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("pandoscope.org.releasebot.check", interrupted)
    flow = Flow()
    flow.on_browse = lambda: capsys.readouterr() and None  # only what comes after counts
    with pytest.raises(KeyboardInterrupt):
        go(flow, tmp_path)
    out = capsys.readouterr().out
    assert "not the one asked for" not in out
    assert "https://github.com/organizations/o/settings/apps/o-release-bot" in out
    assert "delete" in out.lower()
    assert "generate" not in out.lower()


def test_an_interrupt_before_the_report_still_says_the_key_is_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_print = builtins.print

    def print_until_the_report(*args: object, **kwargs: object) -> None:
        if args and str(args[0]).startswith("Created "):
            raise KeyboardInterrupt
        real_print(*args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(builtins, "print", print_until_the_report)
    flow = Flow()
    with pytest.raises(KeyboardInterrupt):
        go(flow, tmp_path)
    assert (tmp_path / ".secrets" / "orgs" / "o" / KEY_FILE).read_text() == CONVERSION["pem"]
    assert "holds the new app's key" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["Ada Bot", "ada.bot", "ada_bot", "ada--bot", "ada-"])
def test_a_name_whose_slug_github_might_spell_differently_is_refused(tmp_path: Path, name: str) -> None:
    flow = Flow()
    with pytest.raises(ValueError, match="name"):
        go(flow, tmp_path, f"--name={name}")
    assert flow.opened == []


def test_a_record_that_cannot_be_kept_says_how_org_init_finds_the_app(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    flow.on_browse = lambda: capsys.readouterr() and None  # only what comes after counts
    flow.fetch.answers[CONVERT] = json.dumps({**CONVERSION, "client_id": "not a client id"}).encode()
    with pytest.raises(ValueError, match="client"):
        go(flow, tmp_path)
    out = capsys.readouterr().out
    assert "--release-bot-app" in out
    assert "--release-bot-client-id" in out
