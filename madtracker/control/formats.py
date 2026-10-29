"""The race formats the program offers, and the one label each goes by.

USAC is the ground rule: a format is offered when the USA Cycling
Rulebook has an article for it, or, as a club format, when a named
venue is documented running it (docs/scoring-rules.md, "Formats").
The keys are stored in the data file, so they never change; "chase"
stays the scratch race's key although the label follows the book.

A label is the format's proper name in Title Case, with no synonym in
it: a venue's own word for a format (the chase, the devil) goes in
its ruleset. A list of formats (the race dialog's picker, the ruleset
editor) shows each with its source, "Handicap (USAC 2D)" or "Chariot
(Club)"; everywhere else (the program table, the PDF, the board) shows
the plain label, so a format reads the same on every screen and sheet.
"""

from dataclasses import dataclass

from madtracker.scoring.rules import RULEBOOK_TITLE, RULEBOOK_VERSION

# A team race's field is its teams: entrants are team ids, and the
# race dialog builds the field from the teams rather than a group.
TEAM_FORMATS = frozenset({"madison"})
# How many riders a team has in each team format (UCI 3.2.077, 3.2.144);
# a format not listed takes two or more.
TEAM_SIZE = {"madison": 2}
# Finish-order formats decided on the line alone: a chariot, a keirin
# final and a match sprint final rank no one by laps, so the rider's
# menu offers no laps and the race is saved with laps off the ranking.
NO_LAP_FORMATS = frozenset({"chariot", "keirin", "match_sprint"})

# The usual jersey colors, in the order teams usually get them, and the
# one hex each is drawn in on the screen, the board and the PDF.
TEAM_COLORS: dict[str, str] = {
    "Blue": "#2f6bff",
    "Red": "#e5323b",
    "Orange": "#ff8a1f",
    "Yellow": "#ffe419",
    "Black": "#16181c",
    "Green": "#2e9e4f",
    "White": "#f4f4f4",
    "Pink": "#ff6fb1",
    "Purple": "#8e4bd6",
    "Silver": "#b8bec7",
    "Brown": "#7a4a24",
    "Tan": "#d2b48c",
}


@dataclass(frozen=True)
class Format:
    key: str
    label: str
    # The USA Cycling Rulebook article; None marks a club format.
    article: str | None = None

    @property
    def source(self) -> str:
        """Whose format it is: "USAC 2D" or "Club"."""
        return f"USAC {self.article}" if self.article else "Club"

    @property
    def source_text(self) -> str:
        """The label with its source, in the one form every list of formats uses."""
        return f"{self.label} ({self.source})"


FORMATS: tuple[Format, ...] = (
    Format("chase", "Scratch Race", "2C"),
    Format("handicap", "Handicap", "2D"),
    # Some tracks still call it the miss-and-out, the name USAC 2E5 gives it.
    Format("elimination", "Elimination", "2E"),
    Format("match_sprint", "Sprint Final", "2F"),
    Format("keirin", "Keirin Final", "2H"),
    Format("points", "Points Race", "2M"),
    Format("madison", "Madison", "2N"),
    Format("tempo", "Tempo Race", "2P"),
    Format("unknown_distance", "Unknown Distance"),
    Format("chariot", "Chariot"),
    Format("win_and_out", "Win-and-Out"),
)
FORMAT_LABELS: dict[str, str] = {f.key: f.label for f in FORMATS}
# A new race starts on the format a night runs most.
DEFAULT_FORMAT = "chase"

USAC_HEADER = f"{RULEBOOK_TITLE} {RULEBOOK_VERSION}"
CLUB_HEADER = "Club Formats"


def picker_groups() -> list[tuple[str, list[Format]]]:
    """The picker's two groups, each sorted by label, under its header."""

    def by_label(formats: list[Format]) -> list[Format]:
        return sorted(formats, key=lambda f: f.label.casefold())

    return [
        (USAC_HEADER, by_label([f for f in FORMATS if f.article])),
        (CLUB_HEADER, by_label([f for f in FORMATS if not f.article])),
    ]


def format_label(key: str) -> str:
    return FORMAT_LABELS.get(key) or key.replace("_", " ").capitalize()
