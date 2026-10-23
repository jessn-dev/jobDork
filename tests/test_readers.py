"""
Several AI readers (config llm.readers, ai/llm.py): asked in order, the next
one answering when the one before cannot. Nothing here calls a model.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.ai import llm
from jobdork.core import config as config_mod
from jobdork.core import setup
from jobdork.core.config import ConfigError

TITLES = "titles: {include: [nurse]}\n"


def _load(text: str):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text(TITLES + text, encoding="utf-8")
        return config_mod.load(str(path))


def _refused(text: str, words: str) -> None:
    try:
        _load(text)
    except ConfigError as exc:
        assert words in str(exc), str(exc)
    else:
        raise AssertionError(f"accepted: {text}")


def test_an_old_config_is_one_reader_and_a_list_is_several():
    cfg = _load("llm: {provider: ollama, model: gemma}\n")
    assert [(r.provider, r.model) for r in cfg.llm.readers] == [("ollama", "gemma")]
    cfg = _load("llm:\n  readers:\n    - {provider: ollama, model: small}\n"
                "    - {provider: ollama, model: big, ollama_url: 'http://box:11434/'}\n"
                "    - {provider: anthropic, model: claude}\n")
    assert [(r.provider, r.model) for r in cfg.llm.readers] == [
        ("ollama", "small"), ("ollama", "big"), ("anthropic", "claude")]
    assert cfg.llm.readers[1].ollama_url == "http://box:11434"
    # The first reader is provider and model, as everything else reads them.
    assert (cfg.llm.provider, cfg.llm.model) == ("ollama", "small")
    assert _load("").llm.readers == []


def test_too_many_twice_the_same_or_an_unknown_provider_is_refused():
    seven = "".join(f"    - {{provider: ollama, model: m{i}}}\n" for i in range(7))
    _refused("llm:\n  readers:\n" + seven, "at most 6")
    _refused("llm:\n  readers:\n    - {provider: ollama, model: a}\n"
             "    - {provider: ollama, model: a}\n", "twice")
    _refused("llm:\n  readers:\n    - {provider: mistral, model: a}\n", "mistral")


def test_the_page_writes_the_readers_and_the_first_is_provider_and_model():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text(TITLES, encoding="utf-8")
        cfg = setup.write(str(path), {"llm": {"readers": [
            {"provider": "ollama", "model": "small", "ollama_url": "http://box:11434"},
            {"provider": "ollama", "model": "big"},
            {"provider": "", "model": "ignored"}]}})
        assert [(r.provider, r.model) for r in cfg.llm.readers] == [
            ("ollama", "small"), ("ollama", "big")]
        assert cfg.llm.readers[0].ollama_url == "http://box:11434"
        assert (cfg.llm.provider, cfg.llm.model) == ("ollama", "small")
        # A model given alone (the terminal's setup) is the first reader's.
        cfg = setup.write(str(path), {"llm": {"provider": "ollama", "model": "tiny"}})
        assert [r.model for r in cfg.llm.readers] == ["tiny", "big"]
        # Off: no readers.
        cfg = setup.write(str(path), {"llm": {"readers": []}})
        assert cfg.llm.readers == [] and cfg.llm.provider == ""


def _fake_ollama(answers: dict):
    """Ollama stand-in: each model answers as `answers` says, or raises."""
    asked = []

    def call(s, system, user, schema, max_tokens, on_text=None):
        asked.append(s.model)
        result = answers[s.model]
        if isinstance(result, Exception):
            raise result
        return json.dumps(result)
    return call, asked


def test_when_the_first_reader_cannot_answer_the_next_one_does():
    cfg = _load("llm:\n  readers:\n    - {provider: ollama, model: first}\n"
                "    - {provider: ollama, model: second}\n")
    settings = llm.Settings.from_config(cfg)
    call, asked = _fake_ollama({"first": llm.LLMError("could not reach box"),
                                "second": {"ok": True}})
    saved = llm._ollama
    llm._ollama = call
    try:
        assert llm.complete_json(settings, "s", "u", {"type": "object"}) == {"ok": True}
    finally:
        llm._ollama = saved
    assert asked == ["first", "second"]
    # What it answered is recorded under the reader that answered.
    assert settings.label == "Ollama (local) · second"


def test_when_no_reader_can_answer_every_reason_is_given():
    cfg = _load("llm:\n  readers:\n    - {provider: ollama, model: first}\n"
                "    - {provider: ollama, model: second}\n")
    call, _ = _fake_ollama({"first": llm.LLMError("could not reach box"),
                            "second": llm.LLMError("rate limited or out of quota")})
    saved = llm._ollama
    llm._ollama = call
    try:
        llm.complete_json(llm.Settings.from_config(cfg), "s", "u", {"type": "object"})
    except llm.LLMError as exc:
        text = str(exc)
        assert "no AI reader could answer" in text
        assert "could not reach box" in text and "rate limited" in text
    else:
        raise AssertionError("answered")
    finally:
        llm._ollama = saved


def test_a_reader_with_no_key_is_passed_over_for_one_that_is_ready():
    llm.VAULT.wipe()
    cfg = _load("llm:\n  readers:\n    - {provider: anthropic, model: claude}\n"
                "    - {provider: ollama, model: local}\n")
    settings = llm.Settings.from_config(cfg)
    # The ready one answers first; the one with no key is still listed.
    assert (settings.provider, settings.model) == ("ollama", "local")
    assert [f.provider for f in settings.fallbacks] == ["anthropic"]
    assert settings.problem() == ""


def test_setup_allows_three_readers_and_the_ai_page_six():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_serve import _with_server

    def readers(n):
        return [{"provider": "ollama", "model": f"m{i}"} for i in range(n)]

    def check(run):
        import time
        path = Path(run.config_path)
        original = path.read_text(encoding="utf-8")
        path.write_text(original + "setup: {step: ai}\n", encoding="utf-8")
        time.sleep(0.01)                       # a new mtime, so the server reloads
        code, body = run.post_json("/api/llm", {"readers": readers(4)})
        assert code == 400 and b"at most 3" in body and b"later on the AI page" in body
        code, body = run.post_json("/api/llm", {"readers": readers(3)})
        assert code == 200 and len(json.loads(body)["readers"]) == 3
        assert json.loads(body)["max_readers"] == 3

        text = path.read_text(encoding="utf-8").replace("setup: {step: ai}\n", "")
        text = "\n".join(line for line in text.splitlines()
                          if not line.startswith("setup:") and "step: ai" not in line) + "\n"
        path.write_text(text, encoding="utf-8")
        code, body = run.post_json("/api/llm", {"readers": readers(6)})
        assert code == 200 and json.loads(body)["max_readers"] == 6
        code, body = run.post_json("/api/llm", {"readers": readers(7)})
        assert code == 400 and b"at most 6" in body
    _with_server(check)


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except BaseException:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc(limit=3)
    raise SystemExit(1 if failed else 0)
