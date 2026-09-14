from __future__ import annotations

from pathlib import Path

import yaml

from pandoscope.reinset.install import MARKER_FILE, find_skill, install_bundle
from pandoscope.reinset.profiles import Profile

REPOS = [
    {"path": "", "slug": "skills", "kind": "skills", "forge": "github"},
    {"path": "", "slug": "meta", "kind": "ops", "forge": "github"},
]


def repos_in(session_root: Path) -> list[dict[str, str]]:
    return [{**repo, "path": str(session_root / repo["slug"])} for repo in REPOS]


def make_skill(root: Path, name: str, *, script: str = "guard.sh") -> Path:
    """A skill directory: a manifest, a non-executable script, a nested file."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
    (root / script).write_text("#!/bin/bash\nexit 0\n")
    (root / script).chmod(0o644)
    (root / "nested").mkdir()
    (root / "nested" / "ref.md").write_text("data\n")
    return root


def profile(*skills: str, role: str = "orchestrator") -> Profile:
    return Profile(
        role, "pandoscope", Path(f"{role}.yml"), {"role": role, "skills": list(skills)}
    )


def test_find_skill_prefers_meta_then_original_then_derived_then_vendored(
    session_root: Path,
) -> None:
    repos = repos_in(session_root)
    assert find_skill("handing-off", session_root, repos) is None
    vendored = make_skill(
        session_root / "meta" / ".agents" / "skills" / "handing-off", "handing-off"
    )
    assert find_skill("handing-off", session_root, repos) == vendored
    derived = make_skill(
        session_root / "skills" / "derived" / "handing-off", "handing-off"
    )
    assert find_skill("handing-off", session_root, repos) == derived
    original = make_skill(
        session_root / "skills" / "original" / "handing-off", "handing-off"
    )
    assert find_skill("handing-off", session_root, repos) == original
    override = make_skill(
        session_root / "meta" / "reinset" / "skills" / "handing-off", "handing-off"
    )
    assert find_skill("handing-off", session_root, repos) == override


def test_install_copies_the_skill_executable_and_marked(
    session_root: Path, home: Path
) -> None:
    make_skill(session_root / "skills" / "original" / "handing-off", "handing-off")
    report = install_bundle(
        profile("handing-off"), session_root, home, repos_in(session_root), prune=True
    )
    assert report.installed == ["handing-off"]
    assert report.errors == []
    target = home / ".claude" / "skills" / "handing-off"
    assert (target / "SKILL.md").is_file()
    assert (target / "nested" / "ref.md").is_file()
    # The source is not executable; the hooks call this copy by path.
    assert (target / "guard.sh").stat().st_mode & 0o111
    marker = yaml.safe_load((target / MARKER_FILE).read_text())
    assert marker["role"] == "orchestrator"
    assert marker["source"] == str(session_root / "skills" / "original" / "handing-off")


def test_install_replaces_a_managed_copy_whole(session_root: Path, home: Path) -> None:
    make_skill(session_root / "skills" / "original" / "handing-off", "handing-off")
    repos = repos_in(session_root)
    install_bundle(profile("handing-off"), session_root, home, repos, prune=True)
    target = home / ".claude" / "skills" / "handing-off"
    (target / "guard.sh").write_text("stale\n")
    (target / "gone.md").write_text("orphan\n")
    report = install_bundle(
        profile("handing-off"), session_root, home, repos, prune=True
    )
    assert report.installed == ["handing-off"]
    assert (target / "guard.sh").read_text() != "stale\n"
    assert not (target / "gone.md").exists()


def test_install_refuses_an_unmanaged_directory(session_root: Path, home: Path) -> None:
    make_skill(session_root / "skills" / "original" / "handing-off", "handing-off")
    target = home / ".claude" / "skills" / "handing-off"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("hand-written\n")
    report = install_bundle(
        profile("handing-off"), session_root, home, repos_in(session_root), prune=True
    )
    assert report.installed == []
    assert len(report.errors) == 1
    assert "not managed" in report.errors[0]
    assert (target / "SKILL.md").read_text() == "hand-written\n"


def test_missing_skill_is_an_error_naming_the_layers(
    session_root: Path, home: Path
) -> None:
    report = install_bundle(
        profile("handing-off"), session_root, home, repos_in(session_root), prune=True
    )
    assert report.installed == []
    assert len(report.errors) == 1
    assert "handing-off" in report.errors[0]
    assert "original" in report.errors[0]


def test_prune_removes_managed_skills_the_role_no_longer_names(
    session_root: Path, home: Path
) -> None:
    make_skill(session_root / "skills" / "original" / "handing-off", "handing-off")
    make_skill(session_root / "skills" / "original" / "grilling", "grilling")
    repos = repos_in(session_root)
    install_bundle(
        profile("handing-off", "grilling"), session_root, home, repos, prune=True
    )
    # A hand-installed skill without the marker is never touched.
    foreign = home / ".claude" / "skills" / "mine"
    foreign.mkdir()
    (foreign / "SKILL.md").write_text("mine\n")
    report = install_bundle(
        profile("handing-off"), session_root, home, repos, prune=True
    )
    assert report.removed == ["grilling"]
    assert not (home / ".claude" / "skills" / "grilling").exists()
    assert (home / ".claude" / "skills" / "handing-off").is_dir()
    assert (foreign / "SKILL.md").is_file()


def test_no_prune_keeps_managed_skills_from_an_earlier_pass(
    session_root: Path, home: Path
) -> None:
    # Without prune, an install only adds.
    make_skill(session_root / "skills" / "original" / "handing-off", "handing-off")
    make_skill(session_root / "skills" / "original" / "grilling", "grilling")
    repos = repos_in(session_root)
    install_bundle(
        profile("handing-off", "grilling"), session_root, home, repos, prune=True
    )
    report = install_bundle(
        profile("handing-off"), session_root, home, repos, prune=False
    )
    assert report.removed == []
    assert (home / ".claude" / "skills" / "grilling").is_dir()


def test_general_with_prune_leaves_no_managed_skill(
    session_root: Path, home: Path
) -> None:
    # D15: the unconfigured state installs nothing.
    make_skill(session_root / "skills" / "original" / "handing-off", "handing-off")
    repos = repos_in(session_root)
    install_bundle(profile("handing-off"), session_root, home, repos, prune=True)
    report = install_bundle(
        profile(role="general"), session_root, home, repos, prune=True
    )
    assert report.removed == ["handing-off"]
    assert not (home / ".claude" / "skills" / "handing-off").exists()
