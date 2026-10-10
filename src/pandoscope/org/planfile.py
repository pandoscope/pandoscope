"""
An org's repo plan as a file in its meta repo.

The file names the org, its approvers and one entry per repo;
``read_plan`` turns it into the ``Repo`` list every org phase reads,
``render_plan`` writes a plan back in the same format.
Format authority: ``read_plan``'s docstring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pandoscope.org.plan import STORES, Repo, _project_answers, _store_answers

KINDS = ("code", "docs", "store", "plain")


def read_plan(path: Path, org: str) -> list[Repo]:
    """
    Return the repo plan the YAML file at ``path`` declares for ``org``.

    The file holds ``org``, ``approvers`` (human logins) and ``repos``,
    a list of entries with ``name``, ``purpose`` and ``kind``
    (``code``, ``docs``, ``store`` or ``plain``),
    ``store`` (the store subtemplate, for ``kind: store`` only),
    and optionally ``title`` (the stamped project name, default the name),
    ``private`` (default true) and ``direct_pushes`` (default false).
    Raises ValueError naming the offending value when the file does not
    hold a valid plan for ``org``.
    """
    data = yaml.safe_load(path.read_text())
    if data["org"] != org:
        msg = f"plan file {path} is for org={data['org']!r}, not org={org!r}"
        raise ValueError(msg)
    names = [entry["name"] for entry in data["repos"]]
    twins = sorted({name for name in names if names.count(name) > 1})
    if twins:
        msg = f"plan file {path} names repos more than once: {twins}"
        raise ValueError(msg)
    gate = {
        "agentic_merge_approval_gate": "true",
        "agentic_merge_approvers": ",".join(data["approvers"]),
    }
    return [_repo(org, entry, gate) for entry in data["repos"]]


def _repo(org: str, entry: dict[str, Any], gate: dict[str, str]) -> Repo:
    name = entry["name"]
    kind = entry["kind"]
    if kind not in KINDS:
        msg = f"repo={name!r} has kind={kind!r}; expected one of {KINDS}"
        raise ValueError(msg)
    if kind == "store" and entry.get("store") not in STORES:
        msg = (
            f"repo={name!r} of kind 'store' has store={entry.get('store')!r};"
            f" expected one of {STORES}"
        )
        raise ValueError(msg)
    direct_pushes = bool(entry.get("direct_pushes", False))
    # A repo that takes direct pushes stays out of the merge gate,
    # so it gets no approval answers (as session-memory in default_plan).
    own_gate = {} if direct_pushes else gate
    if kind == "plain":
        answers: dict[str, str] = {}
    elif kind == "store":
        answers = _store_answers(entry["store"], own_gate)
    else:
        answers = _project_answers(
            org,
            entry.get("title", name),
            name,
            kind,
            own_gate,
            entry["purpose"],
        )
    return Repo(
        name,
        entry["purpose"],
        answers,
        private=bool(entry.get("private", True)),
        direct_pushes=direct_pushes,
    )


def render_plan(org: str, approvers: list[str], plan: list[Repo]) -> str:
    """Return ``plan`` for ``org`` as the YAML ``read_plan`` reads."""
    raise NotImplementedError
