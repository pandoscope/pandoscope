"""Org init: bring every planned repo to its entry with repo sync, then reconcile the org."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pandoscope.org.plan import Repo
from pandoscope.org.reconcile import Outcome
from pandoscope.org.reposync import StepReport

SyncRepo = Callable[[Repo], list[StepReport]]
Reconcile = Callable[[str, list[Repo]], list[Outcome]]


@dataclass(frozen=True)
class InitResult:
    """Per repo, what repo sync reported; per reconciler, what it reported."""

    repos: dict[str, list[StepReport]]
    outcomes: list[Outcome]


def init_org(
    org: str,
    plan: list[Repo],
    *,
    sync_repo: SyncRepo,
    reconcile: Reconcile,
) -> InitResult:
    """
    Bring ``org`` to ``plan``: repo sync for every entry, then the org's reconcile.

    Every repo is synced before the reconcile,
    because the reconcile protects main and the stamp is a direct push to it.
    ``sync_repo`` and ``reconcile`` carry ``--dry-run`` through their own bindings.
    Returns what happened to each repo and what each reconciler reported.
    Raises what any step raises; a failed step stops the run.
    """
    # DECISION:SCOPE — no per-repo step is implemented here (#71):
    # creating and stamping a repo is repo sync's, and org init only calls it.
    report = {repo.name: sync_repo(repo) for repo in plan}
    return InitResult(report, reconcile(org, plan))
