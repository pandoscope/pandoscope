from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.reinset.profiles import SHIPPED, load_profile
from pandoscope.reinset.role import DECLARABLE, WORKER_ROLES


@pytest.mark.parametrize("role", sorted({*WORKER_ROLES, *DECLARABLE}))
def test_every_role_ships_a_profile(role: str, session_root: Path) -> None:
    profile = load_profile(role, session_root)
    assert profile.role == role
    assert profile.layer == "pandoscope"
    assert profile.path == SHIPPED / f"{role}.yml"
    assert isinstance(profile.data["skills"], list)


def test_no_profile_is_named_general(session_root: Path) -> None:
    # meta#195: there is no default role.
    assert not (SHIPPED / "general.yml").exists()
    with pytest.raises(FileNotFoundError, match="general"):
        load_profile("general", session_root)


def test_orchestrator_and_implementer_carry_skills(session_root: Path) -> None:
    assert load_profile("orchestrator", session_root).data["skills"]
    assert load_profile("implementer", session_root).data["skills"]


def test_meta_copy_replaces_the_shipped_profile_whole(session_root: Path) -> None:
    override = session_root / "meta" / "reinset" / "profiles" / "reviewer.yml"
    override.parent.mkdir(parents=True)
    override.write_text("role: reviewer\nskills: [house-review]\n")
    profile = load_profile("reviewer", session_root)
    assert profile.layer == "meta"
    assert profile.path == override
    # Whole-file replacement: nothing from the shipped copy leaks through.
    assert profile.data == {"role": "reviewer", "skills": ["house-review"]}


def test_unknown_role_has_no_profile(session_root: Path) -> None:
    with pytest.raises(FileNotFoundError, match="wizard"):
        load_profile("wizard", session_root)
