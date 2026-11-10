// The relay against stand-ins for GitHub and Resend: no account, no network.
//
//   node relay/feedback/test.mjs
//
// Checks what it refuses, what it sends where, that the reporter's address
// and the screenshots stay off the public issue, and that either service
// failing still delivers through the other.

import assert from "node:assert/strict";
import worker, { sender } from "./worker.js";

const env = {
  GITHUB_REPO: "jessn-dev/jobDork", GITHUB_TOKEN: "gh-test", RESEND_API_KEY: "re-test",
  FEEDBACK_TO: "maintainer@example.com",
};
const report = {
  kind: "problem", title: "Scan stops at Workday", body: "It stopped.\n\nVersion 0.14.3",
  reply_to: "someone@example.com",
  screenshots: [{ name: "shot.png", type: "image/png", data: "iVBORw0KGgo=" }],
};

let calls;
function stub({ github = [201], resend = 200 } = {}) {
  calls = [];
  const githubAnswers = [...github];
  globalThis.fetch = async (url, init) => {
    const body = JSON.parse(init.body);
    calls.push({ url, body, headers: init.headers });
    if (url.startsWith("https://api.github.com/")) {
      const status = githubAnswers.shift() ?? 201;
      return new Response(JSON.stringify({ html_url: "https://github.com/x/y/issues/7" }), { status });
    }
    return new Response("{}", { status: resend });
  };
}

const post = (payload, headers = {}) => worker.fetch(new Request("https://relay.test/", {
  method: "POST", headers: { "Content-Type": "application/json", ...headers },
  body: typeof payload === "string" ? payload : JSON.stringify(payload),
}), env);

const tests = {
  async "a report becomes an issue and an email, private parts by email only"() {
    stub();
    const resp = await post(report);
    assert.equal(resp.status, 200);
    assert.deepEqual(await resp.json(), { issue_url: "https://github.com/x/y/issues/7" });
    const [issue, email] = calls;
    assert.equal(issue.url, "https://api.github.com/repos/jessn-dev/jobDork/issues");
    assert.deepEqual(issue.body.labels, ["bug", "from-app"]);
    assert.ok(!JSON.stringify(issue.body).includes("someone@example.com"));
    assert.ok(!JSON.stringify(issue.body).includes("iVBORw0KGgo="));
    assert.match(issue.body.body, /1 screenshot\(s\) were sent to the maintainers by email/);
    assert.equal(email.url, "https://api.resend.com/emails");
    assert.deepEqual(email.body.to, ["maintainer@example.com"]);
    assert.equal(email.body.reply_to, "someone@example.com");
    assert.equal(email.body.from, "jobdork feedback <onboarding@resend.dev>");
    assert.equal(email.body.attachments[0].filename, "screenshot-1.png");
    assert.equal(email.body.attachments[0].content_type, "image/png");
    assert.equal(email.headers.Authorization, "Bearer re-test");
  },
  async "a missing label does not lose the issue"() {
    stub({ github: [422, 201] });
    const resp = await post(report);
    assert.equal(resp.status, 200);
    assert.deepEqual(calls[1].body.labels, []);
  },
  async "GitHub down: the email still goes, and says no issue was opened"() {
    stub({ github: [500] });
    const resp = await post(report);
    assert.equal(resp.status, 200);
    assert.deepEqual(await resp.json(), { issue_url: "" });
    assert.match(calls.at(-1).body.text, /No GitHub issue was opened/);
  },
  async "both down: the app is told to try later"() {
    stub({ github: [500], resend: 500 });
    assert.equal((await post(report)).status, 502);
  },
  async "an attachment is named here and must be the image it says it is"() {
    stub();
    const html = btoa("<html><script>steal()</script></html>");
    for (const shot of [
      { name: "crash-log.html", type: "image/png", data: html },     // not a PNG
      { name: "x.png", type: "image/png", data: "iVBORw0KGgo=@@" },   // not base64
      { name: "x.png", type: "image/png", data: "" },
      null,
      "iVBORw0KGgo=",
    ]) {
      const resp = await post({ ...report, screenshots: [shot] });
      assert.equal(resp.status, 400, JSON.stringify(shot));
      assert.equal((await resp.json()).error, "bad screenshot");
    }
    const big = btoa("\x89PNG\r\n\x1a\n" + "a".repeat(2 * 1024 * 1024));
    assert.equal((await post({ ...report, screenshots: [{ type: "image/png", data: big }] })).status, 400);
    assert.equal(calls.length, 0);
    stub();
    await post({ ...report, screenshots: [{ name: "\u202egnp.exe", type: "image/png", data: "iVBORw0KGgo=" }] });
    assert.equal(calls.at(-1).body.attachments[0].filename, "screenshot-1.png");
  },
  async "the issue cannot mention, reference or link anything"() {
    stub();
    await post({ ...report, title: "Urgent @victim see #12",
      body: "@victim1 owner/repo#3 [patch](https://evil.example/x.exe) ```` close?" });
    const issue = calls[0].body;
    assert.ok(!/@victim\b/.test(issue.title.replace(/\u200d/g, "!")), issue.title);
    assert.ok(issue.title.includes("@\u200dvictim") && issue.title.includes("#\u200d12"));
    const fence = issue.body.match(/^(`{3,})text\n/);
    assert.ok(fence && fence[1].length > 4, "fence longer than any backtick run");
    const inside = issue.body.slice(fence[0].length, issue.body.indexOf(`\n${fence[1]}`));
    assert.ok(inside.includes("[patch](https://evil.example/x.exe)"), "kept as plain text");
    assert.match(issue.body, /Sent from jobdork's Feedback page/);
  },
  async "a burst is stopped by the limiter, and IPv6 counts by its /64"() {
    stub();
    const keys = [];
    const limited = { ...env, FEEDBACK_LIMITER: { limit: async ({ key }) => {
      keys.push(key); return { success: keys.length <= 1 };
    } } };
    const send = () => worker.fetch(new Request("https://relay.test/", {
      method: "POST", headers: { "Content-Type": "application/json",
        "CF-Connecting-IP": "2001:db8:1:2:aaaa::1" }, body: JSON.stringify(report) }), limited);
    assert.equal((await send()).status, 200);
    assert.equal((await send()).status, 429);
    assert.deepEqual(keys, ["2001:db8:1:2::/64", "2001:db8:1:2::/64"]);
    assert.equal(sender("2001:DB8::1"), "2001:db8:0:0::/64");
    assert.equal(sender("203.0.113.9"), "203.0.113.9");
  },
  async "the hourly counts hold per address and across all of them"() {
    stub();
    const store = new Map();
    const kv = { get: async (k) => store.get(k) ?? null, put: async (k, v) => store.set(k, v) };
    const counted = { ...env, FEEDBACK_KV: kv };
    const from = (ip) => worker.fetch(new Request("https://relay.test/", {
      method: "POST", headers: { "Content-Type": "application/json", "CF-Connecting-IP": ip },
      body: JSON.stringify(report) }), counted);
    for (let i = 0; i < 5; i++) assert.equal((await from("198.51.100.1")).status, 200);
    assert.equal((await from("198.51.100.1")).status, 429, "five an hour per address");
    for (let i = 0; i < 40 - 5; i++) await from(`198.51.100.${10 + i}`);
    assert.equal((await from("198.51.100.250")).status, 429, "forty an hour in all");
  },
  async "only JSON is taken, so a web page cannot post through a visitor"() {
    stub();
    const resp = await worker.fetch(new Request("https://relay.test/", {
      method: "POST", headers: { "Content-Type": "text/plain" }, body: JSON.stringify(report) }), env);
    assert.equal(resp.status, 415);
    assert.equal(calls.length, 0);
  },
  async "what is not a report is refused before anything is sent"() {
    stub();
    for (const [payload, why] of [
      ["not json", "not JSON"],
      [{ ...report, kind: "rant" }, "unknown kind"],
      [{ ...report, kind: "toString" }, "unknown kind"],
      [[report], "not a report"],
      [{ ...report, title: "" }, "bad title"],
      [{ ...report, reply_to: "not an address" }, "bad reply address"],
      [{ ...report, reply_to: ["a@b.co"] }, "bad reply address"],
      [{ ...report, screenshots: [{ name: "x.svg", type: "image/svg+xml", data: "" }] }, "bad screenshot"],
    ]) {
      const resp = await post(payload);
      assert.equal(resp.status, 400);
      assert.equal((await resp.json()).error, why);
    }
    assert.equal(calls.length, 0);
    const get = await worker.fetch(new Request("https://relay.test/"), env);
    assert.equal(get.status, 405);
  },
};

let failures = 0;
for (const [name, fn] of Object.entries(tests)) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (e) {
    failures += 1;
    console.log(`FAIL ${name}: ${e.message}`);
  }
}
console.log(`${Object.keys(tests).length - failures}/${Object.keys(tests).length} passed`);
process.exit(failures ? 1 : 0);
