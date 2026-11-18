"""The waybill order schema (waybill#1): strict, validated wherever an order is read."""

from __future__ import annotations

import json
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
SHORTCODES_SCHEMA_PATH = Path(__file__).parent / "schemas" / SHORTCODES


class ShortcodeError(Exception):
    """The waybill's shortcodes file is missing or not a map of repository to code."""


def load_shortcodes(path: Path) -> dict[str, str]:
    """
    Return the map of repository to shortcode from the waybill's ``shortcodes.json``.

    The file's shape is the schema's (``schemas/shortcodes.json``):
    the map itself, or the map under ``repos``,
    and keys that start with ``_``, such as ``_comment``, are not shortcodes.
    Each shortcode is returned as written.
    Raises ShortcodeError when the file is missing or is not JSON,
    when a key is written twice in one object of the file,
    when the file breaks the schema, naming each place it does,
    and when two shortcodes name one repository, naming both.
    """

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        # A JSON parser keeps the last of two equal keys without a word.
        keys = [key for key, _ in pairs]
        twice = sorted({key for key in keys if keys.count(key) > 1})
        if twice:
            msg = f"the shortcodes file {path} writes a key twice: " + ", ".join(
                repr(key) for key in twice
            )
            raise ShortcodeError(msg)
        return dict(pairs)

    try:
        data = json.loads(path.read_text(), object_pairs_hook=unique)
    except (OSError, json.JSONDecodeError) as error:
        msg = f"cannot read the shortcodes file {path}: {error}"
        raise ShortcodeError(msg) from error
    schema = json.loads(SHORTCODES_SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(schema)
    broken = [
        f"{'/'.join(str(part) for part in error.path) or 'the file'}: {error.message}"
        for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    ]
    if broken:
        msg = (
            f"the shortcodes file {path} breaks the schema {SHORTCODES_SCHEMA_PATH}: "
            + "; ".join(broken)
        )
        raise ShortcodeError(msg)
    repos = data["repos"] if "repos" in data else data
    codes: dict[str, str] = {}
    for short, repo in repos.items():
        if short.startswith("_"):
            continue
        if repo in codes:
            msg = (
                f"the shortcodes file {path} gives {repo} two shortcodes: "
                f"{codes[repo]!r} and {short!r}"
            )
            raise ShortcodeError(msg)
        codes[repo] = short
    return codes


# Every file name that a shortcode map has carried. A second one in the
# waybill is a second source, which pandoscope#61 removed.
MAP_NAMES = (SHORTCODES, "repo-codes.json")


def find_shortcodes(waybill: Path) -> Path:
    """
    Return the waybill's one shortcodes file, ``<waybill>/shortcodes.json``.

    Raises ShortcodeError when that file is missing,
    and when the waybill holds a second map anywhere outside ``.git``:
    another ``shortcodes.json`` or a ``repo-codes.json``.
    The error names every file it found.
    """
    source = waybill / SHORTCODES
    found = sorted(
        path
        for name in MAP_NAMES
        for path in waybill.rglob(name)
        if ".git" not in path.relative_to(waybill).parts
    )
    if source not in found:
        msg = f"the waybill has no shortcodes file at {source}"
        raise ShortcodeError(msg)
    second = [str(path.relative_to(waybill)) for path in found if path != source]
    if second:
        msg = (
            f"the waybill {waybill} holds a second shortcode map beside "
            f"{SHORTCODES}: {', '.join(second)}; one map is the source (pandoscope#61)"
        )
        raise ShortcodeError(msg)
    return source


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
