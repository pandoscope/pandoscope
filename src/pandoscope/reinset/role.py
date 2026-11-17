"""
Where a session's role comes from (meta#194): an order, the environment, a role line.

A waybill order names a worker role; the order schema holds the list.
An environment names a worker role in ``REINSET_ROLE``.
A role line in a prompt declares orchestrator or implementer;
the prompt hook reads the line and passes the role to the composer.
Only a session that the principal started may declare orchestrator.
The entry point in the environment tells such a session,
against a list of measured values (meta#194, probe record part 2).
"""

from __future__ import annotations

from collections.abc import Mapping

from pandoscope.reinset.order import ROLES

ROLE_ENV = "REINSET_ROLE"
ENTRYPOINT_ENV = "CLAUDE_CODE_ENTRYPOINT"
ORCHESTRATOR = "orchestrator"
REVIEWER = "reviewer"
# An order and an environment set these; the order schema is the authority.
WORKER_ROLES: tuple[str, ...] = ROLES
DECLARABLE: tuple[str, ...] = (ORCHESTRATOR, "implementer")
# Measured 2026-11-17: the desktop app and the Android app.
# A session that another session created reads `remote`.
PRINCIPAL_ENTRYPOINTS: tuple[str, ...] = ("remote_desktop", "remote_mobile")

ORDER = "order"
ENVIRONMENT = "environment"
DECLARED = "declared"


class RoleRefused(Exception):
    """A role line or the environment named a role that sets nothing; says why."""


def environment_role(env: Mapping[str, str]) -> str | None:
    """
    Return the worker role that ``REINSET_ROLE`` names, or None when it names none.

    Raises RoleRefused when the variable names orchestrator,
    since a Routine in the wrong environment must never take itself for one.
    Raises RoleRefused when it names a role that is not a worker role.
    """
    role = env.get(ROLE_ENV, "").strip()
    if not role:
        return None
    if role == ORCHESTRATOR:
        msg = (
            f"the environment names orchestrator in {ROLE_ENV}; "
            "an environment sets a worker role only, so it set no role"
        )
        raise RoleRefused(msg)
    if role not in WORKER_ROLES:
        msg = (
            f"the environment names {role!r} in {ROLE_ENV}, "
            "which is not a worker role; "
            f"the worker roles are {', '.join(WORKER_ROLES)}"
        )
        raise RoleRefused(msg)
    return role


def check_declaration(
    role: str, env: Mapping[str, str], *, order_session: bool
) -> None:
    """
    Return None when the role line ``role: <role>`` may set ``role``.

    Raises RoleRefused, naming the reason, when:
    a waybill order started the session, since an order wins;
    the role is reviewer, since a reviewer takes its task from an order;
    the role is not declarable;
    the role is orchestrator and the entry point is not the principal's.
    """
    if order_session:
        msg = (
            f"the role line 'role: {role}' is ignored: a waybill order started "
            "this session, and an order wins over a role line"
        )
        raise RoleRefused(msg)
    if role == REVIEWER:
        msg = (
            "the role line 'role: reviewer' sets nothing: a reviewer takes its pull "
            "request and its kind of review from a waybill order, and no prompt "
            "form declares a reviewer yet"
        )
        raise RoleRefused(msg)
    if role not in DECLARABLE:
        msg = (
            f"the role line 'role: {role}' sets nothing: {role!r} is not a "
            f"declarable role; the declarable roles are {', '.join(DECLARABLE)}"
        )
        raise RoleRefused(msg)
    entrypoint = env.get(ENTRYPOINT_ENV, "")
    if role == ORCHESTRATOR and entrypoint not in PRINCIPAL_ENTRYPOINTS:
        msg = (
            "the role line 'role: orchestrator' sets nothing: only a session that "
            f"the principal started may be orchestrator, and the entry point "
            f"{entrypoint or '(unset)'!r} is not one of "
            f"{', '.join(PRINCIPAL_ENTRYPOINTS)}"
        )
        raise RoleRefused(msg)
