#!/usr/bin/env python3
"""
hallucination_benchmark.py
==========================
The hallucination rate of AI verdicts, measured the way the Dashboard
measures it, on job posts you choose, without changing them.

    python scripts/hallucination_benchmark.py --db COPY.db --resume resume.pdf
    python scripts/hallucination_benchmark.py --db tech.db --db sales.db \\
        --resume a.pdf --resume b.pdf --limit 5     # every resume against each
    python scripts/hallucination_benchmark.py ... --reader ollama:gemma4:26b \\
        --checker ollama:qwen3.8:27b
    python scripts/hallucination_benchmark.py ... \\
        --reader ollama:gemma4:26b@http://pc:11434   # the reader on another computer
    python scripts/hallucination_benchmark.py --case nurse.pdf health/jobdork.db 6 \\
        --case nurse.pdf tech/jobdork.db 2      # its own field, and another
    python scripts/hallucination_benchmark.py ... --judge-only   # verdicts first
    python scripts/hallucination_benchmark.py ... --stored     # verdicts already in the DB

Each job post is judged by the reader (`llm.judge`, the same prompt a scan
uses) and the verdict checked by the checker (`guard.check`, the same
claims and rules). The rate is unsupported claims over all claims, as on
the Dashboard. `--stored` checks the verdicts the database already holds
instead of judging again: a change to the checker measured on the same text.

Verdicts are kept in `<out>/verdicts.json`, by reader and job post, so a
second run re-checks them without asking the reader again; `--rejudge`
asks again. Every claim and its verdict goes to `<out>/claims.jsonl`.

Works on a copy: give it a `sqlite3 .backup` of a database, never the one
the app uses. It opens the copy (which may migrate it) and writes nothing
else to it. Calls go to the models named, local Ollama by default; minutes
per job post on a 26B model. Run it on purpose, not in CI.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jobdork.ai import guard, judging  # noqa: E402
from jobdork.ai.llm import DEFAULT_OLLAMA_URL, LLMError, Settings  # noqa: E402
from jobdork.core.config import Freshness  # noqa: E402
from jobdork.db import grouping  # noqa: E402
from jobdork.db.store import Store  # noqa: E402
from jobdork.search import freshness  # noqa: E402
from jobdork.search import resume as resume_mod  # noqa: E402


def model(spec: str, url: str) -> Settings:
    """"ollama:gemma4:26b" -> Settings; the provider is the part before the
    first colon. "...@http://pc:11434" gives the model its own Ollama, so a
    reader on another computer runs beside the checker on this one."""
    spec, _, own = spec.partition("@")
    provider, _, name = spec.partition(":")
    return Settings(provider=provider, model=name, ollama_url=own or url)


def bucket(claim: str, verdict: str) -> str:
    """A rough kind for each flag, to see where the rate comes from."""
    low = claim.lower()
    if guard._GAP.search(claim):
        return "gap"
    if "year" in low:
        return "years"
    if any(w in low for w in ("posting", "posted", "post is", "days old", "brand new")):
        return "post age"
    if any(w in low for w in ("focus", "primarily", "mainly", "background is",
                              "fragmented", "short-term", "is a ", "is an ")):
        return "judgement"
    return "contradicted" if verdict == "contradicted" else "other"


def pick(store, limit: int) -> list[str]:
    """The job posts to judge: those judged before, so runs compare like
    with like, then the best of the rest; each with enough advert to judge."""
    judged = [r[0] for r in store.conn.execute(
        "SELECT DISTINCT uid FROM ai_outputs WHERE kind = 'judge' AND uid IS NOT NULL")]
    rest = [r["uid"] for r in store.list_roles()
            if len(r["description"] or "") >= judging.MIN_ADVERT]
    return list(dict.fromkeys(judged + rest))[:limit]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", action="append", default=[],
                    help="a COPY of a jobdork.db; repeat for several")
    ap.add_argument("--resume", action="append", default=[],
                    help="a resume; repeat for several. Each is judged against "
                         "--limit job posts from every --db")
    ap.add_argument("--case", nargs=3, action="append", default=[],
                    metavar=("RESUME", "DB", "N"),
                    help="one resume against N job posts from one database; repeat. "
                         "Pairs each resume with jobs in its own field, and a few "
                         "from another, instead of every resume with every --db")
    ap.add_argument("--reader", default="ollama:gemma4:26b")
    ap.add_argument("--checker", default="ollama:qwen3.8:27b")
    ap.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    ap.add_argument("--limit", type=int, default=5, help="job posts per resume and database")
    ap.add_argument("--stored", action="store_true",
                    help="check the verdicts the first database holds, against the "
                         "first resume; judge nothing")
    ap.add_argument("--rejudge", action="store_true")
    ap.add_argument("--judge-only", action="store_true",
                    help="fill the verdict cache and stop: one model loaded at a time")
    ap.add_argument("--out", default=str(ROOT / "out" / "hallucination"))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache_path = out / "verdicts.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    reader = model(args.reader, args.ollama_url)
    checker = model(args.checker, args.ollama_url)
    # The guard checks with the chosen checker first, as a scan does.
    writer = Settings(provider=reader.provider, model=reader.model,
                      ollama_url=reader.ollama_url, checkers=[checker])

    if args.stored:
        cases = [(args.resume[0], args.db[0], args.limit)]
    elif args.case:
        cases = [(r, d, int(n)) for r, d, n in args.case]
    else:
        cases = [(r, d, args.limit) for r in args.resume for d in args.db]
    if not cases:
        ap.error("give --resume and --db, or --case")

    claims_out = (out / "claims.jsonl").open("w", encoding="utf-8")
    total, kinds, per, per_set = Counter(), Counter(), {}, {}
    for resume_path, db, limit in cases:
        resume_text = resume_mod.load(resume_path).text
        span = resume_mod.work_span(resume_text)
        work = span.line() if span else ""
        who = Path(resume_path).stem
        # The job set by its folder (tech/, marketing/), or its file name.
        jobset = Path(db).parent.name if Path(db).stem == "jobdork" else Path(db).stem
        with Store(db) as store:
            if args.stored:
                jobs = [(r["uid"], r["text"], r["model"]) for r in store.conn.execute(
                    "SELECT uid, text, model FROM ai_outputs WHERE kind = 'judge' "
                    "ORDER BY id LIMIT ?", (limit,))]
            else:
                jobs = [(uid, None, reader.label) for uid in pick(store, limit)]
            for uid, text, label in jobs:
                row = store.get(uid)
                if row is None:
                    continue
                tag = f"{who[:24]:24} {uid}"
                posting = freshness.prompt_block(
                    row["posted_at"] or "", grouping.earliest_seen(store.conn, uid=uid),
                    Freshness())
                if text is None:
                    key = f"{reader.label}|{who}|{uid}"
                    if args.rejudge or key not in cache:
                        role = {"title": row["title"], "company": row["company"],
                                "location": row["location_raw"],
                                "description": row["description"],
                                "posting": posting, "work": work}
                        started = time.time()
                        try:
                            # As a scan does: false gaps rescored, then made reasons.
                            cache[key] = judging.judge_checked(reader, role, resume_text)
                        except LLMError as exc:
                            print(f"{tag}: judge failed: {exc}", flush=True)
                            continue
                        cache_path.write_text(json.dumps(cache, indent=1))
                        print(f"{tag}: judged in {time.time() - started:.0f}s", flush=True)
                    if args.judge_only:
                        continue
                    text = judging.verdict_text(cache[key])
                started = time.time()
                report = guard.check(writer, text, judging.guard_sources(
                    row, resume_text, posting, work))
                if not report.checked:
                    print(f"{tag}: check failed: {report.error}", flush=True)
                    total["unchecked"] += 1
                    continue
                bad = report.unsupported
                mine = per.setdefault(who, Counter())
                pair = per_set.setdefault(f"{who[:24]} x {jobset}", Counter())
                for c in (total, mine, pair):
                    c["claims"] += len(report.claims)
                    c["unsupported"] += len(bad)
                for c in report.claims:
                    kind = bucket(c.claim, c.verdict) if c.verdict != "supported" else ""
                    if kind:
                        kinds[kind] += 1
                    claims_out.write(json.dumps({
                        "resume": who, "jobs": jobset, "uid": uid, "title": row["title"],
                        "writer": label,
                        "claim": c.claim, "verdict": c.verdict, "kind": kind,
                        "source": c.source, "quote": c.quote}) + "\n")
                print(f"{tag}: {len(bad)}/{len(report.claims)} unsupported "
                      f"({time.time() - started:.0f}s, checked by {report.model})",
                      flush=True)
                for c in bad:
                    print(f"      {c.verdict[:5]:5} {c.claim}", flush=True)
    claims_out.close()
    if args.judge_only:
        print(f"{len(cache)} verdicts in {cache_path}")
        return 0

    def rate(c):
        return f"{c['unsupported']}/{c['claims']} = " + (
            f"{c['unsupported'] / c['claims']:.1%}" if c["claims"] else "-")
    print()
    for who, c in per.items():
        print(f"{who[:40]:40} {rate(c)}")
    if len(per_set) > len(per):
        print()
        for pair, c in per_set.items():
            print(f"{pair[:40]:40} {rate(c)}")
    print(f"\nall: {rate(total)}  ({total['unchecked']} not checked)")
    print("flags by kind:", dict(kinds.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
