"""
The repos an org holds, and how each is stamped.

The plan is hardcoded for now: the org repos every Pandoscope org needs,
plus one code repo for the project.
A principal-supplied list of repos and their purposes replaces it later;
everything downstream reads only `Repo`, so that list plugs in here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

RUNNER = "ubuntu-latest"
STORES = ("session-memory", "decision-memory", "evidence-memory")
ORG_REPOS = ("meta", *STORES, "waybill")


@dataclass(frozen=True)
class Repo:
    """
    One repo of an org.

    ``answers`` are the copier answers it is stamped with; empty means the
    repo is created but not stamped. ``direct_pushes`` marks a repo that
    takes pushes to main by design, so the reconcilers leave it out of
    branch protection and the merge bot.
    """

    name: str
    purpose: str
    answers: dict[str, str] = field(default_factory=dict)
    private: bool = True
    direct_pushes: bool = False

    @property
    def stamped(self) -> bool:
        """Return whether the repo is stamped from the template."""
        return bool(self.answers)


def default_plan(
    org: str, *, project: str, description: str, approvers: list[str]
) -> list[Repo]:
    """
    Return the hardcoded repo plan for ``org``.

    ``project`` names the code repo and ``description`` is its purpose.
    ``approvers`` are the human logins whose Approve satisfies the merge gate.
    Raises ValueError when ``approvers`` is empty
    or ``project`` collides with an org repo name.
    """
    if not approvers:
        msg = f"approvers must name at least one human login for org={org!r}"
        raise ValueError(msg)
    if project in ORG_REPOS:
        msg = f"project={project!r} collides with an org repo name in {ORG_REPOS}"
        raise ValueError(msg)
    gate = {
        "agentic_merge_approval_gate": "true",
        "agentic_merge_approvers": ",".join(approvers),
    }
    return [
        Repo(
            "meta",
            f"Org-level docs, reconciler config and session environment for {org}.",
            _project_answers(org, "Meta", "meta", "docs", gate),
        ),
        Repo(
            project,
            description,
            _project_answers(org, project, project, "code", gate, description),
        ),
        Repo(
            "session-memory",
            "Session store: append-only thread events and transcript exports.",
            _store_answers("session-memory", {}),
            direct_pushes=True,
        ),
        Repo(
            "decision-memory",
            "Decision store: decision records and the preference set.",
            _store_answers("decision-memory", gate),
        ),
        Repo(
            "evidence-memory",
            "Evidence store: immutable detection records.",
            _store_answers("evidence-memory", gate),
        ),
        Repo(
            "waybill",
            "Orders that fire Routines: one file per order, one branch per order.",
            direct_pushes=True,
        ),
    ]


def _project_answers(
    org: str,
    name: str,
    slug: str,
    kind: str,
    gate: dict[str, str],
    description: str | None = None,
) -> dict[str, str]:
    return {
        "agentic_subtemplate": "template",
        "agentic_project_name": name,
        "agentic_project_slug": slug,
        "agentic_project_description": description or f"{name} for the {org} org.",
        "agentic_project_kind": kind,
        "agentic_repo_owner": org,
        "agentic_forge": "github",
        "agentic_precommit": "prek",
        "agentic_tracker_cli": "ghx",
        "agentic_actions_runner": RUNNER,
        **gate,
    }


def _store_answers(subtemplate: str, gate: dict[str, str]) -> dict[str, str]:
    return {
        "agentic_subtemplate": subtemplate,
        "agentic_actions_runner": RUNNER,
        **gate,
    }
