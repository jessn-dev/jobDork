// The relay against stand-ins for GitHub and Resend: no account, no network.
//
//   node relay/feedback/test.mjs
//
// Checks what it refuses, what it sends where, that the reporter's address
// and the screenshots stay off the public issue, and that either service
// failing still delivers through the other.

import assert from "node:assert/strict";
import worker from "./worker.js";

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
    assert.equal(email.body.attachments[0].filename, "shot.png");
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
  async "what is not a report is refused before anything is sent"() {
    stub();
    for (const [payload, why] of [
      ["not json", "not JSON"],
      [{ ...report, kind: "rant" }, "unknown kind"],
      [{ ...report, title: "" }, "bad title"],
      [{ ...report, reply_to: "not an address" }, "bad reply address"],
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
