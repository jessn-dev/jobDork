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

Every kept key is in one keychain item (BUNDLE), as JSON: an unsigned Mac app
is asked "jobdork wants to use your confidential information" once after
each update, for that one item, not once for each key. Keys kept one item
each, before 0.16.3, move into it the first time it is read, and their own
items are removed.

One caveat, said wherever the choice is offered: that question still comes
once after each update; until someone answers, a scheduled scan runs without
the saved keys.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading

SERVICE = "jobdork"
# The names keys are kept under: the AI providers' and the job sources'.
AI_PREFIX = "ai:"
# The one keychain item every kept key is in, under SERVICE.
BUNDLE = "keys"
# Saving and deleting read the item, change it and write it back: one at a time.
_lock = threading.Lock()


class KeystoreError(Exception):
    pass


# Whether you chose to keep keys (config remember_keys), as this run read it:
# AI calls look here for a key the idle wipe or a restart took out of memory.
remembering = False


# The names this run saved to the keychain or found there, so the page can
# say a key is kept without asking the keychain on every poll (which can
# prompt on a Mac). Removing a key takes its name out.
kept: set[str] = set()


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


def _read() -> dict[str, str]:
    """Every kept key, from the one item. Raises when the keychain refuses."""
    store = _keyring()
    raw = store.get_password(SERVICE, BUNDLE)
    if raw:
        try:
            found = json.loads(raw)
        except json.JSONDecodeError:
            found = {}
        return {str(k): str(v) for k, v in (found if isinstance(found, dict) else {}).items()
                if v}
    # None yet: keys kept one item each (before 0.16.3) move in, once.
    moved = {name: value for name in names() if (value := store.get_password(SERVICE, name))}
    if moved:
        store.set_password(SERVICE, BUNDLE, json.dumps(moved))
        for name in moved:
            with contextlib.suppress(Exception):
                store.delete_password(SERVICE, name)
    return moved


def _write(keys: dict[str, str]) -> None:
    store = _keyring()
    if keys:
        store.set_password(SERVICE, BUNDLE, json.dumps(keys))
    else:
        with contextlib.suppress(Exception):
            store.delete_password(SERVICE, BUNDLE)


def save(name: str, value: str) -> None:
    """Keep one key. Raises KeystoreError, never echoing the key."""
    why = unavailable()
    if why:
        raise KeystoreError(why)
    try:
        with _lock:
            keys = _read()
            keys[name] = value
            _write(keys)
    except Exception as exc:                     # the store refused (denied, locked)
        raise KeystoreError(f"the keychain did not keep it: {type(exc).__name__}") from None
    kept.add(name)


def _all() -> dict[str, str]:
    """Every kept key, or {} (none kept, no store, or access refused)."""
    if unavailable():
        return {}
    try:
        with _lock:
            return _read()
    except Exception:                            # denied or locked: ask instead
        return {}


def load(name: str) -> str:
    """One kept key, or "" (none kept, no store, or access refused)."""
    value = _all().get(name, "")
    if value:
        kept.add(name)
    return value


def delete(name: str) -> None:
    kept.discard(name)
    if unavailable():
        return
    # Not there, or already gone: either way it is not kept.
    with contextlib.suppress(Exception), _lock:
        keys = _read()
        if keys.pop(name, None) is not None:
            _write(keys)
    with contextlib.suppress(Exception):         # a key kept the old way, one item
        _keyring().delete_password(SERVICE, name)


def names() -> list[str]:
    """Every name jobdork may keep a key under."""
    from ..ai.llm import KEYED, OLLAMA_KEY
    from .config import SOURCE_KEY_NAMES

    return [AI_PREFIX + p for p in (*KEYED, OLLAMA_KEY)] + list(SOURCE_KEY_NAMES)


def load_into_memory() -> list[str]:
    """Put every kept key where jobdork reads keys at run time: AI keys in
    the in-memory vault, job-source keys in this process's environment. A
    key already set in the real environment wins and is left alone. Returns
    the names loaded."""
    from ..ai.llm import VAULT

    loaded, keys = [], _all()                    # one read of the one item
    for name in names():
        value = keys.get(name, "")
        if not value:
            continue
        kept.add(name)
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
    kept.clear()
    if unavailable():
        return
    for name in (BUNDLE, *names()):              # the one item, and any kept the old way
        with contextlib.suppress(Exception):
            _keyring().delete_password(SERVICE, name)
