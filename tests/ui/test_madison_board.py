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
