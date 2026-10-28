"""
jobdork.cli
===========
The command line. Everything the dashboard can do has a command here, and the
dashboard is a convenience rather than the product.

    jobdork setup                    first-run questions, as the dashboard asks them
    jobdork scan                     read the sources, screen, store
    jobdork list --new               what appeared since the last scan
    jobdork add <url>                fetch one posting into the database
    jobdork applied <ref> -s applied record what you did
    jobdork rescreen                 re-apply the current config to what is stored
    jobdork show <ref>               one role in full, including the advert
    jobdork sources                  what will run, and what is dormant and why

`scan`, `rescreen` and `sources` are command-line only by design: they are
slow maintenance verbs and a dashboard has nowhere sensible to show progress.

The original Google-dork generator is untouched and still lives in main.py.
`jobdork dork ...` hands straight over to it.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from . import __version__
from .core import config
from .core.config import STATUSES, ConfigError
from .db.store import Store, canonical_url
from .output import render
from .search import scan as scan_mod
from .search.resume import flag_label


def _log(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )


def _say(line: str) -> None:
    """Print a progress line, and record it for the Activity page."""
    from .core import telemetry

    print(line)
    telemetry.line(line)


def _summary(report) -> None:
    """What a finished job is remembered by on the Activity page."""
    from .core import telemetry

    telemetry.summary(" · ".join(report.lines()))


# Commands that run long enough to be worth watching on the Activity page.
RECORDED = ("scan", "enrich", "check", "judge", "rescreen", "generate",
            "letter", "review", "tailor")


def _load(args, first_run: bool = False) -> config.Config:
    """The config, with command-line overrides applied.

    `first_run` is for the commands that do setup: they start without a
    config file, and with one only partly set up. Every other command needs
    setup finished.
    """
    cfg = config.load(getattr(args, "config", "") or "", require=not first_run)
    if not first_run:
        config.require_set_up(cfg)
    for warning in cfg.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    # A scan from the terminal shows its warnings on the Activity page too.
    from .core import telemetry
    telemetry.capture_logs(cfg.db_path)

    radius = getattr(args, "radius", None)
    if radius is not None and radius != "exact":
        try:
            radius = float(radius)
        except ValueError:
            raise config.ConfigError(
                f"--radius {radius!r}: give 'exact' or a number") from None

    return config.apply_overrides(
        cfg,
        titles=getattr(args, "title", None),
        exclude_titles=getattr(args, "exclude_title", None),
        anchor=getattr(args, "anchor", None),
        countries=getattr(args, "country", None),
        units=getattr(args, "units", None),
        radius=radius,
        work_modes=getattr(args, "work_mode", None),
        salary_floor=getattr(args, "salary_floor", None),
        currency=getattr(args, "currency", None),
        resume=getattr(args, "resume", None),
        db=getattr(args, "db", None) or "",
        output_dir=getattr(args, "out", None),
    )


def _fmt_salary(row) -> str:
    if not row["salary_stated"]:
        return "unconfirmed"
    lo, hi = row["salary_min"], row["salary_max"]
    cur = row["salary_currency"] or ""
    if lo and hi:
        return f"{cur}{lo:,.0f}-{hi:,.0f}"
    return f"{cur}{(hi or lo):,.0f}" if (hi or lo) else "unconfirmed"


def _print_roles(rows, show_flags: bool = False) -> None:
    if not rows:
        print("Nothing to show.")
        return
    for row in rows:
        distance = (f"{row['distance_mi']:.0f}mi"
                    if row["distance_mi"] is not None else "-")
        score = f"{row['score']:.0f}" if row["score"] is not None else "-"
        print(f"{score:>4}  {row['title']}  at  {row['company']}")
        print(f"      {row['uid']}  {row['status']}  "
              f"{row['location_raw'] or 'location not stated'}  "
              f"{distance}  {row['work_mode'] or 'arrangement not stated'}  "
              f"{_fmt_salary(row)}")
        if show_flags:
            try:
                flags = json.loads(row["flags"] or "[]")
            except (json.JSONDecodeError, TypeError):
                flags = []
            for flag in flags:
                print(f"      · {flag_label(flag)}")
        print(f"      {row['url']}")


# ── commands ───────────────────────────────────────────────────────────────────

# A scheduled scan's log is kept to about this size: the newest half is kept
# when it grows past it, so a daily scan for years does not fill a disk.
SCHEDULED_LOG_BYTES = 512 * 1024


def _log_scheduled(cfg) -> None:
    """A scheduled scan has no terminal: what it prints goes to a log beside
    the config, which the Dashboard's schedule card names. In a container,
    in the data folder instead, the one folder that is kept."""
    import os
    from datetime import datetime

    from .core import schedule

    base = (Path(cfg.db_path).parent if os.environ.get(config.CONTAINER_ENV)
            else Path(cfg.path or "config.yaml").parent)
    path = base.resolve() / schedule.LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > SCHEDULED_LOG_BYTES:
        tail = path.read_bytes()[-SCHEDULED_LOG_BYTES // 2:]
        path.write_bytes(tail[tail.find(b"\n") + 1:])
    stream = open(path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives as long as the run
    sys.stdout = sys.stderr = stream
    logging.basicConfig(level=logging.WARNING, stream=stream, force=True,
                        format="%(asctime)s %(levelname)s %(message)s")
    print(f"\n── scheduled scan, {datetime.now():%Y-%m-%d %H:%M} ──")


def cmd_scan(args) -> int:
    cfg = _load(args)
    if args.scheduled:
        _log_scheduled(cfg)
        if not cfg.titles_include:
            print("not scanned: no job titles to search for yet; finish setup first")
            return 0
    if args.fresh and not _fresh_start(cfg, args.yes):
        return 2
    with Store(cfg.db_path) as store:
        try:
            report = scan_mod.run(
                cfg, store, limit=args.limit,
                # lambda: scan.run calls progress(line) with one argument; this
                # indents it for the terminal, and --quiet passes None instead.
                progress=(lambda line: _say(f"  {line}"))
                if not (args.quiet or args.scheduled) else None,
            )
        except scan_mod.ScanBusy as exc:
            # Not a failure for a schedule: the scan that is running is the
            # one it would have made.
            from .core import telemetry
            telemetry.summary("not started: another scan was running")
            print(str(exc), file=sys.stderr)
            return 0 if args.scheduled else 3
        except Exception as exc:
            if args.scheduled:
                # No one is watching a scheduled scan: say it failed.
                from .core import notify
                notify.scan_failed(cfg, f"{type(exc).__name__}: {exc}", origin="schedule")
            raise
        if args.scheduled:
            from .core import notify
            notify.scan_finished(cfg, report.newly_seen, report.kept, origin="schedule")
        print()
        for line in report.lines():
            print(line)
        _summary(report)

        # Judged before the files are written, so they carry the verdicts; the
        # dashboard's scan did this and the terminal's did not.
        if cfg.llm.judge_on_scan:
            from .web.api import _judge_after_scan
            print(_judge_after_scan(cfg, store, _say))

        for path in render.write_all(store.list_roles(), cfg, report):
            print(f"wrote {path}")

        if args.email:
            # Deliberately after the files are written: a mail that fails
            # must not cost you the scan that produced it.
            from .output import digest as digest_mod
            new_rows = store.list_roles(new_only=True)
            built = digest_mod.build(new_rows, cfg, new_only=True)
            if built.empty and not args.even_if_empty:
                print("nothing new; no digest sent")
            else:
                try:
                    if args.csv_attachment:
                        digest_mod.attach_csv(built, new_rows)
                    message_id = digest_mod.send(built, args.email)
                    print(f"emailed {len(new_rows)} new to {args.email} "
                          f"(id {message_id})")
                except digest_mod.DigestError as exc:
                    print(f"digest failed, job posts are still stored: {exc}",
                          file=sys.stderr)
    return 0


def cmd_digest(args) -> int:
    """Mail what the last scan found. The point of scheduling a scan."""
    from .output import digest as digest_mod

    cfg = _load(args)
    with Store(cfg.db_path) as store:
        rows = store.list_roles(new_only=not args.all, limit=args.limit)
        built = digest_mod.build(rows, cfg, new_only=not args.all)

        if built.empty and not args.even_if_empty:
            # A mail that says "nothing new" every morning trains you to
            # ignore the one that says something.
            print("Nothing new since the last scan; no digest sent. "
                  "Use --even-if-empty to send anyway.")
            return 0

        if args.csv:
            try:
                digest_mod.attach_csv(built, rows)
            except digest_mod.DigestError as exc:
                print(f"digest: {exc}", file=sys.stderr)
                return 1

        if args.dry_run or not args.email:
            print(built.text)
            if not args.email:
                print("\n(no --email given, so nothing was sent)", file=sys.stderr)
            return 0

        try:
            message_id = digest_mod.send(built, args.email)
        except digest_mod.DigestError as exc:
            print(f"digest: {exc}", file=sys.stderr)
            return 1
        print(f"sent {len(rows)} job post{'' if len(rows) == 1 else 's'} "
              f"to {args.email} (id {message_id})")
    return 0


def cmd_list(args) -> int:
    cfg = _load(args)
    with Store(cfg.db_path) as store:
        rows = store.list_roles(
            status=args.status, new_only=args.new,
            include_settled=args.all, limit=args.limit,
            collapse_duplicates=not args.duplicates,
        )
        if args.json:
            print(json.dumps(render.rows_to_dicts(rows), indent=2))
        else:
            _print_roles(rows, show_flags=args.flags)
            print(f"\n{len(rows)} job post{'' if len(rows) == 1 else 's'}"
                  + ("" if args.all else " (settled ones hidden)"))
    return 0


def cmd_show(args) -> int:
    cfg = _load(args)
    with Store(cfg.db_path) as store:
        matches = store.resolve(args.ref)
        if not matches:
            print(f"Nothing matches {args.ref!r}.")
            return 1
        if len(matches) > 1:
            print(f"{args.ref!r} matches {len(matches)} job posts. "
                  "Give a uid or a URL:")
            _print_roles(matches[:10])
            return 1
        row = matches[0]
        for key in ("uid", "status", "note", "company", "title", "url",
                    "platform", "location_raw", "city", "state", "country",
                    "distance_mi", "work_mode", "posted_at", "first_seen",
                    "last_seen", "score"):
            if key in row and row[key] not in (None, ""):
                print(f"{key:14} {row[key]}")
        try:
            for flag in json.loads(row["flags"] or "[]"):
                print(f"{'flag':14} {flag}")
        except (json.JSONDecodeError, TypeError):
            pass
        if row["description"]:
            print("\n--- advert (as fetched; treat as the employer's claim) ---")
            print(row["description"][:6000])
    return 0


def cmd_applied(args) -> int:
    cfg = _load(args)
    with Store(cfg.db_path) as store:
        matches = store.resolve(args.ref)
        if not matches:
            print(f"Nothing matches {args.ref!r}.")
            return 1
        if len(matches) > 1:
            # Recording a status against the wrong role is worse than not
            # recording it, so this stops rather than guessing.
            print(f"{args.ref!r} matches {len(matches)} job posts. "
                  "Narrow it with a uid or a URL:")
            _print_roles(matches[:10])
            return 1
        row = matches[0]
        store.set_status(row["uid"], args.status, args.note)
        print(f"{row['uid']}  {row['title']} at {row['company']}  ->  {args.status}")
        if args.note:
            print(f"  note: {args.note}")
    return 0


def _fresh_start(cfg, yes: bool) -> bool:
    """`scan --fresh`: preview, or back up and delete every scanned job post."""
    from .web import api

    preview = api.fresh_preview(cfg)
    n = preview["count"]
    print(f"A fresh scan deletes all {n} job posts found by scans, with their "
          "statuses, notes, AI verdicts and document records, then scans again.")
    if preview["pursuing"]:
        print(f"That includes {preview['pursuing']} you are pursuing "
              "(applied, submitted, interviewing, offer).")
    if preview["kept_by_hand"]:
        print(f"{preview['kept_by_hand']} added by hand are kept.")
    if not yes:
        print("Nothing was deleted. Re-run with --yes to do it; the database is "
              "backed up first.")
        return False
    with Store(cfg.db_path) as store:
        backup = api._backup(cfg, store, "fresh-scan")
        deleted = store.clear_scanned()
    print(f"backed up to {backup}\ndeleted {deleted} job posts\n")
    return True


def cmd_rescreen(args) -> int:
    cfg = _load(args)
    with Store(cfg.db_path) as store:
        checked, stale, removed = scan_mod.rescreen(cfg, store, remove=args.remove)
        print(f"checked {checked}, no longer matching {stale}, removed {removed}")
        if stale and not args.remove:
            print("Nothing was deleted. Re-run with --remove to drop the ones "
                  "you have not acted on; job posts with a status you set are kept "
                  "either way.")
    return 0


def _read_url_file(path: str) -> list[str]:
    """One URL per line. Blank lines and `#` comments are skipped.

    Deliberately a list of POSTING urls, not the dork generator's output. That
    file holds Google *search* URLs, and turning those into postings would mean
    scraping Google's results — bot-protected, and a control this tool does not
    work around. Click the results, then paste the ones worth keeping.
    """
    urls: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Tolerate "title<tab>url" and "- url" so a pasted list works.
        match = re.search(r"https?://\S+", line)
        if match:
            urls.append(match.group(0).rstrip(",;)"))
    return urls


def _add_one(cfg, fetcher, url: str, token: str, company: str,
             store, home, quiet: bool = False) -> str:
    """Returns one of: added, updated, failed."""
    from .fetch import link
    from .search import screen

    url = canonical_url(url)
    try:
        wanted = link.read(fetcher, cfg, url, token, company)
    except link.LinkError as exc:
        if not quiet:
            print(f"  ? {url}\n      {exc}. The dashboard's Add a job post can take "
                  "the advert's text pasted in instead")
        return "failed"

    verdict = screen.screen(wanted, cfg, home)
    is_new = store.upsert(wanted)
    if not quiet:
        mark = "+" if is_new else "="
        print(f"  {mark} {wanted.uid}  {wanted.title} at {wanted.company}")
        if not verdict.keep:
            # Stored anyway: you asked for this one by name, and a filter is
            # not a better judge of that than you are.
            print(f"      does not pass your filters ({verdict.reasons[0]}); "
                  "stored anyway because you asked for it")
        for flag in verdict.flags:
            print(f"      · {flag}")
    return "added" if is_new else "updated"


def cmd_add(args) -> int:
    """Fetch postings by URL — the bridge from a Google result to the database."""
    from .fetch.http import Fetcher
    from .search import screen

    cfg = _load(args)
    urls = list(args.url or [])
    if args.from_file:
        try:
            urls.extend(_read_url_file(args.from_file))
        except OSError as exc:
            print(f"add: cannot read {args.from_file}: {exc}", file=sys.stderr)
            return 1
    if not urls:
        print("add: give one or more posting URLs, or --from-file PATH",
              file=sys.stderr)
        return 1
    if args.token and len(urls) > 1:
        print("add: --token applies to a single posting; run those separately",
              file=sys.stderr)
        return 1

    fetcher = Fetcher(cfg.fetch.user_agent, cfg.fetch.timeout, cfg.fetch.retries)
    home = screen.home_of(cfg)
    tally = {"added": 0, "updated": 0, "failed": 0}

    with Store(cfg.db_path) as store:
        for url in urls:
            tally[_add_one(cfg, fetcher, url, args.token, args.company,
                           store, home)] += 1
        store.conn.commit()

    if len(urls) > 1:
        print(f"\n{tally['added']} added, {tally['updated']} updated, "
              f"{tally['failed']} could not be read")
    return 0 if tally["added"] or tally["updated"] else 1


def cmd_discover(args) -> int:
    """Find an employer's board by reading it off their own careers page."""
    from .fetch.http import Fetcher
    from .search import discover as discover_mod

    cfg = _load(args)
    fetcher = Fetcher(cfg.fetch.user_agent, cfg.fetch.timeout, cfg.fetch.retries)

    print(f"Looking for {args.employer}...")
    report = discover_mod.discover(args.employer, fetcher)
    if report.error:
        print(report.error, file=sys.stderr)
        return 1

    for line in report.lines():
        print(line)
    _summary(report)

    addable = [item for item in report.found if item.addable]
    if not addable:
        if report.found:
            print("\nNothing written: a board that did not answer with jobs is "
                  "a guess, and banking a guess is worse than leaving it out.")
        return 0 if report.found or report.unsupported else 1

    if not args.add:
        print("\nRe-run with --add to write these into your config.")
        return 0

    name = args.name or args.employer
    try:
        written = discover_mod.add_to_config(cfg.path, name, addable)
    except ValueError as exc:
        print(f"discover: {exc}", file=sys.stderr)
        return 1
    for item in written:
        print(f"\nadded to {cfg.path}: {item.platform} / {item.token}")
    if not written:
        print(f"\nalready in {cfg.path}; nothing added")
    return 0


def cmd_generate(args) -> int:
    """Screen a role, or draft a CV or cover letter. Spends tokens."""
    from .ai import guard
    from .writing import generate as gen
    from .writing import resume_doc

    cfg = _load(args)
    with Store(cfg.db_path) as store:
        matches = store.resolve(args.ref)
        if not matches:
            print(f"Nothing matches {args.ref!r}.")
            return 1
        if len(matches) > 1:
            print(f"{args.ref!r} matches {len(matches)} job posts. "
                  "Give a uid or a URL:")
            _print_roles(matches[:10])
            return 1
        row = matches[0]

        try:
            result = gen.generate(
                row, args.kind, cfg.resume_path, root=args.dir,
                dry_run=args.dry_run,
                progress=_say if not args.quiet else None,
                settings=guard.settings_for(cfg),
                notes=resume_doc.record_notes(store.projects(), store.education()),
            )
        except gen.GenerateError as exc:
            print(f"generate: {exc}", file=sys.stderr)
            return 1

        if args.dry_run:
            print(f"folder: {result.folder}")
            print(f"would run: {' '.join(gen.build_command(result.folder))}")
            print(f"\n--- prompt ---\n{result.text}")
            print(f"\n{result.cost_note}")
            return 0

        print(f"\nwrote {result.path}")
        for gate in result.gates:
            print(gate.line())
        failed = [g for g in result.gates if not g.passed]
        if failed:
            # Not redrafted: a second pass costs tokens you did not ask for,
            # and a failed gate means read this before you send it rather
            # than this is broken.
            print("\nA failed gate is a thing to read before you send it, "
                  "not a thing that was fixed for you.")

        gen.record(store, row, result)
        if args.kind != "screen" and (row["status"] or "new") == "new":
            store.set_status(row["uid"], "interested",
                             f"{args.kind} drafted")
    return 0


def cmd_enrich(args) -> int:
    """Fetch full adverts for roles that arrived as summaries."""
    from .fetch.http import Fetcher
    from .search import enrich as enrich_mod

    cfg = _load(args)
    fetcher = Fetcher(cfg.fetch.user_agent, cfg.fetch.timeout, cfg.fetch.retries)
    with Store(cfg.db_path) as store:
        report = enrich_mod.enrich(
            cfg, store, fetcher,
            limit=args.limit, platform=args.platform, thin=args.thin,
            dry_run=args.dry_run,
            progress=_say if not args.quiet else None,
        )
    print()
    for line in report.lines():
        print(line)
    _summary(report)
    if args.dry_run:
        print("(dry run: nothing was written)")
    return 0


def cmd_check(args) -> int:
    """Check whether stored postings are still up; close the ones that are not."""
    from .fetch.http import Fetcher
    from .search import listing

    cfg = _load(args)
    fetcher = Fetcher(cfg.fetch.user_agent, cfg.fetch.timeout, cfg.fetch.retries)
    with Store(cfg.db_path) as store:
        report = listing.run(cfg, store, fetcher, limit=args.limit,
                             uid=args.uid, force=args.force,
                             platform=args.platform,
                             progress=None if args.quiet else _say)
    print()
    for line in report.lines():
        print(line)
    _summary(report)
    return 0


def cmd_judge(args) -> int:
    """Have the configured model read the best roles against your resume."""
    from .ai import judging
    from .ai.llm import LLMError

    cfg = _load(args)
    with Store(cfg.db_path) as store:
        try:
            report = judging.run(cfg, store, limit=args.limit, uid=args.uid,
                                 force=args.force,
                                 progress=None if args.quiet else _say)
        except LLMError as exc:
            print(f"cannot judge: {exc}")
            return 1
    print()
    for line in report.lines():
        print(line)
    _summary(report)
    return 0


def _one_uid(store, ref: str) -> str:
    """A uid from a uid, URL or company. Empty when it does not pick one post."""
    matches = store.resolve(ref)
    if len(matches) != 1:
        print(f"{ref!r} matches {len(matches)} job posts; give its uid",
              file=sys.stderr)
        return ""
    return matches[0]["uid"]


def cmd_letter(args) -> int:
    """A cover letter from the AI-page model, guarded and saved to the job folder."""
    from .ai import writer
    from .ai.llm import LLMError

    cfg = _load(args)
    with Store(cfg.db_path) as store:
        uid = _one_uid(store, args.uid)
        if not uid:
            return 2
        try:
            draft = writer.letter(cfg, store, uid, root=args.dir,
                                  progress=None if args.quiet else _say)
        except LLMError as exc:
            print(f"cannot write the letter: {exc}")
            return 1
    print(f"\n{draft.path}")
    _summary_text(f"wrote {draft.path.name} (output {draft.output_id})")
    return 0


def cmd_tailor(args) -> int:
    """Your resume rewritten for one job post, in the ATS template, as a PDF."""
    from .ai import writer
    from .ai.llm import LLMError

    cfg = _load(args)
    with Store(cfg.db_path) as store:
        uid = _one_uid(store, args.uid)
        if not uid:
            return 2
        try:
            result = writer.tailor(cfg, store, uid, root=args.dir,
                                   progress=None if args.quiet else _say)
        except LLMError as exc:
            print(f"cannot tailor the resume: {exc}")
            return 1
    print(f"\n{result.pdf_path}")
    _summary_text(f"wrote {result.pdf_path.name} (output {result.output_id})")
    return 0


def cmd_review(args) -> int:
    """A resume review: general, or against one job post with its uid."""
    from .ai import writer
    from .ai.llm import LLMError

    cfg = _load(args)
    with Store(cfg.db_path) as store:
        uid = _one_uid(store, args.uid) if args.uid else ""
        if args.uid and not uid:
            return 2
        try:
            result = writer.review(cfg, store, uid, root=args.dir,
                                   progress=None if args.quiet else _say)
        except LLMError as exc:
            print(f"cannot review: {exc}")
            return 1
    print()
    print(result.text)
    if result.path:
        print(result.path)
    _summary_text(f"{len(result.health)} resume point(s) (output {result.output_id})")
    return 0


def _summary_text(text: str) -> None:
    from .core import telemetry
    telemetry.summary(text)


def cmd_prune(args) -> int:
    """Delete old or settled job posts. Previews unless --yes."""
    from .web import api

    cfg = _load(args)
    try:
        preview = api.cleanup_preview(cfg, args.older_than, args.status)
    except api.ApiError as exc:
        print(f"prune: {exc}", file=sys.stderr)
        return 2
    print(f"{preview['count']} job posts {preview['reason']}")
    if preview["count"] and preview["count"] == preview["total"]:
        print("That is every job post you have.")
    for title in preview["sample"]:
        print(f"  {title}")
    if not preview["count"] or not args.yes:
        if preview["count"]:
            print("\nNothing deleted. Add --yes to delete them "
                  "(the database is backed up first).")
        return 0
    done = api.cleanup_run(cfg, args.older_than, args.status, preview["count"])
    print(f"\ndeleted {done['deleted']}; backup at {done['backup']}")
    return 0


def cmd_serve(args) -> int:
    from .web import serve as serve_mod

    cfg = _load(args, first_run=True)
    return serve_mod.serve(cfg, port=args.port,
                           open_browser=not args.no_open,
                           token=args.token)


def cmd_uninstall(args) -> int:
    """Remove jobdork's traces from this computer, and what you choose of
    yours (core/uninstall.py): the desktop app's folder, not a source
    checkout's (./run.sh clean is for that)."""
    from .core import uninstall

    home = Path(args.home).expanduser() if args.home else None
    items = [i for i in uninstall.inventory(home) if i.present]
    if args.remove is not None:
        choose = {c.strip() for c in args.remove.split(",") if c.strip()}
        if "all" in choose:
            choose = set(uninstall.CHOICES)
        unknown = choose - set(uninstall.CHOICES)
        if unknown:
            print(f"not something to remove: {', '.join(sorted(unknown))}; "
                  f"choose from {', '.join(uninstall.CHOICES)} or all", file=sys.stderr)
            return 2
    elif sys.stdin.isatty():
        print("The scheduled scan, the app window's storage and any keys kept in the "
              "keychain are always removed.\n"
              "Of yours, choose what to delete; anything you do not answer y to is kept.\n")
        choose = set()
        for item in items:
            mb = item.size / 1e6
            answer = input(f"Delete {item.label} ({item.what}; {mb:.1f} MB)? [y/N] ")
            if answer.strip().lower() in ("y", "yes"):
                choose.add(item.key)
    else:
        choose = set()
    out = uninstall.remove(choose, home)
    if out["unscheduled"]:
        print("removed the scheduled scan")
    for path in out["removed"]:
        print(f"removed {path}")
    for path, why in out["failed"]:
        print(f"could not remove {path}: {why}", file=sys.stderr)
    kept = [label for key, label, _ in uninstall.ITEMS if key in out["left"]]
    if kept:
        print(f"kept: {', '.join(kept)}")
    print("Now remove the program itself: on a Mac drag jobdork from Applications to "
          "the Trash; on Linux delete the AppImage, or `sudo apt remove jobdork`; on "
          "Windows, Settings, Apps, jobdork, Uninstall.")
    return 1 if out["failed"] else 0


def cmd_app(args) -> int:
    from .web import app

    return app.run(port=args.port, home=Path(args.home) if args.home else None,
                   debug=args.debug)


def cmd_setup(args) -> int:
    """First-run questions in the terminal, the same steps as the dashboard's."""
    from .core import setup

    cfg = _load(args, first_run=True)
    from .core import telemetry
    telemetry.record_calls_to(cfg.db_path)     # the AI step's test, its suggestions
    if not cfg.setup_step:
        print(f"Already set up: {cfg.path}. Change settings in the dashboard "
              "(`jobdork serve`) or in that file.")
        return 0
    steps = {"welcome": _setup_welcome, "resume": _setup_resume, "ai": _setup_ai,
             "search": _setup_search, "where": _setup_where, "pay": _setup_pay,
             "scan": _setup_scan}
    while cfg.setup_step in steps:
        cfg = steps[cfg.setup_step](cfg)
        if cfg is None:
            print("\nStopped. Run `jobdork setup` again to carry on from here.")
            return 0
    if cfg.setup_step:                     # a step only the browser asks
        print(f"\nNext: {setup.title(cfg.setup_step)}. Carry on in the browser "
              "with `jobdork serve`.")
    return 0


def _setup_welcome(cfg):
    from .core import setup

    print("Welcome to jobdork. It reads job boards and employers' own "
          "boards,\nscreens every post against what you ask for, and "
          "keeps the ones that pass.\n")
    print("Setup asks, one step at a time:")
    for _name, label in setup.STEPS[1:]:
        print(f"  {label}")
    print("\nEach answer is saved as you go, so you can stop any time and "
          "carry on later: run `jobdork setup` again.")
    if not _yes("Start?"):
        return None
    cfg = setup.write(cfg.path, {"setup_step": setup.next_step("welcome")})
    print(f"saved: {cfg.path}")
    return cfg


def _setup_resume(cfg):
    """Ask for the resume until one reads, then show what was read."""
    from .core import setup
    from .search import resume as resume_mod
    from .web import api

    print(f"\n── {setup.title('resume')} ──")
    print("jobdork scores every job post against your resume, and the AI reads "
          "it to suggest\nwhat to search for. It stays on this computer.")
    while True:
        parsed = None
        if cfg.resume_path:
            try:
                parsed = resume_mod.load(cfg.resume_path)
            except resume_mod.ResumeError as exc:
                print(f"\nThe resume set before no longer reads: {exc}")
        if parsed:
            chars = len(parsed.text)
            years = resume_mod.years_claimed(parsed.text)
            print(f"\nRead {Path(cfg.resume_path).name}: {chars:,} characters"
                  + (f", {years} years of experience claimed" if years else ""))
            note = setup.resume_note(chars)
            if note:
                print(f"warning: {note}")
            if parsed.skills:
                print("Skills: " + ", ".join(
                    resume_mod.skill_name(s) for s in sorted(parsed.skills)))
            print("Start of the text read:\n")
            print("  " + parsed.text[:600].strip().replace("\n", "\n  ") + " …\n")
            if _yes("Use this resume?"):
                return setup.write(cfg.path, {"setup_step": setup.next_step("resume")})
        try:
            raw = input("Path to your resume (PDF, Word, Markdown or text), "
                        "blank to stop: ").strip().strip("'\"")
        except EOFError:
            return None
        if not raw:
            return None
        source = Path(raw).expanduser()
        if not source.is_file():
            print(f"No file at {source}.")
            continue
        if source.stat().st_size > api.MAX_RESUME_BYTES:
            print(f"Not used: over the {api.MAX_RESUME_BYTES // 1_000_000}MB limit.")
            continue
        try:
            saved = api.save_resume(cfg, source.name, source.read_bytes())
        except api.ApiError as exc:
            print(f"Not used: {exc}")
            continue
        cfg = setup.write(cfg.path, {"resume_path": saved["path"]})


def _setup_ai(cfg):
    """Choose a model and prove it answers, or skip: scanning works without."""
    from .ai import llm
    from .core import setup

    print(f"\n── {setup.title('ai')} ──")
    print("A model reads each job post against your resume, suggests what to "
          "search for,\nand drafts cover letters. Scanning works without it; "
          "skip now and set it up\nlater on the dashboard's AI page.\n")
    names = list(llm.PROVIDERS)
    for i, name in enumerate(names, 1):
        cost = "on this computer, free" if name == "ollama" else "spends tokens on your key"
        print(f"  {i}. {llm.PROVIDERS[name]} ({cost})")
    skip = {"setup_step": setup.next_step("ai")}
    while True:
        pick = _pick("Which one? Number, or blank to skip for now: ", len(names))
        if pick is None:
            return setup.write(cfg.path, skip)
        provider = names[pick]
        url = cfg.llm.ollama_url or llm.DEFAULT_OLLAMA_URL
        if provider == "ollama":
            if config.in_container() and "localhost" in url:
                print("Inside Docker, Ollama on this computer is at "
                      f"{llm.OLLAMA_FROM_DOCKER}")
            url = _ask(f"Ollama address [{url}]: ") or url
        elif not llm.key_for(provider)[0]:
            # A terminal run ends, so there is no memory to hold a key in.
            env = llm.ENV_KEYS[provider][0]
            print(f"No {llm.PROVIDERS[provider]} key found. Put {env}=<your key> "
                  "in .env (or the environment) and run `jobdork setup` again, "
                  "or type the key in the browser with `jobdork serve`.")
            continue
        try:
            models = llm.list_models(llm.Settings(provider=provider, ollama_url=url))
        except llm.LLMError as exc:
            print(f"Could not list models: {exc}")
            continue
        if not models:
            print("No models to choose from"
                  + (" (pull one first: ollama pull gemma3)" if provider == "ollama" else ""))
            continue
        for i, name in enumerate(models[:20], 1):
            print(f"  {i}. {name}")
        chosen = _pick("Model number: ", min(len(models), 20))
        if chosen is None:
            continue
        cfg = setup.write(cfg.path, {"llm": {"provider": provider,
                                              "model": models[chosen],
                                              "ollama_url": url}})
        print("Asking the model…")
        try:
            answer = llm.ping(llm.Settings.from_config(cfg))
        except llm.LLMError as exc:
            print(f"It did not answer: {exc}")
            continue
        print(f"{answer['model']} answered in {answer['seconds']}s. Each scan will "
              f"have it read the {setup.JUDGE_TOP} best new job posts against your "
              "resume (change it on the AI page).")
        return setup.write(cfg.path, {**skip, "llm": {"judge_on_scan": True,
                                                       "judge_top": setup.JUDGE_TOP}})


def _setup_search(cfg):
    """Titles, titles to keep out, industries, dealbreakers: suggested, then ticked."""
    from .ai import llm
    from .core import setup
    from .web import api

    print(f"\n── {setup.title('search')} ──")
    choices = api.setup_choices(cfg)
    chosen = choices["chosen"]
    got = {"titles": [], "exclude": [], "industries": [], "dealbreakers": []}
    if chosen["titles"]:
        got = {k: list(chosen[k]) for k in got}
    elif llm.Settings.from_config(cfg).problem():
        print("No AI set up, so type the job titles you want.")
    else:
        said = []

        def stage(fraction, label):
            if label not in said and label != "Done":
                said.append(label)
                print(f"  {round(fraction * 100):3}%  {label}…")
        try:
            got = api.setup_suggest(cfg, progress=stage)
            print("Suggested from your resume:")
        except api.ApiError as exc:
            print(f"The AI could not suggest anything ({exc}). Type them yourself.")

    titles = _keep("Job titles to search for", got["titles"])
    while not titles:
        titles = _added("Give at least one job title, comma separated: ")
        if not titles and not _ask_more():
            return None
    exclude = _keep("Never show these titles", got["exclude"])
    creds = _keep("Your certifications and licenses (an advert's are checked "
                  "against these)",
                  chosen["credentials"] or choices["credentials_found"], lower=False)

    industries = choices["industries"]
    print("\nIndustries: jobdork also reads employers' own job boards in these. "
          "None reads every one.")
    print("  " + ", ".join(industries))
    default = ", ".join(got["industries"])
    raw = _ask(f"Industries, comma separated [{default or 'every industry'}]: ")
    picked = [i.strip().lower() for i in raw.split(",") if i.strip()] if raw \
        else list(got["industries"])
    unknown = [i for i in picked if i not in industries]
    if unknown:
        print(f"Not an industry jobdork knows, left out: {', '.join(unknown)}")
    picked = [i for i in picked if i in industries]

    catalog = choices["dealbreakers"]
    print("\nDealbreakers: words in a job post you would rather not see.")
    for i, d in enumerate(catalog, 1):
        mark = " (suggested)" if d["name"] in got["dealbreakers"] else ""
        on = " [on]" if d["name"] in chosen["dealbreakers"] else ""
        effect = "hides the post" if d["hard"] else "lowers its score"
        print(f"  {i:2}. {d['name']}: {effect}{mark}{on}")
    raw = _ask("Numbers to turn on, comma separated (blank for none): ")
    nums = {int(n) for n in re.findall(r"\d+", raw)}
    deals = [{k: d[k] for k in ("name", "words", "pattern", "hard") if k in d}
             for i, d in enumerate(catalog, 1)
             if i in nums or (not raw and d["name"] in chosen["dealbreakers"])]

    return setup.write(cfg.path, {
        "titles_include": titles, "titles_exclude": exclude,
        "industries": picked, "dealbreakers": deals, "credentials": creds,
        "setup_step": setup.next_step("search")})


def _setup_where(cfg):
    """Country; any regions and cities; radius; work arrangements; countries."""
    from .core import setup
    from .search import geo

    print(f"\n── {setup.title('where')} ──")
    print("Where you would work, how far you would travel to an office, and which "
          "kinds of work to keep.\nRemote jobs are kept whatever the distance. "
          "Only the country is required: with no\nregion and no city, job posts "
          "from the whole country are kept.")
    countries = geo.picker_countries()
    country = _match_place("Country (name or code): ", countries)
    if country is None:
        return None
    regions = geo.picker_regions(country["code"])
    chosen_regions: list[dict] = []
    if regions["regions"]:
        label = regions["label"].lower()
        print(f"Job posts anywhere in a {label} you add are kept. Blank when done.")
        while True:
            region = _match_place(f"{regions['label']} (name or code, blank for no "
                                  f"more): ", regions["regions"], optional=True)
            if not region:
                break
            chosen_regions.append(region)
    print("Job posts within your radius of a city you add are kept. Blank when done.")
    cities: list[str] = []
    while True:
        typed = _ask("City (start of its name, blank for no more): ")
        if not typed:
            break
        found = geo.picker_cities(country["code"], "", typed, limit=10)
        exact = [c for c in found if c.lower() == typed.lower()]
        city = ""
        if exact or len(found) == 1:
            city = (exact or found)[0]
        elif found:
            for i, name in enumerate(found, 1):
                print(f"  {i}. {name}")
            pick = _pick("Which one? Number, or blank to type again: ", len(found))
            city = found[pick] if pick is not None else ""
        else:
            print("Not in the place list; try a bigger city nearby.")
        if city:
            cities.append(city)

    units = geo.default_units([country["code"]])
    radius = _ask(f"How far from a city would you travel, in {units}? A number, or "
                  "'exact' for the city only [25]: ").lower() or "25"
    while radius != "exact" and not re.fullmatch(r"\d+(\.\d+)?", radius):
        radius = _ask("A number, or 'exact': ").lower() or "25"
    modes = [m for m in re.split(r"[,\s]+", _ask(
        "Keep which: remote, hybrid, office (comma separated, blank for all "
        "three): ").lower()) if m in config.WORK_MODES]

    print(f"\nJob posts are kept from {country['name']}. A remote job for an "
          "employer elsewhere\n(say, US employers while living in the Philippines) "
          "needs that country too.")
    codes = {c["code"] for c in countries}
    extra = [c.strip().upper() for c in _ask(
        "Other countries, as two-letter codes (comma separated, blank for "
        "none): ").split(",") if c.strip()]
    unknown = [c for c in extra if c not in codes]
    if unknown:
        print(f"Not a country code jobdork knows, left out: {', '.join(unknown)}")
    keep = list(dict.fromkeys([country["code"], *(c for c in extra if c in codes)]))

    return setup.write(cfg.path, {
        "places_pick": {"country": country["code"],
                        "regions": [r["code"] for r in chosen_regions],
                        "cities": [{"city": c} for c in cities]},
        "radius": radius if radius == "exact" else float(radius), "units": units,
        "work_modes": modes, "countries": keep,
        # Pay is asked next, in the country's currency where a floor can use it.
        **({"currency": country["currency"]}
           if country["currency"] in config.CURRENCIES else {}),
        "setup_step": setup.next_step("where")})


def _setup_pay(cfg):
    """An optional yearly salary floor, in a currency a floor can use."""
    from .core import setup

    print(f"\n── {setup.title('pay')} ──")
    print("Optional. A job post is hidden only when it states a salary and even "
          "the top of it\nis below this; most state none, and those are kept. "
          "A yearly amount: hourly\nrates in posts are turned into yearly pay "
          "first (for an hourly rate, multiply by 2,080).")
    payload = {}
    while True:
        raw = _ask("Lowest yearly pay you would take (blank for none): ")
        amount = raw.replace(",", "").strip()
        if not amount:
            payload["salary_floor"] = None
            break
        if re.fullmatch(r"\d+(\.\d+)?", amount):
            payload["salary_floor"] = float(amount)
            break
        print("A number, such as 65000.")
    if payload["salary_floor"] is not None:
        currency = _ask(f"Currency [{cfg.salary.currency}]: ").upper() or cfg.salary.currency
        while currency not in config.CURRENCIES:
            currency = _ask(f"One of {', '.join(config.CURRENCIES)}: ").upper() \
                or cfg.salary.currency
        payload["currency"] = currency
    cfg = setup.write(cfg.path, payload)
    _setup_sources(cfg)                 # the same step: what will be searched
    return setup.write(cfg.path, {"setup_step": setup.next_step("pay")})


def _setup_scan(cfg):
    """The quick first scan, which finishes setup, then the rest if wanted."""
    from .core import setup, telemetry
    from .web import api

    print(f"\n── {setup.title('scan')} ──")
    print("How old a job post do you still want to see? Older ones are hidden "
          "from Job posts\non the dashboard, never deleted (freshness.show_days). "
          "After three weeks a post\nis often being interviewed for already.")
    while True:
        raw = _ask("Days, or 0 for any age [30]: ").strip() or "30"
        if raw.isdigit():
            cfg = setup.write(cfg.path, {"show_days": int(raw)})
            break
        print("A whole number of days, such as 30.")
    print("\njobdork reads the job boards now: first the keyword sources and a "
          "sample of the\nemployer boards, which takes a minute or two.")
    if not _yes("Start?"):
        return None
    (name, first), (rest_name, rest) = api.first_scan_jobs(cfg)
    try:
        with telemetry.job(cfg.db_path, name, "terminal"):
            summary = first(_say)
            telemetry.summary(summary)
    except Exception as exc:
        print(f"The scan failed: {exc}. Run `jobdork setup` to try again.")
        return None
    print(f"\n{summary}\nSet up. `jobdork list --new` shows what was found, "
          "`jobdork serve` the dashboard.")
    if _yes("\nRead the rest of the employer boards now? It takes several "
            "minutes; `jobdork scan` does it later."):
        with telemetry.job(cfg.db_path, rest_name, "terminal"):
            summary = rest(_say)
            telemetry.summary(summary)
        print(summary)
    return config.load(cfg.path)


def _setup_sources(cfg) -> None:
    """What a scan reads, and the keyed sources your countries can use."""
    import getpass

    from .web import api

    print("\nWhat will be searched")
    d = api.setup_sources(cfg)
    print("Every scan reads these, then keeps only the job posts that pass what "
          "you chose:")
    for x in d["searched"]:
        print(f"  {x['name']}: {x['what']}")
    b = d["boards"]
    print(f"  Employers' own job boards: {b['count']} built in, for "
          f"{', '.join(b['industries']) or 'every industry'} in "
          f"{', '.join(b['countries']) or 'every country'}")
    # Only the ones your countries can use: USAJOBS with the US among them,
    # Adzuna where it covers one of them.
    for k in [k for k in d["keyed"] if k["applies"]]:
        if k["ready"]:
            print(f"  {k['label']}: ready.")
            continue
        print(f"\nUse {k['label']}? {k['offer']} It needs a free key: {k['signup']}")
        if not _yes(f"Add a {k['label']} key now?", default=False):
            continue
        values = {}
        for f in k["fields"]:
            ask = _ask if "EMAIL" in f["name"] else getpass.getpass
            try:
                values[f["name"]] = ask(f"{k['label']} {f['label']}: ").strip()
            except EOFError:
                values[f["name"]] = ""
        try:
            note = api.setup_keys(cfg, values)
            print(f"  {k['label']}: {note or 'tried and saved.'}")
        except api.ApiError as exc:
            print(f"  {k['label']}: not saved ({exc}).")


def _match_place(question: str, rows: list[dict], optional: bool = False):
    """A row whose code or name is what was typed; a short list when unsure."""
    while True:
        typed = _ask(question).strip()
        if not typed:
            return None
        low = typed.lower()
        exact = [r for r in rows if low in (r["code"].lower(), r["name"].lower())]
        if exact:
            return exact[0]
        near = [r for r in rows if r["name"].lower().startswith(low)][:10]
        if len(near) == 1:
            return near[0]
        if near:
            for i, r in enumerate(near, 1):
                print(f"  {i}. {r['name']}")
            pick = _pick("Which one? Number, or blank to type again: ", len(near))
            if pick is not None:
                return near[pick]
        else:
            print("Not found." + (" Blank skips it." if optional else ""))


def _keep(label: str, items: list[str], lower: bool = True) -> list[str]:
    """Show a list, let numbers drop entries, then let more be added.

    `lower` for titles, matched in lower case; a credential keeps its capitals.
    """
    print(f"\n{label}:")
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")
    if items:
        raw = _ask("Enter to keep all, or numbers to drop (e.g. 2,4): ")
        drop = {int(n) for n in re.findall(r"\d+", raw)}
        items = [t for i, t in enumerate(items, 1) if i not in drop]
    return list(dict.fromkeys(items + _added("Add more, comma separated "
                                             "(blank for none): ", lower)))


def _added(question: str, lower: bool = True) -> list[str]:
    return [t.strip().lower() if lower else t.strip()
            for t in _ask(question).split(",") if t.strip()]


def _ask_more() -> bool:
    return _yes("A search needs a job title. Try again?")


def _ask(question: str) -> str:
    try:
        return input(question).strip()
    except EOFError:
        return ""


def _pick(question: str, count: int) -> int | None:
    """A 0-based choice from a numbered list, or None for blank."""
    while True:
        raw = _ask(question)
        if not raw:
            return None
        if raw.isdigit() and 1 <= int(raw) <= count:
            return int(raw) - 1
        print(f"Give a number from 1 to {count}.")


def _yes(question: str, default: bool = True) -> bool:
    try:
        answer = input(f"{question} {'[Y/n]' if default else '[y/N]'} ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes") or (default and answer == "")


def directory_line(cfg) -> str:
    """One line on the built-in employer boards this config reads."""
    from .search import directory

    d = cfg.sources.directory
    if not d.enabled:
        return "directory        off (sources.directory.enabled)"
    chosen = directory.select(cfg)
    countries = ", ".join(d.countries or cfg.locations.countries) or "every country"
    industries = ", ".join(d.industries) or "every industry"
    return (f"directory        {len(chosen)} built-in employer boards "
            f"({countries}; {industries})")


def cmd_sources(args) -> int:
    cfg = _load(args)
    print("Active:")
    for name in cfg.active_sources():
        print(f"  {name}")
    for company in cfg.sources.companies:
        print(f"  {company.platform:16} {company.name} (token {company.token})")
    print(f"  {directory_line(cfg)}")
    dormant = cfg.dormant_sources()
    if dormant:
        print("\nRegistered but not running:")
        for name in dormant:
            if name == "usajobs" and not cfg.usajobs_in_scope():
                reason = ("US federal postings only, and US is not in "
                          "locations.countries")
            elif name == "usajobs":
                reason = "no credential. Get a free key at https://developer.usajobs.gov"
            else:
                reason = ("no credential. Get a free key at "
                          "https://developer.adzuna.com/signup")
            print(f"  {name:16} {reason}")
        if any(not getattr(cfg.sources, f"{n}_ready")() for n in dormant
               if hasattr(cfg.sources, f"{n}_ready")):
            print("\nKeys go in .env, or are pasted in the app (held in memory, or in "
                  "the computer's keychain if you chose to keep keys); never in config.yaml.")
    return 0


def run_dork(rest: list[str]) -> int:
    """Hand over to the Google query generator, unchanged.

    Dispatched before argparse sees anything, because the generator has its own
    flags — `--list-levels`, `--since`, `--csv` — and argparse would either
    claim them or reject them. `argparse.REMAINDER` is not reliable enough
    here: a leading `--flag` is treated as an option to this parser rather than
    as the remainder.
    """
    import runpy
    from pathlib import Path as _Path

    generator = _Path(__file__).resolve().parent / "dork" / "generator.py"
    sys.argv = ["jobdork dork", *rest]
    runpy.run_path(str(generator), run_name="__main__")
    return 0


def cmd_dork(args) -> int:
    return run_dork(args.rest)


# ── parser ─────────────────────────────────────────────────────────────────────

def _overrides_parser() -> argparse.ArgumentParser:
    """Config overrides, inherited by every subcommand.

    Attached to the subcommands rather than the top level so they can be
    written where people expect — `jobdork scan --anchor "Berlin, Germany"` —
    instead of having to precede the verb.

    Every one is a setting that already exists in the config file. The flag
    exists so a different search can be tried without editing a config you
    have tuned, and each is validated exactly as the file is: an override must
    not be a looser way in than the config it replaces.
    """
    parent = argparse.ArgumentParser(add_help=False)
    group = parent.add_argument_group(
        "config overrides", "override config.yaml for this run only")
    group.add_argument("--title", action="append", metavar="TEXT",
                       help="replace titles.include; repeat for several")
    group.add_argument("--exclude-title", action="append", metavar="TEXT",
                       help="replace titles.exclude; repeat for several")
    group.add_argument("--anchor", metavar="PLACE",
                       help='one city in place of locations.cities and regions, e.g. "Berlin, Germany"')
    group.add_argument("--country", action="append", metavar="ISO2",
                       help="replace locations.countries; repeat for several")
    group.add_argument("--radius", metavar="N", help="'exact', or a distance")
    group.add_argument("--units", choices=("mi", "km"))
    group.add_argument("--work-mode", action="append",
                       choices=("remote", "hybrid", "office"),
                       help="replace locations.work_modes; repeat for several")
    group.add_argument("--salary-floor", type=float, metavar="N")
    group.add_argument("--currency", metavar="ISO")
    group.add_argument("--resume", metavar="PATH")
    group.add_argument("--out", metavar="DIR", help="override output.dir")
    group.add_argument("--db", metavar="PATH", help="override the database path")
    return parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobdork",
        description="Watch job boards, wherever you are, and only hear about the "
                    "job posts that pass your own filters.",
    )
    parser.add_argument("--version", action="version", version=f"jobdork {__version__}")
    parser.add_argument("-c", "--config", default="",
                        help="config file (default: config.local.yaml, then config.yaml)")
    parser.add_argument("-v", "--verbose", action="store_true")

    over = _overrides_parser()
    subs = parser.add_subparsers(dest="command", required=True)

    p = subs.add_parser("scan", parents=[over], help="read the sources, screen, store")
    p.add_argument("--limit", type=int, default=0,
                   help="keep at most N job posts, for a quick look")
    p.add_argument("--email", default="",
                   help="mail the new job posts after storing them")
    p.add_argument("--csv-attachment", action="store_true",
                   help="attach the job posts as CSV to that mail")
    p.add_argument("--even-if-empty", action="store_true",
                   help="send the mail even when nothing is new")
    p.add_argument("--fresh", action="store_true",
                   help="delete every scanned job post first (previews unless --yes)")
    p.add_argument("--yes", action="store_true", help="with --fresh: really delete")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--scheduled", action="store_true",
                   help="as the scan schedule runs it: no progress, output to "
                        "logs/scheduled-scan.log beside the config")
    p.set_defaults(func=cmd_scan)

    p = subs.add_parser("digest", parents=[over],
                        help="mail what the last scan found, without rescanning")
    p.add_argument("--email", default="", help="recipient; omit to print instead")
    p.add_argument("--all", action="store_true",
                   help="every open job post, not only what is new")
    p.add_argument("--csv", action="store_true", help="attach the job posts as CSV")
    p.add_argument("--even-if-empty", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="print the message instead of sending it")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_digest)

    p = subs.add_parser("list", parents=[over], help="print stored job posts")
    p.add_argument("--new", action="store_true", help="only what was first seen today")
    p.add_argument("--status", default="", choices=("", *STATUSES))
    p.add_argument("--all", action="store_true", help="include settled job posts")
    p.add_argument("--flags", action="store_true", help="show per-post flags")
    p.add_argument("--duplicates", action="store_true",
                   help="show aggregator repeats of the same job")
    p.add_argument("--json", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_list)

    p = subs.add_parser("show", parents=[over], help="one job post in full, including the advert")
    p.add_argument("ref", help="uid, posting URL, or company name")
    p.set_defaults(func=cmd_show)

    p = subs.add_parser("applied", parents=[over], help="record what you did about a job post")
    p.add_argument("ref", help="uid, posting URL, or company name")
    p.add_argument("-s", "--status", default="applied", choices=STATUSES)
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_applied)

    p = subs.add_parser("rescreen", parents=[over],
                        help="re-apply the current config to what is stored")
    p.add_argument("--remove", action="store_true",
                   help="delete the untouched ones that no longer match")
    p.set_defaults(func=cmd_rescreen)

    p = subs.add_parser("add", parents=[over],
                        help="fetch postings by URL into the database")
    p.add_argument("url", nargs="*", help="one or more posting URLs")
    p.add_argument("--from-file", default="", metavar="PATH",
                   help="read URLs from a file, one per line")
    p.add_argument("--token", default="",
                   help="board token, when the URL does not carry one")
    p.add_argument("--company", default="")
    p.set_defaults(func=cmd_add)

    p = subs.add_parser("generate", parents=[over],
                        help="screen a job post, or draft a CV or cover letter "
                             "(spends tokens)")
    p.add_argument("ref", help="uid, posting URL, or company name")
    p.add_argument("-k", "--kind", default="screen",
                   choices=("screen", "cv", "cover_letter"))
    p.add_argument("--dir", default="",
                   help="where documents are written "
                        "(default: your Documents folder)")
    p.add_argument("--dry-run", action="store_true",
                   help="show the prompt and the command, spend nothing")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_generate)

    p = subs.add_parser("enrich", parents=[over],
                        help="fetch full adverts for job posts stored as summaries")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--platform", default="", help="only this platform")
    p.add_argument("--thin", type=int, default=400,
                   help="advert length below which a job post is worth fetching")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_enrich)

    p = subs.add_parser("prune", parents=[over],
                        help="delete old or settled job posts (previews unless --yes)")
    p.add_argument("--older-than", type=int, default=0, metavar="DAYS",
                   help="first seen over DAYS ago and not applied, submitted, "
                        "interviewing or offer")
    p.add_argument("--status", default="",
                   help="comma separated: rejected,withdrawn,skipped,closed")
    p.add_argument("--yes", action="store_true", help="delete, after a backup")
    p.set_defaults(func=cmd_prune)

    p = subs.add_parser("check", parents=[over],
                        help="check stored postings are still open")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--uid", default="", help="just this job post")
    p.add_argument("--force", action="store_true",
                   help="re-check job posts checked in the last 12 hours")
    p.add_argument("--platform", default="", help="only this platform, e.g. adzuna")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_check)

    p = subs.add_parser("judge", parents=[over],
                        help="AI reads top job posts against your resume (llm: in "
                             "config; keys from the environment)")
    p.add_argument("--limit", type=int, default=0,
                   help="how many job posts (default llm.judge_top)")
    p.add_argument("--uid", default="", help="just this job post")
    p.add_argument("--force", action="store_true",
                   help="judge again even if already judged")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_judge)

    p = subs.add_parser("letter", parents=[over],
                        help="AI cover letter for one job post, checked against "
                             "your resume and the advert")
    p.add_argument("uid", help="the job post's uid, URL or company")
    p.add_argument("--dir", default="", help="job folders root "
                                              "(default ~/Documents/job-applications)")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_letter)

    p = subs.add_parser("tailor", parents=[over],
                        help="AI resume rewritten for one job post, in the ATS "
                             "template, as FirstName_LastName_JobTitle_Resume.pdf")
    p.add_argument("uid", help="the job post's uid, URL or company")
    p.add_argument("--dir", default="", help="job folders root "
                                              "(default ~/Documents/job-applications)")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_tailor)

    p = subs.add_parser("review", parents=[over],
                        help="AI resume review; give a job post id to compare with it")
    p.add_argument("uid", nargs="?", default="", help="compare with this job post")
    p.add_argument("--dir", default="", help="job folders root "
                                              "(default ~/Documents/job-applications)")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_review)

    p = subs.add_parser("setup", help="first-run questions: resume, what and where "
                                      "you are looking, then a first scan")
    p.set_defaults(func=cmd_setup)

    p = subs.add_parser("serve", parents=[over], help="the dashboard, at 127.0.0.1:8765")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-open", action="store_true",
                   help="do not open a browser")
    p.add_argument("--token", default="",
                   help="use this token instead of a fresh one; for a parent "
                        "process that spawned jobdork and already has one")
    p.set_defaults(func=cmd_serve)

    p = subs.add_parser("app", help="the dashboard in a window of its own")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--home", default="",
                   help="keep settings and job posts here instead of the "
                        "app's own folder (also $JOBDORK_HOME)")
    p.add_argument("--debug", action="store_true",
                   help="developer tools in the window (right-click, Inspect) "
                        "and debug logging")
    p.set_defaults(func=cmd_app)

    p = subs.add_parser("uninstall", help="remove jobdork's scheduled scan, app storage "
                                          "and saved keys, and what you choose of your data")
    p.add_argument("--remove", default=None, metavar="ITEMS",
                   help="what of yours to delete, comma separated: settings, jobs, "
                        "resume, documents, logs, downloads, or all (keys kept in the "
                        "keychain always go). Without it "
                        "you are asked about each; nothing is deleted you do not choose")
    p.add_argument("--home", default="",
                   help="the app's folder, if not the usual one (also $JOBDORK_HOME)")
    p.set_defaults(func=cmd_uninstall)

    p = subs.add_parser("discover", parents=[over],
                        help="find an employer's board from their own site")
    p.add_argument("employer", help="their website, e.g. stripe.com")
    p.add_argument("--add", action="store_true",
                   help="write verified boards into sources.companies")
    p.add_argument("--name", default="",
                   help="company name to record (default: what you typed)")
    p.set_defaults(func=cmd_discover)

    p = subs.add_parser("sources", parents=[over], help="what will run, and what is dormant")
    p.set_defaults(func=cmd_sources)

    p = subs.add_parser("dork", help="the original Google query generator")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_dork)

    return parser


def _recorded(args) -> int:
    """Run a command with its progress written where the dashboard reads it."""
    from .core import telemetry

    try:
        db_path = config.load(getattr(args, "config", "") or "").db_path
    except ConfigError:
        return args.func(args)            # the command reports the config error
    origin = "schedule" if getattr(args, "scheduled", False) else "terminal"
    with telemetry.job(db_path, args.command, origin):
        code = args.func(args)
        if code:
            telemetry.summary(f"exited with {code}")
        return code


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "dork":
        return run_dork(raw[1:])

    args = build_parser().parse_args(raw)
    _log(args.verbose)
    try:
        if args.command in RECORDED:
            return _recorded(args)
        return args.func(args)
    except ConfigError as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
