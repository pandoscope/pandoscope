"""The claude-code receiver: where the intent reference arrives (D7)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

REF_ENV = "REINSET_REF"
PAYLOAD_BLOCK = "routine-fire-payload"


@dataclass(frozen=True)
class Reference:
    """A parsed ``<repo>@<commit>:<path>`` intent reference."""

    repo: str
    commit: str
    path: str


def parse_reference(text: str) -> Reference:
    """Parse ``<repo>@<sha>:<path>``. Raises ValueError on any other shape."""
    raise NotImplementedError


def find_reference(env: Mapping[str, str], prompt: str | None) -> str | None:
    """
    Return the reference string, or None when no channel carries one.

    Precedence: ``REINSET_REF``, then a ``reinset:`` line inside the
    prompt's ``<routine-fire-payload>`` block. A ``reinset:`` line outside
    that block is not a channel.
    """
    raise NotImplementedError
