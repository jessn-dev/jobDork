"""pytest's settings for the suite; tests/run_all.py sets the same."""

import os

# No test asks GitHub whether a newer jobdork is out (core/updates.py).
os.environ["JOBDORK_UPDATE_CHECK"] = "off"
# Nor pops up a notification (core/notify.py).
os.environ["JOBDORK_NOTIFY"] = "off"


class _PretendKeychain:
    """A dict in place of the OS keychain: no test reads or writes a real
    one (core/keystore.py)."""

    def __init__(self):
        self.kept = {}

    def get_password(self, service, name):
        return self.kept.get((service, name))

    def set_password(self, service, name, value):
        self.kept[(service, name)] = value

    def delete_password(self, service, name):
        self.kept.pop((service, name), None)


from jobdork.core import keystore  # noqa: E402

keystore._backend = _PretendKeychain()
