import re
import sys

import pytest

from madtracker.control.race import LiveRace
from madtracker.export import pdf as pdf_mod
from madtracker.export import table, write_results_pdf
from madtracker.scoring import rules as R

LONG_FIRST, LONG_LAST = "Maximiliana-Josephine", "Konstantinopoulou"


@pytest.fixture
def texts(drawn):
    class Texts(list):
        def __contains__(self, item):
            return any(d["text"] == item for d in drawn)

        def __iter__(self):
            return iter([d["text"] for d in drawn])

    return Texts()


@pytest.fixture
def scratch(store, event):
    """A scratch race of seven: one long name, five placed, two DNF."""
    event_id, ids = event
    extra = (
        (5, LONG_FIRST, LONG_LAST),
        (6, "Ines", "Halvorsen"),
        (7, "Wu", "Fei"),
    )
    for bib, first, last in extra:
        rider = store.add_rider(first, last)
        store.add_entry(event_id, rider.rider_id, bib, local_group="Cat 3")
        ids[bib] = rider.rider_id
    race = store.add_race(event_id, "Scratch E", "scratch", rules=R.placings_rules().to_dict())
    for bib in (1, 2, 3, 4, 5, 6, 7):
        store.add_race_entry(race.race_id, ids[bib])
    s = LiveRace(store, race.race_id)
    assert s.act(ids[2], "dnf").ok and s.act(ids[6], "dnf").ok
    for bib in (5, 1, 3, 7, 4):
        assert s.click(ids[bib]).ok
    assert s.state == "provisional"
    return s


def _names(drawn, *names):
    return [d for d in drawn if d["text"] in names]


def test_pdf_is_written_with_races_and_non_ascii(store, event, seeded, tmp_path, texts):
    out = write_results_pdf(store, event[0], tmp_path / "r.pdf")
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 5000
    joined = "\n".join(texts)
    for name in ("Chase A", "Points B", "Madison C"):
        assert name in texts
    # A race still in setup is left off the archival sheet.
    assert "Elimination D" not in joined
    assert "Cat 3" in texts
    assert "Zoe Łukasik" in texts
    assert "Red" in texts and "Out at sprint" not in joined
    assert "DNF" in texts
    assert "MadTracker" in joined and "Friday Night Test" in texts
    assert b"pdfaid:part" in data and b"<pdfaid:conformance>B" in data.replace(b'"', b"")


def test_pdf_embeds_the_bundled_font(store, event, seeded, tmp_path):
    # The bundled files must always be found; a None here is a packaging bug.
    assert pdf_mod.find_font() is not None
    data = write_results_pdf(store, event[0], tmp_path / "r.pdf").read_bytes()
    # fpdf2 subsets each face under a tagged name, eg: MPDFAA+InterBold.
    names = {n.split(b"+")[-1] for n in re.findall(rb"/BaseFont\s*/([^\s/<>\[\]]+)", data)}
    assert names == {b"Inter", b"InterBold", b"InterBlack"}
    assert b"/FontFile2" in data
    for other in (b"Arial", b"Liberation", b"DejaVu", b"/Helvetica"):
        assert other not in data


def test_core_font_fallback_does_not_crash(store, event, seeded, tmp_path, monkeypatch, texts):
    monkeypatch.setattr(pdf_mod, "find_font", lambda: None)
    out = write_results_pdf(store, event[0], tmp_path / "plain.pdf", venue_name="Test Velodrome")
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and b"pdfaid" not in data
    assert "Zoe ?ukasik" in texts


def test_missing_logo_falls_back_to_venue_name(store, event, seeded, tmp_path, texts):
    write_results_pdf(
        store, event[0], tmp_path / "n.pdf", logo_path=tmp_path / "nope.png", venue_name="Test Oval"
    )
    assert "Test Oval" in texts


def test_empty_event_still_writes(store, tmp_path):
    m = store.add_event("Empty Night", "2026-04-01")
    out = write_results_pdf(store, m.event_id, tmp_path / "e.pdf")
    assert out.read_bytes().startswith(b"%PDF")


def test_points_rows_carry_total_and_net_laps(store, event, seeded, tmp_path, drawn):
    write_results_pdf(store, event[0], tmp_path / "p.pdf")
    texts = [d["text"] for d in drawn]
    start = texts.index("Points B")
    section = texts[start : texts.index("Madison C")]
    assert "Total" in section and "Laps" in section and "+1" in section


def test_nothing_overflows_its_cell_or_the_page(store, event, seeded, scratch, tmp_path, drawn):
    write_results_pdf(store, event[0], tmp_path / "o.pdf")
    assert drawn
    for d in drawn:
        if "{nb}" in d["text"]:
            continue
        assert d["width"] <= d["w"] - 2 * d["margin"] + 0.01, d
        assert d["x"] + d["w"] <= d["page_w"] + 0.01, d
        assert d["y"] + d["h"] <= d["page_h"] + 0.01, d


def test_long_name_fits_its_column(store, event, scratch, tmp_path, drawn):
    """A long name prints whole at the podium size: the wide page's name column holds it."""
    write_results_pdf(store, event[0], tmp_path / "long.pdf")
    [cell] = _names(drawn, f"{LONG_FIRST} {LONG_LAST}")
    assert cell["width"] <= cell["w"] - 2 * cell["margin"]
    assert cell["size"] == table.TOP.size


def test_the_results_sheet_is_landscape(store, event, seeded, tmp_path, drawn):
    write_results_pdf(store, event[0], tmp_path / "wide.pdf")
    assert all(d["page_w"] > d["page_h"] for d in drawn)


def test_rows_split_evenly_when_neither_page_can_hold_four():
    """Five rows with four fitting: three and two, not one alone under the heading."""
    assert table.pages(42, 200, [10.0] * 5) == [3, 2]
    assert table.pages(32, 200, [10.0] * 4) == [2, 2]
    # Enough rows for both pages: the next page gets its four, as before.
    assert table.pages(62, 200, [10.0] * 9) == [5, 4]
    assert table.pages(145, 200, [10.0] * 23) == [14, 9]


def _five_team_madison(store, event):
    event_id, ids = event
    rules = R.SprintPointsRules(sprint_count=2, scored_unit="team")
    race = store.add_race(event_id, "Madison of Five", "madison", rules=rules.to_dict())
    teams = []
    for n, color in enumerate(("Red", "Blue", "Green", "White", "Orange")):
        pair = []
        for k in range(2):
            rider = store.add_rider("Lane", f"{color}{k}")
            store.add_entry(event_id, rider.rider_id, 300 + 2 * n + k, local_group="Cat 4")
            store.add_race_entry(race.race_id, rider.rider_id)
            pair.append(rider.rider_id)
        team = store.add_team(race.race_id, color, color=color)
        for rid in pair:
            store.add_team_member(team.team_id, rid)
        teams.append(team.team_id)
    s = LiveRace(store, race.race_id)
    for team in teams:
        assert s.click(team).ok
    assert s.record_sprint().ok
    for team in teams:
        assert s.click(team).ok
    assert s.state == "provisional"
    return race.race_id


def test_a_madison_of_five_prints_on_one_page_with_the_riders_beside_the_team(
    store, event, tmp_path, drawn
):
    """The team is the row and its riders the detail, at the rider size,
    one per line right of the name and centered with it, so the venue's
    five-team Madison keeps to one podium sheet."""
    event_id, _ = event
    race_id = _five_team_madison(store, event)
    write_results_pdf(store, event_id, tmp_path / "five.pdf", races=[race_id])
    assert {d["page"] for d in drawn} == {1}
    team = next(d for d in drawn if d["text"] == "Red")
    first, second = (next(d for d in drawn if d["text"] == f"Lane Red{k}") for k in (0, 1))
    assert team["size"] == table.TOP.size and first["size"] == table.TOP.rider_pt
    assert first["x"] == second["x"] > team["x"] + team["width"]
    assert second["y"] > first["y"]
    middle = (first["y"] + second["y"] + second["h"]) / 2
    assert team["y"] + team["h"] / 2 == pytest.approx(middle)
    # Every team's riders start at one x, one gap after the widest name.
    riders = [d for d in drawn if d["text"].startswith("Lane ")]
    assert len({round(d["x"], 3) for d in riders}) == 1
    assert not any("(continued)" in d["text"] for d in drawn)


def test_a_rider_name_that_would_wrap_beside_puts_every_team_s_riders_under(
    store, event, tmp_path, drawn
):
    """One rider too long for the riders' column beside the names: the
    whole table goes back to the riders under each name, no row mixed."""
    event_id, _ = event
    race_id = _five_team_madison(store, event)
    rider = next(r for r in store.riders() if r.last_name == "Red0")
    store.update_rider(rider.rider_id, first_name=LONG_FIRST, last_name=LONG_LAST * 5)
    write_results_pdf(store, event_id, tmp_path / "under.pdf", races=[race_id])
    for color in ("Red", "Blue", "Green", "White", "Orange"):
        team = next(d for d in drawn if d["text"] == color)
        first = next(d for d in drawn if d["text"] == f"Lane {color}1")
        assert first["y"] > team["y"] + team["h"] - 0.01 and first["x"] > team["x"], color


def test_a_team_block_beside_is_as_tall_as_its_name_or_its_riders():
    line = table.rider_line(table.REST.rider_pt)
    riders = tuple(
        (bib, table.Lines((name,), table.REST.rider_pt)) for bib, name in (("1", "A"), ("2", "B"))
    )

    def height(names, *, beside):
        team = table.Lines(names, table.REST.size)
        return table.row_text(
            table.REST, team, riders, line, "", table.REST.rider_pt, beside=beside
        ).height

    assert height(("Red",), beside=True) == pytest.approx(max(table.REST.line, 2 * line))
    assert height(("Red",), beside=False) == pytest.approx(table.REST.line + 2 * line)
    # A team name wrapped to three lines is taller than its two riders.
    assert height(("Red", "Long", "Team"), beside=True) == pytest.approx(3 * table.REST.line)


def test_laps_and_penalty_print_at_the_working_size_beside_a_total(
    store, event, seeded, tmp_path, drawn
):
    """Beside a Total the laps and penalty are its working; a finish-order
    race's laps are the ranking fact and keep the row's size."""
    event_id, ids = event
    points = next(r for r in store.races(event_id) if r.name == "Points B")
    s = LiveRace(store, points.race_id)
    assert s.review(ids[1], "points_penalty:5").ok
    chase = store.add_race(event_id, "Chase W", "chase", rules=R.placings_rules().to_dict())
    for bib in (1, 2, 3):
        store.add_race_entry(chase.race_id, ids[bib])
    s = LiveRace(store, chase.race_id)
    assert s.act(ids[2], "lap_gained").ok
    for bib in (2, 1, 3):
        assert s.click(ids[bib]).ok
    write_results_pdf(store, event_id, tmp_path / "working.pdf")
    texts = [d["text"] for d in drawn]
    own = drawn[texts.index("Points B") : texts.index("Madison C")]
    lap = next(d for d in own if d["text"] == "+1")
    penalty = next(d for d in own if d["text"] == "\u22125")
    total = next(d for d in own if abs(d["y"] - lap["y"]) < 0.01 and d["x"] > penalty["x"])
    assert lap["size"] == penalty["size"] == pdf_mod.WORKING_PT
    assert total["size"] == table.TOP.size
    chase_rows = drawn[texts.index("Chase W") :]
    assert next(d for d in chase_rows if d["text"] == "+1")["size"] == table.TOP.size


def _name_lines(drawn, start):
    """The text of the name cell ``start`` and the lines drawn under it in its column."""
    i = next(k for k, d in enumerate(drawn) if d is start)
    lines = []
    while i < len(drawn) and drawn[i]["x"] == start["x"]:
        lines.append(drawn[i]["text"])
        i += 1
    return lines


def test_a_word_too_long_for_a_line_is_broken_and_the_name_wraps(
    store, event, scratch, tmp_path, drawn
):
    """A word wider than the name column breaks over its lines rather than being cut."""
    event_id, ids = event
    full = f"{LONG_FIRST * 3} {LONG_LAST * 2}"
    store.update_rider(ids[5], first_name=LONG_FIRST * 3, last_name=LONG_LAST * 2)
    write_results_pdf(store, event_id, tmp_path / "cut.pdf")
    texts = [d["text"] for d in drawn]
    assert full not in texts
    start = next(d for d in drawn if d["text"].startswith(LONG_FIRST))
    lines = _name_lines(drawn, start)
    assert 1 < len(lines) <= table.NAME_LINES and all(line.strip() for line in lines)
    assert "".join(lines).replace(" ", "") == full.replace(" ", "")
    for d in drawn:
        if "{nb}" not in d["text"]:
            assert d["width"] <= d["w"] - 2 * d["margin"] + 0.01, d


def test_status_riders_follow_the_placed_riders(store, event, scratch, tmp_path, drawn):
    write_results_pdf(store, event[0], tmp_path / "s.pdf")
    order = [
        d["text"]
        for d in drawn
        if d["text"]
        in ("Ada Wren", "Bo Tran", "Cy Park", "Wu Fei", "Zoe Łukasik", "Ines Halvorsen")
    ]
    assert order[:4] == ["Ada Wren", "Bo Tran", "Wu Fei", "Cy Park"]
    assert sorted(order[4:]) == ["Ines Halvorsen", "Zoe Łukasik"]
    codes = [d for d in drawn if d["text"] == "DNF"]
    assert len(codes) == 2 and all(d["size"] == table.STATUS.size for d in codes)


def test_three_row_sizes(store, event, scratch, tmp_path, drawn):
    write_results_pdf(store, event[0], tmp_path / "t.pdf")
    size = {d["text"]: d["size"] for d in drawn}
    for name in ("Ada Wren", "Bo Tran"):
        assert size[name] == table.TOP.size
    for name in ("Wu Fei", "Cy Park"):
        assert size[name] == table.REST.size
    for name in ("Zoe Łukasik", "Ines Halvorsen"):
        assert size[name] == table.STATUS.size
    assert table.TOP.size > table.REST.size > table.STATUS.size


def test_provisional_tag_until_final_then_a_filled_final_tag(
    store, event, scratch, tmp_path, drawn
):
    write_results_pdf(store, event[0], tmp_path / "a.pdf")
    texts = [d["text"] for d in drawn]
    assert texts.count("PROVISIONAL") == 1 and "FINAL" not in texts
    assert scratch.mark_final().ok
    drawn.clear()
    write_results_pdf(store, event[0], tmp_path / "b.pdf")
    texts = [d["text"] for d in drawn]
    assert "Scratch E" in texts and "PROVISIONAL" not in texts
    # The filled tag, as the standings sheet prints it.
    assert texts.count("FINAL") == 1


@pytest.mark.parametrize("final", [False, True])
def test_a_long_race_name_wraps_clear_of_its_tag(store, event, tmp_path, drawn, final):
    """A name that fills the line wraps short of the tag's slot, FINAL as much as PROVISIONAL."""
    event_id, ids = event
    name = (
        "The Very Long Annual Memorial Chase for the Southeast Michigan Track Cycling "
        "Championship Trophy"
    )
    race = store.add_race(event_id, name, "chase", rules=R.placings_rules().to_dict())
    for bib in (1, 2):
        store.add_race_entry(race.race_id, ids[bib])
    live = LiveRace(store, race.race_id)
    for bib in (1, 2):
        assert live.click(ids[bib]).ok
    if final:
        assert live.mark_final().ok
    write_results_pdf(store, event_id, tmp_path / "r.pdf", races=[race.race_id])
    [tag] = _names(drawn, "FINAL" if final else "PROVISIONAL")
    heads = [d for d in drawn if d["text"].startswith("The Very")]
    assert heads
    for d in heads:
        assert d["x"] + d["w"] <= tag["x"] + 0.01, d


@pytest.mark.parametrize(
    ("text", "width", "style", "size", "least", "most"),
    [
        ("B" * 70, 150.0, "B", 15, 11, 2),
        ("Bartholomew Alexander " + "Bergerdorffvoralternwarengewissenhaftschafers" * 2, 110.0, "", 16, 13.6, 3),
        ("Short " + "Q" * 300, 60.0, "", 12, 10, 2),
    ],
)  # fmt: skip
def test_a_word_too_long_for_its_line_is_broken_and_no_line_is_blank(
    text, width, style, size, least, most
):
    """Every wrapped line fits its width, and none is empty, however long one word runs."""
    pdf = pdf_mod.new_doc(
        title="t", subtitle="", logo=None, venue="", footer_text="", doc_title="t", landscape=True
    )
    pdf.add_page()
    lines, pt = pdf_mod._wrap_lines(pdf, text, width, style, size, least, most)
    pdf.use(style, pt)
    room = width - 2 * pdf.c_margin + 1e-6
    assert 1 <= len(lines) <= most
    assert all(line.strip() for line in lines), lines
    assert all(pdf.get_string_width(line) <= room for line in lines), lines
    # Only text that runs past the last line is cut, and the cut says so.
    whole, shown = text.replace(" ", ""), "".join(lines).replace(" ", "")
    if shown != whole:
        assert shown.endswith(pdf_mod.ELLIPSIS) and whole.startswith(shown[:-1])
    pdf.close_fonts()


@pytest.mark.parametrize("final", [False, True])
def test_a_one_word_race_name_stays_clear_of_its_tag(store, event, tmp_path, drawn, final):
    event_id, ids = event
    race = store.add_race(event_id, "B" * 90, "chase", rules=R.placings_rules().to_dict())
    for bib in (1, 2):
        store.add_race_entry(race.race_id, ids[bib])
    live = LiveRace(store, race.race_id)
    for bib in (1, 2):
        assert live.click(ids[bib]).ok
    if final:
        assert live.mark_final().ok
    write_results_pdf(store, event_id, tmp_path / "r.pdf", races=[race.race_id])
    [tag] = _names(drawn, "FINAL" if final else "PROVISIONAL")
    heads = [d for d in drawn if d["text"].startswith("BBB")]
    assert len(heads) == 2
    assert "".join(d["text"] for d in heads) == "B" * 90
    for d in heads:
        assert d["x"] + d["w"] <= tag["x"] + 0.01, d


def test_a_long_unbroken_surname_adds_no_blank_line_to_its_row(store, event, tmp_path, drawn):
    event_id, ids = event
    # Wider than the name column of a race with no sprints.
    surname = "Bergerdorffvoralternwarengewissenhaftschaferswessenschafewarenwohlgepflege" * 2
    rider = store.add_rider("Bartholomew Alexander", surname)
    store.add_entry(event_id, rider.rider_id, 9)
    race = store.add_race(event_id, "Chase", "chase", rules=R.placings_rules().to_dict())
    order = [ids[1], ids[2], ids[3], rider.rider_id]
    for rider_id in order:
        store.add_race_entry(race.race_id, rider_id)
    live = LiveRace(store, race.race_id)
    for rider_id in order:
        assert live.click(rider_id).ok
    write_results_pdf(store, event_id, tmp_path / "r.pdf", races=[race.race_id])
    [first] = _names(drawn, "Bartholomew Alexander")
    name = [d for d in drawn if d["x"] == first["x"] and d["y"] >= first["y"]]
    # The name's lines, whole, each inside the name column, and not one blank.
    assert "".join(d["text"] for d in name).replace(" ", "") == f"BartholomewAlexander{surname}"
    assert all(d["width"] <= d["w"] - 2 * d["margin"] + 0.01 for d in name)
    assert all(d["text"].strip() for d in name)


def test_a_four_digit_bib_prints_whole(store, event, tmp_path, drawn):
    """The roster takes bibs up to 9999, so a podium row prints all four digits."""
    event_id, _ = event
    order = []
    for bib in (8888, 9999, 1111, 4444):
        rider = store.add_rider("Lane", f"Bib{bib}")
        store.add_entry(event_id, rider.rider_id, bib)
        order.append(rider.rider_id)
    race = store.add_race(event_id, "Chase", "chase", rules=R.placings_rules().to_dict())
    for rider_id in order:
        store.add_race_entry(race.race_id, rider_id)
    live = LiveRace(store, race.race_id)
    for rider_id in order:
        assert live.click(rider_id).ok
    write_results_pdf(store, event_id, tmp_path / "r.pdf", races=[race.race_id])
    for bib in ("8888", "9999", "1111", "4444"):
        assert bib in [d["text"] for d in drawn], bib
    assert not any(d["text"].endswith(pdf_mod.ELLIPSIS) for d in drawn)


def test_footer_names_the_event_page_and_time(store, event, scratch, tmp_path, drawn):
    from datetime import datetime

    stamp = datetime(2026, 3, 6, 21, 5).astimezone()
    write_results_pdf(store, event[0], tmp_path / "f.pdf", generated=stamp)
    footer = [d["text"] for d in drawn if "Generated" in d["text"]]
    assert footer and all("Friday Night Test" in t and "2026-Mar-06 9:05 PM" in t for t in footer)
    assert any(d["text"].startswith("Page 1 of") for d in drawn)


def _field_race(store, event_id, name, count, first_bib):
    """A scratch race of ``count`` new riders, all placed in bib order."""
    race = store.add_race(event_id, name, "scratch", rules=R.placings_rules().to_dict())
    riders = []
    for n in range(count):
        rider = store.add_rider("Lane", f"{name.split()[0]}{n:02d}")
        store.add_entry(event_id, rider.rider_id, first_bib + n, local_group="Cat 4")
        store.add_race_entry(race.race_id, rider.rider_id)
        riders.append(rider.rider_id)
    s = LiveRace(store, race.race_id)
    for rid in riders:
        assert s.click(rid).ok
    assert s.state == "provisional"
    return [f"Lane {name.split()[0]}{n:02d}" for n in range(count)]


def _pages_of(drawn, names):
    return [d["page"] for d in drawn if d["text"] in names]


@pytest.fixture
def full_width(monkeypatch):
    """Every race at the page's full width, for the tests of the one-column table."""
    monkeypatch.setattr(pdf_mod, "TWO_COLUMN_MIN", 10**6)


def test_a_race_with_no_result_prints_one_line_and_no_tag(store, event, tmp_path, drawn):
    event_id, ids = event
    race = store.add_race(event_id, "Chase F", "chase", rules=R.placings_rules().to_dict())
    for bib in (1, 2, 3, 4):
        store.add_race_entry(race.race_id, ids[bib])
    s = LiveRace(store, race.race_id)
    assert s.act(ids[4], "dnf").ok
    assert s.state == "running"
    write_results_pdf(store, event_id, tmp_path / "none.pdf")
    texts = [d["text"] for d in drawn]
    assert "Chase F" in texts
    [line] = [d for d in drawn if d["text"] == "No result yet"]
    assert line["size"] == table.REST.size
    for absent in ("IN PROGRESS", "PROVISIONAL", "DNP", "DNF", "Ada Wren"):
        assert absent not in texts


def test_a_race_part_scored_keeps_the_tag_and_the_standings(store, event, tmp_path, drawn):
    event_id, ids = event
    rules = R.SprintPointsRules(sprint_count=3)
    race = store.add_race(event_id, "Points G", "points", rules=rules.to_dict())
    for bib in (1, 2, 3):
        store.add_race_entry(race.race_id, ids[bib])
    s = LiveRace(store, race.race_id)
    assert s.click(ids[2]).ok and s.click(ids[1]).ok and s.record_sprint().ok
    assert s.state == "running"
    write_results_pdf(store, event_id, tmp_path / "part.pdf")
    texts = [d["text"] for d in drawn]
    assert "IN PROGRESS" in texts and "No result yet" not in texts
    assert texts.index("Zoe Łukasik") < texts.index("Ada Wren")


def test_a_race_ended_with_its_results_standing_says_so_once(store, event, tmp_path, drawn):
    """USAC 2M6: a Points Race stopped after Sprint 2 of 4 prints its two
    sprints and says the race ended after them in the gray line, beside the state;
    the rules line still names the race's four sprints."""
    from madtracker.export.summary import build_summary, state_line

    event_id, ids = event
    rules = R.SprintPointsRules(sprint_count=4)
    race = store.add_race(event_id, "Points H", "points", rules=rules.to_dict())
    for bib in (1, 2, 3):
        store.add_race_entry(race.race_id, ids[bib])
    s = LiveRace(store, race.race_id)
    for bibs in ((2, 1), (1, 3)):
        for bib in bibs:
            assert s.click(ids[bib]).ok
        assert s.record_sprint().ok
    assert s.end_race().ok
    summary = build_summary(store, store.race(race.race_id))
    assert summary.ended_after == 2 and summary.sprint_count == 2
    assert all(len(row.sprint_points) == 2 for row in summary.rows)
    assert summary.rules_line.startswith("4 sprints, ")
    ended = store.race(race.race_id)
    assert state_line(ended, tagged=True, ended_after=2).startswith("Race ended after 2 sprints")
    assert state_line(ended, ended_after=2).startswith("Provisional, race ended after 2 sprints")
    write_results_pdf(store, event_id, tmp_path / "ended.pdf")
    lines = [d["text"] for d in drawn if "Race ended" in d["text"]]
    assert len(lines) == 1 and "Race ended after 2 sprints" in lines[0]
    assert "PROVISIONAL" in [d["text"] for d in drawn]


def test_a_shortened_race_prints_the_count_ridden_and_says_it_was_shortened(
    store, event, tmp_path, drawn
):
    """USAC 1G4(b): set for 4 sprints and shortened to 3, the sheet's rules
    line and table have the three sprints ridden, and the gray line names
    both counts once, beside the state."""
    from madtracker.export.summary import build_summary, state_line

    event_id, ids = event
    rules = R.SprintPointsRules(sprint_count=4)
    race = store.add_race(event_id, "Points S", "points", rules=rules.to_dict())
    for bib in (1, 2, 3):
        store.add_race_entry(race.race_id, ids[bib])
    s = LiveRace(store, race.race_id)
    for bibs in ((2, 1), (1, 3)):
        for bib in bibs:
            assert s.click(ids[bib]).ok
        assert s.record_sprint().ok
    assert s.shorten_race(3).ok
    for bib in (3, 2, 1):
        assert s.click(ids[bib]).ok
    summary = build_summary(store, store.race(race.race_id))
    assert summary.shortened == (4, 3) and summary.ended_after is None
    assert summary.sprint_count == 3 and summary.sprints_run == frozenset({1, 2, 3})
    assert all(len(row.sprint_points) == 3 for row in summary.rows)
    assert summary.rules_line.startswith("3 sprints, 5-3-2-1, double points for the last sprint")
    done = store.race(race.race_id)
    assert state_line(done, shortened=(4, 3)).startswith(
        "Provisional, race shortened from 4 to 3 sprints, announced "
    )
    assert state_line(done, tagged=True, shortened=(4, 3)).startswith(
        "Race shortened from 4 to 3 sprints, announced "
    )
    write_results_pdf(store, event_id, tmp_path / "shortened.pdf")
    lines = [d["text"] for d in drawn if "shortened" in d["text"]]
    assert len(lines) == 1 and "Race shortened from 4 to 3 sprints" in lines[0]


def test_a_race_that_fits_a_page_is_never_split(store, event, tmp_path, drawn, full_width):
    event_id, _ = event
    _field_race(store, event_id, "Alpha race", 12, 100)
    second = _field_race(store, event_id, "Bravo race", 8, 200)
    write_results_pdf(store, event_id, tmp_path / "fresh.pdf")
    assert set(_pages_of(drawn, second)) == {2}
    assert not any("(continued)" in d["text"] for d in drawn)


def test_a_split_race_keeps_four_rows_on_each_page(store, event, tmp_path, drawn, full_width):
    event_id, _ = event
    # 17 rows: page 1 has room for 14, which would leave 3 alone on page 2.
    names = _field_race(store, event_id, "Charlie race", 17, 300)
    write_results_pdf(store, event_id, tmp_path / "split.pdf")
    pages = _pages_of(drawn, names)
    assert len(pages) == 17 and len(set(pages)) == 2
    assert all(pages.count(p) >= table.MIN_ROWS for p in set(pages))
    assert pages == sorted(pages)
    assert any(d["text"] == "Charlie race (continued)" for d in drawn)


def test_long_team_and_madison_names_wrap_rather_than_cut(store, event, tmp_path, drawn):
    # Two teams cut to the same "Red Extremely..." would read as one.
    event_id, ids = event
    rules = R.SprintPointsRules(sprint_count=2, scored_unit="team")
    race = store.add_race(
        event_id, "Madison of the Longest Evening", "madison", rules=rules.to_dict()
    )
    teams = []
    for name, (a, b) in (
        ("Red Extremely Long Team One", (1, 2)),
        ("Red Extremely Long Team Two", (3, 4)),
    ):
        for bib in (a, b):
            store.add_race_entry(race.race_id, ids[bib])
        team = store.add_team(race.race_id, name, color="Red")
        store.add_team_member(team.team_id, ids[a])
        store.add_team_member(team.team_id, ids[b])
        teams.append(team.team_id)
    s = LiveRace(store, race.race_id)
    assert s.click(teams[0]).ok and s.click(teams[1]).ok
    assert s.record_sprint().ok
    assert s.click(teams[1]).ok and s.click(teams[0]).ok
    write_results_pdf(store, event_id, tmp_path / "wrap.pdf")
    texts = [d["text"] for d in drawn]
    assert any(t.endswith("One") for t in texts) and any(t.endswith("Two") for t in texts)
    assert not any(pdf_mod.ELLIPSIS in t for t in texts)
    for d in drawn:
        if "{nb}" not in d["text"]:
            assert d["width"] <= d["w"] - 2 * d["margin"] + 0.01, d


def test_a_one_race_pdf_holds_that_race_alone(store, event, seeded, tmp_path, drawn):
    """Through the night the announcer wants one race as it concludes."""
    out = write_results_pdf(store, event[0], tmp_path / "one.pdf", races=[seeded["mad"]])
    assert out.read_bytes().startswith(b"%PDF")
    texts = [d["text"] for d in drawn]
    assert "Madison C" in texts
    for other in ("Chase A", "Points B", "Elimination D"):
        assert other not in texts
    assert {d["page"] for d in drawn} == {1}


def test_a_pdf_of_a_race_from_another_event_is_refused(store, event, seeded, tmp_path):
    with pytest.raises(ValueError):
        write_results_pdf(store, event[0], tmp_path / "x.pdf", races=[9999])


@pytest.fixture
def doc(monkeypatch):
    """The document the sheet was drawn with, kept for measuring after it is written."""
    kept = []
    original = pdf_mod._tabular_figures

    def keep(pdf):
        kept.append(pdf)
        original(pdf)

    monkeypatch.setattr(pdf_mod, "_tabular_figures", keep)
    return kept


def test_figures_are_tabular_so_columns_line_up(store, event, seeded, tmp_path, doc):
    data = write_results_pdf(store, event[0], tmp_path / "t.pdf").read_bytes()
    [pdf] = doc
    assert pdf.text_shaping is not None and pdf.text_shaping["use_shaping_engine"]
    # Inter's default 1 is narrower than its 7; the tabular ones match.
    # Measured through the document, so it is the width _fit sizes cells by.
    for style in ("", "B", "K"):
        pdf.use(style, 16)
        assert pdf.get_string_width("1111") == pytest.approx(pdf.get_string_width("7777"))
    assert b"pdfaid:part" in data and b"<pdfaid:conformance>B" in data.replace(b'"', b"")


def test_a_remembered_width_is_kept_per_face_and_size(store, event, seeded, tmp_path, doc):
    write_results_pdf(store, event[0], tmp_path / "w.pdf")
    [pdf] = doc
    seen = {}
    for style in ("", "B", "K"):
        for size in (10, 16):
            pdf.use(style, size)
            width = pdf.get_string_width("Avery Quinn")
            # The same as fpdf2 measures it, not a width kept for another face or size.
            assert width == pytest.approx(super(pdf_mod._Doc, pdf).get_string_width("Avery Quinn"))
            seen[style, size] = width
    assert len(set(seen.values())) == len(seen)


def test_a_large_logo_is_embedded_at_print_size_with_its_alpha(store, event, seeded, tmp_path):
    from io import BytesIO

    from PIL import Image

    from madtracker.control import venue

    big = BytesIO()
    Image.new("RGBA", (2400, 2400), (255, 255, 255, 0)).save(big, "PNG")
    venue.set_logo(store, big.getvalue())
    data = write_results_pdf(store, event[0], tmp_path / "l.pdf").read_bytes()
    heights = [
        int(h)
        for d in re.findall(rb" obj\s*<<((?:(?!stream).)*?)>>\s*stream", data, re.S)
        if b"/Subtype /Image" in d
        for h in re.findall(rb"/Height (\d+)", d)
    ]
    # The band's logo height at 300 dpi, for the image and its soft mask.
    target = round((pdf_mod.BAND_H - 2 * pdf_mod.BAND_PAD) / 25.4 * pdf_mod.LOGO_DPI)
    assert heights and all(h == target for h in heights)
    assert b"/SMask" in data
    assert b"pdfaid:part" in data and b"<pdfaid:conformance>B" in data.replace(b'"', b"")


def test_without_uharfbuzz_the_sheet_still_writes(store, event, seeded, tmp_path, monkeypatch, doc):
    # A None entry in sys.modules makes the import fail, as a bundle missing it would.
    monkeypatch.setitem(sys.modules, "uharfbuzz", None)
    data = write_results_pdf(store, event[0], tmp_path / "u.pdf").read_bytes()
    [pdf] = doc
    assert pdf.text_shaping is None
    assert data.startswith(b"%PDF") and b"pdfaid:part" in data


def test_a_chase_with_a_lap_prints_a_laps_column_and_one_without_does_not(
    store, event, tmp_path, drawn
):
    event_id, ids = event

    def chase(name, bibs):
        race = store.add_race(event_id, name, "chase", rules=R.placings_rules().to_dict())
        for bib in bibs:
            store.add_race_entry(race.race_id, ids[bib])
        return LiveRace(store, race.race_id)

    s = chase("Chase Even", [1, 2])
    assert s.click(ids[1]).ok and s.click(ids[2]).ok
    s = chase("Chase Lapped", [1, 2, 3])
    assert s.act(ids[3], "lap_gained").ok
    for bib in (1, 2, 3):
        assert s.click(ids[bib]).ok
    write_results_pdf(store, event_id, tmp_path / "laps.pdf")
    texts = [d["text"] for d in drawn]
    even = texts[texts.index("Chase Even") : texts.index("Chase Lapped")]
    assert "Laps" not in even
    lapped = texts[texts.index("Chase Lapped") :]
    assert "Laps" in lapped and "+1" in lapped


def test_an_elimination_dnf_prints_its_place_with_the_reason(store, event, tmp_path, drawn):
    """Two out, a DNF, then the final. The DNF
    rider is out at that moment and placed 3rd (USAC 2E4(d)), so the sheet
    reads 1, 2, 3, 4, 5 with "Did not finish" beside the third name, and
    the CSV row says 3, never a DNF in the Place column and a hole at 3rd."""
    from madtracker.export.summary import build_summary

    event_id, ids = event
    rider = store.add_rider("Ines", "Halvorsen")
    store.add_entry(event_id, rider.rider_id, 5, local_group="Cat 3")
    ids[5] = rider.rider_id
    race = store.add_race(
        event_id, "Elimination F", "elimination", rules=R.elimination_rules().to_dict()
    )
    for bib in (1, 2, 3, 4, 5):
        store.add_race_entry(race.race_id, ids[bib])
    s = LiveRace(store, race.race_id)
    for bib in (1, 2):
        assert s.click(ids[bib]).ok
    assert s.act(ids[3], "dnf").ok
    # Two left: the winner's click is the final sprint, the other is 2nd.
    assert s.click(ids[4]).ok
    assert s.state == "provisional"

    rows = build_summary(store, store.race(race.race_id)).rows
    assert [(r.place, r.riders[0].bib) for r in rows] == [
        ("1", 4),
        ("2", 5),
        ("3", 3),
        ("4", 2),
        ("5", 1),
    ]
    assert [r.note for r in rows] == ["", "", "Did not finish", "", ""]
    assert all(r.is_finisher for r in rows)

    write_results_pdf(store, event_id, tmp_path / "e.pdf", races=[race.race_id])
    texts = [d["text"] for d in drawn]
    assert "DNF" not in texts
    assert texts.index("Bo Tran") < texts.index("Did not finish") < texts.index("Zoe Łukasik")


def test_every_page_after_the_first_carries_a_running_header(store, event, tmp_path, drawn):
    event_id, _ = event
    for i, name in enumerate(("Chase One", "Chase Two", "Chase Three")):
        _field_race(store, event_id, name, 24, 100 + i * 30)
    write_results_pdf(store, event_id, tmp_path / "long.pdf")
    pages = {d["page"] for d in drawn}
    assert len(pages) >= 3
    # The band names the event on page one, the running header on the rest.
    assert {d["page"] for d in drawn if d["text"] == "Friday Night Test"} == pages


def test_a_win_and_out_line_says_which_lap_winner_takes_first():
    """A reverse race reads the same clicks the other way, so the sheet names the direction."""
    from madtracker.export.summary import rules_line

    assert rules_line(R.win_and_out_rules(places=3)) == "3 places, the first lap's winner takes 1st"
    assert rules_line(R.win_and_out_rules(places=5, direction="reverse")) == (
        "5 places, the last lap's winner takes 1st"
    )


def test_a_name_the_font_cannot_draw_prints_a_mark_and_is_reported(store, event, tmp_path, texts):
    from madtracker.control.race import LiveRace

    event_id, ids = event
    store.update_rider(ids[1], first_name="\u5c71\u7530", last_name="\u7f8e\u54b2")
    race = store.add_race(event_id, "Chase", "chase", rules=R.placings_rules().to_dict())
    for bib in (1, 2):
        store.add_race_entry(race.race_id, ids[bib])
    live = LiveRace(store, race.race_id)
    for bib in (1, 2):
        assert live.click(ids[bib]).ok
    missing: list[str] = []
    write_results_pdf(store, event_id, tmp_path / "r.pdf", unprintable=missing)
    # Inter has no CJK: the cell shows a "?" for what it lacks, never a blank,
    # and the export names the rider so the scorer can write it in.
    assert missing == ["\u5c71\u7530 \u7f8e\u54b2"]
    assert any(t == "? ?" for t in texts)


def test_a_rider_out_of_the_finish_prints_a_numbered_place_with_the_mishap_beside(
    store, event, tmp_path, drawn
):
    """USAC 2M7(b), 2M8(a): Bo's free laps ran into the last kilometer. He is
    placed on his sprint-1 points, 3rd, with "Out of the finish (mishap)"
    beside the name on the sheet, and the USAC CSV gives him the number 3,
    not DNF."""
    import csv

    from madtracker.export import write_usac_csv
    from madtracker.export.summary import build_summary

    event_id, ids = event
    race = store.add_race(
        event_id, "Points G", "points", rules=R.SprintPointsRules(sprint_count=2).to_dict()
    )
    for bib in (1, 2, 3, 4):
        store.add_race_entry(race.race_id, ids[bib])
    s = LiveRace(store, race.race_id)
    for bib in (3, 1):
        assert s.click(ids[bib]).ok
    assert s.record_sprint().ok
    assert s.act(ids[3], "out_of_finish").ok
    for bib in (1, 4, 2):
        assert s.click(ids[bib]).ok
    assert s.state == "provisional"

    rows = build_summary(store, store.race(race.race_id)).rows
    # Ada 3 + 10, Cy 6 in the doubled final, Bo the 5 of sprint 1, Zoe 4.
    assert [(r.place, r.riders[0].bib, r.note) for r in rows] == [
        ("1", 1, ""),
        ("2", 4, ""),
        ("3", 3, "Out of the finish (mishap)"),
        ("4", 2, ""),
    ]
    assert all(r.is_finisher and r.status is None for r in rows)

    write_results_pdf(store, event_id, tmp_path / "g.pdf", races=[race.race_id])
    texts = [d["text"] for d in drawn]
    assert "DNF" not in texts and "DNP" not in texts
    assert texts.index("Bo Tran") < texts.index("Out of the finish (mishap)")
    assert texts.index("Out of the finish (mishap)") < texts.index("Zoe Łukasik")

    out = tmp_path / "g.csv"
    write_usac_csv(store, event_id, out, races=[race.race_id])
    body = list(csv.reader(out.read_bytes().decode("utf-8").split("\r\n")[1:-1]))
    assert [(r[8], r[9]) for r in body] == [
        ("Wren", "1"),
        ("Park", "2"),
        ("Tran", "3"),
        ("Łukasik", "4"),
    ]


@pytest.mark.parametrize("fmt", ["chase", "tempo"])
def test_a_withdrawn_rider_prints_a_numbered_place_with_withdrawn_beside(
    store, event, tmp_path, drawn, fmt
):
    """USAC 2O3(e): in the omnium's Scratch Race and Tempo Race a rider two
    laps down is withdrawn and takes the next place after the finishers.
    The sheet prints the number with "Withdrawn" beside the name, and the
    USAC CSV gives the number, not DNF."""
    import csv

    from madtracker.export import write_usac_csv
    from madtracker.export.summary import build_summary

    event_id, ids = event
    rules = R.placings_rules() if fmt == "chase" else R.tempo_rules(sprint_count=2)
    race = store.add_race(event_id, "Omnium W", fmt, rules=rules.to_dict())
    for bib in (1, 2, 3, 4):
        store.add_race_entry(race.race_id, ids[bib])
    s = LiveRace(store, race.race_id)
    if fmt == "tempo":
        assert s.click(ids[3]).ok and s.record_sprint().ok
    assert s.act(ids[3], "withdrawn").ok
    for bib in (1, 4, 2):
        assert s.click(ids[bib]).ok
    assert s.state == "provisional"

    rows = build_summary(store, store.race(race.race_id)).rows
    assert [(r.place, r.riders[0].bib, r.note) for r in rows] == [
        ("1", 1, ""),
        ("2", 4, ""),
        ("3", 2, ""),
        ("4", 3, "Withdrawn"),
    ]
    assert all(r.is_finisher and r.status is None for r in rows)

    write_results_pdf(store, event_id, tmp_path / "w.pdf", races=[race.race_id])
    texts = [d["text"] for d in drawn]
    assert "DNF" not in texts and "DNP" not in texts
    assert texts.index("Bo Tran") < texts.index("Withdrawn")

    out = tmp_path / "w.csv"
    write_usac_csv(store, event_id, out, races=[race.race_id])
    body = list(csv.reader(out.read_bytes().decode("utf-8").split("\r\n")[1:-1]))
    assert [(r[8], r[9]) for r in body] == [
        ("Wren", "1"),
        ("Park", "2"),
        ("Łukasik", "3"),
        ("Tran", "4"),
    ]


def test_a_hyphen_in_a_name_is_not_widened_to_a_figure(store, event, scratch, tmp_path, doc):
    """Inter's tnum widens the hyphen too, so names never read "Maximiliana - Josephine"."""
    write_results_pdf(store, event[0], tmp_path / "h.pdf")
    [pdf] = doc
    pdf.use("", 16)
    hyphen = pdf.get_string_width("Ada-Bo") - pdf.get_string_width("AdaBo")
    figure = pdf.get_string_width("1")
    assert hyphen < figure * 0.8
    # Numbers keep their tabular figures.
    assert pdf.get_string_width("11") == pytest.approx(pdf.get_string_width("77"))


def _logo(w, h):
    from io import BytesIO

    from PIL import Image

    out = BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(out, "PNG")
    return out.getvalue()


def test_a_crowded_band_never_drops_the_venue(store, event, seeded, tmp_path, drawn):
    from madtracker.control import venue

    event_id, _ = event
    venue.set_logo(store, _logo(600, 600))
    store.update_event(
        event_id,
        name="Pro Series Race Night Number Twelve of the Winter Season Presented by Sponsors",
        series="Winter Track League 2026-27 Championship Series of Southeast Michigan"
        " and Northwest Ohio",
    )
    place = "Riverside Track Arena at the Lakeport County Fairgrounds Velodrome Lakeport Michigan"
    write_results_pdf(store, event_id, tmp_path / "b.pdf", venue_name=place)
    band = " ".join(d["text"] for d in drawn if d["page"] == 1 and d["y"] < 40)
    assert place in band


def test_a_very_wide_logo_leaves_the_event_name_room(store, event, seeded, tmp_path, drawn):
    from madtracker.control import venue

    venue.set_logo(store, _logo(4000, 200))
    write_results_pdf(store, event[0], tmp_path / "w.pdf")
    assert "Friday Night Test" in [d["text"] for d in drawn]
    for d in drawn:
        assert d["w"] > 0, d
        if "{nb}" not in d["text"]:
            assert d["width"] <= d["w"] - 2 * d["margin"] + 0.01, d


def test_the_core_font_fallback_reports_its_marks_and_cuts_with_dots(
    store, event, scratch, tmp_path, monkeypatch, drawn
):
    monkeypatch.setattr(pdf_mod, "find_font", lambda: None)
    event_id, ids = event
    # More than the name's three lines hold, so its last line is cut.
    store.update_rider(ids[5], first_name=LONG_FIRST * 6, last_name=LONG_LAST * 4)
    missing: list[str] = []
    write_results_pdf(store, event_id, tmp_path / "c.pdf", unprintable=missing)
    # Zoe's stroked L prints as "?" in Helvetica; the export names her.
    assert "Zoe \u0141ukasik" in missing
    texts = [d["text"] for d in drawn]
    # A cut name ends in dots, not in the "?" that marks a missing letter.
    start = next(d for d in drawn if d["text"].startswith(LONG_FIRST))
    lines = _name_lines(drawn, start)
    assert len(lines) == table.NAME_LINES and lines[-1].endswith("...")
    assert not any(t.endswith(pdf_mod.ELLIPSIS) for t in texts)


def test_a_cut_race_name_keeps_continued_on_its_next_page(
    store, event, tmp_path, drawn, full_width
):
    """The suffix goes on after the cut, so a long name keeps it."""
    event_id, _ = event
    name = "Charlie " + "Extraordinarily Long Sponsored Race Name " * 6
    _field_race(store, event_id, name.strip(), 23, 300)
    write_results_pdf(store, event_id, tmp_path / "cut.pdf")
    later = [d["text"] for d in drawn if d["page"] == 2 and d["size"] >= pdf_mod.HEAD_MIN_PT]
    assert any(t.endswith("… (continued)") for t in later), later


def test_a_logo_pillow_refuses_prints_the_venue_name_instead(
    store, event, seeded, tmp_path, monkeypatch, drawn
):
    """A very tall logo passes Settings (it caps the width); Pillow's bomb check never raises."""
    from PIL import Image

    from madtracker.control import venue
    from madtracker.export.program import write_program_pdf

    venue.set_logo(store, _logo(600, 600))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    write_results_pdf(store, event[0], tmp_path / "r.pdf", venue_name="Test Oval")
    write_program_pdf(store, event[0], tmp_path / "p.pdf")
    assert "Test Oval" in [d["text"] for d in drawn if d["page"] == 1]


def test_a_points_penalty_prints_its_own_column_and_no_penalty_prints_none(
    store, event, seeded, tmp_path, drawn
):
    """The row builder carries the ruling (USAC 8D5(b)) and the sheet shows
    a Penalty column only on a race that has one, beside the total it
    came off, so the arithmetic can be checked."""
    event_id, ids = event
    write_results_pdf(store, event_id, tmp_path / "before.pdf")
    texts = [d["text"] for d in drawn]
    assert "Penalty" not in texts
    drawn.clear()
    points = next(r for r in store.races(event_id) if r.name == "Points B")
    s = LiveRace(store, points.race_id)
    assert s.review(ids[1], "points_penalty:5").ok and s.state == "provisional"
    write_results_pdf(store, event_id, tmp_path / "after.pdf")
    texts = [d["text"] for d in drawn]
    section = texts[texts.index("Points B") : texts.index("Madison C")]
    assert "Penalty" in section and "\u22125" in section
    assert "Penalty" not in texts[: texts.index("Points B")]
    assert "Penalty" not in texts[texts.index("Madison C") :]
    # The sprints, Laps, Penalty, Total, in that order across the page, as
    # the screens run; read from this race's own section, since the other
    # races' Laps headings sit where Penalty does here.
    own = drawn[texts.index("Points B") : texts.index("Madison C")]
    heads = {d["text"]: d for d in own if d["text"] in ("S2", "Penalty", "Total", "Laps")}
    assert heads["S2"]["x"] < heads["Laps"]["x"] < heads["Penalty"]["x"] < heads["Total"]["x"]


def _row_of(drawn, name):
    """The cells on the line of ``name``'s row, left to right."""
    y = next(d["y"] for d in drawn if d["text"] == name)
    return sorted((d for d in drawn if abs(d["y"] - y) < 0.01), key=lambda d: d["x"])


def _section(drawn, start, stop=None):
    texts = [d["text"] for d in drawn]
    end = texts.index(stop) if stop else len(drawn)
    return drawn[texts.index(start) : end]


def test_a_points_race_prints_each_sprint_and_the_columns_add_up(
    store, event, seeded, tmp_path, drawn
):
    """Sprint 1 awards 5-3-2 to Ada, Zoe, and Bo; the finish is the doubled
    final, 10-6-4 to Ada, Bo, and Zoe; Ada's lap is worth 20. S1 + S2 +
    the lap at the gray line's value is each rider's Total."""
    event_id, _ = event
    write_results_pdf(store, event_id, tmp_path / "sprints.pdf")
    own = _section(drawn, "Points B", "Madison C")
    heads = {d["text"]: d for d in own if d["text"] in ("S1", "S2", "Laps", "Rider")}
    assert heads["Rider"]["x"] < heads["S1"]["x"] < heads["S2"]["x"] < heads["Laps"]["x"]
    assert "S3" not in [d["text"] for d in own]
    by_name = {}
    for name in ("Ada Wren", "Bo Tran", "Zoe Łukasik"):
        row = _row_of(own, name)
        figures = [d["text"] for d in row if d["x"] >= heads["S1"]["x"]]
        by_name[name] = figures
    assert by_name["Ada Wren"] == ["5", "10", "+1", "35"]
    assert by_name["Bo Tran"] == ["2", "6", "8"]
    assert by_name["Zoe Łukasik"] == ["3", "4", "7"]
    # The sprint figures print at the working size, right-aligned under their headers.
    for d in _row_of(own, "Ada Wren"):
        if d["text"] in ("5", "10"):
            assert d["size"] == pdf_mod.WORKING_PT
            head = heads["S1"] if d["text"] == "5" else heads["S2"]
            assert abs(d["x"] + d["w"] - (head["x"] + head["w"])) < 0.01


def test_a_madison_prints_its_sprint_figures_on_the_team_line(
    store, event, seeded, tmp_path, drawn
):
    event_id, _ = event
    write_results_pdf(store, event_id, tmp_path / "madison.pdf")
    own = _section(drawn, "Madison C")
    head = next(d for d in own if d["text"] == "S1")
    red = _row_of(own, "Red")
    assert [d["text"] for d in red if d["x"] >= head["x"]] == ["5", "6", "11"]
    blue = _row_of(own, "Blue")
    assert [d["text"] for d in blue if d["x"] >= head["x"]] == ["3", "10", "13"]
    # The riders sit beside the team's name, left of the figures.
    rider = next(d for d in own if d["text"] == "Ada Wren")
    name = next(d for d in red if d["text"] == "Red")
    assert name["x"] + name["width"] < rider["x"] < next(d for d in red if d["text"] == "5")["x"]


def test_a_sprint_not_yet_run_and_a_sprint_scoring_nothing_print_blank(
    store, event, tmp_path, drawn
):
    """One sprint of three recorded: S1 shows who scored, S2 and S3 are
    blank for everyone, and a rider who scored nothing in S1 has no 0."""
    event_id, ids = event
    rules = R.SprintPointsRules(sprint_count=3)
    race = store.add_race(event_id, "Points P", "points", rules=rules.to_dict())
    for bib in (1, 2, 3, 4):
        store.add_race_entry(race.race_id, ids[bib])
    s = LiveRace(store, race.race_id)
    for bib in (1, 2, 3):
        assert s.click(ids[bib]).ok
    assert s.record_sprint().ok
    write_results_pdf(store, event_id, tmp_path / "part.pdf", races=[race.race_id])
    heads = {d["text"]: d for d in drawn if d["text"] in ("S1", "S2", "S3", "Laps")}
    assert heads["S1"]["x"] < heads["S2"]["x"] < heads["S3"]["x"] < heads["Laps"]["x"]
    for d in drawn:
        if d["size"] == pdf_mod.WORKING_PT and d["text"]:
            assert abs(d["x"] - heads["S1"]["x"]) < 0.01, d
    assert [d["text"] for d in _row_of(drawn, "Ada Wren") if d["x"] >= heads["S1"]["x"]] == [
        "5",
        "5",
    ]
    assert [d["text"] for d in _row_of(drawn, "Cy Park") if d["x"] >= heads["S1"]["x"]] == ["0"]
    assert "0" not in [d["text"] for d in drawn if d["size"] == pdf_mod.WORKING_PT]


def test_too_many_sprints_fold_to_one_sprints_column_with_the_sum(store, event, tmp_path, drawn):
    """A Tempo Race with a sprint every lap: thirty columns do not fit beside
    a readable name, so one Sprints column holds each rider's sum."""
    event_id, ids = event
    rules = R.tempo_rules(sprint_count=30)
    race = store.add_race(event_id, "Tempo T", "tempo", rules=rules.to_dict())
    for bib in (1, 2, 3, 4):
        store.add_race_entry(race.race_id, ids[bib])
    s = LiveRace(store, race.race_id)
    for _ in range(29):
        assert s.click(ids[1]).ok and s.record_sprint().ok
    for bib in (2, 1, 3, 4):
        assert s.click(ids[bib]).ok
    write_results_pdf(store, event_id, tmp_path / "tempo.pdf", races=[race.race_id])
    texts = [d["text"] for d in drawn]
    assert "Sprints" in texts and "S1" not in texts and "S30" not in texts
    head = next(d for d in drawn if d["text"] == "Sprints")
    assert [d["text"] for d in _row_of(drawn, "Ada Wren") if d["x"] >= head["x"]] == ["29", "29"]
    assert [d["text"] for d in _row_of(drawn, "Zoe Łukasik") if d["x"] >= head["x"]] == ["1", "1"]
    rider = next(d for d in drawn if d["text"] == "Rider")
    assert rider["w"] >= pdf_mod.NAME_MIN
    for d in drawn:
        if "{nb}" not in d["text"]:
            assert d["width"] <= d["w"] - 2 * d["margin"] + 0.01, d
            assert d["x"] + d["w"] <= d["page_w"] + 0.01, d


def test_thirteen_sprints_fit_a_madison_as_columns_shrunk_toward_the_smallest_size(
    store, event, tmp_path, drawn
):
    event_id, ids = event
    rules = R.SprintPointsRules(sprint_count=13, scored_unit="team")
    race = store.add_race(event_id, "Madison Thirteen", "madison", rules=rules.to_dict())
    teams = []
    for color, (a, b) in (("Red", (1, 2)), ("Blue", (3, 4))):
        for bib in (a, b):
            store.add_race_entry(race.race_id, ids[bib])
        team = store.add_team(race.race_id, color, color=color)
        store.add_team_member(team.team_id, ids[a])
        store.add_team_member(team.team_id, ids[b])
        teams.append(team.team_id)
    s = LiveRace(store, race.race_id)
    for _ in range(12):
        assert s.click(teams[0]).ok and s.click(teams[1]).ok and s.record_sprint().ok
    assert s.click(teams[0]).ok and s.click(teams[1]).ok
    write_results_pdf(store, event_id, tmp_path / "thirteen.pdf", races=[race.race_id])
    heads = [d for d in drawn if re.fullmatch(r"S\d+", d["text"])]
    assert [d["text"] for d in heads] == [f"S{i}" for i in range(1, 14)]
    assert all(a["x"] < b["x"] for a, b in zip(heads, heads[1:], strict=False))
    figures = [d for d in drawn if d["text"] in ("5", "10") and d["size"] < table.REST.size]
    assert figures and all(pdf_mod.SPRINT_MIN_PT <= d["size"] < pdf_mod.WORKING_PT for d in figures)
    # The team's name and its riders keep NAME_MIN after the bib's room.
    team_head = next(d for d in drawn if d["text"] == "Team")
    room = heads[0]["x"] - pdf_mod.SPRINT_GAP - team_head["x"] - table.BIB_W - table.BIB_GAP
    assert room >= pdf_mod.NAME_MIN - 0.01
    for d in drawn:
        if "{nb}" not in d["text"]:
            assert d["width"] <= d["w"] - 2 * d["margin"] + 0.01, d


def test_three_digit_sprint_points_widen_the_columns(store, event, tmp_path, drawn):
    event_id, ids = event
    rules = R.SprintPointsRules(sprint_count=2, points_by_sprint=((100, 50), (100, 50)))
    race = store.add_race(event_id, "Points H", "points", rules=rules.to_dict())
    for bib in (1, 2, 3):
        store.add_race_entry(race.race_id, ids[bib])
    s = LiveRace(store, race.race_id)
    assert s.click(ids[1]).ok and s.click(ids[2]).ok and s.record_sprint().ok
    for bib in (1, 2, 3):
        assert s.click(ids[bib]).ok
    write_results_pdf(store, event_id, tmp_path / "hundred.pdf", races=[race.race_id])
    cells = [d for d in drawn if d["text"] == "100" and d["size"] == pdf_mod.WORKING_PT]
    assert len(cells) == 2
    for d in cells:
        assert d["width"] <= d["w"] - 2 * d["margin"] + 0.01, d
    head = next(d for d in drawn if d["text"] == "S1")
    row = [d["text"] for d in _row_of(drawn, "Ada Wren") if d["x"] >= head["x"]]
    assert row == ["100", "100", "200"]


def test_a_finish_order_race_and_an_elimination_print_no_sprint_column(
    store, event, seeded, tmp_path, drawn
):
    event_id, _ = event
    write_results_pdf(store, event_id, tmp_path / "none.pdf")
    chase = [d["text"] for d in _section(drawn, "Chase A", "Points B")]
    assert "Laps" not in chase and "S1" not in chase and "Sprints" not in chase
    drawn.clear()
    write_results_pdf(store, event_id, tmp_path / "elim.pdf", races=[seeded["elim"]])
    elim = [d["text"] for d in drawn]
    assert "Rider" in elim and "S1" not in elim and "Sprints" not in elim


def test_a_lap_not_counted_prints_beside_the_name(store, event, tmp_path, drawn):
    """The struck lap leaves no figure, so the sheet
    notes the ruling beside the name, as it notes a mishap."""
    event_id, ids = event
    race = store.add_race(event_id, "Chase L", "chase", rules=R.placings_rules().to_dict())
    for bib in (1, 2, 3):
        store.add_race_entry(race.race_id, ids[bib])
    s = LiveRace(store, race.race_id)
    assert s.act(ids[2], "lap_gained").ok and s.act(ids[2], "lap_not_counted").ok
    for bib in (1, 2, 3):
        assert s.click(ids[bib]).ok
    write_results_pdf(store, event_id, tmp_path / "lap.pdf", races=[race.race_id])
    texts = [d["text"] for d in drawn]
    assert "Lap not counted" in texts


def test_a_penalty_only_on_a_dnf_rider_prints_no_penalty_column(
    store, event, seeded, tmp_path, drawn
):
    """A status row prints no figures, so a column opened for it alone
    would be a heading over nothing."""
    event_id, ids = event
    points = next(r for r in store.races(event_id) if r.name == "Points B")
    s = LiveRace(store, points.race_id)
    assert s.review(ids[1], "points_penalty:3").ok
    assert s.review(ids[1], "dq").ok
    write_results_pdf(store, event_id, tmp_path / "out.pdf")
    texts = [d["text"] for d in drawn]
    assert "Penalty" not in texts and "\u22123" not in texts


def test_prints_answers_as_the_sheet_draws():
    """The check a typed name is given is the sheet's own: a name that prints
    whole there passes, and one the sheet would mark with "?" does not."""
    from madtracker.export.glyphs import prints

    for text in ("Maya Petrakis", "Zoë Ångström", "Пётр Иванов", "Ελένη", "R&B <3", ""):
        assert prints(text), text
    # A joiner draws nothing on its own and is dropped, not marked.
    assert prints("Café‍")
    for text in ("王小明", "김민준", "محمد", "Team 🚴"):
        assert not prints(text), text


def test_the_window_starts_without_the_pdf_writer():
    """fpdf2 costs about 200 ms to import; the window and its name fields ask
    only ``glyphs.prints``, so the writer loads when a sheet is made."""
    import os
    import subprocess
    import sys

    code = (
        "import sys; import madtracker.ui.window; "
        "from madtracker.export.glyphs import prints; prints('Maya'); "
        "print(sorted(m for m in ('fpdf', 'fontTools') if m in sys.modules))"
    )
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
    )
    assert out.stdout.strip() == "[]"


@pytest.mark.parametrize(
    "first", ["madtracker.export.table", "madtracker.export.pdf", "madtracker.export.standings_pdf"]
)
def test_the_sheet_modules_import_in_any_order(first):
    """pdf and table import each other; a fresh interpreter that loads either one
    first still gets a working pair."""
    import os
    import subprocess
    import sys

    code = (
        f"import {first}; from madtracker.export import pdf, table, standings_pdf; "
        "print(pdf.T is table and table.P is pdf)"
    )
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
    )
    assert out.stdout.strip() == "True"


# ----- two columns for a finish order


def _status_race(store, event_id, name, placed, statuses=(), first_bib=500, names=None):
    """A scratch race of ``placed`` riders in bib order, then one rider per status code.

    Returns the names in the order the sheet must print them.
    """
    race = store.add_race(event_id, name, "scratch", rules=R.placings_rules().to_dict())
    count = placed + len(statuses)
    shown = names or [f"Lane {name.split()[0]}{n:02d}" for n in range(count)]
    ids = []
    for n, full in enumerate(shown):
        first, last = full.split(" ", 1)
        rider = store.add_rider(first, last)
        store.add_entry(event_id, rider.rider_id, first_bib + n, local_group="Cat 4")
        store.add_race_entry(race.race_id, rider.rider_id)
        ids.append(rider.rider_id)
    s = LiveRace(store, race.race_id)
    for rid, code in zip(ids[placed:], statuses, strict=True):
        assert s.act(rid, code).ok
    for rid in ids[:placed]:
        assert s.click(rid).ok
    assert s.state == "provisional"
    return shown


def _headers(drawn, page=None):
    return [d for d in drawn if d["text"] == "Place" and page in (None, d["page"])]


def _reading_order(drawn, names):
    """The cells of ``names`` in reading order: by page, then left column, then down."""
    cells = [d for d in drawn if d["text"] in names]
    return sorted(cells, key=lambda d: (d["page"], d["x"] > d["page_w"] / 2, d["y"]))


def test_a_ten_placed_scratch_prints_in_two_columns(store, event, tmp_path, drawn):
    event_id, _ = event
    names = _field_race(store, event_id, "Delta race", 10, 400)
    write_results_pdf(store, event_id, tmp_path / "two.pdf")
    cells = _names(drawn, *names)
    left = [d for d in cells if d["x"] < d["page_w"] / 2]
    right = [d for d in cells if d["x"] > d["page_w"] / 2]
    assert left and right and len(cells) == 10
    heads = _headers(drawn)
    assert len(heads) == 2 and heads[0]["y"] == heads[1]["y"]
    # The podium at the top of the left column, larger than the rest.
    podium = [d for d in left if d["size"] == table.TOP.size]
    assert [d["text"] for d in podium] == names[:3]
    assert min(d["y"] for d in left) == podium[0]["y"]
    # Balanced, the left column the longer: it holds the podium and more.
    assert len(left) >= len(right)


def test_a_seven_placed_scratch_keeps_the_full_width(store, event, tmp_path, drawn):
    event_id, _ = event
    names = _field_race(store, event_id, "Echo race", 7, 400)
    write_results_pdf(store, event_id, tmp_path / "one.pdf")
    assert len(_headers(drawn)) == 1
    assert all(d["x"] < d["page_w"] / 2 for d in _names(drawn, *names))


def test_a_points_race_of_ten_keeps_the_full_width(store, event, tmp_path, drawn):
    event_id, _ = event
    rules = R.SprintPointsRules(sprint_count=2)
    race = store.add_race(event_id, "Points Ten", "points", rules=rules.to_dict())
    ids = []
    for n in range(10):
        rider = store.add_rider("Lane", f"Points{n:02d}")
        store.add_entry(event_id, rider.rider_id, 600 + n, local_group="Cat 4")
        store.add_race_entry(race.race_id, rider.rider_id)
        ids.append(rider.rider_id)
    s = LiveRace(store, race.race_id)
    for rid in ids[:3]:
        assert s.click(rid).ok
    assert s.record_sprint().ok
    for rid in ids:
        assert s.click(rid).ok
    assert s.state == "provisional"
    write_results_pdf(store, event_id, tmp_path / "points.pdf", races=[race.race_id])
    assert len(_headers(drawn)) == 1
    assert "Total" in [d["text"] for d in drawn]


def test_a_column_too_narrow_for_a_readable_name_keeps_the_full_width(
    store, event, tmp_path, drawn, monkeypatch
):
    monkeypatch.setattr(pdf_mod, "NAME_MIN", 200.0)
    event_id, _ = event
    _field_race(store, event_id, "Foxtrot race", 10, 400)
    write_results_pdf(store, event_id, tmp_path / "narrow.pdf")
    assert len(_headers(drawn)) == 1


def test_twenty_placed_with_statuses_read_down_then_across(store, event, tmp_path, drawn):
    event_id, _ = event
    names = _status_race(store, event_id, "Golf race", 20, ("dnf", "dns", "dq"))
    write_results_pdf(store, event_id, tmp_path / "twenty.pdf")
    cells = _reading_order(drawn, names)
    assert sorted(d["text"] for d in cells) == sorted(names)
    order = [d["text"] for d in cells]
    assert order[:20] == names[:20]
    assert set(order[20:]) == set(names[20:])
    assert all(d["size"] == table.STATUS.size for d in cells[20:])
    assert {d["x"] > d["page_w"] / 2 for d in cells} == {False, True}


def test_a_two_column_race_longer_than_a_page_continues_with_its_headers(
    store, event, tmp_path, drawn
):
    event_id, _ = event
    names = _status_race(store, event_id, "Hotel race", 70, ("dnf", "dns"))
    write_results_pdf(store, event_id, tmp_path / "long.pdf")
    cells = _reading_order(drawn, names)
    assert [d["text"] for d in cells][:70] == names[:70]
    pages = [d["page"] for d in cells]
    assert len(set(pages)) >= 2
    assert all(pages.count(p) >= table.MIN_ROWS for p in set(pages))
    for page in set(pages):
        assert len(_headers(drawn, page)) == 2
    for page in sorted(set(pages))[1:]:
        assert any(d["text"] == "Hotel race (continued)" and d["page"] == page for d in drawn)


def test_a_two_column_race_after_another_keeps_four_rows_on_a_page(store, event, tmp_path, drawn):
    """Whatever is above it, no page holds fewer than MIN_ROWS of a race."""
    event_id, _ = event
    for i, count in enumerate((9, 13, 30, 11, 47, 8)):
        names = _status_race(store, event_id, f"Race{i} race", count, ("dnf",), 400 + 100 * i)
    write_results_pdf(store, event_id, tmp_path / "many.pdf")
    for i in range(6):
        names = [d["text"] for d in drawn if d["text"].startswith(f"Lane Race{i}")]
        pages = [d["page"] for d in drawn if d["text"] in names]
        assert all(pages.count(p) >= min(len(pages), table.MIN_ROWS) for p in set(pages)), i
    assert all(d["y"] + d["h"] <= d["page_h"] + 0.01 for d in drawn)


LONG_NAMES = [
    "Maximiliana-Josephine Konstantinopoulou-Abernathy",
    "Christopher-James Quartermaine-Whitcombe",
    "Isadora-Mae Richardson-Oduya Fitzwilliam",
    "Wilhelmina Ivanova-Petrenko Castellanos-Reyes",
]


def test_long_names_in_a_column_wrap_and_are_never_cut(store, event, tmp_path, drawn):
    event_id, _ = event
    names = [LONG_NAMES[n % len(LONG_NAMES)] + f" {n:02d}" for n in range(12)]
    _status_race(store, event_id, "India race", 12, names=names)
    write_results_pdf(store, event_id, tmp_path / "names.pdf")
    assert len(_headers(drawn)) == 2
    texts = [d["text"] for d in drawn]
    assert not any(t.endswith((pdf_mod.ELLIPSIS, "...")) for t in texts)
    for name in names:
        whole = name.replace(" ", "")
        starts = [d for d in drawn if d["text"] and name.startswith(d["text"])]
        assert any("".join(_name_lines(drawn, d)).replace(" ", "") == whole for d in starts), name
    for d in drawn:
        assert d["width"] <= d["w"] - 2 * d["margin"] + 0.01, d


def test_two_columns_balance_with_the_left_the_longest():
    heights, gaps = [11.0] * 3 + [8.0] * 7, [0.0] * 10
    assert table.split(heights, gaps, 0, 10, 200, 2, balance=True) == [5, 5]
    assert table.split(heights, gaps, 0, 10, 200, 2, balance=False) == [10, 0]
    # A status row's gap is not drawn where the row starts a column, so
    # ten rows fill two columns of 50 exactly.
    heights, gaps = [10.0] * 5 + [15.0] + [10.0] * 4, [0.0] * 5 + [5.0] + [0.0] * 4
    assert table.pages(50, 50, heights, gaps, 2) == [10]
    assert table.split(heights, gaps, 0, 10, 50, 2, balance=True) == [5, 5]


def test_the_total_column_is_as_wide_as_the_race_s_widest_total(store, event, seeded):
    """A race of small totals gives the name column the room a fixed Total would
    take; the widest total still prints whole, and never under its header."""
    from madtracker.export.summary import build_summary

    event_id, _ = event
    race = next(r for r in store.races(event_id) if r.name == "Points B")
    summary = build_summary(store, race)
    pdf = pdf_mod.new_doc(
        title="x", subtitle="", logo=None, venue="", footer_text="", doc_title="x", landscape=True
    )
    pdf.add_page()
    cols = pdf_mod._columns(pdf, summary)
    totals = [pdf_mod.format_number(r.total_points) for r in summary.rows if r.is_finisher]
    widest = max(totals, key=len)
    assert cols.points[1] == pytest.approx(table.total_width(pdf, totals))
    assert cols.points[1] >= table.figure_w(pdf, widest, table.TOP.size, "B")
    assert cols.points[1] >= table.figure_w(pdf, "Total", table.HEADER_PT, "B")
    assert table.total_width(pdf, ["5"]) < table.total_width(pdf, ["-120"])
    pdf.close_fonts()


def test_a_hyphenated_name_too_long_for_its_line_breaks_after_the_hyphen():
    pdf = pdf_mod.new_doc(
        title="x", subtitle="", logo=None, venue="", footer_text="", doc_title="x", landscape=True
    )
    pdf.add_page()
    pdf.use("B", 18)
    room = pdf.get_string_width("Ivanova-Petren")
    lines, _ = pdf_mod._wrap_lines(pdf, "Ivanova-Petrenko", room + 2 * pdf.c_margin, "B", 18, 18, 3)
    assert lines == ["Ivanova-", "Petrenko"]
    pdf.close_fonts()


def test_a_logo_s_transparent_edges_are_trimmed_so_its_air_in_the_band_is_even():
    from io import BytesIO

    from PIL import Image

    im = Image.new("RGBA", (300, 100), (0, 0, 0, 0))
    im.paste((255, 255, 255, 255), (60, 10, 240, 90))
    raw = BytesIO()
    im.save(raw, "PNG")
    out = pdf_mod._print_logo(raw.getvalue())
    with Image.open(BytesIO(out)) as trimmed:
        assert trimmed.size == (180, 80)
        assert trimmed.getchannel("A").getbbox() == (0, 0, 180, 80)
