"""Order name patterns: the name says what the order is (pandoscope#57)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# DECISION: one pattern per role, in this table and nowhere else.
# The review pattern is ruled (waybill decisions 98 to 100).
# The implementer pattern is the recommendation of pandoscope#57,
# not ruled: a different ruling changes its one line.
# Each Routine picks its orders by branch name,
# so the model tier stands as a part of its own in every pattern.
PATTERNS: dict[str, str] = {
    "reviewer": "review-<pass>-<model_tier>-<code><n>-<step>",
    "implementer": "implement-<model_tier>-<code><n>-<step>",
}
# The step counts from 1; a repeat run of a step takes b, c and so on.
STEP = re.compile(r"[1-9][0-9]*[b-z]?")
_SUBJECT = re.compile(r"^(?P<repo>[^#]+)#(?P<n>\d+)$")


def name_pattern(role: str) -> str | None:
    """Return the name pattern of ``role``'s orders, or None when it has none."""
    return PATTERNS.get(role)


def name_violations(
    data: Mapping[str, Any], shortcodes: Mapping[str, str]
) -> list[str]:
    """
    Return how the order's ``id`` departs from its role's name pattern.

    ``data`` must already validate against the order schema.
    ``shortcodes`` maps a repository to its shortcode,
    as the waybill's ``shortcodes.json`` does.
    Returns one violation that names the first part of the name that is off,
    or a ``subject`` violation when the subject's repository has no shortcode.
    Returns an empty list when the name fits,
    and when the role has no pattern.
    """
    pattern = name_pattern(data["role"])
    if pattern is None:
        # DECISION:FALLBACK: a role without a name pattern
        # (orchestrator, general, probe; pandoscope#57 leaves them alone).
        # Missing: the pattern to check the name against.
        # In its place: only the schema's check that the id equals the file name.
        # Told: `pandoscope order check` prints that the name is unchecked,
        # so the person who places the order sees it;
        # the session gets its role from the order as before.
        # Test: test_a_role_without_a_name_pattern_keeps_only_the_id_check
        # and test_order_check_tells_a_role_without_a_name_pattern.
        return []
    subject = _SUBJECT.match(data["subject"])
    assert subject is not None  # noqa: S101 — the schema pins the pattern
    code = shortcodes.get(subject["repo"])
    if code is None:
        return [
            f"subject: {subject['repo']!r} has no shortcode in shortcodes.json, "
            "and the order's name needs one"
        ]
    values = {
        "pass": data.get("pass"),
        "model_tier": data["model_tier"],
        "subject": f"{code}{subject['n']}",
    }
    name = str(data["id"])
    rest = name
    for token in pattern.split("-"):
        part, text = _part(token, values)
        if part == "step":
            if STEP.fullmatch(rest):
                return []
            value = "a number from 1, with b, c and so on for a repeat run"
        elif rest == text or rest.startswith(f"{text}-"):
            # A name that stops here is short of the parts after this one.
            rest = rest[len(text) + 1 :]
            continue
        else:
            value = repr(text)
        return [
            f"id: {name!r} is off the pattern {pattern} of a {data['role']} order: "
            f"the {part} part must be {value}, and the name reads {rest!r} there"
        ]
    return []


def _part(token: str, values: Mapping[str, Any]) -> tuple[str, str]:
    """Return the field a pattern token stands for, and the text it must read."""
    if token == "<step>":  # noqa: S105 — a pattern token, not a secret
        return "step", ""
    if token == "<code><n>":  # noqa: S105 — a pattern token
        return "subject", str(values["subject"])
    if token.startswith("<"):
        field = token.strip("<>")
        return field, str(values[field])
    # The literal word that opens the name stands for the role.
    return "role", token
