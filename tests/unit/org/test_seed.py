from __future__ import annotations

from pathlib import Path

from pandoscope.org.plan import Repo
from pandoscope.org.seed import ANSWERS_FILE, STAMP_MESSAGE, stamp_repo

from .fakes import FakeRun

META = Repo("meta", "Org docs.", {"agentic_subtemplate": "template"})


class FakeStamp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str], bool]] = []

    def __call__(
        self,
        directory: str,
        data: dict[str, str] | None = None,
        *,
        defaults: bool = False,
        vcs_ref: str | None = None,
    ) -> None:
        self.calls.append((directory, dict(data or {}), defaults))
        (Path(directory) / ANSWERS_FILE).write_text("_commit: v1\n")


def test_stamp_clones_stamps_commits_and_pushes_main(tmp_path: Path) -> None:
    fake, stamp = FakeRun(), FakeStamp()
    checkout = tmp_path / "meta"
    checkout.mkdir()  # gh repo clone would create it
    assert stamp_repo("o", META, tmp_path, fake, stamp) is True
    assert fake.commands() == [
        ("gh", "repo", "clone", "o/meta", str(checkout)),
        ("git", "checkout", "-B", "main"),
        ("git", "add", "-A"),
        ("git", "commit", "-m", STAMP_MESSAGE),
        ("git", "push", "-u", "origin", "main"),
    ]
    assert stamp.calls == [(str(checkout), META.answers, True)]


def test_git_commands_run_in_the_checkout(tmp_path: Path) -> None:
    fake = FakeRun()
    (tmp_path / "meta").mkdir()
    stamp_repo("o", META, tmp_path, fake, FakeStamp())
    assert [cwd for _, cwd in fake.calls[1:]] == [tmp_path / "meta"] * 4


def test_already_stamped_repo_is_left_alone(tmp_path: Path) -> None:
    fake, stamp = FakeRun(), FakeStamp()
    checkout = tmp_path / "meta"
    checkout.mkdir()
    (checkout / ANSWERS_FILE).write_text("_commit: v1\n")
    assert stamp_repo("o", META, tmp_path, fake, stamp) is False
    assert fake.commands() == [("gh", "repo", "clone", "o/meta", str(checkout))]
    assert stamp.calls == []


def test_unstamped_repo_is_not_cloned(tmp_path: Path) -> None:
    fake, stamp = FakeRun(), FakeStamp()
    assert stamp_repo("o", Repo("waybill", "Orders."), tmp_path, fake, stamp) is False
    assert fake.calls == []
    assert stamp.calls == []
