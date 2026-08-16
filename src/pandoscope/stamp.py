"""Stamp the agentic-engineering-template scaffold into a directory."""

from __future__ import annotations

TEMPLATE_URL = "https://github.com/pandoscope/agentic-engineering-template"


def parse_data(pairs: list[str]) -> dict[str, str]:
    """
    Parse ``KEY=VALUE`` answer pairs into copier data.

    Raises ValueError on a pair without ``=``.
    """
    data: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            msg = f"expected KEY=VALUE, got {pair!r}"
            raise ValueError(msg)
        data[key] = value
    return data


def stamp(
    directory: str,
    data: dict[str, str] | None = None,
    *,
    defaults: bool = False,
    vcs_ref: str | None = None,
) -> None:
    """Render the scaffold into ``directory`` via copier."""
    import copier

    copier.run_copy(
        src_path=TEMPLATE_URL,
        dst_path=directory,
        data=data or {},
        defaults=defaults,
        unsafe=True,
        vcs_ref=vcs_ref,
    )
