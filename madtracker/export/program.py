"""The program sheet: who starts in which race, for the riders and the announcer.

Posted for the riders to find their races, and read by the announcer
before each race to call the riders onto the track.
So every race lists its riders by name, bib first, with the race's
group beside its name and how it scores under it; a Madison lists its
teams. It is printed before racing, and again when a field changes, so
it carries no results and no start times: the night's pace sets those.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from madtracker.control import rulesets
from madtracker.control.formats import TEAM_FORMATS
from madtracker.control.race import rules_for_race
from madtracker.export import pdf as P
from madtracker.export.files import write_replacing
from madtracker.export.summary import sprint_words
from madtracker.scoring import rules as R
from madtracker.store import Race, Store


@dataclass(frozen=True)
class Rider:
    rider_id: int
    bib: int | None
    name: str

    @property
    def listed(self) -> str:
        """'45 Isaac Pell', the bib bare as the rider grid prints it, or the name alone without one."""
        return f"{self.bib} {self.name}" if self.bib is not None else self.name


@dataclass(frozen=True)
class Team:
    color: str
    name: str
    riders: tuple[Rider, ...]


@dataclass(frozen=True)
class ProgramRace:
    number: int
    name: str
    group: str
    format_label: str
    scoring: str
    riders: tuple[Rider, ...] = ()
    teams: tuple[Team, ...] | None = None

    @property
    def empty(self) -> bool:
        return not (self.teams if self.teams is not None else self.riders)


def scoring_text(rules: R._Rules) -> str:
    """How a race scores, as the results sheet says it, less what only checking the sums needs."""
    if isinstance(rules, R.SprintPointsRules):
        return sprint_words(rules)
    if isinstance(rules, R.WinAndOutRules):
        return f"{rules.places} places"
    return ""


def _sort_key(rider: Rider) -> tuple:
    # Bib order, as riders and the announcer look riders up; riders still
    # without a bib follow, by name.
    return (rider.bib is None, rider.bib or 0, rider.name.casefold())


def build_program(store: Store, event_id: int) -> list[ProgramRace]:
    """The event's races in program order, each with its riders or teams."""
    riders: dict[int, Rider] = {}
    for entry, r in store.entries_with_riders(event_id):
        riders[entry.rider_id] = Rider(entry.rider_id, entry.bib, r.name)
    return [
        _program_race(store, n, race, riders) for n, race in enumerate(store.races(event_id), 1)
    ]


def _program_race(store: Store, number: int, race: Race, riders: dict[int, Rider]) -> ProgramRace:
    head = dict(
        number=number,
        name=rulesets.race_short_name(race),
        group=race.group_label,
        format_label=rulesets.race_format_name(race),
        scoring=scoring_text(rules_for_race(race, store)),
    )
    if race.format in TEAM_FORMATS:
        teams = []
        for t in store.teams(race.race_id):
            members = tuple(riders[m] for m in t.members if m in riders)
            # A team named for its color would print the color twice.
            same = (t.name or "").strip().casefold() == (t.color or "").strip().casefold()
            teams.append(Team(t.color or "", "" if same else t.name or "", members))
        return ProgramRace(**head, teams=tuple(teams))
    field = [riders[e.rider_id] for e in store.race_entries(race.race_id) if e.rider_id in riders]
    return ProgramRace(**head, riders=tuple(sorted(field, key=_sort_key)))


def detail_text(race: ProgramRace) -> str:
    """The format, then how the race scores.

    The format prints under every race, a name that says it included:
    a line under some races and none under others read as an omission.
    """
    return "  |  ".join(t for t in (race.format_label, race.scoring) if t)


# ----- the PDF -----------------------------------------------------------

ROW_PT = 11.5
ROW_H = 6.4
COLUMNS = 3
BIB_W = 11.0
TEAM_LABEL_W = 24.0
GAP = 3.0
# A long name shrinks to this before its race drops a column, as far as
# the results sheet lets a name shrink.
NAME_MIN_PT = ROW_PT * 0.7


def _columns(pdf: P._Doc, race: ProgramRace) -> int:
    """Three columns of riders, or fewer when a name would not fit one.

    A name too wide even for the one column of the page is still cut
    with an ellipsis, as the results sheet cuts it.
    """
    pdf.use("", NAME_MIN_PT)
    widest = max((pdf.get_string_width(pdf.txt(r.name)) for r in race.riders), default=0.0)
    for n in (COLUMNS, 2):
        if widest <= pdf.usable / n - BIB_W - 2 - 2 * pdf.c_margin:
            return n
    return 1


def _team_lines(pdf: P._Doc, team: Team, width: float) -> list[str]:
    """The team's name and its riders on one line, or one per line when that does not fit.

    A pair that wraps goes one rider a line, as every surface with the
    height lists a pair, so no name is split across two lines.
    """
    riders = [r.listed for r in team.riders]
    joined = (f"{team.name}: " if team.name else "") + " / ".join(riders)
    kept = len(pdf.unprintable)
    lines, _ = P._wrap_lines(pdf, joined, width, "", ROW_PT, ROW_PT * 0.85, 1)
    del pdf.unprintable[kept:]
    if len(riders) < 2 or lines[0] == pdf.quiet(joined):
        # The export's warning names the line whole, not its trial pieces.
        pdf.txt(joined)
        return lines
    out: list[str] = []
    for text in ([team.name] if team.name else []) + riders:
        out += P._wrap_lines(pdf, text, width, "", ROW_PT, ROW_PT * 0.85, 1)[0]
    return out


def _heading(pdf: P._Doc, race: ProgramRace, more: bool) -> P.Heading:
    """The results sheet's heading, with the program's count in its right slot."""
    detail = "" if more else detail_text(race)
    return P.lay_heading(pdf, race.number, race.name, race.group, detail, right=True, more=more)


def _heading_h(pdf: P._Doc, race: ProgramRace) -> float:
    return _heading(pdf, race, False).height + 1.5


def _rows_h(pdf: P._Doc, race: ProgramRace) -> float:
    if race.empty:
        return ROW_H
    if race.teams is not None:
        width = pdf.usable - TEAM_LABEL_W
        return sum(len(_team_lines(pdf, t, width)) for t in race.teams) * ROW_H
    return -(-len(race.riders) // _columns(pdf, race)) * ROW_H


def _race_heading(pdf: P._Doc, race: ProgramRace, y: float, *, more: bool = False) -> float:
    top = y
    y = P.draw_heading(pdf, _heading(pdf, race, more), y)
    if not race.empty:
        n = len(race.teams) if race.teams is not None else len(race.riders)
        noun = "team" if race.teams is not None else "rider"
        count = f"{n} {noun}{'' if n == 1 else 's'}"
        pdf.set_text_color(*P.MUTED)
        x = P.MARGIN + pdf.usable - P.RIGHT_W
        P._text(pdf, x, top + 0.3, P.RIGHT_W, P.HEADING_H, count, "R", "", P.DETAIL_PT + 1)
        pdf.set_text_color(*P.INK)
    return y + 1.5


def _rider(pdf: P._Doc, rider: Rider, x: float, y: float, w: float) -> None:
    pdf.set_text_color(*P.MUTED)
    bib = "" if rider.bib is None else str(rider.bib)
    P._text(pdf, x, y, BIB_W, ROW_H, bib, "R", "B", ROW_PT)
    pdf.set_text_color(*P.INK)
    P._text(pdf, x + BIB_W + 1, y, w - BIB_W - 2, ROW_H, rider.name, "L", "", ROW_PT, NAME_MIN_PT)


def _race_block(pdf: P._Doc, race: ProgramRace, y: float) -> float:
    """One race: its heading, then its riders down then across, kept on one page when they fit."""
    head = _heading_h(pdf, race)
    need = head + _rows_h(pdf, race)
    fresh = pdf.bottom - pdf.later_top
    # A race starts on a fresh page rather than split, unless it is too
    # long for any page; then it at least starts with a few riders.
    y = _room(pdf, y, need if need <= fresh else head + 3 * ROW_H)
    y = _race_heading(pdf, race, y)
    x0 = P.MARGIN
    width = pdf.usable
    if race.empty:
        pdf.set_text_color(*P.MUTED)
        P._text(pdf, x0, y, width, ROW_H, "No riders yet", "L", "", ROW_PT)
        pdf.set_text_color(*P.INK)
        return y + ROW_H + GAP
    if race.teams is not None:
        for team in race.teams:
            lines = _team_lines(pdf, team, width - TEAM_LABEL_W)
            if y + len(lines) * ROW_H > pdf.bottom:
                pdf.add_page()
                y = _race_heading(pdf, race, pdf.body_top, more=True)
            P._text(pdf, x0, y, TEAM_LABEL_W, ROW_H, team.color or "Team", "L", "B", ROW_PT)
            for line in lines:
                P._text(
                    pdf,
                    x0 + TEAM_LABEL_W,
                    y,
                    width - TEAM_LABEL_W,
                    ROW_H,
                    line,
                    "L",
                    "",
                    ROW_PT,
                    ROW_PT * 0.85,
                )
                y += ROW_H
        return y + GAP
    columns = _columns(pdf, race)
    col_w = width / columns
    left = list(race.riders)
    while left:
        rows_free = max(1, int((pdf.bottom - y) // ROW_H))
        per_col = min(rows_free, -(-len(left) // columns))
        chunk, left = left[: per_col * columns], left[per_col * columns :]
        for i, rider in enumerate(chunk):
            col, row = divmod(i, per_col)
            _rider(pdf, rider, x0 + col * col_w, y + row * ROW_H, col_w)
        y += per_col * ROW_H
        if left:
            pdf.add_page()
            y = _race_heading(pdf, race, pdf.body_top, more=True)
    return y + GAP


def _room(pdf: P._Doc, y: float, need: float) -> float:
    """``y`` if ``need`` fits on this page, else the top of a fresh one."""
    if y + need <= pdf.bottom:
        return y
    pdf.add_page()
    return pdf.body_top


def write_program_pdf(
    store: Store,
    event_id: int,
    path: str | Path,
    *,
    generated: datetime | None = None,
    unprintable: list[str] | None = None,
) -> Path:
    """Write the event's program sheet to ``path``: each race with its riders or teams."""
    event = store.event(event_id)
    venue, logo = P.masthead(store, None, None, event.venue)
    subtitle = ["Program", P._pretty_date(event.event_date)]
    if event.series:
        subtitle.append(event.series)
    if venue and logo:
        subtitle.append(venue)
    footer = P.footer_line(event.name, generated)
    pdf = P.new_doc(
        title=event.name,
        subtitle="  |  ".join(subtitle),
        logo=logo,
        venue=venue,
        footer_text=footer,
        doc_title=f"{event.name} program",
    )
    pdf.add_page()

    races = build_program(store, event_id)
    y = pdf.body_top
    if not races:
        P._text(pdf, P.MARGIN, y, pdf.usable, 8, "No races yet", "L", "", 11)
    for race in races:
        y = _race_block(pdf, race, y)

    try:
        out = write_replacing(path, lambda partial: pdf.output(str(partial)))
    finally:
        pdf.close_fonts()
    if unprintable is not None:
        unprintable.extend(pdf.unprintable)
    return out
