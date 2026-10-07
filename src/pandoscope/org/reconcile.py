"""
Seed an org's repos by running meta's reconcilers against it.

Each reconciler is a ``scripts/sync-gh-*.sh`` in a meta checkout.
It reads its conf from a ``SYNC_*_CONF`` env var
and its org from that conf's ``ORG=`` line
(interface authority: each script's header comment).
Exit 0 means converged, 1 means DRIFT or MANUAL lines remain,
anything else is a usage or conf error.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pandoscope.org.confs import (
    Credentials,
    credentials_conf,
    retarget,
    retarget_excepts,
)
from pandoscope.org.plan import Repo

Exec = Callable[[list[str], dict[str, str]], tuple[int, str]]
REPORTED = ("DRIFT", "MANUAL", "FIXED")


@dataclass(frozen=True)
class Outcome:
    """
    What one reconciler did.

    ``code`` is its exit status, None when it was skipped.
    ``lines`` are its DRIFT, MANUAL and FIXED lines, or the reason it was skipped.
    """

    name: str
    code: int | None
    lines: list[str]


def run_script(cmd: list[str], env: dict[str, str]) -> tuple[int, str]:
    """Run ``cmd`` with ``env`` over the process environment; return code and output."""
    done = subprocess.run(  # noqa: S603 - commands are built here, not from input
        cmd,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, done.stdout + done.stderr


def reconcile(
    org: str,
    plan: list[Repo],
    meta: Path,
    secrets: Path,
    creds: Credentials | None,
    *,
    dry_run: bool,
    exec_: Exec = run_script,
) -> list[Outcome]:
    """
    Run meta's reconcilers against ``org`` in dependency order.

    Settings and rulesets first;
    then credentials, which place the BOT_MERGE_ENABLED switch;
    then collaborators, which read it.
    Generated confs and every script's state live under ``secrets``,
    the org's gitignored secrets directory.
    A fresh ``secrets`` directory is seeded first,
    which lays out the placeholder files for the secret material.
    ``creds`` None skips credentials: the release-bot app does not exist yet.
    Returns one outcome per reconciler.
    Raises RuntimeError naming the script and its output
    on an exit other than 0 or 1,
    and ValueError when a meta conf cannot be retargeted.
    """
    scripts = meta / "scripts"
    confs = secrets / "confs"
    seed_credentials = not secrets.exists()
    confs.mkdir(parents=True, exist_ok=True)
    direct = [repo.name for repo in plan if repo.direct_pushes]

    def conf(name: str, text: str) -> str:
        path = confs / name
        path.write_text(text)
        return str(path)

    def meta_conf(name: str) -> str:
        return retarget((scripts / name).read_text(), org)

    def call(name: str, script: str, env: dict[str, str], *flags: str) -> Outcome:
        cmd = ["bash", str(scripts / script), *flags]
        code, out = exec_(cmd, env)
        if code not in (0, 1):
            msg = f"{script} for org={org!r} failed (exit {code}): {out.strip()}"
            raise RuntimeError(msg)
        lines = [line for line in out.splitlines() if line.startswith(REPORTED)]
        return Outcome(name, code, lines)

    mode = ["--dry-run"] if dry_run else []
    outcomes = [
        call(
            "settings",
            "sync-gh-repo-settings.sh",
            {
                "SYNC_SETTINGS_CONF": conf(
                    "repo-settings.conf", meta_conf("repo-settings.conf")
                ),
                "SYNC_SETTINGS_STATE_DIR": str(secrets / "state" / "repo-settings"),
            },
            *mode,
        ),
        call(
            "rulesets",
            "sync-gh-repo-rulesets.sh",
            {
                "SYNC_RULESETS_CONF": conf(
                    "repo-rulesets.conf",
                    retarget_excepts(meta_conf("repo-rulesets.conf"), direct),
                ),
                "SYNC_RULESETS_STATE_DIR": str(secrets / "state" / "rulesets"),
            },
            *mode,
        ),
    ]
    if creds is None:
        outcomes.append(
            Outcome(
                "credentials",
                None,
                ["skipped: create the org's release-bot GitHub App, then re-run"],
            )
        )
    else:
        env = {
            "SYNC_CREDENTIALS_CONF": conf(
                "actions-credentials.conf", credentials_conf(org, plan, creds)
            ),
            "SYNC_CREDENTIALS_SECRETS_DIR": str(secrets),
        }
        if seed_credentials:
            call("credentials-seed", "sync-gh-actions-credentials.sh", env, "--seed")
        outcomes.append(
            call("credentials", "sync-gh-actions-credentials.sh", env, *mode)
        )
    outcomes.append(
        call(
            "collaborators",
            "sync-gh-repo-collaborators.sh",
            {
                "SYNC_COLLABORATORS_CONF": conf(
                    "repo-collaborators.conf", meta_conf("repo-collaborators.conf")
                )
            },
            *mode,
        )
    )
    return outcomes
