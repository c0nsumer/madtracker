"""Rider rows on the board: the Madison row with a neutral bar, the leader's in the accent."""

import copy
from dataclasses import replace

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFontMetricsF

from madtracker.board import payloads as P
from ui.board_helpers import record_looks, render, strings

# Invented riders: thirty distinct names of usual lengths, one surname long.
FIRSTS = ["Arlo", "Bexa", "Corin", "Dalia", "Emrys", "Fenna"]
LASTS = ["Quillan", "Yarrow", "Fallowby", "Vesk", "Oyelaran-Smith"]
# Surnames long enough that a list sets them by its room, not its rows.
LONG_LASTS = ["Vanderbilt-Rochester", "Montgomery-Blackwood", "Featherstonehaugh"]
START = P.Header(title="Points Race", group="Cat 1/2", status="Start list")
RUNNING = P.Header(title="Points Race", group="Cat 1/2", status="After Sprint 2 of 8")


def rider(i: int, long: bool = False) -> P.Entry:
    first, last = FIRSTS[i % 6], LASTS[(i + i // 6) % 5]
    if long:
        first, last = f"{first}ina", LONG_LASTS[(i + i // 6) % 3]
    return P.Entry(bibs=[str(10 + 3 * i)], names=[f"{first} {last}"])


def named(s: str, names) -> bool:
    """Whether ``s`` is one of ``names`` as the board sets it: whole, initialed, or cut."""
    from madtracker.board import theme as t

    for nm in names:
        for form in (nm, t.initialed(nm) or nm):
            if s == form or (s.endswith("…") and form.startswith(s[:-1])):
                return True
    return False


def start_list(n: int, laps: list[int] | None = None, long: bool = False) -> P.PreRace:
    roster = [rider(i, long) for i in range(n)]
    return P.PreRace(header=START, roster=roster, laps=laps or [])


def table(
    n: int, laps: int = 0, penalty: int = 0, header: P.Header = RUNNING, long: bool = False
) -> P.Standings:
    rows = [
        P.StandingRow(
            rank=i + 1,
            entry=rider(i, long),
            sprints=[max(0, 5 - i), None],
            laps=laps if i == 1 else 0,
            penalty=penalty if i == 2 else 0,
            total=60 - 2 * i,
        )
        for i in range(n)
    ]
    return P.Standings(header=header, sprint_count=8, rows=rows, current_sprint=2)


def record_bands(monkeypatch) -> list[dict]:
    """Every row ``team_rows.paint_band`` paints, with what it was given."""
    from madtracker.board import team_rows

    bands: list[dict] = []
    band = team_rows.paint_band

    def record(p, row, color, u, sweep=0.0, zone_right=None, slant=0.0, **kwargs):
        bands.append({"row": QRectF(row), "color": color, "slant": slant, **kwargs})
        return band(p, row, color, u, sweep, zone_right, slant, **kwargs)

    monkeypatch.setattr(team_rows, "paint_band", record)
    return bands


def record_plates(monkeypatch) -> list[QRectF]:
    from madtracker.board import theme as t

    plates: list[QRectF] = []
    plate = t.plate

    def record(p, r, bib, out=False):
        plates.append(QRectF(r))
        return plate(p, r, bib, out)

    monkeypatch.setattr(t, "plate", record)
    return plates


def record_chips(monkeypatch) -> list[tuple[QRectF, object]]:
    """Every chip drawn, with the device it was drawn on."""
    from madtracker.board import theme as t

    chips: list[tuple[QRectF, object]] = []
    chip = t.chip

    def record(p, x, y, h, s, *args, **kwargs):
        chips.append((QRectF(x, y, t.chip_width(h, s), h), p.device()))
        return chip(p, x, y, h, s, *args, **kwargs)

    monkeypatch.setattr(t, "chip", record)
    return chips


def swatch_air(row: QRectF, x: float, top: float, u: float) -> float:
    """The air between the bar's slanted right edge and ``x``, at the height ``top``."""
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    return x - (row.left() + team_rows.SWATCH_W * u + t.SLANT * (row.bottom() - top))


def _close(a: QColor, b: QColor, tol: int) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a.getRgb()[:3], b.getRgb()[:3], strict=True))


PAGES = [("pre_race", start_list(12)), ("sprint_points", table(9))]


@pytest.mark.parametrize(("layout", "data"), PAGES, ids=["start-list", "table"])
def test_rider_rows_take_the_madison_row_shape(qtbot, monkeypatch, layout, data):
    """Each rider row is painted by the Madison's own band: a square left
    end, a rounded right end, and the bar flush left with its right edge
    at the board's slant, SWATCH_W wide at its foot, with the texture."""
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    w = render(qtbot, layout, data)
    page = w.pages[layout]
    u = page.u
    n = len(getattr(data, "roster", None) or data.rows)
    assert len(bands) == n
    assert {b["slant"] for b in bands} == {t.SLANT}
    assert all(b["texture"] is page.texture for b in bands)
    bands.clear()
    img = page.grab().toImage()
    assert len(bands) == n
    bar = QColor(team_rows.RIDER_BAR)
    for b in bands[1:]:
        row = b["row"]
        # The bar's foot and the square top-left corner are the bar.
        foot = img.pixelColor(int(row.left() + team_rows.SWATCH_W * u / 2), int(row.bottom() - 3))
        assert _close(foot, bar, 24), foot.name()
        corner = img.pixelColor(int(row.left() + 1), int(row.top() + 1))
        assert _close(corner, bar, 24), corner.name()
        # Past the bar's slanted edge at its foot, the fade, not the bar.
        past = img.pixelColor(
            int(row.left() + team_rows.SWATCH_W * u + 6 * u), int(row.bottom() - 3)
        )
        assert not _close(past, bar, 24)
        # The rounded right end leaves the page's ground in its corner.
        right = img.pixelColor(int(row.right() - 1), int(row.top() + 1))
        assert _close(right, t.BG, 6), right.name()


def test_rider_bar_is_the_accent_for_first_place_and_neutral_after(qapp):
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    accent = QColor("#3d8bff")
    assert team_rows.RIDER_BAR == t.MUTED.name()
    assert team_rows.rider_bar(1, accent) == accent.name()
    assert team_rows.rider_bar(2, accent) == team_rows.RIDER_BAR
    assert team_rows.rider_bar(12, accent) == team_rows.RIDER_BAR


def test_the_leaders_bar_is_the_accent_and_the_rest_neutral(qtbot, monkeypatch):
    """On the table the bar says rank: the leader's is the accent, as the
    leader's place is, and every other rider's neutral. A start list has
    no leader, so every bar is neutral."""
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    data = table(9)
    data.rows[1].rank = 1
    w = render(qtbot, "sprint_points", data)
    accent = t.ACCENT.name()
    assert [b["color"] for b in bands] == [accent, accent] + [team_rows.RIDER_BAR] * 7
    bands.clear()
    w.set_accent("#3d8bff")
    try:
        w.grab()
        assert bands[0]["color"] == t.ACCENT.name() != accent
    finally:
        w.set_accent(None)
    bands.clear()
    render(qtbot, "pre_race", start_list(9))
    assert {b["color"] for b in bands} == {team_rows.RIDER_BAR}


@pytest.mark.parametrize("label", ["bibs_names", "names"])
@pytest.mark.parametrize("n", [1, 5, 9, 16, 24])
@pytest.mark.parametrize("layout", ["pre_race", "sprint_points"])
def test_rider_names_plates_and_lap_chips_clear_the_bar(
    qtbot, drawn, monkeypatch, layout, n, label
):
    """However tall the row, the plate, the name's capitals, and a lap
    chip keep SLANT_AIR from the bar's slanted edge where it leans
    nearest them, and every name stands inside its own row."""
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    plates = record_plates(monkeypatch)
    chips = record_chips(monkeypatch)
    laps = [1 if i % 3 == 0 else (-1 if i % 3 == 1 else 0) for i in range(n)]
    data = start_list(n, laps) if layout == "pre_race" else table(n, laps=1, penalty=-5)
    w = render(qtbot, layout, data, label=label)
    u = w.pages[layout].u
    air = team_rows.SLANT_AIR * u - 0.01
    rows = [b["row"] for b in bands]
    assert rows
    # The page's lap chips, not the top bar's group chip.
    page_chips = [c for c, device in chips if device is w.pages[layout]]
    entries = data.roster if layout == "pre_race" else data.rows
    names = {(e if layout == "pre_race" else e.entry).names[0] for e in entries}
    shown = [(r, px) for s, r, px, _c in drawn if named(s, names)]
    assert len(shown) == len(rows)
    for row in rows:
        mine = [r for r, _px in shown if row.contains(r.center())]
        assert len(mine) == 1, row
        for r, px in shown:
            if not row.contains(r.center()):
                continue
            fm = QFontMetricsF(t.font(px, t.SEMI))
            top = r.center().y() + (fm.ascent() - fm.descent()) / 2 - fm.capHeight()
            assert swatch_air(row, r.left(), top, u) >= air
        for pl in [pl for pl in plates if row.contains(pl.center())]:
            assert swatch_air(row, pl.left(), pl.top(), u) >= air
            assert row.top() <= pl.top() and pl.bottom() <= row.bottom()
        for c in [c for c in page_chips if row.contains(c.center())]:
            assert swatch_air(row, c.left(), c.top(), u) >= air
            assert c.right() <= row.right()
    if label == "bibs_names":
        assert len(plates) == len(rows)
    if layout == "pre_race":
        assert page_chips


def _still(drawn, bands, names) -> tuple:
    """What a race must never move: the bands, the names' places, and the names' sizes and text.

    The text as shown, so a name cut or initialed further is a change.
    """
    texts = sorted(
        (round(r.x(), 2), round(r.y(), 2), px, s) for s, r, px, _c in drawn if named(s, names)
    )
    return (
        [b["row"].getRect() for b in bands],
        [(x, y) for x, y, _px, _s in texts],
        [(px, s) for _x, _y, px, s in texts],
    )


@pytest.mark.parametrize("long", [False, True], ids=["usual", "long"])
@pytest.mark.parametrize("label", ["bibs_names", "names"])
@pytest.mark.parametrize("n", [1, 3, 5, 9, 16])
@pytest.mark.parametrize("size", [(1920, 1080), (1280, 720), (1024, 768), (1000, 900)])
def test_nothing_on_the_rider_pages_steps_down_through_a_lap_and_a_penalty(
    qtbot, drawn, monkeypatch, n, label, size, long
):
    """The first lap taken, the first penalty given, and the stamp never
    move a row, its bar, or its name, on the start list or the table,
    however much of its room a long name takes: a name keeps its size and
    is never cut or initialed further. A start list at its base sizes sets
    its names smaller for a lap chip, as it always has (design section
    10); a grown one keeps their size and text too."""
    bands = record_bands(monkeypatch)
    names = [e.names[0] for e in start_list(n, long=long).roster]
    pages: dict = {}

    def seen(layout, data):
        bands.clear()
        drawn.clear()
        pages[layout] = render(qtbot, layout, data, size=size, label=label).pages[layout]
        return _still(drawn, bands, names)

    first = seen("pre_race", start_list(n, long=long))
    _cols, _pitch, name_cap = pages["pre_race"]._layout[1]
    grown = name_cap > (56 if n <= 6 else 46)
    for laps in ([1] + [0] * (n - 1), [-1] * n):
        bars, places, sizes = seen("pre_race", start_list(n, laps, long))
        assert (bars, places) == first[:2]
        assert sizes == first[2] or not grown
    final = P.Header(title="Points Race", group="Cat 1/2", status="Final")
    states = [table(n, long=long), table(n, laps=1, long=long)]
    states.append(table(n, laps=1, penalty=-5, long=long))
    states.append(table(n, laps=-1, penalty=-20, header=final, long=long))
    first = seen("sprint_points", states[0])
    totals = None
    for data in states:
        assert seen("sprint_points", data) == first
        px = {px for s, _r, px, _c in drawn if s in {str(r.total) for r in data.rows}}
        assert totals is None or px == totals
        totals = px


def test_the_rider_table_keeps_its_headings_and_plain_laps(qtbot, drawn, monkeypatch):
    """The table keeps its heading row, with RIDER over the plates, and
    its laps as plain "+1" and "−1": the Madison's "L" is for a table
    with no headings."""
    from madtracker.board.payloads import lap_text

    plates = record_plates(monkeypatch)
    data = table(9, laps=1, penalty=-5)
    data.rows[4].laps = -1
    render(qtbot, "sprint_points", data)
    seen = strings(drawn)
    for heading in ("#", "RIDER", "SPRINT PTS", "LAPS", "PENALTY", "TOTAL"):
        assert heading in seen
    assert lap_text(1) in seen and lap_text(-1) in seen
    assert not [s for s in seen if s.endswith("L") and s[:1] in "+−"]
    rider = next(r for s, r, *_ in drawn if s == "RIDER")
    assert rider.left() == pytest.approx(min(pl.left() for pl in plates), abs=0.5)


# Names of a usual length and short names, as design section 10 measures them.
USUAL = ["Arlo Quillan", "Bexa Yarrow", "Corin Fallowby", "Dalia Vesk", "Emrys Dunhallow"]
SHORT = ["Ada Quill", "Bo Lin", "Cy Dorn", "Di Ash"]


def test_the_rider_sizes_design_section_10_states_at_1080(qtbot, drawn):
    """Five riders of a usual length set start list names of 100 px
    against the base list's 56; five short-name riders set table totals
    of 97 px and names of 74, nine riders 60 and 46, sixteen 44 and 36."""
    roster = [P.Entry(bibs=[str(i + 1)], names=[n]) for i, n in enumerate(USUAL)]
    render(qtbot, "pre_race", P.PreRace(header=START, roster=roster))
    assert {px for s, _r, px, _c in drawn if s in USUAL} == {100}
    for n, total_px, name_px in ((5, 97, 74), (9, 60, 46), (16, 44, 36)):
        rows = [
            P.StandingRow(
                rank=i + 1,
                entry=P.Entry(bibs=[str(500 + i)], names=[SHORT[i % 4]]),
                sprints=[10 + i, None],
                total=1000 + i,
            )
            for i in range(n)
        ]
        drawn.clear()
        render(qtbot, "sprint_points", P.Standings(RUNNING, 2, rows, current_sprint=1))
        totals = {px for s, _r, px, _c in drawn if s in {str(r.total) for r in rows}}
        assert totals == {total_px}, n
        assert {px for s, _r, px, _c in drawn if s in SHORT} == {name_px}, n


# Elimination and the result -------------------------------------------------

ELIM = P.Header(title="Elimination", group="Cat 1/2", status="3 of 12 out")
FINAL = P.Header(title="Scratch Race", group="Cat 1/2", status="Final")


def elimination(n: int, long: bool = False, out_before: int = 2) -> P.Elimination:
    es = [rider(i, long) for i in range(n + 1 + out_before)]
    return P.Elimination(
        header=ELIM, remaining=es[:n], last_eliminated=es[n], eliminated=es[n + 1 :]
    )


def result(n: int, long: bool = False, header: P.Header = FINAL) -> P.Finish:
    return P.Finish(header=header, placings=[P.Placing(i + 1, rider(i, long)) for i in range(n)])


def record_texts(monkeypatch) -> list[tuple]:
    """Every line of text: its ink's box from its capitals' top, its size, color and device.

    The ink's left edge follows the line's alignment, so a centered name
    is measured where it is drawn, not where its rect starts.
    """
    from PySide6.QtCore import Qt

    from madtracker.board import theme as t

    seen: list[tuple] = []
    text = t.text
    left_v = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    def record(p, rect, s, f, color, align=left_v, *a, **k):
        used = text(p, rect, s, f, color, align, *a, **k)
        fm = QFontMetricsF(f)
        if align & Qt.AlignmentFlag.AlignHCenter:
            left = rect.center().x() - used / 2
        elif align & Qt.AlignmentFlag.AlignRight:
            left = rect.right() - used
        else:
            left = rect.left()
        top = rect.center().y() + (fm.ascent() - fm.descent()) / 2 - fm.capHeight()
        ink = QRectF(left, top, used, fm.capHeight())
        seen.append((s, ink, f.pixelSize(), QColor(color).name(), p.device()))
        return used

    monkeypatch.setattr(t, "text", record)
    return seen


ROW_PAGES = [("elimination", n) for n in (1, 3, 4, 6, 8, 14)] + [
    ("finish", n) for n in (3, 8, 16, 24)
]


def _row_data(layout: str, n: int, long: bool = False):
    return elimination(n, long) if layout == "elimination" else result(n, long)


@pytest.mark.parametrize("n", [1, 3, 4, 6, 8, 14])
def test_elimination_rows_and_cards_take_the_row_shape(qtbot, monkeypatch, n):
    """The riders still in, as cards or as rows, and the last-out card are
    each painted by the Madison's band: square left end, rounded right end,
    the bar flush left at the board's slant, the fade and the texture. A
    rider still in has the neutral bar: an elimination has no leader."""
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    w = render(qtbot, "elimination", elimination(n))
    page = w.pages["elimination"]
    u = page.u
    assert len(bands) == n + 1
    assert {b["slant"] for b in bands} == {t.SLANT}
    assert all(b["texture"] is page.texture for b in bands)
    assert [b["color"] for b in bands[:n]] == [team_rows.RIDER_BAR] * n
    bands.clear()
    page.fresh = False
    img = page.grab().toImage()
    bar = QColor(team_rows.RIDER_BAR)
    for b in bands[:n]:
        row = b["row"]
        foot = img.pixelColor(int(row.left() + team_rows.SWATCH_W * u / 2), int(row.bottom() - 3))
        assert _close(foot, bar, 24), foot.name()
        corner = img.pixelColor(int(row.left() + 1), int(row.top() + 1))
        assert _close(corner, bar, 24), corner.name()
        past = img.pixelColor(
            int(row.left() + team_rows.SWATCH_W * u + 6 * u), int(row.bottom() - 3)
        )
        assert not _close(past, bar, 24)
        right = img.pixelColor(int(row.right() - 1), int(row.top() + 1))
        assert _close(right, t.BG, 6), right.name()


@pytest.mark.parametrize("fresh", [True, False], ids=["eliminated", "last-out"])
def test_the_eliminated_card_bar_is_the_out_color(qtbot, monkeypatch, drawn, fresh):
    """The last-out card is a rider row whose bar is the out color. While
    the bell's news is fresh the card keeps its red treatment, the red
    edge and the Eliminated label; settled, it reads Last out without
    the edge."""
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    w = render(qtbot, "elimination", elimination(4))
    page = w.pages["elimination"]
    page.fresh = fresh
    bands.clear()
    drawn.clear()
    img = page.grab().toImage()
    u = page.u
    card = bands[-1]
    assert card["color"] == t.OUT.name()
    assert card["slant"] == t.SLANT and card["texture"] is page.texture
    row = card["row"]
    foot = img.pixelColor(int(row.left() + team_rows.SWATCH_W * u / 2), int(row.bottom() - 4 * u))
    assert _close(foot, t.OUT, 24), foot.name()
    edge = img.pixelColor(int(row.right() - 3 * u), int(row.center().y()))
    assert _close(edge, t.OUT, 40) == fresh, edge.name()
    label = "ELIMINATED" if fresh else "LAST OUT"
    assert [c for s, _r, _px, c in drawn if s == label] == [(t.OUT if fresh else t.MUTED).name()]


def test_the_podium_bars_are_the_accent_and_the_rest_neutral(qtbot, monkeypatch):
    """Every place is a rider row; the podium's three bars are the accent,
    as 1st is, and the rest neutral. A venue's accent follows."""
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    w = render(qtbot, "finish", result(8))
    page = w.pages["finish"]
    accent = t.ACCENT.name()
    assert [b["color"] for b in bands] == [accent] * 3 + [team_rows.RIDER_BAR] * 5
    assert {b["slant"] for b in bands} == {t.SLANT}
    assert all(b["texture"] is page.texture for b in bands)
    bands.clear()
    w.set_accent("#3d8bff")
    try:
        w.grab()
        assert [b["color"] for b in bands[:3]] == [t.ACCENT.name()] * 3 != [accent] * 3
    finally:
        w.set_accent(None)
    bands.clear()
    render(qtbot, "finish", result(24))
    assert len(bands) == 24
    # A rider tied for 3rd below the podium's rows is on the podium too.
    tied = result(8)
    tied.placings[3].place = 3
    bands.clear()
    render(qtbot, "finish", tied)
    assert [b["color"] for b in bands] == [accent] * 4 + [team_rows.RIDER_BAR] * 4


def test_the_result_sizes_design_section_10_states_at_1080(qtbot, drawn):
    """Three places of a usual length set their names at 112 px against
    the base 64, and six places at 98 and 58 against 64 and 38."""
    names = [*USUAL, "Fenna Tamsk"]
    for n, podium_px, rest_px in ((3, 112, None), (6, 98, 58)):
        data = P.Finish(
            header=FINAL,
            placings=[
                P.Placing(i + 1, P.Entry(bibs=[str(i + 1)], names=[names[i]])) for i in range(n)
            ],
        )
        drawn.clear()
        render(qtbot, "finish", data)
        assert {px for s, _r, px, _c in drawn if s in names[:3]} == {podium_px}, n
        if rest_px:
            assert {px for s, _r, px, _c in drawn if s in names[3:n]} == {rest_px}, n


def test_an_undecided_results_rows_hold_still_as_its_places_are_decided(qtbot, monkeypatch):
    """A Win-and-Out shows its places as the bells decide them: the rows
    below the podium keep one place column, so a tenth place decided
    never moves the rows before it."""
    bands = record_bands(monkeypatch)
    lefts = set()
    for n in range(4, 13):
        header = P.Header(title="Win-and-Out", group="Cat 1/2", status=f"{n} of 12 places")
        bands.clear()
        render(qtbot, "finish", result(n, header=header))
        lefts.add(round(bands[3]["row"].left(), 3))
    assert len(lefts) == 1


@pytest.mark.parametrize("long", [False, True], ids=["usual", "long"])
@pytest.mark.parametrize("label", ["bibs_names", "names", "bibs"])
@pytest.mark.parametrize(("layout", "n"), ROW_PAGES)
@pytest.mark.parametrize("size", [(1920, 1080), (1440, 1080), (1000, 900)])
def test_the_result_and_elimination_names_clear_the_bar(
    qtbot, monkeypatch, layout, n, label, long, size
):
    """However tall the row or card, every plate, name, and lap chip on it
    keeps SLANT_AIR from the bar's slanted edge where it leans nearest,
    and stays inside it; a place stands left of its row, as on the table."""
    from madtracker.board import team_rows
    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    plates = record_plates(monkeypatch)
    chips = record_chips(monkeypatch)
    texts = record_texts(monkeypatch)
    w = render(qtbot, layout, _row_data(layout, n, long), size=size, label=label)
    page = w.pages[layout]
    u = page.u
    air = team_rows.SLANT_AIR * u - 0.01
    rows = [b["row"] for b in bands]
    assert rows
    digits = {t.PLATE_TEXT.name(), t.PLATE_OUT_TEXT.name()}
    mine = [(s, ink) for s, ink, _px, c, dev in texts if dev is page and c not in digits]
    ordinals = {P.ordinal(i) for i in range(1, n + 1)}
    for row in rows:
        for s, ink in mine:
            if s in ordinals:
                # Its own row's, not the next column's.
                if row.top() <= ink.center().y() <= row.bottom() and ink.center().x() < row.right():
                    assert ink.right() <= row.left(), s
                continue
            if not row.contains(ink.center()):
                continue
            assert swatch_air(row, ink.left(), ink.top(), u) >= air, s
            assert ink.right() <= row.right(), s
        for pl in [pl for pl in plates if row.contains(pl.center())]:
            assert swatch_air(row, pl.left(), pl.top(), u) >= air
            assert row.top() <= pl.top() and pl.bottom() <= row.bottom()
            assert pl.right() <= row.right()
        for c, dev in chips:
            if dev is page and row.contains(c.center()):
                assert swatch_air(row, c.left(), c.top(), u) >= air
                assert c.right() <= row.right()


# Score changes on the rider table --------------------------------------------


def bib(i: int) -> str:
    return rider(i).bibs[0]


def name(i: int) -> str:
    return rider(i).names[0]


def scored(
    prev: P.Standings,
    changes: dict[int, int],
    kind: str = "sprint",
    laps: dict[int, int] | None = None,
    penalties: dict[int, int] | None = None,
    status: str | None = None,
) -> P.Standings:
    """``prev`` after ``changes`` to the riders' totals, by their index, ranked again.

    A sprint's points go in its next column, so SPRINT PTS rises with the total.
    """
    data = copy.deepcopy(prev)
    index = {bib(i): i for i in range(len(prev.rows))}
    for r in data.rows:
        i = index[r.entry.bibs[0]]
        gain = changes.get(i, 0)
        r.total += gain
        r.laps += (laps or {}).get(i, 0)
        r.penalty += (penalties or {}).get(i, 0)
        if kind == "sprint":
            r.sprints = [*(v for v in r.sprints if v is not None), gain]
    data.rows.sort(key=lambda r: -r.total)
    for i, r in enumerate(data.rows):
        r.rank = i + 1
    if status is not None:
        data.header = replace(data.header, status=status)
    data.scored = P.Scored(kind, [(bib(i),) for i in changes])
    return data


def playing(qtbot, prev, size=(1920, 1080)):
    """A clocked board showing ``prev``, the table a score change plays from."""
    from madtracker.board.motion import ManualClock

    w = render(qtbot, "sprint_points", prev, size=size)
    clock = ManualClock(0.0)
    w.set_clock(clock)
    return w, clock


def frame(w, clock, drawn, at: float) -> dict:
    """What the board draws ``at`` ms on its clock: each string's rect, size and color."""
    clock.advance(at - clock.now())
    drawn.clear()
    w.grab()
    return {s: (QRectF(r), px, c) for s, r, px, c in drawn}


def record_score_chips(monkeypatch) -> list[tuple[str, str, str, QRectF]]:
    """Every score chip drawn: its text, fill, ink and resting rect."""
    from madtracker.board import pages

    chips: list = []
    chip = pages.score_chip

    def record(p, rect, s, f, fill, ink, *args, **kwargs):
        chips.append((s, fill.name(), ink.name(), QRectF(rect)))
        return chip(p, rect, s, f, fill, ink, *args, **kwargs)

    monkeypatch.setattr(pages, "score_chip", record)
    return chips


def order(at: dict, indexes: list[int]) -> list[int]:
    """The riders ``indexes`` top to bottom as drawn."""
    return sorted((i for i in indexes if name(i) in at), key=lambda i: at[name(i)][0].center().y())


def column(drawn, heading: str) -> dict[int, str]:
    """The figures right-aligned under ``heading``, by their row's middle."""
    right = next(r.right() for s, r, *_ in drawn if s == heading)
    return {
        round(r.center().y()): s
        for s, r, *_ in drawn
        if s != heading and abs(r.right() - right) < 1
    }


# Past the end of a two-rider play: both totals landed and the rows moved.
SETTLED = 2 * 1160 + 380 + 600 + 50


def test_a_points_race_sprint_slams_each_riders_points_in_order_then_reorders(
    qtbot, drawn, monkeypatch
):
    from madtracker.board import scorebug
    from madtracker.board import theme as t

    chips = record_score_chips(monkeypatch)
    prev = table(9)
    # Rider 2 (56) takes the lead with 5; rider 4 (52) passes rider 3 (54) with 3.
    data = scored(prev, {2: 5, 4: 3}, status="After Sprint 3 of 8")
    w, clock = playing(qtbot, prev)
    w.set_layout("sprint_points", data)
    page = w.pages["sprint_points"]
    at = frame(w, clock, drawn, 100)
    assert "+5" in at and "+3" not in at and "61" not in at
    assert [c[:3] for c in chips] == [("+5", t.ACCENT.name(), t.ACCENT_INK.name())]
    # On rider 2's row, right-aligned to the TOTAL column.
    assert at["+5"][0].center().y() == pytest.approx(at[name(2)][0].center().y(), abs=1)
    assert chips[-1][3].right() == pytest.approx(at["60"][0].right(), abs=1)
    # The headings stand while it plays.
    for heading in ("#", "RIDER", "SPRINT PTS", "LAPS", "TOTAL"):
        assert heading in at
    # Rows hold their old order while the totals play.
    assert order(at, list(range(9))) == list(range(9))
    at = frame(w, clock, drawn, scorebug.STEP_MS + 100)
    assert "+3" in at and "61" in at
    land = scorebug.STEP_MS + scorebug.SWAP_AT_MS + scorebug.SWAP_MS
    held = frame(w, clock, drawn, land - 10)[name(2)][0].center().y()
    mid = frame(w, clock, drawn, land + scorebug.REORDER_MS / 2)[name(2)][0].center().y()
    at = frame(w, clock, drawn, SETTLED)
    assert at[name(2)][0].center().y() < mid < held
    assert "+5" not in at and "+3" not in at
    assert order(at, list(range(9))) == [2, 0, 1, 4, 3, 5, 6, 7, 8]
    assert not page.scoring_now()


def test_the_leaders_bar_moves_to_the_new_leader_once_the_totals_land(qtbot, drawn, monkeypatch):
    """The accent bar stays with the leader the stands see until the last
    total lands, then rides up with the new leader as the rows reorder."""
    from madtracker.board import scorebug
    from madtracker.board import theme as t

    bands = record_bands(monkeypatch)
    prev = table(9)
    data = scored(prev, {2: 5}, status="After Sprint 3 of 8")
    w, clock = playing(qtbot, prev)
    w.set_layout("sprint_points", data)

    def leader(at: float) -> int:
        bands.clear()
        shown = frame(w, clock, drawn, at)
        accent = [b["row"] for b in bands if b["color"] == t.ACCENT.name()]
        assert len(accent) == 1 and len(bands) == 9
        return next(i for i in range(9) if accent[0].contains(shown[name(i)][0].center()))

    assert leader(100) == 0
    assert leader(scorebug.SWAP_AT_MS + 10) == 0
    reorder = scorebug.SWAP_AT_MS + scorebug.SWAP_MS
    assert leader(reorder + scorebug.REORDER_MS / 2) == 2
    assert leader(reorder + scorebug.REORDER_MS + 50) == 2


def test_a_tempo_race_chip_reads_plus_one(qtbot, drawn, monkeypatch):
    chips = record_score_chips(monkeypatch)
    prev = table(9)
    data = scored(prev, {3: 1}, status="After Sprint 3 of 8")
    w, clock = playing(qtbot, prev)
    w.set_layout("sprint_points", data)
    frame(w, clock, drawn, 100)
    assert [c[0] for c in chips] == ["+1"]


def test_a_points_race_lap_and_penalty_slam_and_corrections_stay_quiet(qtbot, drawn, monkeypatch):
    from madtracker.board import theme as t

    chips = record_score_chips(monkeypatch)
    prev = table(9)
    lapped = scored(prev, {5: 20}, kind="lap_gained", laps={5: 1})
    w, clock = playing(qtbot, prev)
    page = w.pages["sprint_points"]
    w.set_layout("sprint_points", lapped)
    at = frame(w, clock, drawn, 100)
    assert [c[:3] for c in chips] == [("+20", t.ACCENT.name(), t.ACCENT_INK.name())]
    # The lap figure changes as the new total rises in.
    assert "+1" not in at
    at = frame(w, clock, drawn, 5000)
    assert "+1" in at and "70" in at and not page.scoring_now()
    chips.clear()
    penalized = scored(lapped, {1: -5}, kind="penalty", penalties={1: -5})
    w.set_layout("sprint_points", penalized)
    at = frame(w, clock, drawn, clock.now() + 100)
    assert [c[:3] for c in chips] == [("−5", t.OUT.name(), t.TEXT.name())]
    assert "53" not in at
    # A redraw leaves the play running; a correction stops it and settles.
    w.set_layout("sprint_points", replace(penalized, scored=None))
    assert page.scoring_now()
    lowered = copy.deepcopy(penalized)
    row = next(r for r in lowered.rows if r.entry.bibs[0] == bib(1))
    row.penalty, row.total = -2, row.total + 3
    lowered.scored = None
    chips.clear()
    w.set_layout("sprint_points", lowered)
    at = frame(w, clock, drawn, clock.now() + 100)
    assert not page.scoring_now() and not chips
    assert "−2" in at and "56" in at


def test_sprint_pts_updates_as_the_total_rises_in(qtbot, drawn):
    from madtracker.board import scorebug

    prev = table(9)
    data = scored(prev, {2: 9}, status="After Sprint 3 of 8")
    w, clock = playing(qtbot, prev)
    w.set_layout("sprint_points", data)
    frame(w, clock, drawn, 100)
    y = round(next(r.center().y() for s, r, *_ in drawn if s == name(2)))
    assert column(drawn, "SPRINT PTS").get(y) == "3"
    frame(w, clock, drawn, scorebug.SWAP_AT_MS + 10)
    assert column(drawn, "SPRINT PTS").get(y) == "12"


def test_a_rider_scoring_off_the_shown_page_updates_quietly(qtbot, drawn, monkeypatch):
    chips = record_score_chips(monkeypatch)
    prev = table(18)
    w, clock = playing(qtbot, prev)
    page = w.pages["sprint_points"]
    assert page.page_count() == 2 and page.per_page() == 9
    # A lap on the second page while the first is in view.
    lapped = scored(prev, {17: 10}, kind="lap_gained", laps={17: 1})
    w.set_layout("sprint_points", lapped)
    at = frame(w, clock, drawn, 100)
    assert not chips and not page.scoring_now()
    assert name(17) not in at
    # A sprint with riders on both pages plays only the one in view, and
    # the page does not turn while it plays.
    data = scored(lapped, {1: 5, 13: 3}, status="After Sprint 3 of 8")
    w.set_layout("sprint_points", data)
    frame(w, clock, drawn, clock.now() + 100)
    assert page.scoring_now()
    w._turn_page()
    at = frame(w, clock, drawn, clock.now() + 3000)
    assert {c[0] for c in chips} == {"+5"}
    assert name(13) not in at and name(1) in at


def test_no_layout_shows_a_sprint_card(qtbot, drawn, monkeypatch):
    """The table plays a sprint itself: no card over it, clocked or at
    rest, and nothing of the card left in the payload or the board."""
    import dataclasses

    from madtracker.board.window import BoardCanvas

    assert not hasattr(P, "SprintResult")
    assert "sprint_result" not in {f.name for f in dataclasses.fields(P.Standings)}
    assert not hasattr(BoardCanvas, "SPRINT_OVERLAY_MS")
    prev = table(9)
    data = scored(prev, {2: 5, 4: 3}, status="After Sprint 3 of 8")
    w, clock = playing(qtbot, prev)
    w.set_layout("sprint_points", data)
    assert not hasattr(w, "_overlay")
    for at in (100, 1300, SETTLED, 12000):
        frame(w, clock, drawn, at)
        assert not [s for s, *_ in drawn if s.startswith("Sprint ") or s == "Final sprint"]
    # Headless, with no clock, the board shows where the play ends.
    rest = render(qtbot, "sprint_points", prev)
    chips = record_score_chips(monkeypatch)
    rest.set_layout("sprint_points", data)
    drawn.clear()
    rest.grab()
    assert not chips and "61" in strings(drawn) and "+5" not in strings(drawn)


# The start list dissolving into the table ------------------------------------


def zero_table(n: int) -> P.Standings:
    """The table a rider start list dissolves into: every rider at 0, in start-list order."""
    rows = [
        P.StandingRow(rank=i + 1, entry=e, sprints=[]) for i, e in enumerate(start_list(n).roster)
    ]
    header = replace(RUNNING, status="After Sprint 1 of 8")
    return P.Standings(header=header, sprint_count=8, rows=rows, current_sprint=1)


def dissolving(qtbot, n: int = 9, changes: dict[int, int] | None = None):
    """A clocked board on a rider start list, and the first sprint's payload."""
    from madtracker.board.motion import ManualClock

    w = render(qtbot, "pre_race", start_list(n))
    clock = ManualClock(0.0)
    w.set_clock(clock)
    return w, clock, scored(zero_table(n), changes or {2: 5, 4: 3})


def intro_end(rows: int = 9) -> float:
    """When the dissolve and its hold end and the first score plays."""
    from madtracker.board import scorebug

    return scorebug.intro_ms(rows) + scorebug.INTRO_HOLD_MS


def test_the_rider_start_list_dissolves_into_the_table_before_the_first_chip(
    qtbot, drawn, monkeypatch
):
    from madtracker.board import scorebug
    from madtracker.board import theme as t

    chips = record_score_chips(monkeypatch)
    looks = record_looks(monkeypatch)
    bands = record_bands(monkeypatch)
    w, clock, data = dissolving(qtbot)
    picture = w.pages["pre_race"].grab().toImage()
    w.set_layout("sprint_points", data)
    page = w.pages["sprint_points"]
    # At once the page is still the start list, all of it, and no table.
    clock.advance(0)
    looks.clear()
    assert page.grab().toImage() == picture
    assert not looks and not chips and page.scoring_now()
    # Partway, the rows come in top to bottom from the right, the
    # headings with the first; the last row has not begun.
    looks.clear()
    frame(w, clock, drawn, 4 * scorebug.INTRO_STAGGER_MS + 80)
    seen = {s: (op, dx) for s, op, dx in looks}
    first, last = seen[name(0)], seen[name(4)]
    assert first[0] > last[0] > 0
    assert 0 <= first[1] < last[1] <= scorebug.INTRO_DRIFT * page.u
    assert seen["TOTAL"] == pytest.approx(first)
    assert name(8) not in seen
    # The zero table holds in start-list order, no leader and no chip,
    # until the dissolve and the hold end.
    looks.clear()
    bands.clear()
    at = frame(w, clock, drawn, intro_end() - 1)
    assert not chips and order(at, list(range(9))) == list(range(9))
    assert strings(drawn).count("0") == 9
    assert {(op, dx) for _s, op, dx in looks} == {(1.0, 0.0)}
    assert len(bands) == 9 and t.ACCENT.name() not in {b["color"] for b in bands}
    frame(w, clock, drawn, intro_end() + 50)
    assert [c[0] for c in chips] == ["+5"]


def test_the_rider_transition_cancels_on_undo_and_survives_a_redraw(qtbot, drawn, monkeypatch):
    from madtracker.board import scorebug

    chips = record_score_chips(monkeypatch)
    # A redraw leaves it dissolving.
    w, clock, data = dissolving(qtbot)
    page = w.pages["sprint_points"]
    w.set_layout("sprint_points", data)
    frame(w, clock, drawn, 300)
    w.set_layout("sprint_points", replace(data, scored=None))
    frame(w, clock, drawn, 400)
    assert page.scoring_now() and not chips
    frame(w, clock, drawn, intro_end() + 50)
    assert [c[0] for c in chips] == ["+5"]
    # A second score waits behind it and the first.
    chips.clear()
    w, clock, data = dissolving(qtbot)
    w.set_layout("sprint_points", data)
    frame(w, clock, drawn, 300)
    w.set_layout("sprint_points", scored(data, {6: 2}))
    for ms in (50, scorebug.STEP_MS + 100, SETTLED):
        frame(w, clock, drawn, intro_end() + ms)
    assert list(dict.fromkeys(c[0] for c in chips)) == ["+5", "+3", "+2"]
    # Undo back to the start list.
    chips.clear()
    w, clock, data = dissolving(qtbot)
    page = w.pages["sprint_points"]
    w.set_layout("sprint_points", data)
    frame(w, clock, drawn, 300)
    w.set_layout("pre_race", start_list(9))
    at = frame(w, clock, drawn, 310)
    assert w.layout_name() == "pre_race" and "0" not in at and name(8) in at
    assert not page.scoring_now()
    # A switch to another race shows its table whole, with nothing to play.
    w, clock, data = dissolving(qtbot)
    page = w.pages["sprint_points"]
    w.set_layout("sprint_points", data)
    frame(w, clock, drawn, 300)
    w.set_layout("sprint_points", table(9, header=replace(RUNNING, race_id=2)))
    looks = record_looks(monkeypatch)
    at = frame(w, clock, drawn, 310)
    assert "60" in at and {op for _s, op, _dx in looks} == {1.0}
    assert not page.scoring_now()
    frame(w, clock, drawn, intro_end() + 50)
    assert not chips


def test_the_rider_transition_keeps_the_tv_and_preview_in_step(qtbot):
    from madtracker.board.motion import ManualClock
    from madtracker.board.window import ScoreboardWindow

    data = scored(zero_table(9), {2: 5, 4: 3})
    clock = ManualClock()
    boards = []
    for _ in range(2):
        w = ScoreboardWindow("Test Velodrome", "Test Event")
        qtbot.addWidget(w)
        w.resize(1920, 1080)
        w.set_clock(clock)
        w.set_layout("pre_race", start_list(9))
        w.grab()
        boards.append(w)
    for w in boards:
        w.set_layout("sprint_points", data)
    tv, preview = boards
    # The TV paints every step; the preview first paints partway.
    for at in (100, 200, 300, 450):
        clock.advance(at - clock.now())
        if at < 450:
            tv.grab()
    assert tv.grab().toImage() == preview.grab().toImage()
    clock.advance(intro_end() + 300 - clock.now())
    assert tv.grab().toImage() == preview.grab().toImage()


def test_headless_rider_boards_show_the_table_at_once(qtbot, drawn, monkeypatch):
    chips = record_score_chips(monkeypatch)
    w = render(qtbot, "pre_race", start_list(9))
    drawn.clear()
    w.set_layout("sprint_points", scored(zero_table(9), {2: 5, 4: 3}))
    w.grab()
    assert not chips and {"5", "3"} <= set(strings(drawn))
    assert not w.pages["sprint_points"].scoring_now()


def test_a_long_field_dissolves_into_the_page_that_holds_the_first_scorers(
    qtbot, drawn, monkeypatch
):
    """Eighteen riders are two pages of nine; the first sprint's two
    scorers from the start list's second half bring the table in on its
    second page, so the stands see their chips."""
    from madtracker.board import scorebug

    chips = record_score_chips(monkeypatch)
    w, clock, data = dissolving(qtbot, 18, {12: 5, 14: 3, 1: 2})
    w.set_layout("sprint_points", data)
    page = w.pages["sprint_points"]
    at = frame(w, clock, drawn, intro_end(9) - 1)
    assert order(at, list(range(18))) == list(range(9, 18))
    assert {"10", "18"} <= set(at)
    for ms in (50, scorebug.STEP_MS + 100, SETTLED):
        frame(w, clock, drawn, intro_end(9) + ms)
    assert list(dict.fromkeys(c[0] for c in chips)) == ["+5", "+3"]
    assert not page.scoring_now()
