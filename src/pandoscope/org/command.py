"""The ``pandoscope org init`` command: parsed arguments in, a printed report out."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from pandoscope.org import forge, reconcile
from pandoscope.org.confs import Credentials
from pandoscope.org.init import init_org
from pandoscope.org.plan import Repo, default_plan
from pandoscope.org.seed import Stamp, stamp_repo
from pandoscope.stamp import stamp


def run_org_init(
    args: argparse.Namespace,
    *,
    run: forge.Run = forge.run,
    exec_: reconcile.Exec = reconcile.run_script,
    stamp_with: Stamp = stamp,
) -> int:
    """
    Run ``org init`` for parsed ``args`` and print what happened.

    Returns 0 when every reconciler converged, 1 when any reported drift
    or a manual step.
    Without ``--board-url`` it finds or creates the org's project board,
    and the credentials point the add-to-project workflow at it.
    Raises ValueError when ``--meta`` holds no reconcilers or the
    release-bot flags come without each other, and what any step raises.
    """
    meta = Path(args.meta)
    if not (meta / "scripts" / "sync-gh-repo-settings.sh").exists():
        msg = f"--meta {meta} has no scripts/sync-gh-repo-settings.sh"
        raise ValueError(msg)
    release_bot = _release_bot(args)
    board_url = _board(args, run)
    creds = None
    if release_bot:
        app, client_id = release_bot
        creds = Credentials(app_slug=app, client_id=client_id, board_url=board_url)
    secrets = (
        Path(args.secrets) if args.secrets else meta / ".secrets" / "orgs" / args.org
    )
    plan = default_plan(
        args.org,
        project=args.project,
        description=args.description,
        approvers=args.approver,
    )

    def bound_reconcile(org: str, plan: list[Repo]) -> list[reconcile.Outcome]:
        return reconcile.reconcile(
            org, plan, meta, secrets, creds, dry_run=args.dry_run, exec_=exec_
        )

    with tempfile.TemporaryDirectory(prefix="pandoscope-org-") as scratch:
        result = init_org(
            args.org,
            plan,
            Path(args.workdir or scratch),
            run=run,
            stamp=stamp_with,
            stamp_repo=stamp_repo,
            reconcile=bound_reconcile,
            dry_run=args.dry_run,
        )
    for name, events in result.repos.items():
        print(f"{args.org}/{name}: {', '.join(events)}")
    for outcome in result.outcomes:
        print(f"{outcome.name}: {_verdict(outcome)}")
        for line in outcome.lines:
            print(f"  {line}")
    return 1 if any(outcome.code == 1 for outcome in result.outcomes) else 0


def _release_bot(args: argparse.Namespace) -> tuple[str, str] | None:
    app, client_id = args.release_bot_app, args.release_bot_client_id
    if bool(app) != bool(client_id):
        msg = "--release-bot-app and --release-bot-client-id go together"
        raise ValueError(msg)
    if not app:
        return None
    return app, client_id


def _board(args: argparse.Namespace, run: forge.Run) -> str | None:
    """Return the board URL the principal passed, else the org's own board's."""
    if args.board_url:
        return str(args.board_url)
    url, event = forge.ensure_board(args.org, run, dry_run=args.dry_run)
    if url:
        print(f"board: {event} {url}")
    else:
        print(f"board: {event}")
    return url


def _verdict(outcome: reconcile.Outcome) -> str:
    if outcome.code is None:
        return "skipped"
    if outcome.code == 0:
        return "converged"
    return f"exit {outcome.code}"
