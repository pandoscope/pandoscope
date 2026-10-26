"""
Whether the org's installed release bot holds every permission `releasebot.PERMISSIONS` names.

GitHub has no API to change an app's permissions or to accept them for an
installation; both are clicks for an org owner. What can be read is the
installation's accepted permissions, so a gap is reported as a manual step
with the page to click on.
"""

from __future__ import annotations

import json

from pandoscope.org.forge import Run
from pandoscope.org.releasebot import PERMISSIONS, SLUG, install_url

# A permission level covers every level below it.
_LEVELS = {"read": 1, "write": 2, "admin": 3}


def permission_gaps(org: str, slug: str, run: Run) -> list[str]:
    """
    Return one MANUAL line per step the release bot ``slug`` still needs in ``org``.

    Empty when the bot is installed on ``org`` and holds every permission
    at least at the level `releasebot.PERMISSIONS` names. The installation's
    permissions are the accepted ones: a permission added to the app but not
    yet accepted by an org owner still counts as missing.
    Raises ValueError for a slug of another shape, and what ``run`` raises.
    """
    if not SLUG.fullmatch(slug):
        msg = f"release bot slug={slug!r} is not an app slug"
        raise ValueError(msg)
    out = run(
        [
            *("gh", "api", "--paginate", f"orgs/{org}/installations"),
            *("--jq", f'.installations[] | select(.app_slug == "{slug}") | .permissions | tojson'),
        ],
        None,
    )
    found = [line for line in out.splitlines() if line.strip()]
    if not found:
        return [
            f"MANUAL  release bot {slug} is not installed on {org}: "
            f"install it on all repositories at {install_url(slug)}"
        ]
    held = json.loads(found[0])
    if not isinstance(held, dict):
        msg = f"the installation of {slug} answered permissions that are not an object"
        raise ValueError(msg)
    pages = f"https://github.com/organizations/{org}/settings"
    return [
        f"MANUAL  release bot {slug} lacks {name}: {level} (holds {held.get(name) or 'none'}): "
        f"add it at {pages}/apps/{slug}/permissions, then accept it at {pages}/installations"
        for name, level in PERMISSIONS.items()
        if _LEVELS.get(str(held.get(name, "")), 0) < _LEVELS[level]
    ]
