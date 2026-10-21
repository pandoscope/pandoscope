from __future__ import annotations

import errno
import fcntl
import html
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from pandoscope.org.releasebot import (
    KEY_FILE,
    RECORD_FILE,
    apps_url,
    check,
    convert,
    form_page,
    install_url,
    page_file,
    manifest,
    pasted_code,
    recorded,
    store,
)

from .fakes import FakeRun

APPS = "https://github.com/organizations/o/settings/apps"


def test_the_manifest_asks_for_exactly_the_factory_bots_permissions() -> None:
    app = manifest("o", "o-release-bot", APPS)
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
    app = manifest("o", "o-release-bot", APPS)
    assert app["name"] == "o-release-bot"
    assert app["public"] is False
    assert app["hook_attributes"]["active"] is False
    assert app["redirect_url"] == APPS
    assert app["url"] == "https://github.com/o"


def test_the_page_posts_the_manifest_to_the_orgs_new_app_form() -> None:
    app = manifest("o", "o-release-bot", APPS)
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


def test_github_sends_the_browser_back_to_the_orgs_apps_settings() -> None:
    assert apps_url("o") == APPS


@pytest.mark.parametrize(
    "pasted",
    [f"{APPS}?code=abc123&state=s-123", f"  {APPS}?state=s-123&code=abc123\n"],
    ids=["as-redirected", "other-order-and-whitespace"],
)
def test_the_pasted_redirect_with_its_own_state_yields_the_code(pasted: str) -> None:
    assert pasted_code(pasted, "o", "s-123") == "abc123"


@pytest.mark.parametrize(
    "pasted",
    [
        "http://github.com/organizations/o/settings/apps?code=abc123&state=s-123",
        "https://github.com.evil.example/organizations/o/settings/apps?code=abc123&state=s-123",
        "https://github.com@evil.example/organizations/o/settings/apps?code=abc123&state=s-123",
        "https://github.com:8443/organizations/o/settings/apps?code=abc123&state=s-123",
        "https://github.com/organizations/other/settings/apps?code=abc123&state=s-123",
        "https://github.com/organizations/o/settings/apps/x?code=abc123&state=s-123",
        f"{APPS}?code=abc123&state=forged",
        f"{APPS}?code=abc123&state=s-12\u00e9",
        f"{APPS}?code=abc123",
        f"{APPS}?state=s-123",
        f"{APPS}?code=&state=s-123",
        f"{APPS}?code=abc/../x&state=s-123",
        f"{APPS}?code=abc123&code=def456&state=s-123",
        "abc123",
        "",
    ],
    ids=[
        "http", "other-host", "userinfo", "port", "other-org", "other-path",
        "wrong-state", "non-ascii-state", "no-state", "no-code", "empty-code",
        "code-with-a-path", "two-codes", "bare-code", "nothing",
    ],
)
def test_any_other_pasted_text_yields_no_code(pasted: str) -> None:
    assert pasted_code(pasted, "o", "s-123") is None


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
EXCHANGE = (
    "env", "-u", "GH_DEBUG", "-u", "DEBUG", "-u", "GH_HOST",
    "gh", "api", "--method", "POST", "app-manifests/abc123/conversions",
)


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
    store(tmp_path, CONVERSION, "o")
    key = tmp_path / KEY_FILE
    assert key.read_text() == CONVERSION["pem"]
    assert stat.S_IMODE(key.stat().st_mode) == 0o600


def test_the_record_names_the_app_and_keeps_no_secret(tmp_path: Path) -> None:
    record = store(tmp_path, CONVERSION, "o")
    assert record == {"org": "o", "slug": "o-release-bot", "app_id": 4711, "client_id": "Iv23abc"}
    text = (tmp_path / RECORD_FILE).read_text()
    assert json.loads(text) == record
    assert "not-kept" not in text
    assert "synthetic key material" not in text
    assert recorded(tmp_path, "o") == record


def test_an_existing_key_is_never_overwritten(tmp_path: Path) -> None:
    (tmp_path / KEY_FILE).write_text("the key in use\n")
    with pytest.raises(FileExistsError):
        store(tmp_path, CONVERSION, "o")
    assert (tmp_path / KEY_FILE).read_text() == "the key in use\n"
    assert not (tmp_path / RECORD_FILE).exists()


def test_a_record_of_another_org_is_refused(tmp_path: Path) -> None:
    store(tmp_path, CONVERSION, "o")
    assert recorded(tmp_path, "O") is not None
    with pytest.raises(ValueError, match="org"):
        recorded(tmp_path, "other")


def test_a_record_that_names_no_org_is_refused(tmp_path: Path) -> None:
    (tmp_path / RECORD_FILE).write_text(
        '{"slug": "o-release-bot", "app_id": 4711, "client_id": "Iv23abc"}\n'
    )
    with pytest.raises(ValueError, match="org"):
        recorded(tmp_path, "o")


def test_a_key_that_cannot_be_placed_leaves_the_record_and_a_rerun_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise OSError(errno.EIO, "disk said no")

    with monkeypatch.context() as patched:
        patched.setattr(os, "link", broken)
        with pytest.raises(OSError, match="disk said no"):
            store(tmp_path, CONVERSION, "o")
    assert not (tmp_path / KEY_FILE).exists()
    assert recorded(tmp_path, "o") is not None
    store(tmp_path, CONVERSION, "o")
    assert (tmp_path / KEY_FILE).read_text() == CONVERSION["pem"]


def test_a_store_waits_for_the_lock_and_then_sees_the_key_another_run_kept(
    tmp_path: Path,
) -> None:
    secrets = tmp_path / "s"
    secrets.mkdir(mode=0o700)
    (secrets / KEY_FILE).write_text("")
    held = os.open(secrets, os.O_RDONLY)
    fcntl.flock(held, fcntl.LOCK_EX)
    raised: list[BaseException] = []

    def second() -> None:
        try:
            store(secrets, CONVERSION, "o")
        except BaseException as error:  # noqa: BLE001 - handed to the test
            raised.append(error)

    worker = threading.Thread(target=second, daemon=True)
    worker.start()
    worker.join(0.5)
    waited = worker.is_alive()
    (secrets / KEY_FILE).write_text("the first run's key\n")
    fcntl.flock(held, fcntl.LOCK_UN)
    os.close(held)
    worker.join(5)
    assert waited
    assert [type(error) for error in raised] == [FileExistsError]
    assert (secrets / KEY_FILE).read_text() == "the first run's key\n"


@pytest.mark.parametrize("code", [errno.ENOTSUP, errno.EOPNOTSUPP, errno.EPERM], ids=["ENOTSUP", "EOPNOTSUPP", "EPERM"])
def test_a_filesystem_without_hard_links_still_gets_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    def unsupported(*args: object, **kwargs: object) -> None:
        raise OSError(code, "no hard links here")

    monkeypatch.setattr(os, "link", unsupported)
    store(tmp_path, CONVERSION, "o")
    key = tmp_path / KEY_FILE
    assert key.read_text() == CONVERSION["pem"]
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([KEY_FILE, RECORD_FILE])


def test_missing_parents_are_created_private(tmp_path: Path) -> None:
    secrets = tmp_path / "meta" / ".secrets" / "orgs" / "o"
    store(secrets, CONVERSION, "o")
    for directory in (tmp_path / "meta", tmp_path / "meta" / ".secrets", secrets.parent):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700, directory


def test_a_parent_others_can_write_is_refused(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    with pytest.raises(ValueError, match="writable"):
        store(shared / "orgs" / "o", CONVERSION, "o")
    assert list(shared.iterdir()) == []


def test_a_sticky_parent_others_can_write_is_fine(tmp_path: Path) -> None:
    shared = tmp_path / "tmp"
    shared.mkdir()
    shared.chmod(0o1777)
    store(shared / "o", CONVERSION, "o")
    assert (shared / "o" / KEY_FILE).read_text() == CONVERSION["pem"]


def test_the_key_reaches_the_disk_before_it_is_linked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real_fsync, real_link = os.fsync, os.link

    def fsync(fd: int) -> None:
        calls.append("fsync")
        real_fsync(fd)

    def link(*args: object, **kwargs: object) -> None:
        calls.append("link")
        real_link(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "link", link)
    store(tmp_path, CONVERSION, "o")
    assert "link" in calls
    assert "fsync" in calls[: calls.index("link")]


def test_a_secrets_directory_swapped_after_its_check_gets_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secrets = tmp_path / "s"
    secrets.mkdir(mode=0o700)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    real_flock = fcntl.flock

    def flock_then_swap(fd: int, operation: int) -> None:
        real_flock(fd, operation)
        if operation == fcntl.LOCK_EX:
            secrets.rename(tmp_path / "checked")
            secrets.symlink_to(elsewhere)

    monkeypatch.setattr(fcntl, "flock", flock_then_swap)
    store(secrets, CONVERSION, "o")
    assert list(elsewhere.iterdir()) == []
    assert (tmp_path / "checked" / KEY_FILE).read_text() == CONVERSION["pem"]


def test_no_record_means_no_release_bot(tmp_path: Path) -> None:
    assert recorded(tmp_path, "o") is None


def test_the_install_page_is_the_apps_own() -> None:
    assert install_url("o-release-bot") == (
        "https://github.com/apps/o-release-bot/installations/new"
    )


def test_the_page_file_is_readable_by_its_owner_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The page holds a state: pytest's tmp_path cleans it up, the system's would not.
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    path = page_file("<p>state</p>")
    assert path.parent.parent == tmp_path
    assert path.read_text() == "<p>state</p>"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700



def test_the_page_file_is_utf8_whatever_the_locale(tmp_path: Path) -> None:
    # An ASCII locale, as a bare C locale gives when Python does not coerce it.
    env = {
        **os.environ,
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONCOERCECLOCALE": "0",
        "PYTHONUTF8": "0",
        "TMPDIR": str(tmp_path),
    }
    script = "from pandoscope.org.releasebot import page_file; print(page_file('<p>\u2026</p>'))"
    done = subprocess.run(  # noqa: S603 - the test's own interpreter
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert Path(done.stdout.strip()).read_bytes() == "<p>\u2026</p>".encode()


def test_a_page_file_that_cannot_be_written_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with pytest.raises(UnicodeEncodeError):
        page_file("<p>\ud800</p>")
    assert list(tmp_path.iterdir()) == []


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
        store(tmp_path, conversion, "o")
    assert list(tmp_path.iterdir()) == []


def test_a_planted_record_with_shell_characters_is_refused_on_reading(tmp_path: Path) -> None:
    (tmp_path / RECORD_FILE).write_text(
        '{"org": "o", "slug": "x$(touch pwned)", "app_id": 1, "client_id": "Iv23abc"}\n'
    )
    with pytest.raises(ValueError, match="slug"):
        recorded(tmp_path, "o")


def test_the_secrets_directory_and_record_are_private_to_their_owner(tmp_path: Path) -> None:
    secrets = tmp_path / "orgs" / "o"
    store(secrets, CONVERSION, "o")
    assert stat.S_IMODE(secrets.stat().st_mode) == 0o700
    assert stat.S_IMODE((secrets / RECORD_FILE).stat().st_mode) == 0o600


def test_a_symlink_at_the_key_path_is_refused_and_its_target_untouched(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.write_text("not yours\n")
    secrets = tmp_path / "s"
    secrets.mkdir()
    (secrets / KEY_FILE).symlink_to(target)
    with pytest.raises(FileExistsError):
        store(secrets, CONVERSION, "o")
    assert target.read_text() == "not yours\n"
    assert not (secrets / RECORD_FILE).exists()


def test_an_empty_placeholder_key_is_replaced(tmp_path: Path) -> None:
    placeholder = tmp_path / KEY_FILE
    placeholder.write_text("")
    placeholder.chmod(0o644)
    store(tmp_path, CONVERSION, "o")
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
    page = form_page(org, manifest(org, name, APPS), "s-123")
    actions = re.findall(r'<form[^>]*action="([^"]+)"', page)
    assert len(actions) == 1
    url = html.unescape(actions[0])
    assert url.startswith("https://github.com/organizations/")
    assert url.endswith("/settings/apps/new?state=s-123")
    assert url.count("/") == 7
    assert "<script>alert" not in page


def test_a_slug_with_a_slash_cannot_leave_the_apps_install_path() -> None:
    assert install_url("a/../../users").count("/") == 6


def test_a_secrets_path_that_is_a_symlink_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    (tmp_path / "link").symlink_to(real)
    with pytest.raises(ValueError, match="symlink"):
        store(tmp_path / "link", CONVERSION, "o")
    assert list(real.iterdir()) == []


def test_a_secrets_directory_others_can_write_is_refused(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    with pytest.raises(ValueError, match="writable"):
        store(shared, CONVERSION, "o")
    assert list(shared.iterdir()) == []


def test_an_existing_secrets_directory_ends_up_private(tmp_path: Path) -> None:
    secrets = tmp_path / "s"
    secrets.mkdir()
    secrets.chmod(0o755)
    store(secrets, CONVERSION, "o")
    assert stat.S_IMODE(secrets.stat().st_mode) == 0o700


def test_a_temp_file_swapped_for_a_symlink_is_never_linked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secrets = tmp_path / "s"
    secrets.mkdir(mode=0o700)
    victim = tmp_path / "victim"
    victim.write_text("someone else's file\n")
    real_fsync = os.fsync

    def fsync_then_swap(fd: int) -> None:
        real_fsync(fd)
        for temp in secrets.glob(".pandoscope-*"):
            temp.unlink()
            temp.symlink_to(victim)

    monkeypatch.setattr(os, "fsync", fsync_then_swap)
    with pytest.raises(ValueError, match="temp"):
        store(secrets, CONVERSION, "o")
    assert not (secrets / KEY_FILE).exists()
    assert victim.read_text() == "someone else's file\n"


@pytest.mark.parametrize("text", ["[]\n", '"slug"\n', "null\n"])
def test_a_record_that_is_no_object_is_refused(tmp_path: Path, text: str) -> None:
    (tmp_path / RECORD_FILE).write_text(text)
    with pytest.raises(ValueError, match="record"):
        recorded(tmp_path, "o")


def test_the_exchange_never_goes_to_another_gh_host() -> None:
    run = FakeRun({("env",): json.dumps(CONVERSION)})
    convert("abc123", run)
    (command,) = run.commands()
    assert command[: command.index("gh")].count("-u") >= 3
    assert "GH_HOST" in command[: command.index("gh")]


def test_an_app_that_subscribes_to_events_is_refused() -> None:
    with pytest.raises(ValueError, match="events"):
        check({**CONVERSION, "events": ["push"]}, "o", "o-release-bot")
