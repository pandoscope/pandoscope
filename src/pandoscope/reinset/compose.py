"""The composer entry point: detect, receive, resolve, compare, write, render."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ANSWERS_ENV = "REINSET_ANSWERS"


@dataclass
class Composition:
    """What one composer run produced."""

    answers: dict[str, Any]
    answers_path: Path
    render_path: Path
    render_text: str
    errors: list[str] = field(default_factory=list)


def compose(
    env: Mapping[str, str],
    session_root: Path,
    home: Path,
    prompt: str | None,
    path_dirs: list[Path],
) -> Composition:
    """
    Run one composition and write the answers file and the render.

    Returns the composition. Composer errors (a reference without a role,
    an unresolvable reference) are rendered, never raised: the session
    must hear them. Raises UnmanagedTargetError from the render step.
    """
    raise NotImplementedError
