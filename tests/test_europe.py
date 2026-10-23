"""
Two sources for Europe: the Bundesagentur für Arbeit's job search (Germany)
and Arbeitnow (Germany and the rest of Europe). Shapes are the live answers
of 2026-10-23; nothing here touches the network.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import base64
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import arbeitnow, arbeitsagentur
from jobdork.fetch.http import Response
from jobdork.search import agency


class _Answers:
    """Answers by URL, and records what was asked."""

    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def get(self, url, params=None, headers=None, **_):
        self.asked.append((url, dict(params or {}), dict(headers or {})))
        body = self.answer(url, params or {})
        if body is None:
            return Response(url=url, status=404, error="HTTP 404")
        return Response(url=url, status=200, json=body)


def _ba_job(ref, title, city="Berlin", **extra):
    return {"referenznummer": ref, "stellenangebotsTitel": title, "firma": "Charité",
            "stellenlokationen": [{"adresse": {"ort": city, "land": "DEUTSCHLAND"}}],
            "datumErsteVeroeffentlichung": "2026-10-21", **extra}


def _cfg(*titles, countries=("DE",), anchor="Berlin, Germany", radius="25"):
    return Config(titles_include=list(titles),
                  locations=Locations(anchor=anchor, radius=radius, units="km",
                                      countries=list(countries)))


def test_bundesagentur_searches_your_place_and_reads_adverts_for_your_titles():
    jobs = [_ba_job("10-1-S", "Pflegefachkraft (m/w/d)", gehaltsspanneVon=28.0,
                    gehaltsspanneBis=30.0, verguetungsangabe="STUNDENLOHN"),
            _ba_job("10-2-S", "Hausmeister (m/w/d)")]

    def answer(url, params):
        if url == arbeitsagentur.SEARCH:
            return {"ergebnisliste": jobs, "maxErgebnisse": 2}
        if url == arbeitsagentur.DETAIL + base64.b64encode(b"10-1-S").decode():
            return {"stellenangebotsBeschreibung": "<p>Pflege auf Station 4.</p>",
                    "istArbeitnehmerUeberlassung": True}
        return None

    fetcher = _Answers(answer)
    result = arbeitsagentur.fetch(fetcher, _cfg("Pflegefachkraft"))
    _, params, headers = fetcher.asked[0]
    assert params["was"] == "Pflegefachkraft" and params["wo"] == "Berlin"
    assert params["umkreis"] == 25 and params["angebotsart"] == 1
    assert headers == arbeitsagentur.HEADERS
    nurse, caretaker = result.roles
    assert nurse.url == arbeitsagentur.PAGE + "10-1-S"
    assert nurse.description == "Pflege auf Station 4." and nurse.location_raw == "Berlin, Germany"
    assert nurse.salary_currency == "EUR" and nurse.salary_period == "hour"
    assert nurse.salary_min > 50_000                 # 28 € an hour, a year's worth
    assert nurse.flags == ["temporary staffing (Arbeitnehmerüberlassung)"]
    # The caretaker is not one of your titles: kept, no advert requested.
    assert caretaker.description == "" and len(fetcher.asked) == 2


def test_bundesagentur_runs_only_for_germany_and_searches_all_of_it_from_abroad():
    # lambda: an answer that is never asked for; the source skips first.
    assert "Germany is not in" in arbeitsagentur.fetch(_Answers(lambda u, p: None),
                                                       _cfg("x", countries=("US",))).skipped
    # lambda: every search answers empty, whatever was asked.
    fetcher = _Answers(lambda u, p: {"ergebnisliste": [], "maxErgebnisse": 0})
    arbeitsagentur.fetch(fetcher, _cfg("Krankenpfleger", countries=("PH", "DE"),
                                       anchor="Baguio, Philippines"))
    assert "wo" not in fetcher.asked[0][1]


def test_the_agency_is_asked_for_a_city_by_its_german_name():
    assert arbeitsagentur._where(_cfg("x", anchor="Munich, Germany"))[0] == "München"
    assert arbeitsagentur._where(_cfg("x", anchor="Berlin, Germany"))[0] == "Berlin"


def test_the_bundesagenturs_own_agency_marks_make_it_a_recruiters_post():
    poster = agency.classify("Charité", "", "",
                             ["temporary staffing (Arbeitnehmerüberlassung)"])
    assert poster.agency and "Bundesagentur" in poster.why
    assert not agency.classify("Charité", "", "", ["remote worldwide"]).agency


def test_a_job_the_agency_no_longer_lists_is_closed():
    from jobdork.search.listing import Checker

    def answer(url, params):
        gone = url.endswith(base64.b64encode(b"10-9-S").decode())
        return None if gone else {"stellenangebotsTitel": "Pflegefachkraft"}

    checker = Checker(_Answers(answer))
    closed = checker._arbeitsagentur(arbeitsagentur.PAGE + "10-9-S")
    assert closed.state == "closed" and closed.hard
    assert checker._arbeitsagentur(arbeitsagentur.PAGE + "10-1-S").state == "open"
    assert arbeitsagentur.record(checker.fetcher, "https://example.com/job/1") == ({}, False)


TODAY = dt.date(2026, 10, 23)


def _now_job(title, days_old, **extra):
    stamp = int(dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc).timestamp()) - days_old * 86400
    return {"slug": title.lower().replace(" ", "-"), "title": title, "company_name": "Apaleo",
            "url": f"https://www.arbeitnow.com/jobs/companies/apaleo/{days_old}",
            "location": "Munich", "remote": False, "description": "<p>Build things.</p>",
            "created_at": stamp, **extra}


def test_arbeitnow_reads_newest_pages_and_keeps_your_titles():
    pages = {1: [_now_job("Senior Software Engineer", 1, remote=True),
                 _now_job("Buchhalter", 2)],
             2: [_now_job("Software Engineer", 30)]}

    def answer(url, params):
        page = params["page"]
        return {"data": pages.get(page, []),
                "links": {"next": f"{url}?page={page + 1}" if page < 3 else None}}

    fetcher = _Answers(answer)
    result = arbeitnow.fetch(fetcher, _cfg("software engineer", countries=("DE", "NL")),
                             today=TODAY)
    assert [r.title for r in result.roles] == ["Senior Software Engineer"]
    role = result.roles[0]
    assert role.work_mode == "remote" and role.posted_at == "2026-10-22"
    assert role.description == "Build things." and role.company == "Apaleo"
    # Page 2 reached jobs older than MAX_DAYS: no page 3.
    assert [p["page"] for _, p, _ in fetcher.asked] == [1, 2]


def test_a_bare_city_gets_its_country_so_screening_can_place_it():
    role = arbeitnow.to_role(_now_job("Engineer", 1, location="Amsterdam"))
    assert role.location_raw == "Amsterdam, Netherlands"
    assert arbeitnow._place("Nantes; Paris") == "Nantes, France; Paris, France"
    assert arbeitnow._place("Munich, Bavaria, Germany") == "Munich, Bavaria, Germany"
    assert arbeitnow._place("") == ""


def test_arbeitnow_runs_only_for_europe():
    # lambda: an answer that is never asked for; the source skips first.
    result = arbeitnow.fetch(_Answers(lambda u, p: None), _cfg("x", countries=("US",)))
    assert "Europe only" in result.skipped
    # lambda: every page answers empty, whatever was asked.
    empty = arbeitnow.fetch(_Answers(lambda u, p: {"data": [], "links": {}}),
                            _cfg("x", countries=()), today=TODAY)
    assert empty.suspect                             # the board is never empty


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
