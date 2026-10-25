# Settings

The gear at the bottom of the menu: how jobdork looks, runs by itself, tells
you things and keeps itself up to date.

![Settings](images/settings.png)

## Appearance

**Dark mode** on or off. Until you choose, it follows your computer's
light or dark setting.

## Schedule a run

Your computer starts a scan at the time you pick, whether or not jobdork is
open, and the new job posts are waiting the next time you look.

- **Scan**: *Never by itself*, *Every day*, *Every weekday* or *Once a
  week* (then pick the day), **at** a time. **Save**.
- A time missed while the computer was asleep runs when it wakes.
- Once a day is plenty: job boards are read slowly on purpose, and more
  scans get you blocked for a while.
- **Run a scan now** starts one at once.

It uses your computer's own scheduler (launchd on a Mac, Task Scheduler on
Windows, cron on Linux). In Docker there is no scheduler inside the
container: use the host's, as the
[Docker guide](https://github.com/jessn-dev/jobDork/blob/main/docs/run/docker.md#scans-that-run-by-themselves)
shows.

## Notifications

Your computer's own notifications, with a bell, when a scan finds new job
posts (yours or the schedule's), when a scan fails, and when a newer
jobdork is out. Never for a scan that found nothing new.

Turn them off, or their sound off, with the buttons here. **Send a test
notification** checks they reach you. (On a Mac the first one asks your
permission; in Docker, the page rings a bell while it is open instead.)

## Updates

Which version you have and whether a newer one is out.

- **Check now** asks at once.
- **Update** (in the desktop app) downloads the new installer, checks it
  was built by jobdork's own release workflow (its checksum and its build
  attestation), and opens it; one that fails the check is deleted, not
  opened. Elsewhere it says how to update your copy, with **Release page**.
- **Turn off the daily check** stops jobdork asking GitHub once a day. That
  check is one request for the number of the latest release; nothing about
  you is sent ([privacy policy](https://github.com/jessn-dev/jobDork/blob/main/PRIVACY.md)).

## Built-in employer boards

All of the [built-in employer boards](sources.md#built-in-employer-boards)
on or off at once. Choose industries, or switch single boards off, on the
Sources page.

## Where your files are

Buttons that open the folders jobdork keeps things in: settings and the
database, your resume, your letters and resumes, logs and backups. Use them
to back up, move to another computer, or attach a log to a
[feedback report](feedback.md).

## Clean up job posts

Delete old job posts you are not pursuing:

- **Older than** 15 or 30 days, or
- **With status** rejected, withdrawn, skipped or closed.

**Preview** first lists what would go; nothing is deleted until you press
the red button. Posts you applied to, or are interviewing or have an offer
for, are always kept. The database is backed up to `data/backups/` before
every delete, and a deleted post stays deleted: later scans leave it out.
