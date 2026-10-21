from __future__ import annotations

import pytest

from pandoscope.org.releasebot import manifest

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
