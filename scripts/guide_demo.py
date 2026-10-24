#!/usr/bin/env python3
"""
guide_demo.py
=============
A made-up jobdork, for the user guide's screenshots: a settings file, a
resume and a database of job posts, none of them anyone's.

    python scripts/guide_demo.py <folder>

The screenshots are published on the guide's website, so they must never
show a real person's search: the person here (Jordan Rivera, a nurse in
Chicago) and every employer are invented, and every link goes to
example.com. Nothing is fetched: the job posts are written here and scored
by jobdork's own rules (scan.rescreen), so the Match and Fit numbers are
what the app would really give these adverts.

scripts/guide_screenshots.py builds this folder, starts the dashboard on it
and photographs every page. Run that, not this, to refresh the guide.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESUME = """# Jordan Rivera

Chicago, IL · jordan.rivera@example.com

## Summary

Registered nurse with seven years in acute care and telemetry. Charge nurse
on a 32-bed medical-surgical unit; precepted twelve new graduates.

## Experience

**Charge Nurse, Medical-Surgical** | Lakeshore Community Hospital | Chicago, IL | June 2021 - Present
- Lead a team of eight nurses per shift on a 32-bed unit.
- Cut medication errors on the unit by 30% with a bedside barcode scanning rollout.
- Precepted twelve new graduate nurses.

**Registered Nurse, Telemetry** | Prairie View Medical Center | Evanston, IL | May 2018 - May 2021
- Cared for cardiac patients on continuous telemetry monitoring.
- Used Epic for charting and medication administration.

## Education

BSN, Nursing | University of Illinois Chicago | 2018

## Licenses and certifications

RN (Illinois), BLS, ACLS, PALS

## Skills

Patient assessment, telemetry, medication administration, Epic, care
planning, patient education, wound care, IV therapy, leadership, precepting
"""

CONFIG = """# A made-up person's settings, for the user guide's screenshots.
titles:
  include: [registered nurse, charge nurse, nurse manager]
  exclude: [travel, licensed practical]
credentials: [RN, BLS, ACLS]
locations:
  anchor: "Chicago, IL"
  radius: 25
  countries: [US]
  work_modes: [office, hybrid, remote]
salary:
  floor: 75000
  currency: USD
dealbreakers:
  - {words: "night shift only", hard: false}
  - {words: "travel nursing", hard: true}
resume:
  path: {resume}
db: {db}
update_check: false
notifications: {enabled: false}
sources:
  directory: false
llm:
  readers:
    - {provider: ollama, model: gemma4:26b}
    - {provider: ollama, model: qwen2.5:3b}
  checkers:
    - {provider: ollama, model: llama3.2:3b}
  guard: true
"""

ADVERT = """{title} at {company}

About the role
{company} is hiring a {title} to join our {unit} team in {place}. You will lead patient care on a busy unit, work with physicians and pharmacists, and mentor newer nurses.

What you will do
- Assess patients, plan care and give medications safely.
- {duty}
- Chart in Epic and teach patients and families before discharge.

What you need
- Active RN license in Illinois. BLS required; ACLS preferred.
- {years} years of acute care experience; telemetry experience a plus.
- {extra}

Pay and benefits
{pay}. Health, dental and tuition support.
"""

# (company, title, place, platform, unit, duty, years, extra, pay, days ago)
POSTS = [
    ("Northbridge Health", "Charge Nurse - Medical Surgical", "Chicago, IL", "workday",
     "medical-surgical", "Lead the unit on your shift and handle staffing.", "3",
     "Experience as a charge nurse or preceptor.", "$92,000 - $108,000 per year", 1),
    ("Lakeview Regional Hospital", "Registered Nurse - Telemetry", "Evanston, IL",
     "greenhouse", "telemetry", "Monitor cardiac rhythms and respond to alarms.", "2",
     "Telemetry or step-down background.", "$41 - $52 per hour", 3),
    ("Riverside Children's Clinic", "Registered Nurse - Pediatrics", "Oak Park, IL",
     "lever", "pediatric", "Care for children and support their families.", "2",
     "PALS certification.", "", 6),
    ("Harborview Care Partners", "Nurse Manager - Cardiology", "Chicago, IL", "workday",
     "cardiology", "Manage a team of 40 nurses and the unit budget.", "5",
     "Two years in a leadership role; MSN preferred.", "$118,000 - $135,000 per year", 9),
    ("Westfield Medical Group", "Registered Nurse - Remote Care Coordination",
     "Remote (US)", "ashby", "care coordination",
     "Coordinate care for patients by phone and video.", "3",
     "Comfort working from home with telehealth tools.", "$78,000 per year", 2),
    ("Summit Staffing Solutions", "Registered Nurse - Emergency Department",
     "Chicago, IL", "smartrecruiters", "emergency",
     "Triage patients and work with the trauma team.", "2",
     "Our client is a large hospital; night shift only for the first six months.",
     "", 12),
    ("Great Lakes Surgical Center", "Registered Nurse - Pre-Op and PACU", "Skokie, IL",
     "greenhouse", "surgical", "Prepare patients for surgery and recover them after.",
     "2", "PACU or ICU experience.", "$45 per hour", 26),
    ("Midwest Home Health", "Registered Nurse Case Manager", "Naperville, IL", "lever",
     "home health", "Visit patients at home and manage their care plans.", "3",
     "A valid driver's license and your own car.", "$70,000 - $74,000 per year", 5),
]

STATUSES = {0: "interested", 3: "applied", 4: "interviewing", 6: "skipped", 1: "viewed"}

VERDICTS = {
    0: {"score": 86, "summary": "A close match: charge nurse experience on a medical-surgical "
        "unit, Epic and precepting are all in the resume.",
        "reasons": ["Charge nurse on a 32-bed medical-surgical unit",
                    "Precepted twelve new graduate nurses", "Uses Epic"],
        "concerns": ["Staffing duties are not described in the resume"]},
    1: {"score": 74, "summary": "Telemetry experience at Prairie View fits the unit; the "
        "advert asks for two years and the resume shows three.",
        "reasons": ["Three years of telemetry nursing", "ACLS and BLS held"],
        "concerns": ["Most recent role is medical-surgical, not telemetry"]},
    3: {"score": 48, "summary": "Leadership is there as a charge nurse, but managing 40 nurses "
        "and a budget is a step up the resume does not show.",
        "reasons": ["Charge nurse leading eight nurses per shift"],
        "concerns": ["No budget or management experience",
                     "MSN preferred; the resume shows a BSN"]},
}


def build(folder: Path) -> Path:
    """Write the demo into `folder`; return its config file."""
    from jobdork.core.config import load
    from jobdork.db.store import Role, Store
    from jobdork.search import scan as scan_mod

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "data").mkdir(exist_ok=True)
    resume = folder / "data" / "jordan-rivera-resume.md"
    resume.write_text(RESUME, encoding="utf-8")
    config = folder / "config.yaml"
    config.write_text(CONFIG.replace("{resume}", json.dumps(str(resume)))
                      .replace("{db}", json.dumps(str(folder / "data" / "jobdork.db"))),
                      encoding="utf-8")
    cfg = load(str(config))

    now = time.time()
    with Store(cfg.db_path) as store:
        uids = []
        for i, (company, title, place, platform, unit, duty, years, extra, pay,
                ago) in enumerate(POSTS):
            role = Role(platform=platform, company=company, title=title,
                        url=f"https://example.com/{platform}/{i + 1}",
                        location_raw=place,
                        posted_at=time.strftime("%Y-%m-%d", time.localtime(now - ago * 86400)),
                        description=ADVERT.format(title=title, company=company, unit=unit,
                                                  place=place, duty=duty, years=years,
                                                  extra=extra, pay=pay or "Pay to be discussed"))
            _pay(role, pay)
            store.upsert(role)
            uids.append(role.uid)
        scan_mod.rescreen(cfg, store)
        for i, status in STATUSES.items():
            store.set_status(uids[i], status,
                             "Phone screen Tuesday 10am" if status == "interviewing" else "")
        for i, v in VERDICTS.items():
            from jobdork.ai.llm import verdict_for
            claims = len(v["reasons"]) + len(v["concerns"]) + 1
            unsupported = 1 if i == 3 else 0
            guard = {"checked": True, "error": "", "claims": claims,
                     "unsupported": unsupported, "rate": unsupported / claims,
                     "model": "Ollama (local) · llama3.2:3b", "second": True, "note": "",
                     "flagged": [{"claim": "Managed a unit budget", "verdict": "unsupported"}]
                     if unsupported else []}
            text = "\n".join([v["summary"], *v["reasons"], *v["concerns"]])
            output = store.add_ai_output("judge", text, uid=uids[i],
                                         model="Ollama (local) · gemma4:26b", guard=guard)
            store.set_judgement(uids[i], {
                **v, "verdict": verdict_for(v["score"]), "enough_evidence": True,
                "model": "Ollama (local) · gemma4:26b", "advert_chars": 900,
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "guard": guard,
                "ai_output_id": output,
                "second": {"model": "Ollama (local) · llama3.2:3b",
                           "score": v["score"] - (26 if i == 3 else 6),
                           "verdict": verdict_for(v["score"] - (26 if i == 3 else 6)),
                           "summary": "Agrees on the main points."},
                "disagree": i == 3})
        store.set_listing(uids[6], "unlisted", "no longer on the employer's board")
        store.save_project({
            "name": "Falls prevention programme", "kind": "Business or operations",
            "role": "Lead nurse, with two colleagues", "tools": "Morse Fall Scale, bed alarms, staff huddles",
            "situation": "Falls on our unit were above the hospital's target.",
            "task": "Bring falls down within six months.",
            "action": "Introduced hourly rounding and bed alarms for high-risk patients, and trained 30 staff.",
            "result": "Falls fell by 40% in six months."})
        store.save_education({"credential": "MSN, Nursing Leadership", "school": "DePaul University",
                              "location": "Chicago, IL", "start": "Aug 2025",
                              "end": "Expected May 2027"})
        _runs(store, now)
    return config


def _pay(role, pay: str) -> None:
    """The stated pay, as an adapter would read it from the board's own fields."""
    import re

    figures = [float(x.replace(",", "")) for x in re.findall(r"\$([\d,]+)", pay)]
    if not figures:
        return
    from jobdork.fetch.boards import annualise

    period = "hour" if "hour" in pay else "year"
    role.salary_min = annualise(figures[0], period)
    role.salary_max = annualise(figures[-1], period)
    role.salary_currency, role.salary_period, role.salary_stated = "USD", period, True


def _runs(store, now: float) -> None:
    """A week of finished runs, so the Dashboard has something to show."""
    def stamp(t: float) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t))

    for day in range(6, -1, -1):
        at = now - day * 86400 - 3600
        for job, seconds in (("scan", 240), ("check", 60)) if day % 2 == 0 else (("scan", 240),):
            store.conn.execute(
                "INSERT INTO activity(job, origin, pid, started_at, heartbeat_at, finished_at, "
                "state, done, total, counters, hosts, ai, last_line, summary) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job, "schedule" if job == "scan" else "dashboard", 0, stamp(at),
                 stamp(at + seconds), stamp(at + seconds), "done", 1, 1,
                 json.dumps({"kept": 8, "dropped": 112}) if job == "scan" else "{}",
                 json.dumps({"example.com": {"requests": 12, "ok": 12, "client": 0,
                                             "limited": 0, "errors": 0, "seconds": 4.2,
                                             "slowest": 0.8}}),
                 "{}", "done",
                 "workday: 41 roles from 6 boards · greenhouse: 37 roles from 4 boards · "
                 "fetched 120, kept 8, stored 8" if job == "scan" else "checked 8 postings"))
        store.conn.execute(
            "INSERT INTO llm_calls(at, model, purpose, seconds, ok) VALUES(?,?,?,?,?)",
            (stamp(at), "Ollama (local) · gemma4:26b", "judge", 38.0 + day, 1))
    store.conn.commit()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__.split("\n\n")[1])
    print(build(Path(sys.argv[1]).resolve()))
