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
  per address.

## Point the app at it

- Every copy uses `RELAY_URL` in `jobdork/core/feedback.py`, this relay's
  address: pip, Docker and the desktop app alike. A relay moved elsewhere
  means changing it there.
- `JOBDORK_FEEDBACK_URL` in `.env` or the environment replaces it for one
  copy (your own relay, a test one), and `off` turns Send off.

## What it accepts

`POST` JSON, at most 9 MB: `kind` (problem, idea, question), `title`, `body`
(the text the app's preview showed), `reply_to` (optional) and up to three
PNG, JPEG or WebP `screenshots` as `{name, type, data}` with base64 `data`.
It answers `{"issue_url": "..."}`.
