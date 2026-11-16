"""The Madison on the board: the start list names its riders, each team a swatch and fade."""

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


@pytest.mark.parametrize("teams", [1, 2])
def test_a_small_tables_totals_keep_their_share_and_its_surnames_stop_at_96(
    qtbot, drawn, monkeypatch, teams
):
    """One or two teams keep the totals at their share of the tall row, as
    the riders asked; the surnames stop at the start list's largest and
    fit whole."""
    from madtracker.board import pages, team_rows

    bands = record_bands(monkeypatch)
    data = standings(teams)
    w = render(qtbot, "madison", data)
    u = w.pages["madison"].u
    rh = bands[0][0].height()
    totals = [P.total_text(r.total) for r in data.rows]
    assert sizes(drawn, totals) == {round(rh * pages.TEAM_FIGURE_SHARE)}
    places = [str(r.rank) for r in data.rows]
    assert sizes(drawn, places) == {round(rh * pages.TEAM_FIGURE_SHARE * pages.TEAM_PLACE_SCALE)}
    [surname_px] = sizes(drawn, surnames(data))
    assert surname_px <= round(team_rows.START_SURNAME_MOST * u)
    # Whole: drawn as given, never cut.
    assert set(surnames(data)) <= set(strings(drawn))


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
