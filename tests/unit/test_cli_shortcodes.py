from __future__ import annotations

import json
from pathlib import Path

import pytest

from pandoscope.cli import main

GOOD = {
    "_comment": "the org's one map",
    "repos": {"pando": "pandoscope/pandoscope", "sk": "pandoscope/skills"},
}


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "shortcodes.json"
    path.write_text(text)
    return path


def test_a_map_that_fits_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write(tmp_path, json.dumps(GOOD))
    assert main(["shortcodes", "check", str(path)]) == 0
    assert capsys.readouterr().out == f"{path}: ok\n"


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ('{"Pando": "o/p"}', "Pando"),  # a capital letter
        ('{"pando1": "o/p"}', "pando1"),  # a digit
        ('{"p": "o/p"}', "'p'"),  # one letter
        ('{"pandos": "o/p"}', "pandos"),  # six letters
        ('{"pando": "pandoscope"}', "pandoscope"),  # no owner
        ('{"pando": "o/p", "pd": "o/p"}', "pd"),  # two for one repository
        ('{"pando": "o/p", "pando": "o/q"}', "twice"),  # a key written twice
        ("{", "shortcodes.json"),  # not JSON
    ],
)
def test_each_failure_of_the_map_exits_non_zero_and_names_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, word: str
) -> None:
    path = write(tmp_path, text)
    assert main(["shortcodes", "check", str(path)]) == 1
    out = capsys.readouterr().out
    assert out.startswith(f"{path}: "), out
    assert word in out, out
    assert "ok" not in out, out


def test_a_second_map_beside_it_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The guard of pandoscope#61 runs on the map's folder.
    path = write(tmp_path, json.dumps(GOOD))
    (tmp_path / "orders").mkdir()
    (tmp_path / "orders" / "repo-codes.json").write_text("{}")
    assert main(["shortcodes", "check", str(path)]) == 1
    assert "repo-codes.json" in capsys.readouterr().out


def test_a_missing_map_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "shortcodes.json"
    assert main(["shortcodes", "check", str(path)]) == 1
    assert "shortcodes.json" in capsys.readouterr().out
