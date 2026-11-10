# Feedback relay

The Dashboard's **Feedback** page sends a problem, an idea or a question here.
This small service holds the keys, so the app never does: a key built into an
installed app can be read by anyone who has the app.

It opens a GitHub issue (the public record) and emails the maintainers. The
email carries the screenshots and the reporter's address as Reply-To; neither
goes on the public issue. If one of the two fails, the other is still sent.

Deployed at `https://jobdork-feedback.jessengolab-dev.workers.dev`, which
is jobdork's built-in `RELAY_URL`. With sending off (`JOBDORK_FEEDBACK_URL=off`)
the Feedback page offers "Open as a GitHub issue" (prefilled, in the browser)
and "Save as a file" instead of Send.

## Deploy (Cloudflare Workers, free tier)

From this folder, with Node 18 or later; `wrangler.toml` is here already.
It gets its own `jobdork-feedback.<account>.workers.dev` address and touches
no domain or site of yours.

```sh
cd relay/feedback
node test.mjs                                       # the logic, offline
npx wrangler@4.150.0 login                          # opens the browser
npx wrangler@4.150.0 deploy
npx wrangler@4.150.0 secret bulk .env               # the secrets below, from a file
```

The secrets go in `relay/feedback/.env` (git ignores it; `chmod 600` it),
one `NAME=value` per line, and `secret bulk` sends them all. Not the
repository's own `.env`: jobdork loads that one at start, and these keys
are the relay's, not the app's. `npx wrangler@4.150.0 secret put NAME`
sets one by hand instead.

- **GITHUB_TOKEN**: a fine-grained token for this one repository with
  *Issues: read and write* and nothing else. The labels `bug`,
  `enhancement`, `question` and `from-app` exist; an issue whose label is
  missing is filed without labels rather than lost.
- **RESEND_API_KEY**: a key with *sending access* only.
- **FEEDBACK_TO**: where reports are emailed. A secret only so the address
  is not in this public repository.
- **FEEDBACK_FROM**: `jobdork feedback <feedback@your-verified-domain>`.
  Without it the relay sends as Resend's test sender, `onboarding@resend.dev`,
  which Resend lets mail only the address the account was opened with: set
  FEEDBACK_TO to that one.
- **Rate limit** (recommended once the address is public):
  `npx wrangler@4.150.0 kv namespace create FEEDBACK_KV`, put the id in
  `wrangler.toml`'s `[[kv_namespaces]]`, deploy again: five reports an hour
  per address, forty an hour in all. An IPv6 sender counts by its /64.
  `wrangler.toml`'s `[[ratelimits]]` binding (`FEEDBACK_LIMITER`) adds a
  limit per minute that holds even for requests sent all at once, which the
  KV counts alone do not (they read and write in two steps). Both are
  optional: the relay runs without either.

## Point the app at it

- Every copy uses `RELAY_URL` in `jobdork/core/feedback.py`, this relay's
  address: pip, Docker and the desktop app alike. A relay moved elsewhere
  means changing it there.
- `JOBDORK_FEEDBACK_URL` in `.env` or the environment replaces it for one
  copy (your own relay, a test one), and `off` turns Send off.

## What it accepts

`POST` JSON (`Content-Type: application/json`, anything else is refused
with 415), at most 9 MB: `kind` (problem, idea, question), `title`, `body`
(the text the app's preview showed), `reply_to` (optional) and up to three
PNG, JPEG or WebP `screenshots` as `{name, type, data}` with base64 `data`.
It answers `{"issue_url": "..."}`.

Anyone can post here, not only the app, so the relay checks for itself:

- Each screenshot must decode from base64 to at most 2 MB and start the way
  its type does (PNG, JPEG or WebP). The email names it `screenshot-1.png`
  and so on from that type; the `name` sent is never used.
- The issue's body is the report's text inside a code fence longer than any
  run of backticks in it, so nothing in it renders: no mentions, issue
  references, links or images. The title gets a zero-width joiner after
  each `@` and `#`, so it mentions and references nothing either.
