"""
Whether the org's installed release bot holds every permission `releasebot.PERMISSIONS` names.

GitHub has no API to change an app's permissions or to accept them for an
installation; both are clicks for an org owner. What can be read is the
installation's accepted permissions, so a gap is reported as a manual step
with the page to click on.
"""

from __future__ import annotations

from pandoscope.org.forge import Run


def permission_gaps(org: str, slug: str, run: Run) -> list[str]:
    """
    Return one MANUAL line per step the release bot ``slug`` still needs in ``org``.

    Empty when the bot is installed on ``org`` and holds every permission
    at least at the level `releasebot.PERMISSIONS` names.
    """
    raise NotImplementedError
