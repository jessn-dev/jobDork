## Security — 2026-11-12 — The Docker image installs jobdork from a built wheel

The Docker image installed jobdork's own code with `pip install .`, straight
from the source folder. Every dependency was already checked against the
hashes in requirements.lock, but OpenSSF Scorecard counted that last install
as unpinned (code scan #26), because pip cannot check a hash on a folder. The
build now makes a wheel from the same source and installs that file, still
without fetching anything. The image holds the same code as before.
