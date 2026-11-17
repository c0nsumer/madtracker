"""Full fields on the board: names stay readable, one size per list, sprints fold."""

import re
from dataclasses import replace

import pytest
from PySide6.QtCore import QRectF

from madtracker.board import payloads as P
from ui.board_helpers import render, strings

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


def test_a_race_page_header_holds_the_status_alone_and_not_the_event(qtbot, drawn):
    """The event's name is the logo page's: a race page's header carries the
    race, its group, and the status centered in the bar."""
    import dataclasses

    header = P.Header(title="8 Mile Madison", group="Group A", status="Racing")
    w = render(qtbot, "madison", dataclasses.replace(madison(teams=5), header=header))
    assert "Test Event" not in strings(drawn)
    status = next(r for s, r, *_ in drawn if s == "Racing")
    assert status.center().y() == pytest.approx(w.top_bar.height() / 2, abs=1)


@pytest.mark.parametrize(
    "layout", ["pre_race", "elimination", "sprint_points", "madison", "finish"]
)
def test_no_race_pages_top_bar_draws_the_format(qtbot, drawn, layout):
    """Races are named, so the bar carries no format line under the title:
    the title, its group, and the status, with the title in the middle of
    the bar. An unnamed race's title is its format, and that is all."""
    from madtracker.board import sample
    from madtracker.control import formats

    data = {
        "pre_race": sample.pre_race,
        "elimination": sample.elimination,
        "sprint_points": sample.sprint_points,
        "madison": lambda: madison(teams=5),
        "finish": sample.finish,
    }[layout]()
    w = render(qtbot, layout, data)
    drawn.clear()
    w.top_bar.grab()
    h = data.header
    seen = strings(drawn)
    assert set(seen) <= {h.title, h.group, h.status, h.status.upper()}
    assert not (set(formats.FORMAT_LABELS.values()) - {h.title}) & set(seen)
    title = next(r for s, r, *_ in drawn if s == h.title)
    assert title.center().y() == pytest.approx(w.top_bar.height() / 2, abs=1)


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


def test_elimination_cards_share_one_size_and_initial_first_names(qtbot, drawn):
    data = elimination(remaining=6)
    render(qtbot, "elimination", data)
    seen = strings(drawn)
    card_sizes = {px for s, _r, px, _c in drawn if any(_last(n) in s for n in LONG)}
    # The cards share one size; the last-out card has its own.
    assert len(card_sizes) <= 2
    assert "M. Vanderbilt-Rochester" in seen
    assert not [s for s in seen if s.startswith("Maximiliana") and s.endswith("…")]


# The least a card's plate is, in design units, with two to six riders
# left, on each board shape: a narrow board's cards keep their plates
# beside the bar.
LEAST_CARD_PLATES = {
    (1920, 1080): {2: 170, 3: 170, 4: 170, 5: 115, 6: 115},
    (1280, 720): {2: 170, 3: 170, 4: 170, 5: 115, 6: 115},
    (1440, 1080): {2: 170, 3: 115.9, 4: 170, 5: 115, 6: 115},
    (1024, 768): {2: 170, 3: 115.9, 4: 170, 5: 115, 6: 115},
    (1000, 900): {2: 115.9, 3: 60.7, 4: 115.9, 5: 115, 6: 115},
}


@pytest.mark.parametrize("size", list(LEAST_CARD_PLATES))
def test_card_plates_keep_their_size_and_never_shrink_as_riders_go_out(qtbot, monkeypatch, size):
    """On every board shape the cards' plates hold their least size, and
    from six left to two a plate is never smaller than the one before it,
    so the race's climax never steps the bibs down."""
    from madtracker.board import theme

    plates: list = []
    plate = theme.plate

    def record(p, rect, bib, out=False):
        plates.append((rect.height(), bib, out))
        return plate(p, rect, bib, out)

    monkeypatch.setattr(theme, "plate", record)
    heights = []
    for n in range(6, 1, -1):
        plates.clear()
        w = render(qtbot, "elimination", elimination(remaining=n), size=size)
        u = w.pages["elimination"].u
        still = {round(h / u, 1) for h, bib, out in plates if not out and bib != str(n + 1)}
        assert len(still) == 1, (n, still)
        heights.append(still.pop())
        assert heights[-1] >= LEAST_CARD_PLATES[size][n] - 0.1, (n, heights[-1])
    assert heights == sorted(heights), heights


def _mid_elimination(remaining: int) -> P.Elimination:
    """Riders with names of a usual length, which shrink only when their cards narrow."""
    es = [P.Entry(bibs=[str(i + 1)], names=[MID[i]]) for i in range(remaining + 1)]
    return P.Elimination(header=HEADER, remaining=es[:remaining], last_eliminated=es[remaining])


def _still_racing(drawn, names: list[str]) -> list[tuple[str, QRectF, int]]:
    """The strings a page drew for the riders still in: their names, whole or in part."""
    from madtracker.board import theme

    whole = names + [theme.initialed(n) or n for n in names]
    return [
        (s, r, px)
        for s, r, px, _c in drawn
        if s.rstrip("…") and any(s.rstrip("…") in n for n in whole)
    ]


@pytest.mark.parametrize("bibs", [True, False], ids=["bibs_and_names", "names_only"])
@pytest.mark.parametrize("size", [(1920, 1080), (3840, 2160), (1440, 1080), (1024, 768)])
def test_elimination_names_and_plates_never_shrink_as_riders_go_out(
    qtbot, monkeypatch, drawn, size, bibs
):
    """From six left to the winner the names and the plates of the riders
    still in only ever grow: three left keep four's two columns, two and
    one, rather than three narrower cards across."""
    from madtracker.board import theme

    plates: list = []
    plate = theme.plate

    def record(p, rect, bib, out=False):
        plates.append((rect.height(), bib, out))
        return plate(p, rect, bib, out)

    monkeypatch.setattr(theme, "plate", record)
    names, heights = [], []
    for n in range(6, 0, -1):
        plates.clear()
        drawn.clear()
        render(qtbot, "elimination", _mid_elimination(n), size=size, bibs=bibs)
        still = _still_racing(drawn, MID[:n])
        assert still, n
        names.append(min(px for _s, _r, px in still))
        if bibs:
            heights.append(min(h for h, bib, out in plates if not out and bib != str(n + 1)))
    assert names == sorted(names), names
    assert heights == sorted(heights), heights


@pytest.mark.parametrize("bibs", [True, False], ids=["bibs_and_names", "names_only"])
@pytest.mark.parametrize("size", [(1920, 1080), (3840, 2160), (1440, 1080), (1024, 768)])
def test_three_left_center_the_third_card_under_the_two(qtbot, monkeypatch, size, bibs):
    from madtracker.board import team_rows

    cards: list[QRectF] = []
    band = team_rows.paint_band

    def record(p, card, color, *args, **kwargs):
        if color == team_rows.RIDER_BAR:
            cards.append(QRectF(card))
        return band(p, card, color, *args, **kwargs)

    monkeypatch.setattr(team_rows, "paint_band", record)
    render(qtbot, "elimination", _mid_elimination(3), size=size, bibs=bibs)
    a, b, c = cards
    assert abs(a.y() - b.y()) < 0.5 and c.y() >= a.bottom(), "two over one"
    assert abs(c.center().x() - (a.left() + b.right()) / 2) < 0.5


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


def test_a_team_tables_figures_stand_in_their_columns(qtbot, drawn):
    """The laps, then the penalty while one stands, then the total, each
    column's figures right-aligned to one edge and clear of the next
    column's, with no heading over them. The figures sit on the dark row,
    so the laps and the penalty take the gain and loss colors and the
    total is white."""
    from madtracker.board import theme

    data = madison(teams=6)
    for i, row in enumerate(data.rows):
        row.total = 40 - 3 * i
    data.rows[1].laps = 1
    data.rows[2].penalty = -20
    render(qtbot, "madison", data)
    assert not {"#", "LAPS", "PENALTY", "TOTAL"} & set(strings(drawn))
    at = {s: (r, px) for s, r, px, _c in drawn if s in ("+1L", "−20", "40", "34")}

    def ink_left(s: str, weight) -> float:
        rect, px = at[s]
        return rect.right() - theme.text_width(s, theme.font(px, weight, tabular=True))

    # Text rects are drawn right-aligned, so a rect's right edge is its figure's.
    assert at["+1L"][0].right() < ink_left("−20", theme.BOLD)
    assert at["−20"][0].right() < ink_left("40", theme.HEAVY)
    assert at["40"][0].right() == pytest.approx(at["34"][0].right())
    color = {s: c for s, _r, _px, c in drawn}
    assert color["+1L"] == theme.GAIN.name() and color["−20"] == theme.LOSS.name()
    assert color["40"] == color["34"] == theme.TEXT.name()


@pytest.mark.parametrize("teams", [1, 2, 3, 5, 8])
def test_team_rows_share_the_page_and_their_type_grows_with_them(qtbot, drawn, monkeypatch, teams):
    """A small field reads from the track as large as the page allows: the
    rows share its height whatever the count, a lone team half of it, and
    the place and total are shares of the row, giving way to the surnames
    no further than TEAM_FIGURE_LEAST; the surnames are a share of the row
    too, up to the start list's largest."""
    from madtracker.board import pages, team_rows

    rows: list[QRectF] = []
    band = team_rows.paint_band

    def record(p, row, *args, **kwargs):
        rows.append(QRectF(row))
        return band(p, row, *args, **kwargs)

    monkeypatch.setattr(team_rows, "paint_band", record)
    data = madison(teams=teams)
    data.rows[0].laps = 1
    w = render(qtbot, "madison", data)
    page = w.pages["madison"]
    u = page.u
    assert len(rows) == teams
    assert len({round(r.height(), 3) for r in rows}) == 1
    rh = rows[0].height()
    room = page.margin_rect().bottom() - rows[0].top()
    gap = team_rows.ROW_GAP * u
    assert rh * max(teams, pages.TEAM_FILL_LEAST) + (teams - 1) * gap == pytest.approx(room, abs=1)
    [big] = {px for s, _r, px, _c in drawn if s == "0"}
    share = rh * pages.TEAM_FIGURE_SHARE
    assert min(share, pages.TEAM_FIGURE_LEAST * u) - 1 <= big <= round(share)
    ranks = {str(r.rank) for r in data.rows}
    [place] = {px for s, _r, px, _c in drawn if s in ranks}
    assert place == pytest.approx(big * pages.TEAM_PLACE_SCALE, abs=1)
    # The surnames share one size, no larger than their share of the row
    # or the start list's largest.
    lasts = {_last(n) for r in data.rows for n in r.entry.names}
    [surname] = {px for s, _r, px, _c in drawn if s in lasts}
    most = min(rh * pages.TEAM_SURNAME_SHARE, team_rows.START_SURNAME_MOST * u)
    assert surname <= round(most)
    # LAPS keeps pace with the total, up to TEAM_LAPS_MOST, and stays under it.
    lap = next(px for s, _r, px, _c in drawn if s == "+1L")
    laps_share = big * pages.TEAM_LAPS_SHARE / pages.TEAM_FIGURE_SHARE
    assert lap >= min(laps_share, pages.TEAM_LAPS_MOST * u) - 1
    assert lap <= round(pages.TEAM_LAPS_MOST * u) and lap < big
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


@pytest.mark.parametrize("size", [(1920, 1080), (1366, 768)])
def test_a_small_madisons_totals_hold_still_through_its_first_lap_and_penalty(qtbot, size):
    """The page's size is decided as though a lap and a penalty stood, so
    the first lap gained or penalty given never steps the totals or the
    surnames down while the riders are reading them."""
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
        return next(px for s, px in seen if s == "30"), next(px for s, px in seen if s == "Quill")

    start = total_px(0, 0)
    assert total_px(1, 0) == start
    assert total_px(1, -5) == start


@pytest.mark.parametrize("penalty", [0, -20])
def test_a_small_rider_fields_names_and_totals_grow_together(qtbot, drawn, penalty):
    """A long name stops the growth at the size where it fits whole at the
    table's own name size: the names are never shrunk while the figures
    grow, so they keep the base table's proportion to the totals."""
    from madtracker.board import pages

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
    assert name_px >= round(total_px * 46 / pages.RIDER_TOTAL) - 1
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
    assert {px for _r, px in totals} == {round(min(pages.RIDER_TOTAL * g, rh * 0.84))}
    seen = strings(drawn)
    assert all(row.entry.names[0] in seen for row in data.rows)


@pytest.mark.parametrize("riders", [3, 5, 8])
def test_a_small_field_of_long_names_grows_only_while_every_name_fits_whole(qtbot, drawn, riders):
    """The larger figures take the names' room, so the growth stops where
    a name would give up its first name, and never goes under the base."""
    from madtracker.board import pages

    data = points(riders=riders, sprints=3, done=1)
    w = render(qtbot, "sprint_points", data)
    u = w.pages["sprint_points"].u
    seen = strings(drawn)
    assert all(row.entry.names[0] in seen for row in data.rows)
    totals = {px for s, _r, px, _c in drawn if s in {str(row.total) for row in data.rows}}
    assert len(totals) == 1 and totals.pop() >= round(pages.RIDER_TOTAL * u)


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


def test_team_standings_keep_their_sizes_and_columns_when_the_page_turns(qtbot, drawn):
    """Nine teams turn pages of five and four; the surnames are measured over
    every row, so their size and columns hold as the page turns."""
    data = madison(teams=9)
    # The longest surname on the second page only.
    data.rows[7].entry.names = ["Ada Featherstonehaugh-Rochester", "Bo Lin"]
    w = render(qtbot, "madison", data)
    page = w.pages["madison"]
    assert page.page_count() == 2
    lasts = {_last(n) for r in data.rows for n in r.entry.names}

    def seen():
        px = {px for s, _r, px, _c in drawn if s in lasts}
        return px, sorted({round(r.x(), 2) for s, r, *_ in drawn if s in lasts})

    first = seen()
    drawn.clear()
    page.advance()
    w.grab()
    assert seen() == first and len(first[0]) == 1 and len(first[1]) == 2


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
    if layout == "madison":
        # The team table names every rider by surname, whole; the team
        # names wait for its color view.
        for e in entries:
            for name in e.names:
                assert _last(name) in seen, name
        assert not set(LONG_TEAMS) & set(seen)
        return
    # The podium shows its three pairs whole.
    for e in entries[:3]:
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


def test_a_decided_team_table_words_its_places_as_ordinals_under_the_stamp(qtbot, drawn):
    """A Madison's result is the table the stands watched while it ran:
    once the header carries the stamp the places read as ordinals, the
    winner alone in the accent as on the podium page, and each team's
    laps, penalty and total stay in their columns."""
    from madtracker.board import theme

    data = decided_madison(5)
    render(qtbot, "madison", data)
    seen = strings(drawn)
    color = {s: c for s, _r, _px, c in drawn}
    assert color["1st"] == theme.ACCENT.name()
    assert all(color[s] == theme.TEXT.name() for s in ("2nd", "3rd", "4th", "5th"))
    assert not {"1", "2", "3", "4", "5"} & set(seen), "no bare place numbers once decided"
    assert "PROVISIONAL" in seen
    at = {s: r for s, r, *_ in drawn}
    inks = (("+1L", theme.GAIN), ("−20", theme.LOSS), ("60", theme.TEXT))
    assert at["+1L"].right() < at["−20"].right() < at["60"].right()
    for fig, ink in inks:
        assert color[fig] == ink.name(), fig
    # The riders' surnames still lead, and no lap chips: the laps column carries the laps.
    assert {_last(n) for n in data.rows[0].entry.names} <= set(seen)
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


def _podium_width(page) -> float:
    """The width of a podium entry of teams, inside its row, at the page's growth."""
    from madtracker.board import pages

    big = pages.FINISH_PLANS[0][0]
    return page.podium_rect(page.margin_rect(), 0, big, page.g, teams=True).width()


def test_one_long_team_name_does_not_widen_every_block(qtbot, monkeypatch, painted):
    """One 30-character name never makes all three podium blocks 910 px:
    the block is capped at TEAM_SHARE of the row and the long name shrinks
    inside its own block, whole. On the podium, where the riders sit
    beside the block, the fill then gives the block TEAM_FILL of the row
    and no more."""
    from madtracker.board import pages, theme

    widths: set[float] = set()
    block = theme.team_block

    def record(p, rect, *args, **kwargs):
        widths.add(round(rect.width(), 2))
        return block(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "team_block", record)
    entries = [r.entry for r in madison(teams=3).rows]
    entries[2].team = "The Fast and the Furious Crew!"
    data = P.Finish(header=HEADER, placings=[P.Placing(i + 1, e) for i, e in enumerate(entries)])
    w = render(qtbot, "finish", data)
    assert len(widths) == 1
    width = widths.pop()
    row = _podium_width(w.pages["finish"])
    assert row * pages.TEAM_SHARE < width <= row * pages.TEAM_FILL + 0.5
    assert "The Fast and the Furious Crew!" in painted
    assert not _cut(painted)


def test_a_podium_block_takes_the_spare_room_but_never_a_riders_full_name(
    qtbot, monkeypatch, drawn
):
    """Bars and names are not left small in an empty row: a podium with
    room gives the block TEAM_FILL of the row, and one without gives it
    only what the riders' full names leave."""
    from madtracker.board import pages, theme

    widths: list[float] = []
    block = theme.team_block

    def record(p, rect, *args, **kwargs):
        widths.append(rect.width())
        return block(p, rect, *args, **kwargs)

    monkeypatch.setattr(theme, "team_block", record)
    short = P.Entry(bibs=["1", "2"], names=SHORT[:2], team="Blue", color=COLORS[0])
    w = render(qtbot, "finish", P.Finish(header=HEADER, placings=[P.Placing(1, short)]))
    page = w.pages["finish"]
    assert widths and widths[0] >= _podium_width(page) * pages.TEAM_FILL * 0.9
    # A stacked pair that the fill would cut: the block gives up the fill
    # to it, and the pair keeps its full names.
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
    assert "DNF" in seen and "+1L" in seen
    assert "−2L" not in seen and "−2" not in seen and "−20" not in seen and "PENALTY" not in seen


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
    room = bottom - page.margin_rect().y()
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


@pytest.mark.parametrize("n", [1, 6, 12, 24])
def test_a_rider_start_list_draws_no_count_label(qtbot, drawn, n):
    """The list shows the field, as a Madison's does, so no "12 riders"
    label takes its first row's height."""
    data = _laid_out("pre_race", n)
    w = render(qtbot, "pre_race", data)
    page = w.pages["pre_race"]
    assert not [s for s in strings(drawn) if re.search(r"riders?", s, re.IGNORECASE)]
    names = {e.names[0] for e in data.roster} | {
        f"{e.names[0][0]}. {_last(e.names[0])}" for e in data.roster
    }
    top = min(r.y() for s, r, *_ in drawn if s in names)
    assert top < page.margin_rect().y() + 64 * page.u


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
    room = page.margin_rect().height()
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


def test_an_empty_start_list_paints_no_count(qtbot, drawn):
    render(qtbot, "pre_race", _start([]))
    assert not [s for s in strings(drawn) if "RIDER" in s.upper()]


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
            row.total = 30 - i
        theme.text = record
        try:
            render(qtbot, "madison", data)
        finally:
            theme.text = text
        return next(px for s, px in seen if s == "Quill"), next(px for s, px in seen if s == "30")

    assert sizes("Final") == sizes("Racing")
