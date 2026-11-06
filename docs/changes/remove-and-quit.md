## Fixed — 2026-11-05 — Remove jobdork removes it, and a closed jobdork is not running

In 0.16.2 on a Mac, **Settings → Remove jobdork** with everything ticked
seemed to remove nothing: the job posts were still on the page, and jobdork
was still in Applications after quitting. It had removed them, but:

- **The page kept asking the server**, which opened the database again and
  left a new, empty one; the Job posts page still showed the list it had.
  Now, once you confirm, the window shows only **jobdork was removed** and
  one button, the page asks nothing more, and the server answers nothing
  but quitting (410 for anything else).
- **The program stayed.** The page said to drag it to the Trash, and it was
  expected to go by itself. Now quitting removes what you chose once more
  (whatever was opened since is gone too), then moves the program to the
  Trash: the Mac app (only jobdork's own bundle, checked by its bundle id,
  and not a copy run from its disk image or a hidden translocated one) and
  a Linux AppImage (into the desktop's Trash, as freedesktop.org lays it
  out). A .deb still needs `sudo apt remove jobdork`; Windows has its
  uninstaller.
- **What macOS keeps for the window** under `~/Library` (WebKit's storage,
  caches, cookies, saved window state and preferences, by the app's bundle
  id) was left, as was Ask's empty working folder. Both go now, and nothing
  else in `~/Library` is touched.

**Closing the window ends jobdork, on a Mac, Windows and Linux.** Ask's
Claude Code run is stopped with it, and the program ends at once after the
server stops (`app.exit_now`): a scan's fetches, on threads Python would
otherwise wait for, no longer keep it running unseen. A scheduled scan you
turned on still runs without the window, and ends when the scan does.

Tests: the server refuses everything but quitting after a removal; the
Mac's window traces go and another app's do not; a folder given to the
removal never reaches the real `~/Library`; only jobdork's own Mac bundle
or an AppImage is moved, and an AppImage lands in the Trash with its
`.trashinfo`; and the program ends at once with a thread still busy. The
guide's Settings page, the desktop notes and PRIVACY.md say what happens
now; the CLI guide lists `jobdork uninstall`, and ARCHITECTURE.md names
`core/uninstall`.
