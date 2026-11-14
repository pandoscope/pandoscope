"""The release bot's name: a default that fits, a public app of that name, a name changed on GitHub's page."""

from __future__ import annotations

import email.message
import json
import urllib.error
from pathlib import Path

import pytest

from pandoscope.org.releasebot import APP_NAME, default_name, public_app_named

from .fakes import FakeFetch
from .test_release_bot_command import CONVERSION, CONVERT, Flow, build_parser, go, run_org_release_bot

LOOKUP = "https://api.github.com/apps/"


@pytest.mark.parametrize(
    ("org", "name"),
    [("o", "o-release-bot"), ("ada-digital-assistant", "ada-digital-assistant-release-bot")],
)
def test_the_default_name_is_the_orgs(org: str, name: str) -> None:
    assert default_name(org) == name


@pytest.mark.parametrize("org", ["a" * 39, "abcdefghijklmnopqrstu-wxyz", "abcdefghijklmnopqrstuv-xyz"])
def test_a_long_orgs_default_name_is_shortened_to_fit(org: str) -> None:
    name = default_name(org)
    assert len(name) <= 34
    assert name.endswith("-release-bot")
    assert APP_NAME.fullmatch(name)


def test_a_public_app_of_that_name_is_found_and_a_404_is_not() -> None:
    fetch = FakeFetch(
        {
            ("GET", LOOKUP + "dependabot"): b"{}",
            ("GET", LOOKUP + "free-name"): urllib.error.HTTPError(
                LOOKUP + "free-name", 404, "Not Found", email.message.Message(), None
            ),
        }
    )
    assert public_app_named("dependabot", fetch)
    assert not public_app_named("free-name", fetch)


def test_a_public_app_of_that_name_stops_the_run_before_the_browser(tmp_path: Path) -> None:
    flow = Flow()
    flow.fetch.answers[("GET", LOOKUP + "o-release-bot")] = b"{}"
    with pytest.raises(ValueError, match="taken"):
        go(flow, tmp_path)
    assert flow.opened == []


def test_a_long_org_gets_a_default_name_that_fits(tmp_path: Path) -> None:
    org = "a" * 39
    flow = Flow()
    flow.pastes = [f"https://github.com/organizations/{org}/settings/apps?code=abc123&state={{state}}"]
    args = build_parser().parse_args(["org", "release-bot", org, "--meta", str(tmp_path)])
    with pytest.raises(ValueError):  # the fake conversion is o's, not this org's
        run_org_release_bot(args, fetch=flow.fetch, browse=flow.browse, ask=flow.ask)
    assert len(flow.manifest()["name"]) <= 34  # type: ignore[arg-type]


def test_the_steps_say_not_to_rename_on_githubs_page(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    told: list[str] = []
    flow.on_browse = lambda: told.append(capsys.readouterr().out) if not told else None
    go(flow, tmp_path)
    assert "taken" in told[0]
    assert "--name" in told[0]


def test_an_app_renamed_on_githubs_page_names_the_rerun(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flow = Flow()
    flow.on_browse = lambda: capsys.readouterr() and None  # only what comes after counts
    renamed = {**CONVERSION, "name": "o-release-bot-2", "slug": "o-release-bot-2"}
    flow.fetch.answers[CONVERT] = json.dumps(renamed).encode()
    with pytest.raises(ValueError, match="name"):
        go(flow, tmp_path)
    out = capsys.readouterr().out
    assert "--name o-release-bot-2" in out
    assert "delete" in out.lower()
