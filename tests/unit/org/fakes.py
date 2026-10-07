from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


class FakeRun:
    """Record every command; answer from a table keyed by the command's prefix."""

    def __init__(self, answers: dict[tuple[str, ...], str] | None = None) -> None:
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []
        self.answers = answers or {}

    def __call__(self, cmd: Sequence[str], cwd: Path | None = None) -> str:
        self.calls.append((tuple(cmd), cwd))
        for prefix, out in self.answers.items():
            if tuple(cmd[: len(prefix)]) == prefix:
                return out
        return ""

    def commands(self) -> list[tuple[str, ...]]:
        return [cmd for cmd, _ in self.calls]
