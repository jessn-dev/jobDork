"""Lets `python -m jobdork` work without installing anything."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
