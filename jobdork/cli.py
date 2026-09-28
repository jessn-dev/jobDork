"""
jobdork.cli
===========
The command line. Everything the dashboard can do has a command here, and the
dashboard is a convenience rather than the product.

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
            "letter", "review")


def _load(args) -> config.Config:
    cfg = config.load(getattr(args, "config", "") or "")
    for warning in cfg.warnings:
        print(f"warning: {warning}", file=sys.stderr)

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
                print(f"      · {flag}")
        print(f"      {row['url']}")


# ── commands ───────────────────────────────────────────────────────────────────

def cmd_scan(args) -> int:
    cfg = _load(args)
    with Store(cfg.db_path) as store:
        report = scan_mod.run(
            cfg, store, limit=args.limit,
            progress=(lambda line: _say(f"  {line}")) if not args.quiet else None,
        )
        print()
        for line in report.lines():
            print(line)
        _summary(report)

        out_dir = Path(cfg.output.dir)
        rows = store.list_roles()
        writers = {
            "html": lambda: render.to_html(rows, out_dir / "index.html", cfg, report),
            "json": lambda: render.to_json(rows, out_dir / "roles.json"),
            "md":   lambda: render.to_markdown(rows, out_dir / "roles.md", cfg, report),
            "csv":  lambda: render.to_csv(rows, out_dir / "roles.csv"),
        }
        for fmt in cfg.output.formats:
            write = writers.get(fmt)
            if write is None:
                # Unreachable: the config validator rejects unknown formats.
                # Kept so that adding one to that list and forgetting to add
                # it here fails loudly rather than writing nothing.
                print(f"no writer for output format {fmt!r}", file=sys.stderr)
                continue
            print(f"wrote {write()}")

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
             store, anchor, quiet: bool = False) -> str:
    """Returns one of: added, updated, failed."""
    from . import fetch
    from .search import screen

    url = canonical_url(url)
    platform, found_token = _platform_for(url)
    token = token or found_token
    if not platform:
        if not quiet:
            print(f"  ? {url}\n      cannot tell which platform this is on")
        return "failed"
    if not token:
        if not quiet:
            print(f"  ? {url}\n      {platform} posting on the employer's own "
                  "domain; the board token is not in the URL. "
                  "Re-run that one with --token")
        return "failed"

    adapter = fetch.get(platform)
    result = adapter(fetcher, cfg, token=token, company=company or token)
    if result.skipped:
        if not quiet:
            print(f"  ! {platform}: {result.skipped}")
        return "failed"

    wanted = next((r for r in result.roles if canonical_url(r.url) == url), None)
    if wanted is None:
        if not quiet:
            print(f"  - {url}\n      read {token!r} on {platform} "
                  f"({len(result.roles)} job posts) but none is that URL; "
                  "it may already be filled")
        return "failed"

    verdict = screen.screen(wanted, cfg, anchor)
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
    from .search import geo

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
    anchor = geo.resolve_anchor(cfg.locations.anchor, cfg.country_prefs())
    tally = {"added": 0, "updated": 0, "failed": 0}

    with Store(cfg.db_path) as store:
        for url in urls:
            tally[_add_one(cfg, fetcher, url, args.token, args.company,
                           store, anchor)] += 1
        store.conn.commit()

    if len(urls) > 1:
        print(f"\n{tally['added']} added, {tally['updated']} updated, "
              f"{tally['failed']} could not be read")
    return 0 if tally["added"] or tally["updated"] else 1


def _platform_for(url: str) -> tuple[str, str]:
    """Work out the platform and board token from a posting URL.

    Returns ("greenhouse", "") for a `?gh_jid=` link on an employer's own
    domain: the platform is certain but the board token is not in the URL,
    so the caller has to be told to supply it rather than shown a guess.
    """
    import re
    patterns = (
        (r"(?:job-)?boards\.greenhouse\.io/([^/?]+)", "greenhouse"),
        (r"jobs\.ashbyhq\.com/([^/?]+)", "ashby"),
        (r"jobs\.lever\.co/([^/?]+)", "lever"),
        (r"([a-z0-9-]+)\.breezy\.hr", "breezy"),
        (r"jobs\.smartrecruiters\.com/([^/?]+)", "smartrecruiters"),
        (r"api\.smartrecruiters\.com/v1/companies/([^/?]+)", "smartrecruiters"),
    )
    for pattern, platform in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return platform, match.group(1)

    # Greenhouse boards are frequently served from the employer's own domain
    # with the job id in the query string. The platform is unambiguous; the
    # board token is not present at all.
    if re.search(r"[?&]gh_jid=", url, re.IGNORECASE):
        return "greenhouse", ""
    return "", ""


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
    return 0


def cmd_generate(args) -> int:
    """Screen a role, or draft a CV or cover letter. Spends tokens."""
    from .ai import guard
    from .writing import generate as gen

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
    """Have the configured model read the best roles against your résumé."""
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


def cmd_review(args) -> int:
    """A résumé review: general, or against one job post with its uid."""
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
    _summary_text(f"{len(result.health)} résumé point(s) (output {result.output_id})")
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

    cfg = _load(args)
    return serve_mod.serve(cfg, port=args.port,
                           open_browser=not args.no_open,
                           token=args.token)


def cmd_sources(args) -> int:
    cfg = _load(args)
    print("Active:")
    for name in cfg.active_sources():
        print(f"  {name}")
    for company in cfg.sources.companies:
        print(f"  {company.platform:16} {company.name} (token {company.token})")
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
            print("\nKeys go in .env, never config.yaml.")
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
                       help='e.g. "Berlin, Germany" or "Chicago, IL"')
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
        description="Watch North American job boards and only hear about the "
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
    p.add_argument("-q", "--quiet", action="store_true")
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
                        help="AI reads top job posts against your résumé (llm: in "
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
                             "your résumé and the advert")
    p.add_argument("uid", help="the job post's uid, URL or company")
    p.add_argument("--dir", default="", help="job folders root "
                                              "(default ~/Documents/job-applications)")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_letter)

    p = subs.add_parser("review", parents=[over],
                        help="AI résumé review; give a job post id to compare with it")
    p.add_argument("uid", nargs="?", default="", help="compare with this job post")
    p.add_argument("--dir", default="", help="job folders root "
                                              "(default ~/Documents/job-applications)")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_review)

    p = subs.add_parser("serve", parents=[over], help="the dashboard, at 127.0.0.1:8765")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-open", action="store_true",
                   help="do not open a browser")
    p.add_argument("--token", default="",
                   help="use this token instead of a fresh one; for a parent "
                        "process that spawned jobdork and already has one")
    p.set_defaults(func=cmd_serve)

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
    with telemetry.job(db_path, args.command, "terminal"):
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
