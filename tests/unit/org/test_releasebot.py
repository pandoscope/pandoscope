from __future__ import annotations

import html
import json
import re
import stat
from pathlib import Path

import pytest

from pandoscope.org.releasebot import (
    KEY_FILE,
    RECORD_FILE,
    callback_code,
    convert,
    form_page,
    install_url,
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
