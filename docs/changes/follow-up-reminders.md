## Added — 2026-11-05 — Follow-up reminders as your computer's notifications

A next step on My applications (a phone screen, a follow-up email) used to
show only inside jobdork, in red once its date had passed. Now your
computer reminds you on the day it is due, with the same notifications a
scan uses: *Follow-up due today: Phone screen, Acme*, or one notification
naming several when more are due at once.

jobdork looks when it opens, every ten minutes while it stays open (a date
comes due at midnight), and after each scheduled scan, so with a daily scan
on the reminder comes that day even with the window closed. Each next step
is told once for its date, kept in the database, so reopening jobdork does
not repeat it; a new date is told again on its day. **Settings →
Notifications** has **Turn off follow-up reminders**
(`notifications.reminders` in config.yaml).

`core/reminders.py` does it. Tests cover which next steps are due (today and
before, not on an ended application, oldest first), the words of one and of
several, each told once for its date and again for a new one, a notification
that did not show not counted as told, the setting off, and the setting read
and written.
