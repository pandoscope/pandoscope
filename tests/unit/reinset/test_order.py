from __future__ import annotations

import pytest

from pandoscope.reinset.order import validate_order

VALID = {
    "id": "review-spec-fidelity-opus-pr26",
    "role": "reviewer",
    "pass": "spec-fidelity",
    "model-tier": "opus",
    "pull_request": "pandoscope/pandoscope#26",
    "checkouts": {"pandoscope/skills": "claude/sk195-review-driver"},
    "tickets": ["pandoscope/skills#195"],
}


def test_a_valid_review_order_has_no_violations() -> None:
    assert validate_order(VALID, "review-spec-fidelity-opus-pr26") == []


def test_result_is_the_one_optional_field() -> None:
    order = {
        **VALID,
        "result": "pandoscope/pandoscope@claude/review-spec-fidelity-opus-pr26",
    }
    assert validate_order(order, "review-spec-fidelity-opus-pr26") == []


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"id": "other"}, "id"),  # must equal the file name
        ({"role": "auditor"}, "role"),
        ({"model-tier": "Opus"}, "model-tier"),  # the driver's tier is lowercase
        ({"pass": "Spec Fidelity"}, "pass"),
        ({"pull_request": "26"}, "pull_request"),
        ({"pull_request": "pandoscope/pandoscope!26"}, "pull_request"),
        ({"checkouts": {"skills": "main"}}, "checkouts"),  # key is owner/repo
        ({"checkouts": {"pandoscope/skills": "a ref"}}, "checkouts"),  # no spaces
        ({"checkouts": ["pandoscope/skills"]}, "checkouts"),
        ({"tickets": ["195"]}, "tickets"),
        ({"tickets": "pandoscope/skills#195"}, "tickets"),
        ({"pull-request": "pandoscope/pandoscope#26"}, "pull-request"),  # unknown key
    ],
)
def test_each_violation_names_its_field(change: dict[str, object], field: str) -> None:
    violations = validate_order({**VALID, **change}, "review-spec-fidelity-opus-pr26")
    assert violations, change
    assert any(field in v for v in violations), violations


@pytest.mark.parametrize("missing", ["id", "role", "pull_request", "tickets"])
def test_required_fields_are_named_when_missing(missing: str) -> None:
    order = {k: v for k, v in VALID.items() if k != missing}
    violations = validate_order(order, "review-spec-fidelity-opus-pr26")
    assert any(missing in v for v in violations), violations


def test_a_reviewer_needs_pass_and_tier_and_no_other_role_may_carry_them() -> None:
    reviewer = {k: v for k, v in VALID.items() if k not in ("pass", "model-tier")}
    assert any(
        "pass" in v or "model-tier" in v
        for v in validate_order(reviewer, "review-spec-fidelity-opus-pr26")
    )
    implementer = {**VALID, "role": "implementer"}
    assert any(
        "pass" in v or "model-tier" in v
        for v in validate_order(implementer, "review-spec-fidelity-opus-pr26")
    )
    plain = {k: v for k, v in implementer.items() if k not in ("pass", "model-tier")}
    assert validate_order(plain, "review-spec-fidelity-opus-pr26") == []


def test_a_non_mapping_is_one_violation() -> None:
    assert len(validate_order(["not", "a", "mapping"], "x")) == 1


def test_the_model_tier_is_named_model_tier() -> None:
    # `tier` alone was ambiguous next to a finding's grade; the order's
    # field names the model tier.
    order = {k: v for k, v in VALID.items() if k != "model-tier"}
    assert validate_order({**order, "model-tier": "opus"}, VALID["id"]) == []
    assert any(
        "tier" in v for v in validate_order({**order, "tier": "opus"}, str(VALID["id"]))
    )


@pytest.mark.xfail(strict=True)
def test_the_model_tier_key_is_snake_case_like_pull_request() -> None:
    order = {k: v for k, v in VALID.items() if k != "model-tier"}
    assert validate_order({**order, "model_tier": "opus"}, str(VALID["id"])) == []
