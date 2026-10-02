"""
jobdork.core.storage
====================
Where an uploaded resume and generated documents are kept.

On your own machine: the uploaded resume beside the config, in `data/`, and
each job's documents (cover letter, CV, screen, advert snapshot) in a folder
under `~/Documents/job-applications`.

In a container, `JOBDORK_DOCS_DIR` names a folder for both inside the kept
volume (the image sets `/app/data/documents`), so the resume and the letters
written from it survive a restart like scan results and settings do.

`JOBDORK_TEMP_DOCS` is the opt-in opposite: a temporary folder for both,
emptied whenever the dashboard starts and when it stops, for a shared machine
where nothing personal should outlive a run. Set, it wins over
`JOBDORK_DOCS_DIR`. Scan results and settings in `data/` are kept either way.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

TEMP_ENV = "JOBDORK_TEMP_DOCS"
DOCS_ENV = "JOBDORK_DOCS_DIR"
RESUME_STEM = "resume"          # an uploaded resume is always saved as resume.<ext>


def temp_root() -> Path | None:
    """The temporary folder, when one is configured."""
    raw = os.environ.get(TEMP_ENV, "").strip()
    return Path(raw).expanduser() if raw else None


def kept_root() -> Path | None:
    """The kept folder for resume and documents, when one is configured."""
    raw = os.environ.get(DOCS_ENV, "").strip()
    return Path(raw).expanduser() if raw else None


def resume_dir(cfg) -> Path:
    """Where an uploaded resume is written."""
    root = temp_root() or kept_root()
    if root:
        return root / "resume"
    return (Path(cfg.path).parent if getattr(cfg, "path", "") else Path.cwd()) / "data"


def documents_root() -> Path | None:
    """Where job folders go in a container; None means the usual default."""
    root = temp_root() or kept_root()
    return root / "job-applications" if root else None


def is_temporary(path: str | Path) -> bool:
    temp = temp_root()
    if not temp or not path:
        return False
    try:
        Path(path).expanduser().resolve().relative_to(temp.resolve())
        return True
    except (ValueError, OSError):
        return False


def is_uploaded_resume(path: str | Path, cfg) -> bool:
    """A resume this tool saved from an upload, as opposed to one you pointed
    the config at yourself. Only the first kind is ever deleted."""
    if not path:
        return False
    p = Path(path).expanduser()
    if p.stem != RESUME_STEM:
        return False
    try:
        return p.resolve().parent == resume_dir(cfg).resolve()
    except OSError:
        return False


def wipe() -> int:
    """Empty the temporary folder. Returns how many files were removed."""
    temp = temp_root()
    if not temp or not temp.is_dir():
        return 0
    removed = sum(1 for p in temp.rglob("*") if p.is_file())
    for child in temp.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    return removed


MOUNTINFO = Path("/proc/self/mountinfo")


def unkept_data_dir(cfg, mountinfo: Path = MOUNTINFO) -> str:
    """In a container, the data folder when it is not a mounted volume, else "".

    Without `-v <folder>:/app/data`, scan results, settings, the resume and
    letters live in the container's own layer and are deleted with the
    container. Read from the kernel's mount table: the folder holding the
    database, or one above it short of `/`, has to be a mount point.
    """
    from .config import in_container

    if not in_container():
        return ""
    data = Path(cfg.db_path).expanduser().resolve().parent
    try:
        mounts = {line.split()[4] for line in mountinfo.read_text().splitlines()
                  if len(line.split()) > 4}
    except OSError:
        return ""                    # cannot tell; say nothing rather than guess
    for folder in (data, *data.parents):
        if str(folder) == "/":
            break
        if str(folder) in mounts:
            return ""
    return str(data)
