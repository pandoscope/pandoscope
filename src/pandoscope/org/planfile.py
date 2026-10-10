"""
An org's repo plan as a file in its meta repo.

The file names the org, its approvers and one entry per repo;
``read_plan`` turns it into the ``Repo`` list every org phase reads,
``render_plan`` writes a plan back in the same format.
Format authority: ``read_plan``'s docstring.
"""

from __future__ import annotations

from pathlib import Path

from pandoscope.org.plan import Repo


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
    raise NotImplementedError


def render_plan(org: str, approvers: list[str], plan: list[Repo]) -> str:
    """Return ``plan`` for ``org`` as the YAML ``read_plan`` reads."""
    raise NotImplementedError
