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

from jobdork.core import textutil
from jobdork.core.config import Config, Dealbreaker, Locations, Salary
from jobdork.db.store import Role, canonical_url, make_uid
from jobdork.fetch.boards import annualise
from jobdork.search import geo, screen


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
    from jobdork.core.config import OUTPUT_FORMATS
    from jobdork.output import render
    writers = {"html": render.to_html, "json": render.to_json,
               "md": render.to_markdown, "csv": render.to_csv}
    for canonical in set(OUTPUT_FORMATS.values()):
        assert canonical in writers, f"{canonical!r} validates but has no writer"


def test_every_writer_writes_real_database_rows():
    """roles.json failed on every scan once `row.keys()` became `row`."""
    import tempfile

    from jobdork.db.store import Role, Store
    from jobdork.output import render
    with tempfile.TemporaryDirectory() as tmp:
        with Store(Path(tmp) / "t.db") as store:
            store.upsert(Role(platform="greenhouse", company="Acme", title="Engineer",
                              url="https://boards.greenhouse.io/acme/jobs/1",
                              description="Build things."))
            store.conn.commit()
            rows = store.list_roles()
        for name, writer in (("index.html", render.to_html), ("roles.json", render.to_json),
                             ("roles.md", render.to_markdown), ("roles.csv", render.to_csv)):
            path = writer(rows, Path(tmp) / name)
            assert Path(path).read_text(encoding="utf-8"), name
        dumped = render.rows_to_dicts(rows)[0]
        assert dumped["company"] == "Acme" and "description" not in dumped

        # JSON columns come out as JSON, and a stored verdict follows its score.
        with Store(Path(tmp) / "t.db") as store:
            store.set_judgement(rows[0]["uid"], {"score": 30, "verdict": "possible"})
            row = store.list_roles()[0]
        dumped = render.rows_to_dicts([row])[0]
        assert dumped["llm_judgement"]["verdict"] == "weak"
        assert isinstance(dumped["score_parts"], (list, type(None)))


def test_markdown_alias_normalises_to_md():
    """'markdown' and 'md' must not reach the writer as two strings."""
    import os
    import tempfile

    from jobdork.core import config
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
    import os
    import tempfile

    from jobdork.core import config
    from jobdork.core.config import ConfigError
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
    from jobdork.db.store import Role, Store
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

    from jobdork.output import digest
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
    from jobdork.output import digest
    built = digest.build([], _cfg(), new_only=True)
    assert built.empty
    assert "nothing new" in built.subject.lower()


def test_digest_refuses_a_bad_address_before_touching_the_network():
    from jobdork.output import digest
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

    from jobdork.output import digest, render
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
    from jobdork.search import discover
    report = discover.discover("Acme Corporation", fetcher=None)
    assert report.error and "not a domain" in report.error
    assert not report.found


def test_tokens_are_read_from_the_page_not_invented():
    """Vectra's Greenhouse token is `vectranetworks`, not `vectra`."""
    from jobdork.search.discover import _extract
    html = '<script src="https://boards.greenhouse.io/embed/job_board/js?for=vectranetworks"></script>'
    supported, _ = _extract(html, "https://vectra.ai/careers")
    assert [(f.platform, f.token) for f in supported] == [("greenhouse", "vectranetworks")]


def test_every_supported_board_shape_is_recognised():
    from jobdork.search.discover import _extract
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
    from jobdork.search.discover import _extract
    supported, _ = _extract(
        'https://boards.greenhouse.io/embed/job_board?for=realtoken',
        "https://x.test/careers")
    tokens = {f.token for f in supported}
    assert "realtoken" in tokens
    assert "embed" not in tokens and "job_board" not in tokens


def test_platforms_without_an_adapter_are_named_not_hidden():
    """'No adapter' and 'nothing found' are different statements."""
    from jobdork.search.discover import _extract
    _, unsupported = _extract(
        'href="https://acme.wd5.myworkdayjobs.com/careers"',
        "https://acme.test/careers")
    assert unsupported and unsupported[0].platform == "workday"


def test_an_unverified_board_is_never_addable():
    """Banking a guess is worse than leaving it out."""
    from jobdork.search.discover import Found
    for status in ("empty", "unread", "blocked"):
        assert not Found(platform="greenhouse", token="x", status=status).addable
    assert Found(platform="greenhouse", token="x", status="verified").addable
    # Even verified, a platform with no adapter cannot be written.
    assert not Found(platform="workday", token="x", status="verified").addable


def test_add_preserves_comments_and_appends():
    import tempfile

    from jobdork.search import discover
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

        from jobdork.core import config
        cfg = config.load(str(target))
        assert {(c.name, c.token) for c in cfg.sources.companies} == {
            ("Vectra", "vectranetworks"), ("Ramp", "ramp")}



def test_add_matches_a_list_the_dashboard_wrote():
    """A YAML dump puts the dash level with `companies:`; a hand-written file
    indents it. An entry at the other indent is a parse error, and then no
    scan can load the config."""
    import tempfile

    import yaml

    from jobdork.core import config
    from jobdork.search import discover
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "config.yaml"
        target.write_text(yaml.safe_dump({
            "titles": {"include": ["engineer"]},
            "locations": {"anchor": "Chicago, IL", "radius": "exact",
                          "countries": ["US"]},
            "sources": {"companies": [{"name": "Acme", "platform": "ashby",
                                       "token": "acme"}]}}, sort_keys=False))
        discover.add_to_config(str(target), "Ramp", [
            discover.Found(platform="ashby", token="ramp", status="verified")])
        cfg = config.load(str(target))
        assert [c.token for c in cfg.sources.companies] == ["ramp", "acme"]
        # Looked up again: nothing new is written.
        assert discover.add_to_config(str(target), "Ramp", [
            discover.Found(platform="ashby", token="ramp", status="verified")]) == []
        assert len(config.load(str(target)).sources.companies) == 2

# ── cli overrides ──────────────────────────────────────────────────────────────

def _base_config_file(tmpdir) -> str:
    path = Path(tmpdir) / "config.yaml"
    path.write_text(
        "titles: {include: [software engineer]}\n"
        "locations: {anchor: 'Chicago, IL', radius: 25, countries: [US]}\n"
        "sources: {adzuna_countries: [us]}\n",
        encoding="utf-8")
    return str(path)


def test_country_override_moves_units_and_adzuna_together():
    """--country DE must not leave miles and the American index behind."""
    import tempfile

    from jobdork.core import config
    from jobdork.fetch import adzuna
    with tempfile.TemporaryDirectory() as tmp:
        cfg = config.load(_base_config_file(tmp))
        assert cfg.locations.units == "mi" and adzuna._indexes(cfg) == ["us"]

        config.apply_overrides(cfg, countries=["DE"], anchor="Berlin, Germany")
        assert cfg.locations.units == "km", "a German search is in kilometres"
        assert adzuna._indexes(cfg) == ["de"], "a pinned index must not win"


def test_a_km_override_is_converted_not_taken_literally():
    import tempfile

    from jobdork.core import config
    with tempfile.TemporaryDirectory() as tmp:
        cfg = config.load(_base_config_file(tmp))
        config.apply_overrides(cfg, countries=["DE"], anchor="Berlin, Germany",
                               radius=25.0)
        assert abs(cfg.radius_miles() - 15.53) < 0.05


def test_overrides_are_validated_like_the_file():
    """An override must not be a looser way in than the config it replaces."""
    import tempfile

    from jobdork.core import config
    from jobdork.core.config import ConfigError
    with tempfile.TemporaryDirectory() as tmp:
        path = _base_config_file(tmp)
        for bad in ({"countries": ["ZZ"]},
                    {"currency": "XYZ"},
                    {"work_modes": ["telepathic"]},
                    {"resume": "/definitely/not/here.pdf"},
                    {"anchor": "", "radius": 25.0}):
            cfg = config.load(path)
            try:
                config.apply_overrides(cfg, **bad)
            except ConfigError:
                pass
            else:
                raise AssertionError(f"{bad} should have been refused")


def test_every_subcommand_accepts_the_overrides():
    """They belong after the verb, where people write them."""
    from jobdork.cli import build_parser
    parser = build_parser()
    for verb in ("scan", "list", "digest", "rescreen", "sources", "serve",
                 "enrich"):
        args = parser.parse_args([verb, "--anchor", "Berlin, Germany",
                                  "--country", "DE"])
        assert args.anchor == "Berlin, Germany" and args.country == ["DE"], verb


# ── enrich ─────────────────────────────────────────────────────────────────────

def test_a_jobposting_description_is_read_from_json_ld():
    from jobdork.search import enrich
    html = """<html><head>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting",
     "title":"Security Analyst",
     "description":"<p>You will run the SOC.</p><p>Live coding round.</p>"}
    </script></head><body>ignored</body></html>"""
    text = enrich.extract_description(html)
    assert "You will run the SOC." in text
    assert "Live coding round." in text
    assert "<p>" not in text


def test_the_longest_description_wins():
    """A page may carry a teaser block and a full one."""
    from jobdork.search import enrich
    html = ("""<script type="application/ld+json">
            {"@type":"JobPosting","description":"short"}</script>"""
            """<script type="application/ld+json">
            {"@type":"JobPosting","description":"a much longer advert body"}</script>""")
    assert enrich.extract_description(html) == "a much longer advert body"


def test_nested_json_ld_shapes_are_found():
    from jobdork.search import enrich
    for html in (
        '<script type="application/ld+json">[{"@type":"JobPosting",'
        '"description":"in a list"}]</script>',
        '<script type="application/ld+json">{"@graph":[{"@type":"JobPosting",'
        '"description":"in a graph"}]}</script>',
    ):
        assert enrich.extract_description(html)


def test_a_page_with_no_jobposting_yields_nothing():
    from jobdork.search import enrich
    assert enrich.extract_description("<html>no structured data</html>") == ""
    assert enrich.extract_description(
        '<script type="application/ld+json">{"@type":"Organization",'
        '"description":"we are a company"}</script>') == ""
    assert enrich.extract_description(
        '<script type="application/ld+json">{not json</script>') == ""


def test_adzuna_is_never_fetched():
    """Its links answer 403 from bot protection, which is not worked around."""
    from jobdork.search import enrich
    assert "adzuna" in enrich.UNREACHABLE
    assert "403" in enrich.UNREACHABLE["adzuna"]


def test_platforms_that_already_send_full_adverts_are_not_refetched():
    from jobdork.search import enrich
    for platform in ("workable", "greenhouse", "ashby", "lever", "usajobs"):
        assert platform in enrich.ALREADY_FULL


# ── bulk add ───────────────────────────────────────────────────────────────────

def test_a_url_list_tolerates_how_people_paste():
    import tempfile

    from jobdork.cli import _read_url_file
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "urls.txt"
        path.write_text(
            "# pasted from a dork run\n"
            "\n"
            "https://jobs.ashbyhq.com/acme/1\n"
            "- https://jobs.lever.co/acme/2\n"
            "Some Job Title\thttps://job-boards.greenhouse.io/acme/jobs/3\n"
            "https://acme.breezy.hr/p/4,\n",
            encoding="utf-8")
        urls = _read_url_file(str(path))
    assert urls == [
        "https://jobs.ashbyhq.com/acme/1",
        "https://jobs.lever.co/acme/2",
        "https://job-boards.greenhouse.io/acme/jobs/3",
        "https://acme.breezy.hr/p/4",
    ], urls


def test_add_takes_several_urls():
    from jobdork.cli import build_parser
    args = build_parser().parse_args(
        ["add", "https://a.test/1", "https://b.test/2"])
    assert args.url == ["https://a.test/1", "https://b.test/2"]
    assert build_parser().parse_args(["add", "--from-file", "x.txt"]).from_file


def test_the_fuller_advert_wins_a_duplicate_not_the_higher_score():
    """The same role from an aggregator and from the employer's own board.

    Ranking duplicates by score alone kept the worse copy: a Vectra role
    arrived truncated to 500 characters from an aggregator and complete at
    4,701 from Greenhouse, and the truncated one scored higher — tidier
    location string, and no advert content to lose points on. Dealbreakers and
    fit scoring both read the advert, so showing the short copy throws away
    the thing that makes the role screenable.
    """
    import tempfile

    from jobdork.db.store import Role, Store
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "dupes.db")
        try:
            store.upsert(Role(platform="adzuna", company="Vectra",
                              title="Senior Security Engineer",
                              url="https://agg.test/1",
                              description="x" * 500, score=100))
            store.upsert(Role(platform="greenhouse", company="Vectra",
                              title="Senior Security Engineer",
                              url="https://boards.test/1",
                              description="x" * 4701, score=81))
            store.conn.commit()

            shown = store.list_roles()
            assert len(shown) == 1, "the two copies must collapse"
            assert shown[0]["platform"] == "greenhouse", shown[0]["platform"]
            assert len(shown[0]["description"]) == 4701

            assert len(store.list_roles(collapse_duplicates=False)) == 2
        finally:
            store.close()


def test_score_still_decides_between_equally_full_adverts():
    """Bucketed by thousands: 4,700 and 4,900 characters are one advert."""
    import tempfile

    from jobdork.db.store import Role, Store
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "dupes.db")
        try:
            store.upsert(Role(platform="lever", company="Acme", title="Engineer",
                              url="https://a.test/1",
                              description="x" * 4700, score=50))
            store.upsert(Role(platform="ashby", company="Acme", title="Engineer",
                              url="https://b.test/1",
                              description="x" * 4900, score=90))
            store.conn.commit()
            shown = store.list_roles()
            assert len(shown) == 1
            assert shown[0]["platform"] == "ashby", shown[0]["platform"]
        finally:
            store.close()


# ── configurable screening ─────────────────────────────────────────────────────

def test_blockers_can_be_overridden():
    """The default list encodes a judgement about one job market."""
    from jobdork.core.config import Screening
    cfg = _cfg(titles_include=["engineering manager"])
    assert not screen.title_verdict("Engineering Program Manager", cfg)[0]

    # A reader who WANTS programme roles removes the blocker.
    cfg.screening = Screening(blockers=["sales", "account"])
    assert screen.title_verdict("Engineering Program Manager", cfg)[0]


def test_loose_gap_is_configurable():
    from jobdork.core.config import Screening
    cfg = _cfg(titles_include=["head of engineering"])
    title = "Head of Global Platform and Site Reliability Engineering"
    cfg.screening = Screening(loose_gap=0)
    assert not screen.title_verdict(title, cfg)[0]
    cfg.screening = Screening(loose_gap=6)
    assert screen.title_verdict(title, cfg)[0]


def test_extra_arrangement_patterns_add_to_the_defaults():
    """Adding one must not silently lose the built-in ones."""
    from jobdork.core.config import Screening
    cfg = _cfg()
    cfg.screening = Screening(office_patterns=[r"in the (?:Chicago )?office"])

    custom = Role(platform="x", title="Engineer", url="https://x.test/1",
                  description="You will be in the Chicago office daily.")
    assert screen.detect_work_mode(custom, cfg)[0] == "office"

    builtin = Role(platform="x", title="Engineer", url="https://x.test/2",
                   description="This is a fully remote role.")
    assert screen.detect_work_mode(builtin, cfg)[0] == "remote"


def test_a_broken_screening_pattern_stops_the_run():
    import os
    import tempfile

    from jobdork.core import config
    from jobdork.core.config import ConfigError
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write("titles: {include: [engineer]}\n"
                 "locations: {anchor: 'Chicago, IL', radius: exact}\n"
                 "screening: {office_patterns: ['(unclosed']}\n")
        path = fh.name
    try:
        try:
            config.load(path)
        except ConfigError as exc:
            assert "broken pattern" in str(exc)
        else:
            raise AssertionError("a broken pattern must stop the run")
    finally:
        os.unlink(path)


def _in_a_fake_container(tmp, *, marker: bool, variable: bool):
    """cwd = tmp holding the image's example; container signals as asked."""
    import os
    import shutil
    from pathlib import Path

    from jobdork.core import config
    root = Path(__file__).resolve().parent.parent
    shutil.copy(root / "config.example.yaml", Path(tmp) / "config.example.yaml")
    mark = Path(tmp) / ".dockerenv"
    if marker:
        mark.touch()
    config.CONTAINER_MARKERS = (str(mark),)
    os.environ.pop("JOBDORK_CONFIG", None)
    if variable:
        os.environ[config.CONTAINER_ENV] = "1"
    else:
        os.environ.pop(config.CONTAINER_ENV, None)
    os.chdir(tmp)


def _restoring_the_environment(fn):
    def wrapped():
        import os

        from jobdork.core import config
        cwd, markers = os.getcwd(), config.CONTAINER_MARKERS
        saved = {k: os.environ.get(k) for k in (config.CONTAINER_ENV, "JOBDORK_CONFIG")}
        try:
            fn()
        finally:
            os.chdir(cwd)
            config.CONTAINER_MARKERS = markers
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    wrapped.__name__ = fn.__name__
    return wrapped


@_restoring_the_environment
def test_a_container_with_no_config_starts_from_the_example_in_data():
    import tempfile
    from pathlib import Path

    from jobdork.core import config
    with tempfile.TemporaryDirectory() as tmp:
        _in_a_fake_container(tmp, marker=True, variable=True)
        cfg = config.load()
        seeded = Path(tmp) / "data" / "config.yaml"
        assert seeded.is_file(), "the example should be copied into data/"
        assert cfg.path == "data/config.yaml"
        assert any("created from config.example.yaml" in w for w in cfg.warnings)
        # A second start reads the kept copy and does not announce it again.
        seeded.write_text(seeded.read_text() + "\n# edited\n")
        again = config.load()
        assert again.path == "data/config.yaml"
        assert "# edited" in seeded.read_text(), "a kept config is never overwritten"
        assert not any("created from" in w for w in again.warnings)


@_restoring_the_environment
def test_a_mapped_config_yaml_still_wins_over_the_seeded_one():
    import tempfile
    from pathlib import Path

    from jobdork.core import config
    with tempfile.TemporaryDirectory() as tmp:
        _in_a_fake_container(tmp, marker=True, variable=True)
        (Path(tmp) / "config.yaml").write_text("titles: {include: [nurse]}\n")
        cfg = config.load()
        assert cfg.path == "config.yaml"
        assert not (Path(tmp) / "data" / "config.yaml").exists()


@_restoring_the_environment
def test_outside_a_container_no_config_is_written():
    """The variable alone, or the marker alone, is not a container."""
    import tempfile
    from pathlib import Path

    from jobdork.core import config
    from jobdork.core.config import ConfigError
    for marker, variable in ((False, True), (True, False)):
        with tempfile.TemporaryDirectory() as tmp:
            _in_a_fake_container(tmp, marker=marker, variable=variable)
            try:
                config.load()
            except ConfigError as exc:
                assert "No config found" in str(exc)
            else:
                raise AssertionError("no config outside a container must stop the run")
            assert not (Path(tmp) / "data" / "config.yaml").exists()


# ── keep this block LAST ───────────────────────────────────────────────────────

# ── resume fit and thin adverts ───────────────────────────────────────────────

def test_a_teaser_naming_one_skill_is_not_a_perfect_fit():
    """Adzuna's 500 characters named "java" and scored 25 of 25 on it."""
    from jobdork.search.resume import MIN_SKILLS, Resume, fit

    cv = Resume(text="java", skills={"java", "python", "sql", "react", "docker"})
    thin = fit(cv, "We need a Java developer in Chicago.")
    assert thin.matched == ["java"]
    assert thin.score == round(25.0 / MIN_SKILLS, 1), thin.score

    full = fit(cv, "Java, Python, SQL, React and Docker, daily.")
    assert full.score == 25.0, "a full advert you match entirely still scores full"


def test_screening_records_fit_apart_from_the_score():
    from jobdork.search.resume import Resume

    cfg = Config(titles_include=["software engineer"],
                 locations=Locations(anchor="", radius="any", countries=[]),
                 salary=Salary())
    cv = Resume(text="python", skills={"python"})
    role = Role(platform="workable", title="Software Engineer", url="https://x.test/f",
                work_mode="remote", description="Python services.")
    screen.screen(role, cfg, geo.resolve_anchor(""), cv)
    assert role.fit is not None and 0 < role.fit < role.score

    bare = Role(platform="workable", title="Software Engineer", url="https://x.test/g",
                work_mode="remote")
    screen.screen(bare, cfg, geo.resolve_anchor(""), cv)
    assert bare.fit is None, "no advert is not a fit of 0"


def test_a_rescan_does_not_replace_a_fuller_advert_with_a_teaser():
    """The next scan sent Adzuna's 500 characters back over a pasted advert."""
    import tempfile

    from jobdork import fetch
    from jobdork.db.store import Store
    from jobdork.search import scan

    full = "Software engineer. " * 100
    teaser = "Software engineer, short."
    url = "https://x.test/teaser"

    def adapter(_fetcher, _cfg, **_kw):
        return fetch.SourceResult(source="fake", roles=[Role(
            platform="adzuna", title="Software Engineer", url=url,
            work_mode="remote", description=teaser)])

    cfg = Config(titles_include=["software engineer"],
                 locations=Locations(anchor="", radius="any", countries=[]),
                 salary=Salary())
    original_jobs, original_get = scan._jobs_for, fetch.get
    scan._jobs_for = lambda _cfg: [("fake", {})]
    fetch.get = lambda _name: adapter
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg.db_path = str(Path(tmp) / "t.db")
            with Store(cfg.db_path) as store:
                store.upsert(Role(platform="adzuna", title="Software Engineer",
                                  url=url, description=full))
                store.conn.commit()
                report = scan.run(cfg, store)
                assert report.kept == 1, "the role must pass for this to test anything"
                assert store.stored_description(make_uid("adzuna", url)) == full
    finally:
        scan._jobs_for, fetch.get = original_jobs, original_get

def test_every_point_of_the_score_is_explained():
    """The dashboard's hover card must add up to the number beside it."""
    from jobdork.search.resume import Resume

    cfg = Config(titles_include=["software engineer"],
                 locations=Locations(anchor="", radius="any", countries=[]),
                 salary=Salary())
    cv = Resume(text="python", skills={"python"})
    role = Role(platform="workable", title="Software Engineer", url="https://x.test/p",
                work_mode="remote", description="Python and Go services.")
    screen.screen(role, cfg, geo.resolve_anchor(""), cv)
    names = [p["part"] for p in role.score_parts]
    assert names[:2] == ["title", "arrangement"] and names[-1] == "resume fit", names
    assert abs(sum(p["points"] for p in role.score_parts) - role.score) < 0.5
    assert all(p["why"] for p in role.score_parts), "every part says why"
    fit = role.score_parts[-1]
    assert fit["has"] == ["python"] and "go" in fit["wants"]


def test_rescreen_reaches_the_duplicate_copies_the_list_hides():
    """A hidden copy left on its old score outranked the re-screened one."""
    import tempfile

    from jobdork.db.store import Store
    from jobdork.search import scan

    cfg = Config(titles_include=["software engineer"],
                 locations=Locations(anchor="", radius="any", countries=[]),
                 salary=Salary())
    with tempfile.TemporaryDirectory() as tmp:
        cfg.db_path = str(Path(tmp) / "t.db")
        with Store(cfg.db_path) as store:
            for n in (1, 2):
                role = Role(platform="adzuna", company="Acme",
                            title="Software Engineer", work_mode="remote",
                            url=f"https://x.test/copy{n}")
                role.score = 999.0
                store.upsert(role)
            store.conn.commit()
            checked, _, _ = scan.rescreen(cfg, store)
            assert checked == 2
            scores = [r[0] for r in store.conn.execute("SELECT score FROM roles")]
            assert 999.0 not in scores, scores


def test_rescreening_is_not_seeing_the_role_again():
    """rescreen bumped last_seen, so month-old ads looked freshly listed."""
    import tempfile

    from jobdork.db.store import Store
    from jobdork.search import scan

    cfg = Config(titles_include=["software engineer"],
                 locations=Locations(anchor="", radius="any", countries=[]),
                 salary=Salary())
    with tempfile.TemporaryDirectory() as tmp:
        cfg.db_path = str(Path(tmp) / "t.db")
        with Store(cfg.db_path) as store:
            store.upsert(Role(platform="adzuna", title="Software Engineer",
                              work_mode="remote", url="https://x.test/old"))
            store.conn.execute("UPDATE roles SET last_seen = '2026-01-01T00:00:00'")
            store.conn.commit()
            scan.rescreen(cfg, store)
            seen = store.conn.execute("SELECT last_seen FROM roles").fetchone()[0]
            assert seen == "2026-01-01T00:00:00", seen


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
