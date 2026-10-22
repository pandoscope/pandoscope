"""
A directory only the current user can change, reached and used through file descriptors.

`walk` opens a directory one component at a time from ``/``, never following
a symlink but a root-owned one in a directory only root can change, and checks
every directory on the way. `check_private`, `lock`, `full_sync` and
`read_small` work on the descriptor it returns, so nothing is looked up by
path again once the directory is checked.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import stat
import time
from pathlib import Path

# A chain of root-owned symlinks longer than this is refused, like the kernel's ELOOP.
_MAX_LINKS = 8


def walk(path: Path, *, create: bool) -> int:
    """
    Open the directory ``path`` and return its descriptor; the caller closes it.

    Every directory above it must belong to the user or root and be
    writable by no one else unless sticky. With ``create``, missing
    directories are made with mode 0700; without, a missing one raises
    FileNotFoundError.
    Raises ValueError for a ``..`` in ``path``, a symlink that is not
    root's own in a root-only directory, a symlink or non-directory as the
    last component, or a directory above that fails its check.
    """
    # DECISION:SEC — the path is walked as the kernel walks it, one
    # component at a time through descriptors: a check of its realpath
    # would skip the directories that hold its symlinks, and `..` would be
    # resolved differently by the check and by the open.
    given = path if path.is_absolute() else Path(os.getcwd()) / path
    if ".." in given.parts:
        msg = f"secrets path {path} contains '..'"
        raise ValueError(msg)
    pending = [part for part in given.parts[1:] if part not in ("", ".")]
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    where = Path("/")
    links = 0
    try:
        _check_parent(os.fstat(fd), where)
        while pending:
            name = pending.pop(0)
            last = not pending
            if name == "..":
                # Only a root-owned symlink's target gets here.
                fd = _step(fd, "..")
                where = where.parent
                _check_parent(os.fstat(fd), where)
                continue
            created = False
            info = _lstat_at(fd, name)
            if info is None:
                if not create:
                    raise FileNotFoundError(errno.ENOENT, "no such directory", str(where / name))
                with contextlib.suppress(FileExistsError):
                    os.mkdir(name, 0o700, dir_fd=fd)
                    created = True
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                if last:
                    msg = f"secrets directory {where / name} is a symlink"
                    raise ValueError(msg)
                _check_trusted_link(info, os.fstat(fd), where / name)
                links += 1
                if links > _MAX_LINKS:
                    msg = f"secrets path {path} passes more than {_MAX_LINKS} symlinks"
                    raise ValueError(msg)
                target = os.readlink(name, dir_fd=fd)
                parts = [part for part in Path(target).parts if part not in ("", ".")]
                if target.startswith("/"):
                    root = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
                    os.close(fd)
                    fd = root
                    where = Path("/")
                    parts = parts[1:]
                pending = [*parts, *pending]
                continue
            if not stat.S_ISDIR(info.st_mode):
                msg = f"secrets path {where / name} is not a directory"
                raise ValueError(msg)
            fd = _step(fd, name)
            where = where / name
            if created:
                os.fchmod(fd, 0o700)
            if not last:
                _check_parent(os.fstat(fd), where)
    except BaseException:
        os.close(fd)
        raise
    return fd


def check_private(fd: int, path: Path) -> None:
    """
    Make sure the open directory ``fd`` (at ``path``) is the user's own and writable by no one else.

    Raises ValueError naming what fails: whoever can write it can swap
    the files placed in it.
    """
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        msg = f"secrets path {path} is not a directory"
        raise ValueError(msg)
    if info.st_uid != os.getuid():
        msg = f"secrets directory {path} belongs to uid {info.st_uid}, not to you"
        raise ValueError(msg)
    if info.st_mode & 0o022:
        msg = f"secrets directory {path} is writable by group or others"
        raise ValueError(msg)


def lock(fd: int, path: Path, wait: float) -> None:
    """
    Take an exclusive lock on the open directory ``fd``, waiting up to ``wait`` seconds.

    Raises ValueError when another run still holds it then.
    """
    deadline = time.monotonic() + wait
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if time.monotonic() >= deadline:
                msg = f"another run holds {path}; run again once it has finished"
                raise ValueError(msg) from None
            time.sleep(0.05)
        else:
            return


def full_sync(fd: int) -> None:
    """Flush ``fd`` to the drive itself: on macOS, fsync stops at the drive's cache."""
    os.fsync(fd)
    if hasattr(fcntl, "F_FULLFSYNC"):
        # Some filesystems refuse it; fsync above is what they offer.
        with contextlib.suppress(OSError):
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)


def read_small(directory: int, name: str, limit: int, what: str) -> bytes | None:
    """
    Return the content of ``name`` in the open ``directory``, or None when it is missing.

    Raises ValueError, naming ``what``, when it is a symlink, not a regular
    file, someone else's, or larger than ``limit`` bytes.
    """
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        fd = os.open(name, flags, dir_fd=directory)
    except FileNotFoundError:
        return None
    except OSError as error:
        if error.errno == errno.ELOOP:
            msg = f"{what} is a symlink"
            raise ValueError(msg) from None
        raise
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            msg = f"{what} is not a regular file"
            raise ValueError(msg)
        if info.st_uid != os.getuid():
            msg = f"{what} belongs to uid {info.st_uid}, not to you"
            raise ValueError(msg)
        data = os.read(fd, limit + 1)
        if info.st_size > limit or len(data) > limit:
            msg = f"{what} is larger than {limit} bytes"
            raise ValueError(msg)
        return data
    finally:
        os.close(fd)


def _step(fd: int, name: str) -> int:
    """Open the directory ``name`` below ``fd`` without following a symlink, then close ``fd``."""
    opened = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
    os.close(fd)
    return opened


def _lstat_at(fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _check_parent(info: os.stat_result, directory: Path) -> None:
    """A directory above the secrets: the user's or root's, and writable by no one else unless sticky."""
    if info.st_uid not in (os.getuid(), 0):
        msg = f"{directory} belongs to uid {info.st_uid}, neither you nor root"
        raise ValueError(msg)
    if info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
        msg = f"{directory} is writable by group or others"
        raise ValueError(msg)


def _check_trusted_link(link: os.stat_result, holder: os.stat_result, path: Path) -> None:
    """A symlink on the way must be root's own, in a directory only root can change."""
    if link.st_uid != 0 or holder.st_uid != 0 or holder.st_mode & 0o022:
        msg = f"{path} is a symlink only root may place on the secrets path"
        raise ValueError(msg)
