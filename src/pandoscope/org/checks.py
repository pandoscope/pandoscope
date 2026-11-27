"""
`repo sync`'s check step: one line per point, starting OK, MISSING or MANUAL (#71).

A MISSING line fails the run; a MANUAL line names what only someone else can do.
"""

from __future__ import annotations

from pandoscope.org.forge import Run
from pandoscope.org.plan import Repo
from pandoscope.org.reposync import StepReport


def check_repo(owner: str, repo: Repo, agent: str | None, run: Run) -> StepReport:
    """Check ``owner/repo`` against its entry and report it as the "check" step."""
    raise NotImplementedError
