"""
Create an org's release-bot GitHub App through GitHub's app-manifest flow.

The flow needs two confirmations in the principal's browser and one paste:
the page `form_page` renders posts the manifest to GitHub, the principal
confirms "Create GitHub App", and GitHub redirects to the org's apps
settings page with a one-time code in the address. The principal pastes
that address into the terminal; `pasted_code` takes the code from it and
`convert` exchanges it for the app's credentials.
`store` keeps the private key where the credentials sync reads it.
Installing the app on the org has no API; `install_url` is the second
confirmation.
Flow authority: GitHub's "Registering a GitHub App from a manifest" docs.
"""

from __future__ import annotations

import contextlib
import fcntl
import hmac
import html
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit
from typing import Any

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
# GitHub's own rules: a login is 1-39 letters, digits or single inner hyphens;
# an app name is at most 34 characters.
LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}")
APP_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,33}")
# The one-time code goes into an API path: never a path or query of its own.
PLAIN_TOKEN = re.compile(r"[A-Za-z0-9_-]+")
BOARD_URL = re.compile(r"https://github\.com/orgs/[A-Za-z0-9-]+/projects/[0-9]+")
KEY_FILE = "RELEASE_BOT_PRIVATE_KEY.pem"
RECORD_FILE = "release-bot.json"


def page_file(page: str) -> Path:
    """
    Write ``page`` to a new file only the current user can read; return its path.

    The page carries the flow's state, so it never goes over the network:
    the browser opens it from this file.
    """
    # DECISION:SEC — the state ties the pasted address to this flow:
    # kept where only the principal can read it, it cannot be borrowed
    # to pass off a code for someone else's app.
    directory = Path(tempfile.mkdtemp(prefix="pandoscope-release-bot-"))
    path = directory / "create-release-bot.html"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        # The page says charset=utf-8, whatever the terminal's locale.
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(page)
    except BaseException:
        path.unlink(missing_ok=True)
        directory.rmdir()
        raise
    return path


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
    so the pasted redirect can be told from a forged or an earlier one.
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


def apps_url(org: str) -> str:
    """Return ``org``'s GitHub Apps settings page: where GitHub sends the browser back."""
    return f"https://github.com/organizations/{quote(org, safe='')}/settings/apps"


def pasted_code(url: str, org: str, state: str) -> str | None:
    """
    Return the code the address the principal pasted carries, or None.

    Only ``org``'s apps settings page on github.com with this flow's
    ``state`` and a plain-token code counts.
    """
    # DECISION:SEC — the address must be the one this flow sent GitHub to:
    # a pasted code from elsewhere, or from an earlier flow, is never exchanged.
    parts = urlsplit(url.strip())
    expected = urlsplit(apps_url(org))
    if (parts.scheme, parts.netloc, parts.path) != (expected.scheme, expected.netloc, expected.path):
        return None
    query = parse_qs(parts.query)
    codes, states = query.get("code", []), query.get("state", [])
    if len(codes) != 1 or len(states) != 1 or not PLAIN_TOKEN.fullmatch(codes[0]):
        return None
    # Bytes: compare_digest refuses non-ASCII strings with a TypeError.
    if not hmac.compare_digest(states[0].encode(), state.encode()):
        return None
    return codes[0]


def convert(code: str, run: Run) -> dict[str, Any]:
    """
    Exchange the one-time ``code`` for the new app's credentials.

    Returns GitHub's conversion: ``id``, ``slug``, ``client_id``, ``pem`` and more.
    Raises ValueError when ``code`` is not a plain token, and what ``run`` raises.
    """
    if not PLAIN_TOKEN.fullmatch(code):
        msg = f"the code={code!r} is not a plain token"
        raise ValueError(msg)
    # DECISION:SEC — gh's debug log (GH_DEBUG=api, or the older DEBUG)
    # prints response bodies, and this response holds the private key.
    try:
        out = run(
            [
                *("env", "-u", "GH_DEBUG", "-u", "DEBUG"),
                *("gh", "api", "--method", "POST", f"app-manifests/{code}/conversions"),
            ],
            None,
        )
    except RuntimeError as error:
        # DECISION:SEC — the failed command names the code, which stays valid
        # for an hour: the error says what failed without it, and drops the chain.
        raise RuntimeError(str(error).replace(code, "«code»")) from None
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


def store(secrets: Path, conversion: dict[str, Any], org: str) -> dict[str, Any]:
    """
    Keep ``org``'s app's private key and record under ``secrets``; return the record.

    The key goes to ``KEY_FILE`` with mode 0600; org, slug, app id and client
    ID go to ``RECORD_FILE``, first. The client secret is not kept.
    Raises ValueError naming the field when the conversion lacks the key or
    holds a slug, app id or client ID of another shape, before anything is
    written, and FileExistsError when ``secrets`` already holds a key.
    """
    record = _valid_record(
        {
            "org": org,
            "slug": conversion.get("slug"),
            "app_id": conversion.get("id"),
            "client_id": conversion.get("client_id"),
        }
    )
    pem = conversion.get("pem")
    if not isinstance(pem, str) or not pem.strip():
        msg = "the conversion carries no private key"
        raise ValueError(msg)
    secrets.mkdir(mode=0o700, parents=True, exist_ok=True)
    _own_private_directory(secrets)
    key = secrets / KEY_FILE
    # DECISION:SEC — one store per directory at a time, and the key checked
    # again under the lock: two runs that both found the empty placeholder
    # would otherwise both replace it, and the first app's key would be lost.
    with _locked(secrets):
        if key_in_use(secrets):
            msg = f"{key} already holds a release-bot key"
            raise FileExistsError(msg)
        # DECISION:SEC — the client secret is not kept: no workflow uses it,
        # and a secret that is never written cannot leak.
        # The record goes first: if the key then fails, a rerun finds no key
        # in the way and writes both again.
        _place(secrets, secrets / RECORD_FILE, json.dumps(record, indent=2) + "\n", replace=True)
        # DECISION:IRREV — the key is written to a temp file and linked into
        # place: link refuses any existing entry (a key in use, a symlink), and
        # a crash leaves no half-written key. Replacing the app is a deliberate
        # step (move the key away first). Only the empty placeholder the
        # credentials seed lays out is replaced.
        _place(secrets, key, pem, replace=is_placeholder(key))
    return record


@contextlib.contextmanager
def _locked(directory: Path) -> Iterator[None]:
    """Hold an exclusive lock on ``directory`` for the duration."""
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


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


def recorded(secrets: Path, org: str) -> dict[str, Any] | None:
    """Return the release bot ``store`` recorded for ``org`` under ``secrets``, or None."""
    path = secrets / RECORD_FILE
    if not path.exists():
        return None
    record = json.loads(path.read_text())
    if not isinstance(record, dict):
        msg = f"the release bot record in {path} is not an object"
        raise ValueError(msg)
    valid = _valid_record(record)
    if valid["org"].lower() != org.lower():
        msg = f"the release bot record in {path} is for org={valid['org']!r}, not {org!r}"
        raise ValueError(msg)
    return valid


def _valid_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return ``record`` if org, slug, app id and client ID have GitHub's shapes."""
    org = record.get("org")
    if not isinstance(org, str) or not LOGIN.fullmatch(org):
        msg = f"release bot org={org!r} is not an org login"
        raise ValueError(msg)
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
    return {"org": org, "slug": slug, "app_id": app_id, "client_id": client_id}


def lost_key_note(conversion: dict[str, Any], org: str, key: Path) -> str:
    """
    Return what to do when a converted app's key could not be kept.

    An app of ``org`` stays behind with no key on disk: its settings page
    can generate a new key or delete the app. A code for an app outside
    ``org`` left nothing behind in the org.
    """
    owner = (conversion.get("owner") or {}).get("login")
    slug = conversion.get("slug")
    if not isinstance(owner, str) or owner.lower() != org.lower():
        return f"That code was for an app outside {org}; nothing was kept."
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        page = f"https://github.com/organizations/{quote(org, safe='')}/settings/apps"
    else:
        page = f"https://github.com/organizations/{quote(org, safe='')}/settings/apps/{slug}"
    return (
        f"The app now exists in {org}, but its key was not kept. "
        f"Generate a new private key at {page} and save it as {key}, or delete the app there."
    )


def unconverted_note(org: str, name: str, key: Path) -> str:
    """Return what to do when the flow stopped before the app's key was in hand."""
    return (
        f"If GitHub created {name}, it is listed at {apps_url(org)}: delete it there before "
        f"running this again, or generate a private key there and save it as {key}."
    )


def install_url(slug: str) -> str:
    """Return the page that installs the app ``slug`` on an account."""
    return f"https://github.com/apps/{quote(slug, safe='')}/installations/new"
