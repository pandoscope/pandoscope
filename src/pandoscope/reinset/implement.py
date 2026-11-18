"""The implementer's task, composed from the order and the clone (pandoscope#57)."""

from __future__ import annotations

from pathlib import Path

from pandoscope.reinset.receive import Order


class ImplementError(Exception):
    """An implementer order whose task cannot be composed."""


def implementer_task(session_root: Path, order: Order) -> str:
    """Return the implementer's task."""
    raise NotImplementedError
