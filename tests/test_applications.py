"""
Tests for My applications: the dated history of statuses, which jobs count
as applications, an application's details and notes, and the API around
them. On a temporary database; nothing online.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import datetime
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.db import migrations
from jobdork.db.store import Role, Store
from jobdork.web import api


class _Cfg:
    def __init__(self, path: Path):
        self.db_path = path


def _roles(store, n=3, same=False) -> list[str]:
    uids = []
    for i in range(n):
        role = Role(platform="ashby", company="Acme", title="Nurse" if same else f"Nurse {i}",
                    url=f"https://x.test/{i}", location_raw="Chicago, IL")
        store.upsert(role)
        uids.append(role.uid)
    store.conn.commit()
    return uids


def test_each_status_change_is_dated_once():
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store:
        uid = _roles(store, 1)[0]
        store.set_status(uid, "viewed")
        store.set_status(uid, "applied")
        store.set_status(uid, "applied", "a note")
        store.set_status(uid, "interviewing")
        assert [h["status"] for h in store.history(uid)] == ["applied", "interviewing"], \
            "viewed is not a step; the same status again is not a change"


def test_applications_are_the_jobs_applied_to():
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store:
        a, b, c = _roles(store)
        store.set_status(a, "interested")
        store.set_status(b, "applied")
        store.set_status(c, "applied")
        store.set_status(c, "skipped")
        apps = store.applications()
        assert {x["row"]["uid"] for x in apps} == {b, c}, "interested is not applied; skipped after applying is"
        assert all(x["applied_at"] for x in apps)


def test_copies_of_one_job_share_one_application():
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store:
        a, b = _roles(store, 2, same=True)
        store.set_status(a, "applied")
        store.save_application(a, {"next_step": "Call", "next_date": "2026-01-02"})
        store.add_application_note(a, "Spoke to them")
        assert len(store.applications()) == 1, "one job, one row"
        assert store.application(b)["next_step"] == "Call"
        assert [n["note"] for n in store.application_notes(b)] == ["Spoke to them"]
        note = store.application_notes(b)[0]["id"]
        assert store.delete_application_note(b, note)
        assert not store.application_notes(a), "deleted on every copy"


def test_an_old_database_starts_its_history_from_the_status_it_has():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "x.db"
        with Store(path) as store:
            uid = _roles(store, 1)[0]
            store.set_status(uid, "applied")
            store.conn.execute("DELETE FROM status_history")
            store.conn.execute("DELETE FROM meta WHERE key = 'schema_version'")
            store.conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', '14')")
            store.conn.commit()
        with Store(path) as store:
            assert store.applied_migrations == list(range(15, migrations.SCHEMA_VERSION + 1))
            assert [h["status"] for h in store.history(uid)] == ["applied"]


def test_the_list_has_stages_and_overdue_follow_ups():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _Cfg(Path(tmp) / "x.db")
        with Store(cfg.db_path) as store:
            a, b, c = _roles(store)
            for uid in (a, b, c):
                store.set_status(uid, "applied")
            store.set_status(b, "interviewing")
            store.set_status(c, "rejected")
            past = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
            store.save_application(a, {"next_step": "Follow up", "next_date": past})
            store.save_application(c, {"next_step": "Nothing", "next_date": past})
        d = api.list_applications(cfg)
        assert d["counts"] == {"applied": 1, "interviewing": 1, "offer": 0, "closed": 1}
        assert d["overdue"] == 1, "a closed application is never overdue"
        assert next(x for x in d["applications"] if x["uid"] == a)["overdue"]


def test_saving_checks_what_it_is_given():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _Cfg(Path(tmp) / "x.db")
        with Store(cfg.db_path) as store:
            a, b = _roles(store, 2)
            store.set_status(a, "applied")
            other = store.add_artifact(b, "cover_letter", "/x.md")
            mine = store.add_artifact(a, "tailored_resume", "/y.md")
            store.conn.commit()
        bad = [{"next_date": "next week"}, {"contact_email": "not an email"},
               {"contact_link": "javascript:alert(1)"}, {"letter_id": str(other)},
               {"resume_id": "x"}, {"next_step": "x" * 121}]
        for fields in bad:
            try:
                api.save_application(cfg, {"uid": a, **fields})
            except api.ApiError:
                continue
            raise AssertionError(f"accepted {fields}")
        api.save_application(cfg, {"uid": a, "next_step": " Phone   screen ", "next_date": "2026-11-02",
                                   "contact_email": "dana@example.com", "resume_id": str(mine)})
        with Store(cfg.db_path) as store:
            detail = api.application_detail(store, a, [{"id": mine, "kind": "tailored_resume"}])
        assert detail["is_application"] and detail["details"]["next_step"] == "Phone screen"
        assert detail["details"]["resume_id"] == mine and detail["resumes"][0]["id"] == mine
        # Only the contact, as Add a job post sends it: the rest is kept.
        api.save_application(cfg, {"uid": a, "contact_name": "Dana Lee"})
        with Store(cfg.db_path) as store:
            kept = store.application(a)
        assert (kept["contact_name"], kept["next_step"], kept["contact_email"], kept["resume_id"]) \
            == ("Dana Lee", "Phone screen", "dana@example.com", mine)


def test_notes_through_the_api():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _Cfg(Path(tmp) / "x.db")
        with Store(cfg.db_path) as store:
            uid = _roles(store, 1)[0]
            store.set_status(uid, "interviewing")
        for fields in ({"note": "  "}, {"note": "x" * 2001}, {"delete": "999"}):
            try:
                api.application_note(cfg, {"uid": uid, **fields})
            except api.ApiError:
                continue
            raise AssertionError(f"accepted {fields}")
        api.application_note(cfg, {"uid": uid, "note": "Went well"})
        with Store(cfg.db_path) as store:
            (note,) = store.application_notes(uid)
        assert note["stage"] == "interviewing", "filed under the status at the time"
        api.application_note(cfg, {"uid": uid, "delete": str(note["id"])})


def test_deleting_a_job_post_deletes_its_application():
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store:
        uid = _roles(store, 1)[0]
        store.set_status(uid, "applied")
        store.save_application(uid, {"next_step": "Call"})
        store.add_application_note(uid, "hello")
        store.conn.execute("DELETE FROM roles WHERE uid = ?", (uid,))
        store.conn.commit()
        for table in ("status_history", "applications", "application_notes"):
            assert not store.conn.execute(f"SELECT 1 FROM {table}").fetchone(), table  # nosec B608


# ── keep this block LAST ───────────────────────────────────────────────────────

# ── tracking an application sent outside jobdork ─────────────────────────────

def _track_cfg(tmp: str):
    from jobdork.core.config import Config, Locations
    cfg = Config(titles_include=["nurse"], locations=Locations(countries=["US"]))
    cfg.db_path = str(Path(tmp) / "t.db")
    return cfg


ADVERT = "Care for patients on a 30-bed unit. Required: an RN licence. " * 6


def _refused(fn, said: str, status: int = 400):
    try:
        fn()
    except api.ApiError as exc:
        assert said in str(exc) and exc.status == status, (exc, exc.status)
    else:
        raise AssertionError(f"must be refused: {said}")


def test_an_application_tracked_from_a_pasted_advert_is_applied_on_its_day():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _track_cfg(tmp)
        done = api.track_application(cfg, {"url": "https://a.test/1", "title": "Charge Nurse",
                                           "company": "Acme", "text": ADVERT,
                                           "applied_on": "2026-10-20"})
        assert done["tracked"] and done["status"] == "applied" and done["applied_on"] == "2026-10-20"
        listed = api.list_applications(cfg)["applications"]
        assert [(a["uid"], a["applied_at"]) for a in listed] == [(done["uid"], "2026-10-20")]
        with Store(cfg.db_path) as store:
            assert [h["status"] for h in store.history(done["uid"])] == ["applied"]


def test_a_page_that_cannot_be_read_is_tracked_from_its_title_and_employer():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _track_cfg(tmp)
        # lambda: deferred, so _refused can catch what the call raises
        _refused(lambda: api.track_application(cfg, {"url": "https://a.test/2", "title": "Nurse"}),
                 "employer")
        # lambda: deferred, so _refused can catch what the call raises
        _refused(lambda: api.track_application(cfg, {"url": "not a link", "title": "Nurse",
                                                     "company": "Acme"}), "link")
        done = api.track_application(cfg, {"url": "https://a.test/2", "title": "Nurse",
                                           "company": "Acme", "location": "Austin, TX"})
        assert done["tracked"]
        with Store(cfg.db_path) as store:
            row = store.get(done["uid"])
        assert row["status"] == "applied" and row["company"] == "Acme"
        # Today, when no day is given.
        assert done["applied_on"] == datetime.date.today().isoformat()


def test_the_day_applied_is_a_real_day_not_in_the_future():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _track_cfg(tmp)
        base = {"url": "https://a.test/3", "title": "Nurse", "company": "Acme"}
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        # lambda: deferred, so _refused can catch what the call raises
        _refused(lambda: api.track_application(cfg, {**base, "applied_on": tomorrow}), "future")
        # lambda: deferred, so _refused can catch what the call raises
        _refused(lambda: api.track_application(cfg, {**base, "applied_on": "20/10/2026"}), "YYYY-MM-DD")
        # lambda: deferred, so _refused can catch what the call raises
        _refused(lambda: api.track_application(cfg, {**base, "applied_on": "2026-02-30"}), "real date")
        with Store(cfg.db_path) as store:
            assert store.applications() == [], "nothing is stored when the day is refused"


def test_tracking_a_job_already_further_along_leaves_it_there():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _track_cfg(tmp)
        base = {"url": "https://a.test/4", "title": "Nurse", "company": "Acme"}
        first = api.track_application(cfg, base)
        with Store(cfg.db_path) as store:
            store.set_status(first["uid"], "interviewing")
        again = api.track_application(cfg, {**base, "applied_on": "2026-01-02"})
        assert again["uid"] == first["uid"] and not again["tracked"]
        assert again["status"] == "interviewing"


def test_tracking_from_a_link_reads_it_and_a_page_it_cannot_read_asks_for_more():
    from jobdork.fetch import link
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _track_cfg(tmp)
        real = link.read
        try:
            def read(fetcher, cfg_, url, token="", company=""):
                return Role(platform="greenhouse", company="Acme", title="ICU Nurse", url=url,
                            location_raw="Austin, TX", description=ADVERT)
            link.read = read
            done = api.track_application(cfg, {"url": "https://boards.greenhouse.io/acme/jobs/9"})
            assert done["tracked"] and done["title"] == "ICU Nurse"

            def unreadable(*args, **kwargs):
                raise link.LinkError("that page has no job post jobdork can read")
            link.read = unreadable
            # lambda: deferred, so _refused can catch what the call raises
            _refused(lambda: api.track_application(cfg, {"url": "https://a.test/5"}),
                     "Paste the advert", 422)
        finally:
            link.read = real



def test_a_link_that_names_the_job_but_gives_no_advert_asks_for_it():
    """2026-11-09: a page marked up for search engines with no description
    was tracked with an empty advert and nothing said. Now the form is asked
    for the advert, filled with what the link gave."""
    from jobdork.fetch import link
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _track_cfg(tmp)
        real = link._read
        # lambda: a page that gives the job's title and place and no advert.
        link._read = lambda *a, **k: Role(platform="site", company="Acme", title="ICU Nurse",
                                          url="https://a.test/9", location_raw="Austin, TX",
                                          description="Apply now")
        try:
            for call in (lambda: api.track_application(cfg, {"url": "https://a.test/9"}),
                         lambda: api.add_post(cfg, {"url": "https://a.test/9"})):
                try:
                    call()
                except api.ApiError as exc:
                    assert exc.status == 422 and "no advert" in str(exc), exc
                    assert exc.found == {"title": "ICU Nurse", "company": "Acme",
                                         "location": "Austin, TX", "url": "https://a.test/9"}
                else:
                    raise AssertionError("an empty advert was stored")
            with Store(cfg.db_path) as store:
                assert store.list_roles(include_settled=True) == [], "nothing stored"
        finally:
            link._read = real


def test_one_form_adds_a_post_or_tracks_it_when_you_applied():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _track_cfg(tmp)
        added = api.add_post(cfg, {"url": "https://a.test/1", "title": "ICU Nurse",
                                   "company": "Acme", "text": ADVERT})
        assert added["added"] and "tracked" not in added
        today = datetime.date.today().isoformat()
        tracked = api.add_post(cfg, {"url": "https://a.test/2", "title": "Charge Nurse",
                                     "company": "Acme", "text": ADVERT, "applied_on": today})
        assert tracked["tracked"] and tracked["applied_on"] == today
        with Store(cfg.db_path) as store:
            statuses = {r["company"] + r["title"]: r["status"] or "new"
                        for r in store.list_roles(include_settled=True)}
        assert statuses == {"AcmeICU Nurse": "new", "AcmeCharge Nurse": "applied"}


def test_the_documents_you_sent_are_kept_with_the_post_and_read_by_its_tools():
    import os

    from jobdork.ai import writer
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _track_cfg(tmp)
        was = os.environ.get("JOBDORK_DOCS_DIR")
        os.environ["JOBDORK_DOCS_DIR"] = tmp            # never the real ~/Documents
        try:
            done = api.add_post(cfg, {"url": "https://a.test/3", "title": "ICU Nurse",
                                      "company": "Acme", "text": ADVERT,
                                      "applied_on": datetime.date.today().isoformat()})
            uid = done["uid"]
            sent = b"# Jane Doe\n\nICU nurse. RN licence. Epic and telemetry.\n"
            first = api.save_sent_document(cfg, uid, "sent_resume", "my cv.md", sent)
            assert first["name"] == "sent-resume.md" and Path(first["path"]).is_file()
            again = api.save_sent_document(cfg, uid, "sent_resume", "cv.txt", sent)
            assert again["id"] == first["id"], "a new upload keeps the record"
            assert not Path(first["path"]).exists(), "and replaces the file"
            for bad in ("x.exe", ""):
                # lambda: deferred, so _refused can catch what the call raises.
                _refused(lambda bad=bad: api.save_sent_document(cfg, uid, "sent_resume", bad, sent),
                         "not a format")
            # lambda: deferred, as above.
            _refused(lambda: api.save_sent_document(cfg, uid, "notes", "x.md", sent), "kind is")
            _refused(lambda: api.save_sent_document(cfg, "../etc", "sent_resume", "x.md", sent),
                     "not a job post")
            with Store(cfg.db_path) as store:
                detail = api.application_detail(store, uid, [dict(r) for r in store.artifacts(uid)])
                assert [r["kind"] for r in detail["resumes"]] == ["sent_resume"]
                assert "Epic and telemetry" in writer._resume_text(cfg, store, uid)
            api.save_application(cfg, {"uid": uid, "resume_id": str(again["id"])})
            text = api.artifact_text(cfg, again["id"])["text"]
            assert "RN licence" in text
        finally:
            if was is None:
                os.environ.pop("JOBDORK_DOCS_DIR", None)
            else:
                os.environ["JOBDORK_DOCS_DIR"] = was


def test_jobdork_add_applied_on_marks_each_post_applied():
    from types import SimpleNamespace

    from jobdork import cli
    calls, real = [], api.add_post
    # lambda: records what the CLI asks for instead of reading a link.
    api.add_post = lambda cfg, form: calls.append(form) or {
        "uid": "abc", "title": "T", "company": "C", "tracked": True, "applied_on": form["applied_on"]}
    try:
        code = cli._add_applied(object(), ["https://a.test/1", "https://a.test/2"],
                                SimpleNamespace(token="", company="", applied_on="2026-11-01"))
    finally:
        api.add_post = real
    assert code == 0 and [c["applied_on"] for c in calls] == ["2026-11-01", "2026-11-01"]


def test_an_advert_fetched_for_an_application_leaves_it_applied():
    """Fetch missing adverts on a job tracked without its advert: the advert
    is kept, and an advert that misses a filter does not mark it skipped and
    take it off My applications."""
    from jobdork.core.config import Config, Locations
    from jobdork.fetch.http import Response
    from jobdork.search import enrich

    page = ('<script type="application/ld&#x2B;json">{"@type":"JobPosting","title":"Welder",'
            '"description":"' + "Weld steel frames on the night shift. " * 20 + '"}</script>')

    class _Fetcher:
        def get(self, url, **_):
            return Response(url=url, status=200, body=page)

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(titles_include=["nurse"], db_path=str(Path(tmp) / "t.db"),
                     locations=Locations(cities=[], radius="any", countries=[]))
        with Store(cfg.db_path) as store:
            mine = Role(platform="site", company="Acme", title="Welder", url="https://x.test/mine")
            # Another employer: the same title at Acme would be a copy of the
            # same job, and applied with it.
            other = Role(platform="site", company="Bolt", title="Welder", url="https://x.test/other")
            store.upsert(mine)
            store.upsert(other)
            store.set_status(mine.uid, "applied")
            store.conn.commit()
            report = enrich.enrich(cfg, store, _Fetcher())
            assert report.improved == 2
            assert len(store.get(mine.uid)["description"]) > 400
            assert store.conn.execute("SELECT status FROM role_state WHERE uid = ?",
                                      (mine.uid,)).fetchone()[0] == "applied"
            assert report.rescreened_out == [other.uid], "a post nobody acted on is still screened out"

def test_the_funnel_counts_how_applications_went():
    """Applications, interviews, offers, rejections, no reply (and for 30
    days), and replies short of a stage by kind, on the Dashboard."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _Cfg(Path(tmp) / "x.db")
        with Store(cfg.db_path) as store:
            roles = []
            for i in range(6):
                role = Role(platform="ashby", company=f"Co {i}", title=f"Nurse {i}",
                            url=f"https://x.test/{i}", location_raw="Chicago, IL")
                store.upsert(role)
                roles.append(role.uid)
            store.conn.commit()
            a, b, c, d, e, f = roles
            store.set_status(a, "applied", when="2026-09-01T12:00:00")
            for uid, after in ((b, "interviewing"), (c, "offer"), (d, "rejected")):
                store.set_status(uid, "applied", when="2026-10-20T12:00:00")
                store.set_status(uid, after)
            store.set_status(e, "applied", when="2026-11-08T12:00:00")
            store.set_status(f, "applied", when="2026-11-11T12:00:00")
            store.add_reply(e, "viewed", "2026-11-10")
            funnel = api.application_funnel(store, store.applications(),
                                            today=datetime.date(2026, 11, 13))
        assert (funnel["applications"], funnel["interviews"], funnel["offers"],
                funnel["rejected_or_closed"]) == (6, 2, 1, 1)
        assert funnel["replied"] == 4, "an interview, an offer, a rejection and a viewed notice"
        assert (funnel["no_reply"], funnel["no_reply_30"]) == (2, 1)
        assert funnel["replies"] == {"viewed": 1, "recruiter_call": 0, "questionnaire": 0, "other": 0}


def test_a_reply_is_added_checked_and_deleted():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _Cfg(Path(tmp) / "x.db")
        with Store(cfg.db_path) as store:
            uid = _roles(store, 1)[0]
            store.set_status(uid, "applied")
        added = api.application_reply(cfg, {"uid": uid, "kind": "recruiter_call",
                                            "on_day": "2026-11-12", "note": "Dana, 15 min"})
        for bad in ({"kind": "ghosted"}, {"kind": "viewed", "on_day": "2999-01-01"},
                    {"kind": "viewed", "on_day": "12/11/2026"}):
            try:
                api.application_reply(cfg, {"uid": uid, **bad})
            except api.ApiError:
                continue
            raise AssertionError(f"accepted {bad}")
        with Store(cfg.db_path) as store:
            detail = api.application_detail(store, uid, [])
        assert [(r["label"], r["note"]) for r in detail["replies"]] == [("Recruiter call", "Dana, 15 min")]
        assert api.application_reply(cfg, {"uid": uid, "delete": str(added["id"])}) == {"deleted": True}
        with Store(cfg.db_path) as store:
            assert store.replies(uid) == []


def test_the_rejection_review_finds_what_rejections_have_in_common():
    """A skill asked for in every rejection and not on the resume, a job
    title the resume never names, and how they scored against the one that
    reached an interview: a checklist, read from the data, no AI."""
    from types import SimpleNamespace

    with tempfile.TemporaryDirectory() as tmp:
        resume = Path(tmp) / "me.md"
        resume.write_text("# Jo Bloggs\n\nSUMMARY\nNurse with Python and SQL.\n\n"
                          "EXPERIENCE\nNurse, Mercy, 2020 - 2024\n- Ran SQL reports.\n",
                          encoding="utf-8")
        cfg = SimpleNamespace(db_path=Path(tmp) / "x.db", resume_path=str(resume))
        advert = ("Requirements: Kubernetes, Terraform and Python. " * 3)
        with Store(cfg.db_path) as store:
            uids = []
            for i, (title, score) in enumerate((("Platform Engineer", 40), ("Platform Engineer II", 45),
                                                ("Data Analyst", 85))):
                role = Role(platform="ashby", company=f"Co {i}", title=title,
                            url=f"https://x.test/{i}", location_raw="Remote",
                            description=advert)
                role.score = score
                store.upsert(role)
                uids.append(role.uid)
            store.conn.commit()
            for uid in uids:
                store.set_status(uid, "applied")
            store.set_status(uids[0], "rejected")
            store.set_status(uids[1], "rejected")
            store.set_status(uids[2], "interviewing")
        review = api.rejection_review(cfg)
    assert review["count"] == 2 and not review["enough"]
    checks = {c["id"]: c for c in review["checklist"]}
    assert not checks["keywords"]["ok"]
    assert any(i.startswith("Kubernetes: missing in 2 of 2") for i in checks["keywords"]["items"])
    assert not checks["titles"]["ok"] and "Platform Engineer" in checks["titles"]["items"]
    assert checks["format"]["ok"], "a Markdown resume has no layout to trip on"
    assert review["scores"]["rejected"]["match"] < review["scores"]["interviews"]["match"]
    assert {r["company"] for r in review["rejections"]} == {"Co 0", "Co 1"}


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
