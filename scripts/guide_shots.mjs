// Photographs the dashboard for the user guide: guide/docs/images/*.png.
//
//   node scripts/guide_shots.mjs <dashboard url with ?t=token> <out dir> [setup url]
//
// Run through scripts/guide_screenshots.py, which starts the dashboard on the
// made-up demo (scripts/guide_demo.py) and passes the address. Headless
// Chrome over the DevTools protocol; nothing to install but Chrome and Node.
// Light theme, one window size, so pictures stay alike from one run to the
// next. Each shot is a whole page, or one part of it (`clip`, a selector).

import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [,, url, out, setupUrl] = process.argv;
if (!url || !out) {
  console.error('usage: node scripts/guide_shots.mjs <url> <out dir> [setup url]');
  process.exit(2);
}

const CHROME = [
  process.env.CHROME,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
].find(p => p && existsSync(p));
if (!CHROME) { console.error('Chrome not found; set CHROME to its path'); process.exit(2); }

const WIDTH = 1280, HEIGHT = 860, PORT = 9334;
const profile = mkdtempSync(join(tmpdir(), 'jobdork-guide-'));
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`, '--hide-scrollbars', `--window-size=${WIDTH},${HEIGHT}`,
  'about:blank'], {stdio: 'ignore'});
const sleep = ms => new Promise(r => setTimeout(r, ms));

let tabs;
for (let i = 0; i < 60 && !tabs; i++) {
  try { tabs = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json(); } catch { await sleep(250); }
}
const ws = new WebSocket(tabs.find(t => t.type === 'page').webSocketDebuggerUrl);
await new Promise(r => { ws.onopen = r; });
let id = 0;
const waiting = new Map();
ws.onmessage = m => {
  const d = JSON.parse(m.data);
  const done = waiting.get(d.id);
  if (typeof done === 'function') { waiting.delete(d.id); done(d); }
};
const send = (method, params = {}) => new Promise(r => {
  const i = ++id; waiting.set(i, r); ws.send(JSON.stringify({id: i, method, params}));
});
// A value written into the page's script: JSON, with the characters that
// could end a <script> or a line escaped (a role's uid comes from the page).
const lit = v => JSON.stringify(v).replace(/[<>/\u2028\u2029]/g,
  c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
const run = async js => {
  const d = await send('Runtime.evaluate', {expression: `(async () => { ${js} })()`,
                                            awaitPromise: true, returnByValue: true});
  if (d.result && d.result.exceptionDetails) throw new Error(`${js}\n${d.result.exceptionDetails.text}`);
  return d.result && d.result.result ? d.result.result.value : undefined;
};

await send('Page.enable');
await send('Runtime.enable');
await send('Emulation.setEmulatedMedia', {features: [{name: 'prefers-color-scheme', value: 'light'}]});
await send('Emulation.setDeviceMetricsOverride', {width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false});

async function open(address) {
  await send('Page.navigate', {url: address});
  await sleep(2500);
}

// Go to a page of the dashboard by its menu button.
const view = name => `document.querySelector('nav [data-view=${name}]').click();`;

async function shoot(name, {clip, full, pad = 8, height, tall} = {}) {
  await sleep(700);
  let params = {format: 'png'};
  if (tall) {
    // A window this tall for the picture, not one taken beyond the window:
    // that renders at the part's own width, narrow enough to fold the page
    // into its one-column layout.
    await send('Emulation.setDeviceMetricsOverride', {width: WIDTH, height: tall, deviceScaleFactor: 1, mobile: false});
    await sleep(600);
    const r = await run(`window.scrollTo(0, 0); const r = document.querySelector(${lit(clip)}).getBoundingClientRect();
      return {x: r.x, y: r.y, w: r.width, h: r.height};`);
    const shot = await send('Page.captureScreenshot', {format: 'png',
      clip: {x: Math.max(0, r.x - pad), y: Math.max(0, r.y - pad), width: r.w + 2 * pad, height: r.h + 2 * pad, scale: 1}});
    await send('Emulation.setDeviceMetricsOverride', {width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false});
    writeFileSync(join(out, `${name}.png`), Buffer.from(shot.result.data, 'base64'));
    console.log(`  ${name}.png`);
    return;
  }
  if (clip) {
    const box = await run(`const el = document.querySelector(${lit(clip)});
      if (!el) return null; el.scrollIntoView({block: 'start'});
      const r = el.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height};`);
    if (!box) throw new Error(`${name}: nothing matches ${clip}`);
    await sleep(300);
    const again = await run(`const r = document.querySelector(${lit(clip)}).getBoundingClientRect();
      return {x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height};`);
    params.captureBeyondViewport = true;
    params.clip = {x: Math.max(0, again.x - pad), y: Math.max(0, again.y - pad),
                   width: again.w + 2 * pad, height: (height || again.h) + 2 * pad, scale: 1};
  } else {
    await run(`window.scrollTo(0, 0); document.querySelector('main') && document.querySelector('main').scrollTo(0, 0);`);
    await sleep(300);
    if (full) params.captureBeyondViewport = true;
  }
  const shot = await send('Page.captureScreenshot', params);
  writeFileSync(join(out, `${name}.png`), Buffer.from(shot.result.data, 'base64'));
  console.log(`  ${name}.png`);
}

// Hover over a badge so its explanation opens, as a mouse would, and
// photograph the badge with it.
async function tip(name, selector) {
  await run(`document.querySelector(${lit(selector)}).closest('.role').scrollIntoView({block: 'start'});
    scrollBy(0, -20);`);
  await sleep(300);
  const at = await run(`const r = document.querySelector(${lit(selector)}).getBoundingClientRect();
    return {x: r.x + r.width / 2, y: r.y + r.height / 2};`);
  await send('Input.dispatchMouseEvent', {type: 'mouseMoved', x: at.x, y: at.y});
  await sleep(400);
  const box = await run(`const b = document.querySelector(${lit(selector)});
    const t = b.querySelector('.tip'); const a = b.getBoundingClientRect(), c = t.getBoundingClientRect();
    const x = Math.min(a.x, c.x), y = Math.min(a.y, c.y);
    return {x: x + scrollX, y: y + scrollY, w: Math.max(a.right, c.right) - x, h: Math.max(a.bottom, c.bottom) - y};`);
  const shot = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true,
    clip: {x: box.x - 8, y: box.y - 8, width: box.w + 16, height: box.h + 16, scale: 1}});
  writeFileSync(join(out, `${name}.png`), Buffer.from(shot.result.data, 'base64'));
  console.log(`  ${name}.png`);
  await send('Input.dispatchMouseEvent', {type: 'mouseMoved', x: 1, y: 1});
}

try {
  if (setupUrl) {
    await open(setupUrl);
    await shoot('setup');
  }

  await open(url);
  await shoot('dashboard');
  await shoot('dashboard-usage', {clip: '#m-usage'});
  await shoot('dashboard-buttons', {clip: '#view-scan > .bar:has(#run)'});

  await run(view('roles'));
  await sleep(1500);
  await shoot('job-posts');
  await shoot('job-posts-filters', {clip: '#view-roles'});
  await shoot('job-card', {clip: '#list .role'});
  await shoot('job-posts-google', {clip: '#gjobs'});
  await tip('badge-match', '#list .role .badge.match');
  await tip('badge-fit', '#list .role .badge.fit');
  await tip('badge-ai', '#list .role .badge.ai');

  // The job post's window: the advert, then the AI tools tab.
  const uid = await run(`const r = await api('/api/roles?scope=open'); const d = await r.json();
    const roles = d.roles || d; const withAi = roles.find(x => x.ai); return (withAi || roles[0]).uid;`);
  await run(`await openRole(${lit(uid)});`);
  await sleep(1200);
  await shoot('job-window');
  await shoot('job-window-statuses', {clip: '#dlg-head .statusbar'});
  // Opened again, not only redrawn: a picture taken beyond the window
  // resizes it for a moment, and a pane narrowed away gives its post back.
  // A tab's picture is the post beside the list, at its full length.
  const whole = `const p = document.getElementById('roles-pane'); p.style.maxHeight = 'none'; p.style.position = 'static';`;
  await run(`await openRole(${lit(uid)}, 'tools'); ${whole}`);
  await sleep(1500);
  await shoot('job-window-ai-tools', {clip: '#roles-pane', tall: 2400});
  await run(`await openRole(${lit(uid)}, 'ats'); ${whole}`);
  await sleep(1500);
  await shoot('job-window-ats', {clip: '#roles-pane', tall: 2400});
  await run(`document.getElementById('roles-pane').removeAttribute('style');`);
  await run(`closeDetail();`);

  await run(`document.getElementById('scope').value = 'dropped'; await loadRoles();`);
  await sleep(1200);
  await shoot('job-posts-dropped');
  await run(`document.getElementById('scope').value = 'open'; await loadRoles();`);

  // My applications, with the interviewing one chosen: its Application tab.
  await run(view('apps'));
  await sleep(1500);
  await run(`[...document.querySelectorAll('#apps tr[data-uid]')].find(t => t.textContent.includes('Remote Care')).click()`);
  await sleep(1500);
  await shoot('applications');
  await shoot('application-tab', {clip: '#apps-pane', tall: 2000});
  await run(`closeDetail();`);

  await run(view('settings'));
  await sleep(1500);
  await shoot('search');
  await shoot('search-dealbreakers', {clip: '#view-settings .sgroup.wide'});

  await run(view('resume'));
  await sleep(1500);
  await shoot('resume');
  // A tailored resume chosen: its PDF in the preview, then its checks.
  await run(`document.querySelector('#rcards [data-card]:not([data-card="master"]):not([data-card="add"])').click()`);
  await sleep(2500);
  await shoot('resume-tailored');
  await run(`document.querySelector('[data-rtab="checks"]').click()`);
  await sleep(500);
  await shoot('resume-checks', {clip: '#rpreview'});
  // The job post's other documents, as tabs beside its tailored resume.
  await run(`document.querySelector('[data-rtab="interview_prep"]').click()`);
  await sleep(1000);
  await shoot('resume-interview-prep', {clip: '#rpreview'});
  await run(`document.querySelector('[data-rtab="doc"]').click()`);

  await run(view('sources'));
  await sleep(2000);
  await shoot('sources');

  await run(view('ai'));
  await sleep(1500);
  await shoot('ai');
  await shoot('ai-checkers', {clip: '#ai-check'});
  // Coding agent chosen for Reader 1, Ollama after it, not saved: the
  // commands to connect one.
  // The commands as the installed Mac app gives them: this computer's own
  // would put its folders in the picture.
  const app = '/Applications/jobdork.app/Contents/MacOS/jobdork';
  await run(`ai.agent_setup = {claude_code: 'claude mcp add jobdork -- ${app} --mcp',
      codex: 'codex mcp add jobdork -- ${app} --mcp',
      gemini: 'gemini mcp add -s user jobdork ${app} -- --mcp',
      gemini_json: JSON.stringify({mcpServers: {jobdork: {command: '${app}', args: ['--mcp']}}}, null, 2),
      claude_desktop: JSON.stringify({mcpServers: {jobdork: {command: '${app}', args: ['--mcp']}}}, null, 2),
      cursor: JSON.stringify({mcpServers: {jobdork: {command: '${app}', args: ['--mcp']}}}, null, 2),
      vscode: JSON.stringify({servers: {jobdork: {type: 'stdio', command: '${app}', args: ['--mcp']}}}, null, 2),
      cli: '${app} --agent'};
    ai.readers = [{provider: 'agent', model: '', ollama_url: ''},
                  {provider: 'ollama', model: 'gemma4:26b', ollama_url: ''}]; drawReaders(false);`);
  await sleep(500);
  const agentH = await run(`return document.getElementById('ai-agent').getBoundingClientRect().bottom
    - document.getElementById('ai-readers').getBoundingClientRect().top;`);
  await shoot('ai-agent', {clip: '#ai-readers', height: agentH});
  await run(`drawAI();`);
  await sleep(1000);

  await run(view('prefs'));
  await sleep(1500);
  await shoot('settings');

  await run(view('tools'));
  await sleep(800);
  await run(`document.getElementById('fbk-title').value = 'Scan stops at Workday boards';
    document.getElementById('fbk-details').value = 'I pressed Run a scan. It stopped after the Workday boards with no message. I expected it to carry on to the other sources.';`);
  await shoot('feedback');
  await run(`document.getElementById('fbk-preview').click();`);
  await sleep(1500);
  await shoot('feedback-preview', {clip: '#fbk-out'});
} finally {
  ws.close();
  chrome.kill();
  await sleep(500);
  rmSync(profile, {recursive: true, force: true});
}
process.exit(0);
