"""Role profiles: shipped by pandoscope, overridable whole-file by meta (D14)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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
    layers = (
        ("meta", session_root / META_OVERRIDE / f"{role}.yml"),
        ("pandoscope", SHIPPED / f"{role}.yml"),
    )
    for layer, path in layers:
        if path.is_file():
            data = yaml.safe_load(path.read_text())
            if not isinstance(data, dict):
                msg = f"profile {path} is not a mapping"
                raise ValueError(msg)
            return Profile(role, layer, path, data)
    msg = f"no profile for role {role!r} in {[str(p) for _, p in layers]}"
    raise FileNotFoundError(msg)
