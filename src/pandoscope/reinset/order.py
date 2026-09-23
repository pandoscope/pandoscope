"""The waybill order schema (waybill#1): strict, validated wherever an order is read."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = Path(__file__).parent / "schemas" / "order.json"
ROLES: tuple[str, ...] = tuple(
    json.loads(SCHEMA_PATH.read_text())["properties"]["role"]["enum"]
)


def validate_order(data: Any, name: str) -> list[str]:
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
    # A required-key or unknown-key error has no path. Take the key from
    # the message, so every violation still names its field.
    if error.validator in ("required", "additionalProperties", "not"):
        quoted = [part for part in error.message.split("'") if part and " " not in part]
        if quoted:
            return str(quoted[0])
    return "order"
