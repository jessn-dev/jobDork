## Fixed — 2026-11-10 — Clicking a notification opens jobdork

Clicking one of the desktop app's notifications opened the wrong thing:
Script Editor on a Mac, a folder on Windows. The notifications said nothing
about what a click should open, so each system did what it does by default.

- **Mac.** When the app could not post through macOS's own notifications
  (permission never asked, or asked by a scheduled scan with no window), it
  fell back to `osascript`, whose notifications macOS files under Script
  Editor. The app now asks for permission when its window opens, while you
  are there to answer, and never falls back to `osascript`: a notification
  macOS refuses is logged ("allow it in System Settings, Notifications,
  jobdork") instead. A click on the app's own notification opens jobdork.
  Run any other way (pip, source), it is `osascript` as before.
- **Windows.** The installer registers `jobdork://`, and the app's toasts
  open it when clicked (`launch`, protocol activation), which starts
  jobdork.exe. It reads nothing from the link. Run any other way, the toast
  has no link, as only the app has it registered.
- **Linux.** The app's notification has an **Open jobdork** action where
  `notify-send` has `--action` (libnotify 0.7.9 and later), and is grouped
  under jobdork's desktop entry. A shell of its own waits for the click,
  so it still works after a scheduled scan has ended; the title and text
  go to it as arguments, never into its script.
- **jobdork open already.** A click starts jobdork, and a second one could
  not listen on its port, so nothing showed. Now a second start leaves a
  request in the app's folder; the open one sees it, brings its window to
  the front, and the second one ends (`web/app.py`, `show_open_window`).
  Nothing listening, or something else on the port that does not answer:
  it starts as before.

tests/test_notify.py covers the Mac app without `osascript`, the Windows
app's toast link (and none outside the app), the Linux action with the
title kept out of the script and the plain notification on an older
`notify-send`; tests/test_app.py a second start raising the open window,
and starting as usual with nothing open or nothing answering. Not yet
clicked on a real Windows PC or Linux desktop.
