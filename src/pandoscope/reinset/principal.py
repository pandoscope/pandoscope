"""Opaque principal ids (skills#179 §3.2.1)."""

from __future__ import annotations

import hashlib

UNKNOWN = "unknown"


def principal_id(email: str | None, salt: str | None) -> str:
    """
    Return ``p-`` + sha256(salt || lowercase(email))[:12].

    Returns ``unknown`` when either input is missing: an id is never
    guessed, and an unsalted id would be a dictionary-attackable email.
    """
    if not email or not salt:
        return UNKNOWN
    digest = hashlib.sha256(salt.encode() + email.lower().encode()).hexdigest()
    return "p-" + digest[:12]
