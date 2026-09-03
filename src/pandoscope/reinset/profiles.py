"""Role profiles: shipped by pandoscope, overridable whole-file by meta (D14)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

SHIPPED = Path(__file__).parent / "profiles"
META_OVERRIDE = Path("meta") / "reinset" / "profiles"


@dataclass(frozen=True)
class Profile:
    """A loaded profile and the layer it came from."""

    role: str
    layer: str
    path: Path
    data: dict[str, Any]


def load_profile(role: str, session_root: Path) -> Profile:
    """
    Load ``<role>.yml``: meta's copy replaces the shipped one whole.

    Returns the profile with ``layer`` naming the winner (``meta`` or
    ``pandoscope``). Raises FileNotFoundError when neither layer has the
    role.
    """
    raise NotImplementedError
