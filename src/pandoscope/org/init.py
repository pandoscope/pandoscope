"""Org init: org sync without the checks, for an org whose file names no agent yet."""

from __future__ import annotations

from pandoscope.org.orgsync import OrgResult, Reconcile, SyncRepo, sync_org
from pandoscope.org.plan import Repo


def init_org(
    org: str,
    plan: list[Repo],
    *,
    sync_repo: SyncRepo,
    reconcile: Reconcile,
) -> OrgResult:
    """
    Bring ``org`` to ``plan``: repo sync for every entry, then the org's reconcile.

    What only a first setup does (creating the board, seeding the secrets dir)
    is in the bindings ``run_org_init`` passes;
    the order of the steps is ``sync_org``'s.
    Returns what happened to each repo and what each reconciler reported.
    Raises what any step raises; a failed step stops the run.
    """
    return sync_org(org, plan, sync_repo=sync_repo, reconcile=reconcile)
