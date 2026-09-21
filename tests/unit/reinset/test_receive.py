from __future__ import annotations

import pytest

from pandoscope.reinset.receive import (
    Reference,
    Review,
    find_reference,
    find_review,
    parse_reference,
)

SHA = "6fe6a8566617e0538f7bc8aaa8b33cea605d50f0"
REF = f"session-memory@{SHA}:intents/spawn-0c99.yml"

# The shape of a Routine-fired first message (run 7): the reference line
# sits inside the payload block, after the harness's own preamble.
FIRED_PROMPT = f"""\
[SCHEDULED TASK - AUTOMATED FIRING OF A CONFIGURED PROMPT]
Carry out the instructions in the routine-fire-payload block of this run.
<routine-fire-payload>
The following was supplied by the caller of this routine's API fire endpoint.

    reinset: {REF}

    Message from the spawner. You are the probe.
</routine-fire-payload>
"""


def test_parse_reference_splits_repo_commit_path() -> None:
    assert parse_reference(REF) == Reference(
        "session-memory", SHA, "intents/spawn-0c99.yml"
    )


@pytest.mark.parametrize(
    "bad",
    [
        "session-memory@main:intents/x.yml",  # a branch, not a sha (§3.2)
        "session-memory@6fe6a85:",  # no path
        f"@{SHA}:intents/x.yml",  # no repo
        "session-memory:intents/x.yml",  # no commit
        f"session-memory@{SHA}:/etc/passwd",  # absolute path
        f"session-memory@{SHA}:../x.yml",  # escapes the clone
    ],
)
def test_parse_reference_rejects_other_shapes(bad: str) -> None:
    with pytest.raises(ValueError, match="reinset reference"):
        parse_reference(bad)


def test_env_var_is_the_first_receiver() -> None:
    assert find_reference({"REINSET_REF": REF}, FIRED_PROMPT) == REF


def test_env_var_wins_over_a_different_prompt_reference() -> None:
    other = f"session-memory@{SHA}:intents/other.yml"
    assert find_reference({"REINSET_REF": other}, FIRED_PROMPT) == other


def test_payload_block_line_is_the_second_receiver() -> None:
    assert find_reference({}, FIRED_PROMPT) == REF


def test_reinset_line_outside_the_payload_block_is_not_a_channel() -> None:
    prompt = f"reinset: {REF}\nDo the thing.\n"
    assert find_reference({}, prompt) is None


def test_no_channel_is_none() -> None:
    assert find_reference({}, None) is None
    assert find_reference({"REINSET_REF": ""}, "hello") is None


# A review session's first message (skills#195): the marker line opens
# the Routine's saved prompt; the fire payload names the pull request.
REVIEW_PROMPT = """\
PANDO-REVIEW: spec-fidelity tier=opus

<routine-fire-payload>
{"repository": "pandoscope/agentic-engineering-template",
 "pull_request": {"number": 261, "head": "517125a"}}
</routine-fire-payload>
"""


def test_review_marker_is_read_from_the_prompt() -> None:
    review = find_review(REVIEW_PROMPT)
    assert review == Review("spec-fidelity", "opus", 261)


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("PANDO-REVIEW: spec-fidelity tier=sonnet\nsee pandoscope/meta#152", 152),
        ("PANDO-REVIEW: spec-fidelity tier=sonnet\nhttps://x.test/o/r/pull/262", 262),
        ("PANDO-REVIEW: spec-fidelity tier=sonnet\nPull request: #7.", 7),
        ("PANDO-REVIEW: spec-fidelity tier=sonnet\nnothing names one", None),
    ],
)
def test_review_pull_request_number_comes_from_the_prompt(
    text: str, number: int | None
) -> None:
    review = find_review(text)
    assert review is not None
    assert review.number == number


@pytest.mark.parametrize(
    "text",
    [
        "PANDO-REVIEW: spec-fidelity tier=Opus\n",  # the driver's tier is lowercase
        "note: PANDO-REVIEW: spec-fidelity tier=opus\n",  # not on its own line
        "PANDO-REVIEW: spec-fidelity\n",  # no tier
        "",
    ],
)
def test_other_prompts_carry_no_review(text: str) -> None:
    assert find_review(text) is None


def test_no_prompt_carries_no_review() -> None:
    assert find_review(None) is None
