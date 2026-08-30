"""`python -m jobdork.dork` runs the generator directly."""

import runpy
import sys
from pathlib import Path

# The generator reads its own argv and expects to be __main__.
sys.path.insert(0, str(Path(__file__).resolve().parent))
runpy.run_path(str(Path(__file__).resolve().parent / "generator.py"),
               run_name="__main__")
