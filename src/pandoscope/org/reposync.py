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
from pandoscope.org.reconcile import Outcome
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
    reconcile: Callable[[Repo], StepReport] | StepReport | None = None,
    check: Callable[[Repo], StepReport] | None = None,
    dry_run: bool = False,
) -> list[StepReport]:
    """
    Bring ``owner/repo`` to ``repo``, one step at a time; return one report per step.

    ``owner`` is an org or a user account.
    ``template_ref`` is any ref the template's git resolves: a tag, a branch or a commit.
    ``reconcile`` runs the reconcile step and reports it;
    a StepReport is reported as it is, for a step that cannot run (no meta checkout);
    None leaves the step out, for a caller that reconciles the org as a whole.
    ``check`` runs the check step last; None leaves it out.
    Under ``dry_run``, a repo that does not exist yet is neither reconciled nor checked.

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
    if isinstance(reconcile, StepReport):
        reports.append(reconcile)
    elif reconcile is not None:
        if present or not dry_run:
            reports.append(reconcile(repo))
        else:
            # Its reconcilers would find no repo and read that as converged.
            reports.append(
                StepReport("reconcile", "would reconcile", ["the repo does not exist yet"])
            )
    if check is not None:
        if present or not dry_run:
            reports.append(check(repo))
        else:
            reports.append(StepReport("check", "skipped", ["the repo does not exist yet"]))
    return reports


def reconcile_report(outcomes: list[Outcome]) -> StepReport:
    """
    Report what the reconcilers did as the "reconcile" step.

    The state is "converged" when every reconciler that ran exited 0,
    else MANUAL when every one that did not reported MANUAL lines only,
    else DRIFT.
    Each line names its reconciler.
    """
    lines: list[str] = []
    for outcome in outcomes:
        if outcome.code == 1 and not outcome.lines:
            lines.append(f"{outcome.name}: exit 1 with no DRIFT or MANUAL line")
        lines += [f"{outcome.name}: {line}" for line in outcome.lines]
    unconverged = [outcome for outcome in outcomes if outcome.code == 1]
    if not unconverged:
        return StepReport("reconcile", "converged", lines)
    if all(_manual_only(outcome) for outcome in unconverged):
        return StepReport("reconcile", "MANUAL", lines)
    return StepReport("reconcile", "DRIFT", lines)


def _manual_only(outcome: Outcome) -> bool:
    """Whether what keeps ``outcome`` from converging is only someone else's to do."""
    reported = [line.split()[0] for line in outcome.lines]
    return "MANUAL" in reported and "DRIFT" not in reported


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
