"""
`repo sync`: bring one repository to its repo entry.

The per-repo steps, in order: exists, first commit, reconcile, check.
`org init` and `org sync` call `repo_sync` for every entry,
and the wizards `repo init` and `org init` call it once they have an entry;
no other code performs these steps (#71).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pandoscope.org import forge
from pandoscope.org.forge import Run
from pandoscope.org.plan import Repo
from pandoscope.org.seed import Stamp, stamp_first_commit


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
    reconcile: Callable[[Repo], StepReport] | None = None,
    check: Callable[[Repo], StepReport] | None = None,
    dry_run: bool = False,
) -> list[StepReport]:
    """
    Bring ``owner/repo`` to ``repo``, one step at a time; return one report per step.

    ``owner`` is an org or a user account.
    ``template_ref`` is any ref the template's git resolves: a tag, a branch or a commit.
    ``reconcile`` runs the reconcile step and reports it;
    None leaves the step out, for a caller that reconciles the org as a whole.
    ``check`` runs the check step last; None leaves it out.
    The check is skipped under ``dry_run`` for a repo that does not exist yet.

    Each step checks state first and acts only when the state differs.
    ``dry_run`` reports every change and makes none.
    Raises what ``run`` and ``stamp`` raise; a failed step stops the run.
    """
    present = forge.repo_present(owner, repo.name, run)
    if present:
        exists = StepReport("exists", "exists")
    elif dry_run:
        exists = StepReport("exists", "would create")
    else:
        forge.create_repo(owner, repo, run)
        exists = StepReport("exists", "created")
    reports = [
        exists,
        _first_commit(
            owner, repo, workdir, run, stamp, template_ref, present=present, dry_run=dry_run
        ),
    ]
    if reconcile is not None:
        reports.append(reconcile(repo))
    if check is not None:
        if present or not dry_run:
            reports.append(check(repo))
        else:
            reports.append(StepReport("check", "skipped", ["the repo does not exist yet"]))
    return reports


def _first_commit(
    owner: str,
    repo: Repo,
    workdir: Path,
    run: Run,
    stamp: Stamp,
    template_ref: str,
    *,
    present: bool,
    dry_run: bool,
) -> StepReport:
    """
    Make the stamp main's first commit, unless main has commits already.

    A repository with commits but no main is the principal's to sort out:
    stamping it would put an unrelated history beside its own.
    """
    if not repo.stamped:
        return StepReport("first commit", "not stamped", ["a plain entry carries no stamp"])
    names = forge.branches(owner, repo.name, run) if present else []
    if "main" in names:
        return StepReport("first commit", "present")
    if names:
        return StepReport(
            "first commit",
            "MANUAL",
            [f"{owner}/{repo.name} has commits on {', '.join(names)} but no main; not stamped"],
        )
    if dry_run:
        return StepReport("first commit", "would stamp", [f"at {template_ref}"])
    stamp_first_commit(owner, repo, workdir, run, stamp, template_ref)
    return StepReport("first commit", "stamped", [f"at {template_ref}"])
