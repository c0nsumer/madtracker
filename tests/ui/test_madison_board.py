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
HEADER = P.Header(title="2 Mile Madison", group="Group A", status="Start list")


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
    """A dark color has no ring; the riders' names carry a dark team (design section 10)."""
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


def _corners(path, row: QRectF) -> tuple[list[float], list[float]]:
    """The x of a path's points on ``row``'s top edge and on its bottom edge."""
    points = list(path.toFillPolygon())
    top = sorted({round(q.x(), 3) for q in points if abs(q.y() - row.top()) < 1e-6})
    bottom = sorted({round(q.x(), 3) for q in points if abs(q.y() - row.bottom()) < 1e-6})
    return top, bottom


def test_a_band_has_a_square_left_end_and_a_swatch_slanted_on_its_right(qapp):
    """The row's left end is square, top and bottom, and its right end
    keeps its rounded corners. The swatch is flush with the square end:
    its left edge is vertical, its right edge leans at the slant, and it
    is SWATCH_W wide at its foot, wider toward the top."""
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    run = t.SLANT * ROW.height()
    shape = team_rows.band_shape(ROW, 1.0)
    top, bottom = _corners(shape, ROW)
    assert top[0] == pytest.approx(ROW.left()) and bottom[0] == pytest.approx(ROW.left())
    # Both left corners are right angles: the left edge runs straight
    # from the top to the bottom, with no point inside a rounding.
    left = [q for q in shape.toFillPolygon() if q.x() < ROW.left() + team_rows.ROW_RADIUS]
    assert {round(q.x(), 3) for q in left} == {ROW.left()}
    r = team_rows.ROW_RADIUS
    assert top[-1] == pytest.approx(ROW.right() - r, abs=0.5)
    assert bottom[-1] == pytest.approx(ROW.right() - r, abs=0.5)
    top, bottom = _corners(team_rows.swatch_shape(ROW, 1.0, t.SLANT), ROW)
    w = team_rows.SWATCH_W
    assert top == pytest.approx([ROW.left(), ROW.left() + w + run])
    assert bottom == pytest.approx([ROW.left(), ROW.left() + w])


def test_a_slanted_sweep_ends_along_the_slant_short_of_the_zone(qapp):
    """The color's left end is the row's square end; its right end leans
    as the swatch's does, its top corner at the zone's edge at a full
    sweep, so the color opens and closes along the slant."""
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    zone = ROW.left() + 500
    run = t.SLANT * ROW.height()
    top, bottom = _corners(team_rows.fill_shape(ROW, 1.0, 1.0, zone, t.SLANT), ROW)
    assert top == pytest.approx([ROW.left(), zone])
    assert bottom == pytest.approx([ROW.left(), zone - run])
    # Partway, the leading edge leans the same way.
    top, bottom = _corners(team_rows.fill_shape(ROW, 1.0, 0.5, zone, t.SLANT), ROW)
    assert top[-1] - bottom[-1] == pytest.approx(run)
    assert ROW.left() + team_rows.SWATCH_W < bottom[-1] < zone - run


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
    header = P.Header("2 Mile Madison", "Group A", status)
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


def record_bands(monkeypatch, slants: list[float] | None = None):
    """Every team row the page paints: its rect, sweep and color zone's right edge.

    ``slants``, when given, collects each row's slant.
    """
    from madtracker.board import team_rows

    bands: list[tuple[QRectF, float, float | None]] = []
    band = team_rows.paint_band

    def record(p, row, color, u, sweep=0.0, zone_right=None, slant=0.0):
        bands.append((QRectF(row), sweep, zone_right))
        if slants is not None:
            slants.append(slant)
        return band(p, row, color, u, sweep, zone_right, slant)

    monkeypatch.setattr(team_rows, "paint_band", record)
    return bands


def test_the_madison_table_names_view_shows_surnames_and_no_team_words(qtbot, drawn):
    data = standings(5)
    data.rows[1].entry.team = "Stars and Stripes"
    render(qtbot, "madison", data)
    s = strings(drawn)
    assert {"Okafor", "Haddad", "Delgado", "Mori"} <= set(s)
    assert "TEAM" not in s and "SPRINT PTS" not in s
    assert not set(s) & set(formats.TEAM_COLORS) and "Stars and Stripes" not in s
    firsts = {n.partition(" ")[0] for r in data.rows for n in r.entry.names}
    assert not set(s) & firsts


@pytest.mark.parametrize(
    "teams, row_px, total, surname_px", [(1, 446, 127, 96), (2, 439, 115, 96), (5, 167, 104, 80)]
)
def test_madison_table_sizes_at_1080(qtbot, drawn, monkeypatch, teams, row_px, total, surname_px):
    """Design section 10: 5 teams give rows of 167 px, totals of 104 px,
    and surnames of 80 px; 2 teams 439, 115 and 96; a lone team 446, 127
    and 96. The rows start at the page's top, the place is 0.85 of the
    total, and the laps are under it."""
    from madtracker.board import pages, team_rows

    bands = record_bands(monkeypatch)
    data = standings(teams)
    w = render(qtbot, "madison", data)
    rows = [r for r, *_ in bands]
    assert {round(r.height()) for r in rows} == {row_px}
    assert rows[0].top() == pytest.approx(w.pages["madison"].margin_rect().top())
    for a, b in zip(rows, rows[1:], strict=False):
        assert b.top() - a.bottom() == pytest.approx(team_rows.ROW_GAP)
    assert sizes(drawn, [P.total_text(r.total) for r in data.rows]) == {total}
    assert sizes(drawn, surnames(data)) == {surname_px}
    [place] = sizes(drawn, ["1", "2", "3", "4", "5"])
    assert place == pytest.approx(total * pages.TEAM_PLACE_SCALE, abs=1)
    [laps] = sizes(drawn, ["+1L", "−1L"])
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
    [laps] = sizes(drawn, ["+1L"])
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


HEADINGS = {"#", "LAPS", "PENALTY", "TOTAL"}


def test_the_table_draws_no_column_headings(qtbot, drawn):
    """No heading row: the place, the colors, and the figures' order say
    which column is which, so the rows take the page from its top. Not
    while a lap and a penalty stand, not once decided, not in the color view."""
    for data in race_states(5):
        drawn.clear()
        w = render(qtbot, "madison", data)
        assert not HEADINGS & set(strings(drawn)), data.header.status
    assert {"+1L", "−20", "1st"} <= set(strings(drawn))
    clocked(w, color_view_ms())
    drawn.clear()
    w.grab()
    assert LONG_TEAM in strings(drawn) and not HEADINGS & set(strings(drawn))


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
    """The leader's place in the accent; the laps in the gain or loss color
    and the total in white on the dark row, each column right-aligned to
    one edge."""
    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    w = render(qtbot, "madison", standings(5))
    at = {s: (r, c) for s, r, _px, c in drawn}
    assert at["1"][1] == t.ACCENT.name() and at["2"][1] == t.TEXT.name()
    assert at["+1L"][1] == t.GAIN.name() and at["−1L"][1] == t.LOSS.name()
    assert at["28"][1] == at["−14"][1] == t.TEXT.name()
    assert at["28"][0].right() == pytest.approx(at["−14"][0].right())
    assert at["+1L"][0].right() == pytest.approx(at["−1L"][0].right())
    assert at["+1L"][0].right() < at["28"][0].right()
    # The place left of the row, the names on it, the figures at its right end.
    row = bands[0][0]
    assert row.right() == pytest.approx(w.pages["madison"].margin_rect().right())
    assert at["1"][0].right() <= row.left()
    okafor, haddad = at["Okafor"][0], at["Haddad"][0]
    laps_ink = at["+1L"][0].right() - t.text_width(
        "+1L", t.font(sizes(drawn, ["+1L"]).pop(), t.BOLD, tabular=True)
    )
    assert row.left() < okafor.left() < haddad.left() and okafor.right() < laps_ink
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
    laps = next(r for s, r, *_ in drawn if s == "+1L")
    assert {sweep for _r, sweep, _z in bands} == {1.0}
    assert all(z < laps.left() for _r, _s, z in bands)
    # The name is centered on the area, across the row's middle.
    row, _sweep, zone = bands[0]
    red = next(r for s, r, *_ in drawn if s == "Red")
    middle = zone - t.SLANT * row.height() / 2
    assert red.center().x() == pytest.approx((row.left() + middle) / 2, abs=1)
    assert red.center().y() == pytest.approx(row.center().y(), abs=1)


def surname_clearance(drawn, bands, data, u: float) -> float:
    """The least air between a row's slanted swatch and its surnames' capitals."""
    from PySide6.QtGui import QFontMetricsF

    from madtracker.board import team_rows
    from madtracker.board import theme as t

    at = {s: (r, px) for s, r, px, _c in drawn}
    least = float("inf")
    for (row, _sweep, _zone), r in zip(bands, data.rows, strict=True):
        for name in r.entry.names:
            rect, px = at[surname(name)]
            fm = QFontMetricsF(t.font(px, t.HEAVY))
            top = rect.center().y() + (fm.ascent() - fm.descent()) / 2 - fm.capHeight()
            # The swatch's right edge at the top of the capitals, where it is nearest.
            edge = row.left() + team_rows.SWATCH_W * u + t.SLANT * (row.bottom() - top)
            least = min(least, rect.left() - edge)
    return least


@pytest.mark.parametrize("teams", [1, 2, 5, 8])
def test_the_surnames_stand_clear_of_the_slanted_swatch(qtbot, drawn, monkeypatch, teams):
    """However tall the row, and so however far the swatch leans, the
    surnames' capitals keep SLANT_AIR from it, as a race goes on too."""
    from madtracker.board import team_rows

    slants: list[float] = []
    bands = record_bands(monkeypatch, slants)
    for data in race_states(teams):
        bands.clear()
        drawn.clear()
        w = render(qtbot, "madison", data)
        u = w.pages["madison"].u
        assert surname_clearance(drawn, bands, data, u) >= team_rows.SLANT_AIR * u - 0.01
    from madtracker.board import theme as t

    assert set(slants) == {t.SLANT}


@pytest.mark.parametrize("teams", [1, 2, 5, 8])
def test_the_team_name_stands_inside_the_slanted_color(qtbot, drawn, monkeypatch, teams):
    """The color view's name, as wide as its room, keeps clear of the
    color's square left end and of its slanted right end at the bottom of
    its line."""
    from PySide6.QtGui import QFontMetricsF

    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    data = race_states(teams)[-1]
    w = render(qtbot, "madison", data)
    clocked(w, color_view_ms(teams))
    bands.clear()
    drawn.clear()
    w.grab()
    row, sweep, zone = bands[0]
    assert sweep == 1.0
    rect, px = next((r, px) for s, r, px, _c in drawn if s == LONG_TEAM)
    h = QFontMetricsF(t.font(px, t.HEAVY)).height()
    bottom = rect.center().y() + h / 2
    # The color's right end where it meets the line's bottom: the nearest it comes.
    right = zone - t.SLANT * (bottom - row.top())
    assert row.left() < rect.left() and rect.right() < right


def test_the_chip_and_the_rows_share_one_slant(qtbot, drawn, monkeypatch):
    """The chip is sheared and the rows are cut by the one slant, leaning
    the same way: a different slant moves both."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QTransform

    from madtracker.board import theme as t

    monkeypatch.setattr(t, "SLANT", 0.3)
    shears: list[tuple[float, float]] = []
    shear = QPainter.shear

    def record(self, sh, sv):
        shears.append((sh, sv))
        return shear(self, sh, sv)

    monkeypatch.setattr(QPainter, "shear", record)
    slants: list[float] = []
    record_bands(monkeypatch, slants)
    prev = standings(5)
    w, clock = playing(qtbot, prev)
    w.set_layout("madison", scored(prev, {"Red": 5}))
    frame(w, clock, drawn, 100)
    assert set(slants) == {0.3} and set(shears) == {(-0.3, 0)}
    # The chip's sides lean as the row's left end does: the top right of the bottom.
    tilt = QTransform().shear(*shears[0])
    top, bottom = tilt.map(QPointF(0, 0)), tilt.map(QPointF(0, 1))
    assert top.x() - bottom.x() == pytest.approx(0.3)


def test_the_start_list_rows_take_the_tables_slant(qtbot, monkeypatch):
    """The start list's swatch is the table's, so the turn from one to
    the other crossfades like for like."""
    from madtracker.board import theme as t

    slants: list[float] = []
    record_bands(monkeypatch, slants)
    render(qtbot, "pre_race", start_list(5))
    assert set(slants) == {t.SLANT}


def swatch_air(row: QRectF, x: float, top: float, u: float) -> float:
    """The air between the swatch's slanted right edge and ``x``, at the height ``top``."""
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    return x - (row.left() + team_rows.SWATCH_W * u + t.SLANT * (row.bottom() - top))


def record_plates(monkeypatch) -> list[QRectF]:
    from madtracker.board import theme as t

    plates: list[QRectF] = []
    plate = t.plate

    def record(p, r, bib, out=False):
        plates.append(QRectF(r))
        return plate(p, r, bib, out)

    monkeypatch.setattr(t, "plate", record)
    return plates


def first_plate_air(bands, plates, u: float) -> float:
    """The least air between a row's swatch and the plate nearest it."""
    least = float("inf")
    for row, *_ in bands:
        mine = [pl for pl in plates if row.contains(pl.center())]
        if mine:
            near = min(mine, key=lambda pl: pl.left())
            least = min(least, swatch_air(row, near.left(), near.top(), u))
    return least


@pytest.mark.parametrize("label", ["names", "bibs_names", "bibs"])
@pytest.mark.parametrize("teams", [1, 2, 5, 8])
def test_the_start_list_names_and_plates_stand_clear_of_the_swatch(
    qtbot, drawn, monkeypatch, teams, label
):
    """However tall the row, and so however far the swatch's top leans,
    the first rider's plate and the capitals of the stacked name keep
    SLANT_AIR from its slanted right edge."""
    from PySide6.QtGui import QFontMetricsF

    from madtracker.board import team_rows
    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    plates = record_plates(monkeypatch)
    data = start_list(teams)
    if teams > 1:
        # A rider with no bib is named with Bibs Only, so the stacked name
        # stands where the plate would.
        data.roster[-1].bibs = ["", data.roster[-1].bibs[1]]
    w = render(qtbot, "pre_race", data, label=label)
    u = w.pages["pre_race"].u
    air = team_rows.SLANT_AIR * u - 0.01
    if label != "names":
        assert plates and first_plate_air(bands, plates, u) >= air
    at = {s: (r, px) for s, r, px, _c in drawn}
    for (row, *_), e in zip(bands, data.roster, strict=True):
        if label == "bibs" and e.bibs[0]:
            continue
        first, last = e.names[0].split(" ", 1)
        for word, weight in ((first, t.SEMI), (last, t.HEAVY)):
            rect, px = at[word]
            fm = QFontMetricsF(t.font(px, weight))
            top = rect.y() + fm.ascent() - fm.capHeight()
            assert swatch_air(row, rect.left(), top, u) >= air, (word, teams, label)


@pytest.mark.parametrize("teams", [1, 2, 5, 8])
def test_the_tables_bib_plates_stand_clear_of_the_swatch(qtbot, monkeypatch, teams):
    """With Bibs Only the plates stand where the surnames would, and keep
    SLANT_AIR from the swatch's slanted edge at their largest, as a race
    goes on too."""
    from madtracker.board import team_rows

    bands = record_bands(monkeypatch)
    plates = record_plates(monkeypatch)
    for data in race_states(teams):
        bands.clear()
        plates.clear()
        w = render(qtbot, "madison", data, label="bibs")
        u = w.pages["madison"].u
        assert first_plate_air(bands, plates, u) >= team_rows.SLANT_AIR * u - 0.01


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
        held = ("28", "+1L", "1", "−14")
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
    assert at["+5"][0].right() == pytest.approx(at["28"][0].right(), abs=1)
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
    assert "−1L" not in at
    at = frame(w, clock, drawn, SETTLED)
    # Black's old 6 is gone; Yellow's 6 stays.
    assert "−14" in at and "−1L" in at and strings(drawn).count("6") == 1


def zero_table(teams: int = 5) -> P.Standings:
    """The table a Madison's start list turns into: every team at 0, in start-list order."""
    roster = start_list(teams).roster
    rows = [P.StandingRow(rank=i + 1, entry=e, sprints=[]) for i, e in enumerate(roster)]
    header = replace(HEADER, status="After Sprint 1 of 4")
    return P.Standings(header=header, sprint_count=4, rows=rows, current_sprint=1)


def turn_ms(teams: int = 5) -> float:
    """When the turn from the start list and its hold end and the first score plays."""
    from madtracker.board import scorebug

    return scorebug.intro_ms(teams) + scorebug.INTRO_HOLD_MS


def test_the_first_sprint_plays_from_a_zero_table_in_start_list_order(qtbot, drawn):
    prev = start_list(5)
    data = scored(zero_table(5), {"Red": 5, "Orange": 3})
    w, clock = playing(qtbot, prev, layout="pre_race")
    w.set_layout("madison", data)
    at = frame(w, clock, drawn, turn_ms() + 100)
    # Every total reads 0, Red's old one too as it is knocked down.
    assert strings(drawn).count("0") == 5
    assert order(at, RIDERS) == ["Delgado", "Okafor", "Kowalczyk", "Whitfield", "Ferreira"]
    at = frame(w, clock, drawn, turn_ms() + SETTLED)
    assert order(at, RIDERS) == ["Okafor", "Kowalczyk", "Delgado", "Whitfield", "Ferreira"]
    assert {"5", "3"} <= set(at)


# The turn from the start list -----------------------------------------------------


@pytest.mark.parametrize("teams", range(1, 9))
def test_the_start_list_and_the_table_stand_their_rows_on_the_same_bands(
    qtbot, drawn, monkeypatch, teams
):
    """The turn fades each start list row into the table's row on the same band."""
    bands = record_bands(monkeypatch)
    w = render(qtbot, "pre_race", start_list(teams))
    start = [(r.top(), r.bottom()) for r, _s, _z in bands]
    bands.clear()
    w.set_layout("madison", zero_table(teams))
    w.grab()
    assert [(r.top(), r.bottom()) for r, _s, _z in bands] == start
    assert len(start) == teams


def record_looks(monkeypatch) -> list[tuple[str, float, float]]:
    """Every string the board paints, with the painter's opacity and its shift right."""
    from madtracker.board import theme

    looks: list[tuple[str, float, float]] = []
    text = theme.text

    def record(p, rect, s, *args, **kwargs):
        looks.append((s, p.opacity(), p.transform().dx()))
        return text(p, rect, s, *args, **kwargs)

    monkeypatch.setattr(theme, "text", record)
    return looks


def turning(qtbot, teams: int = 5):
    """A clocked board on a Madison's start list, and the first sprint's payload."""
    prev = start_list(teams)
    w, clock = playing(qtbot, prev, layout="pre_race")
    return w, clock, prev, scored(zero_table(teams), {"Red": 5, "Orange": 3})


def test_the_first_score_turns_the_start_list_into_the_table_row_by_row(qtbot, drawn, monkeypatch):
    from madtracker.board import scorebug

    chips = record_chips(monkeypatch)
    looks = record_looks(monkeypatch)
    w, clock, _prev, data = turning(qtbot)
    picture = w.pages["pre_race"].grab().toImage()
    w.set_layout("madison", data)
    page = w.pages["madison"]
    # At once the page is still the start list, every row of it, and no total.
    clock.advance(0)
    looks.clear()
    assert page.grab().toImage() == picture
    assert not looks and not chips and page.scoring_now()
    # Partway, the rows turn top to bottom: the first nearly in, the last
    # still fading in from the right.
    looks.clear()
    frame(w, clock, drawn, 4 * scorebug.INTRO_STAGGER_MS + 80)
    seen = {s: (op, dx) for s, op, dx in looks}
    first, last = seen["Delgado"], seen["Ferreira"]
    assert first[0] > last[0] > 0
    assert 0 <= first[1] < last[1] <= scorebug.INTRO_DRIFT
    # The zero table holds with no chip until the turn and the hold end.
    at = frame(w, clock, drawn, turn_ms() - 1)
    assert not chips and strings(drawn).count("0") == 5
    assert {op for s, op, _dx in looks if s in at} >= {1.0}
    frame(w, clock, drawn, turn_ms() + 50)
    assert [s for s, *_ in chips] == ["+5"]


def test_a_redraw_mid_turn_leaves_it_turning(qtbot, drawn, monkeypatch):
    chips = record_chips(monkeypatch)
    w, clock, _prev, data = turning(qtbot)
    w.set_layout("madison", data)
    frame(w, clock, drawn, 300)
    w.set_layout("madison", quiet(data))
    frame(w, clock, drawn, 400)
    assert w.pages["madison"].scoring_now() and not chips
    frame(w, clock, drawn, turn_ms() + 50)
    assert [s for s, *_ in chips] == ["+5"]


def test_a_second_score_mid_turn_plays_after_the_first(qtbot, drawn, monkeypatch):
    chips = record_chips(monkeypatch)
    w, clock, _prev, data = turning(qtbot)
    w.set_layout("madison", data)
    frame(w, clock, drawn, 300)
    w.set_layout("madison", scored(data, {"Blue": 4}))
    frame(w, clock, drawn, turn_ms() + 50)
    assert [s for s, *_ in chips] == ["+5"]
    chips.clear()
    frame(w, clock, drawn, turn_ms() + SETTLED)
    assert [s for s, *_ in chips] == ["+4"]


def test_an_undo_mid_turn_shows_the_current_state_at_once(qtbot, drawn, monkeypatch):
    chips = record_chips(monkeypatch)
    # Back to the start list.
    w, clock, prev, data = turning(qtbot)
    w.set_layout("madison", data)
    frame(w, clock, drawn, 300)
    w.set_layout("pre_race", prev)
    at = frame(w, clock, drawn, 310)
    assert w.layout_name() == "pre_race" and "0" not in at and "Kowalczyk" in at
    assert not w.pages["madison"].scoring_now()
    # To another table: it shows whole, with nothing left to play.
    w, clock, _prev, data = turning(qtbot)
    w.set_layout("madison", data)
    frame(w, clock, drawn, 300)
    other = scored(zero_table(5), {"Blue": 2})
    w.set_layout("madison", quiet(other))
    looks = record_looks(monkeypatch)
    at = frame(w, clock, drawn, 310)
    assert {"2", "1"} <= set(at) and {op for _s, op, _dx in looks} == {1.0}
    assert not w.pages["madison"].scoring_now()
    frame(w, clock, drawn, turn_ms() + 50)
    assert not chips


def test_the_tv_and_the_preview_turn_together_when_one_paints_late(qtbot):
    from madtracker.board.motion import ManualClock
    from madtracker.board.window import ScoreboardWindow

    prev = start_list(5)
    data = scored(zero_table(5), {"Red": 5, "Orange": 3})
    clock = ManualClock()
    boards = []
    for _ in range(2):
        w = ScoreboardWindow("Test Velodrome", "Test Event")
        qtbot.addWidget(w)
        w.resize(1920, 1080)
        w.set_clock(clock)
        w.set_layout("pre_race", prev)
        w.grab()
        boards.append(w)
    for w in boards:
        w.set_layout("madison", data)
    tv, preview = boards
    # The TV paints every step; the preview first paints partway.
    for at in (100, 200, 300, 350):
        clock.advance(at - clock.now())
        if at < 350:
            tv.grab()
    assert tv.grab().toImage() == preview.grab().toImage()
    clock.advance(turn_ms() + 300 - clock.now())
    assert tv.grab().toImage() == preview.grab().toImage()


def test_a_headless_board_turns_to_the_table_at_once(qtbot, drawn, monkeypatch):
    chips = record_chips(monkeypatch)
    w = render(qtbot, "pre_race", start_list(5))
    drawn.clear()
    w.set_layout("madison", scored(zero_table(5), {"Red": 5, "Orange": 3}))
    w.grab()
    assert not chips and {"5", "3"} <= set(strings(drawn))
    assert not w.pages["madison"].scoring_now()


def test_a_race_coming_back_to_the_board_shows_its_table_without_a_turn(qtbot, drawn, monkeypatch):
    chips = record_chips(monkeypatch)
    looks = record_looks(monkeypatch)
    w, clock, _prev, data = turning(qtbot)
    other = standings(5)
    other.header.race_id = 2
    w.set_layout("madison", other)
    frame(w, clock, drawn, 100)
    w.set_layout("madison", data)
    looks.clear()
    at = frame(w, clock, drawn, 110)
    assert {"5", "3"} <= set(at) and not chips
    assert {op for _s, op, _dx in looks} == {1.0}
    assert not w.pages["madison"].scoring_now()


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
    from madtracker.board import rotation, scorebug

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
    # When the scoring ends the rotation starts over on the names view,
    # from the moment the last total landed, not from the next paint.
    drained = start + scorebug.SWAP_AT_MS + scorebug.SWAP_MS
    bands.clear()
    frame(w, clock, drawn, start + 2000)
    assert not page.scoring_now()
    assert {s for _r, s, _z in bands} == {0.0}
    assert page.since() == pytest.approx(start + 2000 - drained)
    assert page.wake_in() == pytest.approx(rotation.NAMES_MS - (start + 2000 - drained), abs=1)
    bands.clear()
    frame(w, clock, drawn, drained + rotation.NAMES_MS + 330)
    assert max(s for _r, s, _z in bands) > 0


def sweeps_through(w, clock, drawn, bands, ats) -> list[list[float]]:
    """Each row's sweep at each of the clock times ``ats``."""
    seen = []
    for at in ats:
        bands.clear()
        frame(w, clock, drawn, at)
        seen.append([s for _r, s, _z in bands])
    return seen


@pytest.mark.parametrize("kind", ["lap_gained", "sprint"])
def test_a_score_change_in_the_color_view_eases_back_to_names_after(
    qtbot, drawn, monkeypatch, kind
):
    """The slams play over the color view; once the queue drains the table
    takes the change back to names, never a jump. A sprint's new header
    leaves the rotation where it stands."""
    from madtracker.board import rotation, scorebug

    bands = record_bands(monkeypatch)
    prev = standings(5)
    if kind == "sprint":
        data = scored(prev, {"Red": 5, "Orange": 3}, status="After Sprint 3 of 4")
    else:
        data = scored(prev, {"Black": 20}, kind=kind, laps={"Black": 1})
    w, clock = playing(qtbot, prev, size=(960, 540))
    page = w.pages["madison"]
    start = color_view_ms() + 500
    before = sweeps_through(w, clock, drawn, bands, [start])
    w.set_layout("madison", data)
    drained = start + scorebug.duration(page._queue.playing(clock.now()))
    change = rotation.change_ms(5)
    first = sweeps_through(w, clock, drawn, bands, range(start + 16, start + 160, 16))
    held = sweeps_through(w, clock, drawn, bands, range(start + 200, drained - 160, 200))
    last = sweeps_through(w, clock, drawn, bands, range(drained - 160, drained + change + 200, 16))
    assert all(s == [1.0] * 5 for s in before + first + held)
    steps = before + first
    for frames in (steps, last):
        for a, b in zip(frames, frames[1:], strict=False):
            assert max(abs(x - y) for x, y in zip(a, b, strict=True)) < 0.25
    assert last[0] == [1.0] * 5 and last[-1] == [0.0] * 5
    assert any(0 < s < 1 for f in last for s in f)
    # Then the names hold, in full.
    rest = sweeps_through(w, clock, drawn, bands, [drained + change + rotation.NAMES_MS - 100])
    assert rest == [[0.0] * 5]


def test_only_a_new_race_starts_the_rotation_over_on_the_first_pages_names(
    qtbot, drawn, monkeypatch
):
    from madtracker.board import rotation

    bands = record_bands(monkeypatch)
    prev = standings(12)
    names = surnames(prev)
    second = [r.entry.team for r in prev.rows[6:]]
    w, clock = playing(qtbot, prev, size=(960, 540))
    start = rotation.cycle_ms(6) + color_view_ms(6)
    bands.clear()
    at = frame(w, clock, drawn, start)
    assert {s for _r, s, _z in bands} == {1.0} and set(second) <= set(at)
    # The same race's new status leaves the color view and the page in view.
    status = copy.deepcopy(prev)
    status.header.status = "After Sprint 3 of 4"
    w.set_layout("madison", status)
    bands.clear()
    at = frame(w, clock, drawn, start + 16)
    assert {s for _r, s, _z in bands} == {1.0} and set(second) <= set(at)
    other = copy.deepcopy(prev)
    other.header.race_id = 2
    w.set_layout("madison", other)
    bands.clear()
    at = frame(w, clock, drawn, start + 32)
    assert {s for _r, s, _z in bands} == {0.0}
    assert [s for s in strings(drawn) if s in names] == names[:12]


def test_a_board_that_paints_nothing_while_the_scoring_ends_keeps_in_step(
    qtbot, drawn, monkeypatch
):
    """The TV hidden while the last total lands, or a minimized operator
    window's preview, turns its views and pages with the board that
    painted: both restart the rotation when the queue emptied."""
    from madtracker.board import rotation, scorebug
    from madtracker.board.motion import ManualClock
    from madtracker.board.window import ScoreboardWindow

    bands = record_bands(monkeypatch)
    # In place order, so Red's points leave the rows where they stand.
    prev = quiet(scored(standings(12), {}))
    data = scored(prev, {"Red": 5})
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
    painted, idle = boards
    drained = scorebug.SWAP_AT_MS + scorebug.SWAP_MS
    for at in (100, 800, drained + 10):
        clock.advance(at - clock.now())
        painted.grab()
    # The idle board first paints mid-change, a whole cycle and more later,
    # on the second page.
    clock.advance(drained + rotation.cycle_ms(6) + rotation.NAMES_MS + 300 - clock.now())
    seen = []
    for w in boards:
        bands.clear()
        drawn.clear()
        w.grab()
        page = w.pages["madison"]
        sweeps = [round(s, 6) for _r, s, _z in bands]
        seen.append((page.since(), sweeps, sorted(strings(drawn))))
    assert seen[0] == seen[1]
    assert 0 < max(seen[0][1]) < 1
    assert set(seen[0][2]) & {surname(NAMES[b]) for b in key("Brown")}


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


def test_a_lost_lap_and_a_penalty_read_apart_without_headings(qtbot, drawn):
    """With no headings, the laps carry an L ("−1L") and a penalty stays a
    bare figure ("−5"); both are in the loss color at the figure's size."""
    from madtracker.board import theme as t

    data = standings(5)
    for r in data.rows:
        r.laps = 0
    data.rows[0].laps, data.rows[0].penalty = -1, -5
    data.rows[1].laps = 1
    render(qtbot, "madison", data)
    at = {s: (px, c) for s, _r, px, c in drawn}
    assert at["−1L"][1] == t.LOSS.name() and at["−5"][1] == t.LOSS.name()
    assert at["+1L"][1] == t.GAIN.name()
    assert at["−1L"][0] == at["−5"][0] == at["+1L"][0]
    assert "−1" not in at and "+1" not in at


@pytest.mark.parametrize("teams", [1, 2, 5])
def test_the_first_lap_with_its_l_never_steps_the_figures_down(qtbot, drawn, teams):
    """The laps column is measured with the L, so the first lap gained or lost
    leaves the totals, the surnames, and the laps size where they were."""
    seen = []
    for laps in (0, 1, -1, 8, -8):
        data = standings(teams)
        for r in data.rows:
            r.laps = 0
        data.rows[0].laps = laps
        data.rows[-1].penalty = -5 if laps else 0
        seen.append(table_sizes(qtbot, drawn, data))
    assert all(s == seen[0] for s in seen)
