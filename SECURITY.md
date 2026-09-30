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
| `bandit` over the code | Injection, unsafe calls and similar in jobdork's own code. A finding judged safe is marked in the code with its reason |
| `gitleaks` over **the whole git history** | A key, token or password ever committed, even if deleted since |
| `hadolint` | Dockerfile mistakes |
| Trivy on the built image | High and critical vulnerabilities in every package in the image, fixed or not, plus secrets and misconfiguration |
| `scripts/check_image.sh` | That the image runs as user 1000, has no pip, contains no `.env`, config or database, cannot rewrite its own code, and that the dashboard starts and refuses a missing token and an address not named |

**How the image is built to be hard to tamper with:**

- **Every dependency is pinned with its checksum** (`requirements.lock`) and
  installed with `--require-hashes`: a tampered release on PyPI does not match
  and is refused.
- **The base image is pinned by digest**, which names exact contents; a tag
  can be moved to point at something else.
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

---

## How a release is made, and signed off

1. Set the new version in `pyproject.toml` and merge it into `main` through a
   pull request; the checks must pass. The tag in step 2 must match it: a
   tag that does not is stopped before the approval step.
2. **After the merge**, bring `main` up to date, then tag it and push the tag:
   `git checkout main && git pull`, then check that `main` now says the new
   version, `grep -m1 '^version' pyproject.toml`, and only then
   `git tag v0.14.3 && git push origin v0.14.3`. Only an admin can create a
   `v*` tag, and once pushed it can never be moved or deleted, so a tag made
   before the pull lands on the old commit for good (as `v0.14.0`,
   `v0.14.1` and `v0.14.2` did). Pushing a branch or opening a pull request does not put
   anything on `main`; merging it does.
3. The workflow runs every check again on the tag, then stops at **Review
   deployments**: open the run under Actions and approve it. Nothing is
   published, and the Docker Hub token is not handed out, until you do.
4. It publishes the image for Intel and ARM, signs it, verifies the
   signature, and creates the **GitHub Release** page for the tag: the exact
   image digest, the command to verify it, and the changes since the last
   release.

---

## Verifying an image before you run it

Check that it was built by this repository's workflow and not altered since:

```bash
cosign verify <dockerhub-user>/jobdork:<version> \
  --certificate-identity-regexp '^https://github.com/jessn-dev/jobDork/\.github/workflows/docker\.yml@' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

([Install cosign](https://docs.sigstore.dev/cosign/system_config/installation/).)
Then run it **by digest**, the `sha256:…` the verification printed, rather
than by tag:

```bash
docker pull <dockerhub-user>/jobdork@sha256:<digest>
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

**Still to do by the owner:**
- [ ] Two-factor authentication on GitHub, preferably a passkey or security key.
- [ ] Two-factor authentication on Docker Hub.
- [ ] A Docker Hub personal access token for this workflow only, with the
      Read & Write scope (not Delete), saved as the secret `DOCKERHUB_TOKEN`
      in the `release` environment, not in the repository. Rotate it yearly,
      and revoke it at once if it may have leaked.
- [ ] The repository variable `DOCKERHUB_USERNAME`: the Docker Hub account.
- [ ] If offered under Actions → General, require actions to be pinned to a
      full commit SHA.

---

## What this does not cover

- **A compromise of GitHub, Docker Hub or Sigstore themselves.** Verifying
  the signature narrows this, but does not remove it.
- **The machine you run it on.** Anyone who can run commands there as your
  user can read jobdork's database and settings.
- **The dashboard's access token.** It is printed in the container's log and
  put in the link you open; treat that link as a password. See
  [docs/DEPLOY.md](docs/DEPLOY.md) for keeping the dashboard on your own
  network.
