"""The ``pandoscope org`` commands: parsed arguments in, printed output out."""

from __future__ import annotations

import argparse
import secrets as tokens
import tempfile
import webbrowser
from collections.abc import Callable
from pathlib import Path

from pandoscope.org import forge, reconcile, releasebot
from pandoscope.org.confs import Credentials
from pandoscope.org.init import init_org
from pandoscope.org.plan import Repo, default_plan
from pandoscope.org.planfile import read_plan, render_plan
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
    Without the release-bot flags it uses the app ``org release-bot``
    recorded in the org's secrets directory, if any.
    Without ``--board-url`` it finds or creates the org's project board,
    and the credentials point the add-to-project workflow at it.
    The repo plan comes from ``--plan``,
    else from ``--project``, ``--description`` and ``--approver``.
    Raises ValueError when ``--meta`` holds no reconcilers,
    when the release-bot flags come without each other,
    or when neither a plan file nor every plan flag is given,
    and what any step raises.
    """
    meta = Path(args.meta)
    if not (meta / "scripts" / "sync-gh-repo-settings.sh").exists():
        msg = f"--meta {meta} has no scripts/sync-gh-repo-settings.sh"
        raise ValueError(msg)
    release_bot = _release_bot(args)
    # Every check of the arguments runs before _board, which can create a board.
    plan = _plan(args)
    board_url = _board(args, run)
    creds = None
    if release_bot:
        app, client_id = release_bot
        creds = Credentials(app_slug=app, client_id=client_id, board_url=board_url)
    secrets = _secrets(args)

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


def run_org_release_bot(
    args: argparse.Namespace,
    *,
    run: forge.Run = forge.run,
    listen: Callable[[str], releasebot.Callback] = releasebot.listen,
    browse: Callable[[str], object] = webbrowser.open,
) -> int:
    """
    Create the org's release bot through the app-manifest flow; return 0.

    Opens the manifest page and, once the app exists, its install page in the
    principal's browser, and prints the client ID. The key goes to the org's
    secrets directory and is never printed.
    Raises FileExistsError before anything else when the secrets directory
    already holds a key, and what any step raises.
    """
    secrets = _secrets(args)
    key = secrets / releasebot.KEY_FILE
    if releasebot.key_in_use(secrets):
        msg = f"{key} already holds the org's release-bot key; move it away to replace the app"
        raise FileExistsError(msg)
    # DECISION:IFACE — one app per org, named after it by default;
    # --name for an org that already chose another (ada-release-bot).
    name = args.name or f"{args.org}-release-bot"
    state = tokens.token_urlsafe(24)
    callback = listen(state)
    app = releasebot.manifest(args.org, name, callback.url + "/callback")
    page = releasebot.page_file(releasebot.form_page(args.org, app, state))
    try:
        print(f"Opening {page} to send the manifest of {name} to GitHub.")
        print('Confirm "Create GitHub App" there; this command waits for GitHub.')
        browse(page.as_uri())
        code = callback.wait()
        conversion = releasebot.convert(code, run)
        releasebot.check(conversion, args.org, name)
        record = releasebot.store(secrets, conversion)
    finally:
        # The port stays taken until the code is converted and checked.
        callback.close()
        page.unlink(missing_ok=True)
        page.parent.rmdir()
    install = releasebot.install_url(record["slug"])
    print(f"Created {record['slug']} (app id {record['app_id']}).")
    print(f"Client ID: {record['client_id']}")
    print(f"Private key: {key}")
    print(f"Install it on {args.org}, all repositories: {install}")
    browse(install)
    return 0


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


def _secrets(args: argparse.Namespace) -> Path:
    """Return the org's secrets directory: ``--secrets``, else under ``--meta``."""
    if args.secrets:
        return Path(args.secrets)
    return Path(args.meta) / ".secrets" / "orgs" / args.org


def _release_bot(args: argparse.Namespace) -> tuple[str, str] | None:
    app, client_id = args.release_bot_app, args.release_bot_client_id
    if bool(app) != bool(client_id):
        msg = "--release-bot-app and --release-bot-client-id go together"
        raise ValueError(msg)
    if not app:
        # Without the flags, the app `org release-bot` created for this org.
        record = releasebot.recorded(_secrets(args))
        if record is None:
            return None
        return str(record["slug"]), str(record["client_id"])
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
