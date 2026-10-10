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

from pandoscope.org.plan import Repo, _project_answers, _store_answers


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
    gate = {
        "agentic_merge_approval_gate": "true",
        "agentic_merge_approvers": ",".join(data["approvers"]),
    }
    return [_repo(org, entry, gate) for entry in data["repos"]]


def _repo(org: str, entry: dict[str, Any], gate: dict[str, str]) -> Repo:
    name = entry["name"]
    direct_pushes = bool(entry.get("direct_pushes", False))
    # A repo that takes direct pushes stays out of the merge gate,
    # so it gets no approval answers (as session-memory in default_plan).
    own_gate = {} if direct_pushes else gate
    if entry["kind"] == "store":
        answers = _store_answers(entry["store"], own_gate)
    else:
        answers = _project_answers(
            org,
            entry.get("title", name),
            name,
            entry["kind"],
            own_gate,
            entry["purpose"],
        )
    return Repo(name, entry["purpose"], answers, direct_pushes=direct_pushes)


def render_plan(org: str, approvers: list[str], plan: list[Repo]) -> str:
    """Return ``plan`` for ``org`` as the YAML ``read_plan`` reads."""
    raise NotImplementedError
