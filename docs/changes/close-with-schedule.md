## Added — 2026-11-05 — Closing jobdork asks about a scheduled scan; a schedule turned off is kept

Closing the jobdork window said nothing about a scheduled scan, so it was
easy to think closing stopped it, or that jobdork had to stay open for it.
Neither is so: your computer's scheduler starts the scan with jobdork
closed, and it stops when it is done. Turning a schedule off also lost it:
setting it up again meant picking the days and time again.

Now closing the desktop app with a scan scheduled asks **Keep the scheduled
scan?**, saying when it runs: **Keep it and close**, **Turn it off and
close**, or **Cancel**. *Don't ask again when I close jobdork* stops the
question (`ask_on_close: false`); **Ask when I close jobdork**, under the
schedule in Settings, brings it back. A job still running is asked about
first, as before. The question is the page's own: the window holds the close
back, the page says it is asking, and a page that does not answer within
three seconds lets the window close anyway, so jobdork is never stuck open.

A schedule turned off, here or in Settings, is kept (`schedule_saved`):
Settings shows *Off. Kept from before: every day at 08:00*, with **Run it
now** and **Turn it back on**.

`web/app.py ask_before_closing` holds the close and asks the page through
`window.run_js` (pywebview's `evaluate_js` wraps it in `eval`, which the
page's policy refuses); `api.close_question` says whether to ask;
`api.schedule_save` keeps the plan when turning it off and takes
`every=saved`. Tests cover the page asking and the window held, a page that
cannot ask (closed anyway), nothing scheduled (no question), the question
only for a schedule this copy runs and not when turned off, a kept schedule
written, read back and turned on again, nothing kept to turn on, and a kept
schedule jobdork cannot read ignored. Checked in a real app window on a
temporary folder: the page asked, the window stayed open, and **Keep it and
close** closed it.
