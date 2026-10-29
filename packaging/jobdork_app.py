"""What the installed app runs: `jobdork app`, with nothing to type.

Only `--debug`, `--scan`, `--mcp`, `--agent [TOOL JSON]`, `--uninstall [items]` and `--self-test <report>` are read
from the command line, and
anything else is ignored rather than refused: an app has no terminal to show
a usage error in, and macOS has passed launch arguments of its own in the past.

`--scan` is what the scan schedule runs (jobdork/core/schedule.py): one scan
in the app's folder, no window, output to its logs/scheduled-scan.log.

`--uninstall` is what the Windows uninstaller runs before it removes the
program: the scheduled scan and the window's storage go, and the items named
(comma separated, chosen on the uninstaller's page; none when it runs
silently). No window.

`--mcp` is what a coding agent starts (Claude Code, Codex, Cursor, Claude
Desktop): jobdork's tools over stdio, in the app's folder (web/mcp.py).
`--agent TOOL JSON` runs one of them and prints its answer, for an agent
that only runs commands. No window for either.

`--self-test` checks the build has everything it needs, writes what is
missing to <report> (a Windows app has no stdout to print it to), and exits
1 if anything is, without opening a window. packaging/build.py runs it.
"""

import sys

from jobdork.web import app


def self_test(report: str) -> int:
    problems = app.self_test()
    with open(report, "w", encoding="utf-8") as fh:
        fh.write("\n".join(problems) or "ok")
        fh.write("\n")
    return 1 if problems else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--self-test" in args and args.index("--self-test") + 1 < len(args):
        raise SystemExit(self_test(args[args.index("--self-test") + 1]))
    if "--scan" in args:
        raise SystemExit(app.scheduled_scan())
    if "--mcp" in args:
        raise SystemExit(app.agent_server())
    if "--agent" in args:
        raise SystemExit(app.agent_server(["agent", *args[args.index("--agent") + 1:][:2]]))
    if "--uninstall" in args:
        from jobdork.core import uninstall
        at = args.index("--uninstall") + 1
        items = args[at].split(",") if at < len(args) and not args[at].startswith("-") else []
        uninstall.remove(set(items))
        raise SystemExit(0)
    raise SystemExit(app.run(port=8765, debug="--debug" in args))
