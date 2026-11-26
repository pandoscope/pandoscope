"""Stamp a freshly created repo and push the stamp as its first commit on main."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import yaml

from pandoscope.org.forge import Run
from pandoscope.org.plan import Repo
from pandoscope.stamp import TEMPLATE_URL

ANSWERS_FILE = ".copier-answers.agentic.yml"
STAMP_MESSAGE = "chore: stamp agentic-engineering-template scaffold"
# The push takes gh's credential, whatever git protocol gh is set to (#53).
GH_CREDENTIAL = ("-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential")


class Stamp(Protocol):
    """The signature of `pandoscope.stamp.stamp`."""

    def __call__(
        self,
        directory: str,
        data: dict[str, str] | None = None,
        *,
        defaults: bool = False,
        vcs_ref: str | None = None,
    ) -> None:
        """Render the scaffold into ``directory``."""


def stamp_repo(org: str, repo: Repo, workdir: Path, run: Run, stamp: Stamp) -> bool:
    """
    Clone ``org/repo`` into ``workdir``, stamp it, and push main.

    ``init_org`` calls it before the reconcile, for the reason its docstring gives.
    Returns True when the repo was stamped,
    False when it is unstamped by plan or already carries a stamp.
    Raises what ``run`` and ``stamp`` raise.
    """
    if not repo.stamped:
        return False
    checkout = workdir / repo.name
    run(["gh", "repo", "clone", f"{org}/{repo.name}", str(checkout)], None)
    if (checkout / ANSWERS_FILE).exists():
        return False
    run(["git", "checkout", "-B", "main"], checkout)
    stamp(str(checkout), repo.answers, defaults=True)
    run(["git", "add", "-A"], checkout)
    run(["git", "commit", "-m", STAMP_MESSAGE], checkout)
    run(["git", "push", "-u", "origin", "main"], checkout)
    return True


def stamp_first_commit(
    owner: str,
    repo: Repo,
    workdir: Path,
    run: Run,
    stamp: Stamp,
    template_ref: str,
) -> None:
    """
    Stamp ``repo`` at ``template_ref`` and push the stamp as ``owner/repo``'s first commit on main.

    The stamp is made in a new directory under ``workdir``, prepared with
    ``git init -b main``, because the template's stamp tasks need a git work tree.
    The commit message names the template ref, the commit it resolved to,
    and every stamp input.
    The push goes over HTTPS with gh's credential, whatever git protocol gh is set to.
    Raises ValueError when the directory exists already
    or the stamp records no template commit, and what ``run`` and ``stamp`` raise.
    """
    checkout = workdir / repo.name
    if checkout.exists():
        msg = f"stamp directory {checkout} exists already; remove it or pass another workdir"
        raise ValueError(msg)
    run(["git", "init", "-b", "main", str(checkout)], None)
    stamp(str(checkout), repo.answers, defaults=True, vcs_ref=template_ref)
    answers = yaml.safe_load((checkout / ANSWERS_FILE).read_text()) or {}
    resolved = answers.get("_commit")
    if not resolved:
        msg = f"the stamp of {owner}/{repo.name} records no _commit in {ANSWERS_FILE}"
        raise ValueError(msg)
    inputs = "\n".join(f"  {key}: {value}" for key, value in sorted(repo.answers.items()))
    message = (
        f"{STAMP_MESSAGE}\n\n"
        f"Template: {TEMPLATE_URL} at {template_ref} ({resolved})\n"
        f"Inputs:\n{inputs}\n"
    )
    run(["git", "add", "-A"], checkout)
    run(["git", "commit", "-m", message], checkout)
    url = f"https://github.com/{owner}/{repo.name}.git"
    run(["git", *GH_CREDENTIAL, "push", url, "main"], checkout)
