## Added — 2026-11-10 — The hallucination rate by checker, and how long the Dashboard keeps things

The Dashboard's hallucination rate mixes every checker used in the period.
After trying a strict checker for a day (one that flagged three claims in
four), the rate stayed high for as long as those runs were in the period,
with no way to see what the checker now set gave: changing to a better
one seemed to do nothing.

**Hallucination, over time** now splits **By checker** too, beside **By
kind** and **By model**, so the rate of the checker you use now shows at
once; and each line's legend gives its rate for the period as well as its
count. `/api/metrics` adds `checkers` and each day's `claims_by_checker`,
from the checker named in each output's guard report.

The guide's Dashboard page says how long each thing is kept: the
hallucination checks always (a fresh scan deletes the job posts, not this
history), runs and AI calls 120 days, run logs the last 200 runs, other
warnings and errors the last 500; the numbers count only the period
picked. tests/test_telemetry.py covers the split.
