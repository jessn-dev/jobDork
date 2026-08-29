"""
Tests for the rules that are easy to get quietly wrong.

Every case here is one that either bit during development or would silently
throw away real jobs if it regressed. There is no pytest dependency: run
`python tests/run_all.py`, or use pytest if you have it.

The `__main__` block stays at the very END of this file. Collecting globals()
partway up sees only the tests defined above it and reports a full pass having
run half the file.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork import geo, screen, textutil                      # noqa: E402
from jobdork.config import Config, Dealbreaker, Locations, Salary  # noqa: E402
from jobdork.fetch.boards import annualise                     # noqa: E402
from jobdork.store import Role, canonical_url, make_uid        # noqa: E402


def _cfg(**kwargs) -> Config:
    cfg = Config(
        titles_include=["software engineer", "backend engineer"],
        titles_exclude=["sales engineer"],
        locations=Locations(anchor="Austin, TX", radius=25,
                            countries=["US", "CA"]),
        salary=Salary(floor=None, currency="USD"),
    )
    for key, value in kwargs.items():
        setattr(cfg, key, value)
    return cfg


# ── geo ────────────────────────────────────────────────────────────────────────

def test_dc_is_not_washington_state():
    """'Washington, D.C.' resolving to WA is a 2,300-mile error."""
    for text in ("Washington, D.C.", "Washington, DC", "Washington, D.C"):
        resolved = geo.resolve(text)
        assert resolved.state == "DC", f"{text!r} -> {resolved.state}"
    assert geo.resolve("Washington").state == "WA"


def test_remote_string_keeps_its_country():
    """A remote role still has a legal boundary, and it is the whole point."""
    assert geo.resolve("Remote - US").country == "US"
    assert geo.resolve("Remote, Canada").country == "CA"
    assert geo.resolve("Remote (US)").country == "US"


def test_metro_names_resolve_and_are_marked_approximate():
    for text, city in (("Bay Area", "San Francisco"), ("GTA", "Toronto"),
                       ("DMV", "Washington"), ("Silicon Valley", "San Jose")):
        resolved = geo.resolve(text)
        assert resolved.city == city, f"{text!r} -> {resolved.city}"
        assert resolved.approximate, f"{text!r} should be marked approximate"


def test_unreadable_location_is_not_pretended_to_be_read():
    resolved = geo.resolve("Nowhereville, ZZ")
    assert not resolved.located
    assert resolved.note


def test_state_spellings_agree():
    assert geo.resolve("Austin, TX").city == geo.resolve("Austin, Texas").city
    assert geo.normalise_state("California") == "CA"
    assert geo.normalise_state("Ontario") == "ON"
    assert geo.normalise_state("nonsense") == ""


def test_miles_to_km_for_adzuna():
    """Adzuna's `distance` is kilometres; sending miles shrinks the search."""
    assert round(geo.miles_to_km(25)) == 40
    assert round(geo.miles_to_km(5)) == 8


def test_distance_is_actually_measured():
    austin = geo.resolve("Austin, TX")
    round_rock = geo.resolve("Round Rock, TX")
    dallas = geo.resolve("Dallas, TX")
    near = geo.distance_between(austin, round_rock)
    far = geo.distance_between(austin, dallas)
    assert 10 < near < 25, near
    assert 150 < far < 220, far


# ── titles ─────────────────────────────────────────────────────────────────────

def test_exact_title_beats_loose_title():
    cfg = _cfg()
    matched, _, exact = screen.title_verdict("Software Engineer", cfg)
    assert matched
    matched, _, loose = screen.title_verdict("Engineer, Software Platform", cfg)
    assert matched
    assert exact > loose


def test_blocker_word_refuses_a_different_job():
    """'Engineering Program Manager' is not an engineering manager."""
    cfg = _cfg(titles_include=["engineering manager"])
    matched, _, _ = screen.title_verdict("Engineering Program Manager", cfg)
    assert not matched
    matched, _, _ = screen.title_verdict("Manager, Engineering Platform", cfg)
    assert matched


def test_exclude_wins_over_include():
    cfg = _cfg()
    matched, why, _ = screen.title_verdict("Sales Engineer", cfg)
    assert not matched and "excluded" in why


def test_partial_word_does_not_match():
    cfg = _cfg(titles_include=["engineer"])
    matched, _, _ = screen.title_verdict("Engineering Director", cfg)
    assert not matched, "'engineer' should not match inside 'engineering'"


# ── the salary rule ────────────────────────────────────────────────────────────

def test_unstated_salary_is_shown_not_hidden():
    """Most postings state nothing. Hiding them throws away the market."""
    cfg = _cfg(salary=Salary(floor=200000, currency="USD"))
    role = Role(platform="workable", title="Software Engineer",
                url="https://x.test/1", salary_stated=False)
    keep, _, _, flags = screen.salary_verdict(role, cfg)
    assert keep
    assert "unconfirmed salary" in flags


def test_stated_salary_below_floor_is_hidden():
    cfg = _cfg(salary=Salary(floor=200000, currency="USD"))
    role = Role(platform="workable", title="Software Engineer",
                url="https://x.test/1", salary_min=90000, salary_max=110000,
                salary_currency="USD", salary_stated=True)
    keep, why, _, _ = screen.salary_verdict(role, cfg)
    assert not keep and "below floor" in why


def test_other_currency_is_flagged_never_converted():
    """A wrong exchange rate drops real jobs quietly."""
    cfg = _cfg(salary=Salary(floor=200000, currency="USD"))
    role = Role(platform="workable", title="Software Engineer",
                url="https://x.test/1", salary_min=90000, salary_max=110000,
                salary_currency="CAD", salary_stated=True)
    keep, _, _, flags = screen.salary_verdict(role, cfg)
    assert keep
    assert any("not compared" in f for f in flags)


def test_day_and_hour_rates_are_annualised():
    """$600 a day is $156,000 a year, not $600."""
    assert annualise(600, "day") == 156000.0
    assert annualise(100, "hour") == 208000.0
    assert annualise(150000, "year") == 150000.0
    assert annualise(500, "fortnight") is None


# ── work arrangement ───────────────────────────────────────────────────────────

def test_platform_stated_mode_beats_the_advert():
    role = Role(platform="workable", title="Software Engineer",
                url="https://x.test/1", work_mode="hybrid",
                description="We are a fully remote company.")
    mode, _ = screen.detect_work_mode(role)
    assert mode == "hybrid"


def test_tethered_remote_is_not_remote():
    """'Remote, must live within 50 miles of the office' is hybrid."""
    role = Role(platform="greenhouse", title="Software Engineer",
                url="https://x.test/1",
                description="This is a remote role. You must live within 50 "
                            "miles of our Austin office.")
    mode, flags = screen.detect_work_mode(role)
    assert mode == "hybrid"
    assert any("near an office" in f for f in flags)


def test_unstated_arrangement_is_kept_and_flagged():
    cfg = _cfg(locations=Locations(anchor="", radius="exact",
                                   countries=["US", "CA"],
                                   work_modes=["remote"]))
    role = Role(platform="lever", title="Software Engineer",
                url="https://x.test/1", description="A job at a company.")
    verdict = screen.screen(role, cfg)
    assert verdict.keep, "an unstated arrangement must never be dropped"
    assert "arrangement not stated" in verdict.flags


def test_stated_wrong_mode_is_dropped():
    cfg = _cfg(locations=Locations(anchor="", radius="exact",
                                   countries=["US", "CA"],
                                   work_modes=["remote"]))
    role = Role(platform="workable", title="Software Engineer",
                url="https://x.test/1", work_mode="office")
    verdict = screen.screen(role, cfg)
    assert not verdict.keep


# ── location filtering ─────────────────────────────────────────────────────────

def test_remote_bypasses_the_radius():
    """Distance to a job with no office is not a number that means anything."""
    cfg = _cfg()
    role = Role(platform="workable", title="Software Engineer",
                url="https://x.test/1", location_raw="Seattle, WA",
                work_mode="remote")
    verdict = screen.screen(role, cfg)
    assert verdict.keep


def test_far_office_role_is_dropped():
    cfg = _cfg()
    role = Role(platform="workable", title="Software Engineer",
                url="https://x.test/1", location_raw="Seattle, WA",
                work_mode="office")
    verdict = screen.screen(role, cfg)
    assert not verdict.keep and "outside" in verdict.reasons[0]


def test_nearby_office_role_is_kept():
    cfg = _cfg()
    role = Role(platform="workable", title="Software Engineer",
                url="https://x.test/1", location_raw="Round Rock, TX",
                work_mode="office")
    verdict = screen.screen(role, cfg)
    assert verdict.keep
    assert role.distance_mi is not None and role.distance_mi < 25


def test_unresolvable_location_is_kept_not_dropped():
    """'We could not read it' is not evidence the job is far away."""
    cfg = _cfg()
    role = Role(platform="workable", title="Software Engineer",
                url="https://x.test/1", location_raw="Somewhere Nice",
                work_mode="office")
    verdict = screen.screen(role, cfg)
    assert verdict.keep
    assert any("not resolved" in f for f in verdict.flags)


def test_country_outside_scope_is_dropped():
    cfg = _cfg()
    role = Role(platform="workable", title="Software Engineer",
                url="https://x.test/1",
                location_raw="Berlin, Berlin, Germany", work_mode="office")
    verdict = screen.screen(role, cfg)
    assert not verdict.keep


# ── dealbreakers ───────────────────────────────────────────────────────────────

def test_hard_dealbreaker_hides_and_soft_one_warns():
    hard = Dealbreaker(name="coding round", pattern="live coding", hard=True)
    soft = Dealbreaker(name="on-call", pattern="on.?call rotation", hard=False)
    import re
    hard.regex = re.compile(hard.pattern, re.IGNORECASE)
    soft.regex = re.compile(soft.pattern, re.IGNORECASE)

    cfg = _cfg(dealbreakers=[hard])
    role = Role(platform="x", title="Software Engineer", url="https://x.test/1",
                description="There is a live coding exercise.")
    keep, why, _, _ = screen.dealbreaker_verdict(role, cfg)
    assert not keep and "coding round" in why

    cfg = _cfg(dealbreakers=[soft])
    role = Role(platform="x", title="Software Engineer", url="https://x.test/1",
                description="You will join the on-call rotation.")
    keep, _, _, flags = screen.dealbreaker_verdict(role, cfg)
    assert keep and any("on-call" in f for f in flags)


def test_missing_advert_says_so_rather_than_passing_silently():
    rule = Dealbreaker(name="coding round", pattern="live coding", hard=True)
    import re
    rule.regex = re.compile(rule.pattern, re.IGNORECASE)
    cfg = _cfg(dealbreakers=[rule])
    role = Role(platform="x", title="Software Engineer",
                url="https://x.test/1", description="")
    keep, _, _, flags = screen.dealbreaker_verdict(role, cfg)
    assert keep
    assert any("not checked" in f for f in flags)


# ── identity ───────────────────────────────────────────────────────────────────

def test_tracking_params_are_stripped_but_gh_jid_is_not():
    """gh_jid identifies the posting. Stripping it collapses a whole board."""
    a = make_uid("greenhouse", "https://x.test/jobs?gh_jid=1&utm_source=li")
    b = make_uid("greenhouse", "https://x.test/jobs?gh_jid=1")
    c = make_uid("greenhouse", "https://x.test/jobs?gh_jid=2")
    assert a == b, "utm_source should not change identity"
    assert a != c, "gh_jid must change identity"


def test_url_canonicalisation_ignores_case_slash_and_fragment():
    one = canonical_url("https://X.test/Jobs/1/#apply")
    two = canonical_url("https://x.test/Jobs/1")
    assert one == two, (one, two)


# ── html ───────────────────────────────────────────────────────────────────────

def test_escaped_html_is_unescaped_before_stripping():
    """Greenhouse sends `&lt;p&gt;`; a naive stripper returns the entities."""
    out = textutil.to_text("&lt;p&gt;Live coding&lt;/p&gt;")
    assert "Live coding" in out
    assert "&lt;" not in out and "<p>" not in out


def test_tags_do_not_hide_a_dealbreaker_match():
    out = textutil.to_text("<p>live<span> </span>coding round</p>")
    assert "live coding round" in " ".join(out.split()).lower()



# ── output formats ─────────────────────────────────────────────────────────────

def test_every_accepted_format_has_a_writer():
    """A format that validates and then writes nothing is a silent failure."""
    from jobdork import cli, render
    from jobdork.config import OUTPUT_FORMATS
    writers = {"html": render.to_html, "json": render.to_json,
               "md": render.to_markdown, "csv": render.to_csv}
    for canonical in set(OUTPUT_FORMATS.values()):
        assert canonical in writers, f"{canonical!r} validates but has no writer"


def test_markdown_alias_normalises_to_md():
    """'markdown' and 'md' must not reach the writer as two strings."""
    import tempfile, os
    from jobdork import config
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write("titles: {include: [engineer]}\n"
                 "locations: {anchor: 'Chicago, IL', radius: exact}\n"
                 "output: {formats: [markdown, md, json]}\n")
        path = fh.name
    try:
        cfg = config.load(path)
        assert cfg.output.formats == ["md", "json"], cfg.output.formats
    finally:
        os.unlink(path)


def test_unknown_format_is_refused():
    import tempfile, os
    from jobdork import config
    from jobdork.config import ConfigError
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write("titles: {include: [engineer]}\n"
                 "locations: {anchor: 'Chicago, IL', radius: exact}\n"
                 "output: {formats: [pdf]}\n")
        path = fh.name
    try:
        try:
            config.load(path)
        except ConfigError as exc:
            assert "pdf" in str(exc)
        else:
            raise AssertionError("an unknown format should stop the run")
    finally:
        os.unlink(path)


# ── digest ─────────────────────────────────────────────────────────────────────

def _seeded_store(tmpdir):
    """A store with one finished run, and roles seen before and during it."""
    from jobdork.store import Role, Store
    store = Store(Path(tmpdir) / "d.db")

    # An older role, stored before any run was recorded.
    store.upsert(Role(platform="workable", title="Software Engineer",
                      company="Old Co", url="https://x.test/old",
                      location_raw="Chicago, Illinois"))
    store.conn.commit()
    store.conn.execute("UPDATE roles SET first_seen = '2026-01-01T00:00:00'")
    store.conn.commit()

    run_id = store.start_run()
    store.upsert(Role(platform="workable", title="Software Engineer",
                      company="New Co", url="https://x.test/new",
                      location_raw="Chicago, Illinois"))
    store.conn.commit()
    store.finish_run(run_id, {})
    return store


def test_new_means_seen_in_the_last_run_not_on_the_last_date():
    """Scanning twice in one day must not resend the first scan's roles."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        store = _seeded_store(tmp)
        try:
            new = store.list_roles(new_only=True)
            assert len(new) == 1, [r["company"] for r in new]
            assert new[0]["company"] == "New Co"
            assert len(store.list_roles()) == 2
        finally:
            store.close()


def test_digest_renders_without_credentials():
    """Building a digest must never need a key; only sending does."""
    import tempfile
    from jobdork import digest
    with tempfile.TemporaryDirectory() as tmp:
        store = _seeded_store(tmp)
        try:
            built = digest.build(store.list_roles(), _cfg(), new_only=False)
        finally:
            store.close()
    assert not built.empty
    assert "Software Engineer" in built.text
    assert "Software Engineer" in built.html
    assert built.subject.startswith("jobdork")


def test_digest_reports_an_empty_result_rather_than_pretending():
    from jobdork import digest
    built = digest.build([], _cfg(), new_only=True)
    assert built.empty
    assert "nothing new" in built.subject.lower()


def test_digest_refuses_a_bad_address_before_touching_the_network():
    from jobdork import digest
    built = digest.build([], _cfg())
    for bad in ("", "not-an-email", "a@b", "@example.com"):
        try:
            digest.send(built, bad)
        except digest.DigestError as exc:
            assert "email address" in str(exc) or "RESEND" in str(exc)
        else:
            raise AssertionError(f"{bad!r} should not be accepted")


def test_digest_csv_matches_the_normal_writer():
    """One CSV implementation, so inbox and out/roles.csv cannot drift."""
    import csv as csvmod
    import io
    import tempfile
    from jobdork import digest, render
    with tempfile.TemporaryDirectory() as tmp:
        store = _seeded_store(tmp)
        try:
            rows = store.list_roles()
            built = digest.attach_csv(digest.build(rows, _cfg()), rows)
            written = render.to_csv(rows, Path(tmp) / "roles.csv")
        finally:
            store.close()
        header_a = next(csvmod.reader(io.StringIO(built.csv_bytes.decode())))
        with written.open(encoding="utf-8") as fh:
            header_b = next(csvmod.reader(fh))
        assert header_a == header_b == list(render.CSV_COLUMNS)


# ── discover ───────────────────────────────────────────────────────────────────

def test_a_name_is_refused_because_guessing_a_domain_is_guessing():
    from jobdork import discover
    report = discover.discover("Acme Corporation", fetcher=None)
    assert report.error and "not a domain" in report.error
    assert not report.found


def test_tokens_are_read_from_the_page_not_invented():
    """Vectra's Greenhouse token is `vectranetworks`, not `vectra`."""
    from jobdork.discover import _extract
    html = '<script src="https://boards.greenhouse.io/embed/job_board/js?for=vectranetworks"></script>'
    supported, _ = _extract(html, "https://vectra.ai/careers")
    assert [(f.platform, f.token) for f in supported] == [("greenhouse", "vectranetworks")]


def test_every_supported_board_shape_is_recognised():
    from jobdork.discover import _extract
    cases = {
        'href="https://job-boards.greenhouse.io/acme/jobs/1"': ("greenhouse", "acme"),
        'href="https://jobs.ashbyhq.com/primer.io/abc"': ("ashby", "primer.io"),
        'href="https://jobs.lever.co/leverdemo/abc"': ("lever", "leverdemo"),
        'href="https://jobs.eu.lever.co/eudemo/abc"': ("lever", "eudemo"),
        'href="https://acme.breezy.hr/p/1"': ("breezy", "acme"),
        'href="https://jobs.smartrecruiters.com/AcmeInc/1"': ("smartrecruiters", "AcmeInc"),
    }
    for html, expected in cases.items():
        supported, _ = _extract(html, "https://x.test/careers")
        assert (supported[0].platform, supported[0].token) == expected, html


def test_url_furniture_is_not_mistaken_for_a_token():
    from jobdork.discover import _extract
    supported, _ = _extract(
        'https://boards.greenhouse.io/embed/job_board?for=realtoken',
        "https://x.test/careers")
    tokens = {f.token for f in supported}
    assert "realtoken" in tokens
    assert "embed" not in tokens and "job_board" not in tokens


def test_platforms_without_an_adapter_are_named_not_hidden():
    """'No adapter' and 'nothing found' are different statements."""
    from jobdork.discover import _extract
    _, unsupported = _extract(
        'href="https://acme.wd5.myworkdayjobs.com/careers"',
        "https://acme.test/careers")
    assert unsupported and unsupported[0].platform == "workday"


def test_an_unverified_board_is_never_addable():
    """Banking a guess is worse than leaving it out."""
    from jobdork.discover import Found
    for status in ("empty", "unread", "blocked"):
        assert not Found(platform="greenhouse", token="x", status=status).addable
    assert Found(platform="greenhouse", token="x", status="verified").addable
    # Even verified, a platform with no adapter cannot be written.
    assert not Found(platform="workday", token="x", status="verified").addable


def test_add_preserves_comments_and_appends():
    import tempfile
    from jobdork import discover
    example = Path(__file__).resolve().parent.parent / "config.example.yaml"
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "config.yaml"
        target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        before = target.read_text().count("#")

        discover.add_to_config(str(target), "Vectra", [
            discover.Found(platform="greenhouse", token="vectranetworks",
                           status="verified")])
        discover.add_to_config(str(target), "Ramp", [
            discover.Found(platform="ashby", token="ramp", status="verified")])

        text = target.read_text()
        assert text.count("#") == before, "comments must survive the rewrite"
        assert "token: vectranetworks" in text and "token: ramp" in text

        from jobdork import config
        cfg = config.load(str(target))
        assert {(c.name, c.token) for c in cfg.sources.companies} == {
            ("Vectra", "vectranetworks"), ("Ramp", "ramp")}


# ── keep this block LAST ───────────────────────────────────────────────────────

if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except BaseException as exc:            # SystemExit must not end the run
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
