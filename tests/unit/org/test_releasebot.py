from __future__ import annotations

import html
import http.client
import json
import socket
import time
import re
import stat
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from pandoscope.org.releasebot import (
    KEY_FILE,
    RECORD_FILE,
    callback_code,
    convert,
    form_page,
    install_url,
    listen,
    page_file,
    manifest,
    recorded,
    store,
)

from .fakes import FakeRun

CALLBACK = "http://127.0.0.1:8123/callback"


def test_the_manifest_asks_for_exactly_the_factory_bots_permissions() -> None:
    app = manifest("o", "o-release-bot", CALLBACK)
    assert app["default_permissions"] == {
        "actions": "read",
        "contents": "write",
        "issues": "read",
        "metadata": "read",
        "pull_requests": "write",
        "workflows": "write",
    }
    assert app["default_events"] == []


def test_the_manifest_app_stays_in_the_org_and_has_no_webhook() -> None:
    app = manifest("o", "o-release-bot", CALLBACK)
    assert app["name"] == "o-release-bot"
    assert app["public"] is False
    assert app["hook_attributes"]["active"] is False
    assert app["redirect_url"] == CALLBACK
    assert app["url"] == "https://github.com/o"


def test_the_page_posts_the_manifest_to_the_orgs_new_app_form() -> None:
    app = manifest("o", "o-release-bot", CALLBACK)
    page = form_page("o", app, "s-123")
    action = re.search(r'<form[^>]*action="([^"]+)"', page)
    assert action is not None
    assert html.unescape(action.group(1)) == (
        "https://github.com/organizations/o/settings/apps/new?state=s-123"
    )
    assert re.search(r'<form[^>]*method="post"', page)
    value = re.search(r'name="manifest" value="([^"]*)"', page)
    assert value is not None
    assert json.loads(html.unescape(value.group(1))) == app


def test_the_callback_with_its_own_state_yields_the_code() -> None:
    assert callback_code("/callback?code=abc123&state=s-123", "s-123") == "abc123"


@pytest.mark.parametrize(
    "path",
    [
        "/callback?code=abc123&state=forged",
        "/callback?code=abc123",
        "/callback?state=s-123",
        "/callback?code=&state=s-123",
        "/elsewhere?code=abc123&state=s-123",
        "/",
    ],
    ids=["wrong-state", "no-state", "no-code", "empty-code", "other-path", "root"],
)
def test_any_other_request_yields_no_code(path: str) -> None:
    assert callback_code(path, "s-123") is None


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
    "webhook_secret": None,
    "pem": "synthetic key material\n",
}
EXCHANGE = ("gh", "api", "--method", "POST", "app-manifests/abc123/conversions")


def test_the_code_is_exchanged_for_the_apps_credentials() -> None:
    fake = FakeRun({EXCHANGE: json.dumps(CONVERSION)})
    assert convert("abc123", fake) == CONVERSION
    assert fake.commands() == [EXCHANGE]


@pytest.mark.parametrize("code", ["../users", "abc 123", "abc?x=1", ""])
def test_a_code_that_is_no_plain_token_is_refused_before_any_call(code: str) -> None:
    fake = FakeRun()
    with pytest.raises(ValueError, match="code"):
        convert(code, fake)
    assert fake.commands() == []


def test_the_key_is_kept_readable_by_its_owner_only(tmp_path: Path) -> None:
    store(tmp_path, CONVERSION)
    key = tmp_path / KEY_FILE
    assert key.read_text() == CONVERSION["pem"]
    assert stat.S_IMODE(key.stat().st_mode) == 0o600


def test_the_record_names_the_app_and_keeps_no_secret(tmp_path: Path) -> None:
    record = store(tmp_path, CONVERSION)
    assert record == {"slug": "o-release-bot", "app_id": 4711, "client_id": "Iv23abc"}
    text = (tmp_path / RECORD_FILE).read_text()
    assert json.loads(text) == record
    assert "not-kept" not in text
    assert "synthetic key material" not in text
    assert recorded(tmp_path) == record


def test_an_existing_key_is_never_overwritten(tmp_path: Path) -> None:
    (tmp_path / KEY_FILE).write_text("the key in use\n")
    with pytest.raises(FileExistsError):
        store(tmp_path, CONVERSION)
    assert (tmp_path / KEY_FILE).read_text() == "the key in use\n"
    assert not (tmp_path / RECORD_FILE).exists()


def test_no_record_means_no_release_bot(tmp_path: Path) -> None:
    assert recorded(tmp_path) is None


def test_the_install_page_is_the_apps_own() -> None:
    assert install_url("o-release-bot") == (
        "https://github.com/apps/o-release-bot/installations/new"
    )


def get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as answer:  # noqa: S310 - local test server
            return answer.status, answer.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def test_the_local_callback_serves_no_page_and_returns_only_its_own_code() -> None:
    callback = listen("s-123", timeout=10)
    got: list[str] = []
    waiter = threading.Thread(target=lambda: got.append(callback.wait()))
    waiter.start()
    assert get(callback.url + "/")[0] == 404
    assert get(callback.url + "/callback?code=zz&state=forged")[0] == 400
    assert get(callback.url + "/callback?code=zz&state=s-123")[0] == 200
    waiter.join(5)
    callback.close()
    assert got == ["zz"]


def test_the_port_stays_taken_until_close() -> None:
    callback = listen("s-123", timeout=10)
    port = int(callback.url.rsplit(":", 1)[1])
    waiter = threading.Thread(target=callback.wait)
    waiter.start()
    get(callback.url + "/callback?code=zz&state=s-123")
    waiter.join(5)
    with pytest.raises(OSError):
        socket.create_server(("127.0.0.1", port))
    callback.close()
    socket.create_server(("127.0.0.1", port)).close()


def test_the_page_file_is_readable_by_its_owner_only() -> None:
    path = page_file("<p>state</p>")
    assert path.read_text() == "<p>state</p>"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700



def get_as(url: str, host: str, path: str) -> int:
    port = int(url.rsplit(":", 1)[1])
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path, headers={"Host": host})
    status = connection.getresponse().status
    connection.close()
    return status


def test_the_local_callback_answers_only_its_own_host() -> None:
    callback = listen("s-123", timeout=10)
    got: list[str] = []
    waiter = threading.Thread(target=lambda: got.append(callback.wait()))
    waiter.start()
    own = callback.url.removeprefix("http://")
    assert get_as(callback.url, "rebind.attacker.example", "/") == 400
    assert get_as(callback.url, "localhost:1", "/callback?code=evil&state=s-123") == 400
    assert get_as(callback.url, own, "/callback?code=zz&state=s-123") == 200
    waiter.join(5)
    assert got == ["zz"]


def test_an_idle_connection_does_not_hold_the_callback_past_its_timeout() -> None:
    callback = listen("s-123", timeout=1, read_timeout=0.5)
    port = int(callback.url.rsplit(":", 1)[1])
    idle = socket.create_connection(("127.0.0.1", port))
    raised: list[BaseException] = []

    def wait() -> None:
        try:
            callback.wait()
        except TimeoutError as error:
            raised.append(error)

    waiter = threading.Thread(target=wait, daemon=True)
    waiter.start()
    waiter.join(4)
    idle.close()
    assert not waiter.is_alive()
    assert len(raised) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"pem": None},
        {"slug": None},
        {"id": None},
        {"client_id": None},
        {"pem": ""},
        {"slug": "x$(touch pwned)"},
        {"slug": "../../elsewhere"},
        {"client_id": 'Iv23"; rm -rf ~; "'},
        {"id": "4711"},
        {"id": True},
    ],
    ids=["no-pem", "no-slug", "no-id", "no-client-id", "empty-pem", "shell-slug", "path-slug", "shell-client-id", "string-id", "bool-id"],
)
def test_a_conversion_with_a_missing_or_odd_field_is_refused_before_any_write(
    tmp_path: Path, change: dict[str, object]
) -> None:
    conversion = {k: v for k, v in {**CONVERSION, **change}.items() if v is not None}
    with pytest.raises(ValueError):
        store(tmp_path, conversion)
    assert list(tmp_path.iterdir()) == []


def test_a_planted_record_with_shell_characters_is_refused_on_reading(tmp_path: Path) -> None:
    (tmp_path / RECORD_FILE).write_text(
        '{"slug": "x$(touch pwned)", "app_id": 1, "client_id": "Iv23abc"}\n'
    )
    with pytest.raises(ValueError, match="slug"):
        recorded(tmp_path)


def test_the_secrets_directory_and_record_are_private_to_their_owner(tmp_path: Path) -> None:
    secrets = tmp_path / "orgs" / "o"
    store(secrets, CONVERSION)
    assert stat.S_IMODE(secrets.stat().st_mode) == 0o700
    assert stat.S_IMODE((secrets / RECORD_FILE).stat().st_mode) == 0o600


def test_a_symlink_at_the_key_path_is_refused_and_its_target_untouched(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.write_text("not yours\n")
    secrets = tmp_path / "s"
    secrets.mkdir()
    (secrets / KEY_FILE).symlink_to(target)
    with pytest.raises(FileExistsError):
        store(secrets, CONVERSION)
    assert target.read_text() == "not yours\n"
    assert not (secrets / RECORD_FILE).exists()


def test_an_empty_placeholder_key_is_replaced(tmp_path: Path) -> None:
    placeholder = tmp_path / KEY_FILE
    placeholder.write_text("")
    placeholder.chmod(0o644)
    store(tmp_path, CONVERSION)
    assert placeholder.read_text() == CONVERSION["pem"]
    assert stat.S_IMODE(placeholder.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("org", "name"),
    [
        pytest.param('o"><script>alert(1)</script>', "x", id="html"),
        pytest.param("o/../users", "n#frag", id="path"),
        pytest.param("o?state=forged", "n&manifest=", id="query"),
    ],
)
def test_a_hostile_org_or_name_stays_inside_one_escaped_form(org: str, name: str) -> None:
    page = form_page(org, manifest(org, name, CALLBACK), "s-123")
    actions = re.findall(r'<form[^>]*action="([^"]+)"', page)
    assert len(actions) == 1
    url = html.unescape(actions[0])
    assert url.startswith("https://github.com/organizations/")
    assert url.endswith("/settings/apps/new?state=s-123")
    assert url.count("/") == 7
    assert "<script>alert" not in page


def test_a_slug_with_a_slash_cannot_leave_the_apps_install_path() -> None:
    assert install_url("a/../../users").count("/") == 6


def trickle(port: int, stop: threading.Event) -> None:
    """Send a request one byte at a time, each well inside the read timeout."""
    peer = socket.create_connection(("127.0.0.1", port))
    for byte in b"GET /callback?code=slow&state=x HTTP/1.1\r\nHost: x\r\n":
        if stop.is_set():
            break
        peer.send(bytes([byte]))
        time.sleep(0.3)
    peer.close()


def test_a_trickling_peer_neither_blocks_the_callback_nor_its_deadline() -> None:
    callback = listen("s-123", timeout=1.5, read_timeout=0.5)
    port = int(callback.url.rsplit(":", 1)[1])
    stop = threading.Event()
    threading.Thread(target=trickle, args=(port, stop), daemon=True).start()
    time.sleep(0.2)
    assert get(callback.url + "/callback?code=zz&state=s-123")[0] == 200
    assert callback.wait() == "zz"
    callback.close()
    stop.set()
    late = listen("s-456", timeout=1.0, read_timeout=0.5)
    stop_late = threading.Event()
    threading.Thread(target=trickle, args=(int(late.url.rsplit(":", 1)[1]), stop_late), daemon=True).start()
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        late.wait()
    assert time.monotonic() - started < 2
    late.close()
    stop_late.set()


def test_a_non_ascii_state_is_refused_quietly(capfd: pytest.CaptureFixture[str]) -> None:
    callback = listen("s-123", timeout=5)
    try:
        status = get(callback.url + "/callback?code=x&state=%C3%A9")[0]
    except http.client.RemoteDisconnected:
        status = 0
    callback.close()
    assert status == 400
    assert "Traceback" not in capfd.readouterr().err


def test_callback_code_refuses_a_non_ascii_state() -> None:
    assert callback_code("/callback?code=x&state=%C3%A9", "s-123") is None


@pytest.mark.xfail(strict=True)
def test_a_secrets_path_that_is_a_symlink_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    (tmp_path / "link").symlink_to(real)
    with pytest.raises(ValueError, match="symlink"):
        store(tmp_path / "link", CONVERSION)
    assert list(real.iterdir()) == []


@pytest.mark.xfail(strict=True)
def test_a_secrets_directory_others_can_write_is_refused(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    with pytest.raises(ValueError, match="writable"):
        store(shared, CONVERSION)
    assert list(shared.iterdir()) == []


@pytest.mark.xfail(strict=True)
def test_an_existing_secrets_directory_ends_up_private(tmp_path: Path) -> None:
    secrets = tmp_path / "s"
    secrets.mkdir()
    secrets.chmod(0o755)
    store(secrets, CONVERSION)
    assert stat.S_IMODE(secrets.stat().st_mode) == 0o700


@pytest.mark.xfail(strict=True)
def test_a_temp_file_swapped_for_a_symlink_is_never_linked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secrets = tmp_path / "s"
    secrets.mkdir(mode=0o700)
    victim = tmp_path / "victim"
    victim.write_text("someone else's file\n")
    swapped = secrets / ".pandoscope-swapped"
    swapped.symlink_to(victim)
    written = tmp_path / "written"

    def fake_mkstemp(dir: Path, prefix: str) -> tuple[int, str]:  # noqa: A002
        return os.open(written, os.O_WRONLY | os.O_CREAT, 0o600), str(swapped)

    monkeypatch.setattr("pandoscope.org.releasebot.tempfile.mkstemp", fake_mkstemp)
    with pytest.raises(ValueError, match="temp"):
        store(secrets, CONVERSION)
    assert not (secrets / KEY_FILE).exists()
    assert victim.read_text() == "someone else's file\n"
