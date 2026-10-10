from __future__ import annotations

import pytest

from pandoscope.cli import build_parser


def test_org_init_parses_the_plan_inputs() -> None:
    args = build_parser().parse_args(
        [
            "org",
            "init",
            "somnus-app",
            "--project",
            "somnus",
            "--description",
            "Battery wake diagnosis.",
            "--approver",
            "pando-genet",
            "--approver",
            "second-human",
            "--meta",
            "/src/meta",
        ]
    )
    assert args.org == "somnus-app"
    assert args.project == "somnus"
    assert args.description == "Battery wake diagnosis."
    assert args.approver == ["pando-genet", "second-human"]
    assert args.meta == "/src/meta"
    assert args.workdir is None


@pytest.mark.parametrize("missing", ["--meta"])
def test_org_init_requires_every_plan_input(missing: str) -> None:
    given = {
        "--project": "p",
        "--description": "d",
        "--approver": "a",
        "--meta": "m",
    }
    argv = ["org", "init", "o"]
    for flag, value in given.items():
        if flag != missing:
            argv += [flag, value]
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)
