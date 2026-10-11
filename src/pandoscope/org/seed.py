"""Stamp a freshly created repo and push the stamp as its first commit on main."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pandoscope.org.forge import Run
from pandoscope.org.plan import Repo

ANSWERS_FILE = ".copier-answers.agentic.yml"
STAMP_MESSAGE = "chore: stamp agentic-engineering-template scaffold"


class Stamp(Protocol):
    """The signature of `pandoscope.stamp.stamp`."""

    def __call__(
        self,
        directory: str,
        data: dict[str, str] | None = None,
        *,
        defaults: bool = False,
        vcs_ref: str | None = None,
    ) -> None:
        """Render the scaffold into ``directory``."""


def stamp_repo(org: str, repo: Repo, workdir: Path, run: Run, stamp: Stamp) -> bool:
    """
    Clone ``org/repo`` into ``workdir``, stamp it, and push main.

    ``init_org`` calls it before the reconcile, for the reason its docstring gives.
    Returns True when the repo was stamped,
    False when it is unstamped by plan or already carries a stamp.
    Raises what ``run`` and ``stamp`` raise.
    """
    if not repo.stamped:
        return False
    checkout = workdir / repo.name
    run(["gh", "repo", "clone", f"{org}/{repo.name}", str(checkout)], None)
    if (checkout / ANSWERS_FILE).exists():
        return False
    run(["git", "checkout", "-B", "main"], checkout)
    stamp(str(checkout), repo.answers, defaults=True)
    run(["git", "add", "-A"], checkout)
    run(["git", "commit", "-m", STAMP_MESSAGE], checkout)
    run(["git", "push", "-u", "origin", "main"], checkout)
    return True
