# Docker, on your computer

The dashboard from the published image, with nothing installed but Docker.
For an always-on NAS or home server reached from other devices, follow
[nas.md](nas.md) instead; for the other ways in, [README.md](README.md).

## Start it

```bash
mkdir -p jobdork/data && cd jobdork
docker run -d --name jobdork --restart unless-stopped \
  -p 127.0.0.1:8765:8765 \
  -v "$PWD/data:/app/data" \
  jessengolab/jobdork:0.15.4
docker logs jobdork          # the address to open, with its token
```

That is the newest release; [Docker Hub](https://hub.docker.com/r/jessengolab/jobdork/tags)
lists them all. Use 0.14.4 or newer (older images need a `config.yaml`
mapped in by hand). `latest` also means the newest release, but a version
tag makes updating your choice.

Open the address the log prints, `http://127.0.0.1:8765/?t=…`. The token is
new every time the container starts, so after a restart read it from the
log again. `-p 127.0.0.1:8765:8765` publishes the dashboard to your own
machine only; leave the `127.0.0.1:` in.

The first start opens setup, and your answers are saved to
`data/config.yaml`. **Without the `data` folder mapped, everything is
deleted with the container**, and the dashboard says so in red. The
container runs as user 1000, so the folder must be writable by 1000 (on
Linux: `sudo chown -R 1000:1000 data`).

**Or with compose:** [`compose.yaml`](../../compose.yaml) in an empty folder,
with its `ports` line changed to `"127.0.0.1:8765:8765"` and
`JOBDORK_ALLOW_HOSTS` removed, then `docker compose up -d`.

**Or build the image yourself** from a clone: `docker build -t jobdork .`
and use `jobdork` in place of `jessengolab/jobdork:0.15.4`.

## What goes in the data folder

| | |
|---|---|
| `config.yaml` | Your settings, written by setup and the dashboard |
| `jobdork.db` | Job posts, statuses, AI verdicts |
| `documents/` | Your resume, cover letters, CVs |
| `logs/` | What the scans printed |

A `config.yaml` you already have can be mapped instead, with
`-v "$PWD/config.yaml:/app/config.yaml"`. Keys for job sources can also come
from a `.env` file: `--env-file .env` on `docker run`, or `env_file:` in
compose.

## Settings for the container

| Variable | Meaning |
|---|---|
| `JOBDORK_ALLOW_HOSTS` | Addresses besides `127.0.0.1` the dashboard may be opened by, comma separated. Only needed to open it from another device ([nas.md](nas.md)) |
| `JOBDORK_TEMP_DOCS` | `/tmp/jobdork` keeps the resume and documents in a folder emptied at every start and stop, for a shared machine |
| `JOBDORK_UPDATE_CHECK` | `off` stops the daily check for a newer release |

Every variable: [../CONFIG.md](../CONFIG.md#environment).

## An AI model

On the AI page, Ollama running on the same computer is
`http://host.docker.internal:11434` with Docker Desktop (macOS, Windows); on
Linux, add `--add-host=host.docker.internal:host-gateway` to `docker run`
and make Ollama listen on more than `127.0.0.1`. Inside the container,
`localhost` is the container itself. Anthropic, Gemini, OpenAI and Groq need only a
key, typed on the AI page and held in memory until the container stops.

## Scans that run by themselves

**Settings → Schedule a run** needs a computer's own scheduler, which a
container does not have. Use the host's instead, for example in crontab:

```cron
0 8 * * * docker exec jobdork jobdork scan --scheduled
```

It writes to `data/logs/scheduled-scan.log` and shows under All runs. New
posts ring the dashboard's bell rather than a system notification.

## Updating

```bash
docker pull jessengolab/jobdork:0.15.4     # the newest release
docker rm -f jobdork
# then the same docker run as above, with the new version
```

Everything you keep is in `data/`, so a new container finds it. Every
published image is signed; [SECURITY.md](../../SECURITY.md#verifying-an-image-before-you-run-it)
shows how to check one and pin it by its digest.
