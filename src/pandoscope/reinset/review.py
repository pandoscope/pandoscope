"""The reviewer's task: the review pass file's prompt block, filled in."""

from __future__ import annotations

import re
from pathlib import Path

from pandoscope.reinset.receive import Review

PASS_DIR = Path("skills") / "original" / "thread-ledger" / "review"
_BLOCK = re.compile(r"^```text\n(?P<body>.*?)^```", re.MULTILINE | re.DOTALL)
_MARKER_LINE = re.compile(r"^PANDO-REVIEW:[^\n]*\n+")


class ReviewError(Exception):
    """A marker whose pass file cannot become a task."""


def review_task(session_root: Path, review: Review) -> str:
    """
    Return the task text for ``review``.

    Reads ``skills/original/thread-ledger/review/<pass>.md`` under the
    session root, takes its first fenced ``text`` block (the Routine
    prompt), drops the marker line the prompt already carries, and fills
    ``<tier>`` and, when known, ``<n>``. Raises ReviewError when the file
    or the block is missing.
    """
    path = session_root / PASS_DIR / f"{review.pass_}.md"
    if not path.is_file():
        msg = f"no review pass file at {path}"
        raise ReviewError(msg)
    block = _BLOCK.search(path.read_text())
    if block is None:
        msg = f"{path} holds no fenced text block to use as the prompt"
        raise ReviewError(msg)
    task = _MARKER_LINE.sub("", block.group("body"), count=1)
    task = task.replace("<tier>", review.tier)
    if review.number is not None:
        task = task.replace("<n>", str(review.number))
    return task
