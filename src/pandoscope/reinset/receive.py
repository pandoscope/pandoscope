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


@dataclass(frozen=True)
class Reference:
    """A parsed ``<repo>@<commit>:<path>`` intent reference."""

    repo: str
    commit: str
    path: str


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
