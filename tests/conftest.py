"""pytest's settings for the suite; tests/run_all.py sets the same."""

import os

# No test asks GitHub whether a newer jobdork is out (core/updates.py).
os.environ["JOBDORK_UPDATE_CHECK"] = "off"
# Nor pops up a notification (core/notify.py).
os.environ["JOBDORK_NOTIFY"] = "off"
