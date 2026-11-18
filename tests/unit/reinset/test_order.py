from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from pandoscope.reinset.order import ShortcodeError, load_shortcodes, validate_order

SHORTCODES = {"pandoscope/pandoscope": "pando", "pandoscope/skills": "skills"}
NAME = "review-spec-fidelity-opus-pando26-1"
VALID = {
    "id": NAME,
    "role": "reviewer",
    "pass": "spec-fidelity",
    "model_tier": "opus",
    "subject": "pandoscope/pandoscope#26",
    "checkouts": {"pandoscope/skills": "claude/sk195-review-driver"},
    "tickets": ["pandoscope/skills#195"],
}
IMPLEMENTER_NAME = "implement-opus-pando57-1"
IMPLEMENTER = {
    "id": IMPLEMENTER_NAME,
    "role": "implementer",
    "model_tier": "opus",
    "subject": "pandoscope/pandoscope#57",
    "tickets": [],
}


def check(order: Mapping[str, object], name: str = NAME) -> list[str]:
    return validate_order(order, name, SHORTCODES)


def test_a_valid_review_order_has_no_violations() -> None:
    assert check(VALID) == []


def test_an_order_naming_an_issue_passes_and_so_does_one_naming_a_pull_request() -> (
    None
):
    # The forge numbers issues and pull requests in one sequence (decision 106),
    # so the one field `subject` names either.
    assert check(IMPLEMENTER, IMPLEMENTER_NAME) == []
    fix_round = {**IMPLEMENTER, "id": "implement-opus-pando58-2"}
    fix_round["subject"] = "pandoscope/pandoscope#58"
    assert check(fix_round, "implement-opus-pando58-2") == []


def test_result_is_an_optional_field() -> None:
    order = {
        **VALID,
        "result": "pandoscope/pandoscope@claude/review-spec-fidelity-opus-pr26",
    }
    assert check(order) == []


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"id": "other"}, "id"),  # must equal the file name
        ({"role": "auditor"}, "role"),
        ({"model_tier": "Opus"}, "model_tier"),  # the model tier is lowercase
        ({"pass": "Spec Fidelity"}, "pass"),
        ({"subject": "26"}, "subject"),
        ({"subject": "pandoscope/pandoscope!26"}, "subject"),
        ({"checkouts": {"skills": "main"}}, "checkouts"),  # key is owner/repo
        ({"checkouts": {"pandoscope/skills": "a ref"}}, "checkouts"),  # no spaces
        ({"checkouts": ["pandoscope/skills"]}, "checkouts"),
        ({"tickets": ["195"]}, "tickets"),
        ({"tickets": "pandoscope/skills#195"}, "tickets"),
        ({"pull_request": "pandoscope/pandoscope#26"}, "pull_request"),  # gone
    ],
)
def test_each_violation_names_its_field(change: dict[str, object], field: str) -> None:
    violations = check({**VALID, **change})
    assert violations, change
    assert any(field in v for v in violations), violations


@pytest.mark.parametrize(
    "missing",
    [
        "id",
        "role",
        "subject",
        "model_tier",
        "tickets",
    ],
)
def test_required_fields_are_named_when_missing(missing: str) -> None:
    order = {k: v for k, v in VALID.items() if k != missing}
    violations = check(order)
    assert any(missing in v for v in violations), violations


@pytest.mark.parametrize("role", ["implementer", "orchestrator", "general", "probe"])
def test_an_order_of_any_role_without_a_tier_fails_naming_the_field(role: str) -> None:
    order = {k: v for k, v in IMPLEMENTER.items() if k != "model_tier"}
    violations = check({**order, "role": role}, IMPLEMENTER_NAME)
    assert any(v.startswith("model_tier:") for v in violations), violations


def test_only_a_reviewer_names_a_pass_and_it_must() -> None:
    reviewer = {k: v for k, v in VALID.items() if k != "pass"}
    assert any(v.startswith("pass:") for v in check(reviewer))
    implementer = {**IMPLEMENTER, "pass": "spec-fidelity"}
    assert any(v.startswith("pass:") for v in check(implementer, IMPLEMENTER_NAME))


def test_a_non_mapping_is_one_violation() -> None:
    assert len(validate_order(["not", "a", "mapping"], "x", SHORTCODES)) == 1


def test_the_model_tier_is_model_tier_not_tier() -> None:
    # A general word like `tier` carries the noun it classifies,
    # so the order says `model_tier`, in snake case.
    order = {k: v for k, v in VALID.items() if k != "model_tier"}
    assert any("tier" in v for v in check({**order, "tier": "opus"}))


# The name patterns (decisions 98 to 100; the implementer's is the
# recommendation of pandoscope#57). A name the Routine filter misreads
# starts no session or the wrong one, so the check holds name to fields.


@pytest.mark.parametrize(
    "name",
    [
        "review-spec-fidelity-opus-pando26-1",
        "review-spec-fidelity-opus-pando26-4",
        "review-spec-fidelity-opus-pando26-4b",
        "review-spec-fidelity-opus-pando26-12c",
    ],
)
def test_a_review_name_ends_in_its_step_and_a_repeat_letter(name: str) -> None:
    assert check({**VALID, "id": name}, name) == []


@pytest.mark.parametrize(
    ("name", "change", "part"),
    [
        # the role part
        ("implement-opus-pando26-1", {}, "role"),
        ("probe-4", {}, "role"),
        # the pass, the tier and the subject
        ("review-prose-opus-pando26-1", {}, "pass"),
        ("review-spec-fidelity-sonnet-pando26-1", {}, "model_tier"),
        ("review-spec-fidelity-opus-pando27-1", {}, "subject"),
        ("review-spec-fidelity-opus-skills26-1", {}, "subject"),
        ("review-spec-fidelity-opus-pr26-1", {}, "subject"),
        # a pass that is a hyphen-prefix of the name's pass part (F1)
        ("review-spec-fidelity-opus-pando26-1", {"pass": "spec"}, "pass"),
        # the step: absent, from 0, the old round suffix, an `a`, a tail
        ("review-spec-fidelity-opus-pando26", {}, "step"),
        ("review-spec-fidelity-opus-pando26-0", {}, "step"),
        ("review-spec-fidelity-opus-pando26-r2", {}, "step"),
        ("review-spec-fidelity-opus-pando26-1a", {}, "step"),
        ("review-spec-fidelity-opus-pando26-1-x", {}, "step"),
        # an implementer name against a reviewer's fields and back
        ("review-opus-pando57-1", {"role": "implementer"}, "role"),
        ("implement-sonnet-pando57-1", {"role": "implementer"}, "model_tier"),
        ("implement-opus-pando27-1", {"role": "implementer"}, "subject"),
        ("implement-opus-pando57", {"role": "implementer"}, "step"),
    ],
)
def test_a_name_off_its_pattern_fails_and_says_which_part(
    name: str, change: dict[str, object], part: str
) -> None:
    order = {**VALID, **change, "id": name}
    if change.get("role") == "implementer":
        order = {k: v for k, v in order.items() if k != "pass"}
        if part != "subject":
            order["subject"] = "pandoscope/pandoscope#57"
    violations = check(order, name)
    assert len(violations) == 1, violations
    assert violations[0].startswith("id:"), violations
    assert f"the {part} part" in violations[0], violations


def test_a_subject_whose_repository_has_no_shortcode_fails() -> None:
    order = {**VALID, "subject": "pandoscope/meta#26"}
    violations = check(order)
    assert any(
        v.startswith("subject:") and "shortcodes.json" in v for v in violations
    ), violations


def test_a_role_without_a_name_pattern_keeps_only_the_id_check() -> None:
    # DECISION:FALLBACK in order_name.py: the probe role has no pattern.
    probe = {**IMPLEMENTER, "id": "probe-4", "role": "probe"}
    assert check(probe, "probe-4") == []


def test_shortcodes_load_from_the_waybill_file(tmp_path: Path) -> None:
    path = tmp_path / "shortcodes.json"
    path.write_text(json.dumps({"_comment": "seeded once", **SHORTCODES}))
    assert load_shortcodes(path) == SHORTCODES


@pytest.mark.parametrize("text", [None, "[]", '{"a/b": 1}', "{"])
def test_a_missing_or_broken_shortcodes_file_is_an_error(
    tmp_path: Path, text: str | None
) -> None:
    path = tmp_path / "shortcodes.json"
    if text is not None:
        path.write_text(text)
    with pytest.raises(ShortcodeError, match=r"shortcodes\.json"):
        load_shortcodes(path)
