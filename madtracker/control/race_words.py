"""The words of the scoring surface and the log: menus, task and refusal lines, Undo's labels.

The keys the menus carry sit beside their words, so a menu, the
controller that acts on it, and the Undo label read from one table.
The notes a correction or an undo writes into the log are here too,
since the log is read back by their words.
"""

from madtracker.control.describe import race_ended_note, race_shortened_note

# The rider's menu, in the design's order; the menu shows the words, the
# log and the sheet show the code. Out of the finish sits with Did not
# finish, the other way a rider misses the line; it is offered only in
# the final sprint of a Points Race, Madison or Tempo Race. Withdrawn
# follows them, the third way: a rider the officials pulled, or one the
# rule classifies as though pulled, placed by that moment (USAC 2O3(e),
# 1M6(d)); it is offered where Did not finish is, in a race placed at the
# line, a Points Race, a Madison, or a Tempo Race, to a rider without a
# place in the sprint or finish being clicked, and not while a sprint is
# reopened. The two
# rulings (USAC 8D5(b), 8D5(c), 2N3(e)) sit before Disqualify: a
# penalty sets the rider's penalty in points, a lap not counted takes
# back a lap gained, and both are offered while the race runs and once
# its result is complete.
RIDER_ACTIONS: dict[str, str] = {
    "dns": "Did Not Start",
    "dnf": "Did Not Finish",
    "out_of_finish": "Out of the Finish (Mishap)",
    "withdrawn": "Withdrawn",
    "lap_gained": "Gained a Lap",
    "lap_lost": "Lost a Lap",
    "points_penalty": "Points Penalty...",
    "lap_not_counted": "Lap Not Counted",
    "dq": "Disqualify",
}
# The race's own menu, on the task line's ⋯: the officials' calls on the
# race as a whole, not on a rider, which no rider's menu can say. A Points
# Race or Madison stopped after 80 percent is not restarted and its
# results stand (USAC 2M6, 2N5); a race the Chief Referee shortens rides
# on to a new, earlier finish (USAC 1G4(b)). The ellipsis says the item
# asks first.
RACE_ACTIONS: dict[str, str] = {
    "end_race": "End Race Now, Result As-Is...",
    "shorten_race": "Shorten Race...",
}
# The menu's key for a penalty carries no number (the dialog asks for
# it); the key act() and review() record is "points_penalty:5", and the
# number is the rider's whole penalty from then on, not an amount added:
# the result has one Penalty figure per rider, so that is the number the
# scorer keeps (0 takes the penalty off), and two rulings and a reversal
# are one dialog each. The log stores the difference, so the engines,
# the files, and the sheet read it as any other points entry.
PENALTY = "points_penalty:"
ACTION_CODES = {"dns": "DNS", "dnf": "DNF", "dq": "DQ"}
# The Undo button reads "Undo:" and then what was done, as a sentence in
# the past tense, who first: "Undo: #7 Maya Petrakis placed 2nd", "Undo:
# Yellow lost a lap", "Undo: #12 Tess Gallagher marked Did Not Finish",
# "Undo: Sprint 3 recorded": the label says what was done, never that
# something was clicked or tapped. The verbs are
# lowercase, as words in a sentence; the names of things the UI shows
# keep its spelling (a status, "Sprint 3", "Final sprint"), and riders'
# and teams' names stay as typed, which is why the case is set here,
# word by word, and never on the whole label.
UNDO_WORDS: dict[str, str] = {
    "dns": "marked Did Not Start",
    "dnf": "marked Did Not Finish",
    "out_of_finish": "marked Out of the Finish (Mishap)",
    "withdrawn": "marked Withdrawn",
    "lap_gained": "gained a lap",
    "lap_lost": "lost a lap",
    "points_penalty": "penalty set to",
    "lap_not_counted": "marked Lap Not Counted",
    "dq": "marked Disqualified",
    "out": "marked Eliminated",
}
# A dead heat in a sprint being built: on the card of the rider placed
# after another, because in a points race the card is the only place the
# staged order shows. The label names the noun ("team" in a madison).
TIE_ABOVE = "tie_above"
# The same tie from the row above: the rider below joins this place. The
# scorer's eye is on the rider just clicked, the upper row, so it offers
# the tie too. Either row records the one tie.
TIE_BELOW = "tie_below"
# A rider placed from the back of a finish order: the officials often know
# the last places early (a dropped rider, lapped riders) while the bunch
# is still unsorted, and clicking from the front cannot record that.
# First on the card's menu, as the tie
# is: it belongs to the task on screen.
PLACE_LAST = "place_last"
PLACE_LAST_LABEL = "Place Last"
# The button that gives everyone still unplaced one equal placing between
# the front and the back (USAC 1M6(a)): the middle of a bunch nobody
# separates. The result is a tied group, as a dead heat is.
REST_TOGETHER_LABEL = "Place the Rest Together"
# The result row's menu (docs/design.md section 8).
REVIEW_ACTIONS: dict[str, str] = {
    "move_up": "Move Up",
    "move_down": "Move Down",
    # The key carries the target group's index ("move_to:2"); the label
    # names the place the rider would take, and the menu folds the lot
    # into one submenu with this word.
    "move_to": "Move to Place",
    "tie_above": "Tie with the Rider Above",
    "tie_below": "Tie with the Rider Below",
    "dq": "Disqualify",
}
TIES = (TIE_ABOVE, TIE_BELOW)
MOVE_TO = "move_to:"
# The one-step moves, on a result row and on a badged card alike.
MOVES = ("move_up", "move_down")
# Moving up a rider who shares a place takes them out of the tie and
# passes nobody, so the menu reads Break Tie there; the key stays
# move_up (the surface's words, said once for the card and the row).
BREAK_TIE = "Break Tie"
# A move with nowhere to go, wherever it was asked for.
NO_MOVE = "There is no place to move to."

FINAL_TEXT = "Marked final. Reopen to correct."
REVIEW_TEXT = "Check the result, then Mark Final."
NOBODY_LEFT = "Nobody is left in the race."
EMPTY_FIELD = "The field is empty. Edit Event > Roster."
# A team race's field is its teams, made in the race's own dialog, so the
# Roster (where EMPTY_FIELD sends the scorer) cannot fix it.
NO_TEAMS = "No teams yet. Edit Event > Program > Edit..."
NOTHING_TO_UNDO = "Nothing to undo"
# The button's own words for the same, in title style.
NOTHING_TO_UNDO_LABEL = "Nothing to Undo"
CANCEL_CORRECTION = "Cancel Correction"
REOPEN_FIRST = "Reopen First to Undo"
# One correction at a time: a second reopen, Mark Final, or a row's menu
# while a sprint is reopened.
CORRECTION_OPEN = "Record or cancel the correction first."
# Undo names a correction by the rider it moved: "Undo: Finish recorded"
# after a moved row reads as deleting the result.
UNDO = "Undo: "
# Everyone unplaced given one place: the finish it records, said as such.
UNDO_REST = f"{UNDO}the rest placed together"


def undo_moved(label: str, how: str = "") -> str:
    """The Undo label of a move, staged or in review: who moved, and where when known.

    ``how`` is "up", "down", or "to 3rd".
    """
    return f"{UNDO}{label} moved {how}".rstrip()


def undo_tied(label: str, other: str = "") -> str:
    """The Undo label of a tie: the rider who joined the place above, and with whom."""
    return f"{UNDO}{label} tied with {other}" if other else f"{UNDO}{label} tied"


def undo_race_ended(after_sprint: int) -> str:
    """The Undo label of a race ended early: no rider to name, so the event
    itself in the past tense, in the words the sheet's note uses."""
    note = race_ended_note(after_sprint)
    return f"{UNDO}{note[:1].lower()}{note[1:]}"


def undo_shortened(to_count: int) -> str:
    """The Undo label of a race shortened: "Undo: race shortened to 3 sprints"."""
    note = race_shortened_note(None, to_count)
    return f"{UNDO}{note[:1].lower()}{note[1:]}"


def undo_swapped(label: str, other: str) -> str:
    """The Undo label of two lap winners swapped."""
    return f"{UNDO}{label} and {other} swapped"


def move_how(key: str, menu_label: str = "") -> str:
    """A move's direction as the Undo label says it, from its key and its menu label.

    A long move's key carries a group index, not a place; the menu's
    label ("Move to 3rd") names the place the rider took.
    """
    if key == "move_up":
        return "up"
    if key == "move_down":
        return "down"
    if key.startswith(MOVE_TO) and menu_label.startswith("Move to "):
        return "to " + menu_label[len("Move to ") :]
    return ""


CONFLICT_TEXT = "Another window changed this race; reopened"

# Operator notes, so the log says what happened: a void a correction
# wrote, and a row Undo put back.
REENTERED = "corrected"
# A correction's own words in its first row's note ("Moved #7 Maya Petrakis
# to 2nd"): the log shows them above the new entry, since the two
# orders alone do not say who moved.
SAID = "said:"
RESTORED = "restored by undo"
# A row Undo writes again only so the rows it restores keep their place
# in the order: its entry is unchanged.
KEPT_IN_ORDER = "kept in order by undo"
