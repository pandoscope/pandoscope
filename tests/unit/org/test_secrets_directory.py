"""The secrets directory: walked, checked and locked; the record read with care."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from pandoscope.org.releasebot import KEY_FILE, RECORD_FILE, recorded, store

from .test_releasebot import CONVERSION


def in_thread(work: Callable[[], object], seconds: float) -> tuple[bool, list[BaseException]]:
    """Run ``work`` in a daemon thread; return whether it finished in time and what it raised."""
    raised: list[BaseException] = []

    def run() -> None:
        try:
            work()
        except BaseException as error:  # noqa: BLE001 - handed to the test
            raised.append(error)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(seconds)
    return not worker.is_alive(), raised


def test_a_secrets_path_through_a_symlink_in_a_writable_directory_is_refused(tmp_path: Path) -> None:
    shared = tmp_path / "w"
    shared.mkdir()
    shared.chmod(0o777)
    private = tmp_path / "p"
    private.mkdir(mode=0o700)
    (shared / "link").symlink_to(private)
    with pytest.raises(ValueError):
        store(shared / "link" / "s", CONVERSION, "o")
    assert list(private.iterdir()) == []


def test_a_secrets_path_with_dot_dot_is_refused(tmp_path: Path) -> None:
    checked = tmp_path / "p"
    checked.mkdir(mode=0o700)
    elsewhere = tmp_path / "a" / "inner"
    elsewhere.mkdir(parents=True)
    (checked / "s").symlink_to(elsewhere)
    with pytest.raises(ValueError, match=r"\.\."):
        store(checked / "s" / ".." / "org", CONVERSION, "o")
    assert list((tmp_path / "a").iterdir()) == [elsewhere]


def test_a_root_owned_symlink_on_the_way_is_followed() -> None:
    # /tmp is a root-owned symlink on macOS; the walk must still get through it.
    secrets = Path("/tmp") / f"pandoscope-test-{os.getpid()}-{threading.get_ident()}" / "s"
    try:
        store(secrets, CONVERSION, "o")
        assert (secrets / KEY_FILE).read_text() == CONVERSION["pem"]
    finally:
        shutil.rmtree(secrets.parent, ignore_errors=True)


def test_a_lock_held_elsewhere_ends_the_store_within_its_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pandoscope.org.releasebot.LOCK_WAIT", 0.3)
    secrets = tmp_path / "s"
    secrets.mkdir(mode=0o700)
    held = os.open(secrets, os.O_RDONLY)
    fcntl.flock(held, fcntl.LOCK_EX)
    try:
        finished, raised = in_thread(lambda: store(secrets, CONVERSION, "o"), 3)
    finally:
        fcntl.flock(held, fcntl.LOCK_UN)
        os.close(held)
    assert finished
    assert len(raised) == 1 and "another run" in str(raised[0])
    assert not (secrets / KEY_FILE).exists()


def test_a_writable_secrets_directory_is_refused_before_waiting_for_its_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pandoscope.org.releasebot.LOCK_WAIT", 10.0)
    secrets = tmp_path / "s"
    secrets.mkdir()
    secrets.chmod(0o777)
    held = os.open(secrets, os.O_RDONLY)
    fcntl.flock(held, fcntl.LOCK_EX)
    try:
        finished, raised = in_thread(lambda: store(secrets, CONVERSION, "o"), 2)
    finally:
        fcntl.flock(held, fcntl.LOCK_UN)
        os.close(held)
    assert finished
    assert len(raised) == 1 and "writable" in str(raised[0])


def test_a_stale_temp_copy_of_a_key_is_removed(tmp_path: Path) -> None:
    stale = tmp_path / ".pandoscope-release-bot-0123456789abcdef"
    stale.write_text("an old key\n")
    store(tmp_path, CONVERSION, "o")
    assert not stale.exists()


@pytest.mark.skipif(not hasattr(fcntl, "F_FULLFSYNC"), reason="F_FULLFSYNC is macOS only")
def test_the_key_is_flushed_to_the_drive_on_macos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flushed: list[int] = []
    real_fcntl = fcntl.fcntl

    def fcntl_spy(fd: int, cmd: int, *args: object) -> object:
        if cmd == fcntl.F_FULLFSYNC:
            flushed.append(fd)
        return real_fcntl(fd, cmd, *args)  # type: ignore[call-overload]

    monkeypatch.setattr(fcntl, "fcntl", fcntl_spy)
    store(tmp_path, CONVERSION, "o")
    assert len(flushed) >= 2


def test_a_symlinked_record_is_refused(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text('{"org": "o", "slug": "o-release-bot", "app_id": 4711, "client_id": "Iv23abc"}\n')
    secrets = tmp_path / "s"
    secrets.mkdir(mode=0o700)
    (secrets / RECORD_FILE).symlink_to(elsewhere)
    with pytest.raises(ValueError, match="record"):
        recorded(secrets, "o")


def test_a_fifo_record_is_refused_without_waiting(tmp_path: Path) -> None:
    secrets = tmp_path / "s"
    secrets.mkdir(mode=0o700)
    os.mkfifo(secrets / RECORD_FILE)
    finished, raised = in_thread(lambda: recorded(secrets, "o"), 2)
    if not finished:
        # Unblock the reader so the thread ends.
        os.close(os.open(secrets / RECORD_FILE, os.O_WRONLY | os.O_NONBLOCK))
    assert finished
    assert len(raised) == 1 and isinstance(raised[0], ValueError)


def test_an_oversized_record_is_refused(tmp_path: Path) -> None:
    record = {"org": "o", "slug": "o-release-bot", "app_id": 4711, "client_id": "Iv23abc", "pad": "x" * 8000}
    (tmp_path / RECORD_FILE).write_text(json.dumps(record))
    with pytest.raises(ValueError, match="record"):
        recorded(tmp_path, "o")


@pytest.mark.xfail(strict=True, reason="round 3 R2: the sweep takes any .pandoscope- file")
def test_the_sweep_takes_only_its_own_temp_files(tmp_path: Path) -> None:
    marker = tmp_path / ".pandoscope-compose"
    marker.write_text("a managed install\n")
    other = tmp_path / ".pandoscope-notes"
    other.write_text("notes\n")
    folder = tmp_path / ".pandoscope-dir"
    folder.mkdir()
    store(tmp_path, CONVERSION, "o")
    assert marker.exists() and other.exists() and folder.is_dir()


@pytest.mark.xfail(strict=True, reason="round 3 R3: a placeholder laid out just before the link loses the key")
def test_a_placeholder_laid_out_just_before_the_link_is_still_filled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_link = os.link

    def seed_then_link(src: str, dst: str, **kwargs: object) -> None:
        if dst == KEY_FILE:
            (tmp_path / KEY_FILE).write_text("")
        real_link(src, dst, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "link", seed_then_link)
    store(tmp_path, CONVERSION, "o")
    assert (tmp_path / KEY_FILE).read_text() == CONVERSION["pem"]


@pytest.mark.xfail(strict=True, reason="round 3: walk asks for the working directory even for an absolute path")
def test_an_absolute_secrets_path_works_from_a_deleted_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    store(tmp_path / "s", CONVERSION, "o")
    assert (tmp_path / "s" / KEY_FILE).read_text() == CONVERSION["pem"]


def test_a_users_own_symlink_on_the_way_is_refused(tmp_path: Path) -> None:
    private = tmp_path / "p"
    private.mkdir(mode=0o700)
    target = tmp_path / "t"
    target.mkdir(mode=0o700)
    (private / "link").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        store(private / "link" / "s", CONVERSION, "o")
    assert list(target.iterdir()) == []


def test_a_record_in_a_directory_others_can_write_is_refused(tmp_path: Path) -> None:
    store(tmp_path / "s", CONVERSION, "o")
    (tmp_path / "s").chmod(0o777)
    with pytest.raises(ValueError, match="writable"):
        recorded(tmp_path / "s", "o")
