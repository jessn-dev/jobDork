"""
Free-tier limits, kept to rather than run into.

Not everyone can pay for a plan, and a free Gemini or Groq key has a
per-minute and a per-day limit. The limits are set per account and per
model and change without notice: Google shows them in AI Studio, Groq in
its console, and neither publishes one table to copy (checked 2026-10-28).
So there is no table of numbers here: jobdork reads what each provider
says as it goes.

- **Groq** reports, with every answer, the requests left today and the
  tokens left this minute (`x-ratelimit-*` headers). A call waits out the
  minute when the tokens left would not cover it, and background work (a
  scan reading job posts) stops while a few requests are still left today,
  kept back for what you ask for yourself.
- **Gemini** says nothing until it refuses. Its refusal names the quota
  (`...PerMinute...` or `...PerDay...`), its size and how long to wait. A
  per-minute refusal is waited out and the call made again, once, and its
  size learned, so later calls are spaced to stay under it. A per-day one
  stops that model until the quota resets, midnight Pacific time, and its
  size is learned too, so the next day stops short of it.
- **A daily limit you set** (llm.daily_limits, from what AI Studio or the
  Groq console shows you): background work stops short of it.

A stopped model raises LLMError naming the limit and when it resets, with
"rate limited" in it, so the next reader in your list answers instead and
the Dashboard counts it as rate limited. Held in memory: a restart forgets
what was learned, and the provider's next refusal teaches it again.
"""

from __future__ import annotations

import contextlib
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Which providers have a free tier worth guarding. Anthropic and OpenAI keys
# are paid by use: their limits are not a daily allowance running out.
FREE_TIER = ("gemini", "groq")
PACIFIC = ZoneInfo("America/Los_Angeles")      # where Gemini's day turns over
# Requests a day kept back from background work, for what you ask yourself.
RESERVE = 5
MAX_WAIT = 65            # seconds; a longer wait is not made, the call fails
# Purposes that are background work: they stop first. The rest (a letter,
# a review, Save and test) may use the reserve.
BACKGROUND = ("judge", "second_opinion", "page_read", "listing", "guard_verify",
              "suggest")


@dataclass
class _Model:
    label: str = ""
    day: str = ""                    # the provider's day the counts are for
    calls: int = 0                   # made today, by this jobdork
    per_day: int = 0                 # the daily limit, learned or set; 0 unknown
    per_minute: int = 0              # learned from a refusal; 0 unknown
    left_today: int | None = None    # Groq's count, from its last answer
    tokens_left: int | None = None   # Groq's tokens left this minute
    tokens_back: float = 0.0         # when they are back (time.time())
    requests_back: float = 0.0       # when Groq's day's requests are back
    stopped_until: float = 0.0       # no calls before this
    why: str = ""                    # what stopped it
    last_call: float = 0.0


_lock = threading.Lock()
_models: dict[tuple[str, str], _Model] = {}
# The daily limits you set (llm.daily_limits), by provider.
_set_by_you: dict[str, int] = {}
_sleep = time.sleep
_now = time.time


def set_daily_limits(limits: dict) -> None:
    """From the config: {provider: requests a day}. 0 or absent: none set."""
    with _lock:
        _set_by_you.clear()
        _set_by_you.update({p: int(n) for p, n in (limits or {}).items() if int(n or 0) > 0})


def _day(provider: str, at: float) -> str:
    if provider == "gemini":
        return datetime.fromtimestamp(at, PACIFIC).strftime("%Y-%m-%d")
    return time.strftime("%Y-%m-%d", time.gmtime(at))


def _next_day(provider: str, at: float) -> float:
    """When the provider's day turns over: midnight Pacific for Gemini; for
    Groq the time its own answer gave is used instead, this only a fallback."""
    if provider == "gemini":
        here = datetime.fromtimestamp(at, PACIFIC)
        return (here.replace(hour=0, minute=0, second=0, microsecond=0)
                + timedelta(days=1)).timestamp()
    return at + 24 * 3600


def _state(provider: str, model: str, label: str) -> _Model:
    m = _models.setdefault((provider, model), _Model(label=label))
    today = _day(provider, _now())
    if m.day != today:                       # a new day: counts start again
        m.day, m.calls, m.left_today = today, 0, None
        if m.stopped_until <= _now():
            m.stopped_until, m.why = 0.0, ""
    return m


def _limit(provider: str, m: _Model) -> int:
    return _set_by_you.get(provider) or m.per_day


def _when(at: float) -> str:
    """"at 15:00" today, "tomorrow at 15:00", in this computer's time."""
    then = datetime.fromtimestamp(at)
    if then.date() == datetime.now().date():
        return f"at {then:%H:%M}"
    return f"tomorrow at {then:%H:%M}" if then.date() == (
        datetime.now() + timedelta(days=1)).date() else f"on {then:%d %b at %H:%M}"


def before(provider: str, model: str, label: str, purpose: str = "",
           need_tokens: int = 0) -> None:
    """Called before each call. Waits when the minute's allowance would be
    exceeded; raises LLMError when the day's is spent. Free-tier providers
    only; any other returns at once."""
    from .llm import LLMError

    if provider not in FREE_TIER:
        return
    background = purpose in BACKGROUND
    wait = 0.0
    with _lock:
        m = _state(provider, model, label)
        now = _now()
        if m.stopped_until > now:
            raise LLMError(f"rate limited: {m.why}; {label} is asked again "
                           f"{_when(m.stopped_until)}")
        limit = _limit(provider, m)
        left = m.left_today if m.left_today is not None else (
            limit - m.calls if limit else None)
        # Not a stop: what you ask yourself may still use the reserve.
        if left is not None and left <= (RESERVE if background else 0):
            back = m.requests_back if m.left_today is not None and m.requests_back > now \
                else _next_day(provider, now)
            raise LLMError(
                f"rate limited: {left} free requests left today on {label}, kept back "
                f"for what you ask yourself; background work goes on {_when(back)}"
                if background else
                f"rate limited: no free requests left today on {label}; asked again {_when(back)}")
        # Under the minute's allowance: spaced evenly once its size is known,
        # and Groq's tokens left waited for when they would not cover this.
        if m.per_minute:
            wait = max(wait, m.last_call + 60 / m.per_minute - now)
        if m.tokens_left is not None and need_tokens and m.tokens_left < need_tokens:
            wait = max(wait, m.tokens_back - now)
        m.last_call = now + max(wait, 0)
    if wait > MAX_WAIT:
        raise LLMError(f"rate limited: {label} would have to wait {wait:.0f}s for its "
                       "free per-minute allowance")
    if wait > 0:
        _sleep(wait)


def _seconds(text: str) -> float:
    """"1m26.4s", "7.66s", "320ms", "2h0m3s" -> seconds; 0 when unreadable."""
    total, found = 0.0, False
    for value, unit in re.findall(r"([\d.]+)\s*(ms|h|m|s)", text or ""):
        try:
            number = float(value)
        except ValueError:
            continue
        found = True
        total += number * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[unit]
    return total if found else 0.0


def answered(provider: str, model: str, label: str, headers) -> None:
    """After a call the provider answered: count it, and read Groq's counts."""
    if provider not in FREE_TIER:
        return
    with _lock:
        m = _state(provider, model, label)
        m.calls += 1
        if provider != "groq":
            return
        def num(name):
            try:
                return int(float(headers.get(name, "")))
            except (TypeError, ValueError):
                return None
        left, limit = num("x-ratelimit-remaining-requests"), num("x-ratelimit-limit-requests")
        if left is not None:
            m.left_today = left
            m.requests_back = _now() + _seconds(headers.get("x-ratelimit-reset-requests", ""))
        if limit:
            m.per_day = limit
        tokens = num("x-ratelimit-remaining-tokens")
        if tokens is not None:
            m.tokens_left = tokens
            m.tokens_back = _now() + _seconds(headers.get("x-ratelimit-reset-tokens", ""))


def _gemini_refusal(body: dict) -> tuple[str, int, float]:
    """(per "day" or "minute" or "", the quota's size, seconds to wait)."""
    kind, size, wait = "", 0, 0.0
    for detail in ((body or {}).get("error") or {}).get("details") or []:
        if not isinstance(detail, dict):
            continue
        for v in detail.get("violations") or []:
            quota = str((v or {}).get("quotaId") or "")
            kind = "day" if "PerDay" in quota else "minute" if "PerMinute" in quota else kind
            with contextlib.suppress(TypeError, ValueError):
                size = int(v.get("quotaValue") or 0) or size
        if "retryDelay" in detail:
            wait = _seconds(str(detail["retryDelay"]))
    return kind, size, wait


def _groq_refusal(message: str, headers) -> tuple[str, int, float]:
    """Groq names it in words: "... on requests per day (RPD): Limit 1000,
    Used 1000, Requested 1. Please try again in 1m26.4s."."""
    kind = ("day" if re.search(r"per day|\(RPD\)|\(TPD\)", message or "")
            else "minute" if re.search(r"per minute|\(RPM\)|\(TPM\)", message or "") else "")
    found = re.search(r"Limit (\d+)", message or "")
    size = int(found.group(1)) if found else 0
    found = re.search(r"try again in ([\d.hms]+)", message or "")
    wait = _seconds(found.group(1)) if found else 0.0
    with contextlib.suppress(TypeError, ValueError):
        wait = wait or float(headers.get("retry-after", "") or 0)
    return kind, size, wait


def refused(provider: str, model: str, label: str, resp) -> float:
    """After a 429: the seconds to wait before asking once more, or 0 when
    not to ask again (the day's allowance is spent, or the wait too long)."""
    if provider not in FREE_TIER:
        return 0.0
    try:
        body = resp.json()
    except ValueError:
        body = {}
    message = str(((body or {}).get("error") or {}).get("message") or resp.text or "")
    kind, size, wait = (_gemini_refusal(body) if provider == "gemini"
                        else _groq_refusal(message, resp.headers))
    with _lock:
        m = _state(provider, model, label)
        now = _now()
        if kind == "day":
            if size and provider == "gemini":
                m.per_day = size
            m.stopped_until = now + wait if wait > MAX_WAIT else _next_day(provider, now)
            m.why = (f"the free daily limit{f' of {size} requests' if size else ''} "
                     f"on {label} is used up")
            return 0.0
        if kind == "minute" and size and provider == "gemini":
            m.per_minute = size
        if 0 < wait <= MAX_WAIT or (kind == "minute" and not wait):
            return wait or 60.0
        if wait > MAX_WAIT:
            m.stopped_until, m.why = now + wait, f"{label} asked to wait {wait:.0f}s"
        return 0.0


def stopped(provider: str, model: str) -> str:
    """Why a model is stopped now, with when it is asked again; "" if not."""
    with _lock:
        m = _models.get((provider, model))
        if not m or m.stopped_until <= _now():
            return ""
        return f"{m.why}; asked again {_when(m.stopped_until)}"


def snapshot() -> list[dict]:
    """Each free-tier model used since jobdork started, for the AI page."""
    with _lock:
        out = []
        for (provider, model), m in sorted(_models.items()):
            _state(provider, model, m.label)
            limit = _limit(provider, m)
            out.append({
                "provider": provider, "model": model, "label": m.label,
                "calls_today": m.calls,
                "left_today": m.left_today if m.left_today is not None
                              else (max(0, limit - m.calls) if limit else None),
                "per_day": limit or None, "per_minute": m.per_minute or None,
                "stopped": (f"{m.why}; asked again {_when(m.stopped_until)}"
                            if m.stopped_until > _now() else ""),
            })
        return out


def forget() -> None:
    """For tests: nothing learned, nothing counted."""
    with _lock:
        _models.clear()
        _set_by_you.clear()
