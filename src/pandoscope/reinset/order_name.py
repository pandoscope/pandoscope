"""Order name patterns: the name says what the order is (pandoscope#57)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# DECISION: one pattern per role, in this table and nowhere else.
# The review pattern is ruled (waybill decisions 98 to 100),
# and every name carries its pass (decision 109).
# Each Routine picks its orders by branch name,
# so the model tier stands as a part of its own in every pattern.
# DECISION: an underscore separates the parts, and a hyphen stands only
# inside a part (decision 155, question 34): the name alone tells the pass
# `prose-opus` from the pass `prose` on the tier `opus`, with no list of tiers.
SEPARATOR = "_"
PATTERNS: dict[str, str] = {
    "reviewer": "review_<pass>_<model_tier>_<code><n>_<step>",
    "implementer": "implement_<pass>_<model_tier>_<code><n>_<step>",
}
# The literal word that opens each pattern, and the role it belongs to.
ROLE_OF_WORD = {
    pattern.split(SEPARATOR, 1)[0]: role for role, pattern in PATTERNS.items()
}
# The separators of a pattern: an underscore outside a token's angle brackets,
# so `<model_tier>` stays one token.
_PATTERN_SEPARATOR = re.compile(rf"{SEPARATOR}(?![^<]*>)")
# The step counts from 1; a repeat run of a step takes b, c and so on.
STEP = re.compile(r"[1-9][0-9]*[b-z]?")
_SUBJECT = re.compile(r"^(?P<repo>[^#]+)#(?P<n>\d+)$")


def name_pattern(role: str) -> str:
    """Return the name pattern of ``role``'s orders; the schema lists these roles."""
    return PATTERNS[role]


def name_violations(
    data: Mapping[str, Any], shortcodes: Mapping[str, str]
) -> list[str]:
    """
    Return how the order's ``id`` departs from its role's name pattern.

    ``data`` must already validate against the order schema.
    ``shortcodes`` maps a repository to its shortcode,
    as the waybill's ``shortcodes.json`` does.
    Returns a ``subject`` violation when the subject's repository has no
    shortcode, whatever the role,
    a role part violation when the name begins with the word of another role,
    whatever the order's role,
    and otherwise one violation that names the first part of the name that is off.
    Returns an empty list when the name fits.
    """
    subject = _SUBJECT.match(data["subject"])
    assert subject is not None  # noqa: S101 — the schema pins the pattern
    code = shortcodes.get(subject["repo"])
    if code is None:
        return [
            f"subject: {subject['repo']!r} has no shortcode in shortcodes.json, "
            "and every order needs one"
        ]
    name = str(data["id"])
    word = name.split(SEPARATOR, 1)[0]
    owner = ROLE_OF_WORD.get(word)
    if owner is not None and owner != data["role"]:
        # A name that begins with a role's word reads as that role's order,
        # whatever role the order names (pandoscope#59, part D case 3).
        return [
            f"id: {name!r} begins with {word!r}, the role part of the name "
            f"of an order with the role {owner!r}, and the order's role is "
            f"{data['role']!r}"
        ]
    pattern = name_pattern(data["role"])
    values = {
        "pass": data["pass"],
        "model_tier": data["model_tier"],
        "subject": f"{code}{subject['n']}",
    }
    parts = name.split(SEPARATOR)
    tokens = _PATTERN_SEPARATOR.split(pattern)
    for at, token in enumerate(tokens):
        part, text = _part(token, values)
        # The name from this part on; an extra part, as the old `_r2`
        # (part D case 2), shows in the part it stands in.
        rest = SEPARATOR.join(parts[at:])
        if part == "step":
            if len(parts) == len(tokens) and STEP.fullmatch(rest):
                return []
            value = "a number from 1, with b, c and so on for a repeat run"
        elif at < len(parts) and parts[at] == text:
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
