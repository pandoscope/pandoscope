"""The reviewer's task: the review pass file's prompt block, filled in."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pandoscope.reinset.receive import Order

PASS_DIR = Path("skills") / "original" / "thread-ledger" / "review"
_BLOCK = re.compile(r"^```text\n(?P<body>.*?)^```", re.MULTILINE | re.DOTALL)
_MARKER_LINE = re.compile(r"^PANDO-REVIEW:[^\n]*\n+")


class ReviewError(Exception):
    """An order whose pass file cannot become a task."""


def review_task(session_root: Path, pass_: str, tier: str, number: int) -> str:
    """
    Return the task text for review ``pass_`` of pull request ``number``.

    Reads ``skills/original/thread-ledger/review/<pass>.md`` under the
    session root. Takes its first fenced ``text`` block; the driver
    keeps that block as the prompt. Drops a leading marker line, a
    leftover from the days when the Routine prompt carried one. Fills
    ``<tier>`` and ``<n>``. Raises ReviewError when the file or the
    block is missing.
    """
    path = session_root / PASS_DIR / f"{pass_}.md"
    if not path.is_file():
        msg = f"no review pass file at {path}"
        raise ReviewError(msg)
    block = _BLOCK.search(path.read_text())
    if block is None:
        msg = f"{path} holds no fenced text block to use as the prompt"
        raise ReviewError(msg)
    task = _MARKER_LINE.sub("", block.group("body"), count=1)
    return task.replace("<tier>", tier).replace("<n>", str(number))


def pull_refs(clone: Path, number: int) -> tuple[str, str]:
    """
    Return the base branch and head sha of pull request ``number``, read from ``clone``.

    Fetches ``pull/<n>/head`` and every branch of ``origin``. The base
    is the branch the head sits closest above. Raises ReviewError when
    the clone is missing, the fetch fails or the base is ambiguous.
    """
    raise NotImplementedError


def hydrate(session_root: Path, order: Order) -> str:
    """
    Return the reviewer's task: the pass file's prompt block, every placeholder filled.

    Fills ``<repo>``, ``<n>``, ``<pass>``, ``<tier>``, ``<tickets>``
    from the order and ``<base>``, ``<head>`` from the clone of the
    pull request's repository under the session root. Raises
    ReviewError on a placeholder left unfilled.
    """
    raise NotImplementedError
