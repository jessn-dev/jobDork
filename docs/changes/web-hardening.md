## Security — 2026-11-11 — Four smaller fixes to the dashboard's server

From the code scans of 2026-11-06 (Claude Security F11 and the hand scan's
#7, #8 and #11). Each needed the dashboard's token, or a program already on
the computer, to matter.

- **The Ollama key** (#7): the list of an Ollama's models was fetched from
  whatever address the page named, with the key if asked. The key now goes
  only to an address a saved Ollama line already sends it to; a new line's
  models load once it is saved with **Send the Ollama key** ticked, and the
  message says so (`api.llm_models`).
- **The digest** (#8): `/api/digest` mailed the job list to any address
  the request named. The page never used it; it is gone. `jobdork digest`
  in the terminal sends the digest as before.
- **The token in the browser's command line** (F11): jobdork opened the
  browser with the token in the address, and the address handed to the
  system's open command sits in its command line, which any program on the
  computer can read. The browser is now opened with a code that works once,
  within a minute, and swaps itself for the token by a redirect
  (`Session.launch_url`). The desktop window was never affected.
- **A turned-away request** (#11): a request refused before its body was
  read left the body on the connection, and the next request on it was read
  from the middle of that. A refused request that is not a GET now closes
  its connection.

The guide's AI page says when the Ollama key's models load.
tests/test_web_hardening.py covers each one.
