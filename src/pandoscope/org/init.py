"""Org init: create the planned repos, stamp them, then reconcile the org."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pandoscope.org.forge import Run, create_repo, existing_repos
from pandoscope.org.plan import Repo
from pandoscope.org.reconcile import Outcome
from pandoscope.org.seed import Stamp

StampRepo = Callable[[str, Repo, Path, Run, Stamp], bool]
Reconcile = Callable[[str, list[Repo]], list[Outcome]]


@dataclass(frozen=True)
class InitResult:
    """Per repo, what happened to it; per reconciler, what it reported."""

    repos: dict[str, list[str]]
    outcomes: list[Outcome]


def init_org(
    org: str,
    plan: list[Repo],
    workdir: Path,
    *,
    run: Run,
    stamp: Stamp,
    stamp_repo: StampRepo,
    reconcile: Reconcile,
    dry_run: bool = False,
) -> InitResult:
    """
    Bring ``org`` to ``plan``: create, stamp, reconcile, in that order.

    Every repo is stamped before the reconcile, because the reconcile
    protects main and the stamp is a direct push to it.
    Safe to re-run: existing repos and existing stamps are left alone.
    ``dry_run`` creates and stamps nothing; ``reconcile`` gets the same
    flag through its own binding.
    Returns what happened to each repo and what each reconciler reported.
    Raises what any step raises; a failed step stops the run.
    """
    present = existing_repos(org, run)
    report: dict[str, list[str]] = {}
    for repo in plan:
        if repo.name in present:
            report[repo.name] = ["exists"]
        elif dry_run:
            report[repo.name] = ["would create"]
        else:
            create_repo(org, repo, run)
            report[repo.name] = ["created"]
    if not dry_run:
        for repo in plan:
            if stamp_repo(org, repo, workdir, run, stamp):
                report[repo.name].append("stamped")
    return InitResult(report, reconcile(org, plan))
