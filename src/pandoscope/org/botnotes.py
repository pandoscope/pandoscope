"""
What `org release-bot` tells the owner when a run stops: where the app is and what to do with it.

Each note matches one situation: the app refused, not yet checked, its key
lost, another app's key in the way, the key kept, or the code never exchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pandoscope.org import releasebot


def refused_note(conversion: dict[str, Any], org: str, name: str) -> str:
    """Return what to do with an app `check` refused: delete it, never keep a key for it."""
    login = releasebot.owner(conversion)
    if login is not None and login.lower() != org.lower():
        return (
            f"That code was for an app outside {org}: someone else knew this run's state. "
            f"If GitHub created {name}, delete it at {releasebot.apps_url(org)} and run again."
        )
    created = conversion.get("name")
    if login is not None and created != name and conversion.get("permissions") == releasebot.PERMISSIONS:
        rerun = created if isinstance(created, str) and releasebot.APP_NAME.fullmatch(created) else "<a free name>"
        return (
            f"The app was created as {created!r}, not {name!r}: its name was changed on GitHub's page. "
            f"Delete it at {_app_page(conversion, org)} and run again with --name {rerun}."
        )
    return (
        f"GitHub created an app in {org} that is not the one asked for: "
        f"delete it at {_app_page(conversion, org)} and run again; keep no key for it."
    )


def lost_key_note(
    conversion: dict[str, Any], org: str, key: Path, *, key_in_use: bool = False, recorded: bool = True
) -> str:
    """
    Return what to do when the checked app's key could not be kept.

    The app stays behind with no key on disk: its settings page can
    generate a new key or delete the app; with ``key_in_use``, another
    app's key is at ``key``, so only deleting is right. Without ``recorded``,
    org init needs the app named by its flags.
    """
    page = _app_page(conversion, org)
    if key_in_use:
        return (
            f"The app now exists in {org}, but {key} already holds another app's key, "
            f"which stays as it is. Delete this run's app at {page}."
        )
    note = (
        f"The app now exists in {org}, but its key was not kept. "
        f"Generate a new private key at {page} and save it as {key}, or delete the app there."
    )
    if not recorded:
        note += (
            " No record was kept either: give org init the app's slug and client ID"
            " from that page with --release-bot-app and --release-bot-client-id."
        )
    return note


def unchecked_note(conversion: dict[str, Any], org: str) -> str:
    """Return what to do when the run stopped before the converted app was checked."""
    return (
        f"The run stopped before the new app was checked, and its key was not kept: "
        f"delete it at {_app_page(conversion, org)} and run again."
    )


def kept_note(conversion: dict[str, Any], org: str, key: Path) -> str:
    """Return what to do when the run stopped after the key was kept."""
    return (
        f"{key} holds the new app's key, but the run stopped before it finished. "
        f"Install it on {org}, all repositories: {releasebot.install_url(str(conversion['slug']))}"
    )


def _app_page(conversion: dict[str, Any], org: str) -> str:
    """The app's settings page in ``org``, or the org's apps page when the slug is odd."""
    slug = conversion.get("slug")
    if isinstance(slug, str) and releasebot.SLUG.fullmatch(slug):
        return f"{releasebot.apps_url(org)}/{slug}"
    return releasebot.apps_url(org)


def unconverted_note(org: str, name: str, key: Path) -> str:
    """Return what to do when the flow stopped before the app's key was in hand."""
    # A key someone else fetched with the code stays valid until the app is gone:
    # a new key would not revoke it.
    return (
        f"If GitHub created {name}, delete it at {releasebot.apps_url(org)} before running this again: "
        f"a key fetched with its code stays valid until the app is deleted. Nothing was saved to {key}."
    )
