"""
Where a session's role comes from (meta#194): an order, the environment, a role line.

A waybill order names a worker role; the order schema holds the list.
An environment names a worker role in ``REINSET_ROLE``.
A role line in a prompt declares orchestrator, implementer or probe;
the prompt hook reads the line and passes the role to the composer.
Only a session that the principal started may declare orchestrator.
Two signals tell such a session (decision 90, meta#194):
the entry point of the desktop app or a mobile app,
or the entry point ``remote`` with more than one attached repository,
since a session that another session creates gets one at most.
The setup script counts the attached repositories before anything clones
and exports the count as ``REINSET_ATTACHED_REPOS``.

Every worker role loses the tools that reach other sessions (meta#197).
"""

from __future__ import annotations

from collections.abc import Mapping

from pandoscope.reinset.order import ROLES

ROLE_ENV = "REINSET_ROLE"
ENTRYPOINT_ENV = "CLAUDE_CODE_ENTRYPOINT"
ATTACHED_ENV = "REINSET_ATTACHED_REPOS"
ORCHESTRATOR = "orchestrator"
REVIEWER = "reviewer"
# An order and an environment set these; the order schema is the authority.
WORKER_ROLES: tuple[str, ...] = ROLES
# A dojo probe declares its role in its first prompt, as a worker does.
DECLARABLE: tuple[str, ...] = (ORCHESTRATOR, "implementer", "probe")
# Measured 2026-11-17: the desktop app and the Android app.
# A session that another session created reads `remote`,
# and so does a session that the principal started in the web app.
PRINCIPAL_ENTRYPOINTS: tuple[str, ...] = ("remote_desktop", "remote_mobile")
SHARED_ENTRYPOINT = "remote"
# meta#197: a worker reports through its result file and the ledger.
# Each tool maps to the group that the denial names.
SEND_MESSAGE = "send a message to another session"
CREATE_SESSION = "create a session"
SCHEDULE = "create or fire a scheduled task"
WORKER_CLOSED_TOOLS: dict[str, str] = {
    "SendMessage": SEND_MESSAGE,
    "mcp__claude-code-remote__send_message": SEND_MESSAGE,
    "mcp__claude-code-remote__create_session": CREATE_SESSION,
    "mcp__claude-code-remote__create_trigger": SCHEDULE,
    "mcp__claude-code-remote__fire_trigger": SCHEDULE,
    "mcp__claude-code-remote__send_later": SCHEDULE,
}

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
    the role is orchestrator and ``principal_started`` finds no signal.
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
    if role == ORCHESTRATOR:
        why_not = principal_started(env)
        if why_not is not None:
            msg = (
                "the role line 'role: orchestrator' sets nothing: only a session "
                f"that the principal started may be orchestrator, and {why_not}"
            )
            raise RoleRefused(msg)


def principal_started(env: Mapping[str, str]) -> str | None:
    """
    Return None when ``env`` shows a session that the principal started.

    Otherwise return why it does not, naming the entry point
    and the attached repository count it read.
    A count that is missing or not a number shows nothing.
    """
    entrypoint = env.get(ENTRYPOINT_ENV, "")
    if entrypoint in PRINCIPAL_ENTRYPOINTS:
        return None
    shown = entrypoint or "(unset)"
    if entrypoint != SHARED_ENTRYPOINT:
        return (
            f"the entry point {shown!r} is none of "
            f"{', '.join((*PRINCIPAL_ENTRYPOINTS, SHARED_ENTRYPOINT))}"
        )
    count = env.get(ATTACHED_ENV, "").strip()
    if not count.isdigit():
        return (
            f"the entry point is {SHARED_ENTRYPOINT!r} and {ATTACHED_ENV} "
            f"holds no count ({count or 'unset'!r}), so the setup script did not "
            "record the attached repositories"
        )
    if int(count) <= 1:
        return (
            f"the entry point is {SHARED_ENTRYPOINT!r} and the platform attached "
            f"no more than one repository ({count}), as it does for a session "
            "that another session created"
        )
    return None


def tool_gate(role: str) -> dict[str, object]:
    """
    Return the tool gate of ``role`` for the hooks file (meta#197).

    Every role but orchestrator closes ``WORKER_CLOSED_TOOLS``;
    the orchestrator closes nothing.
    """
    closed = {} if role == ORCHESTRATOR else dict(WORKER_CLOSED_TOOLS)
    return {"role": role, "closed_tools": closed}
