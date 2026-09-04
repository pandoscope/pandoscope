from __future__ import annotations

import hashlib

from pandoscope.reinset.principal import principal_id


def test_id_is_salted_sha256_prefix_of_lowercased_email() -> None:
    digest = hashlib.sha256(b"salt" + b"owner@example.test").hexdigest()
    assert principal_id("Owner@Example.test", "salt") == "p-" + digest[:12]


def test_case_of_email_does_not_change_id() -> None:
    assert principal_id("A@B.test", "s") == principal_id("a@b.test", "s")


def test_missing_email_or_salt_is_unknown_never_guessed() -> None:
    assert principal_id(None, "salt") == "unknown"
    assert principal_id("a@b.test", None) == "unknown"
    assert principal_id("", "salt") == "unknown"
