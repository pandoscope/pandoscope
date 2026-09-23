from __future__ import annotations

from pathlib import Path

import pytest

from pandoscope.reinset.review import ReviewError, review_task

PROMPT_FILE = """\
# Routine prompt: spec-fidelity review

Prose about the routine, with `<tier>` in it, which is not the prompt.

```text
PANDO-REVIEW: spec-fidelity tier=<tier>

# Task

Review pull request <n> as tier <tier>.

    git push -u origin claude/review-spec-fidelity-<tier>-pr<n>
```

More prose after the block.
"""


def write_pass(session_root: Path, text: str = PROMPT_FILE) -> Path:
    path = session_root / "skills" / "original" / "thread-ledger" / "review"
    path.mkdir(parents=True)
    target = path / "spec-fidelity.md"
    target.write_text(text)
    return target


def test_task_is_the_pass_files_prompt_block_with_the_placeholders_filled(
    session_root: Path,
) -> None:
    write_pass(session_root)
    task = review_task(session_root, "spec-fidelity", "opus", 261)
    assert task == (
        "# Task\n\nReview pull request 261 as tier opus.\n\n"
        "    git push -u origin claude/review-spec-fidelity-opus-pr261\n"
    )


def test_missing_pass_file_is_a_review_error(session_root: Path) -> None:
    with pytest.raises(ReviewError, match=r"spec-fidelity\.md"):
        review_task(session_root, "spec-fidelity", "opus", 1)


def test_pass_file_without_a_prompt_block_is_a_review_error(
    session_root: Path,
) -> None:
    write_pass(session_root, "# No block here\n")
    with pytest.raises(ReviewError, match=r"text block"):
        review_task(session_root, "spec-fidelity", "opus", 1)
