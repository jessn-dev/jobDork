## Security — 2026-11-09 — The feedback relay checks what it is sent for itself

The relay that turns a problem report into a GitHub issue and an email is
a public address, and anyone can post to it, not only the app. It trusted
what the app checks (Claude Security, 2026-11-09):

- **Attachments.** It checked only the declared type, so anyone could mail
  the maintainers any file under any name (`crash-log.html`, an `.exe`)
  from the trusted feedback sender. Now each screenshot must decode from
  base64 to at most 2 MB and start the way a PNG, JPEG or WebP does, and
  the email names it `screenshot-1.png` and so on from that type; the name
  sent is never used, and the type is given to Resend.
- **The public issue.** The title and text were posted as they came, under
  the maintainer's token, so a sender could @mention people, reference
  other repositories' issues and post phishing links as the maintainer.
  Now the text sits in a code fence longer than any run of backticks in
  it, so nothing renders, and the title gets a zero-width joiner after
  each `@` and `#`.
- **The rate limit.** Five reports an hour per address were counted in KV,
  read and written in two steps, so requests sent all at once all passed.
  Now a rate-limit binding (`FEEDBACK_LIMITER`, two a minute per address)
  counts atomically first; an IPv6 sender counts by its /64; and the KV
  counts add forty an hour across all addresses.
- **Anything but JSON** is refused (415), so a web page cannot make its
  visitors' browsers post reports here; a `kind` like `toString` and a
  screenshot that is not an object are refused too.

The app sends exactly what it did; nothing changes for a real report but
how its issue shows (the text in a fence) and the attachments' names.
`node relay/feedback/test.mjs` covers each of these with stand-ins for
GitHub, Resend, KV and the limiter. The relay takes effect once deployed
(`npx wrangler@4.150.0 deploy` from relay/feedback; a dry run reads the new
binding).
