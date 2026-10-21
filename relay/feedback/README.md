# Feedback relay

The Dashboard's **Feedback** page sends a problem, an idea or a question here.
This small service holds the keys, so the app never does: a key built into an
installed app can be read by anyone who has the app.

It opens a GitHub issue (the public record) and emails the maintainers. The
email carries the screenshots and the reporter's address as Reply-To; neither
goes on the public issue. If one of the two fails, the other is still sent.

Not deployed yet. Until it is, the Feedback page offers "Open as a GitHub
issue" (prefilled, in the browser) and "Save as a file" instead of Send.

## Deploy (Cloudflare Workers, free tier)

```sh
npm create cloudflare@latest jobdork-feedback   # "Hello World" Worker
cp relay/feedback/worker.js jobdork-feedback/src/index.js
cd jobdork-feedback
npx wrangler kv namespace create FEEDBACK_KV     # optional: 5 reports an hour per address
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put RESEND_API_KEY
npx wrangler deploy
```

`wrangler.toml`:

```toml
[vars]
GITHUB_REPO = "jessn-dev/jobDork"
FEEDBACK_TO = "you@example.com"
FEEDBACK_FROM = "jobdork feedback <feedback@your-verified-domain>"

[[kv_namespaces]]
binding = "FEEDBACK_KV"
id = "<from the kv namespace create step>"
```

- **GITHUB_TOKEN**: a fine-grained token for this one repository with
  *Issues: read and write* and nothing else. Labels `bug`, `enhancement`,
  `question` and `from-app` must exist in the repository.
- **RESEND_API_KEY**: a key with *sending access* only, on a verified domain.

## Point the app at it

- Packaged builds: set `RELAY_URL` in `jobdork/core/feedback.py` to the
  Worker's `https://` address before building.
- Any copy: `JOBDORK_FEEDBACK_URL=https://jobdork-feedback.<you>.workers.dev`
  in `.env` or the environment.

## What it accepts

`POST` JSON, at most 9 MB: `kind` (problem, idea, question), `title`, `body`
(the text the app's preview showed), `reply_to` (optional) and up to three
PNG, JPEG or WebP `screenshots` as `{name, type, data}` with base64 `data`.
It answers `{"issue_url": "..."}`.
