"""Plain data the scoreboard layouts render.

The scoreboard never reads the store or runs scoring. Whatever computes
standings hands it one of these values, so the board is driven the same
way by sample data and by the scoring package.
"""

from dataclasses import dataclass, field, is_dataclass
from typing import Any

MINUS = "−"


def lap_text(n: int) -> str:
    """A net lap count as every surface writes it: "+1", "−1", empty when even.

    One spelling for the window, the board and the PDF; the minus sign is
    as wide as the plus, so a column of lap counts lines up.
    """
    if not n:
        return ""
    return f"+{n}" if n > 0 else f"{MINUS}{-n}"


def ordinal(n: int) -> str:
    """A place as the board and the scorer's window both word it: "1st", "12th"."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def total_text(n: int | float) -> str:
    """A total as every surface writes it: plain when zero or above, the
    same minus as lap_text below zero, so a penalty and the total it made
    negative read alike on one row."""
    text = f"{n:g}" if isinstance(n, float) and not n.is_integer() else str(int(n))
    return text.replace("-", MINUS, 1) if n < 0 else text


def lap_words(n: int) -> str:
    """A net lap count as a tag beside a name: "+1 lap", "−2 laps"."""
    if not n:
        return ""
    return f"{lap_text(n)} lap{'' if abs(n) == 1 else 's'}"


@dataclass
class Entry:
    """A rider, or a madison team of two, as one row on the board.

    Teams carry a team name and its color, drawn as one team block, so the
    audience can match the row to the jerseys; single riders leave both
    empty.
    """

    bibs: list[str]
    names: list[str]
    team: str | None = None
    color: str | None = None


@dataclass
class Header:
    """What the top bar shows for the current race.

    ``race_id`` is not drawn: the board keeps what it has shown per race
    (which riders were out when the elimination page was last up), so a
    switch to another race or back is never taken for a new elimination.
    """

    title: str
    group: str = ""
    detail: str = ""
    status: str = ""
    race_id: int = 0


@dataclass
class PreRace:
    header: Header
    roster: list[Entry]
    # Net laps per roster entry, in roster order; empty when nobody has one.
    laps: list[int] = field(default_factory=list)


@dataclass
class Elimination:
    header: Header
    remaining: list[Entry]
    last_eliminated: Entry | None = None
    # Earlier eliminations, oldest first, shown small so a late arrival in
    # the stands can follow the story without the board getting busy.
    eliminated: list[Entry] = field(default_factory=list)


@dataclass
class StandingRow:
    rank: int
    entry: Entry
    # One value per sprint; None for a sprint not yet run.
    sprints: list[int | None]
    laps: int = 0
    lap_points: int = 0
    # The officials' points rulings, negative for a penalty and 0 when
    # there is none; the board writes it as it writes a lap lost ("−5").
    penalty: int = 0
    total: int = 0
    status: str = ""


@dataclass
class SprintResult:
    """The short overlay shown after a sprint, before the board returns to standings."""

    number: int
    placings: list[tuple[int, Entry, int]]
    # The race's sprint count, so the card can say "of 3" or "Final
    # sprint"; None while a race run with sprints as called has not yet
    # reached its finish.
    of: int | None = None


@dataclass
class Standings:
    """Points race and madison table, in the house sheet's column order."""

    header: Header
    sprint_count: int
    rows: list[StandingRow]
    # The sprint most recently scored, highlighted so the audience sees
    # which column just changed.
    current_sprint: int | None = None
    sprint_result: SprintResult | None = None


@dataclass
class Placing:
    place: int
    entry: Entry
    note: str = ""
    laps: int = 0


@dataclass
class Finish:
    header: Header
    placings: list[Placing]


@dataclass
class Between:
    header: Header
    next_title: str
    next_group: str = ""
    next_detail: str = ""
    next_roster: list[Entry] = field(default_factory=list)
    last_title: str = ""
    last_group: str = ""
    last_placings: list[Placing] = field(default_factory=list)


# Which payload each layout takes; the board checks each payload against it.
LAYOUT_PAYLOADS: dict[str, type] = {
    "pre_race": PreRace,
    "elimination": Elimination,
    "sprint_points": Standings,
    "madison": Standings,
    "finish": Finish,
    "between": Between,
}


def coerce(cls: type, data: Any) -> Any:
    """Pass ``data`` through when it is a ``cls``; anything else is a caller's slip."""
    if data is None or (is_dataclass(data) and isinstance(data, cls)):
        return data
    raise TypeError(f"expected {cls.__name__}, got {type(data).__name__}")
