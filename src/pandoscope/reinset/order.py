"""The waybill order schema (waybill#1): strict, validated wherever an order is read."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import jsonschema

from pandoscope.reinset.order_name import name_violations

SCHEMA_PATH = Path(__file__).parent / "schemas" / "order.json"
ROLES: tuple[str, ...] = tuple(
    json.loads(SCHEMA_PATH.read_text())["properties"]["role"]["enum"]
)


SHORTCODES = "shortcodes.json"


class ShortcodeError(Exception):
    """The waybill's shortcodes file is missing or not a map of repository to code."""


_SHORTCODE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_REPO = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def name_code(shortcode: str) -> str:
    """Return the form of ``shortcode`` that an order's name uses: its lowercase."""
    # DECISION: one spelling per shortcode, and the name takes its
    # lowercase form, derived here and nowhere else (pandoscope#61).
    return shortcode.lower()


def load_shortcodes(path: Path) -> dict[str, str]:
    """
    Return the map of repository to name code from the waybill's ``shortcodes.json``.

    The file maps each shortcode to its repository, in the format the
    thread ledger reads: a flat object, or ``{forge, patterns, repos}``
    with the map under ``repos``. Top-level keys that start with ``_``,
    such as ``_comment``, are not shortcodes. The returned code is the
    shortcode's ``name_code``.
    Raises ShortcodeError when the file is missing or is not JSON,
    when the map is not an object,
    when a shortcode is not letters and digits or a repository is not ``owner/repo``,
    when two shortcodes differ only in case,
    and when two shortcodes name one repository.
    """
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        msg = f"cannot read the shortcodes file {path}: {error}"
        raise ShortcodeError(msg) from error
    if not isinstance(data, dict):
        msg = f"the shortcodes file {path} is not an object: {data!r}"
        raise ShortcodeError(msg)
    repos = data["repos"] if "repos" in data else data
    if not isinstance(repos, dict):
        msg = f"the shortcodes file {path} holds no map under repos: {repos!r}"
        raise ShortcodeError(msg)
    codes: dict[str, str] = {}
    spelled: dict[str, str] = {}
    for short, repo in repos.items():
        if short.startswith("_"):
            continue
        if (
            not _SHORTCODE.match(short)
            or not isinstance(repo, str)
            or not _REPO.match(repo)
        ):
            msg = (
                f"the shortcodes file {path} maps {short!r} to {repo!r}; "
                "a shortcode is letters and digits, a repository is owner/repo"
            )
            raise ShortcodeError(msg)
        code = name_code(short)
        if code in spelled:
            msg = (
                f"the shortcodes file {path} spells one shortcode twice: "
                f"{spelled[code]!r} and {short!r}"
            )
            raise ShortcodeError(msg)
        if repo in codes:
            msg = (
                f"the shortcodes file {path} gives {repo} two shortcodes: "
                f"{spelled[codes[repo]]!r} and {short!r}"
            )
            raise ShortcodeError(msg)
        spelled[code] = short
        codes[repo] = code
    return codes


def validate_order(data: Any, name: str, shortcodes: Mapping[str, str]) -> list[str]:
    """
    Return every way ``data`` departs from the order schema, each naming its field.

    ``name`` is the order's file base name. The order's ``id`` must
    equal it: the Routine fires from the branch ``order/<name>``, so an
    id that disagrees would send the session after the wrong order.
    An order that fits the schema must also fit its role's name pattern
    (``order_name.py``), with the subject's repository looked up in
    ``shortcodes``. An empty list means the order is valid.
    """
    if not isinstance(data, dict):
        return ["the order is not a mapping"]
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(schema)
    violations: list[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        field = "/".join(str(part) for part in error.path) or _field_of(error)
        violations.append(f"{field}: {error.message}")
    if data.get("id") != name:
        violations.append(f"id: {data.get('id')!r} must equal the file name {name!r}")
    if not violations:
        violations = name_violations(data, shortcodes)
    return violations


def _field_of(error: jsonschema.ValidationError) -> str:
    # A required-key, unknown-key or forbidden-key error has no path.
    # A forbidden key is one the `not` rule requires and the order holds.
    # The other two name their key in the message,
    # so every violation still names its field.
    if error.validator == "not":
        forbidden = [
            k
            for k in _required_keys(error.validator_value)
            if isinstance(error.instance, dict) and k in error.instance
        ]
        if forbidden:
            return ",".join(forbidden)
    if error.validator in ("required", "additionalProperties"):
        quoted = [part for part in error.message.split("'") if part and " " not in part]
        if quoted:
            return str(quoted[0])
    return "order"


def _required_keys(rule: Any) -> list[str]:
    """Every key that a ``required`` keyword anywhere inside ``rule`` lists."""
    if isinstance(rule, dict):
        keys = list(rule.get("required", []))
        for value in rule.values():
            keys += [k for k in _required_keys(value) if k not in keys]
        return keys
    if isinstance(rule, list):
        keys = []
        for value in rule:
            keys += [k for k in _required_keys(value) if k not in keys]
        return keys
    return []
