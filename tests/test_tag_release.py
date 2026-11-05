"""scripts/tag_release.py: the next version, the release merge, the checks.
Only the parts that decide; nothing here runs git or reaches GitHub."""

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "tag_release", Path(__file__).resolve().parent.parent / "scripts" / "tag_release.py")
tag_release = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tag_release)


def test_the_last_release_is_the_highest_by_number_not_by_text():
    tags = ["v0.9.0", "v0.16.1", "v0.16.0", "v0.2.10", "nightly", "v1.0.0-rc1", ""]
    assert tag_release.last_release(tags) == (0, 16, 1)


def test_no_release_tag_stops():
    with pytest.raises(SystemExit):
        tag_release.last_release(["nightly"])


@pytest.mark.parametrize("kind, want", [("patch", "0.16.2"), ("minor", "0.17.0"),
                                        ("major", "1.0.0")])
def test_each_kind_moves_the_last_release_on(kind, want):
    assert tag_release.bump((0, 16, 1), kind) == want


def test_a_release_merge_is_known_by_its_branch_or_its_squash():
    merge = "Merge pull request #127 from jessn-dev/release/0.16.2"
    assert tag_release.is_release_merge(merge, "", "0.16.2")
    assert tag_release.is_release_merge("chore: release 0.16.2 (see docs/CHANGELOG.md) (#127)",
                                        "", "0.16.2")
    assert not tag_release.is_release_merge(merge, "", "0.16.20")
    assert not tag_release.is_release_merge("Merge pull request #126 from jessn-dev/feat/unslop",
                                            "", "0.16.2")
    assert not tag_release.is_release_merge(
        "Merge pull request #9 from jessn-dev/release/0.16.2-hotfix", "", "0.16.2")


def test_checks_that_pass_or_were_skipped_are_fine():
    runs = [{"name": "test (3.10)", "status": "completed", "conclusion": "success"},
            {"name": "Installers", "status": "completed", "conclusion": "skipped"}]
    assert tag_release.failing(runs) == ([], [])


def test_a_check_running_or_failed_is_named():
    runs = [{"name": "image", "status": "in_progress", "conclusion": None},
            {"name": "security", "status": "completed", "conclusion": "failure"},
            {"name": "CodeQL", "status": "completed", "conclusion": "cancelled"}]
    assert tag_release.failing(runs) == (["image"], ["security (failure)", "CodeQL (cancelled)"])
