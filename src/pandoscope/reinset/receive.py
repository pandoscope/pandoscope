"""The claude-code receiver: the waybill order the Routine fired from (waybill#1)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pandoscope.reinset.order import (
    SHORTCODES,
    ShortcodeError,
    load_shortcodes,
    validate_order,
)

# When the Routine fires on waybill (waybill#1), the harness sets the
# trigger in the environment. It also checks out the pull request head
# under the waybill clone. The order file is therefore on disk before
# any hook runs.
TRIGGER_REPO_ENV = "CCR_TRIGGER_REPO"
TRIGGER_HEAD_ENV = "CCR_TRIGGER_HEAD_REF"
WAYBILL = "waybill"
ORDER_BRANCH_PREFIX = "order/"
_TICKET = re.compile(r"^(?P<repo>[^#]+)#(?P<n>\d+)$")


@dataclass(frozen=True)
class Order:
    """
    The waybill order that the Routine fired from (waybill#1).

    The order is the only receiver (ruling 2026-09-23, skills#195).
    It names the role, the model tier, the tickets
    and its subject: the issue or the pull request under work,
    split here into ``repo``, the repository's shortcode ``code`` and ``number``.
    For a reviewer it also names the pass.
    It may name a base.
    The Routine prompt carries no data.
    """

    path: Path
    data: dict[str, Any]
    role: str
    subject: str
    repo: str
    code: str
    number: int
    base: str | None
    pass_: str | None
    model_tier: str | None
    tickets: list[str]


class OrderError(Exception):
    """The trigger names an order that the clone cannot supply."""


def find_order(env: Mapping[str, str], session_root: Path) -> Order | None:
    """
    Return the order that the Routine fired from, or None for any other session.

    When the Routine fires on the waybill repository from an
    ``order/<name>`` branch, the trigger names
    ``<session_root>/waybill/orders/<name>.yml``. Raises OrderError when
    that file is missing, and when the waybill's ``shortcodes.json``
    beside ``orders/`` is missing or broken. Raises OrderError when the
    file departs from the order schema or its name pattern; the error
    names every violated field.
    """
    repo = env.get(TRIGGER_REPO_ENV, "")
    head = env.get(TRIGGER_HEAD_ENV, "")
    if repo.rsplit("/", 1)[-1] != WAYBILL or not head.startswith(ORDER_BRANCH_PREFIX):
        return None
    path = session_root / WAYBILL / "orders" / f"{head[len(ORDER_BRANCH_PREFIX) :]}.yml"
    if not path.is_file():
        msg = f"the trigger names an order but {path} is missing"
        raise OrderError(msg)
    try:
        shortcodes = load_shortcodes(session_root / WAYBILL / SHORTCODES)
    except ShortcodeError as error:
        raise OrderError(str(error)) from error
    data = yaml.safe_load(path.read_text())
    violations = validate_order(data, path.stem, shortcodes)
    if violations:
        msg = f"order {path} is off the schema: " + "; ".join(violations)
        raise OrderError(msg)
    match = _TICKET.match(data["subject"])
    assert match is not None  # noqa: S101 — the schema pins the pattern
    repo = match.group("repo")
    return Order(
        path,
        data,
        data["role"],
        data["subject"],
        repo,
        # A role without a name pattern needs no shortcode.
        shortcodes.get(repo, ""),
        int(match.group("n")),
        data.get("base"),
        data.get("pass"),
        data.get("model_tier"),
        list(data["tickets"]),
    )
