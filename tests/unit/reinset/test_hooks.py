from __future__ import annotations

import json
from pathlib import Path

from pandoscope.reinset.hooks import render_hooks
from pandoscope.reinset.profiles import Profile


def installed(home: Path, name: str, *scripts: str) -> Path:
    skill = home / ".claude" / "skills" / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
    for script in scripts:
        (skill / script).write_text("#!/bin/bash\nexit 0\n")
        (skill / script).chmod(0o755)
    return skill


def profile(hooks: list[dict[str, str]], *skills: str) -> Profile:
    data = {"role": "orchestrator", "skills": list(skills), "hooks": hooks}
    return Profile("orchestrator", "pandoscope", Path("orchestrator.yml"), data)


def test_hooks_resolve_to_the_installed_skill_scripts(home: Path) -> None:
    skill = installed(home, "handing-off", "guard.sh", "verify.sh")
    target = home / ".claude" / "reinset" / "hooks.json"
    rendered, errors = render_hooks(
        profile(
            [
                {"event": "PreCompact", "command": "handing-off/guard.sh"},
                {
                    "event": "SessionStart",
                    "matcher": "compact",
                    "command": "handing-off/verify.sh",
                },
            ],
            "handing-off",
        ),
        home,
        target,
    )
    assert errors == []
    assert rendered == {
        "PreCompact": [{"command": str(skill / "guard.sh")}],
        "SessionStart": [{"matcher": "compact", "command": str(skill / "verify.sh")}],
    }
    assert json.loads(target.read_text()) == rendered


def test_a_hook_outside_the_bundle_or_missing_on_disk_is_an_error(home: Path) -> None:
    installed(home, "handing-off", "guard.sh")
    target = home / ".claude" / "reinset" / "hooks.json"
    rendered, errors = render_hooks(
        profile(
            [
                {"event": "PreCompact", "command": "grilling/check.sh"},
                {"event": "PreCompact", "command": "handing-off/absent.sh"},
                {"event": "PreCompact", "command": "handing-off/guard.sh"},
            ],
            "handing-off",
        ),
        home,
        target,
    )
    assert len(errors) == 2
    assert "grilling/check.sh" in errors[0]
    assert "absent.sh" in errors[1]
    # The good entry still renders; the bad ones are left out.
    assert list(rendered) == ["PreCompact"]
    assert len(rendered["PreCompact"]) == 1


def test_an_unknown_event_is_an_error(home: Path) -> None:
    installed(home, "handing-off", "guard.sh")
    target = home / ".claude" / "reinset" / "hooks.json"
    rendered, errors = render_hooks(
        profile(
            [{"event": "OnCoffee", "command": "handing-off/guard.sh"}], "handing-off"
        ),
        home,
        target,
    )
    assert rendered == {}
    assert len(errors) == 1
    assert "OnCoffee" in errors[0]


def test_a_profile_without_hooks_renders_an_empty_file(home: Path) -> None:
    # For general, and for any role with skills but no hooks,
    # the dispatcher finds a file with nothing to run.
    target = home / ".claude" / "reinset" / "hooks.json"
    rendered, errors = render_hooks(profile([]), home, target)
    assert (rendered, errors) == ({}, [])
    assert json.loads(target.read_text()) == {}


def test_a_hook_script_escaping_its_skill_is_an_error(home: Path) -> None:
    installed(home, "handing-off", "guard.sh")
    installed(home, "grilling", "check.sh")
    target = home / ".claude" / "reinset" / "hooks.json"
    rendered, errors = render_hooks(
        profile(
            [{"event": "PreCompact", "command": "handing-off/../grilling/check.sh"}],
            "handing-off",
        ),
        home,
        target,
    )
    assert rendered == {}
    assert len(errors) == 1
    assert "outside" in errors[0]
