from __future__ import annotations

import pytest

from pandoscope.reinset.role import (
    DECLARABLE,
    PRINCIPAL_ENTRYPOINTS,
    WORKER_CLOSED_TOOLS,
    WORKER_ROLES,
    RoleRefused,
    check_declaration,
    environment_role,
    principal_started,
    tool_gate,
)


def test_the_worker_roles_are_the_order_roles_without_orchestrator() -> None:
    # Decisions 135 and 143: a probe is never an order, so no environment sets it.
    assert WORKER_ROLES == ("implementer", "reviewer")
    assert DECLARABLE == ("orchestrator", "implementer", "probe")


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


@pytest.mark.parametrize("role", ["general", "wizard"])
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


# Decision 90: `remote` with more than one attached repository is the principal's.
@pytest.mark.parametrize("count", ["2", "12"])
def test_remote_with_several_attached_repositories_may_declare_orchestrator(
    count: str,
) -> None:
    env = {"CLAUDE_CODE_ENTRYPOINT": "remote", "REINSET_ATTACHED_REPOS": count}
    assert principal_started(env) is None
    assert check_declaration("orchestrator", env, order_session=False) is None


@pytest.mark.parametrize("count", ["0", "1"])
def test_remote_with_one_repository_at_most_cannot_declare_orchestrator(
    count: str,
) -> None:
    env = {"CLAUDE_CODE_ENTRYPOINT": "remote", "REINSET_ATTACHED_REPOS": count}
    with pytest.raises(RoleRefused, match=rf"no more than one repository \({count}\)"):
        check_declaration("orchestrator", env, order_session=False)


@pytest.mark.parametrize("count", [None, "", "many", "-3"])
def test_remote_without_a_recorded_count_cannot_declare_orchestrator(
    count: str | None,
) -> None:
    env = {"CLAUDE_CODE_ENTRYPOINT": "remote"}
    if count is not None:
        env["REINSET_ATTACHED_REPOS"] = count
    with pytest.raises(RoleRefused, match="holds no count"):
        check_declaration("orchestrator", env, order_session=False)


def test_other_entry_points_ignore_the_repository_count() -> None:
    env = {"CLAUDE_CODE_ENTRYPOINT": "remote_trigger", "REINSET_ATTACHED_REPOS": "5"}
    with pytest.raises(RoleRefused, match="'remote_trigger' is none of"):
        check_declaration("orchestrator", env, order_session=False)


# meta#197: every worker role closes the tools that reach other sessions.
@pytest.mark.parametrize("role", WORKER_ROLES)
def test_a_worker_role_closes_the_three_tool_groups(role: str) -> None:
    gate = tool_gate(role)
    assert gate["role"] == role
    assert gate["closed_tools"] == WORKER_CLOSED_TOOLS
    assert set(WORKER_CLOSED_TOOLS.values()) == {
        "send a message to another session",
        "create a session",
        "create or fire a scheduled task",
    }


def test_the_orchestrator_closes_no_tool() -> None:
    assert tool_gate("orchestrator") == {"role": "orchestrator", "closed_tools": {}}


@pytest.mark.parametrize("entrypoint", ["remote", "remote_desktop", None])
def test_any_session_may_declare_probe(entrypoint: str | None) -> None:
    # Dojo probes open their first prompt with `role: probe`.
    env = {} if entrypoint is None else {"CLAUDE_CODE_ENTRYPOINT": entrypoint}
    assert check_declaration("probe", env, order_session=False) is None
