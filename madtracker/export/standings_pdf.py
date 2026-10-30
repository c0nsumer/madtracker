"""The standings PDF: a multi-race standings as the scorer's own sheet keeps it.

The third document on the results sheet's header (band, running header,
footer, headings, and tags all come from ``export.pdf``), so the three
read as one set. Under the band: the standings' name with its state tag,
and a gray line saying how it scores and which events it covers. Then one
table per group, as the scorer keeps one tab per group: place, the team
(swatch, name, and riders) or the rider (bib and name), one column per
counting race headed by its event's date, and the total at the right.
Under the tables, which races count, and any left out or not yet raced,
so a mid-season sheet reads right without the data file at hand.

The numbers come from ``control.multi_race.compute``, which replays every
race; nothing here sums anything.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from madtracker.board.payloads import lap_text
from madtracker.control.exports import _safe
from madtracker.control.multi_race import (
    NO_GROUP,
    GroupTable,
    MultiRaceRow,
    MultiRaceTable,
    RaceColumn,
    Refusal,
    compute,
)
from madtracker.dates import short_date, show_date
from madtracker.export import pdf as P
from madtracker.export import table as T
from madtracker.export.files import write_replacing
from madtracker.export.summary import COLOR_HEX, NEUTRAL_HEX, format_number
from madtracker.store import Store

# The place, bib, penalty, and total columns are the results sheet's
# (``export.table``); the omnium penalty is there only when a ranked row
# carries one, as on the results sheet. A race column is sized to the
# group's own widest race figure (an omnium's 40) and the Total to its
# widest total, so one three-digit total widens only its own column.
# A race column is no wider than RACE_MAX, so the figures sit near their
# headers. With more races the team column gives way first, its names
# wrapping, down to TEAM_MIN; then the race columns narrow to what the widest figure
# needs at RACE_PT. Only past that, with the team column at TEAM_FLOOR,
# do the figures shrink. Past what the smallest figures fit beside a
# TEAM_FLOOR column, the races go in bands: the table is printed again
# for each run of races that fits, every band with the names, the
# places, and the total, so a season of nights stays readable.
RACE_MAX = 26.0
TEAM_MIN = 50.0
TEAM_FLOOR = 40.0
# A day's figure prints at the rest of the field's size even on a podium
# row: the total is the number read out, the days are its working.
RACE_PT = T.REST.size
RACE_MIN_PT = 9.0
HEADER_LINE = 3.4
DATE_MIN_PT = 5.5
NOTE_PT = P.DETAIL_PT
NOTE_H = P.DETAIL_H


@dataclass(frozen=True)
class _Cols:
    place: tuple[float, float]
    # A team's swatch, or a rider's bib column; the other is None.
    swatch: float | None
    bib: tuple[float, float] | None
    # The team's name and riders, or the rider's name.
    team: tuple[float, float]
    races: tuple[tuple[float, float], ...]
    total: tuple[float, float]
    race_pt: float
    penalty: tuple[float, float] | None = None
    # A team's name and its riders' column beside it, inside ``team``;
    # None when the riders go under the name, in the same column.
    name: tuple[float, float] | None = None
    riders: tuple[float, float] | None = None

    @property
    def lead(self) -> T.Lead:
        # A rider's name is the row's own line, beside the bib; a team's
        # riders go beside its name or under it.
        if self.bib is not None:
            return T.Lead(self.place, self.swatch, None, self.bib, self.team)
        beside = self.riders is not None
        return T.Lead(
            self.place,
            self.swatch,
            self.name or self.team,
            None,
            self.riders or self.team,
            beside=beside,
        )


def _widest(group: GroupTable) -> str:
    """The group's widest race figure as printed, by characters; at least WIDEST."""
    return T.widest(
        format_number(p)
        for row in group.rows
        if not row.status
        for p in row.per_race
        if p is not None
    )


def _columns(pdf: P._Doc, group: GroupTable) -> _Cols:
    """Place, swatch or bib, the name, the races, the total; the name column gives way first.

    The group's races must fit one band (``_bands``): the name column
    never goes under TEAM_FLOOR.
    """
    # A rider's bib, as wide as on the results sheet.
    bibs = [str(r.bib) for r in group.rows if r.bib is not None] if group.riders else None
    place, swatch, bib, x = T.lead_columns(
        pdf, T.PLACE_W, swatch=not group.riders, bibs=bibs, bib_pt=T.TOP.size, bib_gap=T.BIB_GAP
    )
    widest = _widest(group)
    total_w = T.total_width(pdf, (format_number(r.total) for r in group.rows if not r.status))
    right = P.MARGIN + pdf.usable - total_w
    total = (right, total_w)
    penalty = None
    if any(r.penalty and not r.status for r in group.rows):
        right -= T.GAP + T.PENALTY_W
        penalty = (right, T.PENALTY_W)
    room = right - T.GAP - x
    n = len(group.columns)
    size = RACE_PT
    race_w = 0.0
    if n:
        while (
            n * (T.figure_w(pdf, widest, size) + T.FIGURE_AIR) + TEAM_FLOOR > room
            and size > RACE_MIN_PT
        ):
            size -= 0.5
        need = T.figure_w(pdf, widest, size) + T.FIGURE_AIR
        race_w = max(need, min(RACE_MAX, (room - TEAM_MIN) / n))
    team = (x, room - n * race_w)
    races = tuple((right - T.GAP - (n - i) * race_w, race_w) for i in range(n))
    name = riders = None
    if not group.riders:
        rows = T.ordered(group.rows, lambda r: not r.status)
        names = [(row.team, tier.size) for row, tier in rows]
        riders_w = max(
            [T.text_w(pdf, r, tier.rider_pt, "") for row, tier in rows for r in row.riders],
            default=0.0,
        )
        name_w = T.team_name_width(pdf, team[1], names, riders_w)
        beside = (x + name_w + T.GAP, team[1] - name_w - T.GAP)
        sizes = [(r, tier.rider_pt) for row, tier in rows for r in row.riders]
        if T.riders_fit(pdf, beside[1], sizes):
            name, riders = (x, name_w), beside
    return _Cols(place, swatch, bib, team, races, total, size, penalty, name, riders)


def _band_size(pdf: P._Doc, group: GroupTable) -> int:
    """How many race columns each band holds: as many as fit beside TEAM_MIN at the
    smallest figure size, then evened out so the last band is not a stub."""
    room = _columns(pdf, replace(group, columns=[])).team[1]
    need = T.figure_w(pdf, _widest(group), RACE_MIN_PT) + T.FIGURE_AIR
    most = max(1, int((room - TEAM_MIN) // need))
    bands = -(-len(group.columns) // most)
    return -(-len(group.columns) // bands)


def _bands(pdf: P._Doc, group: GroupTable) -> list[GroupTable]:
    """The group as one table when its races fit, else as bands of races that do.

    Each band is the whole table over a run of its races, so a row's place
    and total read the same in every band and the names are never
    squeezed out.
    """
    if _columns(pdf, group).team[1] >= TEAM_FLOOR:
        return [group]
    size = _band_size(pdf, group)
    out = []
    for start in range(0, len(group.columns), size):
        stop = start + size
        rows = [replace(r, per_race=r.per_race[start:stop]) for r in group.rows]
        out.append(replace(group, columns=group.columns[start:stop], rows=rows))
    return out


def _row_text(pdf: P._Doc, row: MultiRaceRow, cols: _Cols, tier: T.Tier) -> T.RowText:
    # A name prints as on the results sheet: it shrinks a little, then
    # wraps, and a rider's name is bold on the podium and regular below.
    name_w = (cols.name or cols.team)[1]
    style = tier.name_style if cols.bib is not None else "B"
    name = T.wrapped(
        pdf, row.team, name_w, style, tier.size, tier.size * T.NAME_SHRINK, T.NAME_LINES
    )
    if cols.bib is not None:
        bib = "" if row.bib is None else str(row.bib)
        return T.row_text(tier, T.Lines((), tier.size), ((bib, name),), tier.line, style, tier.size)
    rider_pt = tier.rider_pt
    # Beside the name every rider fits one line (``_columns`` checks);
    # under it, each wraps on its own, as on the results sheet.
    lines = 1 if cols.riders is not None else T.NAME_LINES
    w = (cols.riders or cols.team)[1]
    riders = tuple(
        ("", T.wrapped(pdf, r, w, "", rider_pt, rider_pt * T.NAME_SHRINK, lines))
        for r in row.riders
    )
    return T.row_text(
        tier, name, riders, T.rider_line(rider_pt), "", rider_pt, beside=cols.riders is not None
    )


def _swatch(color: str | None) -> str:
    """The team's color as the results sheet draws it: its hex, or its name's, or gray."""
    if color and color.startswith("#"):
        return color
    return COLOR_HEX.get((color or "").strip().lower(), NEUTRAL_HEX)


def _draw_row(
    pdf: P._Doc, row: MultiRaceRow, cols: _Cols, tier: T.Tier, y: float, text: T.RowText
) -> float:
    def figures(top: float) -> None:
        # A blank, not a 0, where the team did not ride: the sheet sums it
        # as nothing, and a 0 would read as a race ridden for no points.
        size = min(tier.size, cols.race_pt)
        for col, points in zip(cols.races, row.per_race, strict=True):
            if points is not None:
                P._text(pdf, col[0], top, col[1], tier.line, format_number(points), "R", "", size)
        if cols.penalty is not None and row.penalty:
            x, w = cols.penalty
            P._text(pdf, x, top, w, tier.line, lap_text(-row.penalty), "R", "", size)
        x, w = cols.total
        P._text(pdf, x, top, w, tier.line, format_number(row.total), "R", "B", tier.size)

    status = tier is T.STATUS
    place = row.status if status else ("" if row.rank is None else str(row.rank))
    color = _swatch(row.color) if cols.swatch is not None else None
    return T.draw_row(pdf, cols.lead, tier, y, text, place=place, color_hex=color, figures=figures)


def _header_names(pdf: P._Doc, group: GroupTable, cols: _Cols) -> list[T.Lines]:
    out = []
    for column, (_, w) in zip(group.columns, cols.races, strict=True):
        out.append(T.wrapped(pdf, column.race_name, w, "", T.HEADER_PT, DATE_MIN_PT, 2))
    return out


def _runs(group: GroupTable) -> list[list[int]]:
    """The race columns by night: each run is the indexes of one event's columns, in order."""
    runs: list[list[int]] = []
    for i, column in enumerate(group.columns):
        if runs and group.columns[runs[-1][0]].event_id == column.event_id:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs


def _dates(pdf: P._Doc, group: GroupTable, cols: _Cols) -> list[tuple[str, ...]]:
    """Each night's date as its header prints it, one entry per run of ``_runs``.

    The full date when every night's fits over its columns, else the
    short form (Oct-17) the standings dialog heads its columns with, the
    year being the band's; else the month over the day. One form for the
    whole table, so the nights read alike across its header.
    """
    runs = _runs(group)
    isos = [group.columns[run[0]].event_date for run in runs]
    widths = [
        cols.races[run[-1]][0] + cols.races[run[-1]][1] - cols.races[run[0]][0] for run in runs
    ]

    def fits(lines: tuple[str, ...], w: float) -> bool:
        pdf.use("B", DATE_MIN_PT)
        room = w - 2 * pdf.c_margin + 1e-6
        return all(pdf.get_string_width(pdf.quiet(line)) <= room for line in lines)

    def stacked(iso: str) -> tuple[str, ...]:
        short = short_date(iso)
        if short == show_date(iso):
            # Not a date: there is no month and day to stack.
            return (short,)
        month, _, day = short.partition("-")
        return (month, day)

    forms = [lambda iso: (show_date(iso),), lambda iso: (short_date(iso),), stacked]
    for form in forms[:-1]:
        lines = [form(iso) for iso in isos]
        if all(fits(ln, w) for ln, w in zip(lines, widths, strict=True)):
            return lines
    return [stacked(iso) for iso in isos]


def _header_h(names: list[T.Lines], dates: list[tuple[str, ...]]) -> float:
    # 0.8 mm under the dates' lines for the rule that spans a night's races.
    date_rows = max((len(d) for d in dates), default=1)
    return HEADER_LINE * (date_rows + max((len(n.lines) for n in names), default=0)) + 0.8 + 1.4


def _draw_header_row(
    pdf: P._Doc,
    group: GroupTable,
    cols: _Cols,
    names: list[T.Lines],
    dates: list[tuple[str, ...]],
    y: float,
) -> float:
    """Place, Team (or Bib and Rider), each race as its event's date over its name, then Total."""
    h = _header_h(names, dates)
    labels = [(cols.place, "Place", "R")]
    if cols.bib is not None:
        labels.append((cols.bib, "Bib", "R"))
    labels.append((cols.team, "Rider" if cols.bib is not None else "Team", "L"))
    labels.append((cols.total, "Total", "R"))
    if cols.penalty is not None:
        labels.append((cols.penalty, "Penalty", "R"))

    def races() -> None:
        # Each night's date once, over the run of its races: a night of two
        # Madisons reads as one night, and a narrow column need not hold a date.
        for run, when in zip(_runs(group), dates, strict=True):
            x = cols.races[run[0]][0]
            w = cols.races[run[-1]][0] + cols.races[run[-1]][1] - x
            align = "R" if len(run) == 1 else "C"
            for k, line in enumerate(when):
                P._text(
                    pdf,
                    x,
                    y + k * HEADER_LINE,
                    w,
                    HEADER_LINE,
                    line,
                    align,
                    "B",
                    T.HEADER_PT,
                    DATE_MIN_PT,
                )
            if len(run) > 1:
                rule_y = y + len(when) * HEADER_LINE + 0.4
                pdf.set_draw_color(*P.RULE)
                pdf.line(x + 1.5, rule_y, x + w - 0.5, rule_y)
        for (x, w), name in zip(cols.races, names, strict=True):
            # Bottom-aligned, so one-line names sit on the header's last line.
            ly = y + h - 1.4 - HEADER_LINE * len(name.lines)
            for k, line in enumerate(name.lines):
                fitted = pdf.quiet_fit(line, w, "", name.size)
                pdf.set_xy(x, ly + k * HEADER_LINE)
                pdf.cell(w, HEADER_LINE, fitted, align="R")

    base = y + h - 1.4 - HEADER_LINE
    return T.draw_header_row(pdf, y, h, labels, label_y=base, label_h=HEADER_LINE, more=races)


def _group_heading(pdf: P._Doc, group: GroupTable, more: bool, detail: str = "") -> P.Heading:
    return P.lay_heading(pdf, None, group.group or NO_GROUP, "", detail, False, more=more)


def _group_section(pdf: P._Doc, group: GroupTable) -> None:
    """One group's tables: a band per run of races that fits, each with the group's heading."""
    bands = _bands(pdf, group)
    done = 0
    for band in bands:
        detail = ""
        if len(bands) > 1:
            first, last = done + 1, done + len(band.columns)
            detail = f"Races {first} to {last} of {len(group.columns)}"
        _band_section(pdf, band, detail)
        done += len(band.columns)


def _band_section(pdf: P._Doc, group: GroupTable, detail: str) -> None:
    """One table, kept on one page when it fits one, else split with its header repeated."""
    cols = _columns(pdf, group)
    names = _header_names(pdf, group, cols)
    dates = _dates(pdf, group, cols)
    head = T.table_head(_group_heading(pdf, group, False, detail).height, _header_h(names, dates))
    rows = T.ordered(group.rows, lambda r: not r.status)
    texts = [_row_text(pdf, r, cols, t) for r, t in rows]

    def top(y: float, more: bool) -> float:
        y = P.draw_heading(pdf, _group_heading(pdf, group, more, detail), y) + T.HEAD_TO_TABLE
        y += _draw_header_row(pdf, group, cols, names, dates, y) + T.HEADER_TO_ROWS
        return y

    # Nothing above it on this page but the sheet's title counts as the
    # top: a fresh page would leave the first page holding a title alone.
    y = T.draw_table(
        pdf,
        head,
        rows,
        texts,
        top,
        lambda row, tier, y, text, _column: _draw_row(pdf, row, cols, tier, y, text),
        first_top=_title_end(pdf),
    )
    pdf.set_xy(P.MARGIN, y + P.SECTION_GAP)


def _race_list(columns: list[RaceColumn]) -> str:
    """'2 Mile Chase, 6 Mile Points (Group B); Elimination (Group A)': each run of one group named once."""
    runs: list[tuple[str, list[str]]] = []
    for column in columns:
        if runs and runs[-1][0] == column.group:
            runs[-1][1].append(column.race_name)
        else:
            runs.append((column.group, [column.race_name]))
    parts = []
    for group, names in runs:
        names_text = ", ".join(names)
        parts.append(f"{names_text} ({group})" if group.strip() else names_text)
    return "; ".join(parts)


# What each race of a night did for the standings, in the order a reader
# asks: what counted, what is still to come, what was left out.
NOTE_WORDS = (
    ("counting", "Counted"),
    ("racing", "Still racing"),
    ("not_yet_raced", "Not yet raced"),
    ("left_out", "Not counted"),
)


def _notes(table: MultiRaceTable, order: dict[int, int]) -> list[tuple[str, str]]:
    """(style, text) lines for under the tables: each night, then what its races did.

    ``order`` is each race's place among the ticked events' races, oldest
    event first and then program order, so each night's races read as
    the night ran whichever group's table a race is in. A night with
    nothing to say (ticked, no race the kind counts) is left out.
    """
    counting = sorted(
        (c for g in table.groups for c in g.columns), key=lambda c: order.get(c.race_id, 0)
    )
    by_kind = {
        "counting": counting,
        "racing": table.racing,
        "not_yet_raced": table.not_yet_raced,
        "left_out": table.left_out,
    }
    out: list[tuple[str, str]] = []
    for event_id, name, iso in table.events:
        lines = []
        for key, word in NOTE_WORDS:
            mine = [c for c in by_kind[key] if c.event_id == event_id]
            if mine:
                lines.append(("", f"{word}: {_race_list(mine)}"))
        if lines:
            out.append(("B", f"{name} ({show_date(iso)})"))
            out += lines
    return out


# The air above a night's bold heading in the notes, so one night's lines
# read apart from the next's.
NOTE_GAP = 2.0


def _draw_notes(pdf: P._Doc, notes: list[tuple[str, str]]) -> None:
    y = pdf.get_y()
    for i, (style, text) in enumerate(notes):
        pdf.use(style, NOTE_PT)
        kept = len(pdf.unprintable)
        lines = P._wrap_words(pdf, text, pdf.usable - 2 * pdf.c_margin)
        del pdf.unprintable[kept:]
        # An event or race name the font lacks is reported once, whole.
        pdf.txt(text)
        if style == "B" and i:
            y += NOTE_GAP
        for line in lines:
            # A heading keeps its first line: alone at a page's foot it
            # would name a list the reader finds overleaf.
            need = 2 * NOTE_H if style == "B" else NOTE_H
            if y + need > pdf.bottom:
                pdf.add_page()
                y = pdf.get_y()
            pdf.set_text_color(*P.MUTED)
            P._text(pdf, P.MARGIN, y, pdf.usable, NOTE_H, pdf.quiet(line), "L", style, NOTE_PT, 7)
            y += NOTE_H
    pdf.set_text_color(*P.INK)
    pdf.set_xy(P.MARGIN, y)


def _refusal_notes(refusal: Refusal) -> list[tuple[str, str]]:
    """The refusal as note rows: the rule, then each event bold over a line per group."""
    notes = [("", refusal.lead)]
    for night, lines in refusal.nights:
        notes.append(("B", night))
        notes.extend(("", line) for line in lines)
    return notes


def _span(events: list[tuple[int, str, str]]) -> str:
    """The nights a standings covers, in the band's words: 'October 17 to 18, 2026'."""
    dates = []
    for _, _, iso in events:
        try:
            dates.append(date.fromisoformat(iso[:10]))
        except ValueError:
            continue
    if not dates:
        return ""
    first, last = min(dates), max(dates)
    if first == last:
        return P._pretty_date(first.isoformat())
    a, b = P.MONTH_NAMES[first.month - 1], P.MONTH_NAMES[last.month - 1]
    if first.year != last.year:
        return f"{a} {first.day}, {first.year} to {b} {last.day}, {last.year}"
    if first.month != last.month:
        return f"{a} {first.day} to {b} {last.day}, {last.year}"
    return f"{a} {first.day} to {last.day}, {last.year}"


def _events_line(table: MultiRaceTable) -> str:
    if not table.events:
        return "No events ticked"
    return "Events: " + ", ".join(f"{name} ({show_date(iso)})" for _, name, iso in table.events)


def _title_lines(table: MultiRaceTable) -> list[str]:
    """The gray lines under the name: the kind and its count, the events, how it scores."""
    return [f"{table.kind_label}: {table.counted}", _events_line(table), table.detail]


def _title(pdf: P._Doc, table: MultiRaceTable) -> None:
    """The standings' name with its FINAL tag once final, and the gray lines saying what it sums."""
    head = P.lay_heading(pdf, None, table.name, "", "", True)
    # Each line wrapped on its own, as many lines as a season's events
    # need, so none is cut to fit the heading's two.
    pdf.use("", P.DETAIL_PT)
    kept = len(pdf.unprintable)
    gray = [
        pdf.quiet(line)
        for text in _title_lines(table)
        for line in P._wrap_words(pdf, text, pdf.usable - 2 * pdf.c_margin)
    ]
    del pdf.unprintable[kept:]
    for text in _title_lines(table):
        pdf.txt(text)
    head = replace(head, gray=gray)
    top = pdf.get_y()
    y = P.draw_heading(pdf, head, top)
    # FINAL once it is, and no tag before: a season's sheet is posted
    # after every night without a warning that says only "not yet over".
    if table.state == "final":
        P.draw_tag(pdf, "FINAL", top, filled=True)
    pdf.set_xy(P.MARGIN, y + P.SECTION_GAP)
    pdf.title_end = y + P.SECTION_GAP  # type: ignore[attr-defined]


def _title_end(pdf: P._Doc) -> float:
    return getattr(pdf, "title_end", pdf.body_top)


def suggested_standings_name(table: MultiRaceTable) -> str:
    """'2026-10-18 - Demo 2 Day Omnium - Standings.pdf': the latest ticked night, then the name.

    The date leads, as on the results exports, so a folder of exports
    sorts by night; it is the latest night the standings covers, since
    a weekend's standings is printed after its last night.
    """
    dates = [iso[:10] for _, _, iso in table.events if iso]
    name = f"{_safe(table.name) or 'Standings'} - Standings.pdf"
    return f"{max(dates)} - {name}" if dates else name


def write_standings_pdf(
    store: Store,
    standings_id: int,
    path: str | Path,
    *,
    logo_path: str | Path | None = None,
    venue_name: str | None = None,
    generated: datetime | None = None,
    unprintable: list[str] | None = None,
) -> Path:
    """Write the standings to a PDF at ``path``, on the results sheet's header.

    ``logo_path``, ``venue_name``, ``generated``, and ``unprintable`` work
    as they do for ``write_results_pdf``; the venue falls back to the
    latest ticked event's venue.
    """
    table = compute(store, standings_id)
    events = [store.event(e[0]) for e in table.events]
    fallback = next((e.venue for e in reversed(events) if e.venue), None)
    venue, logo = P.masthead(store, logo_path, venue_name, fallback)
    subtitle = ["Standings"]
    if span := _span(table.events):
        subtitle.append(span)
    series = {e.series for e in events}
    if len(series) == 1 and (only := series.pop()):
        subtitle.append(only)
    if venue and logo:
        subtitle.append(venue)
    pdf = P.new_doc(
        title=table.name,
        subtitle=P.SEP.join(subtitle),
        logo=logo,
        venue=venue,
        footer_text=P.footer_line(table.name, generated),
        doc_title=f"{table.name} standings",
        landscape=True,
    )
    pdf.add_page()
    _title(pdf, table)
    if table.refusal:
        # Where the tables would be: why the ticked races are no Four-Race
        # Omnium, the rule and then each event's lines as the notes read.
        _draw_notes(pdf, _refusal_notes(table.refusal))
        pdf.set_xy(P.MARGIN, pdf.get_y() + P.SECTION_GAP)
    for group in table.groups:
        _group_section(pdf, group)
    order: dict[int, int] = {}
    for event in events:
        for race in store.races(event.event_id):
            order[race.race_id] = len(order)
    _draw_notes(pdf, _notes(table, order))

    try:
        out = write_replacing(path, lambda partial: pdf.output(str(partial)))
    finally:
        pdf.close_fonts()
    if unprintable is not None:
        unprintable.extend(pdf.unprintable)
    return out
