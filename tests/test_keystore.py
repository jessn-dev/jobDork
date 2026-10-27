"""Keys kept in the computer's keychain when you choose it, and held in
memory otherwise (core/keystore.py). A pretend keychain (tests/conftest.py):
no test reaches a real one."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jobdork.ai import llm  # noqa: E402
from jobdork.core import config, keystore  # noqa: E402
from jobdork.web import api  # noqa: E402

GEMINI = "AIzaFakeKeyForTests0123456789"


def _fresh():
    llm.VAULT.wipe()
    keystore.forget_all()
    for n in config.SOURCE_KEY_NAMES:
        os.environ.pop(n, None)
    config.APP_KEYS.clear()


def _config(tmp: str, extra: str = "") -> config.Config:
    os.chdir(tmp)
    Path("config.yaml").write_text("titles: {include: [nurse]}\nlocations: {countries: [US]}\n"
                                   "llm: {readers: [{provider: gemini, model: g}]}\n" + extra)
    return config.load()


def test_an_ai_key_is_kept_only_when_you_chose_it_and_comes_back_after_a_wipe():
    here = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _fresh()
            _config(tmp)
            api.llm_key("gemini", GEMINI)
            assert keystore.load("ai:gemini") == ""          # not chosen: memory only
            llm.VAULT.wipe()
            assert llm.key_for("gemini") == ("", "")

            cfg = _config(tmp, "remember_keys: true\n")
            assert api.llm_key("gemini", GEMINI)["note"].startswith("kept")
            llm.VAULT.wipe()                                 # the idle wipe, or a restart
            assert llm.key_for("gemini") == (GEMINI, "keychain")
            assert api.keys_state(cfg)["missing"] == []

            api.llm_forget("gemini")                         # Forget takes the kept copy too
            assert keystore.load("ai:gemini") == "" and llm.key_for("gemini") == ("", "")
            assert [m["name"] for m in api.keys_state(cfg)["missing"]] == ["gemini"]
    finally:
        os.chdir(here)
        _fresh()
        keystore.remembering = False


def test_turning_remember_on_keeps_the_keys_held_now_and_off_removes_them():
    _fresh()
    llm.VAULT.put("groq", "gsk_FakeKeyForTests012345")
    os.environ["ADZUNA_APP_KEY"] = "k3y"
    config.APP_KEYS.add("ADZUNA_APP_KEY")
    try:
        assert "Kept 2 keys" in api.remember_keys_changed(True)
        assert keystore.load("ai:groq") and keystore.load("ADZUNA_APP_KEY") == "k3y"
        api.remember_keys_changed(False)
        assert keystore.load("ai:groq") == "" and keystore.load("ADZUNA_APP_KEY") == ""
        assert llm.VAULT.get("groq")                         # still held this run
    finally:
        _fresh()


def test_an_old_plain_keys_file_is_moved_to_the_keychain_or_dropped_and_deleted():
    """0.15.1 and before kept job-source keys in data/source-keys.env."""
    here = os.getcwd()
    try:
        for keep in (True, False):
            with tempfile.TemporaryDirectory() as tmp:
                _fresh()
                old = Path(tmp) / "data" / config.SOURCE_KEYS_FILE
                old.parent.mkdir()
                old.write_text("ADZUNA_APP_ID=abc\nADZUNA_APP_KEY=k3y\n")
                cfg = _config(tmp)
                assert cfg.legacy_keys_file and os.environ["ADZUNA_APP_KEY"] == "k3y"
                assert api.keys_state(cfg)["legacy"]
                out = api.legacy_keys(cfg, keep)
                assert not old.exists()                      # never left in plain text
                assert (keystore.load("ADZUNA_APP_KEY") == "k3y") is keep
                assert out["moved"] == (["ADZUNA_APP_ID", "ADZUNA_APP_KEY"] if keep else [])
                assert config.load().remember_keys is keep
    finally:
        os.chdir(here)
        _fresh()
        keystore.remembering = False


def test_a_container_has_no_keychain_and_says_so():
    saved, os.environ[config.CONTAINER_ENV] = keystore._backend, "1"
    keystore._backend = None
    try:
        assert "container" in keystore.unavailable()
        try:
            keystore.save("ai:groq", "x" * 20)
        except keystore.KeystoreError as exc:
            assert "container" in str(exc)
        else:
            raise AssertionError("saved with no keychain")
        assert keystore.load("ai:groq") == ""
    finally:
        keystore._backend = saved
        os.environ.pop(config.CONTAINER_ENV, None)


def test_a_key_is_never_written_to_the_config():
    here = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _fresh()
            _config(tmp, "remember_keys: true\n")
            api.llm_key("gemini", GEMINI)
            assert GEMINI not in Path("config.yaml").read_text()
            assert not list(Path(tmp).rglob("*.env"))
    finally:
        os.chdir(here)
        _fresh()
        keystore.remembering = False
