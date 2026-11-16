"""The Madison table's idle rotation: the names view, then the color view, on a timer.

The riders' names lead, so the names view holds longest; the color view
gives the stands the team's color and name for a few seconds, which is
how a rider who cannot match surnames to jerseys finds a team (design
section 10). Everything here is a pure function of the milliseconds
since the rotation started, so a test steps it with a ``ManualClock``
and a frame needs no state of its own.
"""

from dataclasses import dataclass

from madtracker.board.motion import ease_out, phase

# How long each view holds once every row has finished changing.
NAMES_MS = 10000
COLOR_MS = 4000
# Within one row's change to the color view: the surnames fade out first,
# the color sweeps across the name area, and the team's name rises in as
# the sweep settles, so the two kinds of type are never on the row at full
# strength together.
NAMES_FADE_MS = 250
SWEEP_MS = 600
LABEL_AT_MS = 450
LABEL_MS = 300
# Each row starts its change this long after the row above it, so the
# change reads as one motion down the table.
ROW_STAGGER_MS = 80


@dataclass(frozen=True)
class RowLook:
    """How far one row stands toward the color view, each part 0..1.

    ``sweep`` is the solid color's reach across the name area, ``names``
    the surnames' opacity, and ``label`` the team name's.
    """

    sweep: float
    names: float
    label: float


NAMES = RowLook(0.0, 1.0, 0.0)
COLOR = RowLook(1.0, 0.0, 1.0)


def change_ms(rows: int) -> float:
    """How long a change between views takes, from the first row's start to the last row's end."""
    return (max(1, rows) - 1) * ROW_STAGGER_MS + max(SWEEP_MS, LABEL_AT_MS + LABEL_MS)


def cycle_ms(rows: int) -> float:
    """One names view, its change to color, the color view, and the change back."""
    return NAMES_MS + change_ms(rows) + COLOR_MS + change_ms(rows)


def _toward_color(ms: float) -> RowLook:
    """One row ``ms`` into its change to the color view."""
    if ms <= 0:
        return NAMES
    return RowLook(
        sweep=ease_out(phase(ms, 0, SWEEP_MS)),
        names=1.0 - ease_out(phase(ms, 0, NAMES_FADE_MS)),
        label=ease_out(phase(ms, LABEL_AT_MS, LABEL_MS)),
    )


def look(since: float, row: int, rows: int) -> RowLook:
    """Row ``row`` of ``rows``, ``since`` ms after the rotation started.

    The change back to names is the change to color run backward in time,
    so it plays the same motion in reverse.
    """
    s = max(0.0, since) % cycle_ms(rows)
    change = change_ms(rows)
    if s < NAMES_MS:
        return NAMES
    s -= NAMES_MS
    if s < change:
        return _toward_color(s - row * ROW_STAGGER_MS)
    s -= change
    if s < COLOR_MS:
        return COLOR
    s -= COLOR_MS
    return _toward_color(change - s - row * ROW_STAGGER_MS)


def moving(since: float, rows: int) -> bool:
    """Whether a change between views is playing ``since`` ms after the rotation started."""
    s = max(0.0, since) % cycle_ms(rows)
    change = change_ms(rows)
    return NAMES_MS <= s < NAMES_MS + change or s >= NAMES_MS + change + COLOR_MS


def until_change(since: float, rows: int) -> float:
    """Milliseconds from ``since`` to the start of the next change; 0 while one plays."""
    if moving(since, rows):
        return 0.0
    s = max(0.0, since) % cycle_ms(rows)
    if s < NAMES_MS:
        return NAMES_MS - s
    return NAMES_MS + change_ms(rows) + COLOR_MS - s


def page_at(since: float, rows: int, pages: int) -> int:
    """The page in view: each page shows names, then color, then the next page turns up."""
    return int(max(0.0, since) // cycle_ms(rows)) % max(1, pages)


def resumed(held: float, rows: int) -> float:
    """Where the rotation picks up after it held at ``held`` while scores played.

    A table held on the names view starts its names hold over on the same
    page. A table held anywhere else goes back to names through the
    change back, from the point whose look is the held one, so no row
    jumps; the names hold follows.
    """
    held = max(0.0, held)
    cycle = cycle_ms(rows)
    base = (held // cycle) * cycle
    s = held - base
    change = change_ms(rows)
    back = NAMES_MS + change + COLOR_MS
    if s <= NAMES_MS:
        return base
    if s < NAMES_MS + change:
        # The change back runs the change to color backward in time.
        return base + back + (NAMES_MS + change - s)
    if s < back:
        return base + back
    return held
