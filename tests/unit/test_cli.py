from __future__ import annotations

import pytest

from pandoscope.cli import build_parser
from pandoscope.stamp import parse_data


def test_parse_data_splits_pairs() -> None:
    assert parse_data(["a=1", "b=x=y"]) == {"a": "1", "b": "x=y"}


def test_parse_data_rejects_bare_key() -> None:
    with pytest.raises(ValueError, match="KEY=VALUE"):
        parse_data(["nonsense"])


def test_stamp_defaults_to_current_directory() -> None:
    args = build_parser().parse_args(["stamp"])
    assert args.directory == "."
    assert args.data == []
    assert args.defaults is False


def test_stamp_collects_repeated_data() -> None:
    args = build_parser().parse_args(
        ["stamp", "proj", "-d", "agentic_project_name=X", "-d", "agentic_forge=github"]
    )
    assert args.directory == "proj"
    assert args.data == ["agentic_project_name=X", "agentic_forge=github"]


def test_command_is_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
