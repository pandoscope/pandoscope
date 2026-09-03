from __future__ import annotations

import pytest

from pandoscope.reinset.receive import Reference, find_reference, parse_reference

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
