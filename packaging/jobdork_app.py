"""What the installed app runs: `jobdork app`, with nothing to type.

Only `--debug`, `--scan` and `--self-test <report>` are read from the command line, and
anything else is ignored rather than refused: an app has no terminal to show
a usage error in, and macOS has passed launch arguments of its own in the past.

`--scan` is what the scan schedule runs (jobdork/core/schedule.py): one scan
in the app's folder, no window, output to its logs/scheduled-scan.log.

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
    raise SystemExit(app.run(port=8765, debug="--debug" in args))
