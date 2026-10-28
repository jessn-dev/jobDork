# Security

## Reporting a problem

Please report a vulnerability privately, through GitHub's
**Security → Report a vulnerability** on this repository, not in a public
issue.

---

## What is checked before an image is published

Every push and pull request runs the checks below
(`.github/workflows/docker.yml`). A **release** is a version tag such as
`v0.14.0`: only a tag publishes an image, only when every check passes, and
only after the owner approves it in the `release` environment. A push to
`main` is built and checked, but not published.

| Check | What it catches |
|---|---|
| Tests and lint, Python 3.10 and 3.14 | Broken behaviour, including the dashboard's Host, token and CSRF guards |
| `pip-audit` on `requirements.lock` | A dependency with a published vulnerability |
| `pip-audit` on `requirements-desktop.lock`, every platform's packages | The same, for what the desktop installers are built from (pyobjc on macOS, pythonnet on Windows included) |
| `bandit` over the code | Injection, unsafe calls and similar in jobdork's own code. A finding judged safe is marked in the code with its reason |
| `gitleaks` over **the whole git history** | A key, token or password ever committed, even if deleted since |
| `zizmor` over the workflows | Template injection, credentials left in a checkout, over-broad token permissions and risky triggers in `.github/workflows`; and, online, that every pinned commit is really its action's and not a known-vulnerable version. Medium and above fail |
| `hadolint` | Dockerfile mistakes |
| Trivy on the built image | High and critical vulnerabilities in every package in the image, fixed or not, plus secrets and misconfiguration |
| `scripts/check_image.sh` | That the image runs as user 1000, has no pip, contains no `.env`, config or database, cannot rewrite its own code, and that the dashboard starts and refuses a missing token and an address not named |
| Dependency Review, on every pull request (`dependency-review.yml`) | A dependency the pull request adds or upgrades with a known vulnerability of moderate severity or above; it fails, and comments which. It reads `pyproject.toml`; the locks are pip-audit's |
| OpenSSF Scorecard, weekly and on every push to `main` (`scorecard.yml`) | How the supply chain is guarded: pinned actions, branch protection, signed releases, reviews, token permissions. Findings go to Security, Code scanning; the score is published to scorecard.dev |
| Desktop app build (`desktop.yml`), macOS (Apple Silicon and Intel) and Windows, after the tests and scans pass | That every installer still build from the hash-pinned `requirements-desktop.lock`, and that the built app carries every module and data file it needs and can verify a build attestation (its `--self-test`) |

**How the image is built to be hard to tamper with:**

- **Every dependency is pinned with its checksum** (`requirements.lock`) and
  installed with `--require-hashes`: a tampered release on PyPI does not match
  and is refused.
- **The base image is pinned by digest**, which names exact contents; a tag
  can be moved to point at something else.
- **Dependabot waits a week** before proposing a new version of an action,
  the base image or a Python package (`.github/dependabot.yml`). A
  malicious release is usually found and pulled within days, and the
  checksums above only stop a tampered copy of a version already pinned.
  Fixes for a published advisory are not held back.
- **Every GitHub Action is pinned to a commit**, not a tag. The scanners run
  from their official images, also pinned by digest.
- **The published image is signed** with [Sigstore](https://www.sigstore.dev/)
  keyless signing: the signature ties it to this repository's workflow and
  commit, is checked against GitHub's identity, and is recorded in a public
  log. There is no signing key that could be stolen.
- **Each image carries a provenance record** (which source, commit and
  workflow built it) **and a software bill of materials** (every package in
  it), attached in the registry.
- The workflow's token can only read the repository; publishing, signing and
  the Docker Hub token are confined to the one approved job.
- **The weekly boards re-check** (`.github/workflows/boards.yml`) is the one
  workflow that writes: it pushes a branch and opens a pull request, with
  `BOARDS_PR_TOKEN`, a fine-grained token for this repository only. Its pull
  request goes through the same required checks and the owner's review as
  any other; nothing it does reaches `main` or an image by itself.

---

## How a release is made, and signed off

1. Set the new version with `python scripts/set_version.py <new version>`,
   which writes it into `pyproject.toml` and into every page that names the
   release to copy (the image tag, the installers' names, the tag command
   below), and merge it into `main` through a pull request; the checks must
   pass, and they fail if any page still names the old release. The tag in
   step 2 must match it: a tag that does not is stopped before the approval
   step.
2. **After the merge**, bring `main` up to date, then tag it and push the tag:
   `git checkout main && git pull`, then check that `main` now says the new
   version, `grep -m1 '^version' pyproject.toml`, and only then
   `git tag v0.15.3 && git push origin v0.15.3`. Only an admin can create a
   `v*` tag, and once pushed it can never be moved or deleted, so a tag made
   before the pull lands on the old commit for good (as `v0.14.0`,
   `v0.14.1` and `v0.14.2` did). Pushing a branch or opening a pull request does not put
   anything on `main`; merging it does.
3. The workflow runs every check again on the tag, then stops at **Review
   deployments**: open the run under Actions and approve it. Nothing is
   published, and the Docker Hub token is not handed out, until you do.
4. It publishes the image for Intel and ARM, signs it, verifies the
   signature, and creates the **GitHub Release** page for the tag: the exact
   image digest, the command to verify it, the desktop installers (the
   macOS `.dmg` and the Windows setup `.exe`, with `SHA256SUMS.txt` and how
   to get past the unsigned warnings), and what changed: the
   `docs/CHANGELOG.md` entries written since the last release, in full
   (`scripts/release_notes.py`), not a list of pull request titles. The installers are not signed, but each carries a build
   provenance attestation: `gh attestation verify <file> --repo
   jessn-dev/jobDork` shows this repository's workflow built it from the
   tagged commit.

---

## How the app checks an update before opening it

**Settings → Updates → Update** in the desktop app downloads the installer
for this computer and opens it (the Windows installer replaces the app). It
opens nothing unless all of these hold (`jobdork/core/updates.py`):

1. **The file was uploaded by the release workflow.** Release files uploaded
   by anyone else (`uploader` other than `github-actions[bot]`) are not
   offered at all. A stolen login or token can add a file to a release, but
   it shows as uploaded by that person.
2. **It matches `SHA256SUMS.txt`** from the same release. This only proves
   the download arrived whole.
3. **Its build attestation verifies.** GitHub's attestation for the file's
   SHA-256 is checked with Sigstore: the signing certificate must be issued
   by GitHub Actions to this repository's `desktop.yml`, run for exactly
   that version's tag (`refs/tags/v<version>`), with a valid transparency
   log entry, and the signed statement must name this file and digest. A
   build from another workflow, branch, fork or tag fails, and so does any
   file whose bytes differ.

A file that fails is deleted. GitHub unreachable while checking is a
failure too, never a pass. Sigstore's trust root is refreshed online, or
taken from the copy inside the app; the app's self-test verifies an
earlier release's real attestation offline, so a build that cannot check
is caught before release. Releases are immutable (see below), so a published file cannot be
swapped later.

---

## Verifying an image before you run it

Check that it was built by this repository's workflow and not altered since:

```bash
cosign verify jessengolab/jobdork:0.15.3 \
  --certificate-identity-regexp '^https://github.com/jessn-dev/jobDork/\.github/workflows/docker\.yml@' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

([Install cosign](https://docs.sigstore.dev/cosign/system_config/installation/).)
Then run it **by digest**, the `sha256:…` the verification printed, rather
than by tag:

```bash
docker pull jessengolab/jobdork@sha256:<digest>
```

A tag can be re-pointed later; a digest always means the exact image you
verified.

---

## Settings only the owner can turn on

These cannot be set from the repository's files. Without them, someone who
got into the GitHub or Docker Hub account could get around everything above.

**Set on 2026-09-29:**
- [x] Environment `release`: the owner is a required reviewer, and it can
      only be deployed from `v*` tags.
- [x] Ruleset for `main`: no deletion or force push; changes by pull request;
      the checks `test (3.10)`, `test (3.14)`, `security` and `image` must pass.
- [x] Ruleset for `v*` tags: never updated or deleted, by anyone.
- [x] Ruleset for `v*` tags: only a repository admin may create one.
- [x] Workflow permissions read-only; Actions cannot approve pull requests.
- [x] Secret scanning and push protection (a key is stopped before it is pushed).
- [x] Dependabot alerts and security updates.
- [x] Private vulnerability reporting.

**Set on 2026-10-23:**
- [x] Code scanning: CodeQL default setup (Python, JavaScript and the
      workflows), on every pull request and push to `main`, and weekly.
- [x] Passkeys on the owner's GitHub and Docker Hub accounts.

**Set, confirmed 2026-10-02:**
- [x] A Docker Hub personal access token for this workflow only, with the
      Read & Write scope (not Delete), saved as the secret `DOCKERHUB_TOKEN`
      in the `release` environment, not in the repository. Rotate it yearly,
      and revoke it at once if it may have leaked.
- [x] The variable `DOCKERHUB_USERNAME`, the Docker Hub account, in the
      `release` environment (not at repository level).

**Set on 2026-10-25:**
- [x] Ruleset for `main`: CodeQL results required; a pull request that adds
      a high or critical security alert, or an error, cannot be merged.
- [x] **Immutable releases**: a published release's files can never be
      changed or replaced.
- [x] Actions: only GitHub's own and the six named in the workflows
      (`docker/*` five, `sigstore/cosign-installer`), each pinned to a full
      commit SHA, which is now required.
- [x] Workflows from every outside contributor wait for approval.
- [x] Wiki and Projects off; merged branches deleted.
- [x] `BOARDS_PR_TOKEN`, for the weekly boards re-check: a fine-grained
      personal access token for this repository only, with Contents and Pull
      requests set to Read and write and nothing else. Rotate it yearly.

**To set (2026-10-28), by the owner:**
- [ ] Actions, allowed actions: add `ossf/scorecard-action@*`, so the
      Scorecard workflow may run (every other action it uses is GitHub's).
- [ ] Code scanning, CodeQL: query suite **Extended**, for more security
      queries on the scan that already runs.

**Not available on this account:** secret scanning's generic patterns and
validity checks need GitHub's paid Secret Protection; provider patterns and
push protection are on.

---

## What a job post cannot do

Every job post is written by someone unknown: its title, its text and its
links. The app treats them as hostile.

- **In the dashboard** every piece of it is escaped before it is shown, and
  a link opens only if it is a web address (`http:` or `https:`), so a
  `javascript:` link does nothing. The page loads nothing from anywhere
  else (its Content-Security-Policy). `tests/test_page_safety.py` fails on
  the two patterns that once let a link run script.
- **In the AI model's prompt** it sits between markers it cannot close,
  labelled as data. The model's answers are text shown to you; nothing it
  says is run.
- **For a draft by Claude Code** (`claude -p`, `jobdork/writing/generate.py`)
  the agent works in that one job's folder with file tools only: no shell,
  no web, none of your MCP servers, whatever your own Claude Code settings
  allow; and it reads none of those settings (`--setting-sources project`),
  so your own permission rules, hooks and plugins do not apply to it. A posting that persuades it can spoil that one draft, not reach
  the rest of your machine.
- **As an address to fetch** (an apply link, a careers page) it reaches
  public addresses only. One that names this machine or its network
  (`localhost`, `192.168.x.x`, `169.254.169.254`), or redirects there, is
  refused (`jobdork/fetch/http.py`), so a posting cannot use the app to
  reach your router, printer or NAS.
- **In the desktop app** the page can ask the app for three things only:
  open a web address in your browser, save a file where you choose, and
  show a PDF. A file is shown only if it really is a PDF, and always as
  `.pdf`, so nothing handed to the app can run (`jobdork/web/app.py`).
  The page's policy still refuses `eval`, in the app as in a browser.

---

## What this does not cover

- **A compromise of GitHub, Docker Hub or Sigstore themselves.** Verifying
  the signature narrows this, but does not remove it.
- **The machine you run it on.** Anyone who can run commands there as your
  user can read jobdork's database and settings.
- **The dashboard's access token.** It is printed in the container's log and
  put in the link you open; treat that link as a password. See
  [docs/run/nas.md](docs/run/nas.md) for keeping the dashboard on your own
  network.
