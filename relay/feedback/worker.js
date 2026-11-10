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
//   FEEDBACK_TO     where the email goes (a secret only to keep it out of the repo)
//   FEEDBACK_FROM   optional: "jobdork feedback <feedback@your-verified-domain>";
//                   without it Resend's test sender, which can mail only the
//                   address the Resend account was opened with
// Vars (wrangler.toml [vars]):
//   GITHUB_REPO     "jessn-dev/jobDork"
// Optional KV binding FEEDBACK_KV: a per-address limit of LIMIT_PER_HOUR, and
// LIMIT_ALL_PER_HOUR across every address.
// Optional rate-limit binding FEEDBACK_LIMITER: an atomic per-address limit
// per minute, so a burst sent all at once cannot slip past the KV counts,
// which are read and written in two steps (Claude Security F10, 2026-11-09).
//
// Anyone can POST here, not only the app, so nothing the app checks is
// taken on trust: screenshots are decoded and checked here and named here,
// and the report's text is posted so that it cannot mention, reference or
// link anything (Claude Security F8, F9, 2026-11-09).

const KINDS = { problem: "bug", idea: "enhancement", question: "question" };
const MAX_BODY = 9 * 1024 * 1024;
const MAX_TITLE = 140;
const MAX_TEXT = 60_000;
const MAX_SHOTS = 3;
const MAX_SHOT_BYTES = 2 * 1024 * 1024;
// Each type with its file extension and how its first bytes must read.
const SHOT_TYPES = {
  "image/png": { ext: "png", starts: (b) => b.startsWith("\x89PNG\r\n\x1a\n") },
  "image/jpeg": { ext: "jpg", starts: (b) => b.startsWith("\xff\xd8\xff") },
  "image/webp": { ext: "webp", starts: (b) => b.startsWith("RIFF") && b.slice(8, 12) === "WEBP" },
};
const BASE64 = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;
const LIMIT_PER_HOUR = 5;
const LIMIT_ALL_PER_HOUR = 40;
const EMAIL = /^[\w.+-]+@[\w-]+(\.[\w-]+)+$/;
const TEST_SENDER = "jobdork feedback <onboarding@resend.dev>";

const answer = (status, body) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

// An IPv6 sender usually holds a whole /64, so it is counted as one address.
export function sender(ip) {
  if (!ip.includes(":")) return ip;
  const [head, tail = ""] = ip.split("::");
  const front = head ? head.split(":") : [];
  const back = tail ? tail.split(":") : [];
  const full = [...front, ...Array(Math.max(0, 8 - front.length - back.length)).fill("0"), ...back];
  return `${full.slice(0, 4).map((part) => part.toLowerCase() || "0").join(":")}::/64`;
}

async function counted(env, key, most) {
  const seen = Number((await env.FEEDBACK_KV.get(key)) || 0);
  if (seen >= most) return true;
  await env.FEEDBACK_KV.put(key, String(seen + 1), { expirationTtl: 3_700 });
  return false;
}

async function limited(env, ip) {
  const who = sender(ip);
  if (env.FEEDBACK_LIMITER && !(await env.FEEDBACK_LIMITER.limit({ key: who })).success)
    return true;
  if (!env.FEEDBACK_KV) return false;
  const hour = Math.floor(Date.now() / 3_600_000);
  return (await counted(env, `rate:${who}:${hour}`, LIMIT_PER_HOUR)) ||
    (await counted(env, `rate:all:${hour}`, LIMIT_ALL_PER_HOUR));
}

// The screenshot's bytes as a binary string, or "" when it is not an image
// of its declared type within the size allowed.
function decoded(shot) {
  const kind = SHOT_TYPES[shot.type];
  if (!kind || typeof shot.data !== "string" || !shot.data || !BASE64.test(shot.data)) return "";
  if ((shot.data.length / 4) * 3 > MAX_SHOT_BYTES + 2) return "";
  const bytes = atob(shot.data);
  return bytes.length <= MAX_SHOT_BYTES && kind.starts(bytes) ? bytes : "";
}

function check(report) {
  if (!report || typeof report !== "object" || Array.isArray(report)) return "not a report";
  if (typeof report.kind !== "string" || !Object.hasOwn(KINDS, report.kind)) return "unknown kind";
  if (typeof report.title !== "string" || !report.title.trim() || report.title.length > MAX_TITLE)
    return "bad title";
  if (typeof report.body !== "string" || report.body.length > MAX_TEXT) return "bad body";
  if (report.reply_to && (typeof report.reply_to !== "string" || !EMAIL.test(report.reply_to)))
    return "bad reply address";
  const shots = report.screenshots || [];
  if (!Array.isArray(shots) || shots.length > MAX_SHOTS) return "too many screenshots";
  for (const s of shots)
    if (!s || typeof s !== "object" || !decoded(s)) return "bad screenshot";
  return "";
}

// Text that GitHub shows as it is: a zero-width joiner after each @ and #
// stops a mention and a reference to an issue (here or in another
// repository) from being made under the maintainer's name.
const ZWJ = "\u200d";
export function inert(text) {
  return text.replace(/([@#])(?=[\w-])/g, `$1${ZWJ}`).replace(/\b(GH-)(?=\d)/gi, `$1${ZWJ}`);
}

// The report's own text, fenced so none of it renders: no mentions,
// references, links, images or headings an anonymous sender could dress up
// as the maintainer's. The fence is longer than any run of backticks in the
// text, so the text cannot close it early.
export function fenced(text) {
  const longest = Math.max(2, ...(text.match(/`+/g) || []).map((run) => run.length));
  const fence = "`".repeat(longest + 1);
  return `${fence}text\n${text}\n${fence}`;
}

async function openIssue(env, report) {
  const shots = (report.screenshots || []).length;
  const body = fenced(report.body) + (shots
    ? `\n\n_${shots} screenshot(s) were sent to the maintainers by email, not posted here._`
    : "") + "\n\n_Sent from jobdork's Feedback page._";
  const post = (labels) => fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/issues`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "jobdork-feedback-relay",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ title: inert(report.title), body, labels }),
  });
  let resp = await post([KINDS[report.kind], "from-app"]);
  // 422: a label the repository does not have. The issue matters more than
  // its labels, so it is filed without them rather than lost.
  if (resp.status === 422) resp = await post([]);
  if (!resp.ok) throw new Error(`GitHub ${resp.status}`);
  return (await resp.json()).html_url;
}

async function sendEmail(env, report, issueUrl) {
  const resp = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.FEEDBACK_FROM || TEST_SENDER,
      to: [env.FEEDBACK_TO],
      subject: report.title,
      ...(report.reply_to ? { reply_to: report.reply_to } : {}),
      text: `${issueUrl ? `Issue: ${issueUrl}\n` : "No GitHub issue was opened.\n"}` +
        `Reply to: ${report.reply_to || "(none given)"}\n\n${report.body}`,
      // Named here from the checked type: the sender's own name is never used.
      attachments: (report.screenshots || []).map((s, i) => ({
        filename: `screenshot-${i + 1}.${SHOT_TYPES[s.type].ext}`,
        content: s.data,
        content_type: s.type,
      })),
    }),
  });
  if (!resp.ok) throw new Error(`Resend ${resp.status}`);
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return answer(405, { error: "POST a report" });
    // JSON only. A web page can make a visitor's browser POST plain text
    // here with no warning, but not JSON, which the browser asks about first.
    if (!(request.headers.get("Content-Type") || "").toLowerCase().startsWith("application/json"))
      return answer(415, { error: "send JSON" });
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
