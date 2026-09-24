"""The reviewer's task: the pass file's prompt block, hydrated from order and clone."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pandoscope.reinset.receive import Order

PASS_DIR = Path("skills") / "original" / "thread-ledger" / "review"
_BLOCK = re.compile(r"^```text\n(?P<body>.*?)^```", re.MULTILINE | re.DOTALL)
_PLACEHOLDER = re.compile(r"<([a-z][a-z-]*)>")


class ReviewError(Exception):
    """An order whose pass file cannot become a task."""


def pull_refs(clone: Path, number: int, base: str | None = None) -> tuple[str, str]:
    """
    Return the base branch and head sha of pull request ``number``, read from ``clone``.

    The base is ``base`` when the order names it, else the remote's
    default branch. Fetches that branch and ``pull/<n>/head``. Raises
    ReviewError when the clone is missing or a fetch fails.
    """
    if not (clone / ".git").exists():
        msg = f"no clone of the pull request's repository at {clone}"
        raise ReviewError(msg)
    # DECISION: git does not record a pull request's base; the forge
    # does. A branch built on the pull request looks like a stacked
    # base from the head, so no heuristic separates them (measured
    # 2026-09-24). The order names the base; without it, the default.
    ref = f"pull/{number}/head"
    try:
        base = base or _default_branch(clone)
        _git(
            clone,
            "fetch",
            "-q",
            "origin",
            f"+refs/heads/{base}:refs/remotes/origin/{base}",
        )
        _git(clone, "fetch", "-q", "origin", ref)
        head = _git(clone, "rev-parse", "FETCH_HEAD")
    except subprocess.CalledProcessError as error:
        msg = (
            f"cannot read {ref} with base {base!r} from {clone}: {error.stderr.strip()}"
        )
        raise ReviewError(msg) from error
    return base, head


def _default_branch(clone: Path) -> str:
    # A session clone carries no origin/HEAD; the remote names its default.
    symref = _git(clone, "ls-remote", "--symref", "origin", "HEAD").split()
    if symref[:1] != ["ref:"]:
        msg = f"the remote of {clone} names no default branch"
        raise ReviewError(msg)
    return symref[1].removeprefix("refs/heads/")


def hydrate(session_root: Path, order: Order) -> str:
    """
    Return the reviewer's task: the pass file's prompt block, every placeholder filled.

    Fills ``<repo>``, ``<n>``, ``<pass>``, ``<tier>``, ``<tickets>``
    from the order and ``<base>``, ``<head>`` from the clone of the
    pull request's repository under the session root. Raises
    ReviewError on a placeholder left unfilled.
    """
    assert order.pass_ and order.tier  # noqa: S101 — the schema requires both
    path = session_root / PASS_DIR / f"{order.pass_}.md"
    if not path.is_file():
        msg = f"no review pass file at {path}"
        raise ReviewError(msg)
    block = _BLOCK.search(path.read_text())
    if block is None:
        msg = f"{path} holds no fenced text block to use as the prompt"
        raise ReviewError(msg)
    base, head = pull_refs(
        session_root / order.repo.rsplit("/", 1)[-1], order.pull_request, order.base
    )
    values = {
        "repo": order.repo,
        "n": str(order.pull_request),
        "pass": order.pass_,
        "tier": order.tier,
        "base": base,
        "head": head,
        "tickets": ", ".join(order.tickets) or "none",
    }
    task = _PLACEHOLDER.sub(
        lambda m: values.get(m.group(1), m.group(0)), block.group("body")
    )
    left = sorted(set(_PLACEHOLDER.findall(task)))
    if left:
        msg = f"{path} leaves placeholders unfilled: " + ", ".join(
            f"<{p}>" for p in left
        )
        raise ReviewError(msg)
    return task


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(cwd), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
