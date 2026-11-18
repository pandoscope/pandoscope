"""The waybill order schema (waybill#1): strict, validated wherever an order is read."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = Path(__file__).parent / "schemas" / "order.json"
ROLES: tuple[str, ...] = tuple(
    json.loads(SCHEMA_PATH.read_text())["properties"]["role"]["enum"]
)


SHORTCODES = "shortcodes.json"


class ShortcodeError(Exception):
    """The waybill's shortcodes file is missing or not a map of repository to code."""


def load_shortcodes(path: Path) -> dict[str, str]:
    """Return the map of repository to shortcode from the waybill's file."""
    raise NotImplementedError


def validate_order(data: Any, name: str, shortcodes: Mapping[str, str]) -> list[str]:
    """
    Return every way ``data`` departs from the order schema, each naming its field.

    ``name`` is the order's file base name. The order's ``id`` must
    equal it: the Routine fires from the branch ``order/<name>``, so an
    id that disagrees would send the session after the wrong order. An
    empty list means the order is valid.
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
