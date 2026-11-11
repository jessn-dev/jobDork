## Security — 2026-11-11 — The dashboard is opened to your network only where its token cannot be read

From the code scan of 2026-11-06 (Claude Security F2). With
`JOBDORK_ALLOW_HOSTS`, the dashboard listened on every network address over
plain HTTP, and its access token, the only thing that keeps others out,
crossed the network readable with every request: anyone on the same
network could take it and use the dashboard.

Now an address in `JOBDORK_ALLOW_HOSTS` is opened only when the token
cannot be read on the way:

- **Over HTTPS**: `JOBDORK_TLS_CERT` and `JOBDORK_TLS_KEY` name a
  certificate and its key (`tailscale cert` makes one for a Tailscale
  name), and the dashboard is served over HTTPS, TLS 1.2 or newer, with the
  printed addresses starting `https://` (`serve.wrap_tls`).
- **By Tailscale**: a Tailscale name (`*.ts.net`) or address
  (100.64.0.0/10) is opened as before, since Tailscale encrypts its
  traffic.
- **Plain HTTP, accepted out loud**: `JOBDORK_ALLOW_HTTP=1`.

Otherwise that address is not opened, and the log says which and what to
set; the Tailscale names in the same list still are, and with none left
jobdork stays on this computer. **This changes a NAS set up from the
guide**: its home-network address stops answering until HTTPS or
`JOBDORK_ALLOW_HTTP=1` is chosen; its Tailscale name keeps working.

`docs/run/nas.md`, `docs/run/docker.md`, `docs/CONFIG.md`, `compose.yaml`
and the Dockerfile's comments say so. tests/test_lan_https.py covers plain
HTTP kept on this computer, Tailscale names kept, the explicit yes, and the
dashboard's server answering over HTTPS with a certificate made for the
test (and not over plain HTTP); tests/test_serve.py's network tests accept
plain HTTP out loud.
