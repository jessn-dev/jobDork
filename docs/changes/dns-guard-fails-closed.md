## Security — 2026-11-09 — A name that cannot be looked up is not fetched

The check that keeps jobdork to public addresses let a name through when
its own lookup failed, "to fail as the request would". But then nothing was
pinned, so the connection looked the name up again, unchecked. A server
built for it could fail the first lookup on purpose and answer the second
with your router's or this machine's address, and a sitemap, a robots.txt
or a job post's link could send jobdork there (Claude Security, 2026-11-09).

Now a name that does not resolve, or resolves to no usable address, is
refused at the check and never connected to (`fetch/http.py`, `checked`).
It is reported as a connection error (`Unresolved`), not as a private
address, so a passing DNS hiccup is still asked again as before, and each
try is checked again. Through a proxy the proxy still looks the name up
itself, as before. tests/test_fetch_guard.py: a name that fails to resolve
is refused, an empty answer too, and the fetcher retries without ever
connecting.
