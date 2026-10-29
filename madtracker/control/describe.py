"""A rider in running text: the bib with its hash, then the name.

The record of entries, Undo and the setup screen all write a rider the
same way, so a one-digit slip reads back as the wrong person, which is
the cheapest way to catch it.
"""

# A status code in words, for beside a name: the review's tip, the
# board's note and the sheet, so the three say it the same way.
STATUS_WORDS = {"DNF": "Did not finish", "DNS": "Did not start", "DQ": "Disqualified"}
# A rider a mishap kept out of the finish, placed on points (USAC 2M7(b),
# 2M8(a)): the card's action, the log's line and the note beside the
# name on the result, the board and the sheet, all the same words.
OUT_OF_FINISH = "Out of the finish (mishap)"
# A rider withdrawn, or classified as though withdrawn, and placed by the
# moment of it (USAC 2O3(e), 1M6(d)): the note beside the name on the
# result, the board and the sheet.
WITHDRAWN = "Withdrawn"


def race_ended_note(after_sprint: int) -> str:
    """ "Race ended after 2 sprints": a race the officials stopped short of its distance
    with its results standing (USAC 2M6, 2N5). The sheet's gray line, the task
    line, the log, and Undo say it in these words."""
    return f"Race ended after {after_sprint} sprint{'' if after_sprint == 1 else 's'}"


def race_shortened_note(from_count: int | None, to_count: int) -> str:
    """ "Race shortened from 4 to 3 sprints": a race the officials shortened to
    fewer sprints, ridden on to its new finish (USAC 1G4(b)). The sheet's gray
    line names both counts, since its rules line names only the one ridden;
    the log and Undo, with no count before it to hand, say "Race
    shortened to 3 sprints"."""
    sprints = f"{to_count} sprint{'' if to_count == 1 else 's'}"
    if from_count is None:
        return f"Race shortened to {sprints}"
    return f"Race shortened from {from_count} to {sprints}"


def lap_not_counted_note(n: int) -> str:
    """The ruling beside a rider's name on the sheet and in the table's tip:
    "Lap not counted", or "2 laps not counted"."""
    if n <= 0:
        return ""
    return "Lap not counted" if n == 1 else f"{n} laps not counted"


def row_note(out_of_finish: bool, laps_not_counted: int, withdrawn: bool = False) -> str:
    """Why a placed row is not a plain finish, every reason that applies."""
    parts = [OUT_OF_FINISH] if out_of_finish else []
    if withdrawn:
        parts.append(WITHDRAWN)
    if laps_not_counted:
        parts.append(lap_not_counted_note(laps_not_counted))
    return "; ".join(parts)


def bib_text(bib: int | str) -> str:
    """``#12``: a bib in running text.

    The hash keeps a bib from reading as part of the name or as a count
    ("3 Marcus Delgado"); a table gives the bib its own column instead.
    """
    return f"#{bib}"


def who(bib: int | str | None, name: str) -> str:
    """``#12 Tess Gallagher``: one rider in running text, bib first."""
    if bib is None or bib == "":
        return name
    return f"{bib_text(bib)} {name}" if name else bib_text(bib)
