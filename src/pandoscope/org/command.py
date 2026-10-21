"""The ``pandoscope org`` commands: parsed arguments in, printed output out."""

from __future__ import annotations

import argparse
import contextlib
import getpass
import secrets as tokens
import shutil
import tempfile
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
    _check_shapes(args)
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
    browse: Callable[[str], object] = webbrowser.open,
    ask: Callable[[str], str] = getpass.getpass,
) -> int:
    """
    Create the org's release bot through the app-manifest flow; return 0.

    Opens the manifest page and, once the app exists, its install page in the
    principal's browser, reads the address GitHub redirected to from the
    terminal, and prints the client ID. The key goes to the org's secrets
    directory and is never printed.
    Raises FileExistsError before anything else when the secrets directory
    already holds a key, and what any step raises.
    """
    _check_shapes(args)
    # DECISION:IFACE — one app per org, named after it by default;
    # --name for an org that already chose another (ada-release-bot).
    name = args.name or f"{args.org}-release-bot"
    if not releasebot.APP_NAME.fullmatch(name):
        msg = f"app name={name!r} is not a GitHub App name (up to 34 letters, digits, ' ._-')"
        raise ValueError(msg)
    secrets = _secrets(args)
    key = secrets / releasebot.KEY_FILE
    # DECISION:SEC — the secrets directory is checked and locked before
    # GitHub creates anything, and stays locked until the key is kept: a
    # directory that cannot take the key must not leave an app behind.
    with releasebot.secrets_directory(secrets) as directory:
        if releasebot.key_in_use_at(directory):
            msg = f"{key} already holds the org's release-bot key; move it away to replace the app"
            raise FileExistsError(msg)
        conversion = _converted(args.org, name, key, run=run, browse=browse, ask=ask)
        try:
            releasebot.check(conversion, args.org, name)
            record = releasebot.store_at(directory, secrets, conversion, args.org)
        except BaseException as error:
            # The key exists only in the conversion: say where the app is, then fail.
            in_use = isinstance(error, FileExistsError)
            print(releasebot.lost_key_note(conversion, args.org, key, key_in_use=in_use))
            raise
    install = releasebot.install_url(record["slug"])
    print(f"Created {record['slug']} (app id {record['app_id']}).")
    print(f"Client ID: {record['client_id']}")
    print(f"Private key: {key}")
    print(f"Install it on {args.org}, all repositories: {install}")
    browse(install)
    return 0


def _converted(
    org: str,
    name: str,
    key: Path,
    *,
    run: forge.Run,
    browse: Callable[[str], object],
    ask: Callable[[str], str],
) -> dict[str, Any]:
    """Send the manifest through the browser, read the pasted redirect, return GitHub's conversion."""
    state = tokens.token_urlsafe(24)
    # DECISION:SEC — GitHub sends the browser back to the org's own apps
    # page and the principal pastes that address: no local port to squat,
    # no local server to flood.
    apps = releasebot.apps_url(org)
    app = releasebot.manifest(org, name, apps)
    sent = False
    try:
        page = releasebot.page_file(releasebot.form_page(org, app, state))
        try:
            print(f"Opening {page}: it sends the manifest of {name} to GitHub.")
            print(f'On GitHub, check that the page creates {name} for {org}, then confirm "Create GitHub App".')
            print(f"GitHub then opens {apps}?code=…&state=…: paste that address here (it is not shown).")
            print(f"If the browser lands anywhere else, do not paste: delete any new app at {apps} and run again.")
            browse(page.as_uri())
            sent = True
            code = _pasted_code(ask, org, state)
        finally:
            # Best effort: a stray file in the directory must not cost the code.
            with contextlib.suppress(OSError):
                page.unlink(missing_ok=True)
            shutil.rmtree(page.parent, ignore_errors=True)
        return releasebot.convert(code, run)
    except BaseException:
        if sent:
            # Whether GitHub created the app is unknown here: say where to look.
            print(releasebot.unconverted_note(org, name, key))
        raise


def _pasted_code(ask: Callable[[str], str], org: str, state: str, tries: int = 3) -> str:
    """Return the code from the redirect address the principal pastes; ask up to ``tries`` times."""
    apps = releasebot.apps_url(org)
    for _ in range(tries):
        code = releasebot.pasted_code(ask(f"Paste the address of {apps} as GitHub shows it: "), org, state)
        if code is not None:
            return code
        print(f"That is not the address GitHub redirected this flow to ({apps}?code=…&state=…).")
    msg = f"{tries} pasted addresses were not this flow's redirect to {apps}"
    raise ValueError(msg)


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


def _check_shapes(args: argparse.Namespace) -> None:
    """
    Refuse values that would leave their place in a path, URL or the sourced conf.

    Raises ValueError naming the argument.
    """
    if not releasebot.LOGIN.fullmatch(args.org):
        msg = f"org={args.org!r} is not a GitHub org name"
        raise ValueError(msg)
    checks = [
        ("release_bot_app", "--release-bot-app", releasebot.SLUG),
        ("release_bot_client_id", "--release-bot-client-id", releasebot.CLIENT_ID),
        ("board_url", "--board-url", releasebot.BOARD_URL),
    ]
    for attr, flag, shape in checks:
        value = getattr(args, attr, None)
        if value is not None and not shape.fullmatch(value):
            msg = f"{flag}={value!r} does not have the shape GitHub gives it"
            raise ValueError(msg)


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
        record = releasebot.recorded(_secrets(args), args.org)
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
