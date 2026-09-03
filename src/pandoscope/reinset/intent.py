"""Resolve an intent reference to the ``passed`` block."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pandoscope.reinset.receive import Reference

ROLES = ("orchestrator", "implementer", "reviewer", "general", "probe")
ORIGINS = ("principal", "spawner", "webhook", "poll")


class IntentError(Exception):
    """A reference that cannot become a valid ``passed`` block."""


def resolve_intent(reference: Reference, session_root: Path) -> dict[str, Any]:
    """
    Read ``<session_root>/<repo>`` at ``<commit>:<path>`` via git show.

    Returns the parsed ``passed`` mapping. Raises IntentError when the
    clone is absent, the object is unreachable, the file is not a mapping,
    a required key is missing, or ``role`` is absent or unknown.
    """
    raise NotImplementedError
