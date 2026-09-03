"""Opaque principal ids (skills#179 §3.2.1)."""

from __future__ import annotations

UNKNOWN = "unknown"


def principal_id(email: str | None, salt: str | None) -> str:
    """
    Return ``p-`` + sha256(salt || lowercase(email))[:12].

    Returns ``unknown`` when either input is missing: an id is never
    guessed, and an unsalted id would be a dictionary-attackable email.
    """
    raise NotImplementedError
