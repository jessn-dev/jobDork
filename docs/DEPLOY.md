# Running jobdork on a NAS or a home server

jobdork runs on your own machine by default. This guide puts it on a NAS (or
any always-on computer), reachable from your laptop or phone wherever you are,
with the AI running on a separate computer that is good at it.

---

## The shape of it

```
   your laptop or phone, anywhere          the AI machine: a Mac or a PC
   (opens the dashboard)                   with a graphics card, running Ollama
              │                                         ▲
              │            Tailscale: a private,        │
              └──────────► encrypted network ◄──────────┘
                           between your devices
                                   │
                                   ▼
                     the NAS, always on, running jobdork
                     (scans, filters, the dashboard, your data)
```

**Why the AI is not on the NAS.** A language model reads text on the
processor, and a NAS processor is built for files, not for this. Measured on a
UGREEN DXP4800 (8 GB) with `qwen2.5:3b`, the smallest model that did the job:
one AI verdict took 8 minutes with the processor at 100% the whole time, so
judging 25 job posts took over three hours and the NAS was slow at everything
else meanwhile. The same verdict on an Apple Silicon Mac takes seconds. So
the NAS runs jobdork, which is light, and a computer with a graphics card or
Apple Silicon runs the model.

**Why Tailscale.** It puts your devices on one private network wherever they
are, with nothing opened on your router. It is what lets you open the
dashboard from abroad, and lets jobdork on the NAS reach the AI machine
wherever that is. Do not forward ports on your router instead: that would
put the dashboard and an Ollama with no password on the open internet.

**What stops when the AI machine is off.** Scans, filters, tracking and the
dashboard carry on; AI verdicts, cover letters and the AI tools wait until it
is back. Nothing is lost.

---

## 1. Docker on the NAS

jobdork ships as a Docker image, so the NAS needs Docker. Install it the way
your system does:

| System | How |
|---|---|
| UGREEN (UGOS Pro) | App Center → Docker → Install. [UGREEN's guide](https://ai.ugreen.com/blogs/knowledge/docker-docker-compose-ugreen-nas) |
| Synology (DSM) | Package Center → Container Manager. [Synology's guide](https://kb.synology.com/en-global/DSM/help/ContainerManager/docker_desc) |
| QNAP (QTS) | App Center → [Container Station](https://www.qnap.com/en/software/container-station) |
| Unraid | Built in: the Docker tab. [Unraid's guide](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/overview/) |
| TrueNAS SCALE | Apps. [TrueNAS's guide](https://www.truenas.com/docs/scale/scaletutorials/apps/) |
| A home-made server (any Linux) | [Docker's install guide](https://docs.docker.com/engine/install/) for your distribution |

---

## 2. Tailscale on every device

Make one free Tailscale account, then install Tailscale on the NAS, the AI
machine, and every laptop or phone you will open the dashboard from, signed
in to the same account. Start with the [quickstart](https://tailscale.com/kb/1017/install).

| Device | How |
|---|---|
| UGREEN | Not in the App Center at the time of writing. The [UGREEN community guide](https://guide.ugreen.community/ugos/install/tailscale/) installs it on the NAS itself over SSH (it is a community guide, not UGREEN's), including a fix for UGOS's DNS |
| Synology | [Tailscale's Synology guide](https://tailscale.com/kb/1131/synology) |
| QNAP | [Tailscale's QNAP guide](https://tailscale.com/kb/1273/qnap) |
| Unraid | [Tailscale's Unraid guide](https://tailscale.com/docs/integrations/unraid) |
| TrueNAS SCALE | [Tailscale's TrueNAS guide](https://tailscale.com/kb/1483/truenas) |
| Linux server | [Install on Linux](https://tailscale.com/kb/1031/install-linux) |
| Mac, Windows, phone | [Download](https://tailscale.com/download) |

Turn on **[MagicDNS](https://tailscale.com/kb/1081/magicdns)** (on by
default for new accounts). Every device then has a name as well as an address:
`my-nas.tail1234.ts.net` rather than `100.68.218.16`. The Machines page of the
Tailscale admin console lists both.

**Check it works for containers.** Tailscale installed on the NAS system
itself (as above) normally lets containers reach your other devices through
the NAS. Tailscale run in a container of its own often uses
[userspace networking](https://tailscale.com/kb/1112/userspace-networking),
which does not, and jobdork would then find the AI machine unreachable. Once
the AI machine is set up (step 3), test from the NAS over SSH:

```bash
sudo docker run --rm curlimages/curl -s -m 5 http://<ai-machine-name>:11434/api/version
```

A version number back means containers can reach it. A timeout means they
cannot: install Tailscale on the NAS system itself, or run its container in
host network mode.

---

## 3. Ollama on the AI machine

Install Ollama: [macOS](https://docs.ollama.com/macos),
[Windows](https://docs.ollama.com/windows), [Linux](https://docs.ollama.com/linux).

**Let only your Tailscale devices reach it.** Ollama answers only the machine
it runs on until told otherwise, and it has no password. Tell it to listen on
the machine's **Tailscale address** (Machines page, `100.x.y.z`), not on
`0.0.0.0`: a laptop on hotel Wi-Fi listening on every network would let
anyone on that Wi-Fi use it. How to set it is in
[Ollama's FAQ](https://docs.ollama.com/faq), under exposing Ollama on the network:

| Machine | Set `OLLAMA_HOST` to the Tailscale address |
|---|---|
| macOS | `launchctl setenv OLLAMA_HOST 100.x.y.z`, then quit and reopen Ollama. Turn **off** "Expose Ollama to the network" in Ollama's settings, which listens everywhere. Repeat the command after a restart |
| Windows | Quit Ollama; in "Edit environment variables for your account" add `OLLAMA_HOST` = `100.x.y.z`; start Ollama |
| Linux | `sudo systemctl edit ollama.service`, add `[Service]` and `Environment="OLLAMA_HOST=100.x.y.z"`, then `sudo systemctl daemon-reload && sudo systemctl restart ollama` |

Tailscale has to be connected before Ollama starts, or Ollama cannot listen on
that address. From another of your devices, check:
`curl http://<ai-machine-name>:11434/api/version`.

**Choose models by the AI machine's memory.** A model needs roughly its
download size in memory, plus 1 to 2 GB while it reads. On a Mac that is the
Mac's memory; on a PC it is the graphics card's (a model larger than that runs
mostly on the processor, much slower). Tested with jobdork:

| Model | Download | Result with jobdork |
|---|---|---|
| `gemma4:26b` | 18.6 GB | Good at everything, cover letters and tailored edits included. Needs about 24 GB: a Mac with 32 GB, or a large graphics card |
| `qwen2.5:3b` | 1.9 GB | Fine for sorting job posts (verdicts, ATS keywords). Too many unsupported claims for writing |
| `llama3.2:3b` | 2.0 GB | Not recommended: rated every post "strong", and failed on tailored edits |

As a rule, pick the largest model that fits. Whatever you choose, jobdork
checks every model's claims against your resume and the ad and shows what it
could not support. A small model makes more of those, not fewer.

Download one on the AI machine with `ollama pull <model>`.

---

## 4. jobdork on the NAS

**The image.** jobdork is published to Docker Hub as
[`jessengolab/jobdork`](https://hub.docker.com/r/jessengolab/jobdork/tags).
Use a version tag (`0.14.4`) so an update is your choice; `latest` is the
newest release. **Use 0.14.4 or newer:** older images do not create their own
settings on the first start and restart over and over without a
`config.yaml` mapped in. Every published image is signed;
[SECURITY.md](../SECURITY.md) shows how to check the signature and pin the
exact image by its digest before you run it.

**A folder for its files.** Make an empty folder on the NAS, for example
`docker/jobdork/data`. It holds everything jobdork keeps: the database of job
posts, `config.yaml`, your resume and your letters. There is no config to
prepare: on the first start jobdork copies the example the image carries into
`data/config.yaml`, and the dashboard's settings are saved there. (A
`config.yaml` of your own mapped to `/app/config.yaml` is used instead, as
before.) **Without this folder mapped, everything is deleted with the
container**; the log and the dashboard say so in red.

The container runs as user and group **1000**, so the folder must be writable
by 1000. Most NAS make their first user 1000 already; if saving fails with
"permission denied", run over SSH `sudo chown -R 1000:1000 /path/to/docker/jobdork`.

**The container: the easy way, a compose project.** Most NAS Docker apps
take a compose file pasted in, which fills every setting at once. Copy
[`compose.yaml`](../compose.yaml) from the repository, change the version
tag and `JOBDORK_ALLOW_HOSTS` (below), and paste it where your NAS asks for
one. Put it in the `docker/jobdork` folder, so its `./data` is the folder
above.

| NAS | Where a compose file goes |
|---|---|
| Synology (Container Manager) | **Project** → **Create** → name `jobdork`, path `docker/jobdork`, source **Create docker-compose.yml** → paste → **Next** → **Done** |
| QNAP (Container Station 3) | **Applications** → **Create** → name `jobdork` → paste → **Create** |
| UGREEN (UGOS Pro) | **Docker** → **Project** → **Create** → name `jobdork`, storage path `docker/jobdork` → paste → **Deploy** |
| TrueNAS SCALE (24.10 and later) | **Apps** → **Discover Apps** → the menu beside Custom App → **Install via YAML** → paste, with `./data` changed to the dataset's full path |
| Portainer, on any of them | **Stacks** → **Add stack** → **Web editor** → paste → **Deploy the stack** |

Menu names move between versions; each NAS's own guide, linked in step 1,
has the current ones.

**The container: setting by setting.** Unraid's Docker tab, and any app
without compose, asks for each value instead:

| Setting | Value |
|---|---|
| Image | `jessengolab/jobdork:<version>` |
| Port | NAS `8765` → container `8765` |
| Volume | `…/docker/jobdork/data` → `/app/data`, read/write |
| Environment | `JOBDORK_ALLOW_HOSTS` = the NAS's addresses, comma separated: its home-network address and its Tailscale name, e.g. `10.0.0.122,my-nas.tail1234.ts.net` |
| Memory limit | 1 GB is plenty |
| Auto restart | On |

On Unraid: **Docker** → **Add Container** → Repository `jessengolab/jobdork:<version>`;
then **Add another Path, Port, Variable, Label or Device** three times: a
Port (8765 to 8765), a Path (container `/app/data`, host
`/mnt/user/appdata/jobdork`) and a Variable (`JOBDORK_ALLOW_HOSTS`) → **Apply**.

Or as a command:

```bash
docker run -d --name jobdork --restart unless-stopped -p 8765:8765 \
  -e JOBDORK_ALLOW_HOSTS=10.0.0.122,my-nas.tail1234.ts.net \
  -v /volume1/docker/jobdork/data:/app/data \
  jessengolab/jobdork:<version>
```

**Opening it.** The container's log prints the address with its access token,
`http://127.0.0.1:8765/?t=…`, and a line for each allowed address. Use the
Tailscale one from anywhere, or the home-network one at home. The token is
new every time the container starts, so after a restart read it from the log
again. Every request needs it; keep the link to yourself.

**Your resume and letters are kept** in `data/documents`, with your job
posts, statuses and settings, so a restart keeps them. If other people use
the NAS and nothing personal should outlive a run, add
`-e JOBDORK_TEMP_DOCS=/tmp/jobdork` to the `docker run`: the resume and
letters then go to a temporary folder, emptied when jobdork starts and stops,
and you upload the resume again after each restart.

---

## 5. Point jobdork at the AI machine

On the dashboard's AI page: provider **Ollama**, address
`http://<ai-machine-name>:11434` (its Tailscale name), a model you downloaded,
then **Save and test**. `localhost` would mean the jobdork container itself,
not the AI machine.

`llm.context` in `config.yaml` (16,384 by default) is how much text jobdork
asks Ollama to make room for on each call; it suits every model above.

---

## If your NAS has more memory

The advice above is the same for any NAS: the AI belongs on a computer with a
graphics card or Apple Silicon. Two exceptions:

- **No other computer is on often enough.** A NAS with 16 GB or more can run
  Ollama itself with `qwen2.5:3b` for sorting job posts, as its own container
  (image `ollama/ollama`, volume → `/root/.ollama`, `OLLAMA_HOST` =
  `0.0.0.0:11434`, a memory limit of about half the NAS's). Expect the timing
  above: minutes per verdict and a busy processor. Turn on judging after each
  scan (`llm.judge_on_scan`) and let it run overnight.
- **The NAS has a graphics card.** Some models take one; the Docker app's GPU
  option then gives it to Ollama, which changes the picture completely.

An 8 GB NAS should run jobdork only: the NAS system, Docker and jobdork use
about 3 GB, and a model on top leaves too little for the NAS's own work.

---

## When something does not work

| You see | Meaning |
|---|---|
| "unrecognised Host header" | The address you opened is not in `JOBDORK_ALLOW_HOSTS`. Add it and restart the container |
| "missing or wrong token" | The token changed on restart, or was left off. Take the link from the container's log |
| The AI page's test cannot reach Ollama | The AI machine is asleep or off, Tailscale is not connected on it, or `OLLAMA_HOST` is not its Tailscale address. Check with `curl` from another device |
| It works from a laptop but not from jobdork | Containers cannot reach Tailscale (step 2's test) |
| "permission denied" saving settings | The folder is not writable by 1000 (step 4) |
| The dashboard does not load at all | The container is stopped, or the port is not published; see its log |
| The container restarts over and over, and its log says "No config found" | The image is 0.14.3 or older, which cannot create its own settings. Use 0.14.4 or newer, or map a `config.yaml` to `/app/config.yaml` |
| A red notice: "Your data is deleted with this container" | `/app/data` is not mapped to a folder on the NAS (step 4's Volume). Add it and recreate the container; until then nothing is kept when the container is removed |
