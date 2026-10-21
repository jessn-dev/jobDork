// jobdork feedback relay: a Cloudflare Worker.
//
// The app holds no keys. It POSTs a report here (jobdork/core/feedback.py,
// Report.payload); this Worker holds the keys, opens the GitHub issue and
// emails the maintainers, with the screenshots attached and the reporter's
// address as Reply-To. It answers {"issue_url": "..."}.
//
// Secrets (wrangler secret put NAME):
//   GITHUB_TOKEN    fine-grained token: this one repository, Issues read/write, nothing else
//   RESEND_API_KEY  Resend key with sending access only
// Vars (wrangler.toml [vars]):
//   GITHUB_REPO     "jessn-dev/jobDork"
//   FEEDBACK_TO     where the email goes
//   FEEDBACK_FROM   "jobdork feedback <feedback@your-verified-domain>"
// Optional KV binding FEEDBACK_KV: a per-address limit of LIMIT_PER_HOUR.

const KINDS = { problem: "bug", idea: "enhancement", question: "question" };
const MAX_BODY = 9 * 1024 * 1024;
const MAX_TITLE = 140;
const MAX_TEXT = 60_000;
const MAX_SHOTS = 3;
const SHOT_TYPES = ["image/png", "image/jpeg", "image/webp"];
const LIMIT_PER_HOUR = 5;
const EMAIL = /^[\w.+-]+@[\w-]+(\.[\w-]+)+$/;

const answer = (status, body) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

async function limited(env, ip) {
  if (!env.FEEDBACK_KV) return false;
  const key = `rate:${ip}:${Math.floor(Date.now() / 3_600_000)}`;
  const seen = Number((await env.FEEDBACK_KV.get(key)) || 0);
  if (seen >= LIMIT_PER_HOUR) return true;
  await env.FEEDBACK_KV.put(key, String(seen + 1), { expirationTtl: 3_700 });
  return false;
}

function check(report) {
  if (!report || typeof report !== "object") return "not a report";
  if (!(report.kind in KINDS)) return "unknown kind";
  if (typeof report.title !== "string" || !report.title.trim() || report.title.length > MAX_TITLE)
    return "bad title";
  if (typeof report.body !== "string" || report.body.length > MAX_TEXT) return "bad body";
  if (report.reply_to && !EMAIL.test(report.reply_to)) return "bad reply address";
  const shots = report.screenshots || [];
  if (!Array.isArray(shots) || shots.length > MAX_SHOTS) return "too many screenshots";
  for (const s of shots)
    if (!SHOT_TYPES.includes(s.type) || typeof s.data !== "string") return "bad screenshot";
  return "";
}

async function openIssue(env, report) {
  const shots = (report.screenshots || []).length;
  const body = report.body + (shots
    ? `\n\n_${shots} screenshot(s) were sent to the maintainers by email, not posted here._`
    : "") + "\n\n_Sent from jobdork's Feedback page._";
  const resp = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/issues`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "jobdork-feedback-relay",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ title: report.title, body, labels: [KINDS[report.kind], "from-app"] }),
  });
  if (!resp.ok) throw new Error(`GitHub ${resp.status}`);
  return (await resp.json()).html_url;
}

async function sendEmail(env, report, issueUrl) {
  const resp = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.FEEDBACK_FROM,
      to: [env.FEEDBACK_TO],
      subject: report.title,
      ...(report.reply_to ? { reply_to: report.reply_to } : {}),
      text: `${issueUrl ? `Issue: ${issueUrl}\n` : "No GitHub issue was opened.\n"}` +
        `Reply to: ${report.reply_to || "(none given)"}\n\n${report.body}`,
      attachments: (report.screenshots || []).map((s) => ({ filename: s.name, content: s.data })),
    }),
  });
  if (!resp.ok) throw new Error(`Resend ${resp.status}`);
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return answer(405, { error: "POST a report" });
    if (Number(request.headers.get("Content-Length") || 0) > MAX_BODY)
      return answer(413, { error: "too big" });
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    if (await limited(env, ip)) return answer(429, { error: "too many reports; try in an hour" });

    let report;
    try {
      const raw = await request.text();
      if (raw.length > MAX_BODY) return answer(413, { error: "too big" });
      report = JSON.parse(raw);
    } catch {
      return answer(400, { error: "not JSON" });
    }
    const problem = check(report);
    if (problem) return answer(400, { error: problem });

    // The issue is the record; the email carries what must not be public.
    // Either one failing still delivers the other.
    let issueUrl = "";
    try {
      issueUrl = await openIssue(env, report);
    } catch (e) {
      console.log("issue failed", String(e));
    }
    try {
      await sendEmail(env, report, issueUrl);
    } catch (e) {
      console.log("email failed", String(e));
      if (!issueUrl) return answer(502, { error: "could not file it; try again later" });
    }
    return answer(200, { issue_url: issueUrl });
  },
};
