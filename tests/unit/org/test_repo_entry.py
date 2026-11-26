"""The repo-mode file: one repo entry with its owner, for a repository managed without an org file (#71)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.org.planfile import read_entry, read_plan

ENTRY = """\
owner: someone
approvers: [someone]
repo:
  name: lean
  kind: code
  purpose: A trial project.
"""


def entry_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "pandoscope.yml"
    path.write_text(text)
    return path


def test_a_repo_mode_file_names_its_owner_and_one_stamped_repo(tmp_path: Path) -> None:
    owner, repo = read_entry(entry_file(tmp_path, ENTRY))

    assert owner == "someone"
    assert repo.name == "lean"
    assert repo.purpose == "A trial project."
    assert repo.private
    assert repo.answers["agentic_repo_owner"] == "someone"
    assert repo.answers["agentic_merge_approvers"] == "someone"
    assert repo.answers["agentic_project_kind"] == "code"


def test_the_entry_is_the_same_as_in_an_org_file(tmp_path: Path) -> None:
    """An org that adopts the project moves the entry over unchanged."""
    org_file = tmp_path / "org.yml"
    org_file.write_text(
        "org: someone\napprovers: [someone]\nrepos:\n"
        "  - name: lean\n    kind: code\n    purpose: A trial project.\n"
    )
    _, repo = read_entry(entry_file(tmp_path, ENTRY))
    assert read_plan(org_file, "someone") == [repo]


@pytest.mark.parametrize(
    ("text", "named"),
    [
        (ENTRY.replace("owner: someone", 'owner: "x$(id)"'), "owner"),
        (ENTRY.replace("approvers: [someone]", 'approvers: ["a b"]'), "approver"),
        (ENTRY.replace("approvers: [someone]", "approvers: []"), "approvers"),
        (ENTRY.replace("name: lean", 'name: "x$(id)"'), "repo name"),
        (ENTRY.replace("kind: code", "kind: library"), "library"),
        ("owner: someone\napprovers: [someone]\n", "repo"),
        (
            "owner: someone\napprovers: [someone]\nrepos:\n"
            "  - {name: lean, kind: code, purpose: p}\n",
            "org file",
        ),
    ],
)
def test_an_invalid_repo_mode_file_is_refused_naming_the_value(
    tmp_path: Path, text: str, named: str
) -> None:
    with pytest.raises(ValueError, match=named):
        read_entry(entry_file(tmp_path, text))
