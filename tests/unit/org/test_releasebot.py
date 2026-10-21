from __future__ import annotations

import html
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from pandoscope.org.releasebot import (
    KEY_FILE,
    RECORD_FILE,
    apps_url,
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
    "env", "-u", "GH_DEBUG", "-u", "DEBUG",
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


def test_the_page_file_is_readable_by_its_owner_only() -> None:
    path = page_file("<p>state</p>")
    assert path.read_text() == "<p>state</p>"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700



@pytest.mark.xfail(strict=True, reason="page_file writes in the locale's encoding")
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


@pytest.mark.xfail(strict=True, reason="page_file leaves its directory behind on failure")
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
        store(tmp_path / "link", CONVERSION)
    assert list(real.iterdir()) == []


def test_a_secrets_directory_others_can_write_is_refused(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    with pytest.raises(ValueError, match="writable"):
        store(shared, CONVERSION)
    assert list(shared.iterdir()) == []


def test_an_existing_secrets_directory_ends_up_private(tmp_path: Path) -> None:
    secrets = tmp_path / "s"
    secrets.mkdir()
    secrets.chmod(0o755)
    store(secrets, CONVERSION)
    assert stat.S_IMODE(secrets.stat().st_mode) == 0o700


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


@pytest.mark.parametrize("text", ["[]\n", '"slug"\n', "null\n"])
def test_a_record_that_is_no_object_is_refused(tmp_path: Path, text: str) -> None:
    (tmp_path / RECORD_FILE).write_text(text)
    with pytest.raises(ValueError, match="record"):
        recorded(tmp_path)
