"""
Create an org's release-bot GitHub App through GitHub's app-manifest flow.

The flow needs two confirmations in the principal's browser and nothing else:
the page `form_page` renders posts the manifest to GitHub, the principal
confirms "Create GitHub App", and GitHub redirects back to a local callback
with a one-time code that `convert` exchanges for the app's credentials.
`store` keeps the private key where the credentials sync reads it.
Installing the app on the org has no API; `install_url` is the second
confirmation.
Flow authority: GitHub's "Registering a GitHub App from a manifest" docs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from pandoscope.org.forge import Run

# The factory's own release bot (pandoscope-release-bot) holds these;
# every stamped workflow that mints its token needs no more.
PERMISSIONS = {
    "actions": "read",
    "contents": "write",
    "issues": "read",
    "metadata": "read",
    "pull_requests": "write",
    "workflows": "write",
}
KEY_FILE = "RELEASE_BOT_PRIVATE_KEY.pem"
RECORD_FILE = "release-bot.json"


class Callback(Protocol):
    """A local endpoint GitHub redirects the browser back to."""

    url: str

    def wait(self, page: str) -> str:
        """Serve ``page`` at ``/`` and return the code ``/callback`` receives."""
        ...


def manifest(org: str, name: str, redirect_url: str) -> dict[str, Any]:
    """
    Return the app manifest for ``org``'s release bot named ``name``.

    The app is owned by the org and installable only there, has no webhook
    and no events, and has the factory release bot's permissions.
    GitHub sends the browser to ``redirect_url`` with the one-time code.
    """
    return {
        "name": name,
        "url": f"https://github.com/{org}",
        "description": f"Release bot of the {org} org: merges, releases, template updates.",
        "public": False,
        "hook_attributes": {"url": f"https://github.com/{org}", "active": False},
        "redirect_url": redirect_url,
        "default_permissions": dict(PERMISSIONS),
        "default_events": [],
    }


def form_page(org: str, app_manifest: dict[str, Any], state: str) -> str:
    """
    Return an HTML page that posts ``app_manifest`` to ``org``'s new-app form.

    ``state`` travels with the request and comes back with the code,
    so a callback can tell its own redirect from a forged one.
    """
    raise NotImplementedError


def callback_code(path: str, state: str) -> str | None:
    """
    Return the code a request for ``path`` carries, or None.

    Only ``/callback`` with the expected ``state`` and a code counts.
    """
    raise NotImplementedError


def convert(code: str, run: Run) -> dict[str, Any]:
    """
    Exchange the one-time ``code`` for the new app's credentials.

    Returns GitHub's conversion: ``id``, ``slug``, ``client_id``, ``pem`` and more.
    Raises ValueError when ``code`` is not a plain token, and what ``run`` raises.
    """
    raise NotImplementedError


def store(secrets: Path, conversion: dict[str, Any]) -> dict[str, Any]:
    """
    Keep the app's private key and record under ``secrets``; return the record.

    The key goes to ``KEY_FILE`` with mode 0600; slug, app id and client ID go
    to ``RECORD_FILE``. The client secret is not kept.
    Raises FileExistsError when ``secrets`` already holds a key.
    """
    raise NotImplementedError


def recorded(secrets: Path) -> dict[str, Any] | None:
    """Return the release bot ``store`` recorded under ``secrets``, or None."""
    raise NotImplementedError


def install_url(slug: str) -> str:
    """Return the page that installs the app ``slug`` on an account."""
    raise NotImplementedError
