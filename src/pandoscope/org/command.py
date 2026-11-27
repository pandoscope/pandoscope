"""The ``pandoscope org`` commands: parsed arguments in, printed output out."""

from __future__ import annotations

import argparse
import tempfile
from collections.abc import Callable
from pathlib import Path

from pandoscope.org import forge, reconcile
from pandoscope.org.confs import Credentials
from pandoscope.org.init import init_org
from pandoscope.org.plan import Repo, default_plan
from pandoscope.org.checks import check_repo
from pandoscope.org.planfile import read_agent, read_entry, read_plan, render_plan
from pandoscope.org.reposync import StepReport, reconcile_report, repo_sync
from pandoscope.org.seed import Stamp
from pandoscope.stamp import stamp

# The states of a reconcile or check step that ran, as opposed to one skipped.
RAN = ("OK", "MISSING", "MANUAL", "converged", "DRIFT")


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
    The repo plan comes from ``--plan``,
    else from ``--project``, ``--description`` and ``--approver``.
    Raises ValueError when ``--meta`` holds no reconcilers,
    when the release-bot flags come without each other,
    or when neither a plan file nor every plan flag is given,
    and what any step raises.
    """
    meta = _meta(args)
    release_bot = _release_bot(args)
    # Every check of the arguments runs before _board, which can create a board.
    plan = _plan(args)
    board_url = _board(args, run)
    creds = _credentials(release_bot, board_url)
    secrets = _secrets(args, meta, args.org)

    def bound_reconcile(org: str, plan: list[Repo]) -> list[reconcile.Outcome]:
        return reconcile.reconcile(
            org, plan, meta, secrets, creds, dry_run=args.dry_run, exec_=exec_
        )

    with tempfile.TemporaryDirectory(prefix="pandoscope-org-") as scratch:
        workdir = Path(args.workdir or scratch)

        def bound_sync(repo: Repo) -> list[StepReport]:
            return repo_sync(
                args.org,
                repo,
                workdir,
                run=run,
                stamp=stamp_with,
                template_ref=args.template_ref,
                dry_run=args.dry_run,
            )

        result = init_org(
            args.org, plan, sync_repo=bound_sync, reconcile=bound_reconcile
        )
    for name, reports in result.repos.items():
        print(f"{args.org}/{name}: {'; '.join(_step(report) for report in reports)}")
    for outcome in result.outcomes:
        print(f"{outcome.name}: {_verdict(outcome)}")
        for line in outcome.lines:
            print(f"  {line}")
    return 1 if any(outcome.code == 1 for outcome in result.outcomes) else 0


def run_org_sync(
    args: argparse.Namespace,
    *,
    run: forge.Run = forge.run,
    exec_: reconcile.Exec = reconcile.run_script,
    stamp_with: Stamp = stamp,
) -> int:
    """
    Run ``org sync`` for parsed ``args`` and print what happened.

    The org file is ``--plan``, by default ``org.yml`` in the meta checkout.
    Returns 1 when any reconciler reported drift or a manual step,
    or a check reported MISSING, else 0.
    Raises ValueError for an invalid org file or one that names no agent,
    for a ``--meta`` without reconcilers, or a secrets dir that does not exist,
    all before any forge call; and what any step raises.
    """
    raise NotImplementedError


def run_repo_sync(
    args: argparse.Namespace,
    *,
    run: forge.Run = forge.run,
    exec_: reconcile.Exec = reconcile.run_script,
    stamp_with: Stamp = stamp,
) -> int:
    """
    Run ``repo sync`` for parsed ``args`` and print one line per step.

    With ``--meta``, the reconcile step runs meta's reconcilers
    narrowed to this repo; without it, the step is skipped.
    Returns 1 when a step reports MISSING or DRIFT, else 0: a MANUAL line names
    what someone else must do and does not fail the run.
    Raises ValueError for an invalid repo-mode file or one that names no agent,
    and, before any forge call, for a ``--meta`` that cannot narrow a run
    or a secrets dir that does not exist;
    and what any step raises.
    """
    path = Path(args.file)
    owner, repo = read_entry(path)
    agent = read_agent(path)
    if agent is None:
        # The init wizard asks for the agent; sync needs the field filled in.
        msg = f"{path} names no agent; repo sync needs agent: <login>"
        raise ValueError(msg)

    step = _narrowed_reconcile(args, owner, repo, exec_)
    with tempfile.TemporaryDirectory(prefix="pandoscope-repo-") as scratch:
        reports = repo_sync(
            owner,
            repo,
            Path(args.workdir or scratch),
            run=run,
            stamp=stamp_with,
            template_ref=args.template_ref,
            reconcile=step,
            check=lambda entry: check_repo(owner, entry, agent, run),
            dry_run=args.dry_run,
        )
    for report in reports:
        if report.step in ("reconcile", "check") and report.state in RAN:
            print(f"{owner}/{repo.name}: {report.step} {report.state}")
            for line in report.lines:
                print(f"  {line}")
        else:
            print(f"{owner}/{repo.name}: {_step(report)}")
    return 1 if any(report.state in ("MISSING", "DRIFT") for report in reports) else 0


def _narrowed_reconcile(
    args: argparse.Namespace, owner: str, repo: Repo, exec_: reconcile.Exec
) -> Callable[[Repo], StepReport] | StepReport:
    """
    Return repo sync's reconcile step for parsed ``args``: meta's reconcilers for ``repo`` only.

    Without ``--meta`` it is a report that the step was skipped.
    Raises ValueError, before anything runs, where ``reconcile.narrowing`` refuses.
    """
    if not args.meta:
        return StepReport("reconcile", "skipped", ["no meta checkout"])
    meta = _meta(args)
    creds = _credentials(_release_bot(args), args.board_url)
    secrets = _secrets(args, meta, owner)
    # DECISION:SCOPE — the confs come from this one entry:
    # a repo-mode file is the whole plan of what Pandoscope manages for its owner.
    reconcile.narrowing(owner, [repo], meta, secrets, repo.name)

    def step(entry: Repo) -> StepReport:
        outcomes = reconcile.reconcile(
            owner,
            [entry],
            meta,
            secrets,
            creds,
            dry_run=args.dry_run,
            exec_=exec_,
            only=entry.name,
        )
        return reconcile_report(outcomes)

    return step


def run_org_plan(args: argparse.Namespace) -> int:
    """Print the default repo plan for parsed ``args`` as a plan file; return 0."""
    plan = default_plan(
        args.org,
        project=args.project,
        description=args.description,
        approvers=args.approver,
    )
    print(render_plan(args.org, args.approver, plan), end="")
    return 0


def _plan(args: argparse.Namespace) -> list[Repo]:
    """Return the plan from ``--plan``, else the default plan from the flags."""
    if args.plan:
        return read_plan(Path(args.plan), args.org)
    if not (args.project and args.description and args.approver):
        msg = (
            "give --plan, or --project, --description and --approver;"
            f" got project={args.project!r} description={args.description!r}"
            f" approver={args.approver!r}"
        )
        raise ValueError(msg)
    return default_plan(
        args.org,
        project=args.project,
        description=args.description,
        approvers=args.approver,
    )


def _meta(args: argparse.Namespace) -> Path:
    """Return ``--meta``; raises ValueError when it holds no reconcilers."""
    meta = Path(args.meta)
    if not (meta / "scripts" / "sync-gh-repo-settings.sh").exists():
        msg = f"--meta {meta} has no scripts/sync-gh-repo-settings.sh"
        raise ValueError(msg)
    return meta


def _secrets(args: argparse.Namespace, meta: Path, owner: str) -> Path:
    """Return ``--secrets``, by default the owner's dir in the meta checkout."""
    return Path(args.secrets) if args.secrets else meta / ".secrets" / "orgs" / owner


def _credentials(
    release_bot: tuple[str, str] | None, board_url: str | None
) -> Credentials | None:
    """Return the credential facts, or None without a release-bot app."""
    if release_bot is None:
        return None
    app, client_id = release_bot
    return Credentials(app_slug=app, client_id=client_id, board_url=board_url)


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


def _step(report: StepReport) -> str:
    detail = f" ({', '.join(report.lines)})" if report.lines else ""
    return f"{report.step} {report.state}{detail}"


def _verdict(outcome: reconcile.Outcome) -> str:
    if outcome.code is None:
        return "skipped"
    if outcome.code == 0:
        return "converged"
    return f"exit {outcome.code}"
