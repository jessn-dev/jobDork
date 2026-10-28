# The user guide

How to use jobdork, page by page, for people who will never read the code:
published at **https://jessn-dev.github.io/jobDork/** from `guide/docs/` by
[guide.yml](../.github/workflows/guide.yml) on every push to `main` that
changes it. The developer documentation stays in [docs/](../docs/).

## Every change to what the app shows updates the guide

A pull request that adds or changes a button, a page, a setting, a status
or a score changes the guide in the same pull request:

1. **The words.** Name the new button or heading in the page of the guide
   for that part of the app (`guide/docs/<page>.md`), and say what it does
   and when to use it, in plain words. `tests/test_guide.py` fails until
   every button label and heading on the dashboard is named somewhere in the
   guide, every status has a row in `statuses.md`, and every page of the
   menu has a guide page.
2. **The pictures.** `python scripts/guide_screenshots.py` takes every
   picture again from the real dashboard, run on a made-up person's data
   (`scripts/guide_demo.py`: Jordan Rivera, a nurse in Chicago, and invented
   employers). Needs Chrome and Node. Commit the pictures that changed. A
   new picture is a new `shoot()` in `scripts/guide_shots.mjs`; the test
   fails for a picture the script does not take, so none goes stale.
3. **The other docs.** The same change in `README.md`, `docs/CONFIG.md`
   and `docs/run/` where they cover it, and an entry in
   `docs/CHANGELOG.md`.

**Never photograph your own data.** The guide is public. The demo is
invented so that no real resume, search or employer list is ever published;
add to the demo when a picture needs something it lacks.

## Preview it

```bash
python -m venv .venv-guide && .venv-guide/bin/pip install -r guide/requirements.txt
# or, exactly what CI builds it with, every package checked by hash:
#   .venv-guide/bin/pip install --require-hashes -r requirements-ci.lock
.venv-guide/bin/mkdocs serve -f guide/mkdocs.yml     # http://127.0.0.1:8000
```

The build is strict: a link to a page or a section that does not exist
fails it, on the pull request, before anything is published.

## Pages

| Page | Covers |
|---|---|
| `index.md` | The landing page, for someone who has never heard of jobdork: what it does, who it is for, how it compares, questions, download. Its hero and the tags search engines and link previews read are in `overrides/home.html`, its styles in `docs/stylesheets/home.css`. Every claim on it is one the README and docs back; change them together |
| `overview.md` | The guide's front page: what jobdork does, the six steps, the pages |
| `getting-started.md` | Installing (links to docs/run) and setup |
| `dashboard.md` | Dashboard buttons, tiles, charts, run detail |
| `job-posts.md` | The list, one post, filters, dropped posts |
| `job-window.md` | A post's window: advert, statuses, every AI tool |
| `scores.md` | Match, Fit and AI |
| `statuses.md` | Statuses, age, listing, recruiter and yellow tags |
| `search.md`, `resume.md`, `sources.md`, `ai.md`, `settings.md` | One page each |
| `feedback.md` | Writing, previewing and sending feedback |
| `glossary.md` | Words a newcomer meets |

The first publish needs the repository's **Settings → Pages → Source** set
to **GitHub Actions**, once, by the owner.
