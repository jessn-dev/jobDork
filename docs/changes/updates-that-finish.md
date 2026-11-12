## Fixed — 2026-11-12 — Updates finish on Windows and Linux, and a What's new list after one

Reported on 2026-11-12: on Windows and Linux, an update from 0.16.3 ran but
the old version stayed.

- **Windows.** jobdork started the new installer while it was still open
  and closed itself seconds later. The installer could find it open (its
  close question waiting on a scheduled scan), and, running silently, went
  on without the files it could not replace, then opened the old version.
  Now the installer is started only once jobdork has quit (a hidden
  PowerShell that waits for it, `updates.run_windows_installer_after_quit`)
  and writes a log (`logs/update-install.log`). The installer itself waits
  up to a minute for a running jobdork to close and closes it if it will not
  (`CloseApplications=force`, `PrepareToInstall`, packaging/jobdork.iss), so
  an update started from 0.16.4 or 0.16.3, whose old code starts it early,
  finishes too.
- **Linux, the .deb.** The version was read from the downloaded file's name
  as `jobdork-0.16.4-…`, which a .deb (`jobdork_0.16.4_amd64.deb`) never
  matched, so a .deb was never installed, only its folder opened. Read now
  with either separator. That fix is in the new version's code, so moving
  off 0.16.4 or older with a .deb needs one install by hand (`sudo apt
  install ./jobdork_<version>_amd64.deb`).
- **What's new.** The first time jobdork opens on a newer version, a window
  lists what changed for you: the release entry's list
  (`jobdork/data/whats-new.json`, written by `scripts/whats_new.py`), once,
  with a link to the release page. A new copy shows nothing; one updated
  from before this existed, with job posts already, shows it.
  tests/test_whats_new.py fails while the list names another version than
  pyproject.toml.
- **Notifications:** "You have no notifications from jobdork" is in the
  middle of the page, not of a narrower box.

tests/test_whats_new.py covers the list, when it is shown, the .deb's name
and the Windows installer's start; the guide's Settings page says so.
