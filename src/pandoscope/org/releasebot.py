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
import stat
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
# The slug and client ID end up inside a bash file the credentials sync
# sources, and in URLs: only what GitHub issues, never a quote or a $.
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
CLIENT_ID = re.compile(r"[A-Za-z0-9.]+")
KEY_FILE = "RELEASE_BOT_PRIVATE_KEY.pem"
RECORD_FILE = "release-bot.json"


class Callback(Protocol):
    """A local endpoint GitHub redirects the browser back to."""

    url: str

    def wait(self) -> str:
        """Return the code the first ``/callback`` with this flow's state brings."""
        ...

    def close(self) -> None:
        """Release the port; until then no one else can bind it."""
        ...


def page_file(page: str) -> Path:
    """
    Write ``page`` to a new file only the current user can read; return its path.

    The page carries the flow's state, so it never goes over the network:
    the browser opens it from this file.
    """
    # DECISION:SEC — the state is the flow's only secret: served over the
    # local server, any local peer could read it, end the flow with a junk
    # code and catch the real one on the freed port.
    directory = Path(tempfile.mkdtemp(prefix="pandoscope-release-bot-"))
    path = directory / "create-release-bot.html"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(page)
    return path


def listen(state: str, timeout: float = 600, read_timeout: float = 5) -> Callback:
    """
    Open a callback on 127.0.0.1 for the flow that sent ``state``.

    It answers only ``/callback`` and returns, from ``wait``, the code of the
    first redirect with this ``state``. The port stays taken until ``close``.
    Raises TimeoutError from ``wait`` when no code arrives within ``timeout`` seconds.
    ``read_timeout`` bounds how long one connection may take to send its request.
    """
    return _LocalCallback(state, timeout, read_timeout)


class _QuietServer(ThreadingHTTPServer):
    """A request that fails is the peer's problem: no traceback on the owner's terminal."""

    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Drop the error; the peer's connection closes."""


class _LocalCallback:
    """HTTP endpoint on 127.0.0.1, one thread per request; the port is the system's choice."""

    def __init__(self, state: str, timeout: float, read_timeout: float) -> None:
        self._state = state
        self._timeout = timeout
        self._read_timeout = read_timeout
        self._code: str | None = None
        self._lock = threading.Lock()
        self._arrived = threading.Event()
        self._server = _QuietServer(("127.0.0.1", 0), self._handler())
        self._host = f"127.0.0.1:{self._server.server_address[1]}"
        self.url = f"http://{self._host}"
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True
        )
        self._thread.start()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            # A peer that connects and sends nothing must not keep its thread forever.
            timeout = outer._read_timeout

            def do_GET(self) -> None:  # noqa: N802 - the http.server hook name
                # DECISION:SEC — only requests addressed to this very host and
                # port: a DNS-rebound name in the browser gets nothing.
                if self.headers.get("Host") != outer._host:
                    self._answer(400, "Wrong host.")
                    return
                if urlsplit(self.path).path != "/callback":
                    self._answer(404, "Nothing here.")
                    return
                code = callback_code(self.path, outer._state)
                if code is None:
                    self._answer(400, "This is not the release bot's callback.")
                    return
                outer._accept(code)
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

    def _accept(self, code: str) -> None:
        with self._lock:
            if self._code is None:
                self._code = code
                self._arrived.set()

    def wait(self) -> str:
        """Return the code the first redirect with this flow's state brought."""
        if not self._arrived.wait(self._timeout):
            msg = f"no callback reached {self.url} within {self._timeout} s"
            raise TimeoutError(msg)
        assert self._code is not None  # set before the event
        return self._code

    def close(self) -> None:
        """Stop answering and release the port."""
        self._server.shutdown()
        self._server.server_close()


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
        f"https://github.com/organizations/{quote(org, safe='')}/settings/apps/new"
        f"?state={quote(state, safe='')}"
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
    # Bytes: compare_digest refuses non-ASCII strings with a TypeError.
    if not code or not hmac.compare_digest(given.encode(), state.encode()):
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
    Raises ValueError naming the field when the conversion lacks the key or
    holds a slug, app id or client ID of another shape, before anything is
    written, and FileExistsError when ``secrets`` already holds a key.
    """
    record = _valid_record(
        {"slug": conversion.get("slug"), "app_id": conversion.get("id"), "client_id": conversion.get("client_id")}
    )
    pem = conversion.get("pem")
    if not isinstance(pem, str) or not pem.strip():
        msg = "the conversion carries no private key"
        raise ValueError(msg)
    secrets.mkdir(mode=0o700, parents=True, exist_ok=True)
    _own_private_directory(secrets)
    key = secrets / KEY_FILE
    # DECISION:IRREV — the key is written to a temp file and linked into
    # place: link refuses any existing entry (a key in use, a symlink), and
    # a crash leaves no half-written key. Replacing the app is a deliberate
    # step (move the key away first). Only the empty placeholder the
    # credentials seed lays out is replaced.
    _place(secrets, key, pem, replace=is_placeholder(key))
    # DECISION:SEC — the client secret is not kept: no workflow uses it,
    # and a secret that is never written cannot leak.
    _place(secrets, secrets / RECORD_FILE, json.dumps(record, indent=2) + "\n", replace=True)
    return record


def is_placeholder(key: Path) -> bool:
    """Return whether ``key`` is the empty file the credentials seed lays out."""
    try:
        info = key.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISREG(info.st_mode) and info.st_size == 0


def key_in_use(secrets: Path) -> bool:
    """Return whether ``secrets`` holds a release-bot key: anything but a placeholder."""
    key = secrets / KEY_FILE
    return os.path.lexists(key) and not is_placeholder(key)


def _own_private_directory(directory: Path) -> None:
    """
    Make sure ``directory`` is the current user's own, then make it 0700.

    Raises ValueError when it is a symlink, not a directory, owned by
    someone else, or writable by group or others: whoever can write it can
    swap the key's temp file.
    """
    info = directory.lstat()
    if stat.S_ISLNK(info.st_mode):
        msg = f"secrets directory {directory} is a symlink"
        raise ValueError(msg)
    if not stat.S_ISDIR(info.st_mode):
        msg = f"secrets path {directory} is not a directory"
        raise ValueError(msg)
    if info.st_uid != os.getuid():
        msg = f"secrets directory {directory} belongs to uid {info.st_uid}, not to you"
        raise ValueError(msg)
    if info.st_mode & 0o022:
        msg = f"secrets directory {directory} is writable by group or others"
        raise ValueError(msg)
    os.chmod(directory, 0o700)


def _place(directory: Path, path: Path, text: str, *, replace: bool) -> None:
    """
    Write ``text`` to ``path`` (mode 0600) through a temp file in ``directory``.

    Raises ValueError when the temp file is no longer the file written
    (swapped, for a symlink or another file) before it is put in place.
    """
    fd, temp = tempfile.mkstemp(dir=directory, prefix=".pandoscope-")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
            handle.flush()
            written = os.fstat(handle.fileno())
        current = os.lstat(temp)
        if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != (
            written.st_dev,
            written.st_ino,
        ):
            msg = f"the temp file {temp} was replaced before it was put in place"
            raise ValueError(msg)
        if replace:
            os.replace(temp, path)
        else:
            os.link(temp, path, follow_symlinks=False)
    finally:
        if os.path.lexists(temp):
            os.unlink(temp)


def recorded(secrets: Path) -> dict[str, Any] | None:
    """Return the release bot ``store`` recorded under ``secrets``, or None."""
    path = secrets / RECORD_FILE
    if not path.exists():
        return None
    return _valid_record(json.loads(path.read_text()))


def _valid_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return ``record`` if slug, app id and client ID have GitHub's shapes."""
    slug, app_id, client_id = record.get("slug"), record.get("app_id"), record.get("client_id")
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        msg = f"release bot slug={slug!r} is not an app slug"
        raise ValueError(msg)
    if not isinstance(app_id, int) or isinstance(app_id, bool) or app_id <= 0:
        msg = f"release bot app_id={app_id!r} is not an app id"
        raise ValueError(msg)
    if not isinstance(client_id, str) or not CLIENT_ID.fullmatch(client_id):
        msg = f"release bot client_id={client_id!r} is not a client ID"
        raise ValueError(msg)
    return {"slug": slug, "app_id": app_id, "client_id": client_id}


def install_url(slug: str) -> str:
    """Return the page that installs the app ``slug`` on an account."""
    return f"https://github.com/apps/{quote(slug, safe='')}/installations/new"
