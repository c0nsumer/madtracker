"""The Madison on the board: the start list names its riders, each team a swatch and fade."""

import copy
from dataclasses import replace

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from madtracker.board import payloads as P
from madtracker.board import sample
from madtracker.control import formats
from ui.board_helpers import render, strings

NAMES = dict(sample.GROUP_A + sample.GROUP_B)
# Color word, then the two riders' bibs, as the demo pairs them.
TEAMS = [
    ("Blue", "3", "24"),
    ("Red", "5", "36"),
    ("Orange", "8", "27"),
    ("Yellow", "11", "21"),
    ("Black", "14", "31"),
    ("Green", "17", "42"),
    ("Purple", "4", "7"),
    ("White", "9", "12"),
    ("Pink", "19", "22"),
    ("Silver", "33", "38"),
    ("Brown", "45", "51"),
    ("Tan", "60", "61"),
]
NAMES |= {"60": "Ines Calloway", "61": "Theo Brandvold"}
HEADER = P.Header(title="2 Mile Madison", group="Group A", detail="Madison", status="Start list")


def team(color: str, a: str, b: str) -> P.Entry:
    return P.Entry(
        bibs=[a, b], names=[NAMES[a], NAMES[b]], team=color, color=formats.TEAM_COLORS[color]
    )


def start_list(teams: int) -> P.PreRace:
    return P.PreRace(header=HEADER, roster=[team(*t) for t in TEAMS[:teams]])


def surname(name: str) -> str:
    return name.partition(" ")[2]


def sizes(drawn, words) -> set[int]:
    return {px for s, _r, px, _c in drawn if s in set(words)}


def test_split_name_takes_the_first_word_and_keeps_the_rest_together(qapp):
    from madtracker.board import team_rows

    assert team_rows.split_name("Marcus Delgado") == ("Marcus", "Delgado")
    assert team_rows.split_name("Jan van der Berg") == ("Jan", "van der Berg")
    assert team_rows.split_name("  Cher ") == ("", "Cher")


def test_a_team_start_list_names_riders_first_and_no_team_or_count(qtbot, drawn):
    """The riders' names lead; the color identifies. No "5 TEAMS", no
    team word, and no team name of its own."""
    data = start_list(teams=5)
    data.roster[1].team = "Corktown Cyclery Racing"
    render(qtbot, "pre_race", data)
    s = strings(drawn)
    assert not any(x.lower().endswith("teams") or x in formats.TEAM_COLORS for x in s)
    assert "Corktown Cyclery Racing" not in s
    assert {"Delgado", "Mori", "Marcus", "Kenji"} <= set(s)


@pytest.mark.parametrize("teams, last, first", [(5, 83, 45), (8, 49, 36)])
def test_start_list_name_sizes_at_1080(qtbot, drawn, teams, last, first):
    """Design section 10: 5 teams set surnames of 83 px and first names of
    45 px; 8 teams set 49 and 36."""
    data = start_list(teams)
    render(qtbot, "pre_race", data)
    names = [n for e in data.roster for n in e.names]
    [got_last] = sizes(drawn, [surname(n) for n in names])
    [got_first] = sizes(drawn, [n.partition(" ")[0] for n in names])
    assert abs(got_last - last) <= 1 and abs(got_first - first) <= 1


@pytest.mark.parametrize("teams", [1, 2])
def test_a_lone_team_takes_half_the_page_and_surnames_stop_at_96(qtbot, drawn, teams):
    from madtracker.board import team_rows

    w = render(qtbot, "pre_race", start_list(teams))
    u = w.pages["pre_race"].u
    lasts = sizes(drawn, [surname(NAMES[b]) for _c, *bibs in TEAMS[:teams] for b in bibs])
    assert lasts == {round(team_rows.START_SURNAME_MOST * u)}
    firsts = sizes(drawn, [NAMES[b].split()[0] for _c, *bibs in TEAMS[:teams] for b in bibs])
    assert firsts == {round(team_rows.START_FIRST_MOST * u)}


def test_a_teams_two_riders_sit_side_by_side_in_one_row(qtbot, drawn):
    w = render(qtbot, "pre_race", start_list(5))
    page = w.pages["pre_race"]
    rects = {s: r for s, r, *_ in drawn}
    one, two = rects["Delgado"], rects["Mori"]
    assert one.center().y() == pytest.approx(two.center().y(), abs=0.5)
    assert two.left() > page.margin_rect().center().x() > one.left()
    # The first name stands above its surname, in the same column.
    assert rects["Marcus"].left() == pytest.approx(one.left())
    assert rects["Marcus"].center().y() < one.center().y()
    # The next team is a row below.
    assert rects["Okafor"].top() > one.bottom() - 1


@pytest.mark.parametrize("teams", [1, 2, 3, 4, 5, 8, 12])
@pytest.mark.parametrize("size", [(1920, 1080), (1920, 1200), (1280, 720)])
def test_each_teams_riders_stand_inside_its_own_row(qtbot, drawn, monkeypatch, teams, size):
    """However few teams share the page, a rider's ink, first name's
    capitals to surname's descenders, and plate stay inside the team's
    row: no line reaches the next team's."""
    from PySide6.QtGui import QFontMetricsF

    from madtracker.board import team_rows
    from madtracker.board import theme as t

    rows: list[QRectF] = []
    plates: list[QRectF] = []
    band, plate = team_rows.paint_band, t.plate

    def record_band(p, row, *args, **kwargs):
        rows.append(QRectF(row))
        return band(p, row, *args, **kwargs)

    def record_plate(p, r, bib, out=False):
        plates.append(QRectF(r))
        return plate(p, r, bib, out)

    monkeypatch.setattr(team_rows, "paint_band", record_band)
    monkeypatch.setattr(t, "plate", record_plate)
    w = render(qtbot, "pre_race", start_list(teams), size=size)
    area = w.pages["pre_race"].margin_rect()
    assert rows and all(area.adjusted(0, 0, 0, 0.5).contains(r) for r in rows)
    for a, b in zip(rows, rows[1:], strict=False):
        assert b.top() >= a.bottom()
    seen = {s: (r, px) for s, r, px, _c in drawn}
    for k, row in enumerate(rows):
        _color, *bibs = TEAMS[k]
        for bib in bibs:
            first, last = NAMES[bib].split(" ", 1)
            fr, fpx = seen[first]
            lr, lpx = seen[last]
            ff = QFontMetricsF(t.font(fpx, t.SEMI))
            lf = QFontMetricsF(t.font(lpx, t.HEAVY))
            assert row.top() <= fr.y() + ff.ascent() - ff.capHeight()
            assert lr.y() + lf.ascent() + lf.descent() <= row.bottom()
            assert row.left() < fr.left() and lr.right() <= row.right()
    assert all(any(row.contains(pl) for row in rows) for pl in plates)


def test_the_first_name_is_quieter_than_the_surname(qtbot, drawn, monkeypatch):
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    pens: dict[str, int] = {}
    text = t.text

    def record(p, rect, s, f, color, *args, **kwargs):
        pens[s] = color.alpha()
        return text(p, rect, s, f, color, *args, **kwargs)

    monkeypatch.setattr(t, "text", record)
    render(qtbot, "pre_race", start_list(5))
    assert pens["Marcus"] == team_rows.FIRST_NAME_ALPHA < pens["Delgado"] == 255


def test_a_long_surname_shrinks_to_the_floor_then_is_cut(qtbot, drawn):
    from madtracker.board import theme as t

    data = start_list(8)
    data.roster[0].names = [
        "Ada Featherstonehaugh-Rochester",
        "Bo Montgomery-Blackwood-Oyelaran-Smith",
    ]
    w = render(qtbot, "pre_race", data)
    u = w.pages["pre_race"].u
    base = next(px for s, _r, px, _c in drawn if s == "Okafor")
    shrunk = [(s, r, px) for s, r, px, _c in drawn if s.startswith("Featherstonehaugh")]
    cut = [(s, r, px) for s, r, px, _c in drawn if s.startswith("Montgomery")]
    # Whole, smaller than the rest, never under the floor, and inside its half.
    [(s, r, px)] = shrunk
    assert s == "Featherstonehaugh-Rochester" and round(t.MIN_PX * u) <= px < base
    assert t.text_width(s, t.font(px, t.HEAVY)) <= r.width() + 0.5
    # Too long even at the floor: set at the floor and cut.
    [(s, r, px)] = cut
    assert px == round(t.MIN_PX * u) and s.endswith("…")
    # The first names are never shrunk.
    assert sizes(drawn, ["Ada", "Bo"]) == sizes(drawn, ["Priya"])


def test_a_long_first_name_is_cut_not_shrunk(qtbot, drawn):
    data = start_list(8)
    data.roster[0].names = ["Maximilianaannelieseevangelina" * 2 + " Quill", NAMES["24"]]
    render(qtbot, "pre_race", data)
    first = [(s, px) for s, _r, px, _c in drawn if s.startswith("Maximiliana")]
    [(s, px)] = first
    assert s.endswith("…") and {px} == sizes(drawn, ["Priya"])


def test_a_rider_with_one_name_shows_it_as_a_surname(qtbot, drawn):
    data = start_list(5)
    data.roster[0].names = ["Cher", NAMES["24"]]
    render(qtbot, "pre_race", data)
    assert sizes(drawn, ["Cher"]) == sizes(drawn, ["Mori"])
    assert "" not in strings(drawn)


def test_twelve_teams_show_as_two_pages_of_six_with_dots(qtbot, drawn, monkeypatch):
    dots: list[QRectF] = []
    ellipse = QPainter.drawEllipse

    def record(self, *args):
        dots.append(args[0])
        return ellipse(self, *args)

    monkeypatch.setattr(QPainter, "drawEllipse", record)
    data = start_list(12)
    w = render(qtbot, "pre_race", data)
    page = w.pages["pre_race"]
    assert page.page_count() == 2 and len(dots) == 2
    lasts = [surname(NAMES[b]) for _c, *bibs in TEAMS for b in bibs]
    first_page = [s for s in strings(drawn) if s in lasts]
    assert first_page == lasts[:12]
    px = sizes(drawn, lasts)
    drawn.clear()
    page.advance()
    w.grab()
    assert [s for s in strings(drawn) if s in lasts] == lasts[12:]
    # The pages share one size, so a turn never steps the names.
    assert sizes(drawn, lasts) == px
    page.advance()
    assert page.page == 0


def test_eight_teams_are_one_page_and_the_pager_leaves_them(qtbot, drawn):
    w = render(qtbot, "pre_race", start_list(8))
    page = w.pages["pre_race"]
    assert page.page_count() == 1
    page.advance()
    assert page.page == 0


def test_bibs_only_shows_two_plates_and_no_names(qtbot, drawn, monkeypatch):
    from madtracker.board import theme as t

    plates: list[str] = []
    plate = t.plate
    monkeypatch.setattr(
        t, "plate", lambda p, r, bib, out=False: plates.append(bib) or plate(p, r, bib)
    )
    data = start_list(5)
    render(qtbot, "pre_race", data, label="bibs")
    assert plates == [b for e in data.roster for b in e.bibs]
    words = {w for s in strings(drawn) for w in s.split()}
    assert not words & {w for e in data.roster for n in e.names for w in n.split()}


@pytest.mark.parametrize("label, plated", [("names", False), ("bibs_names", True)])
def test_names_only_drops_the_plates(qtbot, drawn, monkeypatch, label, plated):
    from madtracker.board import theme as t

    plates: list[str] = []
    plate = t.plate
    monkeypatch.setattr(
        t, "plate", lambda p, r, bib, out=False: plates.append(bib) or plate(p, r, bib)
    )
    data = start_list(5)
    render(qtbot, "pre_race", data, label=label)
    assert bool(plates) is plated
    assert {"Delgado", "Mori"} <= set(strings(drawn))


@pytest.mark.parametrize("label", ["names", "bibs_names", "bibs"])
@pytest.mark.parametrize("teams", [1, 5, 8, 12])
def test_nothing_on_a_team_start_list_is_under_the_floor(qtbot, drawn, label, teams):
    from madtracker.board import theme as t

    render(qtbot, "pre_race", start_list(teams), label=label)
    plates = {t.PLATE_TEXT.name()}
    assert min(px for _s, _r, px, color in drawn if color not in plates) >= t.MIN_PX


# The band --------------------------------------------------------------------

ROW = QRectF(20, 20, 800, 100)
RED = formats.TEAM_COLORS["Red"]


def _band(**kwargs) -> QImage:
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    img = QImage(840, 140, QImage.Format.Format_RGB32)
    img.fill(t.BG)
    p = QPainter(img)
    team_rows.paint_band(p, ROW, RED, 1.0, **kwargs)
    p.end()
    return img


def _close(a: QColor, b: QColor, tol: int = 6) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a.getRgb()[:3], b.getRgb()[:3], strict=True))


def test_a_band_is_a_swatch_then_a_fade_that_is_gone_by_sixty_percent(qapp):
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    img = _band()
    y = int(ROW.center().y())
    assert _close(img.pixelColor(int(ROW.left() + team_rows.SWATCH_W / 2), y), QColor(RED))

    # The fade: strong at the left, weaker at a quarter, the bare row past 60%.
    def strength(share: float) -> int:
        c = img.pixelColor(int(ROW.left() + ROW.width() * share), y)
        return abs(c.red() - t.ROW.red())

    assert strength(0.05) > strength(team_rows.FADE_MID_AT) > strength(0.5) > 0
    assert _close(img.pixelColor(int(ROW.left() + ROW.width() * 0.65), y), t.ROW, 2)


def test_a_full_sweep_fills_the_color_to_the_zone_edge(qapp):
    from madtracker.board import theme as t

    zone = ROW.left() + 500
    img = _band(sweep=1.0, zone_right=zone)
    y = int(ROW.center().y())
    for x in (ROW.left() + 60, ROW.left() + 300, zone - 3):
        assert _close(img.pixelColor(int(x), y), QColor(RED)), x
    assert _close(img.pixelColor(int(zone + 3), y), t.ROW, 2)


def test_a_partial_sweep_stops_partway_with_a_light_leading_edge(qapp):
    from madtracker.board import team_rows

    zone = ROW.left() + 700
    img = _band(sweep=0.5, zone_right=zone)
    y = int(ROW.center().y())
    start = ROW.left() + team_rows.SWATCH_W
    lead = start + (zone - start) * 0.5
    solid = img.pixelColor(int(start + 20), y)
    edge = img.pixelColor(int(lead - 3), y)
    assert _close(solid, QColor(RED))
    assert edge.lightness() > solid.lightness() + 10
    assert not _close(img.pixelColor(int(lead + 40), y), QColor(RED), 30)


def test_a_dark_team_gets_no_ring(qapp):
    """Spec section 7: a light ring was tried and rejected; the names carry a dark team."""
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    img = QImage(840, 140, QImage.Format.Format_RGB32)
    img.fill(t.BG)
    p = QPainter(img)
    team_rows.paint_band(p, ROW, formats.TEAM_COLORS["Black"], 1.0)
    p.end()
    # Nothing lighter than the row anywhere along the band's top edge.
    y = int(ROW.top()) + 1
    light = max(img.pixelColor(x, y).lightness() for x in range(int(ROW.left()), int(ROW.right())))
    assert light <= max(t.ROW.lightness(), QColor(formats.TEAM_COLORS["Black"]).lightness()) + 4


# The standings table -----------------------------------------------------------

# The design's example: color word, laps, total, in place order.
TABLE = [("Red", 1, 28), ("Blue", 0, 17), ("Orange", 0, 11), ("Yellow", 0, 6), ("Black", -1, -14)]


def standings(teams: int = 5, status: str = "After Sprint 2 of 4") -> P.Standings:
    bibs = {c: (a, b) for c, a, b in TEAMS}
    first = [c for c, *_ in TABLE]
    order = first + [c for c, *_ in TEAMS if c not in first]
    figures = {c: (laps, total) for c, laps, total in TABLE}
    rows = []
    for i, color in enumerate(order[:teams]):
        laps, total = figures.get(color, (0, 5 - i))
        entry = team(color, *bibs[color])
        rows.append(P.StandingRow(rank=i + 1, entry=entry, sprints=[], laps=laps, total=total))
    header = P.Header("2 Mile Madison", "Group A", "Madison", status)
    return P.Standings(header=header, sprint_count=4, rows=rows, current_sprint=2)


def surnames(data: P.Standings) -> list[str]:
    return [surname(n) for r in data.rows for n in r.entry.names]


def clocked(w, at: float = 0.0):
    """Give the board a clock ``at`` ms into the rotation."""
    from madtracker.board.motion import ManualClock

    clock = ManualClock(0.0)
    w.set_clock(clock)
    clock.advance(at)
    return clock


def color_view_ms(rows: int = 5) -> float:
    from madtracker.board import rotation

    return rotation.NAMES_MS + rotation.change_ms(rows) + 10


def record_bands(monkeypatch) -> list[tuple[QRectF, float, float | None]]:
    """Every team row the page paints: its rect, sweep and color zone's right edge."""
    from madtracker.board import team_rows

    bands: list[tuple[QRectF, float, float | None]] = []
    band = team_rows.paint_band

    def record(p, row, color, u, sweep=0.0, zone_right=None):
        bands.append((QRectF(row), sweep, zone_right))
        return band(p, row, color, u, sweep, zone_right)

    monkeypatch.setattr(team_rows, "paint_band", record)
    return bands


def test_the_madison_table_names_view_shows_surnames_and_no_team_words(qtbot, drawn):
    data = standings(5)
    data.rows[1].entry.team = "Stars and Stripes"
    render(qtbot, "madison", data)
    s = strings(drawn)
    assert {"Okafor", "Haddad", "Delgado", "Mori"} <= set(s)
    assert {"#", "LAPS", "TOTAL"} <= set(s)
    assert "TEAM" not in s and "PENALTY" not in s and "SPRINT PTS" not in s
    assert not set(s) & set(formats.TEAM_COLORS) and "Stars and Stripes" not in s
    firsts = {n.partition(" ")[0] for r in data.rows for n in r.entry.names}
    assert not set(s) & firsts


@pytest.mark.parametrize("teams, total, surname_px", [(5, 97, 75)])
def test_madison_table_sizes_at_1080(qtbot, drawn, monkeypatch, teams, total, surname_px):
    """Design section 10: 5 teams give rows of 156 px, totals of 97 px, and
    surnames of 75 px; the place is 0.85 of the total and LAPS under it."""
    from madtracker.board import pages, team_rows

    bands = record_bands(monkeypatch)
    data = standings(teams)
    render(qtbot, "madison", data)
    rows = [r for r, *_ in bands]
    assert {round(r.height()) for r in rows} == {156}
    for a, b in zip(rows, rows[1:], strict=False):
        assert b.top() - a.bottom() == pytest.approx(team_rows.ROW_GAP)
    assert sizes(drawn, ["28", "17", "11", "6", "−14"]) == {total}
    assert sizes(drawn, surnames(data)) == {surname_px}
    assert sizes(drawn, ["1", "2", "3", "4", "5"]) == {round(total * pages.TEAM_PLACE_SCALE)}
    [laps] = sizes(drawn, ["+1", "−1"])
    assert laps < total


def table_sizes(qtbot, drawn, data: P.Standings) -> tuple[int, int]:
    """The total's and the surnames' pixel sizes on a 1080p board showing ``data``."""
    drawn.clear()
    render(qtbot, "madison", data)
    totals = [P.total_text(r.total) for r in data.rows if not r.status]
    [total] = sizes(drawn, totals)
    [surname_px] = sizes(drawn, surnames(data))
    return total, surname_px


@pytest.mark.parametrize("teams", [1, 2])
def test_a_small_table_never_sets_its_totals_or_surnames_smaller_than_five_teams(
    qtbot, drawn, teams
):
    """Fewer rows get larger type: the totals give way to the surnames in a
    tall row, but never below the five-team table's, and the usual
    surnames stand whole at the start list's largest."""
    from madtracker.board import team_rows

    five = table_sizes(qtbot, drawn, standings(5))
    data = standings(teams)
    total, surname_px = table_sizes(qtbot, drawn, data)
    assert total >= five[0] and surname_px >= five[1]
    assert surname_px == team_rows.START_SURNAME_MOST
    assert set(surnames(data)) <= set(strings(drawn))
    # LAPS stops at its cap, under the total.
    [laps] = sizes(drawn, ["+1"])
    assert laps <= 96 and laps < total


def test_long_surnames_drive_the_figures_to_84_before_they_shrink(qtbot, drawn):
    from madtracker.board import pages

    data = standings(2)
    data.rows[0].entry.names = ["Ada Featherstonehaugh-Rochester", "Bo Montgomery-Blackwood"]
    total, surname_px = table_sizes(qtbot, drawn, data)
    assert total == pages.TEAM_FIGURE_LEAST
    assert pages.TEAM_PLACE_SCALE * total == pytest.approx(
        next(iter(sizes(drawn, ["1", "2"]))), abs=1
    )
    # The figures went as far as they go; only then did the surnames shrink.
    assert surname_px < 96
    # A short pair's surnames give the figures no reason to give way.
    total, surname_px = table_sizes(qtbot, drawn, standings(2))
    assert total > pages.TEAM_FIGURE_LEAST and surname_px == 96


LONG_TEAM = "Corktown and Woodbridge Wheelmen"


def race_states(teams: int) -> list[P.Standings]:
    """One table as a race goes on: no lap, a first lap, a first penalty, the stamp."""

    def data(laps=0, penalty=0, status="After Sprint 2 of 4"):
        d = standings(teams, status=status)
        for r in d.rows:
            r.laps = 0
        d.rows[0].laps, d.rows[-1].penalty = laps, penalty
        d.rows[0].entry.team = LONG_TEAM
        return d

    return [data(), data(laps=1), data(laps=1, penalty=-20), data(1, -20, "Final")]


@pytest.mark.parametrize("teams", [1, 2, 5])
def test_the_first_lap_penalty_and_stamp_never_step_the_table_down(qtbot, drawn, teams):
    """The sizes are decided as though a lap, a penalty, and ordinal places
    stood, so none of them steps the totals or the surnames down."""
    seen = [table_sizes(qtbot, drawn, d) for d in race_states(teams)]
    assert all(s == seen[0] for s in seen)


@pytest.mark.parametrize("teams", [1, 2, 5])
def test_the_color_name_and_bib_plates_hold_their_size_through_a_race(
    qtbot, drawn, monkeypatch, teams
):
    """The color view's team name and the Bibs Only plates are sized for the
    room a penalty and ordinal places would leave, as the surnames are, so
    a long team name never steps down as the race goes on."""
    from madtracker.board import theme as t

    heights: list[float] = []
    plate = t.plate

    def record(p, r, bib, out=False):
        heights.append(round(r.height(), 3))
        return plate(p, r, bib, out)

    monkeypatch.setattr(t, "plate", record)

    def looks(data: P.Standings) -> tuple[int, set[float]]:
        w = render(qtbot, "madison", data)
        clocked(w, color_view_ms(teams))
        drawn.clear()
        w.grab()
        [label] = {px for s, _r, px, _c in drawn if s == LONG_TEAM}
        heights.clear()
        render(qtbot, "madison", data, label="bibs")
        return label, set(heights)

    seen = [looks(d) for d in race_states(teams)]
    assert all(s == seen[0] for s in seen) and len(seen[0][1]) == 1


def test_the_wake_timer_is_precise(qtbot):
    """A coarse timer may fire a few percent of its 10 s late, and the
    change's first frame would land partway through it."""
    from PySide6.QtCore import Qt

    w = render(qtbot, "madison", standings(5))
    assert w.pages["madison"]._wake.timerType() == Qt.TimerType.PreciseTimer


def test_the_table_puts_place_names_and_figures_in_their_columns(qtbot, drawn, monkeypatch):
    """The leader's place in the accent; LAPS in the gain or loss color and
    TOTAL in white on the dark row, each right-aligned under its heading."""
    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    w = render(qtbot, "madison", standings(5))
    at = {s: (r, c) for s, r, _px, c in drawn}
    assert at["1"][1] == t.ACCENT.name() and at["2"][1] == t.TEXT.name()
    assert at["+1"][1] == t.GAIN.name() and at["−1"][1] == t.LOSS.name()
    assert at["28"][1] == at["−14"][1] == t.TEXT.name()
    assert at["28"][0].right() == pytest.approx(at["TOTAL"][0].right())
    assert at["+1"][0].right() == pytest.approx(at["LAPS"][0].right())
    assert at["+1"][0].right() < at["28"][0].right()
    # The place left of the row, the names on it, the figures at its right end.
    row = bands[0][0]
    assert row.right() == pytest.approx(w.pages["madison"].margin_rect().right())
    assert at["1"][0].right() <= row.left()
    okafor, haddad = at["Okafor"][0], at["Haddad"][0]
    assert row.left() < okafor.left() < haddad.left() < at["LAPS"][0].left()
    assert okafor.center().y() == pytest.approx(row.center().y(), abs=1)


def test_the_color_view_shows_the_team_name_in_its_ink(qtbot, drawn, monkeypatch):
    from PySide6.QtGui import QColor

    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    data = standings(5)
    data.rows[1].entry.team = "Stars and Stripes"
    w = render(qtbot, "madison", data)
    clocked(w, color_view_ms())
    drawn.clear()
    bands.clear()
    w.grab()
    colors = {s: c for s, _r, _px, c in drawn}
    assert colors["Red"] == t.team_ink(QColor(formats.TEAM_COLORS["Red"])).name()
    assert colors["Yellow"] == t.team_ink(QColor(formats.TEAM_COLORS["Yellow"])).name()
    assert "Stars and Stripes" in colors and "Blue" not in colors
    assert not set(colors) & set(surnames(data))
    # The color fills the name area solid, short of the LAPS column.
    laps = next(r for s, r, *_ in drawn if s == "+1")
    assert {sweep for _r, sweep, _z in bands} == {1.0}
    assert all(z < laps.left() for _r, _s, z in bands)
    # The name is centered on the area.
    row, _sweep, zone = bands[0]
    red = next(r for s, r, *_ in drawn if s == "Red")
    assert red.center().x() == pytest.approx((row.left() + zone) / 2, abs=1)
    assert red.center().y() == pytest.approx(row.center().y(), abs=1)


def test_a_long_team_name_shrinks_to_the_floor_then_is_cut(qtbot, drawn):
    from madtracker.board import theme as t

    data = standings(8)
    longest = "The Grand Corktown and Woodbridge Racing"
    data.rows[0].entry.team = longest
    data.rows[2].entry.team = "Stars and Stripes"
    w = render(qtbot, "madison", data, size=(900, 768))
    clocked(w, color_view_ms(8))
    drawn.clear()
    w.grab()
    u = w.pages["madison"].u
    px = {s: (r, px) for s, r, px, _c in drawn}
    rect, size = px[longest]
    assert size == round(t.MIN_PX * u)
    assert t.elide(longest, rect.width(), t.font(size, t.HEAVY)).endswith("…")
    rect, size = px["Stars and Stripes"]
    assert size >= round(t.MIN_PX * u)
    assert t.text_width("Stars and Stripes", t.font(size, t.HEAVY)) <= rect.width()


def test_totals_and_laps_hold_still_across_the_rotation(qtbot, drawn):
    from madtracker.board import rotation

    w = render(qtbot, "madison", standings(5))
    clock = clocked(w)
    frames = []
    for at in (0, rotation.NAMES_MS + 200, color_view_ms() - 10, color_view_ms()):
        clock.advance(at - clock.now())
        drawn.clear()
        w.grab()
        held = ("28", "+1", "1", "LAPS")
        frames.append({s: (QRectF(r), px) for s, r, px, _c in drawn if s in held})
    assert all(f == frames[0] for f in frames) and len(frames[0]) == 4


def test_a_change_moves_down_the_table_a_row_at_a_time(qtbot, drawn, monkeypatch):
    """Partway through the change each row is a little behind the one above."""
    from madtracker.board import rotation

    bands = record_bands(monkeypatch)
    w = render(qtbot, "madison", standings(5))
    clocked(w, rotation.NAMES_MS + 330)
    bands.clear()
    w.grab()
    sweeps = [s for _r, s, _z in bands]
    assert len(sweeps) == 5
    assert all(a > b for a, b in zip(sweeps, sweeps[1:], strict=False))
    assert 0 < sweeps[-1] and sweeps[0] < 1


def test_twelve_teams_turn_a_page_after_each_names_and_color_cycle(qtbot, drawn):
    from madtracker.board import rotation

    data = standings(12)
    w = render(qtbot, "madison", data)
    clock = clocked(w)
    names = surnames(data)

    def shown() -> list[str]:
        drawn.clear()
        w.grab()
        return [s for s in strings(drawn) if s in names]

    assert shown() == names[:12]
    # The canvas's page clock leaves a rotating table to its rotation.
    w._turn_page()
    assert shown() == names[:12]
    clock.advance(rotation.cycle_ms(6))
    assert shown() == names[12:]
    clock.advance(rotation.cycle_ms(6))
    assert shown() == names[:12]


def test_a_headless_table_never_rotates(qtbot, drawn):
    data = standings(12)
    w = render(qtbot, "madison", data)
    page = w.pages["madison"]
    assert page.clock is None
    assert {"Okafor", "Haddad"} <= set(strings(drawn))
    assert not set(strings(drawn)) & set(formats.TEAM_COLORS)
    # Headless, the canvas's page clock turns the pages, as before.
    drawn.clear()
    w._turn_page()
    w.grab()
    assert page.page == 1
    assert set(strings(drawn)) & set(surnames(data)) == set(surnames(data)[12:])


def test_bibs_only_shows_the_riders_plates_in_place_of_surnames(qtbot, drawn, monkeypatch):
    from madtracker.board import theme as t

    plates: list[str] = []
    plate = t.plate
    monkeypatch.setattr(
        t, "plate", lambda p, r, bib, out=False: plates.append(bib) or plate(p, r, bib)
    )
    data = standings(5)
    render(qtbot, "madison", data, label="bibs")
    assert plates == [b for r in data.rows for b in r.entry.bibs]
    assert not set(strings(drawn)) & set(surnames(data))
    plates.clear()
    drawn.clear()
    render(qtbot, "madison", data, label="bibs_names")
    assert not plates and {"Okafor", "Haddad"} <= set(strings(drawn))


@pytest.mark.parametrize("label", ["names", "bibs_names", "bibs"])
@pytest.mark.parametrize("teams", [1, 2, 5, 8, 12])
@pytest.mark.parametrize("view", ["names", "color"])
def test_nothing_on_the_madison_table_is_under_the_floor(qtbot, drawn, label, teams, view):
    from madtracker.board import theme as t

    data = standings(teams)
    data.rows[0].entry.names = ["Ada Featherstonehaugh-Rochester-Montgomery", NAMES["36"]]
    data.rows[-1].entry.team = "The Grand Corktown and Woodbridge Racing"
    w = render(qtbot, "madison", data, label=label)
    if view == "color":
        clocked(w, color_view_ms(min(teams, 6 if teams > 8 else teams)))
        drawn.clear()
        w.grab()
    plates = {t.PLATE_TEXT.name()}
    assert min(px for _s, _r, px, color in drawn if color not in plates) >= t.MIN_PX


def test_between_changes_the_table_waits_with_no_frames(qtbot):
    """Frames run only while a change moves; between changes one timer
    waits for the next change and nothing repaints."""
    from madtracker.board import rotation

    w = render(qtbot, "madison", standings(5))
    w.show()
    page = w.pages["madison"]
    clock = clocked(w)
    w.grab()
    assert not page.moving_now()
    assert page.wake_in() == pytest.approx(rotation.NAMES_MS, abs=1)
    clock.advance(rotation.NAMES_MS + 100)
    w.grab()
    assert page.moving_now() and page.wake_in() is None
    clock.advance(rotation.change_ms(5))
    w.grab()
    assert not page.moving_now()
    assert page.wake_in() == pytest.approx(rotation.COLOR_MS - 100, abs=1)


# Score changes -------------------------------------------------------------------


def key(color: str) -> tuple[str, ...]:
    _c, a, b = next(x for x in TEAMS if x[0] == color)
    return (a, b)


def scored(
    prev: P.Standings,
    changes: dict[str, int],
    kind: str = "sprint",
    laps: dict[str, int] | None = None,
    status: str | None = None,
) -> P.Standings:
    """``prev`` after ``changes`` to the named teams' totals, ranked again, as new scoring."""
    data = copy.deepcopy(prev)
    for r in data.rows:
        r.total += changes.get(r.entry.team, 0)
        r.laps += (laps or {}).get(r.entry.team, 0)
    data.rows.sort(key=lambda r: -r.total)
    for i, r in enumerate(data.rows):
        r.rank = i + 1
    if status is not None:
        data.header.status = status
    data.scored = P.Scored(kind, [key(c) for c in changes])
    return data


def quiet(data: P.Standings) -> P.Standings:
    return replace(data, scored=None)


def playing(qtbot, prev, layout: str = "madison", size=(1920, 1080)):
    """A clocked board showing ``prev``, the table a score change plays from."""
    w = render(qtbot, layout, prev, size=size)
    return w, clocked(w)


def frame(w, clock, drawn, at: float) -> dict[str, tuple[QRectF, int, str]]:
    """What the board draws ``at`` ms on its clock: each string's rect, size and color."""
    clock.advance(at - clock.now())
    drawn.clear()
    w.grab()
    return {s: (QRectF(r), px, c) for s, r, px, c in drawn}


def record_chips(monkeypatch) -> list[tuple[str, str, str]]:
    """Every score chip drawn: its text, fill and ink."""
    from madtracker.board import pages

    chips: list[tuple[str, str, str]] = []
    chip = pages.score_chip

    def record(p, rect, s, f, fill, ink, *args, **kwargs):
        chips.append((s, fill.name(), ink.name()))
        return chip(p, rect, s, f, fill, ink, *args, **kwargs)

    monkeypatch.setattr(pages, "score_chip", record)
    return chips


def order(at: dict, names: list[str]) -> list[str]:
    """``names`` top to bottom as drawn."""
    return sorted((n for n in names if n in at), key=lambda n: at[n][0].center().y())


RIDERS = ["Okafor", "Delgado", "Kowalczyk", "Whitfield", "Ferreira"]
# Past the end of a two-team play: both totals landed and the rows moved.
SETTLED = 2 * 1160 + 380 + 600 + 50


def test_a_sprint_slams_each_teams_points_in_order_then_reorders(qtbot, drawn, monkeypatch):
    from madtracker.board import scorebug
    from madtracker.board import theme as t

    chips = record_chips(monkeypatch)
    prev = standings(5)
    prev.rows[1].total = 12
    data = scored(prev, {"Red": 5, "Orange": 3}, status="After Sprint 3 of 4")
    w, clock = playing(qtbot, prev)
    w.set_layout("madison", data)
    at = frame(w, clock, drawn, 100)
    assert "+5" in at and "+3" not in at and "33" not in at
    assert chips == [("+5", t.ACCENT.name(), t.ACCENT_INK.name())]
    # On Red's row, right-aligned to the total.
    assert at["+5"][0].center().y() == pytest.approx(at["Okafor"][0].center().y(), abs=1)
    assert at["+5"][0].right() == pytest.approx(at["TOTAL"][0].right(), abs=1)
    # Rows hold their old order while the totals play.
    assert order(at, RIDERS) == RIDERS
    at = frame(w, clock, drawn, scorebug.STEP_MS + 100)
    assert "+3" in at and "33" in at
    # The reorder: Orange slides up past Blue after the last total lands.
    land = scorebug.STEP_MS + scorebug.SWAP_AT_MS + scorebug.SWAP_MS
    held = frame(w, clock, drawn, land - 10)["Kowalczyk"][0].center().y()
    mid = frame(w, clock, drawn, land + scorebug.REORDER_MS / 2)["Kowalczyk"][0].center().y()
    at = frame(w, clock, drawn, SETTLED)
    assert at["Kowalczyk"][0].center().y() < mid < held
    assert "+5" not in at and "+3" not in at
    assert order(at, RIDERS) == ["Okafor", "Kowalczyk", "Delgado", "Whitfield", "Ferreira"]
    assert not w.pages["madison"].scoring_now()


def test_the_chip_shows_the_change_to_the_total(qtbot, drawn, monkeypatch):
    from madtracker.board import theme as t

    chips = record_chips(monkeypatch)
    prev = standings(5)
    prev.rows[4].laps, prev.rows[4].total = 0, 6
    data = scored(prev, {"Black": -20}, kind="lap_lost", laps={"Black": -1})
    w, clock = playing(qtbot, prev)
    w.set_layout("madison", data)
    at = frame(w, clock, drawn, 100)
    assert chips[-1] == ("−20", t.OUT.name(), t.TEXT.name())
    # The lap figure changes as the new total rises in.
    assert "−1" not in at
    at = frame(w, clock, drawn, SETTLED)
    # Black's old 6 is gone; Yellow's 6 stays.
    assert "−14" in at and "−1" in at and strings(drawn).count("6") == 1


def test_the_first_sprint_plays_from_a_zero_table_in_start_list_order(qtbot, drawn):
    prev = start_list(5)
    rows = [P.StandingRow(rank=i + 1, entry=e, sprints=[]) for i, e in enumerate(prev.roster)]
    header = replace(HEADER, status="After Sprint 1 of 4")
    zero = P.Standings(header=header, sprint_count=4, rows=rows, current_sprint=1)
    data = scored(zero, {"Red": 5, "Orange": 3})
    w, clock = playing(qtbot, prev, layout="pre_race")
    w.set_layout("madison", data)
    clock.advance(100)
    drawn.clear()
    w.grab()
    # Every total reads 0, Red's old one too as it is knocked down.
    assert strings(drawn).count("0") == 5
    at = {s: (QRectF(r), px, c) for s, r, px, c in drawn}
    assert order(at, RIDERS) == ["Delgado", "Okafor", "Kowalczyk", "Whitfield", "Ferreira"]
    at = frame(w, clock, drawn, SETTLED)
    assert order(at, RIDERS) == ["Okafor", "Kowalczyk", "Delgado", "Whitfield", "Ferreira"]
    assert {"5", "3"} <= set(at)


def test_an_undo_mid_sequence_shows_the_current_table_at_once(qtbot, drawn):
    prev = standings(5)
    data = scored(prev, {"Red": 5, "Orange": 3})
    w, clock = playing(qtbot, prev)
    w.set_layout("madison", data)
    frame(w, clock, drawn, 500)
    w.set_layout("madison", quiet(standings(5)))
    at = frame(w, clock, drawn, 600)
    assert "+5" not in at and "+3" not in at
    assert {"28", "17", "11", "6", "−14"} <= set(at) and "33" not in at
    assert not w.pages["madison"].scoring_now()


def test_a_redraw_mid_sequence_leaves_it_playing(qtbot, drawn):
    """A staging click redraws the board with the same table; the sprint keeps playing."""
    from madtracker.board import scorebug

    prev = standings(5)
    data = scored(prev, {"Red": 5, "Orange": 3})
    w, clock = playing(qtbot, prev)
    w.set_layout("madison", data)
    frame(w, clock, drawn, 500)
    w.set_layout("madison", quiet(data))
    at = frame(w, clock, drawn, 600)
    assert "+5" in at and w.pages["madison"].scoring_now()
    assert "+3" in frame(w, clock, drawn, scorebug.STEP_MS + 100)


def test_a_race_switch_mid_sequence_plays_nothing(qtbot, drawn):
    prev = standings(5)
    data = scored(prev, {"Red": 5, "Orange": 3})
    w, clock = playing(qtbot, prev)
    w.set_layout("madison", data)
    frame(w, clock, drawn, 500)
    other = scored(standings(5), {"Blue": 4})
    other.header.race_id = 2
    w.set_layout("madison", other)
    at = frame(w, clock, drawn, 600)
    assert not {"+5", "+3", "+4"} & set(at) and "21" in at
    # Back to the first race: the board last showed another, so its next sprint lands quietly.
    w.set_layout("madison", scored(data, {"Yellow": 2}))
    at = frame(w, clock, drawn, 700)
    assert "+2" not in at and "8" in at
    assert not w.pages["madison"].scoring_now()


def test_another_data_file_plays_nothing_from_the_last_files_races(qtbot, drawn):
    """Race ids are a file's own: after another file opens, a race with the
    same id as one shown before starts with no memory of it."""
    prev = standings(5)
    w, clock = playing(qtbot, prev)
    w.set_layout("madison", scored(prev, {"Red": 5}))
    frame(w, clock, drawn, 100)
    w.forget_races()
    assert not w.pages["madison"].scoring_now()
    w.set_layout("madison", scored(prev, {"Orange": 3}))
    at = frame(w, clock, drawn, 200)
    assert "+3" not in at and "+5" not in at and "14" in at


def test_a_team_scoring_off_the_shown_page_updates_quietly(qtbot, drawn):
    from madtracker.board import scorebug

    pink = [surname(NAMES[b]) for b in key("Pink")]
    prev = standings(12)
    # Pink is on the second page, and its lap takes it to the first.
    w, clock = playing(qtbot, prev)
    assert not set(pink) & set(frame(w, clock, drawn, 50))
    w.set_layout("madison", scored(prev, {"Pink": 20}, kind="lap_gained", laps={"Pink": 1}))
    at = frame(w, clock, drawn, 100)
    assert "+20" not in at and set(pink) <= set(at)
    assert not w.pages["madison"].scoring_now()
    # A sprint scored on both pages plays only the team in view.
    w2, clock2 = playing(qtbot, prev)
    w2.set_layout("madison", scored(prev, {"Red": 5, "Pink": 3}))
    assert "+5" in frame(w2, clock2, drawn, 100)
    assert "+3" not in frame(w2, clock2, drawn, scorebug.STEP_MS + 100)


def test_a_resize_mid_sequence_ends_on_the_new_sizes_end_picture(qtbot, drawn):
    prev = standings(5)
    data = scored(prev, {"Red": 5, "Orange": 13})
    w, clock = playing(qtbot, prev)
    w.set_layout("madison", data)
    frame(w, clock, drawn, 500)
    w.resize(1280, 720)
    frame(w, clock, drawn, 900)
    frame(w, clock, drawn, SETTLED)
    got = sorted((s, QRectF(r).getRect(), px, c) for s, r, px, c in drawn)
    drawn.clear()
    render(qtbot, "madison", quiet(data), size=(1280, 720))
    want = sorted((s, QRectF(r).getRect(), px, c) for s, r, px, c in drawn)
    assert got == want


def test_the_rotation_pauses_during_a_sequence_and_restarts_on_names(qtbot, drawn, monkeypatch):
    from madtracker.board import rotation

    bands = record_bands(monkeypatch)
    prev = standings(5)
    data = scored(prev, {"Black": 20}, kind="lap_gained", laps={"Black": 1})
    w, clock = playing(qtbot, prev)
    page = w.pages["madison"]
    start = rotation.NAMES_MS - 100
    frame(w, clock, drawn, start)
    w.set_layout("madison", data)
    assert page.scoring_now() and page._ticker._timer.isActive()
    # The change to color would be under way by now; the names view holds.
    bands.clear()
    frame(w, clock, drawn, start + 1000)
    assert {s for _r, s, _z in bands} == {0.0}
    # When the scoring ends the rotation starts over on the names view.
    bands.clear()
    frame(w, clock, drawn, start + 2000)
    assert not page.scoring_now()
    assert {s for _r, s, _z in bands} == {0.0}
    assert page.wake_in() == pytest.approx(rotation.NAMES_MS, abs=1)
    bands.clear()
    frame(w, clock, drawn, start + 2000 + rotation.NAMES_MS + 330)
    assert max(s for _r, s, _z in bands) > 0


def test_queued_scoring_plays_after_the_play_ahead_from_its_totals(qtbot, drawn):
    from madtracker.board import scorebug

    prev = standings(5)
    a = scored(prev, {"Red": 5})
    b = scored(a, {"Blue": 4})
    w, clock = playing(qtbot, prev)
    w.set_layout("madison", a)
    frame(w, clock, drawn, 100)
    w.set_layout("madison", b)
    at = frame(w, clock, drawn, 200)
    assert "+5" in at and "+4" not in at and "21" not in at
    at = frame(w, clock, drawn, scorebug.SWAP_AT_MS + scorebug.SWAP_MS + 100)
    assert "+4" in at and "33" in at and "+5" not in at


def test_a_team_whose_total_did_not_change_gets_no_chip(qtbot, drawn, monkeypatch):
    from madtracker.board import scorebug

    chips = record_chips(monkeypatch)
    prev = standings(5)
    w, clock = playing(qtbot, prev)
    w.set_layout("madison", scored(prev, {"Red": 5, "Blue": 0}))
    frame(w, clock, drawn, scorebug.STEP_MS + 100)
    assert {s for s, *_ in chips} == {"+5"}
    # Nothing left to play: the table updates quietly.
    w2, _clock2 = playing(qtbot, prev)
    w2.set_layout("madison", scored(prev, {"Blue": 0}))
    assert not w2.pages["madison"].scoring_now()


def test_a_headless_board_shows_the_new_table_at_once(qtbot, drawn, monkeypatch):
    chips = record_chips(monkeypatch)
    prev = standings(5)
    w = render(qtbot, "madison", prev)
    drawn.clear()
    w.set_layout("madison", scored(prev, {"Red": 5, "Orange": 3}))
    w.grab()
    assert not chips and {"33", "14"} <= set(strings(drawn))
    assert not w.pages["madison"].scoring_now()


def test_the_tv_and_the_preview_play_the_same_sequence(qtbot, drawn):
    from madtracker.board.motion import ManualClock
    from madtracker.board.window import ScoreboardWindow

    prev = standings(5)
    data = scored(prev, {"Red": 5, "Orange": 3})
    clock = ManualClock()
    boards = []
    for _ in range(2):
        w = ScoreboardWindow("Test Velodrome", "Test Event")
        qtbot.addWidget(w)
        w.resize(1920, 1080)
        w.set_clock(clock)
        boards.append(w)
    for payload in (prev, data):
        for w in boards:
            w.set_layout("madison", payload)
    clock.advance(300)
    seen = []
    for w in boards:
        drawn.clear()
        w.grab()
        seen.append([(s, QRectF(r).getRect(), px, c) for s, r, px, c in drawn])
    assert seen[0] == seen[1] and any(s == "+5" for s, *_ in seen[0])
