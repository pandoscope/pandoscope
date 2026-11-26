"""
`repo sync`: bring one repository to its repo entry.

The per-repo steps, in order: exists, first commit, reconcile, check.
`org init` and `org sync` call `repo_sync` for every entry,
and the wizards `repo init` and `org init` call it once they have an entry;
no other code performs these steps (#71).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pandoscope.org.forge import Run
from pandoscope.org.plan import Repo
from pandoscope.org.seed import Stamp


@dataclass(frozen=True)
class StepReport:
    """What one step found and did: the reported ``state`` word and its ``lines``."""

    step: str
    state: str
    lines: list[str] = field(default_factory=list)


def repo_sync(
    owner: str,
    repo: Repo,
    workdir: Path,
    *,
    run: Run,
    stamp: Stamp,
    template_ref: str,
    dry_run: bool = False,
) -> list[StepReport]:
    """
    Bring ``owner/repo`` to ``repo``, one step at a time; return one report per step.

    ``owner`` is an org or a user account.
    ``template_ref`` is any ref the template's git resolves: a tag, a branch or a commit.

    Each step checks state first and acts only when the state differs.
    ``dry_run`` reports every change and makes none.
    """
    raise NotImplementedError
