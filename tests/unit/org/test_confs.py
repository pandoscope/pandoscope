from __future__ import annotations

import pytest

from pandoscope.org.confs import (
    Credentials,
    credentials_conf,
    retarget,
    retarget_excepts,
)
from pandoscope.org.plan import Repo

PLAN = [
    Repo("meta", "m", {"agentic_subtemplate": "template"}),
    Repo("somnus", "s", {"agentic_subtemplate": "template"}),
    Repo("session-memory", "s", {"agentic_subtemplate": "x"}, direct_pushes=True),
    Repo("waybill", "w", direct_pushes=True),
]

META_RULESETS = """\
# comment naming pandoscope stays
ORG="pandoscope"

RULESETS=(
    "verified-signatures.json|all"
    "protect-main.json|except:session-memory,waybill"
    "require-ci-ok.json|except:session-memory,waybill"
)
"""


def test_retarget_rewrites_only_the_org_line() -> None:
    out = retarget(META_RULESETS, "somnus-app")
    assert 'ORG="somnus-app"' in out
    assert 'ORG="pandoscope"' not in out
    assert "# comment naming pandoscope stays" in out


def test_retarget_refuses_a_conf_without_an_org_line() -> None:
    with pytest.raises(ValueError, match="ORG="):
        retarget("RULESETS=()\n", "o")


def test_retarget_excepts_names_the_plans_direct_push_repos() -> None:
    out = retarget_excepts(META_RULESETS, ["session-memory", "waybill", "ledger"])
    assert '"protect-main.json|except:session-memory,waybill,ledger"' in out
    assert '"require-ci-ok.json|except:session-memory,waybill,ledger"' in out
    assert '"verified-signatures.json|all"' in out


def test_retarget_excepts_without_direct_push_repos_widens_to_all() -> None:
    out = retarget_excepts(META_RULESETS, [])
    assert '"protect-main.json|all"' in out


def full() -> Credentials:
    return Credentials(
        app_slug="somnus-release-bot",
        client_id="Iv23abc",
        board_url="https://github.com/orgs/somnus-app/projects/1",
    )


def test_credentials_conf_targets_the_org_and_its_session_store() -> None:
    conf = credentials_conf("somnus-app", PLAN, full())
    assert 'ORG="somnus-app"' in conf
    assert '"somnus-release-bot"' in conf
    assert '"var|RELEASE_BOT_CLIENT_ID|all|Iv23abc"' in conf
    assert '"var|SESSION_MEMORY_REPO|all|somnus-app/session-memory"' in conf
    assert (
        '"var|PROJECT_BOARD_URL|all|https://github.com/orgs/somnus-app/projects/1"'
        in conf
    )
    assert '"secret|PROJECT_BOARD_TOKEN|all|PROJECT_BOARD_TOKEN"' in conf


def test_bot_merge_covers_exactly_the_gated_repos() -> None:
    conf = credentials_conf("o", PLAN, full())
    assert '"var|BOT_MERGE_ENABLED|only:meta,somnus|true"' in conf


def test_credentials_without_a_board_leave_the_board_out() -> None:
    creds = Credentials(app_slug="a", client_id="c", board_url=None)
    conf = credentials_conf("o", PLAN, creds)
    assert "PROJECT_BOARD" not in conf


def test_credentials_carry_no_pandoscope_values() -> None:
    conf = credentials_conf("o", PLAN, full())
    values = [line for line in conf.splitlines() if not line.startswith("#")]
    assert not [line for line in values if "pandoscope" in line]


@pytest.mark.parametrize(
    "secret",
    [
        "RELEASE_BOT_PRIVATE_KEY|all|RELEASE_BOT_PRIVATE_KEY.pem",
        "LABELS_TOKEN",
        "PUSH_BLOCKLIST",
    ],
)
def test_credentials_declare_the_shared_secrets(secret: str) -> None:
    assert f'"secret|{secret}' in credentials_conf("o", PLAN, full())


def test_credentials_without_a_session_store_refuse() -> None:
    with pytest.raises(ValueError, match="session-memory"):
        credentials_conf("o", PLAN[:2], full())
