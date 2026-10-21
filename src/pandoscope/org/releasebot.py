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

import hmac
import html
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit
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


def listen(state: str, timeout: float = 600) -> Callback:
    """
    Open a callback on 127.0.0.1 for the flow that sent ``state``.

    Its ``wait`` serves the page at ``/``, ignores every request but the
    redirect with this ``state``, and returns that redirect's code.
    Raises TimeoutError from ``wait`` when no code arrives within ``timeout`` seconds.
    """
    return _LocalCallback(state, timeout)


class _LocalCallback:
    """One-shot HTTP endpoint on 127.0.0.1; the port is the system's choice."""

    def __init__(self, state: str, timeout: float) -> None:
        self._state = state
        self._timeout = timeout
        self._page = ""
        self._code: str | None = None
        self._server = HTTPServer(("127.0.0.1", 0), self._handler())
        self._server.timeout = 1
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - the http.server hook name
                if urlsplit(self.path).path == "/":
                    self._answer(200, outer._page)
                    return
                code = callback_code(self.path, outer._state)
                if code is None:
                    self._answer(400, "This is not the release bot's callback.")
                    return
                outer._code = code
                self._answer(200, "The app exists. Back to the terminal.")

            def _answer(self, status: int, text: str) -> None:
                body = text.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                """Keep the terminal quiet: the command prints what matters."""

        return Handler

    def wait(self, page: str) -> str:
        """Serve ``page`` until the callback brings this flow's code; return it."""
        self._page = page
        deadline = time.monotonic() + self._timeout
        try:
            while self._code is None:
                if time.monotonic() > deadline:
                    msg = f"no callback reached {self.url} within {self._timeout} s"
                    raise TimeoutError(msg)
                self._server.handle_request()
        finally:
            self._server.server_close()
        return self._code


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
    action = (
        f"https://github.com/organizations/{quote(org)}/settings/apps/new"
        f"?state={quote(state)}"
    )
    value = html.escape(json.dumps(app_manifest), quote=True)
    return (
        "<!doctype html><meta charset=utf-8><title>Create the release bot</title>"
        f'<form id="create" action="{html.escape(action, quote=True)}" method="post">'
        f'<input type="hidden" name="manifest" value="{value}">'
        "<p>Sending the release bot's manifest to GitHub…</p>"
        '<button type="submit">Continue to GitHub</button>'
        "</form>"
        '<script>document.getElementById("create").submit()</script>'
    )


def callback_code(path: str, state: str) -> str | None:
    """
    Return the code a request for ``path`` carries, or None.

    Only ``/callback`` with the expected ``state`` and a code counts.
    """
    # DECISION:SEC — a random state per flow, compared in constant time:
    # another page cannot hand this flow a code for an app of its own.
    parts = urlsplit(path)
    if parts.path != "/callback":
        return None
    query = parse_qs(parts.query)
    given = query.get("state", [""])[0]
    code = query.get("code", [""])[0]
    if not code or not hmac.compare_digest(given, state):
        return None
    return code


def convert(code: str, run: Run) -> dict[str, Any]:
    """
    Exchange the one-time ``code`` for the new app's credentials.

    Returns GitHub's conversion: ``id``, ``slug``, ``client_id``, ``pem`` and more.
    Raises ValueError when ``code`` is not a plain token, and what ``run`` raises.
    """
    # The code goes into an API path: a plain token only, never a path or query.
    if not re.fullmatch(r"[A-Za-z0-9_-]+", code):
        msg = f"the callback's code={code!r} is not a plain token"
        raise ValueError(msg)
    out = run(["gh", "api", "--method", "POST", f"app-manifests/{code}/conversions"], None)
    conversion: dict[str, Any] = json.loads(out)
    return conversion


def check(conversion: dict[str, Any], org: str, name: str) -> None:
    """
    Make sure ``conversion`` is the app this flow asked for.

    The app must belong to ``org``, carry ``name`` and hold exactly
    ``PERMISSIONS``.
    Raises ValueError naming what differs.
    """
    # DECISION:SEC — the state alone cannot prove the code is this flow's:
    # whoever reads the local page can send a code for an app of their own.
    owner = (conversion.get("owner") or {}).get("login")
    if not isinstance(owner, str) or owner.lower() != org.lower():
        msg = f"the code belongs to an app of owner={owner!r}, not of org={org!r}"
        raise ValueError(msg)
    if conversion.get("name") != name:
        msg = f"the code belongs to app name={conversion.get('name')!r}, not {name!r}"
        raise ValueError(msg)
    if conversion.get("permissions") != PERMISSIONS:
        msg = f"the app holds permissions={conversion.get('permissions')!r}, not {PERMISSIONS!r}"
        raise ValueError(msg)


def store(secrets: Path, conversion: dict[str, Any]) -> dict[str, Any]:
    """
    Keep the app's private key and record under ``secrets``; return the record.

    The key goes to ``KEY_FILE`` with mode 0600; slug, app id and client ID go
    to ``RECORD_FILE``. The client secret is not kept.
    Raises FileExistsError when ``secrets`` already holds a key.
    """
    secrets.mkdir(parents=True, exist_ok=True)
    # DECISION:IRREV — O_EXCL: a key in use is never replaced, not even by a race;
    # replacing the app is a deliberate step (move the key away first).
    fd = os.open(secrets / KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as key:
        key.write(conversion["pem"])
    # DECISION:SEC — the client secret is not kept: no workflow uses it,
    # and a secret that is never written cannot leak.
    record = {
        "slug": conversion["slug"],
        "app_id": conversion["id"],
        "client_id": conversion["client_id"],
    }
    (secrets / RECORD_FILE).write_text(json.dumps(record, indent=2) + "\n")
    return record


def recorded(secrets: Path) -> dict[str, Any] | None:
    """Return the release bot ``store`` recorded under ``secrets``, or None."""
    path = secrets / RECORD_FILE
    if not path.exists():
        return None
    record: dict[str, Any] = json.loads(path.read_text())
    return record


def install_url(slug: str) -> str:
    """Return the page that installs the app ``slug`` on an account."""
    return f"https://github.com/apps/{quote(slug)}/installations/new"
