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
import sys
from pathlib import Path

from . import __version__, config, render, scan as scan_mod
from .config import STATUSES, ConfigError
from .store import Store, canonical_url


def _log(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )


def _load(args) -> config.Config:
    cfg = config.load(getattr(args, "config", "") or "")
    for warning in cfg.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if getattr(args, "db", ""):
        cfg.db_path = args.db
    return cfg


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
        print(f"{score:>4}  {row['title']}  —  {row['company']}")
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
            progress=(lambda line: print(f"  {line}")) if not args.quiet else None,
        )
        print()
        for line in report.lines():
            print(line)

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
            from . import digest as digest_mod
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
                    print(f"digest failed, roles are still stored: {exc}",
                          file=sys.stderr)
    return 0


def cmd_digest(args) -> int:
    """Mail what the last scan found. The point of scheduling a scan."""
    from . import digest as digest_mod

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
        print(f"sent {len(rows)} role{'' if len(rows) == 1 else 's'} "
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
            print(f"\n{len(rows)} role{'' if len(rows) == 1 else 's'}"
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
            print(f"{args.ref!r} matches {len(matches)} roles. "
                  "Give a uid or a URL:")
            _print_roles(matches[:10])
            return 1
        row = matches[0]
        for key in ("uid", "status", "note", "company", "title", "url",
                    "platform", "location_raw", "city", "state", "country",
                    "distance_mi", "work_mode", "posted_at", "first_seen",
                    "last_seen", "score"):
            if key in row.keys() and row[key] not in (None, ""):
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
            print(f"{args.ref!r} matches {len(matches)} roles. "
                  "Narrow it with a uid or a URL:")
            _print_roles(matches[:10])
            return 1
        row = matches[0]
        store.set_status(row["uid"], args.status, args.note)
        print(f"{row['uid']}  {row['title']} — {row['company']}  ->  {args.status}")
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
                  "you have not acted on; roles with a status you set are kept "
                  "either way.")
    return 0


def cmd_add(args) -> int:
    """Fetch one posting by URL — the bridge from a Google result to the database."""
    from . import fetch, geo, screen
    from .fetch.http import Fetcher

    cfg = _load(args)
    url = canonical_url(args.url)
    platform, token = _platform_for(url)
    token = args.token or token
    if not platform:
        print(f"Cannot tell which platform {url} is on. Supported: "
              "greenhouse, ashby, lever, breezy, smartrecruiters. "
              "Pass --platform and --token if you know them.")
        return 1
    if not token:
        print(f"That is a {platform} posting served from the employer's own "
              "domain, so the board token is not in the URL. Re-run with the "
              f"token:\n\n  jobdork add {args.url} --token <board-token>\n\n"
              "The token is the path segment on the board's own URL, e.g. "
              "'stripe' in job-boards.greenhouse.io/stripe/jobs/123.")
        return 1

    adapter = fetch.get(platform)
    fetcher = Fetcher(cfg.fetch.user_agent, cfg.fetch.timeout, cfg.fetch.retries)
    result = adapter(fetcher, cfg, token=token, company=args.company or token)
    if result.skipped:
        print(f"{platform}: {result.skipped}")
        return 1

    wanted = next((r for r in result.roles if canonical_url(r.url) == url), None)
    if wanted is None:
        print(f"Read {token!r} on {platform} ({len(result.roles)} roles) but "
              f"none of them is that URL. It may already be filled.")
        return 1

    anchor = geo.resolve_anchor(cfg.locations.anchor, cfg.country_prefs())
    verdict = screen.screen(wanted, cfg, anchor)
    with Store(cfg.db_path) as store:
        is_new = store.upsert(wanted)
        store.conn.commit()
    state = "added" if is_new else "updated"
    print(f"{state}: {wanted.uid}  {wanted.title} — {wanted.company}")
    if not verdict.keep:
        # Stored anyway: you asked for this one by name, and a filter is not
        # a better judge of that than you are.
        print(f"  note: this does not pass your filters ({verdict.reasons[0]}). "
              "Stored anyway because you asked for it.")
    for flag in verdict.flags:
        print(f"  · {flag}")
    return 0


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
    from . import discover as discover_mod
    from .fetch.http import Fetcher

    cfg = _load(args)
    fetcher = Fetcher(cfg.fetch.user_agent, cfg.fetch.timeout, cfg.fetch.retries)

    print(f"Looking for {args.employer}...")
    report = discover_mod.discover(args.employer, fetcher)
    if report.error:
        print(report.error, file=sys.stderr)
        return 1

    for line in report.lines():
        print(line)

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


def cmd_sources(args) -> int:
    cfg = _load(args)
    print("Active:")
    for name in cfg.active_sources():
        print(f"  {name}")
    for company in cfg.sources.companies:
        print(f"  {company.platform:16} {company.name} (token {company.token})")
    dormant = cfg.dormant_sources()
    if dormant:
        print("\nRegistered but dormant — no credential:")
        for name in dormant:
            where = ("https://developer.usajobs.gov" if name == "usajobs"
                     else "https://developer.adzuna.com/signup")
            print(f"  {name:16} free key at {where}")
        print("\nKeys go in .env, never config.yaml.")
    return 0


def run_dork(rest: list[str]) -> int:
    """Hand over to the original generator, unchanged.

    Dispatched before argparse sees anything, because the generator has its own
    flags — `--list-levels`, `--since`, `--csv` — and argparse would either
    claim them or reject them. `argparse.REMAINDER` is not reliable enough here:
    a leading `--flag` is treated as an option to this parser, not as the
    remainder.
    """
    import runpy
    sys.argv = ["main.py"] + rest
    runpy.run_path(str(Path(__file__).parent.parent / "main.py"),
                   run_name="__main__")
    return 0


def cmd_dork(args) -> int:
    return run_dork(args.rest)


# ── parser ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobdork",
        description="Watch North American job boards and only hear about the "
                    "roles that pass your own filters.",
    )
    parser.add_argument("--version", action="version", version=f"jobdork {__version__}")
    parser.add_argument("-c", "--config", default="",
                        help="config file (default: config.local.yaml, then config.yaml)")
    parser.add_argument("--db", default="", help="override the database path")
    parser.add_argument("-v", "--verbose", action="store_true")
    subs = parser.add_subparsers(dest="command", required=True)

    p = subs.add_parser("scan", help="read the sources, screen, store")
    p.add_argument("--limit", type=int, default=0,
                   help="keep at most N roles — for a quick look")
    p.add_argument("--email", default="",
                   help="mail the new roles after storing them")
    p.add_argument("--csv-attachment", action="store_true",
                   help="attach the roles as CSV to that mail")
    p.add_argument("--even-if-empty", action="store_true",
                   help="send the mail even when nothing is new")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_scan)

    p = subs.add_parser("digest",
                        help="mail what the last scan found, without rescanning")
    p.add_argument("--email", default="", help="recipient; omit to print instead")
    p.add_argument("--all", action="store_true",
                   help="every open role, not only what is new")
    p.add_argument("--csv", action="store_true", help="attach the roles as CSV")
    p.add_argument("--even-if-empty", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="print the message instead of sending it")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_digest)

    p = subs.add_parser("list", help="print stored roles")
    p.add_argument("--new", action="store_true", help="only what was first seen today")
    p.add_argument("--status", default="", choices=("",) + STATUSES)
    p.add_argument("--all", action="store_true", help="include settled roles")
    p.add_argument("--flags", action="store_true", help="show per-role flags")
    p.add_argument("--duplicates", action="store_true",
                   help="show aggregator repeats of the same job")
    p.add_argument("--json", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_list)

    p = subs.add_parser("show", help="one role in full, including the advert")
    p.add_argument("ref", help="uid, posting URL, or company name")
    p.set_defaults(func=cmd_show)

    p = subs.add_parser("applied", help="record what you did about a role")
    p.add_argument("ref", help="uid, posting URL, or company name")
    p.add_argument("-s", "--status", default="applied", choices=STATUSES)
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_applied)

    p = subs.add_parser("rescreen",
                        help="re-apply the current config to what is stored")
    p.add_argument("--remove", action="store_true",
                   help="delete the untouched ones that no longer match")
    p.set_defaults(func=cmd_rescreen)

    p = subs.add_parser("add", help="fetch one posting by URL into the database")
    p.add_argument("url")
    p.add_argument("--token", default="",
                   help="board token, when the URL does not carry one")
    p.add_argument("--company", default="")
    p.set_defaults(func=cmd_add)

    p = subs.add_parser("discover",
                        help="find an employer's board from their own site")
    p.add_argument("employer", help="their website, e.g. stripe.com")
    p.add_argument("--add", action="store_true",
                   help="write verified boards into sources.companies")
    p.add_argument("--name", default="",
                   help="company name to record (default: what you typed)")
    p.set_defaults(func=cmd_discover)

    p = subs.add_parser("sources", help="what will run, and what is dormant")
    p.set_defaults(func=cmd_sources)

    p = subs.add_parser("dork", help="the original Google query generator")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_dork)

    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "dork":
        return run_dork(raw[1:])

    args = build_parser().parse_args(raw)
    _log(args.verbose)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
