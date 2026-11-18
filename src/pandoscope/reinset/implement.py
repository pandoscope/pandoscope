"""The implementer's task, composed from the order and the clone (pandoscope#57)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import jinja2

from pandoscope.reinset.order_name import BUILD, FIX
from pandoscope.reinset.receive import WAYBILL, Order
from pandoscope.reinset.review import ReviewError, _check_origin, _default_branch, _git

TASK = Path(__file__).parent / "tasks" / "implementer.md.j2"
DISPOSITIONS = Path(WAYBILL) / "dispositions"


class ImplementError(Exception):
    """An implementer order whose task cannot be composed."""


def implementer_task(session_root: Path, order: Order) -> str:
    """
    Return the implementer's task, rendered from ``tasks/implementer.md.j2``.

    The order's pass decides, and its subject must fit it.
    The pass fix makes a fix round on a pull request of ``order.repo``:
    the task names the pull request's branch
    and the waybill's disposition files under the session root.
    The pass build makes a first build on an issue:
    the task names the tickets, the order's base or the default branch,
    and a new branch ``claude/<code><n>-implement-<step>``.
    Raises ImplementError when the subject's clone is missing
    or belongs to another repository,
    when a ref cannot be read,
    when the pass is build and the subject a pull request
    or the pass fix and the subject an issue, naming both,
    when no branch or more than one points at a pull request's head,
    and when a fix round finds no disposition folder.
    """
    clone = session_root / order.repo.rsplit("/", 1)[-1]
    if not (clone / ".git").exists():
        msg = f"no clone of the subject's repository {order.repo} at {clone}"
        raise ImplementError(msg)
    try:
        _check_origin(clone, order.repo)
        head = _pull_head(clone, order.number)
        _check_pass(order, head)
        values = {
            "id": order.data["id"],
            "model_tier": order.model_tier,
            "subject": order.subject,
            "clone": str(clone),
            "fix_round": head is not None,
        }
        if head is None:
            values |= _first_build(clone, order)
        else:
            values |= _fix_round(session_root, clone, order, head)
    except (ReviewError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", None) or str(error)
        msg = f"cannot compose the task of {order.subject} from {clone}: {detail}"
        raise ImplementError(msg) from error
    env = jinja2.Environment(  # noqa: S701 — the task is Markdown, not HTML
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
    )
    return env.from_string(TASK.read_text()).render(values)


def _pull_head(clone: Path, number: int) -> str | None:
    """Return the head sha of pull request ``number``, or None when it is an issue."""
    # DECISION: git, not the forge's API, tells a pull request from an issue.
    # The forge numbers both in one sequence (decision 106),
    # and only a pull request has a ref refs/pull/<n>/head.
    listed = _git(clone, "ls-remote", "origin", f"refs/pull/{number}/head")
    return listed.split()[0] if listed else None


def _check_pass(order: Order, head: str | None) -> None:
    """Raise ImplementError when the order's pass and its subject disagree."""
    # The order check knows only the subject's number;
    # git tells the composer what the number is (decision 109).
    if order.pass_ == BUILD and head is not None:
        msg = (
            f"the order's pass {BUILD!r} builds the ticket of an issue, "
            f"and its subject {order.subject} is a pull request"
        )
        raise ImplementError(msg)
    if order.pass_ == FIX and head is None:
        msg = (
            f"the order's pass {FIX!r} fixes the findings on a pull request, "
            f"and its subject {order.subject} is an issue"
        )
        raise ImplementError(msg)


def _first_build(clone: Path, order: Order) -> dict[str, str]:
    # The step is the last part of the name: a repeat run (`1b`)
    # gets a branch of its own.
    step = str(order.data["id"]).rsplit("-", 1)[-1]
    tickets = [order.subject, *(t for t in order.tickets if t != order.subject)]
    return {
        "base": order.base or _default_branch(clone),
        # DECISION: the composer names the branch, so the task states it.
        # It fits the ticket gate's branch pattern with the subject as its ticket.
        "branch": f"claude/{order.code}{order.number}-implement-{step}",
        "tickets": ", ".join(tickets),
    }


def _fix_round(
    session_root: Path, clone: Path, order: Order, head: str
) -> dict[str, str]:
    folder = session_root / DISPOSITIONS
    if not folder.is_dir():
        msg = f"a fix round reads the disposition files, and {folder} is missing"
        raise ImplementError(msg)
    # The forge keeps a pull request's branch at its head;
    # git names the branch only by that sha.
    heads = _git(clone, "ls-remote", "--heads", "origin").splitlines()
    branches = [
        ref.removeprefix("refs/heads/")
        for sha, ref in (line.split("\t") for line in heads)
        if sha == head
    ]
    if len(branches) != 1:
        found = ", ".join(branches) or "no branch"
        msg = (
            f"the head {head} of {order.subject} needs exactly one branch "
            f"of origin, and found {found}"
        )
        raise ImplementError(msg)
    return {
        "branch": branches[0],
        "dispositions": str(folder),
        "tickets": ", ".join(order.tickets) or "none",
    }
