"""The claude-code receiver: where the intent reference arrives (D7)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

REF_ENV = "REINSET_REF"
PAYLOAD_BLOCK = "routine-fire-payload"

_REFERENCE = re.compile(
    r"^(?P<repo>[A-Za-z0-9._-]+)@(?P<commit>[0-9a-f]{7,40}):(?P<path>\S+)$"
)
_PAYLOAD = re.compile(rf"<{PAYLOAD_BLOCK}>(?P<body>.*?)</{PAYLOAD_BLOCK}>", re.DOTALL)
_LINE = re.compile(r"^\s*reinset:\s*(?P<ref>\S+)\s*$", re.MULTILINE)
# The review driver's marker (skills#195), on a line of its own; the
# tier is lowercase because it names the findings directory and the
# review branch verbatim.
_REVIEW = re.compile(
    r"^PANDO-REVIEW:\s*(?P<pass>[a-z0-9-]+)\s+tier=(?P<tier>[a-z0-9-]+)\s*$",
    re.MULTILINE,
)
# Where a fire payload names the pull request, most specific first.
_PULL_REQUEST = (
    re.compile(r"/pull/(?P<n>\d+)"),
    re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+#(?P<n>\d+)"),
    re.compile(r'"number":\s*(?P<n>\d+)'),
    re.compile(r"pull request[^\d\n]{0,12}(?P<n>\d+)", re.IGNORECASE),
)


@dataclass(frozen=True)
class Reference:
    """A parsed ``<repo>@<commit>:<path>`` intent reference."""

    repo: str
    commit: str
    path: str


@dataclass(frozen=True)
class Review:
    """A review session declared by the prompt's marker line."""

    pass_: str
    tier: str
    number: int | None


def find_review(prompt: str | None) -> Review | None:
    """
    Return the review the prompt's marker declares, or None.

    The pull request number is read from the rest of the prompt (a
    ``/pull/<n>`` URL, an ``owner/repo#n`` reference, a JSON ``number``
    field, or the words "pull request" followed by a number); None when
    nothing names one, so the task keeps its placeholder.
    """
    if not prompt:
        return None
    match = _REVIEW.search(prompt)
    if match is None:
        return None
    number = None
    for pattern in _PULL_REQUEST:
        hit = pattern.search(prompt)
        if hit:
            number = int(hit.group("n"))
            break
    return Review(match.group("pass"), match.group("tier"), number)


def parse_reference(text: str) -> Reference:
    """Parse ``<repo>@<sha>:<path>``. Raises ValueError on any other shape."""
    match = _REFERENCE.match(text)
    if match is None:
        msg = f"reinset reference must be <repo>@<sha>:<path>, got {text!r}"
        raise ValueError(msg)
    path = match.group("path")
    if path.startswith("/") or ".." in path.split("/"):
        msg = f"reinset reference path must stay inside the clone, got {path!r}"
        raise ValueError(msg)
    return Reference(match.group("repo"), match.group("commit"), path)


def find_reference(env: Mapping[str, str], prompt: str | None) -> str | None:
    """
    Return the reference string, or None when no channel carries one.

    Precedence: ``REINSET_REF``, then a ``reinset:`` line inside the
    prompt's ``<routine-fire-payload>`` block. A ``reinset:`` line outside
    that block is not a channel.
    """
    from_env = env.get(REF_ENV, "").strip()
    if from_env:
        return from_env
    if not prompt:
        return None
    block = _PAYLOAD.search(prompt)
    if block is None:
        return None
    line = _LINE.search(block.group("body"))
    return line.group("ref") if line else None
