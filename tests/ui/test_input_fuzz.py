"""The input fuzzer, quick tier: the fixed corpus into every input of every screen and dialog.

Runs in the everyday suite. The deep tier (tests/test_fuzz_deep.py, the
``fuzz`` marker) adds seeded random mixes and scorer step sequences.
"""

import sys

import pytest
from apps import dispose_app
from fuzz_inputs import (
    CORPUS,
    FUZZED_CLASSES,
    NO_TEXT_INPUT,
    Escapes,
    every_dialog_class,
    make_controller,
    quiet_qt,
    run_duplicate_ruleset,
    run_screen,
    screens,
)

from madtracker import applog


@pytest.fixture(scope="module")
def fuzzed(qapp, tmp_path_factory):
    """One demo file for every screen, as one scorer's night: what one screen stored, the next sees."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        quiet_qt(monkeypatch)
        escapes = Escapes()
        monkeypatch.setattr(sys, "excepthook", escapes)
        c = make_controller(qapp, tmp_path_factory.mktemp("fuzz"))
        yield c, escapes
        dispose_app(c)
    applog.use_folder(None)


def test_every_dialog_with_text_input_is_fuzzed():
    """A dialog added later is fuzzed, or says here why it has nothing to type in."""
    missing = every_dialog_class() - FUZZED_CLASSES - set(NO_TEXT_INPUT)
    assert not missing, f"add these to tests/fuzz_inputs.py screens(): {sorted(missing)}"


@pytest.mark.parametrize(
    "screen",
    [
        "Edit Event",
        "New Event",
        "New Rider",
        "Edit Rider",
        "Edit Riders",
        "Choose Riders",
        "Merge Riders",
        "Import preview",
        "Add Race",
        # An unscored Madison: every field Edit race has, and Sprints and Teams.
        "Edit Madison",
        "Team",
        "New Group",
        "Rename group",
        "Settings",
        "New Ruleset",
        "Multi-Race Standings",
        "Multi-Race Standings by Place",
        "Multi-Race Standings Omnium",
        "Multi-Race Standings Four-Race",
    ],
)
def test_garbage_in_every_input_is_cleaned_or_refused_and_nothing_breaks(fuzzed, tmp_path, screen):
    c, escapes = fuzzed
    failures = run_screen(c, screens(c)[screen], CORPUS, tmp_path / "out", escapes)
    assert not failures, "\n".join(failures[:20])


def test_garbage_as_a_duplicated_rulesets_name(fuzzed):
    c, escapes = fuzzed
    failures = run_duplicate_ruleset(c, CORPUS, escapes)
    assert not failures, "\n".join(failures[:20])
