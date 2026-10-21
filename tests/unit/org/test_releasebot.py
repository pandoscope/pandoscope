from __future__ import annotations

import html
import json
import re

import pytest

from pandoscope.org.releasebot import callback_code, convert, form_page, manifest

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


@pytest.mark.xfail(strict=True)
def test_the_code_is_exchanged_for_the_apps_credentials() -> None:
    fake = FakeRun({EXCHANGE: json.dumps(CONVERSION)})
    assert convert("abc123", fake) == CONVERSION
    assert fake.commands() == [EXCHANGE]


@pytest.mark.xfail(strict=True)
@pytest.mark.parametrize("code", ["../users", "abc 123", "abc?x=1", ""])
def test_a_code_that_is_no_plain_token_is_refused_before_any_call(code: str) -> None:
    fake = FakeRun()
    with pytest.raises(ValueError, match="code"):
        convert(code, fake)
    assert fake.commands() == []
