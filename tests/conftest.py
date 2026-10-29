"""Shared pytest setup.

Qt must run headless on Linux CI, on the Windows box without a second
display, and inside a plain terminal. Setting the platform plugin here,
before any Qt import, is what makes that true for every test file
without each one remembering to.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest  # noqa: E402 (after the platform is set)


@pytest.fixture(scope="session", autouse=True)
def _app_look(qapp):
    """Fusion, the light palette and the bundled font, once, before any widget.

    This is what main() does. It also keeps the suite off a Windows hang:
    switching the application style while hundreds of widgets from
    earlier tests are alive never returns there, so no test may be the
    first to apply the look mid-run.
    """
    from madtracker.ui.look import apply_look

    apply_look(qapp)


@pytest.fixture(autouse=True)
def _deferred_deletes(qapp):
    """Carry out each test's deleteLater calls when the test ends.

    The app runs an event loop, which deletes a widget soon after its
    deleteLater. A test mostly calls processEvents, which does not, so
    every rider card a surface ever replaced would stay queued until the
    first test that ran a real event loop: hundreds of thousands of
    widgets deleted at once, which reads as a hang in an unrelated
    scoreboard test on Windows.
    """
    yield
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture(autouse=True)
def _no_slow_disk_box(monkeypatch):
    """No test measures the disk, so no test sees the Slow Disk box uninvited.

    The app warns once a session when a commit takes longer than its
    threshold. A hosted CI runner stalls for seconds at times, and a
    test that clicks a card then gets a message box it never asked for
    and fails as though the click had misbehaved. A test of the warning
    itself lowers the threshold back.
    """
    from madtracker import app

    monkeypatch.setattr(app, "SLOW_COMMIT_MS", float("inf"))
