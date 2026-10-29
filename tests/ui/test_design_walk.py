"""The acceptance walk: every screen in every state for every format, as docs/design.md says.

``WALK`` is the design, written down: for each format, the steps a
night takes and what the window must show after each (the state word,
the task line, the buttons that exist, the cards, the menus on a card
and on a result row, the board page, the Undo label). The walk asserts
exactly that. The sweep then clicks every visible control in every
state and fails on anything silent (principle 3): a click must change
what the scorer sees, open a menu or a dialog, or say why not.
"""

import itertools
from collections.abc import Callable
from dataclasses import dataclass, field, replace

import pytest
from apps import demo_data_dir, dispose_app
from logbook import event_log
from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QFileDialog

from madtracker.control import race as rc
from madtracker.dates import show_date
from madtracker.ui import cards, icons, widgets

DNS, DNF, GAIN, LOSE, DQ = (
    "Did Not Start",
    "Did Not Finish",
    "Gained a Lap",
    "Lost a Lap",
    "Disqualify",
)
MISHAP = "Out of the Finish (Mishap)"
WITHDRAWN = "Withdrawn"
PLACE_LAST = "Place Last"
REST = "Place the Rest Together"
PENALTY, NOT_COUNTED = "Points Penalty...", "Lap Not Counted"
UP, DOWN, TIE = "Move Up", "Move Down", "Tie with the Rider Above"
TIE_BELOW = "Tie with the Rider Below"
# While the race runs a row's ⋯ offers what the rider's card offers, less
# the staged moves and ties (section 7): a points race's
# rows take the format's lists below; a rider already placed in a chase (whose card
# goes done with the click) gets the laps and Disqualify after the row's moves,
# and an elimination's out or a win-and-out's lap winner Disqualify alone.
PLACED = [GAIN, LOSE, DQ]


def moves(first: int, last: int) -> list[str]:
    """The long moves a row offers: one per other place in its section."""
    return [f"Move to {rc.ordinal(n)}" for n in range(first, last + 1)]


CHASE, ELIMINATION, POINTS, MADISON, WIN_AND_OUT, MADISON_2, HANDICAP = range(7)
# The demo's Group B Unknown Distance, after the other added formats; the
# last row is Group B's Miss-and-Out.
UNKNOWN_DISTANCE = 11
TEMPO = 7

# The menus, section 5.
FILE_MENU = [
    "New Event...",
    "Open Event...",
    "Edit Riders...",
    "Export Program PDF...",
    "Export Results PDF...",
    "Export USAC CSV...",
    "Multi-Race Standings...",
    "Backup Now...",
    "Settings...",
    "New Data File...",
    "Open Data File...",
    "Quit",
]
SCOREBOARD_MENU = ["Automatic", "None", "Logo", "Live"]
HELP_MENU = [
    "Getting Started",
    "Scoring",
    "Results",
    "Multi-Race Standings",
    "Backups",
    "Demo Data File...",
    "Open Data Folder",
    "About MadTracker",
]


@dataclass(frozen=True)
class Expect:
    """What the surface shows in one state."""

    state: str
    task: str
    buttons: list[str]
    cards: int
    board: str
    undo: str
    undo_enabled: bool
    card_menu: list[str] | None = None
    row_menus: dict[int, list[str]] = field(default_factory=dict)
    status: str = ""
    headers_open: bool = False
    record_enabled: bool | None = None
    # The done cards' marks in bib order (a place, or a status's short
    # word), beside the ``cards`` that take a click; None leaves them
    # unchecked.
    done: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Step:
    do: Callable
    expect: Expect


def click(*tokens):
    def run(c):
        for token in tokens:
            eid = c.live.roster.resolve(token)
            assert c.click(eid), (token, c.main.surface.problem.text())

    return run


def record(c):
    """Record Sprint. The walk's sprints are short on purpose (two of six
    clicked, to keep the table small), so the app's question for a short
    sprint is answered Record here; the quiet fixture says No to
    every other question."""
    from madtracker.ui import icons

    was = icons.ask
    icons.ask = lambda *a, **k: True
    try:
        assert c.record_sprint()
    finally:
        icons.ask = was


def tie(token):
    """The card's "Tie with the Rider Above": a dead heat in the sprint being built."""

    def run(c):
        eid = c.live.roster.resolve(token)
        assert c.rider_action(eid, "tie_above"), c.main.surface.problem.text()

    return run


def move(token, key):
    """A badged card's Move Up, Move Down, or Move to Place: the staged order changes, one Undo."""

    def run(c):
        eid = c.live.roster.resolve(token)
        assert c.rider_action(eid, key), c.main.surface.problem.text()

    return run


def row_move(token, key):
    """A staged result row's ⋯ move, through the row's own door."""

    def run(c):
        eid = c.live.roster.resolve(token)
        assert c.row_action(eid, key), c.main.surface.problem.text()

    return run


def mishap(token):
    """The card's "Out of the finish (mishap)" on a rider in the final sprint.

    Through the controller: the app's question is answered No by the
    quiet fixture, as it is for every ask.
    """

    def run(c):
        eid = c.live.roster.resolve(token)
        assert c.live.act(eid, "out_of_finish").ok, c.main.surface.problem.text()
        c.refresh()

    return run


def withdraw(token, place):
    """The card's "Withdrawn" (USAC 2O3(e), 1M6(d)): the card goes done and the
    row keeps a numbered place after every rider still racing, with the
    note beside the name.

    Through the controller, as the mishap is: the quiet fixture answers
    the app's question No.
    """

    def run(c):
        eid = c.live.roster.resolve(token)
        assert c.live.act(eid, "withdrawn").ok, c.main.surface.problem.text()
        c.refresh()
        row = next(r for r in c.main.surface.table.screen.rows if r.entrant_id == eid)
        assert (row.place_text, row.note) == (place, "Withdrawn"), token

    return run


def status(token, key):
    """A status from the card's ⋯ (Did Not Finish and the rest), through the
    controller: the quiet fixture answers the app's question No."""

    def run(c):
        eid = c.live.roster.resolve(token)
        assert c.live.act(eid, key).ok, c.main.surface.problem.text()
        c.refresh()

    return run


def place_last(token):
    """The card's "Place Last": the officials know the last places before the bunch."""

    def run(c):
        eid = c.live.roster.resolve(token)
        assert c.rider_action(eid, "place_last"), c.main.surface.problem.text()

    return run


def ruling(token, key):
    """A ruling through the row's door, the key as the app records it (a
    penalty's with the dialog's number, the rider's whole penalty)."""

    def run(c):
        eid = c.live.roster.resolve(token)
        assert c.live.review(eid, key).ok, c.main.surface.problem.text()
        c.refresh()

    return run


def lap(token):
    """The card's +1: a lap gained, recorded at once."""

    def run(c):
        eid = c.live.roster.resolve(token)
        assert c.rider_action(eid, "lap_gained"), c.main.surface.problem.text()

    return run


def rest_together(c):
    assert c.place_rest_together(), c.main.surface.problem.text()


def undo(c):
    assert c.undo()


def mark_final(c):
    assert c.mark_final()


def reopen(c):
    assert c.reopen_race()


def nothing(c):
    pass


def set_bibs(**bibs):
    """The roster desk types (or empties, with None) these riders' bibs: ``set_bibs(b19=None)``.

    A rider is named by the bib the demo seeds them with, found through
    their name, so the step that puts a number back finds them too.
    """
    from madtracker.board import sample

    names = dict(sample.GROUP_A + sample.GROUP_B)

    def run(c):
        event_id = c.event.event_id
        for key, bib in bibs.items():
            first, last = names[key[1:]].split(" ", 1)
            rider = next(
                r for r in c.store.riders() if (r.first_name, r.last_name) == (first, last)
            )
            c.store.change_bib(event_id, rider.rider_id, bib)
        c.live.reload()
        c.refresh()

    return run


def undo_to_start(c):
    """Undo until nothing is left to undo: the race is back at its start list."""
    for _ in range(50):
        if not c.main.undo.isEnabled():
            break
        assert c.undo()


def add_team(color, *bibs):
    """Edit Event, the race's Edit..., Add Team..., Save, Score: a team joins the race.

    The race dialog opens unlocked, since no entry stands (section 6).
    """

    def run(c):
        by_bib = {e.bib: e.rider_id for e in c.store.entries(c.event.event_id)}
        race_id = c.live.race_id
        c.open_setup()
        setup = c.main.setup
        edit = setup.race_dialog(race_id)
        assert not edit.scored and edit.teams_box.isEnabled()
        assert edit.add_team(color, [by_bib[int(b)] for b in bibs]), edit.error.text()
        edit.exec = lambda: (edit.save(), edit.result())[1]
        setup.race_dialog = lambda _rid: edit
        try:
            assert setup.edit_race(race_id)
        finally:
            del setup.race_dialog
        c.close_setup()
        assert c.live.race_id == race_id

    return run


B_RIDERS = ["4", "7", "9", "12", "19", "22", "33", "38", "45", "51"]
A_RIDERS = ["3", "5", "8", "11", "14", "17", "21", "24", "27", "31", "36", "42"]
TEAMS = ["Blue", "Red", "Orange", "Yellow", "Black"]
# The first card's menu. Did not start stays while that rider has nothing
# recorded or staged, however far the race has gone; Out of the finish
# (mishap) is offered in the final sprint of a points race to a rider not
# yet placed in it, and Withdrawn to a rider not placed in the sprint or
# finish being clicked (USAC 2O3(e), 1M6(d)).
ALL_ACTIONS = [DNS, DNF, WITHDRAWN, GAIN, LOSE, DQ]
RUNNING_ACTIONS = [DNF, WITHDRAWN, GAIN, LOSE, DQ]
# A finish order being built offers Place Last first, as the tie is
# first in a sprint: it belongs to the task on screen.
CHASE_ACTIONS = [PLACE_LAST, *ALL_ACTIONS]
# The chase with 7 and 12 placed from the front and 51 from the back:
# Place the Rest Together's Undo brings it back exactly.
CHASE_BACK_MARKED = Expect(
    "Racing",
    "Click riders in the order they finish.",
    [REST],
    7,
    "pre_race",
    "Undo: #51 Hana Yoon placed 10th",
    True,
    CHASE_ACTIONS,
    {0: [DOWN, TIE_BELOW, *PLACED], 1: [UP, TIE, *PLACED], 2: PLACED},
    done=("1", "2", "10"),
)
# Two placed from the back as well: each moves within the back, where up
# is the better place, and Undo takes one move back.
CHASE_TWO_BACK = Expect(
    "Racing",
    "Click riders in the order they finish.",
    [REST],
    6,
    "pre_race",
    "Undo: #45 Isaac Pell placed 9th",
    True,
    CHASE_ACTIONS,
    {0: [DOWN, TIE_BELOW, *PLACED], 1: [UP, TIE, *PLACED], 2: [DOWN, *PLACED], 3: [UP, *PLACED]},
    done=("1", "2", "9", "10"),
)
FINAL_SPRINT_ALL = [DNS, DNF, MISHAP, WITHDRAWN, GAIN, LOSE, DQ]
FINAL_SPRINT_ACTIONS = [DNF, MISHAP, WITHDRAWN, GAIN, LOSE, DQ]
# Laps count in a points race, a madison and a chase, not in an
# elimination or a win-and-out (section 7).
NO_LAP_ALL = [DNS, DNF, DQ]
NO_LAP_RUNNING = [DNF, DQ]
# A Points Race or Madison has points to take (USAC 8D5(b)), so its card
# offers Points Penalty... too, and Lap Not Counted once a lap gained
# stands (sections 7 and 8).
POINTS_ALL = [DNS, DNF, WITHDRAWN, GAIN, LOSE, PENALTY, DQ]
POINTS_RUNNING = [DNF, WITHDRAWN, GAIN, LOSE, PENALTY, DQ]
POINTS_FINAL = [DNF, MISHAP, WITHDRAWN, GAIN, LOSE, PENALTY, DQ]
LAPPED_RUNNING = [DNF, WITHDRAWN, GAIN, LOSE, PENALTY, NOT_COUNTED, DQ]
LAPPED_FINAL = [DNF, MISHAP, WITHDRAWN, GAIN, LOSE, PENALTY, NOT_COUNTED, DQ]
# A rider with a staged place crossed the line of the sprint or finish
# being clicked, so neither the mishap nor Withdrawn is offered.
POINTS_BADGED = [DNF, GAIN, LOSE, PENALTY, DQ]
LAPPED_BADGED = [DNF, GAIN, LOSE, PENALTY, NOT_COUNTED, DQ]
# Sprint 1 of the points race with 12 then 7 clicked; the first card (4)
# has no badge, so its menu is the plain one.
POINTS_TWO_BADGED = Expect(
    "Racing",
    "Sprint 1: click the first 6 riders in order, then Record Sprint.",
    ["Record Sprint"],
    10,
    "pre_race",
    "Undo: #7 Maya Petrakis placed 2nd",
    True,
    POINTS_ALL,
    {0: POINTS_ALL},
    record_enabled=True,
)
# The first card badged 3rd behind two others: its menu starts with the
# moves (no Move Down from the last place), the long moves, and the tie;
# a staged place is a result, so Did Not Start goes.
POINTS_THREE_BADGED = Expect(
    "Racing",
    "Sprint 1: click the first 6 riders in order, then Record Sprint.",
    ["Record Sprint"],
    10,
    "pre_race",
    "Undo: #4 Corey Abernathy placed 3rd",
    True,
    [UP, "Move to 1st", "Move to 2nd", TIE, *POINTS_BADGED],
    {0: POINTS_BADGED},
    record_enabled=True,
)
# 12 and 7 tied for 1st, then 4 placed 3rd behind them: two groups, so the
# card has Move Up and the tie, no long moves.
POINTS_TIED_THEN_ONE = Expect(
    "Racing",
    "Sprint 1: click the first 6 riders in order, then Record Sprint.",
    ["Record Sprint"],
    10,
    "pre_race",
    "Undo: #4 Corey Abernathy placed 3rd",
    True,
    [UP, TIE, *POINTS_BADGED],
    {0: POINTS_BADGED},
    record_enabled=True,
)
# 12 and 7 tied for 1st; the first card is not in the tie.
POINTS_TIED = Expect(
    "Racing",
    "Sprint 1: click the first 6 riders in order, then Record Sprint.",
    ["Record Sprint"],
    10,
    "pre_race",
    rc.undo_tied("#7 Maya Petrakis", "#12 Tess Gallagher"),
    True,
    POINTS_ALL,
    {0: POINTS_ALL},
    record_enabled=True,
)
# Sprint 1 recorded, Sprint 2 not yet clicked.
POINTS_SPRINT_2 = Expect(
    "Racing",
    "Sprint 2: click the first 6 riders in order, then Record Sprint.",
    ["Record Sprint"],
    10,
    "sprint_points",
    "Undo: Sprint 1 recorded",
    True,
    POINTS_ALL,
    {0: POINTS_RUNNING},
    record_enabled=False,
    headers_open=True,
    done=(),
)
POINTS_SPRINT_2_DNF = replace(
    POINTS_SPRINT_2,
    cards=9,
    undo="Undo: #38 Rosa Navarro marked Did Not Finish",
    done=("DNF",),
)

WALK: dict[str, tuple[int, list[Step]]] = {
    "chase": (
        CHASE,
        [
            Step(
                nothing,
                Expect(
                    "Start list",
                    "Click riders in the order they finish.",
                    [],
                    10,
                    "pre_race",
                    rc.NOTHING_TO_UNDO_LABEL,
                    False,
                    CHASE_ACTIONS,
                ),  # fmt: skip
            ),
            Step(
                click("7"),
                Expect(
                    "Racing",
                    "Click riders in the order they finish.",
                    [REST],
                    9,
                    "pre_race",
                    "Undo: #7 Maya Petrakis placed 1st",
                    True,
                    CHASE_ACTIONS,
                    {0: PLACED},
                ),  # fmt: skip
            ),
            Step(
                click("12"),
                Expect(
                    "Racing",
                    "Click riders in the order they finish.",
                    [REST],
                    8,
                    "pre_race",
                    "Undo: #12 Tess Gallagher placed 2nd",
                    True,
                    CHASE_ACTIONS,
                    {0: [DOWN, TIE_BELOW, *PLACED], 1: [UP, TIE, *PLACED]},
                    # Each placed card holds its slot, its place in the badge.
                    done=("1", "2"),
                ),  # fmt: skip
            ),
            # The last place is known early: it goes in from the back,
            # numbered from the field left, and its card goes done.
            Step(place_last("51"), CHASE_BACK_MARKED),
            Step(place_last("45"), CHASE_TWO_BACK),
            # A move at the back swaps 9th and 10th.
            Step(
                row_move("45", "move_down"),
                Expect(
                    "Racing",
                    "Click riders in the order they finish.",
                    [REST],
                    6,
                    "pre_race",
                    rc.undo_moved("#45 Isaac Pell", "down"),
                    True,
                    CHASE_ACTIONS,
                    {
                        0: [DOWN, TIE_BELOW, *PLACED],
                        1: [UP, TIE, *PLACED],
                        2: [DOWN, *PLACED],
                        3: [UP, *PLACED],
                    },
                ),  # fmt: skip
            ),
            Step(undo, CHASE_TWO_BACK),
            Step(undo, CHASE_BACK_MARKED),
            # The bunch in the middle takes one equal placing (USAC 1M6(a)):
            # seven riders share 3rd, in bib order, and 10th stays 10th.
            Step(
                rest_together,
                Expect(
                    "Provisional",
                    rc.REVIEW_TEXT,
                    ["Mark Final"],
                    0,
                    "finish",
                    rc.UNDO_REST,
                    True,
                    None,
                    {
                        0: [DOWN, "Move to 2nd", "Move to 9th", "Move to 10th", TIE_BELOW, DQ],
                        2: [UP, DOWN, "Move to 1st", "Move to 2nd", "Move to 9th", TIE, DQ],
                        3: [UP, DOWN, "Move to 1st", "Move to 2nd", "Move to 9th", DQ],
                        9: [UP, *moves(1, 3), TIE, DQ],
                    },
                    "Provisional",
                ),  # fmt: skip
            ),
            # Undo of that finish puts the front and the back back as they were.
            Step(undo, CHASE_BACK_MARKED),
            Step(
                click("33", "4", "22", "9", "19", "45", "38"),
                Expect(
                    "Provisional",
                    rc.REVIEW_TEXT,
                    ["Mark Final"],
                    0,
                    "finish",
                    "Undo: #38 Rosa Navarro placed 9th",
                    True,
                    None,
                    {
                        0: [DOWN, *moves(2, 10), TIE_BELOW, DQ],
                        1: [UP, DOWN, "Move to 1st", *moves(3, 10), TIE, TIE_BELOW, DQ],
                        9: [UP, *moves(1, 9), TIE, DQ],
                    },
                    "Provisional",
                ),  # fmt: skip
            ),
            Step(
                mark_final,
                Expect(
                    "Final",
                    rc.FINAL_TEXT,
                    ["Reopen"],
                    0,
                    "finish",
                    rc.REOPEN_FIRST,
                    False,
                    None,
                    {0: [], 5: []},
                    "Final",
                ),  # fmt: skip
            ),
            Step(
                reopen,
                Expect(
                    "Provisional",
                    rc.REVIEW_TEXT,
                    ["Mark Final"],
                    0,
                    "finish",
                    "Undo: #38 Rosa Navarro placed 9th",
                    True,
                    None,
                    {0: [DOWN, *moves(2, 10), TIE_BELOW, DQ]},
                    "Provisional",
                ),  # fmt: skip
            ),
        ],
    ),
    "elimination": (
        ELIMINATION,
        [
            Step(
                nothing,
                Expect(
                    "Start list",
                    "Click the rider who is out.",
                    [],
                    12,
                    "pre_race",
                    rc.NOTHING_TO_UNDO_LABEL,
                    False,
                    NO_LAP_ALL,
                ),  # fmt: skip
            ),
            Step(
                click("42"),
                Expect(
                    "Racing",
                    "Click the rider who is out.",
                    [],
                    11,
                    "elimination",
                    "Undo: #42 Eli Brandt marked Eliminated",
                    True,
                    NO_LAP_ALL,
                    {0: [DQ]},
                    done=("12",),
                ),  # fmt: skip
            ),
            Step(
                # The third bell: each out keeps a done card in bib order,
                # numbered with the place the out took.
                click("17", "31"),
                Expect(
                    "Racing",
                    "Click the rider who is out.",
                    [],
                    9,
                    "elimination",
                    "Undo: #31 Ray Duchene marked Eliminated",
                    True,
                    NO_LAP_ALL,
                    done=("11", "10", "12"),
                ),  # fmt: skip
            ),
            Step(
                click("8", "36", "27", "21", "14", "11", "5"),
                Expect(
                    "Final sprint",
                    "Click the winner.",
                    [],
                    2,
                    "elimination",
                    "Undo: #5 Priya Okafor marked Eliminated",
                    True,
                    NO_LAP_ALL,
                    # The outs move while the race runs: the last out (3rd)
                    # down, the first out (12th) up or into the bell above.
                    {0: [DOWN, *moves(4, 12), TIE_BELOW, DQ], 9: [UP, *moves(3, 11), TIE, DQ]},
                    done=("3", "9", "4", "5", "11", "6", "7", "10", "8", "12"),
                ),  # fmt: skip
            ),
            Step(
                click("24"),
                Expect(
                    "Provisional",
                    rc.REVIEW_TEXT,
                    ["Mark Final"],
                    0,
                    "finish",
                    "Undo: Final sprint recorded",
                    True,
                    None,
                    {
                        0: [DOWN, TIE_BELOW, DQ],
                        1: [UP, TIE, DQ],
                        2: [DOWN, *moves(4, 12), TIE_BELOW, DQ],
                        11: [UP, *moves(3, 11), TIE, DQ],
                    },  # fmt: skip
                    "Provisional",
                ),  # fmt: skip
            ),
            Step(
                mark_final,
                Expect(
                    "Final",
                    rc.FINAL_TEXT,
                    ["Reopen"],
                    0,
                    "finish",
                    rc.REOPEN_FIRST,
                    False,
                    None,
                    {0: []},
                    "Final",
                ),  # fmt: skip
            ),
        ],
    ),
    "points": (
        POINTS,
        [
            Step(
                nothing,
                Expect(
                    "Start list",
                    "Sprint 1: click the first 6 riders in order, then Record Sprint.",
                    ["Record Sprint"],
                    10,
                    "pre_race",
                    rc.NOTHING_TO_UNDO_LABEL,
                    False,
                    POINTS_ALL,
                    {0: POINTS_ALL},
                    record_enabled=False,
                ),  # fmt: skip
            ),
            Step(click("12", "7"), POINTS_TWO_BADGED),
            Step(click("4"), POINTS_THREE_BADGED),
            # Move Up on 3rd: 2nd now, with a move each way and Undo Move.
            Step(
                move("4", "move_up"),
                Expect(
                    "Racing",
                    "Sprint 1: click the first 6 riders in order, then Record Sprint.",
                    ["Record Sprint"],
                    10,
                    "pre_race",
                    rc.undo_moved("#4 Corey Abernathy", "up"),
                    True,
                    [UP, DOWN, "Move to 1st", "Move to 3rd", TIE, TIE_BELOW, *POINTS_BADGED],
                    {0: POINTS_BADGED},
                    record_enabled=True,
                ),  # fmt: skip
            ),
            Step(undo, POINTS_THREE_BADGED),
            Step(undo, POINTS_TWO_BADGED),
            Step(tie("7"), POINTS_TIED),
            # A third rider tied in: the first card shares the badge, so its
            # Move Up reads Break Tie on the menu (checked in check()).
            Step(
                lambda c: (click("4")(c), tie("4")(c)),
                Expect(
                    "Racing",
                    "Sprint 1: click the first 6 riders in order, then Record Sprint.",
                    ["Record Sprint"],
                    10,
                    "pre_race",
                    rc.undo_tied("#4 Corey Abernathy", "#12 Tess Gallagher"),
                    True,
                    [UP, DOWN, *POINTS_BADGED],
                    {0: POINTS_BADGED},
                    record_enabled=True,
                ),  # fmt: skip
            ),
            Step(undo, POINTS_TIED_THEN_ONE),
            Step(undo, POINTS_TIED),
            Step(record, POINTS_SPRINT_2),
            Step(
                # A rider out mid-race keeps a done card with the status's
                # short word; Undo turns it live in the same slot.
                status("38", "dnf"),
                POINTS_SPRINT_2_DNF,
            ),
            Step(undo, POINTS_SPRINT_2),
            Step(
                # A lap gained (the card's +1): the lap is a result, so Did not
                # start goes, and Lap Not Counted comes while the lap stands.
                lap("4"),
                Expect(
                    "Racing",
                    "Sprint 2: click the first 6 riders in order, then Record Sprint.",
                    ["Record Sprint"],
                    10,
                    "sprint_points",
                    "Undo: #4 Corey Abernathy gained a lap",
                    True,
                    LAPPED_RUNNING,
                    {0: LAPPED_RUNNING},
                    record_enabled=False,
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                lambda c: (click("7", "12")(c), record(c)),
                Expect(
                    "Final sprint",
                    "Final sprint: click every rider in order.",
                    [],
                    10,
                    "sprint_points",
                    "Undo: Sprint 2 recorded",
                    True,
                    LAPPED_FINAL,
                    {0: POINTS_FINAL},
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                # Placed in the final sprint: neither Did not start nor the mishap.
                click("4"),
                Expect(
                    "Final sprint",
                    "Final sprint: click every rider in order.",
                    [],
                    10,
                    "sprint_points",
                    "Undo: #4 Corey Abernathy placed 1st",
                    True,
                    LAPPED_BADGED,
                    {0: POINTS_FINAL},
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                # A mishap in the last kilometer (USAC 2M7(b)): the card goes done
                # and the finish completes without the rider.
                mishap("7"),
                Expect(
                    "Final sprint",
                    "Final sprint: click every rider in order.",
                    [],
                    9,
                    "sprint_points",
                    "Undo: #7 Maya Petrakis marked Out of the Finish (Mishap)",
                    True,
                    LAPPED_BADGED,
                    {0: []},
                    headers_open=True,
                    done=("Mishap",),
                ),  # fmt: skip
            ),
            Step(
                click(*[b for b in B_RIDERS if b not in ("4", "7")]),
                Expect(
                    "Provisional",
                    rc.REVIEW_TEXT,
                    ["Mark Final"],
                    0,
                    "sprint_points",
                    "Undo: #51 Hana Yoon placed 9th",
                    True,
                    None,
                    # The leader took the lap: its row may give it back.
                    {0: [PENALTY, NOT_COUNTED, DQ], 9: [PENALTY, DQ]},
                    "Provisional",
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                # The officials take a point from the leader after a protest:
                # the row's Points Penalty... sets the penalty to 1.
                ruling("4", "points_penalty:1"),
                Expect(
                    "Provisional",
                    rc.REVIEW_TEXT,
                    ["Mark Final"],
                    0,
                    "sprint_points",
                    "Undo: #4 Corey Abernathy penalty set to 1",
                    True,
                    None,
                    {0: [PENALTY, NOT_COUNTED, DQ], 9: [PENALTY, DQ]},
                    "Provisional",
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                # Set to 0, the penalty is off, as an entry of its own, without
                # unwinding anything recorded since; Undo puts the 1 back.
                ruling("4", "points_penalty:0"),
                Expect(
                    "Provisional",
                    rc.REVIEW_TEXT,
                    ["Mark Final"],
                    0,
                    "sprint_points",
                    "Undo: #4 Corey Abernathy penalty set to 0",
                    True,
                    None,
                    {0: [PENALTY, NOT_COUNTED, DQ], 9: [PENALTY, DQ]},
                    "Provisional",
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                undo,
                Expect(
                    "Provisional",
                    rc.REVIEW_TEXT,
                    ["Mark Final"],
                    0,
                    "sprint_points",
                    "Undo: #4 Corey Abernathy penalty set to 1",
                    True,
                    None,
                    {0: [PENALTY, NOT_COUNTED, DQ], 9: [PENALTY, DQ]},
                    "Provisional",
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                undo,
                Expect(
                    "Provisional",
                    rc.REVIEW_TEXT,
                    ["Mark Final"],
                    0,
                    "sprint_points",
                    "Undo: #51 Hana Yoon placed 9th",
                    True,
                    None,
                    {0: [PENALTY, NOT_COUNTED, DQ], 9: [PENALTY, DQ]},
                    "Provisional",
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                lambda c: c.reopen_sprint(1),
                Expect(
                    "Provisional",
                    "Correcting Sprint 1: click the first 6 riders in order, then Record Sprint.",
                    ["Cancel", "Record Sprint"],
                    10,
                    "sprint_points",
                    "Undo: #7 Maya Petrakis placed 1st",
                    True,
                    [],
                    {0: []},
                    "Provisional",
                    record_enabled=True,
                ),  # fmt: skip
            ),
            Step(
                lambda c: c.main.surface.cancel_button.click(),
                Expect(
                    "Provisional",
                    rc.REVIEW_TEXT,
                    ["Mark Final"],
                    0,
                    "sprint_points",
                    "Undo: #51 Hana Yoon placed 9th",
                    True,
                    None,
                    {0: [PENALTY, NOT_COUNTED, DQ]},
                    "Provisional",
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                mark_final,
                Expect(
                    "Final",
                    rc.FINAL_TEXT,
                    ["Reopen"],
                    0,
                    "sprint_points",
                    rc.REOPEN_FIRST,
                    False,
                    None,
                    {0: []},
                    "Final",
                ),  # fmt: skip
            ),
        ],
    ),
    "madison": (
        MADISON,
        [
            Step(
                nothing,
                Expect(
                    "Start list",
                    "Sprint 1: click the first 4 teams in order, then Record Sprint.",
                    ["Record Sprint"],
                    5,
                    "pre_race",
                    rc.NOTHING_TO_UNDO_LABEL,
                    False,
                    POINTS_ALL,
                    {0: POINTS_ALL},
                    record_enabled=False,
                ),  # fmt: skip
            ),
            Step(
                lambda c: (click("Blue", "Red")(c), tie("Red")(c)),
                Expect(
                    "Racing",
                    "Sprint 1: click the first 4 teams in order, then Record Sprint.",
                    ["Record Sprint"],
                    5,
                    "pre_race",
                    rc.undo_tied("Red", "Blue"),
                    True,
                    [UP, DOWN, *POINTS_BADGED],
                    {0: POINTS_BADGED},
                    record_enabled=True,
                ),  # fmt: skip
            ),
            Step(
                record,
                Expect(
                    "Racing",
                    "Sprint 2: click the first 4 teams in order, then Record Sprint.",
                    ["Record Sprint"],
                    5,
                    "madison",
                    "Undo: Sprint 1 recorded",
                    True,
                    POINTS_RUNNING,
                    {0: POINTS_RUNNING},
                    record_enabled=False,
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                lambda c: (click("Red", "Orange")(c), record(c), click("Orange")(c), record(c)),
                Expect(
                    "Final sprint",
                    "Final sprint: click every team in order.",
                    [],
                    5,
                    "madison",
                    "Undo: Sprint 3 recorded",
                    True,
                    POINTS_FINAL,
                    {0: POINTS_FINAL},
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                mishap("Black"),
                Expect(
                    "Final sprint",
                    "Final sprint: click every team in order.",
                    [],
                    4,
                    "madison",
                    "Undo: Black marked Out of the Finish (Mishap)",
                    True,
                    POINTS_FINAL,
                    {0: POINTS_FINAL},
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                click(*[t for t in TEAMS if t != "Black"]),
                Expect(
                    "Provisional",
                    rc.REVIEW_TEXT,
                    ["Mark Final"],
                    0,
                    "madison",
                    "Undo: Yellow placed 4th",
                    True,
                    None,
                    {0: [PENALTY, DQ]},
                    "Provisional",
                    headers_open=True,
                ),  # fmt: skip
            ),
            Step(
                mark_final,
                Expect(
                    "Final",
                    rc.FINAL_TEXT,
                    ["Reopen"],
                    0,
                    "madison",
                    rc.REOPEN_FIRST,
                    False,
                    None,
                    {0: []},
                    "Final",
                ),  # fmt: skip
            ),
        ],
    ),
    "win_and_out": (
        WIN_AND_OUT,
        [
            Step(
                nothing,
                Expect(
                    "Start list",
                    "Lap 1: click the winner.",
                    [],
                    10,
                    "pre_race",
                    rc.NOTHING_TO_UNDO_LABEL,
                    False,
                    NO_LAP_ALL,
                ),  # fmt: skip
            ),
            Step(
                click("7"),
                Expect(
                    "Racing",
                    "Lap 2: click the winner.",
                    [],
                    9,
                    "finish",
                    "Undo: #7 Maya Petrakis won Lap 1",
                    True,
                    NO_LAP_ALL,
                    {0: [DQ]},
                    done=("1",),
                ),  # fmt: skip
            ),
            Step(
                click("12", "33", "4", "22"),
                Expect(
                    "Final sprint",
                    "Click the rest in the order they finish.",
                    [],
                    5,
                    "finish",
                    "Undo: #22 Lena Fischer won Lap 5",
                    True,
                    NO_LAP_ALL,
                    {4: [DQ]},
                ),  # fmt: skip
            ),
            Step(
                click("9"),
                Expect(
                    "Final sprint",
                    "Click the rest in the order they finish.",
                    [],
                    4,
                    "finish",
                    "Undo: #9 Ben Szymanski placed 6th",
                    True,
                    NO_LAP_ALL,
                    {5: [DQ]},
                ),  # fmt: skip
            ),
            Step(
                click("19", "38", "45", "51"),
                Expect(
                    "Provisional",
                    rc.REVIEW_TEXT,
                    ["Mark Final"],
                    0,
                    "finish",
                    "Undo: #51 Hana Yoon placed 10th",
                    True,
                    None,
                    {
                        # Lap winners swap one step at a time; the fill
                        # moves like a finish order.
                        0: [DOWN, DQ],
                        1: [UP, DOWN, DQ],
                        4: [UP, DQ],
                        5: [DOWN, *moves(7, 10), TIE_BELOW, DQ],
                        6: [UP, DOWN, "Move to 6th", *moves(8, 10), TIE, TIE_BELOW, DQ],
                        9: [UP, *moves(6, 9), TIE, DQ],
                    },
                    "Provisional",
                ),  # fmt: skip
            ),
            Step(
                mark_final,
                Expect(
                    "Final",
                    rc.FINAL_TEXT,
                    ["Reopen"],
                    0,
                    "finish",
                    rc.REOPEN_FIRST,
                    False,
                    None,
                    {0: []},
                    "Final",
                ),  # fmt: skip
            ),
        ],
    ),
}
# USAC 2D5: after the start a handicap is run as a scratch race, so it
# shows the scratch race's screens in every state.
WALK["handicap"] = (HANDICAP, WALK["chase"][1])
# An unknown distance is a scratch race whose length the riders learn at
# the bell; the scorer clicks the same finish order.
WALK["unknown_distance"] = (UNKNOWN_DISTANCE, WALK["chase"][1])


def survivors(n):
    """The race's own rules ride to ``n`` survivors (USAC 2E5), so the final sprint is a finish order."""

    def run(c):
        race = c.store.race(c.live.race_id)
        c.store.update_race(race.race_id, rules={**race.rules, "survivors": n})
        c.live.reload()
        c.refresh()

    return run


ELIMINATION_THREE_LEFT = Expect(
    "Final sprint",
    "Final sprint: click riders in the order they finish.",
    [],
    3,
    "elimination",
    "Undo: #11 Jenna Whitfield marked Eliminated",
    True,
    NO_LAP_ALL,
    done=("9", "4", "5", "11", "6", "7", "10", "8", "12"),
)
# Ridden to three survivors, the final sprint places them one click at a
# time: a placed survivor's card goes done beside the outs' while the
# other two still take a click.
WALK["elimination final sprint"] = (
    ELIMINATION,
    [
        Step(
            survivors(3),
            Expect(
                "Start list",
                "Click the rider who is out.",
                [],
                12,
                "pre_race",
                rc.NOTHING_TO_UNDO_LABEL,
                False,
                NO_LAP_ALL,
                done=(),
            ),  # fmt: skip
        ),
        Step(click("42", "17", "31", "8", "36", "27", "21", "14", "11"), ELIMINATION_THREE_LEFT),
        Step(
            click("24"),
            replace(
                ELIMINATION_THREE_LEFT,
                cards=2,
                undo="Undo: #24 Kenji Mori placed 1st",
                row_menus={0: [DQ]},
                done=("9", "4", "5", "11", "6", "1", "7", "10", "8", "12"),
            ),
        ),
        Step(undo, ELIMINATION_THREE_LEFT),
    ],
)

# A withdrawn rider leaves the cards and ranks after every rider still
# racing, the later withdrawn higher (USAC 2O3(e)): the row has no menu
# while the race runs, nothing moves into or past it, and once the result
# is complete it takes the rulings and Disqualify.
WALK["scratch race withdrawn"] = (
    CHASE,
    [
        Step(click("7"), WALK["chase"][1][1].expect),
        Step(
            withdraw("45", "10"),
            Expect(
                "Racing",
                "Click riders in the order they finish.",
                [REST],
                8,
                "pre_race",
                "Undo: #45 Isaac Pell marked Withdrawn",
                True,
                CHASE_ACTIONS,
                {0: PLACED, 1: []},
            ),  # fmt: skip
        ),
        Step(
            withdraw("51", "9"),
            Expect(
                "Racing",
                "Click riders in the order they finish.",
                [REST],
                7,
                "pre_race",
                "Undo: #51 Hana Yoon marked Withdrawn",
                True,
                CHASE_ACTIONS,
                {0: PLACED, 1: [], 2: []},
            ),  # fmt: skip
        ),
        Step(
            click("4", "9", "12", "19", "22", "33", "38"),
            Expect(
                "Provisional",
                rc.REVIEW_TEXT,
                ["Mark Final"],
                0,
                "finish",
                "Undo: #38 Rosa Navarro placed 8th",
                True,
                None,
                {
                    0: [DOWN, *moves(2, 8), TIE_BELOW, DQ],
                    7: [UP, *moves(1, 7), TIE, DQ],
                    8: [DQ],
                    9: [DQ],
                },
                "Provisional",
            ),  # fmt: skip
        ),
    ],
)
WALK["tempo race withdrawn"] = (
    TEMPO,
    [
        Step(
            lambda c: (click("7")(c), record(c)),
            Expect(
                "Racing",
                "Sprint 2: click the winner, then Record Sprint.",
                ["Record Sprint"],
                10,
                "sprint_points",
                "Undo: Sprint 1 recorded",
                True,
                POINTS_ALL,
                {0: POINTS_RUNNING},
                record_enabled=False,
                headers_open=True,
            ),  # fmt: skip
        ),
        Step(
            withdraw("45", "10"),
            Expect(
                "Racing",
                "Sprint 2: click the winner, then Record Sprint.",
                ["Record Sprint"],
                9,
                "sprint_points",
                "Undo: #45 Isaac Pell marked Withdrawn",
                True,
                POINTS_ALL,
                {0: POINTS_RUNNING, 9: []},
                record_enabled=False,
                headers_open=True,
            ),  # fmt: skip
        ),
        Step(
            lambda c: (click("12")(c), record(c)),
            Expect(
                "Final sprint",
                "Final sprint: click every rider in order.",
                [],
                9,
                "sprint_points",
                "Undo: Sprint 2 recorded",
                True,
                [DNS, *POINTS_FINAL],
                {0: POINTS_FINAL, 9: []},
                headers_open=True,
            ),  # fmt: skip
        ),
        Step(
            withdraw("51", "9"),
            Expect(
                "Final sprint",
                "Final sprint: click every rider in order.",
                [],
                8,
                "sprint_points",
                "Undo: #51 Hana Yoon marked Withdrawn",
                True,
                [DNS, *POINTS_FINAL],
                {0: POINTS_FINAL, 8: [], 9: []},
                headers_open=True,
            ),  # fmt: skip
        ),
        Step(
            click("4", "7", "9", "12", "19", "22", "33", "38"),
            Expect(
                "Provisional",
                rc.REVIEW_TEXT,
                ["Mark Final"],
                0,
                "sprint_points",
                "Undo: #38 Rosa Navarro placed 8th",
                True,
                None,
                {0: [PENALTY, DQ], 8: [PENALTY, DQ], 9: [PENALTY, DQ]},
                "Provisional",
                headers_open=True,
            ),  # fmt: skip
        ),
    ],
)

# A bib is required to score, never to register (section 6): a field with
# a rider still waiting for one, or a number twice, waits on the start
# list with the refusal as its task, and scores as usual once fixed.
# A Madison scored, undone to its start list, and given a sixth team in
# Edit Event (section 6: an entry Undo took back is no entry), then
# scored on with the new team.
MADISON_START = WALK["madison"][1][0].expect
WALK["madison undone to its start"] = (
    MADISON,
    [
        Step(lambda c: (click("Blue", "Red")(c), record(c)), WALK["madison"][1][2].expect),
        Step(undo_to_start, MADISON_START),
        Step(add_team("Green", "17", "42"), replace(MADISON_START, cards=6)),
        Step(
            click("Green"),
            Expect(
                "Racing",
                "Sprint 1: click the first 4 teams in order, then Record Sprint.",
                ["Record Sprint"],
                6,
                "pre_race",
                "Undo: Green placed 1st",
                True,
                POINTS_ALL,
                {0: POINTS_ALL, 5: POINTS_BADGED},
                record_enabled=True,
            ),  # fmt: skip
        ),
    ],
)
WALK["chase without bibs"] = (
    CHASE,
    [
        Step(
            set_bibs(b45=None, b51=None),
            Expect(
                "Start list",
                "2 riders have no bib. Edit Event > Roster.",
                [],
                10,
                "pre_race",
                rc.NOTHING_TO_UNDO_LABEL,
                False,
                [],
            ),  # fmt: skip
        ),
        Step(set_bibs(b45=45, b51=51), WALK["chase"][1][0].expect),
    ],
)
WALK["chase with a bib twice"] = (
    CHASE,
    [
        Step(
            set_bibs(b51=45),
            Expect(
                "Start list",
                "Bib 45 is worn by two riders in this race. Edit Event > Roster.",
                [],
                10,
                "pre_race",
                rc.NOTHING_TO_UNDO_LABEL,
                False,
                [],
            ),  # fmt: skip
        ),
        Step(set_bibs(b45=51), WALK["chase"][1][0].expect),
    ],
)
WALK["points without a bib"] = (
    POINTS,
    [
        Step(
            set_bibs(b45=None),
            Expect(
                "Start list",
                "1 rider has no bib. Edit Event > Roster.",
                ["Record Sprint"],
                10,
                "pre_race",
                rc.NOTHING_TO_UNDO_LABEL,
                False,
                [],
                {0: []},
                record_enabled=False,
            ),  # fmt: skip
        ),
        Step(set_bibs(b45=45), WALK["points"][1][0].expect),
    ],
)


@pytest.fixture
def quiet(monkeypatch):
    """Every dialog and menu records itself instead of blocking; file pickers pick nothing."""
    opened: list[str] = []
    monkeypatch.setattr(widgets, "run_menu", lambda menu, where: opened.append("menu:" + ",".join(x.text() for x in menu.actions())))  # fmt: skip
    monkeypatch.setattr(QDialog, "exec", lambda self: opened.append("dialog:" + self.windowTitle()) or int(QDialog.DialogCode.Rejected))  # fmt: skip

    def picker(kind, result):
        return staticmethod(lambda *a, **k: opened.append(kind) or result)

    monkeypatch.setattr(QFileDialog, "getOpenFileName", picker("file", ("", "")))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", picker("file", ("", "")))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", picker("folder", ""))
    monkeypatch.setattr(icons, "ask", lambda *a, **k: opened.append("ask:" + a[1]) or False)
    monkeypatch.setattr(icons, "choose", lambda *a, **k: opened.append("choose:" + a[1]) and None)
    monkeypatch.setattr(icons, "inform", lambda *a, **k: opened.append("inform:" + a[1]))
    monkeypatch.setattr(icons, "warn", lambda *a, **k: opened.append("warn:" + a[1]))
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: opened.append("browse:" + url.toLocalFile()) or True))  # fmt: skip
    return opened


@pytest.fixture
def make_app(qapp, tmp_path, quiet):
    from madtracker.app import AppController

    made = []
    numbers = itertools.count()

    def build():
        n = next(numbers)
        settings = QSettings(str(tmp_path / f"s{n}.ini"), QSettings.Format.IniFormat)
        c = AppController(qapp, settings=settings, data_dir=demo_data_dir(tmp_path, n))
        c.main.resize(1600, 900)
        made.append(c)
        return c

    def dispose(c):
        # A walk rebuilds the app many times; each one let go as the next
        # is made keeps one in memory, not every one to the end of the test.
        dispose_app(c)
        made.remove(c)

    build.dispose = dispose
    yield build
    for c in made:
        dispose_app(c)


@pytest.fixture
def app(make_app):
    return make_app()


def select(c, row: int) -> None:
    c.select_race(c.races[row].race_id)


def check(c, expect: Expect, where: str) -> None:
    win = c.main
    s = win.surface
    assert win.showing() == "surface", where
    assert s.state.text() == expect.state, where
    assert s.task.text() == expect.task, where
    assert s.visible_buttons() == expect.buttons, where
    if expect.record_enabled is not None:
        assert s.record_button.isEnabled() == expect.record_enabled, where
    # The cards that take a click: a done card holds its slot in the grid.
    cards = [w for w in s.cards.cards if not w.card.done]
    assert len(cards) == expect.cards, where
    done = [w for w in s.cards.cards if w.card.done]
    if expect.done is not None:
        assert tuple(w.badge_text() for w in done) == expect.done, where
    for w in done:
        # Gray, no laps, the arrow, and a ⋯ only where its row has a menu.
        assert w.property("done") is True and w.chip_rect() is None, where
        assert not w.lap_up.isVisibleTo(s) and not w.lap_down.isVisibleTo(s), where
        assert w.cursor().shape() == Qt.CursorShape.ArrowCursor, where
        assert w.dots.isVisibleTo(s) == bool(w.menu_actions), where
        assert w.toolTip() == w.card.done_tip, where
    if expect.card_menu is not None and cards:
        card = cards[0]
        assert [label for _, label in card.card.actions] == expect.card_menu, where
        # The lap actions are the card's +1 and -1 buttons, never in its menu.
        laps = GAIN in expect.card_menu
        menu = [a for a in expect.card_menu if a not in (GAIN, LOSE)]
        if card.card.tied:
            # The row's rule (review.row_menu), on the card: out of a tie
            # upward passes nobody.
            menu = [rc.BREAK_TIE if a == UP else a for a in menu]
        assert [label for _, label in card.menu_actions] == menu, where
        assert card.dots.isVisibleTo(s) == bool(menu), where
        assert card.lap_up.isVisibleTo(s) == laps, where
        assert card.lap_down.isVisibleTo(s) == laps, where
    rows = s.table.screen.rows
    for index, labels in expect.row_menus.items():
        assert [label for _, label in rows[index].actions] == labels, (where, index)
        has_dots = s.table.cellWidget(index, s.table.columnCount() - 1) is not None
        assert has_dots == bool(labels), (where, index)
    assert s.table.horizontalHeader().sectionsClickable() == expect.headers_open, where
    assert c.board.layout_name() == expect.board, where
    assert win.undo.text() == expect.undo, where
    assert win.undo.isEnabled() == expect.undo_enabled, where
    assert s.problem.text() == "", where
    current = win.program.current_race_id()
    rows_status = {r.race_id: r.status for r in win.program._rows}
    # The list's tag follows the surface's state word: Racing from the
    # first staged click through the final sprint, nothing on a start list.
    tag = expect.status or ("Racing" if expect.state in ("Racing", "Final sprint") else "")
    assert rows_status[current] == tag, where
    assert win.tv.is_live() and win.live_action.isChecked(), where


@pytest.mark.parametrize("fmt", list(WALK))
def test_every_state_of_every_format_shows_what_the_design_says(app, fmt):
    c = app
    c.set_board_live(True)
    row, steps = WALK[fmt]
    select(c, row)
    for i, step in enumerate(steps):
        step.do(c)
        check(c, step.expect, f"{fmt} step {i}")


def test_window_regions_menus_and_start(app):
    from madtracker.ui.window import window_title

    win = app.main
    # Two columns and the bar, always the same (section 5): the event
    # heads the program and the title bar.
    assert win.splitter.count() == 2
    assert win.program.heading.text() == "Demo Race Night"
    assert win.program.date.text() == show_date(app.event.event_date)
    # The event's name and date share one tinted band at the top of the column.
    assert win.program.heading.parent() is win.program.band is win.program.date.parent()
    assert win.program.box.layout().indexOf(win.program.band) == 0
    assert win.windowTitle() == window_title("Demo Race Night", app.event.event_date)
    assert f"Demo Race Night ({win.program.date.text()})" in win.windowTitle()
    assert win.bar.indexOf(win.program.mode) == 0 and win.bar.indexOf(win.undo) == 1
    assert win.tv.parent() is win.program, "the preview under the program"
    assert [r.name for r in win.program._rows] == [
        "2 Mile Chase",
        "Elimination",
        "6 Mile Points",
        "8 Mile Madison",
        "Win-and-Out",
        "4 Mile Madison",
        "Handicap",
        "4 Mile Tempo",
        "Sprint Final",
        "Keirin Final",
        "Chariot",
        "Unknown Distance",
        "Miss-and-Out",
    ]
    assert win.program.mode.score.isChecked()
    menus = {m.text().replace("&", ""): m.menu() for m in win.menuBar().actions()}
    assert list(menus) == ["File", "Scoreboard", "Help"]
    items = lambda menu: [a.text() for a in menu.actions() if not a.isSeparator()]  # noqa: E731
    labels = lambda menu: [text.replace("&", "") for text in items(menu)]  # noqa: E731
    assert labels(menus["File"]) == FILE_MENU
    assert labels(menus["Scoreboard"]) == SCOREBOARD_MENU
    assert labels(menus["Help"]) == HELP_MENU
    # Every item has its own letter after Alt+F, Alt+S or Alt+H, except the
    # Scoreboard menu's display list: the board's display is never switched
    # from the keyboard.
    for menu in menus.values():
        lettered = [text for text in items(menu) if "&" in text]
        bare = [text for text in items(menu) if "&" not in text]
        assert bare == (SCOREBOARD_MENU[:-2] if menu is menus["Scoreboard"] else []), bare
        keys = [text[text.index("&") + 1].casefold() for text in lettered]
        assert len(set(keys)) == len(keys), lettered
    # Every launch starts on the logo, with the first race selected.
    assert not win.tv.is_live() and win.logo_action.isChecked()
    assert app.board.page_kind() == "logo"
    assert win.program.current_race_id() == app.races[0].race_id
    assert win.showing() == "surface"
    # The cards sort by bib and show bib and name alike (section 7).
    bibs = [int(card.card.entry.bibs[0]) for card in win.surface.cards.cards]
    assert bibs == sorted(bibs)
    # A card says nothing on hover: its face is what a click does.
    assert win.surface.cards.cards[0].toolTip() == ""


# ----- the sweep: nothing is silent ------------------------------------------


def snapshot(c) -> tuple:
    win = c.main
    s = win.surface
    live = c.live
    return (
        win.showing(),
        win.program.current_race_id(),
        s.state.text(),
        s.task.text(),
        s.problem.text(),
        tuple(s.visible_buttons()),
        s.record_button.isEnabled(),
        tuple((card.card.entrant_id, card.card.badge) for card in s.cards.cards),
        tuple(
            (r.entrant_id, r.place_text, r.staged)
            for r in (s.table.screen.rows if s.table.screen else ())
        ),  # noqa: E501
        win.undo.text(),
        win.tv.is_live(),
        c.board.layout_name(),
        c.board.page_kind(),
        c.board.isVisible(),
        win.none_action.isChecked(),
        next((a.text() for a in win.display_group.actions() if a.isChecked()), None),
        win.help_window is not None and win.help_window.isVisible(),
        live.state if live else None,
        tuple(r.action_id for r in live.rows()) if live else (),
        tuple(tuple(g) for g in live._staged.groups) if live else (),
        live.editing_sprint if live else None,
        tuple(tuple(g) for g in live._staged.tail) if live else (),
    )


def restore(c, before: tuple) -> bool:
    """Back to the state before one click: one Undo, a Reopen, a cancelled edit. False when it is not."""
    win = c.main
    live = c.live
    help_at, state_at, actions_at, staged_at, editing_at, tail_at = 16, 17, 18, 19, 20, 21
    if win.showing() == "setup":
        c.close_setup()
    if win.program.current_race_id() != before[1]:
        c.select_race(before[1])
        live = c.live
    if live is not None:
        if live.state == "final" and before[state_at] != "final":
            c.reopen_race()
        if live.editing_sprint is not None and before[editing_at] is None:
            live.cancel_edit()
            c.refresh()
        if before[state_at] == "final" and live.state != "final":
            c.mark_final()
        now = (
            tuple(r.action_id for r in live.rows()),
            tuple(tuple(g) for g in live._staged.groups),
            tuple(tuple(g) for g in live._staged.tail),
        )
        if now != (before[actions_at], before[staged_at], before[tail_at]):
            c.undo()
    if win.tv.is_live() != before[10]:
        c.set_board_live(before[10])
    if c.board.isVisible() != before[13] or win.none_action.isChecked() != before[14]:
        c.show_board(not before[14])
    checked = next((a.text() for a in win.display_group.actions() if a.isChecked()), None)
    if checked != before[15]:
        for action in win.display_group.actions():
            if action.text() == before[15]:
                action.trigger()
    if win.help_window is not None and win.help_window.isVisible() and not before[help_at]:
        win.help_window.hide()
    win.show_problem(None)
    c.refresh()
    return snapshot(c) == before


def done_click(c, card) -> None:
    """A click on a done card: the controller's sentence on the red line, and nothing recorded."""
    eid = card.card.entrant_id
    live = c.live
    log = [r.action_id for r in live.rows()]

    def staged():
        return [tuple(map(tuple, live._staged.groups)), tuple(map(tuple, live._staged.tail))]

    before = staged()
    # The refusal records nothing, so asking the controller first is safe.
    refusal = live.click(eid)
    assert not refusal.ok and refusal.message, eid
    card.click()
    assert c.main.surface.problem.text() == refusal.message, eid
    assert [r.action_id for r in live.rows()] == log and staged() == before, eid
    assert not card.property("lit"), eid


def controls(c) -> list[tuple[str, Callable]]:
    """Every visible control in the window now, each as (name, press)."""
    win = c.main
    s = win.surface
    out: list[tuple[str, Callable]] = []
    for card in s.cards.cards:
        name = card.card.entry.names[0]
        if card.card.done:
            out.append((f"card done {name}", lambda card=card: done_click(c, card)))
        else:
            out.append((f"card {name}", card.click))
        if card.dots.isVisibleTo(s):
            out.append((f"card dots {card.card.entry.names[0]}", card.dots.click))
        for lap in (card.lap_up, card.lap_down):
            if lap.isVisibleTo(s):
                out.append((f"card lap {lap.text()} {card.card.entry.names[0]}", lap.click))
    if s.task_dots.isVisibleTo(s):
        out.append(("task dots", s.task_dots.click))
        # Each item of the race's own menu, as its pick runs: each asks or
        # opens its box first.
        for key, label in s.screen.race_actions:
            out.append((f"race item {label}", lambda key=key: c.race_action(key)))
    for b in s._buttons():
        if b.isVisibleTo(s) and b.isEnabled():
            out.append((f"button {b.text()}", b.click))
    table = s.table
    for i in range(table.rowCount()):
        w = table.cellWidget(i, table.columnCount() - 1)
        if w is not None:
            out.append((f"row dots {i}", w.click))
    if table.horizontalHeader().sectionsClickable():
        for n in table.screen.sprint_columns:
            col = table.sprint_column(n)
            out.append(
                (f"header S{n}", lambda col=col: table.horizontalHeader().sectionClicked.emit(col))
            )  # noqa: E501
    if win.undo.isEnabled():
        out.append(("undo", win.undo.click))
    # The preview is the TV's one control: a click switches Logo and Live.
    out.append(("preview", win.tv.click))
    # The side of the switch that is off; the side that is on is the screen already shown.
    mode = win.program.mode
    off = mode.score if mode.edit.isChecked() else mode.edit
    out.append((f"switch {off.text()}", off.click))
    for race in c.races:
        if race.race_id != win.program.current_race_id():
            out.append(
                (f"program row {race.name}", lambda rid=race.race_id: win.program.select(rid))
            )  # noqa: E501
            break
    for menu in (win.file_menu, win.board_menu, win.help_menu):
        for action in menu.actions():
            if action.isSeparator() or action.menu() is not None:
                continue
            # Compared without the mnemonic's "&": quitting ends the walk.
            if action.text().replace("&", "") == "Quit":
                continue
            if action in (win.logo_action, win.live_action) and action.isChecked():
                continue  # the chosen one of a pair: clicking it again chooses the same
            if action in win.display_group.actions():
                continue  # the display list is swept below, its ticked entry left alone
            out.append((f"menu {action.text()}", action.trigger))
    for action in win.display_group.actions():
        if not action.isChecked():
            out.append((f"display {action.text()}", action.trigger))
    return out


@pytest.mark.parametrize("fmt", list(WALK))
def test_every_visible_control_does_something_in_every_state(make_app, quiet, fmt):
    row, steps = WALK[fmt]

    def reach(i: int):
        """A fresh app in the state after step ``i``: the demo event is deterministic."""
        c = make_app()
        c.main.show()
        c.place_board()
        c.set_board_live(True)
        select(c, row)
        for step in steps[: i + 1]:
            step.do(c)
        return c

    c = None
    for i in range(len(steps)):
        if c is not None:
            make_app.dispose(c)
        c = reach(i)
        k = 0
        while k < len(controls(c)):
            # Listed afresh each round: a rebuilt app has new widgets.
            name, press = controls(c)[k]
            k += 1
            before = snapshot(c)
            quiet.clear()
            press()
            # As the app's event loop would: the cards each press replaced
            # are deleted now, not all together at the end.
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            after = snapshot(c)
            changed = after != before
            problem = c.main.surface.problem.text() or c.main.surface.flashing()
            assert changed or quiet or problem, f"{fmt} step {i}: {name} was silent"
            if "dots" in name:
                assert quiet and quiet[0].startswith("menu:") and quiet[0] != "menu:", (
                    fmt,
                    i,
                    name,
                )
            if name.startswith("card dots"):
                assert GAIN not in quiet[0] and LOSE not in quiet[0], (fmt, i, name)
            if name.startswith("card lap"):
                # Routine: recorded at once, nothing asked.
                assert not quiet and changed and not problem, (fmt, i, name)
            if not restore(c, before):
                # An Undo cannot be undone: the state is rebuilt from the walk.
                make_app.dispose(c)
                c = reach(i)
                assert snapshot(c) == before, (
                    f"{fmt} step {i}: {name} left a state the walk cannot rebuild"
                )  # noqa: E501


def test_the_task_lines_menu_offers_end_race_and_shorten_race_until_the_final_sprint(app, quiet):
    """Section 5: the task line's ⋯ holds End Race Now, Result As-Is... and
    Shorten Race... from the race's first screen, grayed until a sprint is
    recorded; each asks first, Shorten Race in its own box. In the final
    sprint Shorten Race is grayed again, with why. A format with no call of
    its own has no ⋯."""
    c = app
    select(c, CHASE)
    s = c.main.surface
    assert not s.task_dots.isVisibleTo(s) and not s.open_race_actions()
    select(c, POINTS)
    assert s.task_dots.isVisibleTo(s)
    quiet.clear()
    s.task_dots.click()
    assert quiet == ["menu:End Race Now, Result As-Is...,Shorten Race..."]
    assert s.screen.race_actions == ()
    for eid in c.live.roster.ids[: c.live.scoring_places(1)]:
        assert c.click(eid)
    assert c.record_sprint()
    quiet.clear()
    s.task_dots.click()
    assert quiet == ["menu:End Race Now, Result As-Is...,Shorten Race..."]
    quiet.clear()
    assert not c.race_action("shorten_race")
    assert quiet == ["dialog:Shorten Race"]
    assert c.live.sprint_count == c.live.rules.sprint_count, "Cancel records nothing"
    assert s.problem.text() == ""
    while c.live.task().kind != "final_sprint":
        for eid in c.live.roster.ids[: c.live.scoring_places(c.live.task().sprint_no)]:
            assert c.click(eid)
        assert c.record_sprint()
    quiet.clear()
    s.task_dots.click()
    assert quiet == ["menu:End Race Now, Result As-Is...,Shorten Race..."]
    assert s.screen.race_actions == (("end_race", "End Race Now, Result As-Is..."),)
    assert s.screen.race_menu[1][2] == (
        "The final sprint has begun; use End Race Now, Result As-Is... to stop the race."
    )


# ----- the other screens: setup and the File menu's dialogs -------------------


def form_labels(widget) -> list[str]:
    """The form labels, top to bottom, leaving out the unlabeled rows."""
    from PySide6.QtWidgets import QFormLayout

    out = []
    for form in widget.findChildren(QFormLayout):
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            text = item.widget().text() if item is not None and item.widget() else ""
            if text:
                out.append(text)
    return out


def button_rows(widget) -> list[list[str]]:
    """The visible buttons as laid out: rows top to bottom, each left to right."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication, QPushButton

    QApplication.processEvents()
    placed = []
    for b in widget.findChildren(QPushButton):
        if b.isVisibleTo(widget):
            at = b.mapTo(widget, QPoint(0, 0))
            placed.append((at.y() + b.height() // 2, at.x(), b.text()))
    rows: list[list[tuple[int, int, str]]] = []
    for y, x, text in sorted(placed):
        if rows and abs(rows[-1][0][0] - y) <= 4:
            rows[-1].append((y, x, text))
        else:
            rows.append([(y, x, text)])
    return [[text for _, _, text in sorted(row, key=lambda p: p[1])] for row in rows]


def test_set_up_event_shows_its_three_parts_and_done_rightmost(app):
    """Section 6: Event, Roster, Program top to bottom; Score leaves it."""
    c = app
    c.main.show()
    c.open_setup()
    s = c.main.setup
    assert c.main.showing() == "setup"
    assert [s.event_box.title(), s.roster_box.title(), s.program_box.title()] == [
        "Event",
        "Roster",
        "Program",
    ]
    assert s.event_box.y() < s.roster_box.y() < s.program_box.y()
    # Series shares the Date row, for a 768-pixel screen.
    assert form_labels(s.event_box) == ["Name", "Date"]
    assert s.series.isVisibleTo(s)
    assert button_rows(s.event_box) == []
    assert button_rows(s.roster_box) == [["Choose Riders...", "Edit Groups..."]]
    assert button_rows(s.program_box) == [["Add...", "Edit...", "Duplicate...", "Remove", "", ""]]
    # The arrows carry no word, so their names are on them for the tooltip.
    assert [s.up_button.accessibleName(), s.down_button.accessibleName()] == [
        "Move up",
        "Move down",
    ]
    # The program names each format by its plain label; only the picker adds the article.
    formats = [s.program.item(r, 1).text() for r in range(len(c.races))]
    assert formats == [
        "Scratch Race",
        "Elimination",
        "Points Race",
        "Madison",
        "Win-and-Out",
        "Madison",
        "Handicap",
        "Tempo Race",
        "Sprint Final",
        "Keirin Final",
        "Chariot",
        "Unknown Distance",
        "Elimination",
    ]
    # No Done on the screen: Score, on the program pane's switch, is the way back.
    assert "Done" not in [t for row in button_rows(s) for t in row]


def test_edit_score_switch_sits_in_the_bar_under_the_program(app):
    """Section 5: the switch in the bar, under the program column and as wide
    as it, both words whole."""
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    win = app.main
    win.show()
    QTest.qWait(50)  # the bar fits to the columns a turn of the loop later
    mode = win.program.mode
    assert mode.parent() is not win.program, "placed by the window, in the bar"
    at, program = mode.mapTo(win, QPoint(0, 0)), win.program.mapTo(win, QPoint(0, 0))
    assert at.x() == program.x() and mode.width() == win.program.width()
    assert at.y() >= program.y() + win.program.height()
    assert button_rows(mode)[-1] == ["Edit", "Score"]
    for side in (mode.edit, mode.score):
        assert side.width() >= side.sizeHint().width(), side.text()


def test_the_switch_shows_and_changes_the_screen(app):
    """One corner for the way in and the way out, showing which is open."""
    c = app
    c.main.show()
    mode = c.main.program.mode
    assert mode.score.isChecked() and not mode.edit.isChecked()
    # A focus ring on the side that is off would look half chosen on Windows.
    assert all(side.focusPolicy() == Qt.FocusPolicy.NoFocus for side in (mode.edit, mode.score))
    s = c.main.surface
    for b in s._buttons():
        assert b.focusPolicy() == Qt.FocusPolicy.NoFocus, b.text()
    previous = c.live.race_id if c.live else None
    mode.score.click()
    assert c.main.showing() == "surface" and mode.score.isChecked(), "the side already on"
    mode.edit.click()
    assert c.main.showing() == "setup"
    assert mode.edit.isChecked() and not mode.score.isChecked()
    mode.edit.click()
    assert c.main.showing() == "setup" and mode.edit.isChecked(), "the side already on"
    mode.score.click()
    assert c.main.showing() == "surface" and mode.score.isChecked()
    assert not mode.edit.isChecked() and mode.toolTip() == ""
    assert c.live is not None and c.live.race_id == previous, "back to the race it was on"


def test_settings_dialog_lists_the_venue_values_and_save_rightmost(app):
    """Section 11: the venue's set-once values; the primary action is rightmost."""
    from madtracker.ui.settings import SettingsDialog
    from madtracker.ui.widgets import settings_word

    d = SettingsDialog(app.store, app.data_dir, app.main)
    d.show()
    assert d.windowTitle() == settings_word() == app.main.welcome_settings.text().rstrip(".")
    assert form_labels(d) == [
        "Venue name",
        "Scoreboard logo",
        "Riders on the scoreboard",
        "Accent color",
        "Backup folder",
        "Exports folder",
        "Rulesets",
    ]
    rows = button_rows(d)
    assert rows[0] == ["Choose...", "Use Default"]
    assert ["Rulesets..."] in rows
    assert rows[-1] == ["Cancel", "Save"]
    d.close()


def test_rulesets_dialog_buttons_in_order_and_close_last(app):
    """Section 11: USAC 2025 and the venue's copies, one column of actions."""
    from madtracker.ui.about import NOT_USAC
    from madtracker.ui.rulesets import BUILTIN_LOCKED_TIP, BUILTIN_TIP, COPY_NOTE, RulesetsDialog

    d = RulesetsDialog(app.store, app.main)
    d.show()
    assert d.windowTitle() == "Rulesets"
    flat = [text for row in button_rows(d) for text in row]
    assert flat == [
        "Duplicate...",
        "Edit...",
        "Delete",
        "Export to File...",
        "Import from File...",
        "Set as Default",
        "Close",
    ]
    # No paragraph on the dialog: the note is the tooltip of what it explains.
    d.list.setCurrentRow(d.names().index("Demo house rules"))
    assert d.edit_button.toolTip() == COPY_NOTE and d.delete_button.toolTip() == COPY_NOTE
    # The built-in row names its source and edition; its disabled buttons say why.
    d.list.setCurrentRow(d.names().index("rulebook"))
    assert d.list.currentItem().text().startswith("USAC 2025 + Club formats")
    assert d.list.currentItem().toolTip() == BUILTIN_TIP
    assert "USA Cycling Rulebook, version 8•25 (effective 2025-Aug-19)" in BUILTIN_TIP
    assert BUILTIN_TIP.endswith(NOT_USAC), "the one USAC line, the About box's"
    for b in (d.edit_button, d.delete_button):
        assert not b.isEnabled() and b.toolTip() == BUILTIN_LOCKED_TIP
    d.close()


def test_new_event_dialog_asks_name_date_start_from_and_create_rightmost(app):
    """Section 6: a new event can start from an earlier event's program."""
    from madtracker.ui.setup import NewEventDialog

    d = NewEventDialog(app.store, app.main)
    d.show()
    assert d.windowTitle() == "New Event"
    assert form_labels(d) == ["Name", "Date", "Start from"]
    assert d.start_from.itemText(0) == "An Empty Program"
    assert button_rows(d) == [["Cancel", "Create Event"]]
    d.close()


def test_open_event_dialog_lists_events_newest_first_and_open_rightmost(app):
    """Section 5: File > Open event picks from a table, the open event already selected."""
    from madtracker.ui.setup import OpenEventDialog
    from madtracker.ui.widgets import selected_id

    store = app.store
    older = store.add_event("Old Night", "2020-01-01")
    d = OpenEventDialog(store, app.event.event_id, app.main)
    d.show()
    assert d.windowTitle() == "Open Event"
    headers = [d.table.horizontalHeaderItem(i).text() for i in range(d.table.columnCount())]
    assert headers == ["Date", "Name", "Series", "Races", "Riders"]
    from madtracker.dates import show_date

    # Newest first, each date with its month as a word (2026-Oct-14).
    events = store.events()
    assert [e.event_date for e in events] == sorted((e.event_date for e in events), reverse=True)
    dates = [d.table.item(r, 0).text() for r in range(d.table.rowCount())]
    assert dates == [show_date(e.event_date) for e in events]
    assert selected_id(d.table) == app.event.event_id
    assert d.table.item(0, 3).text() == str(len(store.races(app.event.event_id)))
    assert button_rows(d) == [["Delete", "Cancel", "Open"]], "Delete apart, at the left"
    d.select_event(older.event_id)
    assert d.open_chosen() and d.event_id == older.event_id
    d.close()


def test_file_riders_column_of_actions_and_merge_settles_values(app):
    """Section 12: the venue's list keeps, edits and merges riders."""
    from madtracker.ui.setup import MergeDialog, RidersDialog

    store = app.store
    spare = store.add_rider("Walk", "Duplicate")
    keep = store.add_rider("Walker", "Duplicate")
    d = RidersDialog(store, None, app.main)
    d.show()
    flat = [text for row in button_rows(d) for text in row]
    assert flat == [
        "New Rider...",
        "Import from BikeReg...",
        "Edit...",
        "Merge With...",
        "Delete",
        "Close",
    ]
    d.select_rider(spare.rider_id)
    assert d.merge.isEnabled()
    m = MergeDialog(store, spare.rider_id, d)
    m.show()
    assert m.windowTitle() == "Merge Riders"
    assert m.table.item(0, 0).text() == "Walker", "the likely match comes first"
    assert button_rows(m)[-1] == ["Cancel", "Next"] and not m.next_button.isEnabled()
    m.select_rider(keep.rider_id)
    assert m.go_next()
    assert button_rows(m)[-1] == ["Back", "Cancel", "Merge"]
    assert not m.merge_button.isEnabled() and m.left.text() == "1 to choose"
    m.choose("First name", "Walker")
    assert m.merge() and store.rider(m.kept).first_name == "Walker"
    m.close()
    d.close()


def test_a_start_list_waiting_for_bibs_refuses_and_shows_who_lacks_one(app):
    """Section 7: the refusal is the task line, in red; a click flashes it
    rather than repeating it under itself; Record sprint says it; and an
    empty plate marks each rider still without a number."""
    c = app
    select(c, POINTS)
    set_bibs(b45=None, b51=None)(c)
    line = "2 riders have no bib. Edit Event > Roster."
    s = c.main.surface
    assert s.task.text() == line
    assert not s.record_button.isEnabled() and s.record_button.toolTip() == line
    cards = s.cards.cards
    assert [card.card.entry.bibs for card in cards[-2:]] == [[], []]
    assert all(card.card.entry.bibs for card in cards[:-2]), "the bibless sort last"
    assert cards[-1]._bib_name()[0] == "" and cards[-1].shown_name()
    assert "color: #b3261e" in s.task.styleSheet()
    assert not c.click(cards[0].card.entrant_id)
    assert s.problem.text() == "" and s.flashing()
    assert c.live.rows() == [] and c.live.staged() == []


def test_all_riders_imports_onto_the_open_events_roster_without_bibs(app, tmp_path):
    """Sections 6 and 12: the import is in the Riders window, and offers the open event's
    roster; a rider may be on it before the venue hands out bibs."""
    from madtracker.ui import setup as su

    c = app
    c.main.show()
    c.open_setup()
    screen = c.main.setup
    riders = su.RidersDialog(c.store, None, c.main, import_event=c.event.event_id)
    path = tmp_path / "entries.csv"
    path.write_text(
        "Last Name,First Name,USAC License,Category,Bib\n"
        "Quill,Ada,100001,Group A,\nLin,Bo,100002,Group B,\nWard,Cy,100003,Group B,\n",
        encoding="utf-8",
    )
    preview = riders.preview_for(path)
    assert preview.event.currentData() == c.event.event_id
    bibs = [preview.table.item(r, su.P_BIB) for r in range(3)]
    assert [b.text() for b in bibs] == ["", "", ""]
    assert all(b.background().color() == su.style.DANGER_TINT for b in bibs)
    assert preview.apply_button.isEnabled() and preview.apply_button.toolTip() == ""
    assert preview.apply()
    riders.import_done(preview)
    assert riders.status.text() == "", "a clean import shows on the roster count, not the line"
    screen.refresh()
    count = len(c.store.entries(c.event.event_id))
    # The demo's own riders with no group are counted as well.
    assert screen.roster_count.text() == f"{count} riders, 3 without a bib, 3 without a group"


def test_export_pdf_dialog_offers_the_race_or_the_event_and_export_rightmost(app):
    """Section 9: a PDF for the race that just concluded, or for the whole event."""
    from madtracker.ui.setup import ExportPdfDialog

    d = ExportPdfDialog([(1, "Scratch A"), (2, "Points A")], default=2, race_first=True, parent=app.main)  # fmt: skip
    d.show()
    assert d.windowTitle() == "Export Results PDF"
    assert [d.whole.text(), d.race.text()] == ["Whole event", "Race"]
    assert d.choice.currentText() == "Points A" and d.race_id() == 2
    assert button_rows(d) == [["Cancel", "Export"]]
    d.close()


def test_multi_race_standings_dialog_has_the_list_the_page_and_the_preview(app):
    """Section 8a: the standings on the left, its page beside them, the Standings box, Close last."""
    from PySide6.QtWidgets import QGroupBox

    from madtracker.ui.standings import StandingsDialog

    d = StandingsDialog(app.store, app.main, export=lambda standings_id: None)
    d.show()
    assert d.windowTitle() == "Multi-Race Standings"
    assert form_labels(d) == ["Name", "Kind", "Place points"]
    assert d.kind.currentText() == "Team Omnium by Points"
    assert [d.kind.itemText(i) for i in range(d.kind.count())] == [
        "Team Omnium by Points",
        "Team Omnium by Place",
        "Omnium by Place",
        "Four-Race Omnium",
    ]
    # The Place points row is the place kind's alone: hidden, not grayed.
    assert not d.form.isRowVisible(d.place_points)
    d.kind.setCurrentIndex(1)
    assert d.form.isRowVisible(d.place_points) and d.place_points.text() == "7, 5, 3, 2, 1"
    assert [b.title() for b in d.findChildren(QGroupBox)] == ["Events", "Races", "Standings"]
    flat = sorted(text for row in button_rows(d) for text in row)
    assert flat == sorted(["Add...", "Duplicate...", "Delete", "Export PDF...", "Close"])
    assert button_rows(d)[-1][-1] == "Close"
    # No tag until the standings are final; the Standings box is read, never picked.
    assert d.state.text() == ""
    (table,) = d.standings_views
    for part in table.parts:
        assert part.selectionMode() == part.SelectionMode.NoSelection
    d.close()
    d.deleteLater()


def test_every_control_in_the_multi_race_standings_dialog_does_something(
    make_app, quiet, monkeypatch
):
    """The sweep for the File menu's Multi-Race Standings dialog: nothing in it is silent."""
    from PySide6.QtWidgets import QPushButton

    from madtracker.ui.standings import StandingsDialog
    from madtracker.ui.widgets import NameDialog

    def ask_name(self):
        quiet.append("input:" + self.windowTitle())
        return int(QDialog.DialogCode.Rejected)

    monkeypatch.setattr(NameDialog, "exec", ask_name)
    from madtracker.ui.penalty import OmniumPenaltyDialog

    monkeypatch.setattr(OmniumPenaltyDialog, "exec", ask_name)

    from madtracker.control.demo import DEMO_FOUR_RACE_STANDINGS

    def build(kind):
        c = make_app()
        for s in c.store.list_standings():
            c.store.update_standings(s.standings_id, kind=kind)
        d = StandingsDialog(c.store, c.main, export=lambda sid: quiet.append(f"export:{sid}"))
        if kind == "four_race_omnium":
            # The demo's Four-Race standings has a table, so Omnium Penalty...
            # and Export PDF... are live controls.
            d.select(DEMO_FOUR_RACE_STANDINGS)
        d.show()
        return c, d

    def snap(d) -> tuple:
        return (
            tuple(d.names()),
            d.selected_id(),
            d.name.text(),
            d.kind.currentText(),
            d.place_points.text(),
            tuple(d.ticked_events()),
            tuple(sorted(d.race_ticks().items())),
            tuple(t.cells() for t in d.standings_views),
            d.status.text(),
            d.isVisible(),
            d.help_window is not None and d.help_window.isVisible(),
        )

    def controls(d) -> list[tuple[str, Callable]]:
        out = [
            (b.text(), b.click)
            for b in d.findChildren(QPushButton)
            if b.isVisibleTo(d) and b.isEnabled()
        ]
        for check_list in (d.events, d.races):
            for i in range(check_list.count()):
                item = check_list.item(i)
                # An event's heading in the Races list is a heading, not a control.
                if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    out.append(
                        (
                            f"tick {item.text()}",
                            lambda cl=check_list, it=item: cl.itemClicked.emit(it),
                        )
                    )

        def rename():
            d.name.setText("Renamed")
            d.name.editingFinished.emit()

        out.append(("name", rename))
        # The other kind, as a pick from the list does.
        out.append(("kind", lambda: d.kind.setCurrentIndex(1 - d.kind.currentIndex())))
        if d.place_points.isVisibleTo(d):

            def place_points():
                d.place_points.setText("10, 6, 3")
                d.place_points.editingFinished.emit()

            out.append(("place points", place_points))
        out.append(("F1", d.help_action.trigger))
        return out

    # Each kind: the Place points row is the place kinds' alone, the rider
    # kinds list other races, and the Four-Race Omnium refuses the demo's program.
    for kind in ("team_omnium", "team_omnium_places", "omnium_places", "four_race_omnium"):
        c, d = build(kind)
        names = [name for name, _press in controls(d)]
        assert {"Add...", "Duplicate...", "Delete", "Close", "kind"} <= set(names)
        assert ("place points" in names) == (kind in ("team_omnium_places", "omnium_places"))
        assert "Export PDF..." in names
        assert ("Omnium Penalty..." in names) == (kind == "four_race_omnium")
        d.close()
        make_app.dispose(c)
        for k in range(len(names)):
            # A fresh file for each control: a tick or a rename is saved at once.
            # Each app is let go once its control is pressed: sixty open
            # data files at once is past macOS's limit of 256 open files.
            c, d = build(kind)
            name, press = controls(d)[k]
            before = snap(d)
            quiet.clear()
            press()
            assert snap(d) != before or quiet, f"Multi-Race Standings ({kind}): {name} was silent"
            d.close()
            make_app.dispose(c)


# ----- corrections, the primary buttons, events, and ties ---------------------


def _points_in_review(c):
    select(c, POINTS)
    live = c.live
    for _ in range(live.sprint_count - 1):
        click(*B_RIDERS[:3])(c)
        record(c)
    click(*B_RIDERS)(c)
    assert live.state == "provisional"


def _state(c):
    live = c.live
    return (live.state, tuple(r.action_id for r in live.rows()), live.editing_sprint)


def test_a_reopened_sprint_says_correcting_and_cancel_leaves_it_as_it_was(app):
    c = app
    _points_in_review(c)
    before = _state(c)
    assert c.reopen_sprint(1)
    s = c.main.surface
    assert (
        s.task.text()
        == "Correcting Sprint 1: click the first 6 riders in order, then Record Sprint."
    )
    assert s.visible_buttons() == ["Cancel", "Record Sprint"]
    # Cancel sits left of Record sprint.
    assert s.cancel_button.x() < s.record_button.x() or not c.main.isVisible()
    click("4")(c)  # a change to the staged order, thrown away by Cancel
    s.cancel_button.click()
    assert _state(c) == before and c.live.state == "provisional"
    assert s.task.text() == rc.REVIEW_TEXT and s.visible_buttons() == ["Mark Final"]


def test_leaving_a_reopened_sprint_cancels_it(app):
    c = app
    _points_in_review(c)
    before = _state(c)
    race_id = c.live.race_id
    assert c.reopen_sprint(2)
    select(c, CHASE)
    c.select_race(race_id)
    assert _state(c) == before
    assert c.reopen_sprint(2)
    c.open_setup()
    c.close_setup()
    c.select_race(race_id)
    assert _state(c) == before


def test_place_the_rest_together_sits_in_record_sprints_slot_and_is_primary(app):
    """One filled button per state: the chase's completes the order from its middle."""
    c = app
    s = c.main.surface
    select(c, CHASE)
    assert not s.rest_button.isVisibleTo(s), "nobody placed yet"
    assert c.click(c.live.roster.resolve("7"))
    assert s.visible_buttons() == [REST]
    assert s.rest_button.styleSheet() == s.record_button.styleSheet()
    assert s.rest_button.minimumHeight() == s.record_button.minimumHeight()
    # The button itself, through the window's signal to the controller.
    s.rest_button.click()
    assert s.state.text() == "Provisional" and s.problem.text() == ""
    assert [r.place_text for r in s.table.screen.rows] == ["1"] + ["2"] * 9
    assert s.visible_buttons() == ["Mark Final"]


def test_mark_final_is_styled_as_the_primary_button(app):
    c = app
    _points_in_review(c)
    s = c.main.surface
    assert s.final_button.styleSheet() == s.record_button.styleSheet()
    assert s.final_button.font() == s.record_button.font()
    assert s.final_button.minimumHeight() == s.record_button.minimumHeight()


def test_closing_the_scoreboard_hides_it_and_never_quits(app, monkeypatch):
    c = app
    quit_asked = []
    monkeypatch.setattr(c.main, "request_quit", lambda: quit_asked.append(1))
    c.main.show()
    c.place_board()
    assert c.board.isVisible()
    c.board.close_requested.emit()
    assert not c.board.isVisible() and c.main.none_action.isChecked()
    assert quit_asked == []


def test_new_event_started_from_a_program_opens_set_up_event(app, monkeypatch):
    from madtracker.ui import setup as su

    c = app

    def run(dialog):
        dialog.name.setText("Next Night")
        dialog.start_from.setCurrentIndex(1)
        return int(QDialog.DialogCode.Accepted) if dialog.create() else 0

    monkeypatch.setattr(su.NewEventDialog, "exec", run)
    event_id = c.new_event()
    assert event_id is not None and c.store.races(event_id)
    assert c.main.showing() == "setup"


def test_file_menu_event_items_from_set_up_event_are_never_silent(app, quiet):
    c = app
    c.open_setup()
    for action, opened in (
        (c.main.new_event_action, "dialog:New Event"),
        (c.main.open_event_action, "dialog:Open Event"),
    ):
        quiet.clear()
        action.trigger()
        assert quiet == [opened], action.text()
        # Cancelled, the scorer is still setting up the same event.
        assert c.main.showing() == "setup"


def test_new_event_from_set_up_event_sets_up_the_new_one(app, monkeypatch):
    from madtracker.ui import setup as su

    c = app
    c.open_setup()
    before = c.event.event_id

    def run(dialog):
        dialog.name.setText("Next Night")
        return int(QDialog.DialogCode.Accepted) if dialog.create() else 0

    monkeypatch.setattr(su.NewEventDialog, "exec", run)
    c.main.new_event_action.trigger()
    assert c.event.event_id != before
    assert c.main.showing() == "setup"
    assert c.main.setup.event_id == c.event.event_id
    assert c.main.setup.name.text() == "Next Night"


def test_open_event_from_set_up_event_lands_on_its_scoring_surface(app, monkeypatch):
    c = app
    first = c.event
    # An event with no races opens on its setup screen.
    c.open_event(c.store.add_event("Next Night", "2026-12-01").event_id)
    assert c.main.showing() == "setup"
    from madtracker.ui import setup as su

    def run(dialog):
        dialog.select_event(first.event_id)
        return int(QDialog.DialogCode.Accepted) if dialog.open_chosen() else 0

    monkeypatch.setattr(su.OpenEventDialog, "exec", run)
    c.main.open_event_action.trigger()
    assert c.event.event_id == first.event_id
    assert c.main.showing() == "surface"


def test_every_row_of_a_tie_offers_break_tie(app, quiet):
    """A five-way tie from Place the Rest Together is broken from its first
    row too, and that row reads Break Tie, since Move Up would look like a
    swap with the place above."""
    from madtracker.ui.review import BREAK_TIE, row_menu

    c = app
    select(c, CHASE)
    click(*B_RIDERS)(c)
    second = c.live.roster.resolve(B_RIDERS[1])
    assert c.row_action(second, "tie_above")
    screen = c.main.surface.table.screen
    assert [label for _, label in row_menu(screen, 0)][0] == BREAK_TIE
    assert [label for _, label in row_menu(screen, 1)][0] == BREAK_TIE
    assert [label for _, label in row_menu(screen, 2)][0] == UP
    # The menu opens with the same words; the action is still a move up.
    quiet.clear()
    c.main.surface.table.open_row_menu(1)
    assert quiet[-1].startswith(f"menu:{BREAK_TIE},")
    # From the first row the rider takes the place alone, ahead of the rest.
    first = c.live.roster.resolve(B_RIDERS[0])
    assert c.row_action(first, "move_up")
    rows = c.main.surface.table.screen.rows
    assert [(r.place_text, r.entrant_id) for r in rows[:2]] == [("1", first), ("2", second)]


@pytest.mark.parametrize("fmt,first,second,words", [
    ("points", "12", "7", TIE),
    ("madison", "Blue", "Red", "Tie with the Team Above"),
])  # fmt: skip
def test_a_sprint_dead_heat_is_tied_from_the_card_and_both_badges_share_the_place(
    app, quiet, fmt, first, second, words
):
    c = app
    select(c, WALK[fmt][0])
    click(first, second)(c)
    resolve = c.live.roster.resolve

    def card(token):
        return next(w for w in c.main.surface.cards.cards if w.card.entrant_id == resolve(token))

    assert [label for _, label in card(second).menu_actions[:2]] == [UP, words]
    assert words not in [label for _, label in card(first).menu_actions]
    assert card(second).badge_text() == "2"
    quiet.clear()
    card(second).open_actions()
    assert quiet[-1].startswith(f"menu:{UP},{words},")
    # The menu pick goes the card's own way: its action signal.
    card(second).action.emit(resolve(second), "tie_above")
    # The plain number on both, as the table and the sheet write a shared place.
    assert [card(t).badge_text() for t in (first, second)] == ["1", "1"]
    assert c.main.undo.text() == rc.undo_tied(
        c.live.label(resolve(second)), c.live.label(resolve(first))
    )
    assert words not in [label for _, label in card(second).menu_actions]
    # Both badges are shared, so both menus start with Break Tie.
    assert [label for _, label in card(second).menu_actions[:2]] == [rc.BREAK_TIE, DOWN]
    assert [label for _, label in card(first).menu_actions[:2]] == [rc.BREAK_TIE, DOWN]
    assert not card(second).badge_rect().intersects(card(second).dots.geometry())


def test_a_badged_cards_menu_folds_the_long_moves_into_one_submenu(app, quiet):
    """Three or more badges: the card's ⋯ reads Move Up, Move Down, Move to
    Place (a submenu of the other places), the tie, then the rest, as a
    result row's does."""
    c = app
    select(c, POINTS)
    click("12", "7", "4", "9")(c)
    resolve = c.live.roster.resolve
    card = next(w for w in c.main.surface.cards.cards if w.card.entrant_id == resolve("4"))
    assert [label for _, label in card.menu_actions][:6] == [
        UP, DOWN, "Move to 1st", "Move to 2nd", "Move to 4th", TIE
    ]  # fmt: skip
    quiet.clear()
    card.open_actions()
    assert quiet[-1].startswith(f"menu:{UP},{DOWN},Move to Place,{TIE},")
    # A pick from the submenu goes the card's own way.
    card.action.emit(resolve("4"), "move_to:0")
    badges = {w.card.entrant_id: w.card.badge for w in c.main.surface.cards.cards}
    assert [badges[resolve(b)] for b in ("4", "12", "7", "9")] == [1, 2, 3, 4]
    assert c.main.undo.text() == rc.undo_moved(c.live.label(resolve("4")), "to 1st")
    # A refused move says so in the red line, once.
    assert not c.rider_action(resolve("4"), "move_up")
    assert c.main.surface.problem.text() == rc.NO_MOVE


def test_the_result_table_gives_the_bib_its_own_column(app):
    from PySide6.QtCore import Qt

    c = app
    select(c, CHASE)
    click(*B_RIDERS[:1])(c)
    t = c.main.surface.table
    headers = [t.horizontalHeaderItem(i).text() for i in range(t.columnCount())]
    assert headers[:3] == ["Place", "Bib", "Rider"]
    e = c.live.roster.get(c.live.roster.resolve(B_RIDERS[0]))
    assert t.item(0, 1).text() == str(e.bibs[0])
    assert t.item(0, 1).textAlignment() & Qt.AlignmentFlag.AlignRight
    assert t.horizontalHeaderItem(1).textAlignment() & Qt.AlignmentFlag.AlignRight
    assert t.item(0, 2).text() == e.names[0]


def test_the_place_badge_never_sits_under_the_dots(app):
    from madtracker.ui import style

    c = app
    c.main.show()
    select(c, POINTS)
    click(*B_RIDERS[:3])(c)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    badged = [card for card in c.main.surface.cards.cards if card.card.badge]
    assert len(badged) == 3
    for card in badged:
        assert card.dots.isVisibleTo(card)
        assert not card.badge_rect().intersects(card.dots.geometry())
        # The actions strip runs the card's full height, flush inside its
        # border: 1 px, and 2 px along the bottom shade.
        strip = card.dots.geometry()
        assert (strip.right(), strip.top()) == (card.width() - 2, 1)
        assert strip.height() == card.height() - 3
        # The lap buttons sit between the badge and the strip, side by
        # side, -1 then +1, each the strip's height and at least a
        # finger's width: stacked, each would be about 30 px tall at 1366.
        up, down = card.lap_up.geometry(), card.lap_down.geometry()
        assert up.right() + 1 == strip.left() and down.right() + 1 == up.left()
        assert up.width() == down.width() == cards.lap_width() >= style.TOUCH_LAP
        assert strip.width() >= style.TOUCH and strip.height() >= style.TOUCH
        assert up.top() == down.top() == 1
        assert up.bottom() == down.bottom() == strip.bottom()
        assert card.badge_rect().right() < up.left()


def test_plus_one_on_a_card_records_a_lap_at_once(app, quiet):
    from PySide6.QtWidgets import QApplication

    from madtracker.ui.cards import lap_width

    c = app
    c.main.show()
    select(c, POINTS)
    QApplication.processEvents()
    s = c.main.surface
    card = s.cards.cards[0]
    assert (card.lap_up.text(), card.lap_down.text()) == ("+1", "−1")
    assert (card.lap_up.toolTip(), card.lap_down.toolTip()) == ("Gained a lap", "Lost a lap")
    assert card.lap_up.width() == lap_width()
    name = card.card.entry.names[0]
    quiet.clear()
    card.lap_up.click()
    assert quiet == [], "a lap asks nothing"
    # The entry is in the file's log at once, worded for the scorer.
    log = lambda: event_log(c.store, c.event.event_id)[-1].text  # noqa: E731
    assert "Gained a lap: " in log() and name in log()
    t = s.table
    headers = [t.horizontalHeaderItem(i).text() for i in range(t.columnCount())]
    laps, rider = headers.index("Laps"), headers.index("Rider")
    row = next(i for i in range(t.rowCount()) if t.item(i, rider).text() == name)
    assert t.item(row, laps).text() == "+1"
    assert c.main.undo.text().endswith(" gained a lap")
    s.cards.cards[0].lap_down.click()
    assert "Lost a lap: " in log()


@pytest.mark.parametrize("fmt", ["chase", "points", "madison"])
def test_a_lap_shows_on_the_card_as_a_chip(app, fmt):
    from PySide6.QtWidgets import QApplication

    c = app
    c.main.show()
    select(c, WALK[fmt][0])
    QApplication.processEvents()
    card = c.main.surface.cards.cards[0]
    assert card.chip_rect() is None
    card.lap_up.click()
    QApplication.processEvents()
    card = c.main.surface.cards.card_for(card.card.entrant_id)
    assert card.chip_text() == "+1 lap"
    chip = card.chip_rect()
    assert chip.right() < card.lap_up.geometry().left()
    if not card.card.entry.color:
        # The name gives way to the chip, never over it.
        assert card._name_left() + card.name_room() < chip.left()
    eid = card.card.entrant_id
    grid = c.main.surface.cards
    grid.card_for(eid).lap_down.click()
    assert grid.card_for(eid).chip_rect() is None, "even again: no chip"
    grid.card_for(eid).lap_down.click()
    assert grid.card_for(eid).chip_text() == "−1 lap"


def test_a_chase_lap_before_the_finish_is_on_the_card_then_in_a_laps_column(app):
    from PySide6.QtCore import Qt

    c = app
    select(c, CHASE)
    t = c.main.surface.table
    headers = lambda: [t.horizontalHeaderItem(i).text() for i in range(t.columnCount())]  # noqa: E731
    lapped = c.live.roster.resolve("45")
    c.rider_action(lapped, "lap_gained")
    assert c.main.surface.cards.card_for(lapped).chip_text() == "+1 lap"
    assert t.rowCount() == 0 and "Laps" not in headers()
    click("7")(c)
    # A row without a lap: the column stays off until a row has one.
    assert "Laps" not in headers()
    click(*[b for b in B_RIDERS if b not in ("7",)])(c)
    assert headers()[:4] == ["Place", "Bib", "Rider", "Laps"]
    laps, rider = headers().index("Laps"), headers().index("Rider")
    name = c.live.roster.get(lapped).names[0]
    row = next(i for i in range(t.rowCount()) if t.item(i, rider).text() == name)
    assert t.item(row, laps).text() == "+1"
    assert t.item(row, laps).textAlignment() & Qt.AlignmentFlag.AlignRight


def test_a_madison_team_card_has_the_lap_buttons_and_an_elimination_card_does_not(app):
    c = app
    select(c, MADISON)
    team = c.main.surface.cards.cards[0]
    assert team.card.entry.color and team.laps
    assert not team.lap_up.isHidden() and not team.lap_down.isHidden()
    select(c, ELIMINATION)
    rider = c.main.surface.cards.cards[0]
    assert not rider.laps and rider.lap_up.isHidden() and rider.lap_down.isHidden()


def _font_pt(w) -> float:
    return w.font().pointSizeF()


def test_nothing_in_the_operator_window_is_below_12_pt(qapp, make_app):
    from PySide6.QtWidgets import QApplication, QWidget

    from madtracker.ui.look import apply_look

    apply_look(qapp)  # as main() does before any window is built
    c = make_app()
    c.main.show()
    _points_in_review(c)
    QApplication.processEvents()
    small = [
        (type(w).__name__, w.objectName(), _font_pt(w))
        for w in c.main.findChildren(QWidget)
        if w.isVisible() and 0 < _font_pt(w) < 12
    ]
    assert small == []
    assert QApplication.font().pointSizeF() == 12
    c.open_setup()
    QApplication.processEvents()
    small = [
        (type(w).__name__, _font_pt(w))
        for w in c.main.setup.findChildren(QWidget)
        if w.isVisible() and 0 < _font_pt(w) < 12
    ]
    assert small == []


def test_a_1366_window_shows_every_card_in_two_columns_and_the_standings(app):
    from PySide6.QtWidgets import QApplication

    c = app
    win = c.main
    win.resize(1366, 740)
    win.show()
    select(c, POINTS)
    QApplication.processEvents()
    left = win.program.width()
    assert 240 <= left < 300, "the program gives way on a small window"
    assert win.tv.width() == left, "the preview is the program column's width"
    grid = win.surface.cards
    assert not win.surface.wide, "a 1366 laptop stacks the cards over the standings"
    # Two columns, each wide enough for a whole 16-character name beside
    # finger-sized buttons: the scorer takes calls by name, and taps.
    assert len(grid.cards) == 10 and grid.columns() == 2
    assert grid.height() >= grid.needed_height(), "every card shows without scrolling"
    assert win.surface.table.isVisible() and win.surface.table.height() > 100
    # A big window (maximized on a 1920 display) gives the program more
    # room, and the cards their own column beside the standings.
    win.resize(1920, 1000)
    QApplication.processEvents()
    assert win.program.width() > left and win.tv.width() == win.program.width()
    assert win.surface.wide and grid.columns() == 2


def test_a_madisons_five_team_cards_never_scroll_at_1366_by_768(qapp, make_app):
    """A team with no card to click cannot be scored; team cards are one
    line, the color and the team's name."""
    from PySide6.QtWidgets import QApplication

    from madtracker.ui.look import apply_look

    apply_look(qapp)
    c = make_app()
    win = c.main
    win.resize(1366, 768)
    win.show()
    select(c, MADISON)
    for team in ("Blue", "Orange"):
        click(team)(c)
    record(c)
    for _ in range(3):
        QApplication.processEvents()
    grid = win.surface.cards
    assert len(grid.cards) == 5
    assert grid.height() >= grid.needed_height(), "every team card shows without scrolling"
    assert win.surface.table.isVisible()


def test_a_16_rider_field_fits_a_1366_by_768_window_on_shorter_cards(qapp, make_app):
    from PySide6.QtWidgets import QApplication

    from madtracker.ui.cards import full_card_height, short_card_height
    from madtracker.ui.look import apply_look

    # The real face and style sheet, as main() applies them: the room
    # the cards get depends on every other control's height.
    apply_look(qapp)
    c = make_app()
    win = c.main
    win.resize(1366, 768)
    win.show()
    select(c, CHASE)
    late = "Wren Talbot,Iker Solano,Mina Varga,Otto Brennan,Zara Quell,Teo Marchetti".split(",")
    for i, name in enumerate(late):
        rider_id = c.store.add_rider(*name.split()).rider_id
        c.store.add_entry(c.event.event_id, rider_id, 60 + i, local_group="Group B")
        c.store.add_race_entry(c.live.race_id, rider_id)
    c.live.reload()
    c.refresh()
    QApplication.processEvents()
    grid = win.surface.cards
    # Two columns of finger-sized cards:
    # eight rows, which fit at 768 on shorter cards.
    assert len(grid.cards) == 16 and grid.columns() == 2
    heights = {card.height() for card in grid.cards}
    assert len(heights) == 1
    assert short_card_height() <= heights.pop() <= full_card_height()
    assert grid.height() >= grid.needed_height(), "every card shows without scrolling"
    assert not grid.verticalScrollBar().isVisible()
    assert win.surface.table.isVisible() and win.surface.table.height() > 0
    # A taller window gives the cards their full height back.
    win.resize(1366, 1200)
    QApplication.processEvents()
    assert {card.height() for card in grid.cards} == {full_card_height()}


def test_a_16_character_name_shows_whole_beside_a_badge_on_a_1366_window(app):
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    from madtracker.ui import style
    from madtracker.ui.cards import NAME_PT

    c = app
    win = c.main
    win.resize(1366, 768)
    win.show()
    select(c, POINTS)
    click(*B_RIDERS[:3])(c)
    QApplication.processEvents()
    badged = [card for card in win.surface.cards.cards if card.card.badge]
    assert len(badged) == 3
    long_name = "Annika Rosenthal"
    assert len(long_name) == 16
    advance = QFontMetrics(style.ui_font(NAME_PT, bold=True)).horizontalAdvance(long_name)
    for card in badged:
        assert card.badge_rect() is not None
        assert card.name_room() >= advance
        assert card.shown_name() == card.card.entry.names[0]


def test_a_16_rider_points_race_keeps_three_standings_rows_on_a_1366_by_768_window(qapp, make_app):
    from PySide6.QtWidgets import QApplication

    from madtracker.ui.cards import short_card_height
    from madtracker.ui.look import apply_look
    from madtracker.ui.surface import RIDER_RESULT_ROWS

    apply_look(qapp)
    c = make_app()
    win = c.main
    win.resize(1366, 768)
    win.show()
    select(c, POINTS)
    late = "Wren Talbot,Iker Solano,Mina Varga,Otto Brennan,Zara Quell,Teo Marchetti".split(",")
    for i, name in enumerate(late):
        rider_id = c.store.add_rider(*name.split()).rider_id
        c.store.add_entry(c.event.event_id, rider_id, 60 + i, local_group="Group B")
        c.store.add_race_entry(c.live.race_id, rider_id)
    c.live.reload()
    c.refresh()
    QApplication.processEvents()
    grid, table = win.surface.cards, win.surface.table
    assert len(grid.cards) == 16
    click(*B_RIDERS[:5])(c)
    record(c)
    click(*B_RIDERS[5:8])(c)
    QApplication.processEvents()
    # Mid-sprint the standings are read: the cards go short and scroll
    # before the table drops under its fewest rows (three, with cards
    # of a finger's size).
    assert table.viewport().height() >= RIDER_RESULT_ROWS * table.rowHeight(0)
    assert {card.height() for card in grid.cards} == {short_card_height(True)}
    assert grid.verticalScrollBar().maximum() > 0
    # Whole rows of cards, none cut by the grid's bottom edge.
    step = short_card_height(True) + grid.grid.spacing()
    assert (grid.height() - 2 + grid.grid.spacing()) % step == 0


def test_a_62_rider_roster_shows_eight_rows_on_a_1366_by_768_window(app):
    from PySide6.QtWidgets import QApplication

    from madtracker.ui import setup as su

    c = app
    win = c.main
    win.resize(1366, 768)
    win.show()
    event_id = c.event.event_id
    for i in range(62 - len(c.store.entries(event_id))):
        rider = c.store.add_rider("Rider", f"Number{i}")
        c.store.add_entry(event_id, rider.rider_id, 300 + i)
    c._after_setup_change()
    c.open_setup()
    QApplication.processEvents()
    setup = win.setup
    # The program gives way first, then the screen scrolls; the roster,
    # the list the scorer works down, keeps its rows.
    assert setup.roster.height() >= setup.table_height(setup.roster, su.ROSTER_MIN_ROWS)
    assert setup.program.height() == setup.program_height(su.PROGRAM_SHORT_ROWS)
    assert setup.event_box.isVisible()


def test_the_window_fits_a_1366_by_768_screen_at_125_percent_and_names_stay_readable(app):
    """About 1093 logical pixels wide there: the side panes give the middle
    the room, and the standings keep a rider's name, not "T..."."""
    from PySide6.QtWidgets import QApplication

    from madtracker.ui.review import NAME_MIN_CHARS

    c = app
    win = c.main
    win.resize(1093, 600)
    win.show()
    select(c, POINTS)
    QApplication.processEvents()
    assert win.width() == 1093
    table = win.surface.table
    floor = table.fontMetrics().averageCharWidth() * NAME_MIN_CHARS
    assert table.columnWidth(2) >= floor


def test_a_long_undo_label_is_cut_on_the_right_and_whole_in_its_tooltip(app):
    from PySide6.QtWidgets import QApplication

    c = app
    win = c.main
    win.resize(1366, 768)
    win.show()
    QApplication.processEvents()
    # Undo takes the surface's width in the bar; a label longer than that is cut.
    win.undo.setFixedWidth(240)
    QApplication.processEvents()
    column = win.program.width()
    text = "Undo: #110 Rosalind Vasquez-Featherstonehaugh gained a lap"
    win.set_undo(text, True)
    QApplication.processEvents()
    # The whole label shows on hover only because it is cut.
    assert win.undo.text() == text and win.undo.is_cut()
    win.set_undo("Undo", True)
    assert not win.undo.is_cut()
    # The label is cut to the button; its length never moves the columns.
    assert win.program.width() == column


def test_the_rulesets_word_for_a_format_heads_the_surface_and_its_line_sits_under_it(app):
    """Section 8: the header says the format as the race's ruleset named it; the
    description, when the venue wrote one, is one dim line under the header
    and takes no room otherwise."""
    c = app
    win = c.main
    race = c.races[ELIMINATION]
    c.store.update_race(
        race.race_id,
        rules={
            **race.rules,
            "format_name": "Devil",
            "format_description": "Last rider over the line every 2 laps is out",
        },
    )
    select(c, ELIMINATION)
    assert win.surface.detail.text() == "Group A  |  Devil"
    riders = len(c.store.race_entries(race.race_id))
    assert riders > 1 and win.surface.field.text() == f"{riders} riders"
    assert win.surface.description.text() == "Last rider over the line every 2 laps is out"
    assert not win.surface.description.isHidden()
    assert win.surface.description.font().pointSize() == win.surface.detail.font().pointSize()
    select(c, CHASE)
    assert win.surface.detail.text() == "Group B  |  Scratch Race"
    assert win.surface.description.isHidden()


def test_one_gap_between_every_pane_and_the_bar(app):
    """The program over the preview on the left, the surface beside them, and
    the bar under both columns, Edit | Score as wide as the program and Undo
    as wide as the surface; every gap the same."""
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from madtracker.ui import style

    win = app.main
    win.resize(1366, 768)
    win.show()
    QApplication.processEvents()
    QTest.qWait(50)  # the bar fits to the columns a turn of the loop later

    def box(w):
        at = w.mapTo(win, QPoint(0, 0))
        return at.x(), at.y(), at.x() + w.width(), at.y() + w.height()

    program, preview = box(win.program.box), box(win.tv)
    middle = box(win.stack)
    switch, undo = box(win.program.mode), box(win.undo)
    gaps = [
        preview[1] - program[3],
        middle[0] - program[2],
        switch[1] - preview[3],
        undo[1] - middle[3],
        undo[0] - switch[2],
    ]
    assert gaps == [style.SM] * 5, gaps
    # The columns start and end together; the bar's controls sit under them.
    assert program[1] == middle[1] and preview[3] == middle[3]
    assert (switch[0], switch[2]) == (program[0], program[2])
    assert (undo[0], undo[2]) == (middle[0], middle[2])
    assert switch[1] == undo[1] and switch[3] == undo[3]


# ----- the window: two columns, the bar, the preview as the TV's control ---


def test_the_title_bar_names_the_event_and_its_date():
    """The event first, as a document's window names it; the app's name alone
    with no event."""
    from madtracker.ui.window import window_title

    assert (
        window_title("Race Night 12", "2026-10-16", "win32")
        == "Race Night 12 (2026-Oct-16) - MadTracker"
    )
    assert (
        window_title("Race Night 12", "2026-10-16", "linux")
        == "Race Night 12 (2026-Oct-16) - MadTracker"
    )
    # macOS names the document alone: the menu bar names the app.
    assert window_title("Race Night 12", "2026-10-16", "darwin") == "Race Night 12 (2026-Oct-16)"
    assert window_title("", "", "darwin") == "MadTracker"
    assert window_title("Race Night 12", "", "win32") == "Race Night 12 - MadTracker"
    assert window_title("Race Night 12", "", "darwin") == "Race Night 12"
    assert window_title("", "") == "MadTracker"


def test_the_program_heads_no_event_when_none_is_open(app):
    from madtracker.ui.window import window_title

    win = app.main
    win.set_event("", "")
    assert win.program.date.text() == "No event" and not win.program.heading.isVisibleTo(win)
    assert win.windowTitle() == "MadTracker"
    assert not win.program.mode.isEnabled()
    win.set_event("Race Night 12", "")
    assert win.program.heading.text() == "Race Night 12"
    assert not win.program.date.isVisibleTo(win), "no date, no empty line"
    assert win.windowTitle() == window_title("Race Night 12", "")
    assert win.program.mode.isEnabled()


def test_the_bar_keeps_edit_score_as_wide_as_the_program_column(app):
    from PySide6.QtTest import QTest

    from madtracker.ui.window import BAR_H

    win = app.main
    win.resize(1366, 768)
    win.show()
    QTest.qWait(50)  # the bar fits to the columns a turn of the loop later
    assert win.program.mode.width() == win.program.width()
    assert win.program.mode.height() >= BAR_H and win.undo.height() >= BAR_H
    win.resize(1920, 1000)
    QTest.qWait(50)
    assert win.program.width() > 300
    assert win.program.mode.width() == win.program.width()


def test_undo_in_the_bar_follows_the_race(app):
    c = app
    win = c.main
    select(c, CHASE)
    assert win.undo.text() == rc.NOTHING_TO_UNDO_LABEL and not win.undo.isEnabled()
    click("4")(c)
    assert win.undo.isEnabled() and win.undo.text().startswith("Undo: #4 ")
    c.open_setup()
    assert not win.undo.isEnabled(), "Undo would change a race the screen hides"
    c.close_setup()
    assert win.undo.isEnabled() and win.undo.text().startswith("Undo: #4 ")


def test_the_surface_goes_side_by_side_from_1300_px(app):
    """Section 7: at 1920 the cards and the standings sit side by side, Record
    Sprint the cards' full width, Mark Final under the table, and a complete
    result with no cards gives the standings the whole width; a 1366 laptop
    stacks them."""
    from PySide6.QtWidgets import QApplication

    from madtracker.ui import surface as su

    c = app
    win = c.main
    s = win.surface
    win.resize(1920, 1000)
    win.show()
    select(c, CHASE)
    QApplication.processEvents()
    assert s.width() >= su.WIDE_W and s.wide
    assert s.final_row.indexOf(s.final_button) >= 0 and s.buttons.indexOf(s.final_button) < 0
    assert s.left_box.isVisibleTo(s) and s.right_box.isVisibleTo(s)
    assert s.left_box.x() < s.right_box.x() and s.left_box.y() == s.right_box.y()
    assert s.record_button.minimumHeight() == su.WIDE_PRIMARY_H
    eids = list(c.live.roster.ids)
    assert c.click(eids[0])
    QApplication.processEvents()
    shown = [b for b in (s.record_button, s.rest_button) if b.isVisibleTo(s)]
    assert shown and all(b.width() == s.left_box.width() for b in shown), "the column's width"
    for eid in eids[1:]:
        assert c.click(eid)
    QApplication.processEvents()
    assert c.live.state == "provisional" and not s.cards.cards
    assert not s.left_box.isVisibleTo(s), "the standings take the whole width"
    assert s.final_button.isVisibleTo(s) and s.final_box.isVisibleTo(s)
    win.resize(1366, 768)
    QApplication.processEvents()
    assert not s.wide
    assert s.buttons.indexOf(s.final_button) >= 0 and not s.final_box.isVisibleTo(s)
    assert s.left_box.isVisibleTo(s) and s.final_button.isVisibleTo(s)
    assert s.record_button.minimumHeight() == su.PRIMARY_H


def test_the_cards_grow_into_their_column_and_shrink_back_when_stacked(app):
    from PySide6.QtWidgets import QApplication

    c = app
    win = c.main
    win.resize(1920, 1000)
    win.show()
    select(c, POINTS)
    QApplication.processEvents()
    grid = win.surface.cards
    assert win.surface.wide and cards.NAME_PT > cards.NAME_PT_BASE
    assert grid.columns() >= 2, "never fewer columns than the base size gives"
    for card in grid.cards:
        assert card.shown_name() == card.card.entry.names[0], "whole names at the larger size"
    win.resize(1366, 768)
    QApplication.processEvents()
    assert not win.surface.wide and cards.NAME_PT == cards.NAME_PT_BASE


def test_a_long_team_name_holds_the_cards_type_down(app):
    """A team card's scale is measured with the team's own name beside its
    swatch, so it never cuts "Stars and Stripes" to "Stars an..."."""
    from PySide6.QtWidgets import QApplication

    c = app
    win = c.main
    mad = c.races[MADISON]
    teams = c.store.teams(mad.race_id)
    c.store.connection.execute(
        "UPDATE team SET name=? WHERE team_id=?", ("Stars and Stripes", teams[0].team_id)
    )
    c.store.connection.commit()
    win.resize(1920, 1000)
    win.show()
    select(c, MADISON)
    QApplication.processEvents()
    grid = win.surface.cards
    assert win.surface.wide
    card = next(w for w in grid.cards if w.card.entry.team == "Stars and Stripes")
    assert card.team_name_fits(card.width()), cards.NAME_PT


def test_a_long_name_gives_the_cards_spare_room_to_the_standings(app):
    """Side by side, a long name holds the cards to one column; the
    column keeps only what its names want, and the standings take the
    rest, so the table shows the name whole beside the cards."""
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    from madtracker.ui import surface as su

    c = app
    win = c.main
    select(c, POINTS)
    rider_id = c.live.roster.resolve("12")
    c.store.update_rider(rider_id, first_name="Christopher", last_name="Vandenberghe-Szczepanski")
    c._reload_races()
    select(c, CHASE)
    win.resize(1920, 1000)
    win.show()
    select(c, POINTS)
    QApplication.processEvents()
    s = win.surface
    grid, table = s.cards, s.table
    assert s.wide and grid.columns() == 1
    margins = s.layout().contentsMargins()
    inner = s.width() - margins.left() - margins.right() - s.body.spacing()
    assert s.left_box.width() < round(inner * su.CARDS_SHARE), "the cards gave room back"
    for card in grid.cards:
        assert card.shown_name() == card.card.entry.names[0], "whole names on the cards"
    row = next(r for r in range(table.rowCount()) if "Vandenberghe" in table.item(r, 2).text())
    name = table.item(row, 2).text()
    assert QFontMetrics(table.font()).horizontalAdvance(name) < table.columnWidth(2)
    assert s.record_button.width() == s.left_box.width(), "Record Sprint is the column's width"


def test_a_twelve_sprint_points_race_keeps_every_column_in_view_side_by_side(app):
    """The scorer checks every sprint by eye: side by side,
    the standings take the width their columns need before the cards get
    their share, so the table never scrolls sideways at 1920."""
    from PySide6.QtWidgets import QApplication

    c = app
    win = c.main
    select(c, POINTS)
    riders = list(c.live.roster.ids)
    points = c.races[POINTS]
    rules = dict(points.rules)
    rules["sprint_count"] = 12
    big = c.store.add_race(
        points.event_id,
        "40 Mile Points",
        "points",
        group_label=points.group_label,
        rules_preset=points.rules_preset,
        rules=rules,
        rules_version=points.rules_version,
    )
    for rider_id in riders:
        c.store.add_race_entry(big.race_id, rider_id)
    c._reload_races()
    win.resize(1920, 1000)
    win.show()
    c.select_race(big.race_id)
    QApplication.processEvents()
    table = win.surface.table
    assert win.surface.wide and len(table.screen.sprint_columns) == 12
    assert table.horizontalScrollBar().maximum() == 0
    assert table.columnWidth(table._name_col) >= table._name_floor()
    assert win.surface.left_box.width() >= cards.CARD_MIN_W


def test_a_madison_row_lists_its_riders_one_per_line_and_caps_the_team_column(app):
    from PySide6.QtWidgets import QApplication

    from madtracker.ui import review, style

    c = app
    win = c.main
    mad = c.races[MADISON]
    teams = c.store.teams(mad.race_id)
    c.store.connection.execute(
        "UPDATE team SET name=? WHERE team_id=?",
        ("Stars and Stripes Racing Club", teams[0].team_id),
    )
    c.store.connection.commit()
    win.resize(1920, 1000)
    win.show()
    select(c, MADISON)
    QApplication.processEvents()
    table = win.surface.table
    riders = [table.item(r, 2).text() for r in range(table.rowCount())]
    assert riders and all("\n" in text and "/" not in text for text in riders), riders
    names = [table.item(r, 1).text() for r in range(table.rowCount())]
    assert "Stars and Stripes Racing Club" in names
    cap = table.fontMetrics().averageCharWidth() * review.TEAM_MAX_CHARS + 2 * style.MD
    assert table.columnWidth(1) <= cap


def test_program_rows_keep_their_height_after_a_race_is_added_and_the_window_widens(app):
    """Program rows keep sizeHintForRow's 50 px after a race is added at
    runtime and the window widens."""
    from PySide6.QtWidgets import QApplication

    from madtracker.ui import program as pg

    c = app
    win = c.main
    win.resize(1600, 900)
    win.show()
    QApplication.processEvents()
    first = c.races[0]
    race = c.store.add_race(first.event_id, "Added Later", "placings", group_label="Group B")
    c._reload_races()
    c.select_race(race.race_id)
    win.resize(1920, 1000)
    QApplication.processEvents()
    lst = win.program.list
    rects = [lst.visualItemRect(lst.item(i)) for i in range(lst.count())]
    assert len(rects) == len(c.races) == 14
    assert [r.height() for r in rects] == [lst.sizeHintForRow(i) for i in range(lst.count())]
    assert all(r.height() >= pg.ROW_H for r in rects)
    for above, below in zip(rects, rects[1:], strict=False):
        assert below.top() == above.bottom() + 1, (above, below)


def test_undo_in_the_bar_names_the_rider_apart_from_the_verb_and_the_place(app, monkeypatch):
    """The controller says which part of the Undo label is the rider, matched
    against the race's own labels, so the button never guesses from a name."""
    from madtracker.ui import icons

    # Leaving the chase mid-scoring asks; the madison is the point here.
    monkeypatch.setattr(icons, "ask", lambda *a, **k: True)
    c = app
    c.select_race(c.races[CHASE].race_id)
    c.click(c.live.roster.resolve("7"))
    assert c.main.undo.text() == "Undo: #7 Maya Petrakis placed 1st"
    assert c.main.undo.who() == "#7 Maya Petrakis"
    assert c.main.undo.runs() == [
        ("Undo:", True),
        ("#7 Maya Petrakis", False),
        ("placed 1st", False),
    ]
    c.rider_action(c.live.roster.resolve("12"), "lap_gained")
    assert c.main.undo.runs() == [
        ("Undo:", True),
        ("#12 Tess Gallagher", False),
        ("gained a lap", False),
    ]
    c.select_race(c.races[MADISON].race_id)
    c.click(c.live.roster.resolve("Blue"))
    assert c.main.undo.runs() == [("Undo:", True), ("Blue", False), ("placed 1st", False)]
    c.undo()
    assert c.main.undo.runs() == [("Nothing to Undo", True)]


def test_every_touch_target_is_a_fingers_size_at_1366_and_1920(app, monkeypatch):
    """The card's -1, +1, and ⋯, a result
    row, and a ⋯ menu's items are at least style.TOUCH on the touchscreen."""
    from PySide6.QtWidgets import QApplication

    from madtracker.ui import icons, style, widgets

    # Leaving the half-clicked Points Race for the chase asks first.
    monkeypatch.setattr(icons, "ask", lambda *a, **k: True)
    c = app
    win = c.main
    win.show()
    select(c, POINTS)
    click(*B_RIDERS[:2])(c)
    # A done card beside the live ones: its ⋯ takes a finger as theirs does.
    status(B_RIDERS[2], "dnf")(c)
    for size in ((1366, 768), (1920, 1080)):
        win.resize(*size)
        for _ in range(4):
            QApplication.processEvents()
        done = [card for card in win.surface.cards.cards if card.card.done]
        assert len(done) == 1 and done[0].dots.isVisible(), size
        for card in win.surface.cards.cards:
            if not card.card.done:
                for button in (card.lap_down, card.lap_up):
                    assert button.width() >= style.TOUCH_LAP, size
                    assert button.height() >= style.TOUCH, size
            assert card.dots.width() >= style.TOUCH and card.dots.height() >= style.TOUCH, size
            # The strip is where the live card's is: the full height inside
            # the border (1 px above, 2 px below), at the card's right edge.
            assert card.dots.width() == cards.strip_width(), size
            assert card.dots.geometry().bottom() == card.height() - 3, size
            assert card.dots.geometry().right() == card.width() - 2, size
        assert win.surface.cards.height() >= win.surface.cards.needed_height(), (
            size,
            "every card in view",
        )
    # A card's ⋯ menu, and the result row's, are the touch menus.
    menus = []
    monkeypatch.setattr(widgets, "run_menu", lambda menu, where: menus.append(menu))
    win.surface.cards.cards[0].open_actions()
    assert menus and menus[-1].objectName() == "touchMenu"
    sub = next((a.menu() for a in menus[-1].actions() if a.menu() is not None), None)
    assert sub is None or sub.objectName() == "touchMenu"
    select(c, CHASE)
    for eid in list(c.live.roster.ids):
        c.click(eid)
    QApplication.processEvents()
    table = win.surface.table
    assert table.rowHeight(0) >= style.TOUCH
    assert table.open_row_menu(0)
    assert menus[-1].objectName() == "touchMenu"


def test_a_team_card_is_one_line_and_its_riders_are_in_the_standings(app):
    """For scoring a Madison the cards need only the color and the team; the
    standings beside them list each team's riders."""
    from PySide6.QtWidgets import QApplication

    from madtracker.ui import cards

    c = app
    win = c.main
    for size in ((1366, 768), (1920, 1080)):
        win.resize(*size)
        win.show()
        select(c, MADISON)
        for _ in range(4):
            QApplication.processEvents()
        team_cards = win.surface.cards.cards
        rider_h = cards.full_card_height()
        assert all(card.height() <= rider_h for card in team_cards), size
        assert win.surface.cards.height() >= win.surface.cards.needed_height(), size
    rows = win.surface.table.screen.rows
    assert all(len(r.entry.names) == 2 for r in rows if r.entry is not None)
    assert "\n" in win.surface.table.item(0, 2).text(), "the riders, in the standings"
    win.resize(1366, 768)
    for _ in range(4):
        QApplication.processEvents()
    assert cards.NAME_PT == cards.NAME_PT_BASE and cards.member_pt() == cards.MEMBER_PT
