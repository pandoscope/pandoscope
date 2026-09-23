"""The reviewer's task: the review pass file's prompt block, filled in."""

from __future__ import annotations

import re
from pathlib import Path

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
