## Added — 2026-11-11 — A Notifications page, and notifications that stay until closed

Asked for on 2026-11-11.

**Notifications**, a new item in the menu, lists every notification jobdork
sent, newest first, with when: the ones closed on the desktop and the ones
the computer could not show (in Docker). A count beside it says how many
are unseen; opening the page marks them seen. A click opens what it was
about (new job posts: Job posts; a follow-up: My applications; a failed
scan: the Dashboard; a newer jobdork: Settings). **Clear all** empties it,
and with none the page says only "You have no notifications from jobdork",
in the middle. Each one is kept in a new `notifications` table (created on
open, so an older database gains it), the newest 500, and the same words
within a day once: a follow-up reminder the desktop could not show is tried
again at every check. Nothing is kept before there is a database.

**A click on a notification opens the Notifications page** (asked the
same day): jobdork starts there, or its open window comes to the front and
turns to it. Windows' toast opens `jobdork://notifications`, the Linux
click starts it with `--notifications`, and on a Mac the app answers the
click itself (a UserNotifications delegate, set before it finishes
launching so a click that starts it counts too); an open window is told
through the same request file a second start already used
(`app.open_view`, the page's `openView`). Not yet tried on a real desktop:
the Mac click and the Windows protocol are checked only by tests here.

**Desktop notifications stay until closed.** Windows: a reminder toast,
with Windows' own Dismiss button, which Windows needs to keep one on
screen. Linux: `notify-send --urgency=critical --expire-time=0` (GNOME
keeps only a critical one). The Mac app: `NSUserNotificationAlertStyle =
alert` in its Info.plist, so its notifications are Alerts rather than
banners by default; System Settings can still change it, and jobdork run
outside the app (osascript) still shows banners, which macOS closes.

The guide's Settings page says so, with a new picture
(`notifications.png`; the demo has three notifications). The rest of the
pictures, whose menus now lack the new item, are retaken with the next
release's pictures. tests/test_notifications_page.py covers keeping one
with or without a desktop, the count, seen, Clear all, once a day, the 500,
no database, and the three systems' staying; tests/test_notify.py and
tests/test_guide.py follow the reminder toast and the new page.
