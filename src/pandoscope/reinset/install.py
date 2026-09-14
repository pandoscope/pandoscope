"""
Install the role's bundle: the profile's skills, rendered into ~/.claude/skills.

The profile names the skills,
and this step puts them where the harness reads them (skills#179 §4).
Each installed skill is a render, like CLAUDE.md.
The step copies it whole from its source and marks the copy.
The next pass replaces a marked copy whole.
A directory without the marker is never touched.
The general profile names no skill,
so an unconfigured SessionStart installs nothing
and removes what an earlier role left (D15).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pandoscope.reinset.profiles import Profile

MARKER_FILE = ".pandoscope-compose"
META_OVERRIDE = Path("meta") / "reinset" / "skills"
SKILLS_KIND = "skills"
SKILLS_LAYERS = ("original", "derived")
VENDORED = Path(".agents") / "skills"


@dataclass
class InstallReport:
    """What one install pass did."""

    installed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _layers(name: str, session_root: Path, repos: list[dict[str, Any]]) -> list[Path]:
    """Candidate source directories for ``name``, highest precedence first."""
    layers = [session_root / META_OVERRIDE / name]
    clones = [Path(repo["path"]) for repo in repos]
    for repo in repos:
        if repo.get("kind") == SKILLS_KIND:
            layers += [Path(repo["path"]) / layer / name for layer in SKILLS_LAYERS]
    layers += [clone / VENDORED / name for clone in clones]
    return layers


def find_skill(
    name: str, session_root: Path, repos: list[dict[str, Any]]
) -> Path | None:
    """Return the source directory for ``name``, or None when no layer has it."""
    for candidate in _layers(name, session_root, repos):
        if (candidate / "SKILL.md").is_file():
            return candidate
    return None


def _managed(target: Path) -> bool:
    return (target / MARKER_FILE).is_file()


def _copy(source: Path, target: Path, profile: Profile) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    for script in target.rglob("*.sh"):
        script.chmod(script.stat().st_mode | 0o111)
    marker = {
        "managedBy": "pandoscope compose",
        "role": profile.role,
        "layer": profile.layer,
        "source": str(source),
    }
    (target / MARKER_FILE).write_text(yaml.safe_dump(marker, sort_keys=False))


def install_bundle(
    profile: Profile,
    session_root: Path,
    home: Path,
    repos: list[dict[str, Any]],
    *,
    prune: bool,
) -> InstallReport:
    """
    Render the profile's skills into ``home/.claude/skills`` and return the report.

    A skill with no source is an error in the report, and the step skips it.
    So is a target directory without the marker.
    Nothing raises.
    With ``prune``, the step removes every marked directory
    that the profile does not name.
    """
    report = InstallReport()
    skills_dir = home / ".claude" / "skills"
    wanted = [str(name) for name in profile.data.get("skills") or []]
    for name in wanted:
        source = find_skill(name, session_root, repos)
        if source is None:
            searched = ", ".join(str(p) for p in _layers(name, session_root, repos))
            report.errors.append(f"skill {name!r} has no source; searched {searched}")
            continue
        target = skills_dir / name
        if target.exists() and not _managed(target):
            report.errors.append(
                f"{target} exists and is not managed by pandoscope compose "
                "— not overwriting"
            )
            continue
        _copy(source, target, profile)
        report.installed.append(name)
    if prune and skills_dir.is_dir():
        for entry in sorted(skills_dir.iterdir()):
            if entry.is_dir() and _managed(entry) and entry.name not in wanted:
                shutil.rmtree(entry)
                report.removed.append(entry.name)
    return report
