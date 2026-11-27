"""
`repo sync`'s check step: one line per point, starting OK, MISSING or MANUAL (#71).

A MISSING line fails the run; a MANUAL line names what only someone else can do.
"""

from __future__ import annotations

from pandoscope.org.forge import Run
from pandoscope.org.plan import Repo
from pandoscope.org.reposync import StepReport


# The rulesets meta's repo-rulesets.conf places; a repo that takes direct pushes
# carries only the first, as the conf's `except:` scopes say.
RULESETS = ("verified-signatures", "protect-main", "require-ci-ok")
DIRECT_PUSH_RULESETS = ("verified-signatures",)
PUSH = ("write", "maintain", "admin")
# What the forge answers for rulesets on a private repo under a plan without them.
PLAN_REFUSAL = "Upgrade to GitHub Pro"


def check_repo(owner: str, repo: Repo, agent: str | None, run: Run) -> StepReport:
    """
    Check ``owner/repo`` against its entry and report it as the "check" step.

    The points: the visibility the entry declares, main as the default branch,
    the rulesets meta places, and push access for ``agent``.
    The step's state is MISSING when any line is, else MANUAL when any line is, else OK.
    Raises what ``run`` raises, except the plan's refusal of rulesets,
    which is a MANUAL line: only the owner can change the plan.
    """
    full = f"{owner}/{repo.name}"
    lines: list[str] = []
    meta = run(["gh", "api", f"repos/{full}", "--jq", '"\\(.visibility) \\(.default_branch)"'], None)
    visibility, branch = meta.split()
    want = "private" if repo.private else "public"
    lines.append(_line(visibility == want, f"{full} is {visibility}", f"the entry says {want}"))
    lines.append(
        _line(branch == "main", f"{full}'s default branch is {branch}", "it should be main")
    )
    lines.extend(_rulesets(full, repo, run))
    if agent is None:
        lines.append(f"MISSING {full}: no agent named; add agent: <login> to the file")
    else:
        permission = run(
            ["gh", "api", f"repos/{full}/collaborators/{agent}/permission", "--jq", ".permission"],
            None,
        ).strip()
        lines.append(
            _line(permission in PUSH, f"{agent} has {permission} on {full}", "it needs write")
        )
    for state in ("MISSING", "MANUAL"):
        if any(line.startswith(state) for line in lines):
            return StepReport("check", state, lines)
    return StepReport("check", "OK", lines)


def _rulesets(full: str, repo: Repo, run: Run) -> list[str]:
    try:
        out = run(["gh", "api", f"repos/{full}/rulesets", "--jq", ".[].name"], None)
    except RuntimeError as error:
        if PLAN_REFUSAL not in str(error):
            raise
        return [
            f"MANUAL {full}: the forge's plan holds no rulesets on a private repo;"
            " the merge bot and the collaborator ceiling stand in for them"
        ]
    present = set(out.split())
    wanted = DIRECT_PUSH_RULESETS if repo.direct_pushes else RULESETS
    return [_line(name in present, f"{full} has ruleset {name}", "it is not there") for name in wanted]


def _line(ok: bool, fact: str, gap: str) -> str:
    return f"OK {fact}" if ok else f"MISSING {fact}: {gap}"
