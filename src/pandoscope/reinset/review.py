"""The reviewer's task: the pass file rendered as a template from order and clone."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import jinja2
import jinja2.meta

from pandoscope.reinset.receive import Order

PASS_DIR = Path("skills") / "original" / "thread-ledger" / "review"
PROSE_CHECK = Path("skills") / "original" / "writing-prose" / "check.sh"


class ReviewError(Exception):
    """An order whose pass file cannot become a task."""


def pull_refs(clone: Path, number: int, base: str | None = None) -> tuple[str, str]:
    """
    Return the base branch and head sha of pull request ``number``, read from ``clone``.

    The base is ``base`` when the order names it,
    else the remote's default branch.
    Fetches that branch and ``pull/<n>/head``.
    Raises ReviewError when the clone is missing or a fetch fails.
    """
    if not (clone / ".git").exists():
        msg = f"no clone of the pull request's repository at {clone}"
        raise ReviewError(msg)
    # DECISION: the forge records a pull request's base; git does not.
    # Seen from the head, a branch built on the pull request
    # and a stacked base look the same,
    # so no heuristic tells them apart (measured 2026-09-24).
    # The order names the base.
    # An order without one gets the remote's default branch.
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


def findings_contract(schema: dict[str, Any], indent: str = "") -> str:
    """Render a findings JSON schema as a Markdown field list (skills#225)."""
    lines = []
    for key, prop in schema.get("properties", {}).items():
        kind = (
            " or ".join(f"`{v}`" for v in prop["enum"])
            if "enum" in prop
            else prop.get("type", "value")
        )
        line = f"{indent}- `{key}` ({kind}): {prop.get('description', '')}"
        items = prop.get("items", {})
        if items.get("properties"):
            lines.append(line + ". Each item:")
            lines.append(findings_contract(items, indent + "  "))
        else:
            lines.append(line)
    return "\n".join(lines)


def _surface(path: str) -> str:
    """The writing-prose surface of a changed file."""
    name = Path(path).name
    if not name.endswith(".md"):
        return "comment"
    if name == "SKILL.md":
        return "skill"
    if name in {"CLAUDE.md", "AGENTS.md"}:
        return "primed"
    return "markdown"


def prose_candidates(check: Path, clone: Path, base: str, head: str) -> str:
    """
    Return the F and H hits of the writing-prose ``check`` on the changed files.

    Runs the check once per file the pull request adds or changes,
    on the file at ``head`` in ``clone``,
    and returns the hits on lines the pull request adds,
    or ``none`` when there are none.
    Raises ReviewError when the check is missing or fails to run.
    """
    if not check.is_file():
        msg = f"no prose check at {check}"
        raise ReviewError(msg)
    changed = _git(
        clone, "diff", "-z", "--name-only", "--diff-filter=d", f"origin/{base}...{head}"
    )
    hits = []
    for path in filter(None, changed.split("\0")):
        # The prefix keeps a file named `-` from reading as stdin.
        run = subprocess.run(  # noqa: S603
            ["bash", str(check), _surface(path), f"./{path}"],  # noqa: S607
            cwd=clone,
            capture_output=True,
            text=True,
            check=False,
        )
        # Exit 1 means F hits; anything else past 0 is a check that did not run.
        if run.returncode not in (0, 1):
            msg = f"{check} failed on {path}: {run.stderr.strip()}"
            raise ReviewError(msg)
        added = _added_lines(clone, base, head, path)
        for line in run.stdout.splitlines():
            hit = re.match(r"\./(.+?):(\d+): [FH] ", line)
            if hit and int(hit[2]) in added:
                hits.append(line.removeprefix("./"))
    return "\n".join(hits) or "none"


def _added_lines(clone: Path, base: str, head: str, path: str) -> set[int]:
    """The line numbers at ``head`` that the pull request adds to ``path``."""
    diff = _git(clone, "diff", "-U0", f"origin/{base}...{head}", "--", path)
    added: set[int] = set()
    for start, count in re.findall(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", diff, re.M):
        first = int(start)
        added.update(range(first, first + int(count or 1)))
    return added


def _check_origin(clone: Path, repo: str) -> None:
    """Raise ReviewError unless the clone's origin is the forge repository ``repo``."""
    try:
        url = _git(clone, "config", "--get", "remote.origin.url")
    except subprocess.CalledProcessError:
        url = ""
    # Raw config, not `remote get-url`: an insteadOf rewrite is transport.
    path = url.rstrip("/").removesuffix(".git").replace(":", "/")
    if not path.lower().endswith("/" + repo.lower()):
        msg = f"{clone} clones {url or 'no origin'}, not {repo}"
        raise ReviewError(msg)


def hydrate(session_root: Path, order: Order) -> str:
    """
    Return the reviewer's task: the whole pass file, rendered.

    Renders ``repo``, ``n``, ``pass``, ``model_tier`` and ``tickets`` from the order,
    and ``base`` and ``head`` from the clone of the pull request's repository
    under the session root.
    Switches that clone to the review ``branch`` at the head.
    Renders ``findings_contract`` from the findings schema beside the pass file,
    and ``candidates``, when the pass file uses it,
    from the writing-prose check over the changed files (skills#220).
    Raises ReviewError when the pass file, the clone or a ref is missing,
    when the clone belongs to another repository,
    when the switch fails,
    and when the template does not render, as on an undefined variable.
    """
    assert order.pass_ and order.model_tier  # noqa: S101 — the schema requires both
    path = session_root / PASS_DIR / f"{order.pass_}.md"
    if not path.is_file():
        msg = f"no review pass file at {path}"
        raise ReviewError(msg)
    clone = session_root / order.repo.rsplit("/", 1)[-1]
    if clone.is_dir():
        _check_origin(clone, order.repo)
    base, head = pull_refs(clone, order.pull_request, order.base)
    # The reviewer runs no git steps (skills#224).
    # The files on disk are the head,
    # on the branch that the driver publishes at Stop.
    branch = f"claude/review-{order.pass_}-{order.model_tier}-pr{order.pull_request}"
    try:
        _git(clone, "switch", "-q", "-C", branch, head)
    except subprocess.CalledProcessError as error:
        msg = f"cannot switch {clone} to {branch} at {head}: {error.stderr.strip()}"
        raise ReviewError(msg) from error
    values = {
        "repo": order.repo,
        "n": str(order.pull_request),
        "pass": order.pass_,
        "model_tier": order.model_tier,
        "base": base,
        "head": head,
        "tickets": ", ".join(order.tickets) or "none",
        "branch": branch,
    }
    schema = session_root / PASS_DIR / "findings.schema.json"
    if schema.is_file():
        values["findings_contract"] = findings_contract(json.loads(schema.read_text()))
    # DECISION: the pass file is a Jinja template.
    # Markup in angle brackets stays text,
    # and StrictUndefined keeps a misspelled variable an error
    # (pandoscope#31 review, F002).
    env = jinja2.Environment(  # noqa: S701 — the task is Markdown, not HTML
        undefined=jinja2.StrictUndefined, keep_trailing_newline=True
    )
    try:
        template = env.parse(path.read_text())
        # DECISION: the composer runs the prose check, not the reviewer.
        # The review policy denies the reviewer every execution,
        # and a check run before the session pins the candidates in the task
        # (skills#220, option A).
        if "candidates" in jinja2.meta.find_undeclared_variables(template):
            values["candidates"] = prose_candidates(
                session_root / PROSE_CHECK, clone, base, head
            )
        task = env.from_string(path.read_text()).render(values)
    except jinja2.TemplateError as error:
        msg = f"{path} does not render: {error}"
        raise ReviewError(msg) from error
    return task


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(cwd), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
