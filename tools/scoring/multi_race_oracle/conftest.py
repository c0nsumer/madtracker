"""The suite's setup and its helpers, for the hand cases outside tests/.

The cases borrow the fixtures and race builders of
tests/control/test_multi_race.py, so they score races exactly as the
suite does. pytest loads tests/conftest.py only for files under tests/,
so its two autouse fixtures are repeated here: the look is applied once
before any widget, and each case's deferred deletes are carried out.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# tools/scoring/multi_race_oracle/ is three folders under the repo root.
REPO = Path(__file__).resolve().parents[3]
for sub in ("tests", "tests/control"):
    p = str(REPO / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import pytest  # noqa: E402

# The suite's store and riders fixtures, imported here so pytest finds
# them for every case in this folder.
from test_multi_race import riders, store  # noqa: E402, F401


@pytest.fixture(scope="session", autouse=True)
def _app_look(qapp):
    from madtracker.ui.look import apply_look

    apply_look(qapp)


@pytest.fixture(autouse=True)
def _deferred_deletes(qapp):
    yield
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
