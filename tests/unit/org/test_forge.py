from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pandoscope.org.forge import create_repo, ensure_board, existing_repos, run
from pandoscope.org.plan import Repo

from .fakes import FakeRun


def test_existing_repos_lists_the_org_once() -> None:
    fake = FakeRun({("gh", "repo", "list"): "meta\nwaybill\n"})
    assert existing_repos("somnus-app", fake) == {"meta", "waybill"}
    assert fake.commands() == [
        (
            "gh",
            "repo",
            "list",
            "somnus-app",
            "--limit",
            "1000",
            "--json",
            "name",
            "--jq",
            ".[].name",
        )
    ]


def test_existing_repos_of_an_empty_org_is_empty() -> None:
    assert existing_repos("o", FakeRun()) == set()


def test_create_stamped_repo_is_private_and_empty() -> None:
    fake = FakeRun()
    create_repo(
        "o", Repo("meta", "Org docs.", {"agentic_subtemplate": "template"}), fake
    )
    assert fake.commands() == [
        ("gh", "repo", "create", "o/meta", "--private", "--description", "Org docs.")
    ]


def test_create_unstamped_repo_gets_a_readme_so_main_exists() -> None:
    fake = FakeRun()
    create_repo("o", Repo("waybill", "Orders."), fake)
    assert fake.commands()[0][-1] == "--add-readme"


def test_create_public_repo() -> None:
    fake = FakeRun()
    create_repo("o", Repo("site", "Site.", private=False), fake)
    assert "--public" in fake.commands()[0]


def test_run_returns_stdout() -> None:
    assert run(["printf", "hi"]) == "hi"


def test_run_failure_names_command_cwd_and_stderr(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError) as error:
        run(["sh", "-c", "echo boom >&2; exit 3"], tmp_path)
    message = str(error.value)
    assert "exit 3" in message
    assert "boom" in message
    assert str(tmp_path) in message
    assert isinstance(error.value.__cause__, subprocess.CalledProcessError)


BOARD = "https://github.com/orgs/o/projects/1"
OTHER = "https://github.com/orgs/o/projects/2"
VARIABLES = ("gh", "api", "orgs/o/actions/variables")
PROJECTS = ("gh", "project", "list")
CREATE = ("gh", "project", "create")


def calls(fake: FakeRun) -> list[tuple[str, ...]]:
    return [cmd[:3] for cmd in fake.commands()]


def test_ensure_board_keeps_the_board_the_org_variable_records() -> None:
    fake = FakeRun({VARIABLES: f"{BOARD}\n"})
    assert ensure_board("o", fake, dry_run=False) == (BOARD, "recorded")
    assert calls(fake) == [VARIABLES]


def test_ensure_board_adopts_the_orgs_only_open_project() -> None:
    fake = FakeRun({PROJECTS: f"{BOARD}\tRoadmap\n"})
    assert ensure_board("o", fake, dry_run=False) == (BOARD, "adopted")
    assert CREATE not in calls(fake)


def test_ensure_board_creates_one_titled_after_the_org_when_it_has_none() -> None:
    fake = FakeRun({CREATE: f"{BOARD}\n"})
    assert ensure_board("o", fake, dry_run=False) == (BOARD, "created")
    create = next(cmd for cmd in fake.commands() if cmd[:3] == CREATE)
    assert create[3:7] == ("--owner", "o", "--title", "o")


def test_ensure_board_dry_run_creates_nothing() -> None:
    fake = FakeRun()
    assert ensure_board("o", fake, dry_run=True) == (None, "would create")
    assert CREATE not in calls(fake)


def test_ensure_board_refuses_to_guess_between_open_projects() -> None:
    fake = FakeRun({PROJECTS: f"{BOARD}\tRoadmap\n{OTHER}\tBugs\n"})
    with pytest.raises(ValueError, match="--board-url") as error:
        ensure_board("o", fake, dry_run=True)
    assert BOARD in str(error.value)
    assert OTHER in str(error.value)
    assert CREATE not in calls(fake)
