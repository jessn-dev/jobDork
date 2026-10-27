"""
jobdork.core.keystore
=====================
Keys you chose to keep, in this computer's own encrypted store: the macOS
Keychain, Windows Credential Manager, or the Secret Service on Linux (GNOME
Keyring, KWallet), through the `keyring` package. The store encrypts them
with your login; jobdork never writes a key to a file, a log or the config.

Only when you choose it (`remember_keys`, setup's first page and Settings).
Otherwise every key, AI and job source alike, is held in memory while
jobdork runs and asked for again after it closes or updates.

Where there is no such store (a container, a Linux box with no Secret
Service, a copy without `keyring`), saving says why not, and keys come from
memory or the environment as before.

One caveat, said wherever the choice is offered: an unsigned Mac app is asked
"jobdork wants to use your keychain" once after each update; until someone
answers, a scheduled scan runs without the saved keys.
"""

from __future__ import annotations

import contextlib
import os

SERVICE = "jobdork"
# The names keys are kept under: the AI providers' and the job sources'.
AI_PREFIX = "ai:"


class KeystoreError(Exception):
    pass


# Whether you chose to keep keys (config remember_keys), as this run read it:
# AI calls look here for a key the idle wipe or a restart took out of memory.
remembering = False


# The `keyring` module, or a stand-in with get_password, set_password and
# delete_password: tests put one here so no test reaches a real keychain.
_backend = None


def _keyring():
    if _backend is not None:
        return _backend
    import keyring
    return keyring


def unavailable() -> str:
    """Why keys cannot be kept on this computer, or "" when they can."""
    from .config import CONTAINER_ENV

    if _backend is not None:
        return ""
    if os.environ.get(CONTAINER_ENV):
        return ("jobdork is running in a container, which has no keychain; give keys "
                "in the container's environment instead")
    try:
        import keyring
        from keyring.backends import fail
    except ImportError:
        return "the keyring package is not installed (pip install keyring)"
    backend = keyring.get_keyring()
    if isinstance(backend, fail.Keyring) or getattr(backend, "priority", 1) < 1:
        return ("this computer has no keychain jobdork can use; on Linux it needs a "
                "Secret Service such as GNOME Keyring or KWallet")
    return ""


def save(name: str, value: str) -> None:
    """Keep one key. Raises KeystoreError, never echoing the key."""
    why = unavailable()
    if why:
        raise KeystoreError(why)
    try:
        _keyring().set_password(SERVICE, name, value)
    except Exception as exc:                     # the store refused (denied, locked)
        raise KeystoreError(f"the keychain did not keep it: {type(exc).__name__}") from None


def load(name: str) -> str:
    """One kept key, or "" (none kept, no store, or access refused)."""
    if unavailable():
        return ""
    try:
        return _keyring().get_password(SERVICE, name) or ""
    except Exception:                            # denied or locked: ask instead
        return ""


def delete(name: str) -> None:
    if unavailable():
        return
    # Not there, or already gone: either way it is not kept.
    with contextlib.suppress(Exception):
        _keyring().delete_password(SERVICE, name)


def names() -> list[str]:
    """Every name jobdork may keep a key under."""
    from ..ai.llm import KEYED
    from .config import SOURCE_KEY_NAMES

    return [AI_PREFIX + p for p in KEYED] + list(SOURCE_KEY_NAMES)


def load_into_memory() -> list[str]:
    """Put every kept key where jobdork reads keys at run time: AI keys in
    the in-memory vault, job-source keys in this process's environment. A
    key already set in the real environment wins and is left alone. Returns
    the names loaded."""
    from ..ai.llm import VAULT

    loaded = []
    for name in names():
        value = load(name)
        if not value:
            continue
        if name.startswith(AI_PREFIX):
            provider = name[len(AI_PREFIX):]
            if not VAULT.get(provider):
                VAULT.put(provider, value)
                loaded.append(name)
        elif not os.environ.get(name):
            os.environ[name] = value
            loaded.append(name)
    return loaded


def forget_all() -> None:
    """Remove every key jobdork kept (Settings, Forget saved keys; uninstall)."""
    for name in names():
        delete(name)
