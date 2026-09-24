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


def pull_refs(clone: Path, number: int) -> tuple[str, str]:
    """
    Return the base branch and head sha of pull request ``number``, read from ``clone``.

    Fetches ``pull/<n>/head`` and every branch of ``origin``. The base
    is the branch the head sits closest above. Raises ReviewError when
    the clone is missing, the fetch fails or the base is ambiguous.
    """
    if not (clone / ".git").exists():
        msg = f"no clone of the pull request's repository at {clone}"
        raise ReviewError(msg)
    ref = f"pull/{number}/head"
    try:
        _git(clone, "fetch", "-q", "origin", "+refs/heads/*:refs/remotes/origin/*")
        _git(clone, "fetch", "-q", "origin", ref)
        head = _git(clone, "rev-parse", "FETCH_HEAD")
        bases = _nearest_branches(clone, head)
    except subprocess.CalledProcessError as error:
        msg = f"cannot read {ref} from {clone}: {error.stderr.strip()}"
        raise ReviewError(msg) from error
    if len(bases) != 1:
        found = ", ".join(bases) or "none"
        msg = f"the base of {ref} in {clone} is not one branch: {found}"
        raise ReviewError(msg)
    return bases[0], head


def _nearest_branches(clone: Path, head: str) -> list[str]:
    # DECISION: the base is the branch whose merge base with the head
    # leaves the fewest head commits above it. Git does not record a
    # pull request's base; the forge does. The nearest branch equals it
    # for a stacked pull request and for one on a main that moved on. A
    # tie goes to the default branch (a merged branch ties main), else
    # it stays a tie, and the caller reports it: never a guess.
    distance: dict[str, int] = {}
    listing = _git(
        clone, "for-each-ref", "--format=%(refname:lstrip=3)", "refs/remotes/origin/"
    )
    for branch in listing.split():
        if branch == "HEAD":
            continue
        tip = f"refs/remotes/origin/{branch}"
        if _git(clone, "rev-parse", tip) == head:
            continue
        fork = _git(clone, "merge-base", tip, head)
        distance[branch] = int(_git(clone, "rev-list", "--count", f"{fork}..{head}"))
    if not distance:
        return []
    nearest = min(distance.values())
    bases = sorted(b for b, d in distance.items() if d == nearest)
    if len(bases) == 1:
        return bases
    # A session clone carries no origin/HEAD; the remote names its default.
    symref = _git(clone, "ls-remote", "--symref", "origin", "HEAD").split()
    default = symref[1].removeprefix("refs/heads/") if symref[:1] == ["ref:"] else ""
    return [default] if default in bases else bases


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
        session_root / order.repo.rsplit("/", 1)[-1], order.pull_request
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
