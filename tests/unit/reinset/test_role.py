from __future__ import annotations

import pytest

from pandoscope.reinset.role import (
    DECLARABLE,
    PRINCIPAL_ENTRYPOINTS,
    WORKER_ROLES,
    RoleRefused,
    check_declaration,
    environment_role,
)


def test_the_worker_roles_are_the_order_roles_without_orchestrator() -> None:
    assert WORKER_ROLES == ("implementer", "reviewer", "probe")
    assert DECLARABLE == ("orchestrator", "implementer")


@pytest.mark.parametrize("role", WORKER_ROLES)
def test_the_environment_names_a_worker_role(role: str) -> None:
    assert environment_role({"REINSET_ROLE": role}) == role


@pytest.mark.parametrize("value", [None, "", "  "])
def test_an_environment_without_a_role_names_none(value: str | None) -> None:
    env = {} if value is None else {"REINSET_ROLE": value}
    assert environment_role(env) is None


def test_an_environment_that_names_orchestrator_sets_no_role() -> None:
    with pytest.raises(RoleRefused, match="worker role only"):
        environment_role({"REINSET_ROLE": "orchestrator"})


@pytest.mark.parametrize("role", ["general", "wizard"])
def test_an_environment_that_names_an_unknown_role_sets_no_role(role: str) -> None:
    with pytest.raises(RoleRefused, match=f"'{role}'.*not a worker role"):
        environment_role({"REINSET_ROLE": role})


@pytest.mark.parametrize("entrypoint", PRINCIPAL_ENTRYPOINTS)
def test_the_principal_may_declare_orchestrator(entrypoint: str) -> None:
    env = {"CLAUDE_CODE_ENTRYPOINT": entrypoint}
    assert check_declaration("orchestrator", env, order_session=False) is None


@pytest.mark.parametrize("entrypoint", ["remote", "remote_trigger", "cli", None])
def test_another_entry_point_cannot_declare_orchestrator(
    entrypoint: str | None,
) -> None:
    env = {} if entrypoint is None else {"CLAUDE_CODE_ENTRYPOINT": entrypoint}
    with pytest.raises(RoleRefused, match="only a session that the principal started"):
        check_declaration("orchestrator", env, order_session=False)


def test_a_created_session_may_declare_implementer() -> None:
    env = {"CLAUDE_CODE_ENTRYPOINT": "remote"}
    assert check_declaration("implementer", env, order_session=False) is None


def test_reviewer_is_not_declarable_and_the_reason_says_why() -> None:
    with pytest.raises(
        RoleRefused, match=r"takes its pull request .* from a waybill order"
    ):
        check_declaration("reviewer", {}, order_session=False)


@pytest.mark.parametrize("role", ["general", "probe", "wizard"])
def test_an_unknown_role_lists_the_declarable_roles(role: str) -> None:
    with pytest.raises(
        RoleRefused, match="declarable roles are orchestrator, implementer"
    ):
        check_declaration(role, {}, order_session=False)


@pytest.mark.parametrize("role", ["implementer", "orchestrator"])
def test_an_order_wins_over_a_role_line(role: str) -> None:
    env = {"CLAUDE_CODE_ENTRYPOINT": "remote_desktop"}
    with pytest.raises(RoleRefused, match="an order wins over a role line"):
        check_declaration(role, env, order_session=True)
