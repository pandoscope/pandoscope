"""
`org sync`: repo sync for every entry of the org file, then the org-wide reconcile.

`org init` is the same run without the check,
and only it creates the board and seeds the secrets dir (#71).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pandoscope.org.plan import Repo
from pandoscope.org.reconcile import Outcome
from pandoscope.org.reposync import StepReport

SyncRepo = Callable[[Repo], list[StepReport]]
Reconcile = Callable[[str, list[Repo]], list[Outcome]]
Check = Callable[[Repo], StepReport]


@dataclass(frozen=True)
class OrgResult:
    """Per repo, what repo sync reported; per reconciler, its outcome; per repo, its check."""

    repos: dict[str, list[StepReport]]
    outcomes: list[Outcome]
    checks: dict[str, StepReport] = field(default_factory=dict)


def sync_org(
    org: str,
    plan: list[Repo],
    *,
    sync_repo: SyncRepo,
    reconcile: Reconcile,
    check: Check | None = None,
) -> OrgResult:
    """
    Bring ``org`` to ``plan``: repo sync for every entry, the org's reconcile, then the checks.

    Every repo is synced before the reconcile,
    because the reconcile protects main and the stamp is a direct push to it;
    the check runs last, so it sees what the reconcile placed.
    ``check`` None leaves the checks out.
    ``sync_repo``, ``reconcile`` and ``check`` carry ``--dry-run`` through their own bindings.
    Raises what any step raises; a failed step stops the run.
    """
    raise NotImplementedError
