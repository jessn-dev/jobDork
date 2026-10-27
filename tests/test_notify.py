"""
Notifications (core/notify.py) and the Update button's download
(core/updates.py). Nothing here shows a notification or goes online: every
command is a stand-in, and the download reads from memory.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core import notify, updates
from jobdork.core.config import Config, Notifications


@contextlib.contextmanager
def _env(**values):
    saved = {k: os.environ.get(k) for k in values}
    for k, v in values.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def _platform(name, frozen=False):
    saved = sys.platform
    sys.platform = name
    if frozen:
        sys.frozen = True
    try:
        yield
    finally:
        sys.platform = saved
        if frozen:
            del sys.frozen


class _Run:
    def __init__(self, code=0):
        self.calls, self.code = [], code

    def __call__(self, argv, **kw):
        self.calls.append((list(argv), kw))
        return types.SimpleNamespace(returncode=self.code, stdout="", stderr="")


def test_macos_uses_notification_center_with_a_bell():
    run = _Run()
    with _platform("darwin"):
        assert notify.send('Say "hi"', "3 new job posts", sound=True, run=run)
    argv, _ = run.calls[0]
    assert argv[:2] == ["osascript", "-e"]
    script = argv[2]
    assert 'with title "Say \\"hi\\""' in script and 'sound name "Glass"' in script
    run = _Run()
    with _platform("darwin"):
        notify.send("t", "b", sound=False, run=run)
    assert "sound name" not in run.calls[0][0][2]


def test_windows_shows_a_toast_under_the_apps_own_id():
    run = _Run()
    with _platform("win32", frozen=True):
        assert notify.send("2 new <job> posts", "found & kept", sound=True, run=run)
    argv, kw = run.calls[0]
    assert argv[0] == "powershell" and "CreateToastNotifier" in argv[-1]
    # What could change the script goes in the environment, escaped.
    assert kw["env"]["JOBDORK_AUMID"] == notify.APP_ID
    xml = kw["env"]["JOBDORK_TOAST"]
    assert "2 new &lt;job&gt; posts" in xml and "found &amp; kept" in xml
    assert "Notification.Default" in xml
    assert 'silent="true"' in notify.toast_xml("t", "b", sound=False)
    run = _Run()
    with _platform("win32"):
        notify.send("t", "b", run=run)
    assert run.calls[0][1]["env"]["JOBDORK_AUMID"] == notify.POWERSHELL_AUMID


def test_linux_uses_notify_send_with_the_bell_sound():
    run = _Run()
    with _platform("linux"):
        assert notify.send("t", "b", sound=True, run=run)
    argv = run.calls[0][0]
    assert argv[0] == "notify-send" and "--hint=string:sound-name:bell" in argv


def test_settings_and_the_environment_decide():
    cfg = Config(notifications=Notifications(enabled=True, sound=False))
    with _env(JOBDORK_NOTIFY=None):
        assert notify.wanted(cfg) == (True, False)
        assert notify.wanted(Config(notifications=Notifications(enabled=False))) == (False, False)
    with _env(JOBDORK_NOTIFY="off"):
        assert notify.wanted(cfg) == (False, False)
        assert not notify.native()
    with _env(JOBDORK_NOTIFY=None, JOBDORK_IN_CONTAINER="1"):
        assert not notify.native()


def test_a_scan_with_nothing_new_says_nothing():
    run = _Run()
    cfg = Config()
    saved = notify.native
    # lambda: as on a desktop, whatever machine the tests run on.
    notify.native = lambda: True
    try:
        with _env(JOBDORK_NOTIFY=None), _platform("linux"):
            assert not notify.scan_finished(cfg, 0, 40, run=run)
            assert notify.scan_finished(cfg, 3, 40, origin="schedule", run=run)
            assert notify.scan_failed(cfg, "HTTP 500", run=run)
    finally:
        notify.native = saved
    assert len(run.calls) == 2
    first = " ".join(run.calls[0][0])
    assert "3 new job posts" in first and "The scheduled scan found 3" in first


def test_a_failing_command_never_breaks_a_scan():
    def broken(argv, **kw):
        raise OSError("no such command")
    saved = notify.native
    # lambda: as on a desktop, whatever machine the tests run on.
    notify.native = lambda: True
    try:
        with _env(JOBDORK_NOTIFY=None), _platform("linux"):
            assert notify.notify(Config(), "t", "b", run=broken) is False
    finally:
        notify.native = saved


# ── the Update button ─────────────────────────────────────────────────────────


INSTALLER = b"pretend this is a disk image"
BASE = updates.DOWNLOAD_PREFIX + "v9.0.0/"


def _opener(files):
    """urlopen's stand-in: answers from `files` by URL."""
    def open_(request, timeout=0):
        body = files[request.full_url]
        answer = io.BytesIO(body)
        answer.headers = {"Content-Length": str(len(body))}
        return contextlib.closing(answer)
    return open_


NAME = "jobdork-9.0.0-windows-x64-setup.exe"
BOT = {"login": updates.CI_UPLOADER}


def _github(sums: bytes, uploader=BOT, attestations=None):
    """GitHub's stand-in: the release (files uploaded by `uploader`) and,
    for any installer digest, `attestations` (one bundle by default).
    (fetch, files for _opener)."""
    asked = []

    def fetch(url):
        asked.append(url)
        if url == updates.LATEST_URL:
            return {"tag_name": "v9.0.0", "html_url": "https://github.com/x", "assets": [
                {"name": n, "browser_download_url": BASE + n, "uploader": uploader}
                for n in (NAME, updates.SUMS_FILE)]}
        assert url.startswith(updates.ATTEST_URL.split("{")[0]), url
        return {"attestations": [{"bundle": {"pretend": "bundle"}}]
                if attestations is None else attestations}
    fetch.asked = asked
    return fetch, {BASE + NAME: INSTALLER, BASE + updates.SUMS_FILE: sums}


def _vouches(name=NAME, digest=None, version="9.0.0"):
    """Sigstore's stand-in: verifies only the identity of `version`'s
    workflow, and returns a statement naming `name` with `digest`."""
    def verify(bundle, identity):
        if identity != updates.build_identity(version):
            raise ValueError("certificate identity does not match")
        return {"subject": [{"name": name, "digest": {
            "sha256": digest or hashlib.sha256(INSTALLER).hexdigest()}}]}
    return verify


GOOD_SUMS = f"{hashlib.sha256(INSTALLER).hexdigest()}  {NAME}\n".encode()


def _refused(folder, why, **kw):
    try:
        updates.download_installer(folder / "Downloads", **kw)
    except updates.UpdateError as exc:
        assert why in str(exc), str(exc)
    else:
        raise AssertionError("an installer was let through")
    assert not (folder / "Downloads" / NAME).exists()


def test_the_installer_is_downloaded_and_checked_against_the_release():
    with tempfile.TemporaryDirectory() as tmp, _platform("win32", frozen=True):
        folder = Path(tmp)
        fetch, files = _github(GOOD_SUMS)
        said = []
        path = updates.download_installer(folder / "Downloads", progress=said.append,
                                          opener=_opener(files), fetch=fetch, verify=_vouches())
        assert path.name == NAME and path.read_bytes() == INSTALLER
        assert any("checksum matches" in s for s in said)
        assert any("built by this project's release workflow" in s for s in said)
        assert not list((folder / "Downloads").glob(".jobdork-*"))   # the sums file went
        digest = hashlib.sha256(INSTALLER).hexdigest()
        assert fetch.asked == [updates.LATEST_URL, updates.ATTEST_URL.format(digest=digest)]


def test_an_installer_that_does_not_match_is_deleted():
    with tempfile.TemporaryDirectory() as tmp, _platform("win32", frozen=True):
        folder = Path(tmp)
        fetch, files = _github(f"{'0' * 64}  {NAME}\n".encode())
        _refused(folder, "does not match", opener=_opener(files), fetch=fetch, verify=_vouches())


def test_a_file_uploaded_by_hand_is_not_offered():
    """A stolen login or token can put a file on a release, but it is
    uploaded by that person, not by the release workflow."""
    with tempfile.TemporaryDirectory() as tmp, _platform("win32", frozen=True):
        folder = Path(tmp)
        fetch, files = _github(GOOD_SUMS, uploader={"login": "jessn-dev"})
        _refused(folder, "no installer for this computer", opener=_opener(files),
                 fetch=fetch, verify=_vouches())


def test_an_installer_with_a_matching_checksum_but_no_valid_attestation_is_deleted():
    """Whoever could replace the installer could replace SHA256SUMS.txt."""
    with tempfile.TemporaryDirectory() as tmp, _platform("win32", frozen=True):
        folder = Path(tmp)
        cases = [
            ([], _vouches()),                          # no attestation at all
            (None, _vouches(version="8.0.0")),         # another tag's build
            (None, _vouches(name="other.exe")),        # another file
            (None, _vouches(digest="f" * 64)),         # other contents
        ]
        for attestations, verify in cases:
            fetch, files = _github(GOOD_SUMS, attestations=attestations)
            _refused(folder, "could not be shown to come from this project's release workflow",
                     opener=_opener(files), fetch=fetch, verify=verify)


def test_an_installer_is_not_opened_when_github_cannot_be_asked_who_built_it():
    def offline(url):
        if url == updates.LATEST_URL:
            return fetch(url)
        raise OSError("no network")
    with tempfile.TemporaryDirectory() as tmp, _platform("win32", frozen=True):
        folder = Path(tmp)
        fetch, files = _github(GOOD_SUMS)
        _refused(folder, "could not ask GitHub who built", opener=_opener(files),
                 fetch=offline, verify=_vouches())


def test_the_real_attestation_of_0_14_4_verifies_offline_and_only_for_its_tag_and_file():
    """The bundle GitHub published for 0.14.4's macOS installer, checked with
    Sigstore against the trust root that ships with it: no network."""
    import functools
    from importlib import resources

    kept = json.loads(resources.files("jobdork").joinpath(
        "data/attestation-check.json").read_text(encoding="utf-8"))
    offline = functools.partial(updates.signed_statement, offline=True)

    def fetch(url):
        return {"attestations": [{"bundle": kept["bundle"]}]}

    updates.verify_attestation(kept["name"], kept["sha256"], "0.14.4", fetch=fetch, verify=offline)
    for name, digest, version in ((kept["name"], kept["sha256"], "0.15.0"),     # another tag
                                  ("jobdork-0.14.4-windows-x64-setup.exe", kept["sha256"], "0.14.4"),
                                  (kept["name"], "0" * 64, "0.14.4")):
        try:
            updates.verify_attestation(name, digest, version, fetch=fetch, verify=offline)
        except updates.UpdateError:
            pass
        else:
            raise AssertionError(f"verified {name} {digest[:8]} for {version}")
    assert updates.check_bundled_attestation() == ""


def test_only_the_desktop_app_on_a_known_system_gets_an_installer():
    assert updates.installer_name("9.0.0") == ""                    # not the desktop app
    with _platform("win32", frozen=True):
        assert updates.installer_name("9.0.0") == "jobdork-9.0.0-windows-x64-setup.exe"
    saved = updates.platform.machine
    try:
        for machine, arch in (("arm64", "arm64"), ("x86_64", "x86_64")):
            # lambda: the processor this Mac reports, Apple silicon or Intel.
            updates.platform.machine = lambda m=machine: m
            with _platform("darwin", frozen=True):
                assert updates.installer_name("9.0.0") == f"jobdork-9.0.0-macos-{arch}.dmg"
    finally:
        updates.platform.machine = saved
    with _platform("linux", frozen=True):
        assert updates.installer_name("9.0.0") == ""
    try:
        updates._download("https://example.com/evil.exe", Path("x"))
    except updates.UpdateError as exc:
        assert "release downloads" in str(exc)
    else:
        raise AssertionError("downloaded from elsewhere")


def test_a_new_version_is_announced_once():
    with tempfile.TemporaryDirectory() as tmp:
        assert updates.first_notice(tmp, "9.0.0")
        assert not updates.first_notice(tmp, "9.0.0")
        assert updates.first_notice(tmp, "9.1.0")


def test_check_now_asks_even_within_the_day():
    calls = []

    def fetch(url):
        calls.append(url)
        return {"tag_name": "v9.0.0", "html_url": "https://github.com/x", "assets": [
            {"name": "SHA256SUMS.txt", "browser_download_url": BASE + "SHA256SUMS.txt",
             "uploader": BOT},
            {"name": "bad", "browser_download_url": "https://elsewhere.example/bad",
             "uploader": BOT}]}

    def clock():
        return 1000.0

    with tempfile.TemporaryDirectory() as tmp, _env(JOBDORK_UPDATE_CHECK=None):
        updates.latest(tmp, fetch=fetch, now=clock)
        release = updates.latest(tmp, fetch=fetch, now=clock)
        assert len(calls) == 1
        assert set(release["assets"]) == {"SHA256SUMS.txt"}       # only this repo's
        updates.latest(tmp, fetch=fetch, now=clock, force=True)
        assert len(calls) == 2


def test_the_settings_page_routes():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_serve import _with_server

    def check(run):
        code, body = run.get("/api/state")
        assert code == 200 and json.loads(body)["notifications"]["native"] is False
        code, body = run.post("/api/update/install", {})
        assert code == 409 and b"only the desktop app" in body
        code, body = run.post("/api/notify/test", {})
        assert code == 200 and json.loads(body)["shown"] is False
        code, _ = run.post_json("/api/config", {"notifications": {"enabled": False}})
        assert code == 200 and run.cfg_now.notifications.enabled is False
        code, body = run.post("/api/notify/test", {})
        assert code == 409 and b"notifications are off" in body
        code, body = run.post("/api/update/check", {})
        assert code == 200 and json.loads(body)["newer"] is False   # tests never ask
    _with_server(check)


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except BaseException:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc(limit=3)
    raise SystemExit(1 if failed else 0)


def test_the_update_window_is_told_each_stage_as_it_passes():
    with tempfile.TemporaryDirectory() as tmp, _platform("win32", frozen=True):
        fetch, files = _github(GOOD_SUMS)
        seen = []
        updates.download_installer(Path(tmp) / "Downloads", opener=_opener(files), fetch=fetch,
                                   verify=_vouches(),
                                   # lambda: records each stage and its facts, in order.
                                   step=lambda stage, **facts: seen.append((stage, facts)))
        stages = [s for s, _ in seen]
        assert stages[:2] == ["asking", "downloading"] and stages[-2:] == ["checksum", "attestation"]
        assert seen[1][1] == {"file": NAME, "version": "9.0.0"}
        assert ("bytes", {"done": len(INSTALLER), "total": len(INSTALLER)}) in seen


def test_a_download_that_stops_part_way_says_why():
    with tempfile.TemporaryDirectory() as tmp, _platform("win32", frozen=True):
        fetch, _files = _github(GOOD_SUMS)

        def dropped(request, timeout=0):
            raise OSError("connection reset")
        _refused(Path(tmp), "the download stopped", opener=dropped, fetch=fetch, verify=_vouches())


def test_the_update_window_shows_the_end_and_a_failure_with_its_reason():
    """0.15.0 said "Downloading the update" while the job had already failed."""
    from jobdork.web import api, app

    def done(folder, progress=None, step=None):
        step("asking")
        step("downloading", file=NAME, version="9.0.0")
        step("checksum")
        step("attestation")
        return folder / NAME

    def refused(folder, progress=None, step=None):
        step("asking")
        raise updates.UpdateError("could not ask GitHub for the release (offline)")

    original, opener = updates.download_installer, app.open_with_system
    try:
        # lambda: stands in for opening the installer, which a test must not do.
        app.open_with_system = lambda path: None
        with _platform("win32", frozen=True):
            updates.download_installer = done
            api.update_job(None)(lambda line: None)
            state = api.update_progress()
            assert state["stage"] == "opened" and state["file"] == NAME
            updates.download_installer = refused
            with contextlib.suppress(RuntimeError):
                api.update_job(None)(lambda line: None)
            state = api.update_progress()
            assert state["stage"] == "failed" and "offline" in state["error"]
    finally:
        updates.download_installer, app.open_with_system = original, opener
