## Fixed — 2026-11-13 — The image check no longer fails with the address in its log

CI's `image` check failed now and then with "no address in the log", the
address printed right under it. It piped the container's log to `grep -q`
under `pipefail`: grep stops at the first match, `docker logs` is cut off,
and the pipeline counts as failed. `scripts/check_image.sh` now reads the log
first and looks in it. The 90-second wait added on 2026-10-30 for the same
symptom stays.
