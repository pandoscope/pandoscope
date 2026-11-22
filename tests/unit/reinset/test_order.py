from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

import jsonschema
import pytest

from pandoscope.reinset import order as order_module
from pandoscope.reinset.order import (
    SHORTCODES_SCHEMA_PATH,
    ShortcodeError,
    find_shortcodes,
    load_shortcodes,
    validate_order,
)
from pandoscope.reinset.order_name import PATTERNS, ROLE_OF_WORD

README = Path(__file__).parents[3] / "README.md"

SHORTCODES = {"pandoscope/pandoscope": "pando", "pandoscope/skills": "sk"}
NAME = "review_spec-fidelity_opus_pando26_1"
VALID = {
    "id": NAME,
    "role": "reviewer",
    "pass": "spec-fidelity",
    "model_tier": "opus",
    "subject": "pandoscope/pandoscope#26",
    "checkouts": {"pandoscope/skills": "claude/sk195-review-driver"},
    "tickets": ["pandoscope/skills#195"],
}
IMPLEMENTER_NAME = "implement_build_opus_pando57_1"
IMPLEMENTER = {
    "id": IMPLEMENTER_NAME,
    "role": "implementer",
    "pass": "build",
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
    name = "implement_fix_opus_pando58_2"
    fix_round = {**IMPLEMENTER, "id": name, "pass": "fix"}
    fix_round["subject"] = "pandoscope/pandoscope#58"
    assert check(fix_round, name) == []


def test_result_is_an_optional_field() -> None:
    order = {
        **VALID,
        "result": "pandoscope/pandoscope@claude/review-spec-fidelity-opus-pando26",
    }
    assert check(order) == []


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"id": "other"}, "id"),  # must equal the file name
        ({"role": "auditor"}, "role"),
        # meta#194: an order sets a worker role only, and no role is general.
        ({"role": "orchestrator"}, "role"),
        ({"role": "general"}, "role"),
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


@pytest.mark.parametrize("role", ["orchestrator", "general", "probe"])
def test_an_order_names_a_worker_role_only(role: str) -> None:
    # Decisions 135 and 143: an orchestrator is started by the principal,
    # a probe is a subagent or a session an orchestrator starts,
    # and the role general goes.
    name = f"{role}_build_opus_pando57_1"
    violations = check({**IMPLEMENTER, "id": name, "role": role}, name)
    assert len(violations) == 1, violations
    assert violations[0].startswith("role:"), violations
    assert repr(role) in violations[0], violations


@pytest.mark.parametrize("role", ["reviewer", "implementer"])
def test_an_order_of_any_role_without_a_tier_fails_naming_the_field(role: str) -> None:
    order = {k: v for k, v in IMPLEMENTER.items() if k != "model_tier"}
    violations = check({**order, "role": role}, IMPLEMENTER_NAME)
    assert any(v.startswith("model_tier:") for v in violations), violations


@pytest.mark.parametrize(
    "role",
    ["reviewer", "implementer"],
)
def test_an_order_of_any_role_without_a_pass_fails_naming_the_field(
    role: str,
) -> None:
    # Decision 109: every role has a pass, not only the reviewer.
    order = {k: v for k, v in IMPLEMENTER.items() if k != "pass"}
    violations = check({**order, "role": role}, IMPLEMENTER_NAME)
    assert any(v.startswith("pass:") for v in violations), violations


@pytest.mark.parametrize("pass_", ["spec-fidelity", "builds"])
def test_the_order_check_holds_no_list_of_implementer_passes(pass_: str) -> None:
    # Decision 137: a role's passes are its pass files,
    # which the composer looks up, as for a reviewer.
    name = f"implement_{pass_}_opus_pando57_1"
    assert check({**IMPLEMENTER, "id": name, "pass": pass_}, name) == []


def test_a_tier_has_letters_and_digits_only() -> None:
    # B1: with a hyphen between all parts, review-spec-fidelity-opus-pando26-3 read as
    # pass `spec` and tier `fidelity-opus`, and the opus Routine took it.
    name = "review_spec-fidelity_opus_pando26_3"
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
        "review_spec-fidelity_opus_pando26_1",
        "review_spec-fidelity_opus_pando26_4",
        "review_spec-fidelity_opus_pando26_4b",
        "review_spec-fidelity_opus_pando26_12c",
    ],
)
def test_a_review_name_ends_in_its_step_and_a_repeat_letter(name: str) -> None:
    assert check({**VALID, "id": name}, name) == []


@pytest.mark.parametrize(
    ("name", "change", "part"),
    [
        # the role part
        ("implement_opus_pando26_1", {}, "role"),
        ("probe-4", {}, "role"),
        # the pass, the tier and the subject
        ("review_prose_opus_pando26_1", {}, "pass"),
        ("review_spec-fidelity_sonnet_pando26_1", {}, "model_tier"),
        ("review_spec-fidelity_opus_pando27_1", {}, "subject"),
        ("review_spec-fidelity_opus_sk26_1", {}, "subject"),
        ("review_spec-fidelity_opus_pr26_1", {}, "subject"),
        # a pass that is a hyphen-prefix of the name's pass part (F1)
        ("review_spec-fidelity_opus_pando26_1", {"pass": "spec"}, "pass"),
        # the step: absent, from 0, the old round suffix, an `a`, a tail part, a tail
        ("review_spec-fidelity_opus_pando26", {}, "step"),
        ("review_spec-fidelity_opus_pando26_0", {}, "step"),
        ("review_spec-fidelity_opus_pando26_r2", {}, "step"),
        ("review_spec-fidelity_opus_pando26_1a", {}, "step"),
        ("review_spec-fidelity_opus_pando26_1_x", {}, "step"),
        ("review_spec-fidelity_opus_pando26_1-x", {}, "step"),
        # an implementer name against a reviewer's fields and back
        *(
            (name, {"role": "implementer"}, part)
            for name, part in [
                ("review_build_opus_pando57_1", "role"),
                # the name of an implementer order carries its pass (decision 109)
                ("implement_opus_pando57_1", "pass"),
                ("implement_fix_opus_pando57_1", "pass"),
                ("implement_build_sonnet_pando57_1", "model_tier"),
                ("implement_build_opus_pando27_1", "subject"),
                ("implement_build_opus_pando57", "step"),
            ]
        ),
    ],
)
def test_a_name_off_its_pattern_fails_and_says_which_part(
    name: str, change: dict[str, object], part: str
) -> None:
    order = {**VALID, **change, "id": name}
    if change.get("role") == "implementer":
        order = {**order, "pass": "build"}
        if part != "subject":
            order["subject"] = "pandoscope/pandoscope#57"
    violations = check(order, name)
    assert len(violations) == 1, violations
    assert violations[0].startswith("id:"), violations
    assert f"the {part} part" in violations[0], violations


def test_a_pass_that_holds_a_tier_word_is_told_from_a_tier() -> None:
    # Part D case 1, ruled by decision 155 (question 34): an underscore
    # separates the parts, so the pass `prose-opus` on the tier `sonnet`
    # reads one way only, with no list of tiers to check against.
    name = "review_prose-opus_sonnet_pando58_1"
    order = {**VALID, "id": name, "pass": "prose-opus", "model_tier": "sonnet"}
    order["subject"] = "pandoscope/pandoscope#58"
    assert check(order, name) == []
    misread = {**order, "pass": "prose", "model_tier": "opus"}
    violations = check(misread, name)
    assert len(violations) == 1, violations
    assert "the pass part must be 'prose'" in violations[0], violations


@pytest.mark.parametrize(
    ("name", "change"),
    [
        ("review-spec-fidelity-opus-pando26-1", {}),
        ("implement-build-opus-pando57-1", IMPLEMENTER),
    ],
)
def test_a_name_with_a_hyphen_between_its_parts_fails(
    name: str, change: Mapping[str, object]
) -> None:
    # Decision 155, question 34: an underscore separates the parts of a name,
    # and a hyphen stands only inside a part. Finding 2 of
    # review-spec-fidelity-mythos-pando64-8: the message blamed the role part,
    # the one word that is right, and not the separator.
    order = {**VALID, **change, "id": name}
    violations = check(order, name)
    assert len(violations) == 1, violations
    assert violations[0].startswith("id:"), violations
    assert "an underscore separates the parts" in violations[0], violations
    assert "the role part must be" not in violations[0], violations


def test_a_hyphen_inside_a_part_is_part_of_it() -> None:
    # The pass `spec-fidelity` keeps its hyphen; only the underscore separates.
    name = "review_spec_fidelity_opus_pando26_1"
    violations = check({**VALID, "id": name}, name)
    assert len(violations) == 1, violations
    assert "the pass part must be 'spec-fidelity'" in violations[0], violations


@pytest.mark.parametrize("role", ["reviewer", "implementer"])
def test_an_extra_part_after_the_tier_blames_the_part_it_stands_in(role: str) -> None:
    # Part D case 2: the old `-r2` stands where the subject belongs,
    # and the tier in the name agrees with the order.
    pass_ = "spec-fidelity" if role == "reviewer" else "build"
    word = "review" if role == "reviewer" else "implement"
    name = f"{word}_{pass_}_opus_r2_pando58_4"
    order = {**VALID, "id": name, "role": role, "pass": pass_}
    order["subject"] = "pandoscope/pandoscope#58"
    violations = check(order, name)
    assert len(violations) == 1, violations
    assert "the subject part" in violations[0], violations
    assert "'r2_pando58_4'" in violations[0], violations


@pytest.mark.parametrize(
    ("name", "role", "owner"),
    [
        ("implement_opus_pando57_1", "reviewer", "implementer"),
        ("implement_build_opus_pando57_1", "reviewer", "implementer"),
        ("review_spec-fidelity_opus_pando57_1", "implementer", "reviewer"),
    ],
)
def test_a_name_that_begins_with_a_roles_word_needs_that_role(
    role: str, name: str, owner: str
) -> None:
    # Part D case 3: the name of one role on an order of another.
    order = {**IMPLEMENTER, "id": name, "role": role}
    violations = check(order, name)
    assert len(violations) == 1, violations
    assert violations[0].startswith("id:"), violations
    assert "the role part" in violations[0], violations
    assert repr(owner) in violations[0], violations
    assert repr(role) in violations[0], violations


def test_a_subject_whose_repository_has_no_shortcode_fails() -> None:
    order = {**VALID, "subject": "pandoscope/meta#26"}
    violations = check(order)
    assert any(
        v.startswith("subject:") and "shortcodes.json" in v for v in violations
    ), violations


@pytest.mark.parametrize("role", ["reviewer", "implementer"])
def test_a_subject_without_a_shortcode_fails_for_every_role(role: str) -> None:
    order = {**IMPLEMENTER, "role": role, "subject": "other/repo#3"}
    violations = check(order, IMPLEMENTER_NAME)
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
        # one shortcode per repository, and the error names both
        ({"pando": "o/p", "pd": "o/p"}, ["pando", "pd", "o/p"]),
        # a repository is written owner/repo
        ({"pando": "pandoscope"}, ["pando", "pandoscope"]),
        ({"pando": 7}, ["pando"]),
        # a shortcode is letters only
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


@pytest.mark.parametrize("short", ["Pando", "pando1", "p", "pandos", "sk\n"])
@pytest.mark.parametrize("form", ["flat", "forge"])
def test_a_shortcode_off_two_to_five_lowercase_letters_fails_naming_it(
    tmp_path: Path, short: str, form: str
) -> None:
    # Decision 122: a capital letter, a digit, one letter or six letters,
    # and a trailing line feed, which $ in a Python regex lets through.
    repos = {short: "pandoscope/pandoscope"}
    path = tmp_path / "shortcodes.json"
    path.write_text(json.dumps(repos if form == "flat" else {"repos": repos}))
    with pytest.raises(ShortcodeError) as raised:
        load_shortcodes(path)
    assert repr(short) in str(raised.value), raised.value


@pytest.mark.parametrize("repo", ["Pandoscope/skills", "pandoscope/Skills"])
@pytest.mark.parametrize("form", ["flat", "forge"])
def test_a_repository_with_a_capital_letter_fails_naming_it(
    tmp_path: Path, repo: str, form: str
) -> None:
    # Decision 143, answer 6: a repository in the map is written in lowercase,
    # so two spellings of one repository cannot get two shortcodes.
    repos = {"sk": "pandoscope/skills", "skl": repo}
    path = tmp_path / "shortcodes.json"
    path.write_text(json.dumps(repos if form == "flat" else {"repos": repos}))
    with pytest.raises(ShortcodeError) as raised:
        load_shortcodes(path)
    assert repr(repo) in str(raised.value), raised.value


def test_a_shortcode_is_used_as_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The schema is the one home of the shape rules: under a schema that
    # allows any shape, the loader states none of its own.
    schema = tmp_path / "any.json"
    schema.write_text("{}")
    monkeypatch.setattr(order_module, "SHORTCODES_SCHEMA_PATH", schema)
    path = tmp_path / "shortcodes.json"
    path.write_text(json.dumps({"Pando7": "pandoscope", "_note": 1}))
    assert load_shortcodes(path) == {"pandoscope": "Pando7"}


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ('{"pando": "o/p", "pando": "o/q"}', "pando"),
        ('{"repos": {"pando": "o/p", "pando": "o/p"}}', "pando"),
        ('{"repos": {}, "repos": {"pando": "o/p"}}', "repos"),
    ],
)
def test_a_key_written_twice_is_an_error(tmp_path: Path, text: str, key: str) -> None:
    # A JSON parser keeps the last of two equal keys without a word.
    path = tmp_path / "shortcodes.json"
    path.write_text(text)
    with pytest.raises(ShortcodeError) as raised:
        load_shortcodes(path)
    assert repr(key) in str(raised.value), raised.value
    assert "twice" in str(raised.value), raised.value


def schema_errors(data: object) -> list[str]:
    schema = json.loads(SHORTCODES_SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(schema)
    return [error.message for error in validator.iter_errors(data)]


WAYBILL_FORM = {
    "_comment": "the org's one map",
    "repos": {"aet": "pandoscope/agentic-engineering-template", "sc": "o/sc"},
}


@pytest.mark.parametrize(
    "data",
    [
        WAYBILL_FORM,
        {**SHORTCODE_FILE},
        {
            "forge": "https://forge.example.test",
            "patterns": {"ticket": "{base}/{repo}/issues/{n}"},
            "repos": {"pando": "pandoscope/pandoscope", "_why": "a note"},
        },
    ],
)
def test_the_schema_takes_both_forms_and_comment_keys(data: object) -> None:
    assert schema_errors(data) == []


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"repos": []},
        {"Pando": "o/p"},
        {"pando1": "o/p"},
        {"p": "o/p"},
        {"pandos": "o/p"},
        {"repos": {"Pando": "o/p"}},
        {"pando": "pandoscope"},
        {"pando": 7},
        {"repos": {"pando": "o/p/q"}},
        {"pando": "O/p"},
        {"repos": {"pando": "o/P"}},
        # a key beside the map under repos is a forge setting or a comment
        {"repos": {"pando": "o/p"}, "owner": "pandoscope"},
        {"repos": {"pando": "o/p"}, "forge": 7},
        # $ in a Python regex also matches before a final line feed
        {"sk\n": "o/p"},
        {"repos": {"sk\n": "o/p"}},
        {"pando": "o/p\n"},
    ],
)
def test_the_schema_states_the_shape(data: object) -> None:
    assert schema_errors(data), data


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


def test_the_readme_points_to_the_name_patterns_and_the_shortcode_schema() -> None:
    # Findings 5 and 6 of review-principal-pando64-9: the README restated the
    # name patterns and the shortcode shape, which can drift from their source.
    readme = README.read_text()
    for pattern in PATTERNS.values():
        assert pattern not in readme, pattern
    assert "`PATTERNS` in `src/pandoscope/reinset/order_name.py`" in readme
    assert "two to five" not in readme
    assert "`src/pandoscope/reinset/schemas/shortcodes.json`" in readme
    # The examples that stand in place of the patterns fit them.
    examples = re.findall(r"`((?:review|implement)_[a-z0-9_-]+)`", readme)
    assert {name.split("_")[0] for name in examples} == set(ROLE_OF_WORD), examples
    repo_of = {code: repo for repo, code in SHORTCODES.items()}
    for name in examples:
        word, pass_, tier, subject, _ = name.split("_")
        found = re.fullmatch(r"([a-z]+)([0-9]+)", subject)
        assert found is not None, name
        order = {
            "id": name,
            "role": ROLE_OF_WORD[word],
            "pass": pass_,
            "model_tier": tier,
            "subject": f"{repo_of[found[1]]}#{found[2]}",
            "tickets": [],
        }
        assert check(order, name) == [], name
