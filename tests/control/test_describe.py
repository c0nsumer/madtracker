"""Scorer actions read back in words."""

import pytest

from madtracker.control.describe import who
from madtracker.control.race import ordinal
from madtracker.control.roster import Entrant, EntryError, Roster, RosterBib

ROSTER = Roster(
    [
        Entrant(1, (7,), ("Maya Petrakis",)),
        Entrant(2, (12,), ("Tess Gallagher",)),
        Entrant(3, (33,), ("Jack Moreau",)),
    ]
)


def test_ordinals():
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 101, 111)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "101st", "111th",
    ]  # fmt: skip


def test_a_bib_in_text_carries_a_hash():
    assert who(12, "Tess Gallagher") == "#12 Tess Gallagher"
    assert who(None, "Tess Gallagher") == "Tess Gallagher"


def test_a_bib_worn_tonight_but_not_in_this_race_names_the_rider():
    roster = Roster(ROSTER.entrants, [RosterBib(51, 99, "Nora Lindqvist")])
    with pytest.raises(EntryError, match="^#51 Nora Lindqvist is not in this race$"):
        roster.resolve("51")
