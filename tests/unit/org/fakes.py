from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


class FakeRun:
    """
    Record every command; answer from a table keyed by the command's prefix.

    A prefix in ``errors`` raises RuntimeError with its message instead,
    as `forge.run` does for a command that exits non-zero.
    """

    def __init__(
        self,
        answers: dict[tuple[str, ...], str] | None = None,
        errors: dict[tuple[str, ...], str] | None = None,
    ) -> None:
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []
        self.answers = answers or {}
        self.errors = errors or {}

    def __call__(self, cmd: Sequence[str], cwd: Path | None = None) -> str:
        self.calls.append((tuple(cmd), cwd))
        for prefix, message in self.errors.items():
            if tuple(cmd[: len(prefix)]) == prefix:
                raise RuntimeError(message)
        for prefix, out in self.answers.items():
            if tuple(cmd[: len(prefix)]) == prefix:
                return out
        if _repo_lookup(cmd):
            # Unless a table says otherwise, the fake forge is a new org.
            msg = f"command failed (exit 1): {' '.join(cmd)}\nstderr: Not Found (HTTP 404)"
            raise RuntimeError(msg)
        return ""

    def commands(self) -> list[tuple[str, ...]]:
        return [cmd for cmd, _ in self.calls]


def _repo_lookup(cmd: Sequence[str]) -> bool:
    """Whether ``cmd`` is repo sync's lookup of one repo, ``gh api repos/<owner>/<name>``."""
    return (
        tuple(cmd[:2]) == ("gh", "api")
        and len(cmd) > 2
        and cmd[2].startswith("repos/")
        and cmd[2].count("/") == 2
    )
