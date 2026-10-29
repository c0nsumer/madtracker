"""The packaging smoke test must pass here before it can mean anything in the exe."""

from madtracker.store import run_selftest


def test_selftest_passes(tmp_path):
    assert run_selftest(tmp_path) == []
    assert (tmp_path / "selftest.sqlite").exists()
    assert (tmp_path / "selftest-backup.sqlite").exists()


def test_selftest_reports_failures_instead_of_raising(tmp_path):
    # An unwritable directory is the likeliest packaging failure: wrong data folder.
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory")
    failures = run_selftest(blocker / "sub")
    assert failures and failures[0].startswith("open:")
