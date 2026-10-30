"""Full fields on the board: names stay readable, one size per list, sprints fold."""

import re
from dataclasses import replace

import pytest
from PySide6.QtCore import QRectF

from madtracker.board import payloads as P

# Invented riders, long on purpose. The first word is the first name.
LONG = [
    "Maximiliana Vanderbilt-Rochester",
    "Bartholomew Montgomery-Blackwood",
    "Christopher-James Kowalczyk",
    "Anneliese Szczepanowski",
    "Konstantinos Papadopoulos",
    "Evangelina Abernathy",
    "Nathaniel Featherstonehaugh",
    "Wilhelmina Oyelaran-Smith",
]
SHORT = ["Ada Quill", "Bo Lin", "Cy Dorn", "Di Ash"]
# Names of a usual length, for a list whose growth the widest name decides.
MID = ["Arlo Quillan", "Bexa Yarrow", "Corin Fallowby", "Dalia Vesk", "Emrys Dunhallow",
       "Fenna Tamsk", "Galo Brisk", "Hesper Rendt"]  # fmt: skip
COLORS = ["#f2f2f2", "#f28c28", "#222222", "#2ca44e", "#e03c3c", "#ee5fb5"]
HEADER = P.Header(title="Test Race", group="Pro", status="Racing")


def _name(i: int) -> str:
    return LONG[i % len(LONG)]


def _last(name: str) -> str:
    return name.partition(" ")[2]


def points(riders: int = 12, sprints: int = 9, done: int = 7) -> P.Standings:
    rows = []
    for i in range(riders):
        # Distinct, recognizable values: rider i scores 10 + i in sprint 1
        # and i % 4 in the others, so every Earlier sum is predictable.
        sp = [10 + i] + [i % 4] * (done - 1) + [None] * (sprints - done)
        rows.append(
            P.StandingRow(
                rank=i + 1,
                entry=P.Entry(bibs=[str(500 + i)], names=[_name(i)]),
                sprints=sp,
                total=1000 + i,
            )
        )
    return P.Standings(header=HEADER, sprint_count=sprints, rows=rows, current_sprint=done)


def madison(teams: int = 12, sprints: int = 6) -> P.Standings:
    rows = []
    for i in range(teams):
        names = [_name(i), SHORT[i % len(SHORT)]] if i % 2 else [SHORT[i % 4], _name(i + 3)]
        entry = P.Entry(
            bibs=[str(i + 1), str(i + 41)],
            names=names,
            team=f"Team {i + 1}",
            color=COLORS[i % len(COLORS)],
        )
        rows.append(P.StandingRow(rank=i + 1, entry=entry, sprints=[1] * 4 + [None] * 2))
    return P.Standings(header=HEADER, sprint_count=sprints, rows=rows, current_sprint=4)


def elimination(remaining: int = 14) -> P.Elimination:
    es = [P.Entry(bibs=[str(i + 1)], names=[_name(i)]) for i in range(remaining + 1)]
    return P.Elimination(header=HEADER, remaining=es[:remaining], last_eliminated=es[remaining])


def finish(n: int = 16) -> P.Finish:
    return P.Finish(
        header=HEADER,
        placings=[P.Placing(i + 1, P.Entry(bibs=[str(i + 1)], names=[_name(i)])) for i in range(n)],
    )


@pytest.fixture
def drawn(monkeypatch):
    """Every string the board paints, with its rect, pixel size and color."""
    from madtracker.board import theme

    seen: list[tuple[str, object, int, str]] = []
    text = theme.text

    def record(p, rect, s, f, color, *args, **kwargs):
        seen.append((s, rect, f.pixelSize(), color.name()))
        return text(p, rect, s, f, color, *args, **kwargs)

    monkeypatch.setattr(theme, "text", record)
    return seen


def render(qtbot, layout, data, size=(1920, 1080), bibs=True):
    from madtracker.board.window import ScoreboardWindow

    w = ScoreboardWindow("Test Velodrome", "Test Event")
    qtbot.addWidget(w)
    w.set_show_bibs(bibs)
    w.resize(*size)
    w.set_layout(layout, data)
    w.grab()
    return w


def strings(drawn) -> list[str]:
    return [s for s, *_ in drawn]


def test_a_race_page_header_holds_the_status_alone_and_not_the_event(qtbot, drawn):
    """The event's name is the logo page's: a race page's header carries the
    race, its group and format, and the status centered in the bar."""
    import dataclasses

    header = P.Header(title="8 Mile Madison", group="Group A", detail="Madison", status="Racing")
    w = render(qtbot, "madison", dataclasses.replace(madison(teams=5), header=header))
    assert "Test Event" not in strings(drawn)
    status = next(r for s, r, *_ in drawn if s == "Racing")
    assert status.center().y() == pytest.approx(w.top_bar.height() / 2, abs=1)


# fit_name -----------------------------------------------------------------


def test_fit_name_cuts_the_first_name_before_the_last(qapp):
    from madtracker.board import theme as t

    f = t.font(40)
    full = "Maximiliana Vanderbilt-Rochester"
    short = "M. Vanderbilt-Rochester"
    assert t.fit_name(full, t.text_width(full, f) + 1, f) == full
    assert t.fit_name(full, t.text_width(short, f) + 1, f) == short
    cut = t.fit_name(full, t.text_width(short, f) * 0.7, f)
    assert cut.startswith("M. Vander") and cut.endswith("…")
    # A one-word name can only be elided.
    assert t.fit_name("Cher", 1, f) != "Cher"


def test_initialed_keeps_a_multi_word_last_name(qapp):
    from madtracker.board import theme as t

    assert t.initialed("Jan van der Berg") == "J. van der Berg"
    assert t.initialed("Cher") is None


# Standings ------------------------------------------------------------------


@pytest.mark.parametrize("bibs", [True, False], ids=["bibs", "names-only"])
def test_standings_show_place_name_sprints_laps_and_total_and_no_sprint_columns(qtbot, drawn, bibs):
    """Riders read the board at speed for their place, total and laps;
    sprint columns would squeeze long team names and make the table too
    busy. Each sprint shows on its card as it lands, and one SPRINT PTS
    column sums them (a bare number under SPRINTS reads as a count of
    sprints) and LAPS holds the laps alone, without the points in
    parentheses."""
    data = points(riders=10)
    data.rows[0].sprints = [0] * 7 + [None] * 2
    render(qtbot, "sprint_points", data, bibs=bibs)
    seen = strings(drawn)
    assert "RIDER" in seen and "SPRINT PTS" in seen and "LAPS" in seen and "TOTAL" in seen
    assert "SPRINTS" not in seen
    assert not [s for s in seen if re.fullmatch(r"S\d+(-S\d+)?", s)]
    # Every rider's last name is on the board, whole, every total, and
    # the sprint points so far as a plain number (no "+": that is a lap).
    for row in data.rows[1:]:
        assert any(_last(row.entry.names[0]) in s for s in seen), row.entry.names[0]
        assert str(row.total) in seen
        assert str(sum(v for v in row.sprints if v)) in seen
    assert not [s for s in seen if s.startswith("+") and "lap" not in s.lower()]
    # A rider yet to score shows nothing in the column, not a zero.
    assert seen.count("0") == 0
    drawn.clear()
    data.rows[3].laps = 1
    data.rows[3].lap_points = 20
    render(qtbot, "sprint_points", data, bibs=bibs)
    seen = strings(drawn)
    assert "+1" in seen and not [s for s in seen if "(" in s]


def test_long_standings_turn_pages_instead_of_shrinking(qtbot, drawn):
    from madtracker.board.pages import PAGE_ROWS

    data = points(riders=24)
    w = render(qtbot, "sprint_points", data)
    page = w.pages["sprint_points"]
    seen = strings(drawn)
    # The pages share the rows evenly: 24 is 12 and 12, never 16 and 8.
    assert PAGE_ROWS == 16 and page.page_count() == 2
    # Totals are unique per rider (1000 plus the index): the 13th waits for page 2.
    assert "1000" in seen and "1011" in seen and "1012" not in seen
    assert not any(" of 24" in s for s in seen), "page dots, no footer to read"
    # Twelve rows read at the size a twelve-rider table has: no shrinking for the rest.
    sizes = {px for s, _r, px, _c in drawn if any(_last(n) in s for n in LONG)}
    drawn.clear()
    render(qtbot, "sprint_points", points(riders=12))
    twelve = {px for s, _r, px, _c in drawn if any(_last(n) in s for n in LONG)}
    assert abs(min(sizes) - min(twelve)) <= 1
    drawn.clear()
    page.advance()
    w.grab()
    seen = strings(drawn)
    assert "1023" in seen and "1012" in seen and "1000" not in seen
    assert w._pager.isActive()


def test_a_full_field_at_166_m_is_one_page(qtbot, drawn):
    """Sixteen riders, the most a 166 m track may start (USAC 2B7), stand
    on one page with every figure and name at the board's minimum or above."""
    from madtracker.board import theme

    data = points(riders=16)
    w = render(qtbot, "sprint_points", data)
    assert w.pages["sprint_points"].page_count() == 1
    seen = strings(drawn)
    for row in data.rows:
        assert str(row.total) in seen and str(row.rank) in seen
    for row in data.rows:
        assert any(_last(row.entry.names[0])[:8] in s for s in seen), row.entry.names[0]
    assert min(_unplated(drawn)) >= theme.MIN_PX


def test_madison_pages_hold_eight_teams(qtbot):
    w = render(qtbot, "madison", madison(teams=8))
    assert w.pages["madison"].page_count() == 1
    w = render(qtbot, "madison", madison(teams=12))
    # Twelve teams, the most a 166 m track allows, are two pages of six.
    assert w.pages["madison"].page_count() == 2


def _unplated(drawn) -> list[int]:
    """Pixel sizes of everything drawn but the digits on bib plates."""
    from madtracker.board import theme

    plates = {theme.PLATE_TEXT.name(), theme.PLATE_OUT_TEXT.name()}
    return [px for _s, _r, px, color in drawn if color not in plates]


def _laid_out(layout: str, n: int):
    if layout == "pre_race":
        return P.PreRace(
            header=HEADER,
            roster=[P.Entry(bibs=[str(i + 1)], names=[_name(i)]) for i in range(n)],
        )
    if layout == "elimination":
        return elimination(remaining=n - 1)
    if layout == "finish":
        return finish(n)
    return points(riders=n)


@pytest.mark.parametrize("n", [6, 12, 16, 24])
@pytest.mark.parametrize("layout", ["pre_race", "elimination", "finish", "sprint_points"])
@pytest.mark.parametrize("label", ["names", "bibs_names"])
def test_nothing_on_the_board_is_under_the_floor(qtbot, drawn, layout, n, label):
    """Design section 10: nothing smaller than a thirtieth of the screen
    height, for any field up to 24 riders (a 250 m track), names, figures,
    labels and the header's group chip alike. Bib plate digits are the one
    exception: a white plate reads by its shape and contrast."""
    from madtracker.board import theme
    from madtracker.board.window import ScoreboardWindow

    w = ScoreboardWindow("Test Velodrome", "Test Event")
    qtbot.addWidget(w)
    w.set_rider_label(label)
    w.resize(1920, 1080)
    w.set_layout(layout, _laid_out(layout, n))
    w.grab()
    assert min(_unplated(drawn)) >= theme.MIN_PX


@pytest.mark.parametrize("n", [16, 24])
def test_a_result_shows_every_place(qtbot, drawn, n):
    """A 16-rider result shows 16th; up to 24 the rows below the podium
    open a third column rather than leave places off."""
    render(qtbot, "finish", finish(n))
    seen = strings(drawn)
    assert all(P.ordinal(i) in seen for i in range(1, n + 1))


@pytest.mark.parametrize("n", [12, 24])
def test_start_list_rows_never_overlap(qtbot, drawn, n):
    """Twenty-four riders' names follow the row, so no name's descenders
    run into the next row (as 46 px names in 54 px rows would)."""
    data = _laid_out("pre_race", n)
    render(qtbot, "pre_race", data)
    names = {e.names[0] for e in data.roster} | {
        f"{e.names[0][0]}. {_last(e.names[0])}" for e in data.roster
    }
    rows = [(r.x(), r.y(), px) for s, r, px, _c in drawn if s in names]
    assert len(rows) == n
    for x in {x for x, _y, _px in rows}:
        col = sorted((y, px) for cx, y, px in rows if cx == x)
        for (y1, px), (y2, _px) in zip(col, col[1:], strict=False):
            assert y2 - y1 >= px * 1.21, (y1, y2, px)


def test_madison_team_names_share_one_size_and_no_rider_is_drawn(qtbot, drawn):
    data = madison()
    render(qtbot, "madison", data)
    # Each team's name on its block, every one at one size; the riders'
    # names are not on the page while the race runs.
    teams = {r.entry.team for r in data.rows}
    sizes = {px for s, _r, px, _c in drawn if s in teams}
    assert len(sizes) == 1, sizes
    seen = strings(drawn)
    assert not any("  /  " in s for s in seen)
    assert not any(_last(name) in s for r in data.rows for name in r.entry.names for s in seen)
    assert "S1" not in seen


def test_a_long_team_name_is_drawn_whole_on_the_madison_board(qtbot, drawn):
    """ "Stars and Stripes" has the room, with no sprint columns to squeeze it."""
    data = madison(teams=8)
    data.rows[2].entry.team = "Stars and Stripes"
    render(qtbot, "madison", data)
    seen = strings(drawn)
    assert "Stars and Stripes" in seen
    # The block is the row up to the figures, one width for every team.
    assert len({px for s, _r, px, _c in drawn if s in {r.entry.team for r in data.rows}}) == 1


def test_elimination_cards_share_one_size_and_initial_first_names(qtbot, drawn):
    data = elimination(remaining=6)
    render(qtbot, "elimination", data)
    seen = strings(drawn)
    card_sizes = {px for s, _r, px, _c in drawn if any(_last(n) in s for n in LONG)}
    # The cards share one size; the last-out card has its own.
    assert len(card_sizes) <= 2
    assert "M. Vanderbilt-Rochester" in seen
    assert not [s for s in seen if s.startswith("Maximiliana") and s.endswith("…")]


@pytest.mark.parametrize("size", [(1920, 1080), (1440, 900)])
@pytest.mark.parametrize("remaining", [1, 2, 3, 4])
def test_the_last_riders_plates_stay_inside_their_cards(qtbot, monkeypatch, size, remaining):
    """Three left on a big monitor: the plate is capped and never wider
    than the card, so the three never run together."""
    from madtracker.board import pages, theme

    plates: list = []
    plate = theme.plate

    def record(p, rect, bib, out=False):
        plates.append((rect, bib, out))
        return plate(p, rect, bib, out)

    monkeypatch.setattr(theme, "plate", record)
    w = render(qtbot, "elimination", elimination(remaining=remaining), size=size)
    u = w.pages["elimination"].u
    still = [r for r, bib, out in plates if not out and bib != str(remaining + 1)]
    assert len(still) == remaining
    assert all(r.height() <= pages.PLATE_CAP * u + 0.5 for r in still)
    # Air between neighbors in a row: at least the gap between the cards
    # themselves (four left are two rows of two).
    for row_y in {round(r.y()) for r in still}:
        row = sorted((r for r in still if round(r.y()) == row_y), key=lambda r: r.x())
        for a, b in zip(row, row[1:], strict=False):
            assert b.x() - a.right() >= 24 * u + 48 * u - 0.5


def test_the_out_earlier_plates_wrap_onto_rows_inside_the_side_column(qtbot, monkeypatch):
    """Twelve out before the last one: the plates run onto more than one row,
    newest first, and none passes the side column's right or bottom edge."""
    from madtracker.board import pages, theme

    plates: list = []
    plate = theme.plate

    def record(p, rect, bib, out=False):
        plates.append((rect, bib, out))
        return plate(p, rect, bib, out)

    sides: list = []
    remaining = pages.EliminationPage._remaining

    def side_of(self, p, side, y, n):
        sides.append(QRectF(side))
        return remaining(self, p, side, y, n)

    monkeypatch.setattr(theme, "plate", record)
    monkeypatch.setattr(pages.EliminationPage, "_remaining", side_of)
    es = [P.Entry(bibs=[str(i + 1)], names=[_name(i)]) for i in range(16)]
    data = P.Elimination(header=HEADER, remaining=es[:3], last_eliminated=es[3], eliminated=es[4:])
    render(qtbot, "elimination", data)
    side = sides[-1]
    out = [(r, bib) for r, bib, was_out in plates if was_out]
    assert [bib for _r, bib in out][:2] == ["16", "15"], "newest first"
    assert len({round(r.y()) for r, _bib in out}) > 1
    for r, bib in out:
        assert r.right() <= side.right() + 0.5 and r.bottom() <= side.bottom() + 0.5, bib


def test_a_big_elimination_opens_as_rows_with_names_at_the_floor(qtbot, drawn):
    """Thirteen to sixteen riders open as two columns of start-list rows,
    since four rows of cards would put names at 27 px and long ones at 19."""
    from madtracker.board import theme

    data = elimination(remaining=16)
    render(qtbot, "elimination", data)
    sizes = [px for s, _r, px, _c in drawn if any(_last(n) in s for n in LONG)]
    assert sizes and min(sizes) >= theme.MIN_PX
    assert "16" in strings(drawn)


def test_finish_recap_shares_one_size(qtbot, drawn):
    data = finish()
    render(qtbot, "finish", data)
    names = {pl.entry.names[0] for pl in data.placings[3:]}
    sizes = {px for s, r, px, _c in drawn if s in names and r.y() > 500}
    assert len(sizes) == 1, sizes


def test_board_scales_with_height(qtbot, drawn):
    data = points()
    render(qtbot, "sprint_points", data)
    small = {s: px for s, _r, px, _c in drawn}
    drawn.clear()
    render(qtbot, "sprint_points", data, size=(3840, 2160))
    big = {s: px for s, _r, px, _c in drawn}
    # Same strings at twice the size (within a pixel of rounding).
    assert set(small) == set(big)
    for s, px in small.items():
        assert abs(big[s] - 2 * px) <= 2, (s, px, big[s])


# Names only: stacked names and the long-name steps ---------------------------

# Invented, 28 characters: longer than any ordinary first and last name
# pair a table is designed to show whole.
LONGEST = "Evangelina Featherstonehaugh"


def _painted(draw, size=(800, 400)):
    """Run ``draw(painter)`` on a black image and return the image."""
    from PySide6.QtGui import QImage, QPainter

    img = QImage(*size, QImage.Format.Format_RGB32)
    img.fill(0)
    p = QPainter(img)
    try:
        draw(p)
    finally:
        p.end()
    return img


def _ink_bands(img) -> list[tuple[int, int]]:
    """Runs of inked rows, top and bottom: one per line of capitals."""
    bands: list[tuple[int, int]] = []
    for y in range(img.height()):
        if any(img.pixelColor(x, y).lightness() > 128 for x in range(0, img.width(), 2)):
            if bands and bands[-1][1] == y - 1:
                bands[-1] = (bands[-1][0], y)
            else:
                bands.append((y, y))
    return bands


def _names_page():
    from madtracker.board.pages import Page

    page = Page()
    page.rider_label = "names"
    return page


def test_two_line_name_is_one_block_centered_by_its_capitals(qapp, drawn):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFontMetricsF

    from madtracker.board import theme as t

    rect = QRectF(100, 60, 480, 280)
    px = 60
    # Capitals only, so each band of ink runs exactly from cap top to baseline.
    img = _painted(lambda p: _names_page().name_block(p, rect, "HELENE HAMMERHEIM", px))
    assert strings(drawn) == ["HELENE", "HAMMERHEIM"]
    (top1, base1), (top2, base2) = _ink_bands(img)
    # Baselines a little over an em apart, under the font's line box.
    assert abs((base2 - base1) - t.STACK_LEADING * px) <= 1.5
    assert base2 - base1 < QFontMetricsF(t.font(px, t.BOLD)).height()
    # The block of capitals sits on the rect's center line, inside the rect.
    assert abs((top1 + base2) / 2 - rect.center().y()) <= 1.5
    assert rect.top() < top1 and base2 < rect.bottom()


def test_one_line_name_is_centered_by_its_capitals(qapp, drawn):
    from PySide6.QtCore import QRectF

    rect = QRectF(100, 60, 600, 280)
    img = _painted(lambda p: _names_page().name_block(p, rect, "HAL HEM", 60))
    [(top, base)] = _ink_bands(img)
    assert abs((top + base) / 2 - rect.center().y()) <= 1.5


def test_madison_pair_is_one_block_centered_in_its_row(qapp, drawn):
    from PySide6.QtCore import QRectF

    from madtracker.board import theme as t

    rect = QRectF(0, 40, 1200, 120)
    entry = P.Entry(bibs=["1", "2"], names=["HAL HEM", "IAN HILL"], team="Team", color="#000000")
    page = _names_page()
    lines = [r for r, _s, _f, kind in page.entry_texts(rect, entry, 42, True) if kind == "name"]
    # The pair is set at 80% of the team name, but never under the floor.
    f = t.font(max(42 * 0.8, min(42, t.MIN_PX * page.u)), t.SEMI)
    assert [r.y() for r in lines] == [r.y() for r in t.stacked_lines(rect, f, 2)]
    assert lines[1].y() - lines[0].y() == pytest.approx(t.STACK_LEADING * f.pixelSize())


def test_name_block_steps_for_a_long_name(qapp, drawn):
    from PySide6.QtCore import QRectF

    from madtracker.board import theme as t

    page = _names_page()
    px = 50
    f = t.font(px, t.BOLD)
    first, last = LONGEST.split(" ")

    def shown(name: str, width: float) -> list[str]:
        drawn.clear()
        _painted(lambda p: page.name_block(p, QRectF(0, 0, width, 300), name, px))
        return strings(drawn)

    # Room for the whole name: one line.
    assert shown(LONGEST, t.text_width(LONGEST, f) + 2) == [LONGEST]
    # Room for the longer word: first name over last name.
    assert shown(LONGEST, t.text_width(last, f) + 2) == [first, last]
    # A first name too long for the card over a short last name: one initialed line.
    assert shown("Wilhelmina Lin", t.text_width("W. Lin", f) + 2) == ["W. Lin"]
    # Too narrow for the last name: the first name is down to its initial,
    # on its own line, and only then is the last name cut.
    initial, cut = shown(LONGEST, t.text_width(last, f) * 0.7)
    assert initial == "E." and cut.startswith("Feather") and cut.endswith("…")


def test_list_steps_for_a_long_name_in_names_only_mode(qapp, drawn):
    """One scale for the list down to the floor, then initial and last name, then elided."""
    from PySide6.QtCore import QRectF

    from madtracker.board import theme as t

    page = _names_page()
    # Large enough that NAME_FLOOR, not the board's minimum, is the floor.
    size = 52
    entries = [P.Entry(bibs=["1"], names=[LONGEST]), P.Entry(bibs=["2"], names=["Ada Quill"])]
    full = t.text_width(LONGEST, t.font(size, t.BOLD))
    short = t.text_width("E. Featherstonehaugh", t.font(size, t.BOLD))

    def shown(width: float) -> tuple[float, list[tuple[str, int]]]:
        rect = QRectF(0, 0, width, 80)
        scale = page.entry_scale(entries, rect, size)
        drawn.clear()
        for e in entries:
            _painted(lambda p, e=e: page.entry_line(p, rect, e, size, scale=scale), (1600, 100))
        return scale, [(s, px) for s, _r, px, _c in drawn]

    scale, out = shown(full + 4)
    assert scale == 1.0 and out[0][0] == LONGEST
    # A little short: the whole list shrinks together and the name stays whole.
    scale, out = shown(full * 0.85)
    assert t.NAME_FLOOR < scale < 1.0 and out[0][0] == LONGEST and out[0][1] == out[1][1]
    # Past the floor: the list stops shrinking and the long name is initialed.
    scale, out = shown(short * t.NAME_FLOOR + 4)
    assert scale == t.NAME_FLOOR and out == [("E. Featherstonehaugh", out[1][1]), out[1]]
    assert out[1][0] == "Ada Quill"
    # Narrower still: the initialed form is cut at the end.
    _scale, out = shown(short * t.NAME_FLOOR * 0.7)
    assert out[0][0].startswith("E. Feather") and out[0][0].endswith("…")


@pytest.mark.parametrize("layout", ["pre_race", "finish", "elimination"])
def test_longest_name_on_the_board_in_names_only_mode(qtbot, drawn, layout):
    from madtracker.board import sample

    if layout == "pre_race":
        data = sample.pre_race()
        data.roster[2].names = [LONGEST]
    elif layout == "finish":
        data = sample.finish()
        data.placings[0].entry.names = [LONGEST]
        data.placings[4].entry.names = [LONGEST]
    else:
        data = sample.elimination()
        data.remaining[1].names = [LONGEST]
        data.last_eliminated.names = [LONGEST]
    render(qtbot, layout, data, bibs=False)
    seen = strings(drawn)
    if layout != "elimination":
        # A start list row and a result row have the room: whole.
        assert seen.count(LONGEST) == (2 if layout == "finish" else 1)
        return
    # The last-out card: first name over last name, both whole.
    assert "Evangelina" in seen and "Featherstonehaugh" in seen
    # More than six still racing open as rows: the last name is whole, the
    # first given way to its initial, never a cut last name.
    assert len(data.remaining) > 6 and "E. Featherstonehaugh" in seen


@pytest.mark.parametrize(
    ("number", "of", "title"),
    [(2, 3, "Sprint 2 of 3"), (3, 3, "Final sprint"), (4, None, "Sprint 4")],
)
def test_sprint_card_title_counts_like_the_header(qtbot, drawn, number, of, title):
    data = points(riders=4, sprints=3, done=2)
    data.sprint_result = P.SprintResult(
        number=number, of=of, placings=[(1, data.rows[0].entry, 10)]
    )
    render(qtbot, "sprint_points", data)
    assert title in strings(drawn)
    assert not any("result" in s for s in strings(drawn))


@pytest.mark.parametrize("teams", [True, False], ids=["teams", "riders"])
def test_sprint_card_sets_its_points_one_gap_after_the_entry_and_keeps_to_its_content(
    qtbot, drawn, monkeypatch, teams
):
    """The points sit beside the block or the rider, one right-aligned
    column, and the card is no wider than what it shows: a "+5" at the
    far end of a wide card is read with the wrong team."""
    from madtracker.board import pages, theme

    blocks: list[object] = []
    block = theme.team_block

    def record(p, rect, *args, **kwargs):
        blocks.append(rect)
        return block(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "team_block", record)
    data = madison(teams=5) if teams else points(riders=5, sprints=3, done=2)
    if teams:
        data.rows[1].entry.team = "Stars and Stripes"
    data.sprint_result = P.SprintResult(
        number=2,
        of=3,
        placings=[
            (i + 1, r.entry, v)
            for i, (r, v) in enumerate(zip(data.rows[:4], [10, 3, 2, 1], strict=True))
        ],
    )
    layout = "madison" if teams else "sprint_points"
    w = render(qtbot, layout, data)
    page = w.pages[layout]
    u = page.u * page.card_scale
    figs = [r for s, r, *_ in drawn if s in ("+10", "+3", "+2", "+1")]
    assert len(figs) == 4
    # One column, right edges together.
    assert len({round(r.right(), 2) for r in figs}) == 1
    if teams:
        card_blocks = blocks[-4:]
        assert len({round(r.width(), 2) for r in card_blocks}) == 1
        for b, fig in zip(card_blocks, figs, strict=True):
            assert fig.x() - b.right() == pytest.approx(pages.SPRINT_GAP * u)
        # The block holds the widest name whole.
        assert "Stars and Stripes" in strings(drawn)
    else:
        # Every rider's last name is whole beside its plate.
        for r in data.rows[:4]:
            assert any(_last(r.entry.names[0]) in s for s in strings(drawn))
    # The card ends where its content does: the title's rect spans the
    # card less its margins, and its right edge is the points'.
    title = next(r for s, r, *_ in drawn if s == "Sprint 2 of 3")
    assert title.right() == pytest.approx(figs[0].right())
    assert title.width() < pages.SPRINT_CARD_MOST * u


@pytest.mark.parametrize(("places", "at_cap"), [(4, True), (8, False)])
def test_the_sprint_card_is_as_large_as_fits_the_page(qtbot, drawn, places, at_cap):
    """A four-place card takes the cap; a longer table takes a smaller unit
    so every place stays on the page."""
    from madtracker.board import pages

    data = points(riders=10, sprints=3, done=2)
    table = [10, 7, 5, 3, 2, 1, 1, 1][:places]
    data.sprint_result = P.SprintResult(
        number=2,
        of=3,
        placings=[
            (i + 1, r.entry, v)
            for i, (r, v) in enumerate(zip(data.rows[:places], table, strict=True))
        ],
    )
    w = render(qtbot, "sprint_points", data)
    page = w.pages["sprint_points"]
    assert (page.card_scale == pages.SPRINT_CARD_SCALE) is at_cap
    figs = [r for s, r, *_ in drawn if s.startswith("+")]
    assert len(figs) == places
    assert all(0 <= r.top() and r.bottom() <= w.height() for r in figs)


def test_a_penalty_on_a_status_row_opens_no_column_and_a_negative_total_shares_the_minus(
    qtbot, drawn
):
    """The TV's feed drops status rows and the operator's preview keeps
    them, so a penalty on a DNF rider must open the
    column on neither; a total a penalty pushed below zero is written with
    the penalty's minus, not a hyphen."""
    data = points(riders=6)
    data.rows[4].penalty = -5
    data.rows[4].status = "DNF"
    render(qtbot, "sprint_points", data)
    seen = strings(drawn)
    assert "PENALTY" not in seen and "−5" not in seen
    drawn.clear()
    data = points(riders=6)
    data.rows[1].penalty = -5
    data.rows[1].total = -4
    render(qtbot, "sprint_points", data)
    seen = strings(drawn)
    assert "−5" in seen and "−4" in seen and "-4" not in seen


def test_a_penalty_opens_its_column_between_laps_and_total(qtbot, drawn):
    """A points ruling (USAC 8D5(b)) is rare: the column exists only while
    a row on the board carries one, so the names keep the room."""
    from madtracker.board import theme

    render(qtbot, "sprint_points", points(riders=10))
    seen = strings(drawn)
    assert "PENALTY" not in seen and not [s for s in seen if s.startswith("−")]
    drawn.clear()
    data = points(riders=10)
    data.rows[2].penalty = -5
    data.rows[2].total = 995
    render(qtbot, "sprint_points", data)
    seen = strings(drawn)
    assert "PENALTY" in seen and "−5" in seen and "995" in seen
    at = {s: r for s, r, *_ in drawn if s in ("LAPS", "PENALTY", "TOTAL", "−5")}
    # The heading spills over the gutters as SPRINT PTS does; the figure sits
    # in its own column, after the laps and before the total.
    assert at["LAPS"].center().x() < at["PENALTY"].center().x() < at["TOTAL"].center().x()
    assert at["LAPS"].right() <= at["−5"].x() and at["−5"].right() <= at["TOTAL"].x()
    color = next(c for s, _r, _px, c in drawn if s == "−5")
    assert color == theme.LOSS.name()
    # Every rider's last name is still whole beside the extra column.
    for row in data.rows:
        assert any(_last(row.entry.names[0]) in s for s in seen), row.entry.names[0]


# The team page --------------------------------------------------------------


@pytest.mark.parametrize(
    ("color", "dark_ink"),
    [
        ("#f4f4f4", True),  # White
        ("#ffe419", True),  # Yellow
        ("#ff8a1f", True),  # Orange
        ("#16181c", False),  # Black
        ("#7a4a24", False),  # Brown
    ],
)
def test_a_team_block_sets_its_name_in_the_ink_its_color_needs(qapp, color, dark_ink):
    """Dark ink on a light color, white on a dark one, at WCAG's 4.5:1."""
    from PySide6.QtGui import QColor

    from madtracker.board import theme as t

    ink = t.team_ink(QColor(color))
    assert ink.name() == (t.PLATE_TEXT if dark_ink else t.TEXT).name()
    assert t.contrast(QColor(color), ink) >= t.ACCENT_CONTRAST


def test_a_mid_tone_team_takes_white_ink_at_large_types_contrast(qapp):
    """Blue reaches 4.5:1 with neither ink; it gets white, as a jersey's
    lettering reads, at WCAG's 3:1 for large type."""
    from PySide6.QtGui import QColor

    from madtracker.board import theme as t

    blue = QColor("#2f6bff")
    assert max(t.contrast(blue, c) for c in (t.TEXT, t.PLATE_TEXT)) < t.ACCENT_CONTRAST
    assert t.team_ink(blue).name() == t.TEXT.name()
    assert t.contrast(blue, t.team_ink(blue)) >= t.LARGE_CONTRAST


def test_a_black_team_block_keeps_the_light_ring(qapp):
    """Black on the near-black board would vanish without the swatch's ring;
    a light color needs none."""
    from PySide6.QtCore import QRectF

    from madtracker.board import theme as t

    def edge_and_middle(color: str) -> tuple[int, int]:
        img = _painted(
            lambda p: t.team_block(p, QRectF(20, 20, 300, 100), color, "", t.font(40, t.BOLD))
        )
        return img.pixelColor(21, 70).lightness(), img.pixelColor(170, 70).lightness()

    edge, middle = edge_and_middle("#16181c")
    assert edge > middle + 40
    edge, middle = edge_and_middle("#ffe419")
    assert edge <= middle


def test_the_team_page_shows_place_team_laps_and_total_and_no_riders_or_sprint_pts(
    qtbot, drawn, monkeypatch
):
    """Riders read the board at speed for team, place and points, and
    want less: no riders' names while the race runs, and the bar is the
    row from the place to the page's edge, carrying the figures. The
    Points Race page keeps SPRINT PTS (its test is above)."""
    from PySide6.QtGui import QColor

    from madtracker.board import pages, theme

    blocks: list[object] = []
    block = theme.team_block

    def record(p, rect, *args, **kwargs):
        blocks.append(rect)
        return block(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "team_block", record)
    data = madison(teams=5)
    for i, row in enumerate(data.rows):
        row.sprints = [7] * 4 + [None] * 2
        row.total = 50 - i
    data.rows[1].laps = 1
    w = render(qtbot, "madison", data)
    seen = strings(drawn)
    assert "TEAM" in seen and "LAPS" in seen and "TOTAL" in seen and "+1" in seen
    assert "SPRINT PTS" not in seen
    assert "28" not in seen, "no sprint points figure: the total is what they race on"
    # No rider's name anywhere on the page.
    assert not any("  /  " in s for s in seen)
    assert not any(_last(name) in s for r in data.rows for name in r.entry.names for s in seen)
    # The team name on its block, in the block's ink: Team 1 is white.
    assert next(c for s, _r, _px, c in drawn if s == "Team 1") == theme.PLATE_TEXT.name()
    # The place and the total share the row's largest type, and the team
    # name on the block is set as large as the block holds.
    place = {px for s, _r, px, _c in drawn if s in {str(r.rank) for r in data.rows}}
    total = {px for s, _r, px, _c in drawn if s in {str(r.total) for r in data.rows}}
    assert place == total and len(place) == 1
    big = place.pop()
    rh = next(r for s, r, *_ in drawn if s == "1").height()
    assert big == round(pages.TEAM_FIGURE_SHARE * rh)
    assert {px for s, _r, px, _c in drawn if s == "Team 1"} == {round(pages.TEAM_NAME_SHARE * rh)}
    # One bar width for the list, the row from the place to the page's
    # edge, with the lap figure inside its right end in the bar's ink: a
    # green "+1" on a green bar would vanish.
    widths = {round(r.width()) for r in blocks}
    assert len(widths) == 1 and widths.pop() > w.pages["madison"].width() * 0.8
    assert blocks[0].right() == pytest.approx(w.pages["madison"].margin_rect().right())
    lap = next(r for s, r, _px, _c in drawn if s == "+1")
    assert blocks[1].center().x() < lap.x() and lap.right() < blocks[1].right()
    ink = theme.team_ink(QColor(data.rows[1].entry.color)).name()
    assert next(c for s, _r, _px, c in drawn if s == "+1") == ink


def test_the_team_bar_carries_laps_penalty_and_total_under_their_headings(
    qtbot, drawn, monkeypatch
):
    """The figures sit inside the bar's right end, LAPS, then PENALTY
    while one stands, then TOTAL, each heading over its figures with the
    right edges together, as every figure column on the board is."""
    from PySide6.QtGui import QColor

    from madtracker.board import theme

    blocks: list[object] = []
    block = theme.team_block

    def record(p, rect, *args, **kwargs):
        blocks.append(rect)
        return block(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "team_block", record)
    data = madison(teams=6)
    for i, row in enumerate(data.rows):
        row.total = 40 - 3 * i
    data.rows[1].laps = 1
    data.rows[2].penalty = -20
    w = render(qtbot, "madison", data)
    at = {s: r for s, r, *_ in drawn if s in ("LAPS", "PENALTY", "TOTAL", "+1", "−20", "40", "34")}
    # Headings are drawn right-aligned in wide rects; the words themselves
    # stand clear of each other, in order.
    lab = theme.label(w.pages["madison"].u)
    left = {s: at[s].right() - theme.text_width(s, lab) for s in ("PENALTY", "TOTAL")}
    assert at["LAPS"].right() < left["PENALTY"] and at["PENALTY"].right() < left["TOTAL"]
    # Text rects are drawn right-aligned, so each figure's right edge is
    # its heading's.
    assert at["+1"].right() == pytest.approx(at["LAPS"].right())
    assert at["−20"].right() == pytest.approx(at["PENALTY"].right())
    assert at["40"].right() == pytest.approx(at["TOTAL"].right())
    # Every figure ends inside its row's bar, the total short of the bar's end.
    for s, bar in (("40", blocks[0]), ("+1", blocks[1]), ("−20", blocks[2]), ("34", blocks[2])):
        assert bar.x() < at[s].x() and at[s].right() < bar.right(), s
        assert bar.top() <= at[s].center().y() <= bar.bottom(), s
    # No riders' names beside the figures, and the penalty in the bar's ink.
    ink = theme.team_ink(QColor(data.rows[2].entry.color)).name()
    assert next(c for s, _r, _px, c in drawn if s == "−20") == ink


@pytest.mark.parametrize("teams", [1, 2, 3, 5, 8])
def test_team_rows_share_the_page_and_their_type_grows_with_them(qtbot, drawn, teams):
    """A small field reads from the track as large as the page allows: the
    rows share its height whatever the count, a lone team half of it, and
    the place, total, and team name are shares of the row."""
    from madtracker.board import pages

    data = madison(teams=teams)
    # Short names, so the figures have no reason to give way to them.
    for i, row in enumerate(data.rows):
        row.entry.team = f"T{i + 1}"
    data.rows[0].laps = 1
    w = render(qtbot, "madison", data)
    page = w.pages["madison"]
    ranks = {str(r.rank) for r in data.rows}
    rects = sorted((r for s, r, *_ in drawn if s in ranks), key=lambda r: r.y())
    assert len(rects) == teams
    assert len({round(r.height(), 3) for r in rects}) == 1
    rh = rects[0].height()
    room = page.margin_rect().bottom() - rects[0].y()
    assert rh == pytest.approx(room / max(teams, pages.TEAM_FILL_LEAST), abs=1)
    big = {px for s, _r, px, _c in drawn if s in ranks}
    assert big == {round(rh * pages.TEAM_FIGURE_SHARE)}
    # LAPS grows with the row and stays under the total.
    lap = next(px for s, _r, px, _c in drawn if s == "+1")
    assert lap >= round(rh * pages.TEAM_LAPS_SHARE) - 1
    assert lap < big.pop()
    assert pages.TEAM_PAGE_ROWS == 8


def test_a_decided_field_of_two_keeps_its_ordinals_to_a_share_of_the_page(qtbot, drawn):
    """ "2nd" at a two-team row's height would take a quarter of the page and
    squeeze the team names, so the place gives way before the total."""
    from madtracker.board import pages

    data = madison(teams=2)
    data.header = P.Header("Madison", status="Final")
    for i, row in enumerate(data.rows):
        row.total = 30 - 10 * i
    w = render(qtbot, "madison", data)
    page = w.pages["madison"]
    place = {px for s, _r, px, _c in drawn if s in {"1st", "2nd"}}
    total = {px for s, _r, px, _c in drawn if s in {"30", "20"}}
    assert len(place) == 1 and len(total) == 1
    assert place.pop() < total.pop()
    from madtracker.board import theme

    widest = max(
        theme.text_width(s, theme.font(px, theme.HEAVY, tabular=True))
        for s, _r, px, _c in drawn
        if s in {"1st", "2nd"}
    )
    assert widest <= page.margin_rect().width() * pages.TEAM_PLACE_SHARE


@pytest.mark.parametrize("size", [(1920, 1080), (1440, 1080), (1024, 768)])
@pytest.mark.parametrize("status", ["Racing", "Final"])
def test_a_small_madisons_figures_give_way_to_its_team_names(
    qtbot, drawn, monkeypatch, size, status
):
    """Two teams with long names, laps, and a penalty: the figures shrink
    before a name does, so a name is under TEAM_NAME_LEAST only once the
    figures are at TEAM_FIGURE_LEAST, every name is drawn whole, and
    nothing runs out of the bar into the place column, on a 16:9 board or
    a 4:3 one."""
    from madtracker.board import pages, theme

    blocks: list[object] = []
    block = theme.team_block

    def record(p, rect, *args, **kwargs):
        blocks.append(rect)
        return block(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "team_block", record)
    data = madison(teams=2)
    data.header = P.Header("Madison", status=status)
    long_names = ["Stars and Stripes Racing", "Motor City Velo Club"]
    for row, name, laps, pen, total in zip(
        data.rows, long_names, [1, -1], [0, -20], [45, -8], strict=True
    ):
        row.entry.team, row.laps, row.penalty, row.total = name, laps, pen, total
    w = render(qtbot, "madison", data, size=size)
    u = w.pages["madison"].u
    total_px = next(px for s, _r, px, _c in drawn if s == "45")
    for name in long_names:
        rect, px = next((r, px) for s, r, px, _c in drawn if s == name)
        if px < round(pages.TEAM_NAME_LEAST * u) - 1:
            assert total_px == round(pages.TEAM_FIGURE_LEAST * u)
        assert theme.text_width(name, theme.font(px, theme.BOLD)) <= rect.width() + 0.5
    bar_x = blocks[0].x()
    for s in ("+1", "−1", "−20", "LAPS", "PENALTY"):
        # Right-aligned in its box, so the text starts where its width ends.
        r, px = next((r, px) for t, r, px, _c in drawn if t == s)
        bold = theme.font(px, theme.BOLD, tabular=True)
        start = r.right() - theme.text_width(s, bold)
        assert start >= bar_x - 0.5, s
    places = {"1st", "2nd"} if status == "Final" else {"1", "2"}
    for r in (r for t, r, *_ in drawn if t in places):
        assert r.right() <= bar_x + 0.5


@pytest.mark.parametrize("size", [(1920, 1080), (1366, 768)])
def test_a_small_madisons_totals_hold_still_through_its_first_lap_and_penalty(qtbot, size):
    """The page's size is decided as though a lap and a penalty stood, so
    the first lap gained or penalty given never steps the totals down
    while the riders are reading them."""
    from madtracker.board import theme

    def total_px(laps, penalty):
        seen = []
        text = theme.text

        def record(p, rect, s, f, *args, **kwargs):
            seen.append((s, f.pixelSize()))
            return text(p, rect, s, f, *args, **kwargs)

        data = madison(teams=2)
        for row, name, total in zip(
            data.rows, ["Stars and Stripes Racing", "Motor City Velo Club"], [30, 29], strict=True
        ):
            row.entry.team, row.total = name, total
        data.rows[0].laps, data.rows[1].penalty = laps, penalty
        theme.text = record
        try:
            render(qtbot, "madison", data, size=size)
        finally:
            theme.text = text
        return next(px for s, px in seen if s == "30")

    start = total_px(0, 0)
    assert total_px(1, 0) == start
    assert total_px(1, -5) == start


@pytest.mark.parametrize("size", [(1440, 1080), (1280, 1024), (1024, 768)])
def test_a_small_madisons_figures_stay_inside_the_bar_whatever_the_names(
    qtbot, drawn, monkeypatch, size
):
    """The figures step down until they start inside the bar on a narrow
    board, even when the names ask for no room (a bare color block)."""
    from madtracker.board import theme

    blocks: list[object] = []
    block = theme.team_block

    def record(p, rect, *args, **kwargs):
        blocks.append(rect)
        return block(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "team_block", record)
    data = madison(teams=2)
    for row in data.rows:
        row.entry.team = ""
    data.rows[0].laps, data.rows[1].laps, data.rows[1].penalty = 1, -1, -20
    render(qtbot, "madison", data, size=size)
    bar_x = blocks[0].x()
    for s in ("+1", "−1", "−20", "LAPS", "PENALTY"):
        # Right-aligned in its box, so the text starts where its width ends.
        r, px = next((r, px) for t, r, px, _c in drawn if t == s)
        bold = theme.font(px, theme.BOLD, tabular=True)
        start = r.right() - theme.text_width(s, bold)
        assert start >= bar_x - 0.5, s


def test_a_small_madisons_plate_keeps_to_its_figures(qtbot, drawn, monkeypatch):
    """When the figures give way, the total's plate shrinks with them
    rather than standing the bar's full height behind a smaller figure."""
    from madtracker.board import theme

    plates: list[object] = []
    plate = theme.figure_plate

    def record(p, rect, *args, **kwargs):
        plates.append(rect)
        return plate(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "figure_plate", record)
    data = madison(teams=2)
    for row, name in zip(
        data.rows, ["Stars and Stripes Racing", "Motor City Velo Club"], strict=True
    ):
        row.entry.team, row.laps, row.penalty = name, 1, -5
    render(qtbot, "madison", data, size=(1440, 1080))
    total = next((r, px) for s, r, px, _c in drawn if s == str(data.rows[0].total))
    assert plates and plates[0].height() < total[1] * 1.3


@pytest.mark.parametrize("penalty", [0, -20])
def test_a_small_rider_fields_names_and_totals_grow_together(qtbot, drawn, penalty):
    """A long name stops the growth at the size where it fits whole at the
    table's own name size: the names are never shrunk while the figures
    grow, so they keep the base table's proportion to the totals."""
    data = points(riders=5, sprints=3, done=1)
    for i, row in enumerate(data.rows):
        row.entry.names = [SHORT[i % len(SHORT)]]
    data.rows[2].entry.names = ["Maximiliana Vanderbilt-Rochester"]
    data.rows[3].penalty = penalty
    render(qtbot, "sprint_points", data)
    totals = {px for s, _r, px, _c in drawn if s in {str(row.total) for row in data.rows}}
    names = {px for s, _r, px, _c in drawn if s in {row.entry.names[0] for row in data.rows}}
    assert len(totals) == 1 and len(names) == 1
    total_px, name_px = totals.pop(), names.pop()
    assert name_px >= round(total_px * 46 / 60) - 1
    seen = strings(drawn)
    assert all(row.entry.names[0] in seen for row in data.rows)


@pytest.mark.parametrize("riders", [3, 4, 5, 6, 8])
def test_a_small_rider_field_grows_its_rows_type_and_columns_as_one(qtbot, drawn, riders):
    """Fewer riders than nine take taller rows, up to the room a field of
    RIDER_FILL_LEAST shares, and the type and columns grow with them by
    one factor, so the figures stay in their columns."""
    from madtracker.board import pages

    data = points(riders=riders, sprints=3, done=1)
    for i, row in enumerate(data.rows):
        row.entry.names = [SHORT[i % len(SHORT)]]
    w = render(qtbot, "sprint_points", data)
    page = w.pages["sprint_points"]
    u = page.u
    totals = [(r, px) for s, r, px, _c in drawn if s in {str(row.total) for row in data.rows}]
    assert len(totals) == riders
    rh = totals[0][0].height()
    # The growth, read off the TOTAL column, which is 170 at the base.
    total_head = next(r for s, r, *_ in drawn if s == "TOTAL")
    g = (total_head.width() + 20 * u) / 170
    assert g > u
    room = page.margin_rect().bottom() - totals[0][0].y()
    fill = room / max(riders, pages.RIDER_FILL_LEAST)
    assert rh <= fill + 1
    assert rh == pytest.approx(min(fill, pages.RIDER_ROW_FULL * g), abs=1)
    assert {px for _r, px in totals} == {round(min(60 * g, rh * 0.84))}
    seen = strings(drawn)
    assert all(row.entry.names[0] in seen for row in data.rows)


@pytest.mark.parametrize("riders", [3, 5, 8])
def test_a_small_field_of_long_names_grows_only_while_every_name_fits_whole(qtbot, drawn, riders):
    """The larger figures take the names' room, so the growth stops where
    a name would give up its first name, and never goes under the base."""
    data = points(riders=riders, sprints=3, done=1)
    w = render(qtbot, "sprint_points", data)
    u = w.pages["sprint_points"].u
    seen = strings(drawn)
    assert all(row.entry.names[0] in seen for row in data.rows)
    totals = {px for s, _r, px, _c in drawn if s in {str(row.total) for row in data.rows}}
    assert len(totals) == 1 and totals.pop() >= round(60 * u)


@pytest.mark.parametrize("riders", [9, 10, 16])
def test_nine_riders_or_more_set_the_rider_table_at_its_base_sizes(qtbot, drawn, riders):
    """A full field is the board's design case: its rows share the page at
    RIDER_ROW_FULL or less, and its type and columns are the base sizes."""
    from madtracker.board import pages

    data = points(riders=riders, sprints=3, done=1)
    w = render(qtbot, "sprint_points", data)
    u = w.pages["sprint_points"].u
    rh = next(r for s, r, *_ in drawn if s == str(data.rows[0].total)).height()
    assert rh <= pages.RIDER_ROW_FULL * u + 0.01
    total_head = next(r for s, r, *_ in drawn if s == "TOTAL")
    assert total_head.width() == pytest.approx(150 * u, abs=1)


# The team block's priority --------------------------------------------------

LONG_TEAMS = [
    "Stars and Stripes Racing",
    "Motor City Velo Club",
    "Detroit Rock City Cycling",
    "Wolverine Sports Club",
    "Belle Isle Track Team",
    "Corktown Cyclery Racing",
    "Eastern Market Bike Co",
    "Hamtramck Velo Collective",
]
# Two long hyphenated names a team, a pair that would cut on one line.
HYPHENATED = [
    "Maximiliana Vanderbilt-Rochester",
    "Bartholomew Montgomery-Blackwood",
    "Wilhelmina Oyelaran-Smith",
    "Anastasia Papadopoulou-Smith",
]


def _long_teams(n: int = 8) -> list[P.Entry]:
    return [
        P.Entry(
            bibs=[str(i + 1), str(i + 41)],
            names=[HYPHENATED[i % 4], HYPHENATED[(i + 1) % 4]],
            team=LONG_TEAMS[i % len(LONG_TEAMS)],
            color=COLORS[i % len(COLORS)],
        )
        for i in range(n)
    ]


@pytest.fixture
def painted(monkeypatch):
    """Every string as the painter draws it, after any elision.

    ``drawn`` records what a page asks ``theme.text`` for, before the
    cut; a cut team name shows only here.
    """
    from PySide6.QtGui import QPainter

    seen: list[str] = []
    draw = QPainter.drawText

    def record(self, *args):
        if len(args) == 3 and isinstance(args[2], str):
            seen.append(args[2])
        return draw(self, *args)

    monkeypatch.setattr(QPainter, "drawText", record)
    return seen


def _cut(painted) -> list[str]:
    return [s for s in painted if s.endswith("…")]


def test_up_next_long_teams_show_as_whole_blocks(qtbot, drawn, painted):
    """Eight long team names whose riders are dropped take a block measured
    without the riders, so no name is cut ("Stars a...")."""
    # A Last result beside it, so Up next has the narrower half.
    data = P.Between(
        header=HEADER,
        next_title="8 Mile Madison",
        next_roster=_long_teams(),
        last_title="Elite Points Race",
        last_placings=finish(6).placings,
    )
    render(qtbot, "between", data)
    seen = strings(drawn)
    assert set(LONG_TEAMS) <= set(seen)
    assert not _cut(painted)


def test_last_result_long_teams_show_as_whole_blocks(qtbot, drawn, painted):
    """The Last result side drops the riders too, never "Stars and..."
    beside "M. Vanderbilt-Ro..."."""
    data = P.Between(
        header=HEADER,
        next_title="Elite Points Race",
        last_title="8 Mile Madison",
        last_placings=[P.Placing(i + 1, e) for i, e in enumerate(_long_teams())],
    )
    render(qtbot, "between", data)
    assert set(LONG_TEAMS) <= set(strings(drawn))
    assert not _cut(painted)


@pytest.mark.parametrize("laps", [False, True], ids=["plain", "laps"])
def test_a_start_list_of_eight_long_teams_keeps_every_team_name_whole(qtbot, drawn, painted, laps):
    """Held at TEAM_SHARE of a half-width column, the block would cut every
    team name at the floor; a team name has no initial to give up, so
    the riders give way first and never a team name."""
    from madtracker.board import theme

    roster = _long_teams()
    lap_list = [1, 0, 0, -1, 0, 0, 0, 2] if laps else []
    render(qtbot, "pre_race", P.PreRace(header=HEADER, roster=roster, laps=lap_list))
    seen = strings(drawn)
    assert set(LONG_TEAMS) <= set(seen)
    assert not _cut(painted)
    sizes = {px for s, _r, px, _c in drawn if s in LONG_TEAMS}
    assert min(sizes) >= theme.MIN_PX


def test_team_standings_keep_one_block_width_when_the_page_turns(qtbot, monkeypatch):
    """Nine teams turn pages of five and four; the block is measured over
    every row, so the riders never move as the page turns."""
    from madtracker.board import theme

    widths: list[float] = []
    block = theme.team_block

    def record(p, rect, *args, **kwargs):
        widths.append(round(rect.width(), 2))
        return block(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "team_block", record)
    data = madison(teams=9)
    # The widest team name on the second page only.
    data.rows[7].entry.team = "Orange and Yellow"
    w = render(qtbot, "madison", data)
    page = w.pages["madison"]
    assert page.page_count() == 2
    first = set(widths)
    widths.clear()
    page.advance()
    w.grab()
    assert set(widths) == first and len(first) == 1


@pytest.mark.parametrize("layout", ["madison", "finish"])
def test_a_long_hyphenated_pair_is_stacked_or_given_room_never_cut(qtbot, drawn, painted, layout):
    """Two long hyphenated names on one line at the floor are never cut
    ("B. Montgomery-Bla...") while the block beside them has air."""
    entries = _long_teams()
    if layout == "madison":
        data = madison(teams=8)
        for row, e in zip(data.rows, entries, strict=True):
            row.entry = e
    else:
        laps = [2, 1, -1, 0, 0, 0, 0, 0]
        data = P.Finish(
            header=HEADER,
            placings=[P.Placing(i + 1, e, laps=laps[i]) for i, e in enumerate(entries)],
        )
    render(qtbot, layout, data)
    assert not _cut(painted)
    seen = strings(drawn)
    # The team page shows no riders while the race runs; the podium shows
    # its three pairs whole.
    shown = [] if layout == "madison" else entries[:3]
    for e in shown:
        for name in e.names:
            assert any(_last(name) in s for s in seen), name
    assert set(LONG_TEAMS[: len(entries)]) <= set(seen)


def decided_madison(teams: int, status: str = "Provisional") -> P.Standings:
    """A Madison the officials have decided: the table with the stamp in its header."""
    data = madison(teams=teams)
    laps = [1, 0, 0, 0, -2, 0, 0, 0]
    for i, row in enumerate(data.rows):
        row.laps = laps[i % len(laps)]
        row.total = 70 - 5 * i
        row.penalty = -20 if i == 2 else 0
    data.header = P.Header(title="Test Race", group="Pro", status=status)
    return data


def test_a_decided_team_table_words_its_places_as_ordinals_under_the_stamp(
    qtbot, drawn, monkeypatch
):
    """A Madison's result is the table the stands watched while it ran:
    once the header carries the stamp the places read as ordinals, the
    winner alone in the accent as on the podium page, and each team's
    laps, penalty and total stay inside its bar under the headings, the
    total dark on its plate."""
    from PySide6.QtGui import QColor

    from madtracker.board import theme

    blocks: list[object] = []
    block = theme.team_block

    def record(p, rect, *args, **kwargs):
        blocks.append(rect)
        return block(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "team_block", record)
    data = decided_madison(5)
    render(qtbot, "madison", data)
    seen = strings(drawn)
    color = {s: c for s, _r, _px, c in drawn}
    assert color["1st"] == theme.ACCENT.name()
    assert all(color[s] == theme.TEXT.name() for s in ("2nd", "3rd", "4th", "5th"))
    assert not {"1", "2", "3", "4", "5"} & set(seen), "no bare place numbers once decided"
    assert "PROVISIONAL" in seen
    at = {s: r for s, r, *_ in drawn}
    for heading, fig, row in (("LAPS", "+1", 0), ("PENALTY", "−20", 2), ("TOTAL", "60", 2)):
        assert at[fig].right() == pytest.approx(at[heading].right()), heading
        bar = blocks[row]
        assert bar.x() < at[fig].x() and at[fig].right() < bar.right(), fig
        ink = theme.team_ink(QColor(data.rows[row].entry.color))
        assert color[fig] == (theme.PLATE_TEXT if fig == "60" else ink).name(), fig
    # No riders and no lap chips: the bar carries the laps.
    assert not any(_last(n) in s for r in data.rows for n in r.entry.names for s in seen)
    assert not any("lap" in s for s in seen)


def test_a_running_team_table_keeps_bare_place_numbers(qtbot, drawn):
    """Until the officials decide the race a place is a standing that can
    still change, so it stays a bare number."""
    render(qtbot, "madison", madison(teams=5))
    assert {"1", "2", "3", "4", "5"} <= set(strings(drawn))
    assert not any(re.fullmatch(r"\d+(st|nd|rd|th)", s) for s in strings(drawn))


def test_twelve_decided_teams_turn_the_table_at_six_and_six(qtbot, drawn):
    """The decided table keeps the running page's rows rather than
    shrinking its names, and turns its pages on the same clock."""
    w = render(qtbot, "madison", decided_madison(12))
    assert w.pages["madison"].page_count() == 2
    first = {s for s in strings(drawn) if re.fullmatch(r"\d+(st|nd|rd|th)", s)}
    assert first == {"1st", "2nd", "3rd", "4th", "5th", "6th"}
    drawn.clear()
    w._turn_page()
    w.grab()
    second = {s for s in strings(drawn) if re.fullmatch(r"\d+(st|nd|rd|th)", s)}
    assert second == {"7th", "8th", "9th", "10th", "11th", "12th"}


def test_names_take_proportional_figures_and_columns_tabular(qapp):
    """Inter's tabular set widens the hyphen to a digit's width:
    "Vanderbilt-Rochester" would draw as "Vanderbilt - Rochester"."""
    from PySide6.QtGui import QFont

    from madtracker.board import theme as t

    name = "Vanderbilt-Rochester"
    plain = t.font(100, t.BOLD)
    figures = t.font(100, t.BOLD, tabular=True)
    assert QFont.Tag("tnum") not in plain.featureTags()
    assert QFont.Tag("tnum") in figures.featureTags()
    hyphen = t.text_width("-", plain)
    assert hyphen < t.text_width("-", figures)
    assert t.text_width(name, plain) < t.text_width(name, figures)
    # The column's digits still share one width.
    assert t.text_width("11", figures) == pytest.approx(t.text_width("88", figures))


@pytest.mark.parametrize("status", ["Provisional", "Final"])
def test_the_result_stamp_is_at_the_floor(qtbot, drawn, status):
    """At 56 u the stamp's type would be 31 px, the one thing on the board
    under the floor."""
    from madtracker.board import theme

    header = P.Header(title="Test Race", group="Pro", status=status)
    data = finish(3)
    data.header = header
    w = render(qtbot, "finish", data)
    u = w.pages["finish"].u
    stamp = [px for s, _r, px, _c in drawn if s == status.upper()]
    assert stamp and min(stamp) >= round(theme.MIN_PX * u)


def test_one_long_team_name_does_not_widen_every_block(qtbot, monkeypatch, painted):
    """One 30-character name never makes all five blocks 910 px: the block
    is capped at TEAM_SHARE of the row and the long name shrinks inside its
    own block, whole. On the start list, where
    the riders sit beside the block, the fill then gives the block
    TEAM_FILL of the row and no more."""
    from madtracker.board import pages, theme

    widths: set[float] = set()
    block = theme.team_block

    def record(p, rect, *args, **kwargs):
        widths.add(round(rect.width(), 2))
        return block(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "team_block", record)
    roster = [r.entry for r in madison(teams=5).rows]
    roster[2].team = "The Fast and the Furious Crew!"
    w = render(qtbot, "pre_race", P.PreRace(header=HEADER, roster=roster))
    assert len(widths) == 1
    width = widths.pop()
    page = w.pages["pre_race"]
    assert page.width() * pages.TEAM_SHARE < width <= page.width() * pages.TEAM_FILL
    assert "The Fast and the Furious Crew!" in painted
    assert not _cut(painted)


def test_a_start_list_block_takes_the_spare_room_but_never_a_riders_full_name(
    qtbot, monkeypatch, drawn
):
    """Bars and names are not left small in an empty row: a list with
    room gives the block TEAM_FILL of the row, and
    a list without gives it only what the riders' full names leave."""
    from madtracker.board import pages, theme

    widths: list[float] = []
    block = theme.team_block

    def record(p, rect, *args, **kwargs):
        widths.append(rect.width())
        return block(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "team_block", record)
    short = [P.Entry(bibs=["1", "2"], names=SHORT[:2], team="Blue", color=COLORS[0])]
    w = render(qtbot, "pre_race", P.PreRace(header=HEADER, roster=short))
    page = w.pages["pre_race"]
    assert widths and widths[0] >= page.width() * pages.TEAM_FILL * 0.9
    # A stacked pair that the fill would cut: the block gives up the fill
    # to it, and the pair keeps its full names.
    from PySide6.QtCore import QRectF

    long = P.Entry(bibs=["1", "2"], names=HYPHENATED[:2], team="Blue", color=COLORS[0])
    u = page.u
    row = QRectF(0, 0, 1600 * u, 100 * u)
    page.team_fill = pages.TEAM_FILL
    scale = page.entry_scale([long], row, 64 * u, two_line_names=True)
    width, mode = page.team_w, page.team_mode
    assert mode == "stack" and width < row.width() * pages.TEAM_FILL
    names = theme.font(page.pair_size(64 * u * scale), theme.SEMI)
    widest = max(theme.text_width(n, names) for n in HYPHENATED[:2])
    assert width + pages.TEAM_GAP * u + widest <= row.width() + 0.5


def test_a_madison_status_row_shows_its_status_and_no_figures(qtbot, drawn):
    """A team out on a DNF shows the word alone: no laps and no penalty beside it."""
    data = decided_madison(5, status="")
    data.rows[2].penalty = 0
    out = data.rows[4]
    out.status, out.laps, out.penalty = "DNF", -2, -20
    render(qtbot, "madison", data)
    seen = strings(drawn)
    assert "DNF" in seen and "+1" in seen
    assert "−2" not in seen and "−20" not in seen and "PENALTY" not in seen


def test_a_madison_total_plate_keeps_one_width_from_the_first_lap(qtbot, drawn, monkeypatch):
    """The plates are sized for three figures from the start, so they never widen as
    the totals grow or a status appears, and three figures sit with the same air on
    both sides; a status row has no plate."""
    from madtracker.board import theme

    plates: list[object] = []
    plate = theme.figure_plate

    def record(p, rect, *args, **kwargs):
        plates.append(rect)
        return plate(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "figure_plate", record)
    widths = set()
    for totals, status in (([0] * 5, ""), ([128, 97, 41, 22, 0], "DNF")):
        plates.clear()
        drawn.clear()
        data = madison(5)
        for row, total in zip(data.rows, totals, strict=True):
            row.total = total
        data.rows[-1].status = status
        render(qtbot, "madison", data)
        assert len(plates) == (4 if status else 5)
        widths |= {round(r.width(), 3) for r in plates}
    assert len(widths) == 1
    at = {s: (r, px) for s, r, px, _c in drawn}
    rect, px = at["128"]
    figure_w = theme.text_width("128", theme.font(px, theme.HEAVY, tabular=True))
    left = rect.right() - figure_w - plates[0].left()
    assert left == pytest.approx(plates[0].right() - rect.right(), abs=1)


def test_a_rider_table_status_row_shows_its_status_and_no_figures(qtbot, drawn):
    """The feed leaves a status row off the board; a page given one anyway shows
    the word alone, as the Madison page does: no sprint points and no laps."""
    data = points(riders=12)
    out = data.rows[3]
    out.status, out.laps = "DNF", -2
    render(qtbot, "sprint_points", data)
    seen = strings(drawn)
    assert "DNF" in seen and "17" in seen
    assert "31" not in seen and "−2" not in seen


# The start list and the result fill the page ------------------------------


def _start(names, laps=()):
    return P.PreRace(
        header=HEADER,
        roster=[P.Entry(bibs=[str(i + 1)], names=[n]) for i, n in enumerate(names)],
        laps=list(laps),
    )


def _team_start(n, names=None):
    return P.PreRace(
        header=HEADER,
        roster=[
            P.Entry(
                bibs=[str(i + 1), str(i + 41)],
                names=[SHORT[(2 * i) % 4], SHORT[(2 * i + 1) % 4]],
                team=(names or [f"Team {k + 1}" for k in range(n)])[i],
                color=COLORS[i % len(COLORS)],
            )
            for i in range(n)
        ],
    )


def _name_rows(drawn, names):
    return [(r, px) for s, r, px, _c in drawn if s in set(names)]


@pytest.mark.parametrize("n", [2, 3, 5, 6])
def test_a_small_start_list_shares_the_page_and_its_names_grow(qtbot, drawn, n):
    """A field under the race table's least (RIDER_FILL_LEAST) is set as
    that many rows would be, and its names grow past the base size."""
    from madtracker.board import pages

    names = [f"{SHORT[i % 4]} {chr(65 + i)}" for i in range(n)]
    w = render(qtbot, "pre_race", _start(names))
    page = w.pages["pre_race"]
    rows = _name_rows(drawn, names)
    assert len(rows) == n
    assert min(px for _r, px in rows) > 56 * page.u
    bottom = page.margin_rect().bottom()
    # Every row is the room shared by the least field, no larger.
    tops = sorted({round(r.center().y()) for r, _px in rows})
    pitch = tops[1] - tops[0]
    room = bottom - page.margin_rect().y() - 64 * page.u
    assert pitch <= room / max(n, pages.RIDER_FILL_LEAST) + 1
    assert pitch >= 128 * page.u


@pytest.mark.parametrize("n", [3, 6])
def test_a_small_start_list_of_long_names_keeps_every_name_whole(qtbot, drawn, n):
    """The growth stops where a name would give up its first name or be cut."""
    names = [_name(i) for i in range(n)]
    w = render(qtbot, "pre_race", _start(names))
    rows = _name_rows(drawn, names)
    assert len(rows) == n
    assert {px for _r, px in rows} == {rows[0][1]}
    assert rows[0][1] >= round(56 * w.pages["pre_race"].u)


def test_a_small_start_list_holds_still_when_the_first_lap_is_taken(qtbot, drawn):
    """A placed race keeps its start list up while it runs; the room for a
    lap chip is kept from the start, so the first lap moves nothing."""
    names = [_name(i) for i in range(4)]
    render(qtbot, "pre_race", _start(names))
    before = _name_rows(drawn, names)
    drawn.clear()
    render(qtbot, "pre_race", _start(names, [1, 0, 0, -1]))
    after = _name_rows(drawn, names)
    assert [(r.y(), px) for r, px in before] == [(r.y(), px) for r, px in after]


@pytest.mark.parametrize("n", [16, 24])
def test_a_full_start_list_keeps_its_base_rows(qtbot, drawn, n):
    """Sixteen riders (a full field at 166.66 m) and more fill the page at
    the base pitch; only the names may grow inside their rows."""
    data = _laid_out("pre_race", n)
    w = render(qtbot, "pre_race", data)
    u = w.pages["pre_race"].u
    names = {e.names[0] for e in data.roster} | {
        f"{e.names[0][0]}. {_last(e.names[0])}" for e in data.roster
    }
    tops = sorted({round(r.y()) for s, r, *_ in drawn if s in names})
    assert tops[1] - tops[0] <= 112 * u + 1


def test_seven_riders_take_one_column_when_it_sets_them_larger(qtbot, drawn):
    """Two half-width columns cap seven names of a usual length; one
    column of seven rows sets them larger and fills the page. Seven short
    names read larger still in two."""
    names = [_name(i).split("-")[0] for i in range(7)]
    render(qtbot, "pre_race", _start(names))
    rows = _name_rows(drawn, names)
    assert len({round(r.x()) for r, _px in rows}) == 1
    drawn.clear()
    short = [f"{SHORT[i % 4]} {chr(65 + i)}" for i in range(7)]
    render(qtbot, "pre_race", _start(short))
    assert len({round(r.x()) for r, _px in _name_rows(drawn, short)}) == 2


@pytest.mark.parametrize("n", [2, 3, 4])
@pytest.mark.parametrize("size", [(1920, 1080), (1920, 1200)])
def test_a_small_team_start_list_grows_and_keeps_its_riders_inside_their_rows(
    qtbot, drawn, monkeypatch, n, size
):
    """Two to four teams grow past the base list, and each team's two
    riders stand inside its own row: no line reaches the next team's."""
    from madtracker.board import pages

    bands = []
    entry_line = pages.Page.entry_line

    def record(self, p, rect, *args, **kwargs):
        bands.append(rect)
        return entry_line(self, p, rect, *args, **kwargs)

    monkeypatch.setattr(pages.Page, "entry_line", record)
    data = _team_start(n)
    w = render(qtbot, "pre_race", data, size=size)
    u = w.pages["pre_race"].u
    teams = [(r, px) for s, r, px, _c in drawn if s in {e.team for e in data.roster}]
    assert len(teams) == n
    riders = [(s, r) for s, r, *_ in drawn if s in set(SHORT)]
    assert len(riders) == 2 * n
    # The riders past the base list's 45 px.
    assert min(px for s, _r, px, _c in drawn if s in set(SHORT)) > 45 * u
    from PySide6.QtGui import QFontMetricsF

    from madtracker.board import theme

    px = next(px for s, _r, px, _c in drawn if s in set(SHORT))
    fm = QFontMetricsF(theme.font(px, theme.SEMI))
    assert len(bands) == n
    for k, band in enumerate(bands):
        top, bottom = riders[2 * k][1], riders[2 * k + 1][1]
        # The ink, capitals to descenders, inside the row's band: the
        # entry's rect and the band's padding around it, 8 px at most.
        ink_top = top.y() + fm.ascent() - fm.capHeight()
        ink_bottom = bottom.y() + fm.ascent() + fm.descent()
        assert band.y() - 8 * u <= ink_top and ink_bottom <= band.bottom() + 8 * u


def test_a_start_list_of_one_counts_one_rider(qtbot, drawn):
    render(qtbot, "pre_race", _start(["Ada Quill"]))
    seen = strings(drawn)
    assert "1 RIDER" in seen and "1 RIDERS" not in seen


FINAL = P.Header(title="Test Race", group="Pro", status="Final")


@pytest.mark.parametrize("n", [3, 6, 10])
def test_a_small_result_grows_its_podium_and_rows_as_one(qtbot, drawn, n):
    """Under sixteen places the podium and the places below it grow by one
    factor, so the podium keeps its lead over the rest."""
    data = P.Finish(
        header=FINAL,
        placings=[
            P.Placing(i + 1, P.Entry(bibs=[str(i + 1)], names=[f"{SHORT[i % 4]} {chr(65 + i)}"]))
            for i in range(n)
        ],
    )
    w = render(qtbot, "finish", data)
    page = w.pages["finish"]
    g = page.g
    assert g > 1
    first = next(px for s, _r, px, _c in drawn if s == "1st")
    assert first == round(72 * page.u * g)
    names = [pl.entry.names[0] for pl in data.placings]
    seen = strings(drawn)
    assert all(nm in seen for nm in names)
    if n > 3:
        podium = {px for s, _r, px, _c in drawn if s in names[:3]}
        rest = {px for s, _r, px, _c in drawn if s in names[3:]}
        assert podium == {round(64 * page.u * g)} and rest == {round(38 * page.u * g)}
    bottom = max(r.bottom() for s, r, *_ in drawn if s in names)
    assert bottom <= page.margin_rect().bottom() + 1


def test_a_small_result_of_long_names_grows_only_while_they_fit_whole(qtbot, drawn):
    data = replace(finish(6), header=FINAL)
    w = render(qtbot, "finish", data)
    seen = strings(drawn)
    assert all(pl.entry.names[0] in seen for pl in data.placings)
    assert w.pages["finish"].g >= 1


@pytest.mark.parametrize("n", [16, 24])
def test_a_full_result_keeps_its_base_sizes(qtbot, drawn, n):
    w = render(qtbot, "finish", replace(finish(n), header=FINAL))
    assert w.pages["finish"].g == 1
    first = next(px for s, _r, px, _c in drawn if s == "1st")
    assert first == round(72 * w.pages["finish"].u)


@pytest.mark.parametrize("long", [False, True])
@pytest.mark.parametrize("n", [8, 9, 10, 12, 16])
@pytest.mark.parametrize("size", [(1920, 1080), (1920, 1200), (1000, 900)])
def test_a_grown_start_list_never_sets_its_rows_shorter_than_the_base_list(
    qtbot, drawn, monkeypatch, n, size, long
):
    """Larger names in shorter rows would shrink the plates the stands
    match to the track, so a list's rows keep at least its base pitch."""
    import math

    from madtracker.board import pages

    bands = []
    entry_line = pages.Page.entry_line

    def record(self, p, rect, *args, **kwargs):
        bands.append(rect)
        return entry_line(self, p, rect, *args, **kwargs)

    monkeypatch.setattr(pages.Page, "entry_line", record)
    names = [_name(i) if long else f"{MID[i % len(MID)]} {i}" for i in range(n)]
    w = render(qtbot, "pre_race", _start(names), size=size)
    page = w.pages["pre_race"]
    room = page.margin_rect().height() - 64 * page.u
    tops = sorted({round(b.y(), 3) for b in bands})
    pitch = tops[1] - tops[0]
    # The base list: two columns from seven riders.
    assert pitch >= min(112 * page.u, room / math.ceil(n / 2)) - 1


def test_a_result_still_being_decided_keeps_its_base_sizes(qtbot, drawn):
    """A Win-and-Out shows its places as the bells decide them; grown by
    the places so far, the page would step down with every bell."""
    header = P.Header(title="Test Race", group="Pro", status="3 of 5 places decided")
    w = render(qtbot, "finish", replace(finish(3), header=header))
    assert w.pages["finish"].g == 1
    assert next(px for s, _r, px, _c in drawn if s == "1st") == round(72 * w.pages["finish"].u)


@pytest.mark.parametrize("n", [12, 14, 15])
def test_a_grown_result_never_sets_its_rows_below_the_podium_shorter(qtbot, drawn, n):
    """The podium's growth takes no height from the places below it."""
    from madtracker.board import pages

    data = P.Finish(
        header=FINAL,
        placings=[
            P.Placing(i + 1, P.Entry(bibs=[str(i + 1)], names=[MID[i % 8]])) for i in range(n)
        ],
    )
    w = render(qtbot, "finish", data)
    page = w.pages["finish"]
    rest = sorted({round(r.y(), 3) for s, r, *_ in drawn if s in set(MID) and r.x() < 900})
    rest = [y for y in rest if y > (3 * 136 + 30) * page.u * page.g]
    per_col = -(-(n - 3) // 2)
    below = page.margin_rect().height() - (3 * 136 + 30) * page.u
    assert rest[1] - rest[0] >= min(84 * page.u, below / per_col) - 1
    assert pages.FINISH_FILL_LEAST == 5


def test_an_empty_start_list_paints_its_count_alone(qtbot, drawn):
    render(qtbot, "pre_race", _start([]))
    assert "0 RIDERS" in strings(drawn)


@pytest.mark.parametrize("riders", [2, 5, 8])
@pytest.mark.parametrize("size", [(1920, 1080), (1280, 720)])
def test_a_small_rider_table_holds_still_when_the_first_penalty_is_given(qtbot, size, riders):
    """The names are measured beside a PENALTY column from the start, so
    the column opening never steps the names or the totals down."""
    from madtracker.board import theme

    def sizes(penalty):
        seen = []
        text = theme.text

        def record(p, rect, s, f, *args, **kwargs):
            seen.append((s, f.pixelSize()))
            return text(p, rect, s, f, *args, **kwargs)

        data = points(riders=riders, sprints=4, done=2)
        for i, row in enumerate(data.rows):
            row.entry.names = [MID[i % len(MID)]]
        data.rows[1].penalty = penalty
        theme.text = record
        try:
            render(qtbot, "sprint_points", data, size=size)
        finally:
            theme.text = text
        name = next(px for s, px in seen if s == MID[0])
        total = next(px for s, px in seen if s == str(data.rows[0].total))
        return name, total

    assert sizes(-20) == sizes(0)


@pytest.mark.parametrize("teams", [2, 3, 4])
def test_a_madison_holds_its_names_and_totals_when_it_is_decided(qtbot, teams):
    """The places read as ordinals once decided; the page is sized for
    them from the start, so the result never sets the names smaller."""
    from madtracker.board import theme

    def sizes(status):
        seen = []
        text = theme.text

        def record(p, rect, s, f, *args, **kwargs):
            seen.append((s, f.pixelSize()))
            return text(p, rect, s, f, *args, **kwargs)

        data = madison(teams=teams)
        data.header = P.Header(title="Test Race", group="Pro", status=status)
        for i, row in enumerate(data.rows):
            row.entry.team, row.total = ["Red", "Blue", "Orange", "Yellow"][i], 30 - i
        theme.text = record
        try:
            render(qtbot, "madison", data)
        finally:
            theme.text = text
        return next(px for s, px in seen if s == "Red"), next(px for s, px in seen if s == "30")

    assert sizes("Final") == sizes("Racing")


@pytest.mark.parametrize("size", [(1000, 900), (1200, 1080), (1920, 1200)])
def test_the_sprint_card_stays_on_a_narrow_board(qtbot, monkeypatch, size):
    """A board narrower than 16:9 (a window) sets the card in a smaller
    unit before a card of long names runs off its sides."""
    from PySide6.QtGui import QPainter

    cards = []
    rounded = QPainter.drawRoundedRect

    def record(self, rect, *args, **kwargs):
        cards.append(QRectF(rect))
        return rounded(self, rect, *args, **kwargs)

    monkeypatch.setattr(QPainter, "drawRoundedRect", record)
    data = points(riders=8, sprints=4, done=2)
    data.sprint_result = P.SprintResult(
        2, [(i + 1, data.rows[i].entry, [5, 3, 2][i]) for i in range(3)], 4
    )
    w = render(qtbot, "sprint_points", data, size=size)
    card = max(cards, key=lambda r: r.width())
    assert card.left() >= 0 and card.right() <= w.width()
