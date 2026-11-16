"""Rider rows on the board: the Madison row with a neutral bar, the leader's in the accent."""

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFontMetricsF

from madtracker.board import payloads as P
from ui.board_helpers import render, strings

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
