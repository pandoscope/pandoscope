"""Every release surface carries one version (docs/releasing.md)."""

import json
import tomllib
from pathlib import Path

from pandoscope import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_every_release_surface_carries_the_same_version() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    npm = json.loads((ROOT / "npm" / "package.json").read_text())
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert (
        pyproject["project"]["version"]
        == npm["version"]
        == plugin["version"]
        == __version__
    )
