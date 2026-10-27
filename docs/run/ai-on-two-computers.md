# The AI on two computers

The AI page asks for two models: a **reader**, which judges job posts and
writes letters, and a **checker**, which checks what the reader wrote against
your resume and the advert. The good ones (`gemma4:26b` as reader,
`qwen3.8:27b` as checker) are about 18 GB each. One computer rarely holds
both: on a 32 GB Mac they push each other out of memory, every call reloads a
model, and calls fail.

Put one on each computer you already own. jobdork lets every model have its
own Ollama address, so the reader can run on a PC with a graphics card and
the checker on the laptop jobdork runs on. They talk over
[Tailscale](https://tailscale.com), a free private network between your own
devices, so nothing is opened to your home network or the internet.

```
  laptop (jobdork + checker)                PC with a graphics card (reader)
  ┌────────────────────────────┐            ┌────────────────────────────┐
  │ jobdork                    │  Tailscale │ Ollama                     │
  │   reader  ─────────────────┼───────────▶│   gemma4:26b               │
  │   checker ─▶ Ollama        │            │                            │
  │              qwen3.8:27b   │            │ port 11434, Tailscale only │
  └────────────────────────────┘            └────────────────────────────┘
```

Tried this way: jobdork on a MacBook Pro (M4) with `qwen3.8:27b` as checker,
and `gemma4:26b` as reader on a Windows 11 PC with an AMD Radeon RX 6700 XT
(12 GB) and 64 GB of memory. The PC ran 78% of the model on the card and
judged a job post in about 50 seconds over Tailscale, once Flash Attention
was off (see [AMD cards on Windows](#amd-cards-on-windows)). The M4 alone
judged one in about 13 seconds: a second computer is for memory, so each
holds one big model, not always for speed.

Any pair works the same way: two Macs, a Linux box, the other way round. The
steps below name a **PC** (the computer that gets the second model) and a
**laptop** (the one jobdork runs on).

---

## 1. Tailscale on both

Make one free Tailscale account and install Tailscale on both computers from
[tailscale.com/download](https://tailscale.com/download), signed in to the
same account. Leave **[MagicDNS](https://tailscale.com/kb/1081/magicdns)** on
(the default), so each computer has a name.

Check from the laptop that both are there:

```
tailscale status
```

Each computer is one line with a `100.x.y.z` address; the second column is
its name, used below as `<pc-name>`. On a Mac, Terminal may not know the
`tailscale` command; it is `/Applications/Tailscale.app/Contents/MacOS/Tailscale`.

## 2. Ollama on the PC, and its graphics card

Install Ollama from [ollama.com/download](https://ollama.com/download), then
download the reader and try it:

```
ollama pull gemma4:26b
ollama run gemma4:26b "say hi"
ollama ps
```

The **PROCESSOR** column says where the model runs. `22%/78% CPU/GPU` means
most of it is on the graphics card, which is what you want; a model larger
than the card's memory always has some on the processor. **`100% CPU`**
means the card is not used, and the model will be several times slower.
For that, see [Ollama's GPU page](https://docs.ollama.com/gpu). Two cases come
up with AMD cards that Ollama's ROCm build does not list (the RX 6700 XT is one):

- **Linux:** set `HSA_OVERRIDE_GFX_VERSION` in Ollama's service environment to
  the nearest supported version (`10.3.0` for the RX 6000 series).
- **Windows:** Ollama may use its Vulkan backend for the card on its own
  (the log says `ggml_vulkan`); older versions needed `OLLAMA_VULKAN=1`, set
  as in step 3. Read [AMD cards on Windows](#amd-cards-on-windows) before
  step 3's memory settings.

`CONTEXT 4096` in that line is what `ollama run` asks for. jobdork asks for its
own (`llm.context`, 16,384 by default) on every call; nothing to change.

## 3. Let your Tailscale devices reach it

Ollama answers only the computer it runs on until told otherwise, and **it
has no password**: whoever can reach it can use it. So it listens for other
computers, and a firewall rule lets in Tailscale's addresses only.

**Windows.** In PowerShell, one line at a time:

```
setx OLLAMA_HOST 0.0.0.0:11434
setx OLLAMA_KEEP_ALIVE 30m
```

With an **NVIDIA** card, add these two, which roughly halve the memory a
model's reading takes and so leave more of the model on the card:

```
setx OLLAMA_FLASH_ATTENTION 1
setx OLLAMA_KV_CACHE_TYPE q8_0
```

With an **AMD** card, leave them out: see
[AMD cards on Windows](#amd-cards-on-windows).

Then quit Ollama from its tray icon and start it again: `setx` reaches only
programs started after it. Open a new PowerShell window before checking
anything, for the same reason.

Then, in **PowerShell as Administrator** (right-click PowerShell, Run as
administrator), the firewall rule, in one line:

```
New-NetFirewallRule -DisplayName "Ollama via Tailscale" -Direction Inbound -Protocol TCP -LocalPort 11434 -RemoteAddress 100.64.0.0/10 -Action Allow
```

`100.64.0.0/10` is Tailscale's address range. Check the port came out right
(it should print `11434`):

```
Get-NetFirewallRule -DisplayName "Ollama via Tailscale" | Get-NetFirewallPortFilter | Select-Object LocalPort
```

If Windows ever asks whether to allow `ollama.exe` on networks, click
**Cancel**: the rule above already lets Tailscale in, and allowing it there
would open it to everyone on your Wi-Fi.

`KEEP_ALIVE 30m` keeps the model loaded between calls instead of loading
18 GB again for each job post.

A PowerShell window keeps the settings it had when it opened: to check one
(`echo $env:OLLAMA_HOST`), open a new window first.

**macOS or Linux as the PC.** Listen on the computer's Tailscale address
instead, which needs no firewall rule: the table in
[nas.md, step 3](nas.md#3-ollama-on-the-ai-machine) has the command for each.
That is also the safer choice for a laptop that goes on other Wi-Fi. Its
catch: Tailscale must be connected before Ollama starts. The Windows way
above does not have that catch, which suits a desktop that stays at home.

## 4. Keep the PC reachable

- **Sleep:** Settings, System, Power, sleep **Never** when plugged in. A
  sleeping PC drops off Tailscale, and every AI call to it fails.
- **Log in after a restart:** Ollama starts when you log in to Windows.
- Optional: Tailscale's **Run unattended** (its tray menu, Preferences)
  keeps Tailscale connected before anyone logs in.

## 5. Test from the laptop

```
curl http://<pc-name>:11434/api/tags
```

A list naming `gemma4:26b` means it works. Nothing back at all (it waits,
then gives up) is covered under [When something does not work](#when-something-does-not-work).

## 6. Tell jobdork

On the **AI** page:

1. **Reader 1:** provider **Ollama**, Ollama address
   `http://<pc-name>:11434`, **Load models**, choose `gemma4:26b`.
2. **Checker 1:** provider **Ollama**, Ollama address
   `http://localhost:11434` (the laptop's own), model `qwen3.8:27b`.
   Download it on the laptop first: `ollama pull qwen3.8:27b`.
3. **Save and test.** Each line should end "answered in …s".

The same in `config.yaml`: an entry with no `ollama_url` uses the one at the
top of `llm`.

```yaml
llm:
  ollama_url: http://localhost:11434
  readers:
    - provider: ollama
      model: gemma4:26b
      ollama_url: http://<pc-name>:11434
  checkers:
    - provider: ollama
      model: qwen3.8:27b
```

jobdork refuses to fetch job pages from private addresses, so that a job
post cannot point it into your network; that rule is for job sites only. AI
calls go to the addresses you set here, Tailscale's `100.x` ones included.

**A fallback.** Add a second checker on the PC (`ollama pull gpt-oss:20b`
there, the same PC address): when the first checker cannot answer, the next
is asked. A second reader works the same way, for when the PC is off.

---

## Which computer runs what

A model is fast when it fits in the graphics card's memory (on a Mac, its
memory). Part of it on the processor still works, more slowly. Ollama holds
a model loaded for as long as `OLLAMA_KEEP_ALIVE` says, and the card is busy
for that whole time.

| The strong computer has | Run there | Run on jobdork's computer |
|---|---|---|
| A graphics card of 8 to 12 GB | The reader, part of it on the processor (here, 12 GB: about 50 s a job post), or a smaller reader that fits the card | The checker |
| 16 to 24 GB | The reader (`gemma4:26b`, 18.6 GB) | The checker |
| 40 GB or more, two cards, or a Mac with 64 GB | **Both** reader and checker | Nothing but jobdork |

**Both on one strong computer.** The two models together are about 37 GB,
and about 2 GB more each while reading: some 40 GB holds both loaded at
once. With less, it still works: Ollama unloads one to load the other at
each switch, about 18 GB read again each time. On the AI page give both the
same address, or in `config.yaml`:

```yaml
llm:
  ollama_url: http://<pc-name>:11434     # every entry without its own address
  readers:
    - provider: ollama
      model: gemma4:26b
  checkers:
    - provider: ollama
      model: qwen3.8:27b
```

Then jobdork's own computer needs no Ollama at all, and stays free while a
scan's AI work runs.

**Using the PC for other things too.** On a card smaller than the model,
the model fills it while it works (here 10.7 to 11.6 GB of 12, however few
layers it was told to use). Set `OLLAMA_KEEP_ALIVE 2m` instead of `30m`: the
card is free two minutes after the last call, and the next scan waits about
25 seconds while the model loads again.

## AMD cards on Windows

On the RX 6700 XT, `OLLAMA_FLASH_ATTENTION 1` with `OLLAMA_KV_CACHE_TYPE
q8_0` made every job post fail. Ollama ran the card through Vulkan; reading
a prompt slowed from 138 to 17 tokens a second as it went, about 210 seconds
a job post, and then the model process died: jobdork showed HTTP 500,
"An existing connection was forcibly closed", and AMD's crash report
appeared. With both settings off, the same job posts took about 50 seconds
and none failed.

The signs, if it happens to you:

- jobdork: AI calls fail with HTTP 500 and "An existing connection was
  forcibly closed", and AMD's crash report appears on the PC.
- Ollama's log has `ggml_vulkan: device fault`. To look:
  `Select-String -Path "$env:LOCALAPPDATA\Ollama\server*.log" -Pattern "device fault"`

The fix, in PowerShell:

```
setx OLLAMA_FLASH_ATTENTION 0
setx OLLAMA_KV_CACHE_TYPE f16
```

Both at once: the `q8_0` cache needs Flash Attention, and with only the
first changed Ollama refuses to start ("quantized V cache requires
flash_attn"). Then stop every Ollama process, since quitting from the tray
can leave one running, and start Ollama again:

```
Get-Process ollama* | Stop-Process -Force
```

Not the sign: Task Manager's **Shared GPU memory** above zero. Windows
lends the card some of your normal memory whether it works or not; here it
held 3.2 GB with the card full (11.6 of 12 GB) and every job post fine.
Reserving room on the card (`OLLAMA_GPU_OVERHEAD`) and fewer layers on it (a
model made with `PARAMETER num_gpu`) did not help either.

## Security

- **Never forward port 11434 on your router.** Ollama has no password;
  forwarded, anyone on the internet can use your computer's model.
- Tailscale devices are the ones signed in to your account. Sharing a
  device, or a tag, with someone else's account lets them in too.
- Your resume and the job posts go to the PC to be read. Over Tailscale they
  are encrypted end to end, and they stay on your two computers.

## Someone else using your Ollama

For a tester who is not on your tailnet, put Ollama behind a gatekeeper that
checks a key (a reverse proxy or tunnel that requires
`Authorization: Bearer <key>`), and give them a connection code instead of
four settings:

```bash
jobdork ollama-code --url https://ollama.example.org --reader gemma4:26b --checker qwen3.8:27b
```

It asks for the key without showing it (never on the command line, where it
would stay in your shell's history) and prints one line starting
`jobdork-ollama-1:`. Send it privately: it carries the key. They paste it on
their AI page under **Use this code**. jobdork sends the key only on the
Ollama lines marked **Send the Ollama key**; a refused key says "the key was
refused". `JOBDORK_OLLAMA_KEY` in the environment works too.

## When something does not work

| You see | Meaning |
|---|---|
| `curl` from the laptop waits, then gives up | The firewall rule is missing or has the wrong port (step 3's check), Ollama was not restarted after `setx`, or the PC is asleep or off Tailscale |
| `curl` answers "connection refused" | Ollama is not running on the PC, or `OLLAMA_HOST` is not set: in a new PowerShell window, `echo $env:OLLAMA_HOST` should print `0.0.0.0:11434` |
| `ollama ps` on the PC says `100% CPU` | The graphics card is not used; step 2 |
| HTTP 500, "forcibly closed", or AMD's crash report; each job post several minutes | [AMD cards on Windows](#amd-cards-on-windows) |
| "quantized V cache requires flash_attn" | `OLLAMA_KV_CACHE_TYPE` is still `q8_0` with Flash Attention off; set it to `f16` and restart Ollama |
| Save and test: "could not reach <pc-name>:11434" for the reader only | The PC went to sleep, or Tailscale on it disconnected |
| Out of memory, or every call slow on the laptop | Both models are still on the laptop: the reader's address is `localhost`, not the PC's |
| `tailscale: command not found` on a Mac | Use `/Applications/Tailscale.app/Contents/MacOS/Tailscale status` |

jobdork in Docker or on a NAS reaches Tailscale names only when Tailscale is
on the machine itself, not in a container of its own: see
[nas.md, step 2](nas.md#2-tailscale-on-every-device).
