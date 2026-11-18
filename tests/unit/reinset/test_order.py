from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from pandoscope.reinset.order import (
    ShortcodeError,
    find_shortcodes,
    load_shortcodes,
    validate_order,
)

SHORTCODES = {"pandoscope/pandoscope": "pando", "pandoscope/skills": "sk"}
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


def test_a_tier_has_letters_and_digits_only() -> None:
    # B1: with a hyphen, review-spec-fidelity-opus-pando26-3 read as
    # pass `spec` and tier `fidelity-opus`, and the opus Routine took it.
    name = "review-spec-fidelity-opus-pando26-3"
    order = {**VALID, "id": name, "pass": "spec", "model_tier": "fidelity-opus"}
    assert any(v.startswith("model_tier:") for v in check(order, name))


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
        ("review-spec-fidelity-opus-sk26-1", {}, "subject"),
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
    probe = {**IMPLEMENTER, "id": "probe-opus-4", "role": "probe"}
    assert check(probe, "probe-opus-4") == []


@pytest.mark.parametrize("name", ["probe-sonnet-4", "probe-4", "opus-probe-4"])
def test_a_role_without_a_name_pattern_still_names_its_tier(name: str) -> None:
    # F2: a Routine picks an order by the tier between hyphens in its name.
    probe = {**IMPLEMENTER, "id": name, "role": "probe"}
    violations = check(probe, name)
    assert len(violations) == 1, violations
    assert violations[0].startswith("id:"), violations
    assert "-opus-" in violations[0], violations


@pytest.mark.parametrize("role", ["probe", "general", "orchestrator"])
def test_a_subject_without_a_shortcode_fails_for_every_role(role: str) -> None:
    # F3: the lookup stood after the early return of a role without a pattern.
    order = {**IMPLEMENTER, "id": "probe-opus-4", "role": role}
    order["subject"] = "other/repo#3"
    violations = check(order, "probe-opus-4")
    assert any(
        v.startswith("subject:") and "shortcodes.json" in v for v in violations
    ), violations


# The waybill's file maps each shortcode to its repository, in the
# format the thread ledger reads (pandoscope#61).
SHORTCODE_FILE = {
    "_comment": "seeded once",
    "pando": "pandoscope/pandoscope",
    "sk": "pandoscope/skills",
}


def test_shortcodes_load_from_the_waybill_file(tmp_path: Path) -> None:
    path = tmp_path / "shortcodes.json"
    path.write_text(json.dumps(SHORTCODE_FILE))
    assert load_shortcodes(path) == SHORTCODES


def test_shortcodes_load_from_the_forge_form(tmp_path: Path) -> None:
    path = tmp_path / "shortcodes.json"
    repos = {k: v for k, v in SHORTCODE_FILE.items() if not k.startswith("_")}
    path.write_text(
        json.dumps(
            {
                "_comment": "seeded once",
                "forge": "https://forge.example.test",
                "patterns": {"ticket": "{base}/{repo}/issues/{n}"},
                "repos": repos,
            }
        )
    )
    assert load_shortcodes(path) == SHORTCODES


@pytest.mark.parametrize(
    ("repos", "words"),
    [
        # one spelling per shortcode: a case-only twin is an error
        ({"AET": "o/a", "aet": "o/b"}, ["AET", "aet"]),
        # one shortcode per repository
        ({"PANDO": "o/p", "pd": "o/p"}, ["PANDO", "pd", "o/p"]),
        # a repository is written owner/repo
        ({"PANDO": "pandoscope"}, ["PANDO", "pandoscope"]),
        ({"PANDO": 7}, ["PANDO"]),
        # a shortcode is letters and digits, so its lowercase form fits a name
        ({"PAN-DO": "o/p"}, ["PAN-DO"]),
    ],
)
def test_a_shortcodes_file_that_reads_two_ways_is_an_error(
    tmp_path: Path, repos: dict[str, object], words: list[str]
) -> None:
    path = tmp_path / "shortcodes.json"
    path.write_text(json.dumps(repos))
    with pytest.raises(ShortcodeError) as raised:
        load_shortcodes(path)
    for word in words:
        assert word in str(raised.value), raised.value


@pytest.mark.parametrize("text", [None, "[]", '{"ab": 1}', '{"repos": []}', "{"])
def test_a_missing_or_broken_shortcodes_file_is_an_error(
    tmp_path: Path, text: str | None
) -> None:
    path = tmp_path / "shortcodes.json"
    if text is not None:
        path.write_text(text)
    with pytest.raises(ShortcodeError, match=r"shortcodes\.json"):
        load_shortcodes(path)


def test_the_waybill_has_one_shortcodes_file(tmp_path: Path) -> None:
    (tmp_path / "shortcodes.json").write_text(json.dumps(SHORTCODE_FILE))
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "shortcodes.json").write_text("{}")  # git's, not a map
    assert find_shortcodes(tmp_path) == tmp_path / "shortcodes.json"


@pytest.mark.parametrize(
    "second", ["orders/shortcodes.json", "config/shortcodes.json", "repo-codes.json"]
)
def test_a_second_shortcodes_file_in_the_waybill_is_an_error(
    tmp_path: Path, second: str
) -> None:
    # The guard of pandoscope#61: one map, and a second one fails.
    (tmp_path / "shortcodes.json").write_text(json.dumps(SHORTCODE_FILE))
    (tmp_path / second).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / second).write_text("{}")
    with pytest.raises(ShortcodeError, match=second):
        find_shortcodes(tmp_path)


def test_a_waybill_without_its_shortcodes_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ShortcodeError, match=r"shortcodes\.json"):
        find_shortcodes(tmp_path)
