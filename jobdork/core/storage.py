"""
jobdork.core.storage
====================
Where an uploaded resume and generated documents are kept.

On your own machine: the uploaded resume beside the config, in `data/`, and
each job's documents (cover letter, CV, screen, advert snapshot) in a folder
under `~/Documents/job-applications`.

In a container, `JOBDORK_TEMP_DOCS` names a temporary folder for both. It is
emptied whenever the dashboard starts and when it stops, so a resume and the
letters written from it do not outlive the run: upload the resume again after
a restart, and download a letter you want to keep. Scan results and settings
in `data/` are not affected.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

TEMP_ENV = "JOBDORK_TEMP_DOCS"
RESUME_STEM = "resume"          # an uploaded resume is always saved as resume.<ext>


def temp_root() -> Path | None:
    """The temporary folder, when one is configured."""
    raw = os.environ.get(TEMP_ENV, "").strip()
    return Path(raw).expanduser() if raw else None


def resume_dir(cfg) -> Path:
    """Where an uploaded resume is written."""
    temp = temp_root()
    if temp:
        return temp / "resume"
    return (Path(cfg.path).parent if getattr(cfg, "path", "") else Path.cwd()) / "data"


def documents_root() -> Path | None:
    """Where job folders go when temporary; None means the usual default."""
    temp = temp_root()
    return temp / "job-applications" if temp else None


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
