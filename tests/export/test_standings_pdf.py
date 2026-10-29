"""The standings PDF: a multi-race standings on the results sheet's header.

Stores are built as ``tests/control/test_multi_race.py`` builds them: each
Madison is scored through ``LiveRace`` to land on the totals a test
names, the tens as laps at 10 a lap and the rest as one sprint's points.
"""

import re
from dataclasses import replace

import pytest

from madtracker.control import multi_race
from madtracker.control.demo import DEMO_STANDINGS, seed_demo
from madtracker.control.race import LiveRace
from madtracker.export import pdf as pdf_mod
from madtracker.export.standings_pdf import suggested_standings_name, write_standings_pdf
from madtracker.scoring import rules as R

FIRST = ["Ada", "Bram", "Cleo", "Dov", "Esme", "Finn", "Gus", "Hana"]
LAST = ["Arden", "Birch", "Corso", "Dunmore", "Ellery"]
COLORS = ["Red", "Blue", "Green", "White", "Purple", "Yellow", "Black", "Silver", "Orange",
          "Teal", "Pink", "Gold", "Navy", "Lime", "Maroon", "Brown"]  # fmt: skip


def riders(store, n):
    return [
        store.add_rider(FIRST[i % len(FIRST)], LAST[i // len(FIRST)]).rider_id for i in range(n)
    ]


def night(store, ids, name, date):
    event = store.add_event(name, date, venue="Test Velodrome")
    for i, rider_id in enumerate(ids):
        store.add_entry(event.event_id, rider_id, i + 1)
    return event.event_id


def madison(store, event_id, teams, totals, *, group="Pro", name="Pro Madison", final=True):
    """A Madison whose teams finish on ``totals`` (name -> total); returns its race_id."""
    points = {team: total % 10 for team, total in totals.items()}
    order = sorted(totals, key=lambda team: -points[team])
    rules = R.SprintPointsRules(
        points_by_sprint=(tuple(points[t] for t in order),),
        lap_gained_points=10,
        lap_lost_points=10,
        scored_unit="team",
    )
    race = store.add_race(event_id, name, "madison", group_label=group, rules=rules.to_dict())
    made = {}
    for team, pair in teams.items():
        for rider_id in pair:
            store.add_race_entry(race.race_id, rider_id)
        t = store.add_team(race.race_id, team, color=team)
        for rider_id in pair:
            store.add_team_member(t.team_id, rider_id)
        made[team] = t.team_id
    s = LiveRace(store, race.race_id)
    for team, total in totals.items():
        laps = (total - points[team]) // 10
        for _ in range(abs(laps)):
            assert s.act(made[team], "lap_gained" if laps > 0 else "lap_lost").ok
    for team in order:
        assert s.click(made[team]).ok
    if final:
        assert s.mark_final().ok
    return race.race_id


def standings(store, event_ids, name="Weekend Omnium"):
    made = store.add_standings(name)
    store.update_standings(made.standings_id, event_ids=list(event_ids))
    return made.standings_id


def wide(store, teams=12, races=4):
    """``teams`` pairs over ``races`` Madisons on two nights; returns the standings id."""
    ids = riders(store, 2 * teams)
    pairs = {COLORS[i]: (ids[2 * i], ids[2 * i + 1]) for i in range(teams)}
    nights = [
        night(store, ids, "Day One", "2026-10-16"),
        night(store, ids, "Day Two", "2026-10-17"),
    ]
    for k in range(races):
        # Totals spread from -39 up, so the table carries a negative total.
        totals = {c: (i * 7 + k * 3) % 50 - 39 + (k + i) % 9 for i, c in enumerate(pairs)}
        madison(store, nights[k % 2], pairs, totals, name=f"Madison {k + 1}")
    return standings(store, nights, name="Pro Winter Omnium")


@pytest.fixture
def texts(drawn):
    return lambda: [d["text"] for d in drawn]


def test_the_demo_writes_a_pdfa_sheet_with_its_tables_and_notes(store, tmp_path, drawn):
    tonight = seed_demo(store, "2026-10-18")
    (made,) = [s for s in store.list_standings() if s.name == DEMO_STANDINGS]
    out = write_standings_pdf(store, made.standings_id, tmp_path / "s.pdf")
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and b"pdfaid:part" in data
    assert b"<pdfaid:conformance>B" in data.replace(b'"', b"")
    texts = [d["text"] for d in drawn]
    assert texts.count(DEMO_STANDINGS) >= 2, "the band and the title"
    assert "Group A" in texts and "PROVISIONAL" not in texts and "FINAL" not in texts
    assert "Total" in texts
    table = multi_race.compute(store, made.standings_id)
    for row in table.groups[0].rows:
        assert row.team in texts
        assert pdf_mod.format_number(row.total) in texts
    assert "2026-Oct-17" in texts, "the race column is headed by its night's date"
    # Under the tables, each night, then what its races did for the standings.
    assert "Demo Opening Night (2026-Oct-17)" in texts
    assert "Counted: 8 Mile Madison, 4 Mile Madison (Group A)" in texts
    assert "Demo Race Night (2026-Oct-18)" in texts
    assert "Not yet raced: 8 Mile Madison, 4 Mile Madison (Group A)" in texts
    assert not any(t.startswith("Not counted") for t in texts), "only when there are any"
    # The heading's gray lines: the kind and its count, the events, how it scores.
    assert "Team Omnium by Points: 2 of 4 Madisons raced over 2 events" in texts
    assert any(t.startswith("Events: Demo Opening Night (2026-Oct-17)") for t in texts)
    assert "Each team's Madison totals are summed." in texts
    assert store.event(tonight).name in " ".join(texts)


def test_a_team_that_rode_one_night_is_left_off_the_sheet(store, tmp_path, drawn):
    ids = riders(store, 6)
    friday = night(store, ids, "Friday", "2026-10-16")
    saturday = night(store, ids, "Saturday", "2026-10-17")
    red, blue, teal = (ids[0], ids[1]), (ids[2], ids[3]), (ids[4], ids[5])
    madison(store, friday, {"Red": red, "Blue": blue, "Teal": teal},
            {"Red": 26, "Blue": 50, "Teal": -12})  # fmt: skip
    madison(store, saturday, {"Red": red, "Blue": blue}, {"Red": 42, "Blue": 0})
    sid = standings(store, [friday, saturday])
    write_standings_pdf(store, sid, tmp_path / "a.pdf")
    by_text = {d["text"]: d for d in drawn}
    # Teal rode Friday alone: not on the sheet, and
    # its minus with it. Red's figures and total print in the board's minus
    # form when negative; here Red's 26 and 42 sum to 68.
    assert "Teal" not in by_text and "−12" not in by_text
    assert "3" not in by_text, "two teams, two places"
    # Blue's 0 on Saturday is a race ridden for nothing, and prints.
    blue_row = by_text["Blue"]["y"]
    assert "0" in [d["text"] for d in drawn if abs(d["y"] - blue_row) < 0.01]
    # Each race column's figures sit right-aligned under its header.
    dates = [d for d in drawn if d["text"] in ("2026-Oct-16", "2026-Oct-17")]
    assert len(dates) == 2 and dates[0]["x"] < dates[1]["x"]
    assert "FINAL" in by_text and "PROVISIONAL" not in by_text


def test_a_long_table_breaks_over_pages_and_repeats_its_header(store, tmp_path, drawn):
    # Sixteen teams over four races: more than a page holds.
    sid = wide(store, teams=16, races=4)
    write_standings_pdf(store, sid, tmp_path / "w.pdf")
    pages = {d["page"] for d in drawn}
    assert len(pages) >= 2
    headed = {d["page"] for d in drawn if d["text"] == "Total"}
    rows = {d["page"] for d in drawn if d["text"] in COLORS}
    assert len(rows) >= 2, "the table itself spans pages"
    assert rows <= headed, "every page of the table has its header row"
    assert any(d["text"] == "Pro (continued)" for d in drawn)
    for d in drawn:
        if "{nb}" in d["text"]:
            continue
        assert d["width"] <= d["w"] - 2 * d["margin"] + 0.01, d
        bottom = d["page_h"] - pdf_mod.MARGIN - pdf_mod.FOOTER_H
        if d["y"] < bottom:  # the footer's own line sits under the body
            assert d["y"] + d["h"] <= bottom + 0.01, d


def test_many_races_squeeze_the_team_column_not_the_figures(store, tmp_path, drawn):
    sid = wide(store, teams=4, races=8)
    write_standings_pdf(store, sid, tmp_path / "m.pdf")
    figures = [d for d in drawn if d["text"].lstrip("−").isdigit() and d["size"] < 20]
    assert figures
    for d in figures:
        assert d["width"] <= d["w"] - 2 * d["margin"] + 0.01, d
    # The widest figure a race column must hold fits every race column.
    races = {(round(d["x"], 2), round(d["w"], 2)) for d in drawn if d["text"].startswith("Madison")}
    assert len(races) == 8


def test_the_suggested_name_leads_with_the_latest_night(store):
    seed_demo(store, "2026-10-18")
    (made,) = [s for s in store.list_standings() if s.name == DEMO_STANDINGS]
    table = multi_race.compute(store, made.standings_id)
    assert suggested_standings_name(table) == "2026-10-18 - Demo 2 Day Omnium - Standings.pdf"
    store.update_standings(made.standings_id, name="A/B: Omnium?")
    table = multi_race.compute(store, made.standings_id)
    assert suggested_standings_name(table) == "2026-10-18 - A B  Omnium - Standings.pdf"


def test_a_name_the_font_cannot_draw_prints_a_mark_and_is_reported(store, tmp_path, drawn):
    ids = riders(store, 4)
    store.update_rider(ids[0], first_name="山田", last_name="美咲")
    friday = night(store, ids, "Friday", "2026-10-16")
    madison(store, friday, {"Red": (ids[0], ids[1]), "Blue": (ids[2], ids[3])},
            {"Red": 12, "Blue": 4})  # fmt: skip
    missing: list[str] = []
    write_standings_pdf(store, standings(store, [friday]), tmp_path / "u.pdf", unprintable=missing)
    assert missing == ["山田 美咲"]
    # Each rider on a line of their own, as the dialog's preview lists a pair.
    assert "? ?" in [d["text"] for d in drawn]
    assert any(d["text"].startswith("Bram") for d in drawn)


def test_the_core_font_fallback_writes_a_plain_pdf(store, tmp_path, monkeypatch, drawn):
    monkeypatch.setattr(pdf_mod, "find_font", lambda: None)
    ids = riders(store, 4)
    store.update_rider(ids[2], last_name="Łukasik")
    friday = night(store, ids, "Friday", "2026-10-16")
    madison(store, friday, {"Red": (ids[0], ids[1]), "Blue": (ids[2], ids[3])},
            {"Red": 12, "Blue": -24})  # fmt: skip
    missing: list[str] = []
    out = write_standings_pdf(
        store, standings(store, [friday]), tmp_path / "c.pdf", unprintable=missing
    )
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and b"pdfaid" not in data
    texts = [d["text"] for d in drawn]
    assert "-24" in texts, "the minus has a Latin-1 stand-in"
    assert missing == ["Cleo Łukasik"]


def test_no_events_ticked_still_writes(store, tmp_path, drawn):
    sid = store.add_standings("Empty Season").standings_id
    out = write_standings_pdf(store, sid, tmp_path / "e.pdf")
    assert out.read_bytes().startswith(b"%PDF")
    texts = [d["text"] for d in drawn]
    assert not any(t.startswith("Counted") for t in texts) and "No events ticked" in texts


def test_a_status_row_follows_the_ranked_rows_with_its_code_and_no_figures(
    store, tmp_path, monkeypatch, drawn
):
    # No kind marks a team out today (the Team Omnium sums every night), so
    # the table is handed in as a kind that does would compute it.
    import madtracker.export.standings_pdf as sheet

    column = multi_race.RaceColumn(1, 1, "Friday", "2026-10-16", "Madison", "Pro", "final", False)
    rows = [
        multi_race.MultiRaceRow(1, "Red", "red", ["Ada Arden", "Bram Arden"], [12], 12, ""),
        multi_race.MultiRaceRow(None, "Blue", "blue", ["Cleo Arden", "Dov Arden"], [7], 7, "DNF"),
    ]
    table = multi_race.MultiRaceTable(
        1, "Season", "team_omnium", "Team Omnium by Points", "detail", "final",
        [multi_race.GroupTable("Pro", [column], rows)], [], [], [(1, "Friday", "2026-10-16")],
    )  # fmt: skip
    monkeypatch.setattr(sheet, "compute", lambda store, sid: table)
    store.add_event("Friday", "2026-10-16")
    write_standings_pdf(store, 1, tmp_path / "s.pdf")
    texts = [d["text"] for d in drawn]
    assert texts.index("Red") < texts.index("DNF") < texts.index("Blue")
    blue = next(d for d in drawn if d["text"] == "Blue")
    assert "7" not in [d["text"] for d in drawn if abs(d["y"] - blue["y"]) < 0.01]


def test_a_team_omnium_by_place_prints_its_table_and_place_points(store, tmp_path, drawn):
    """The place kind's detail names its table, and each race cell holds the place points."""
    ids = riders(store, 6)
    friday = night(store, ids, "Friday", "2026-10-16")
    pairs = {"Red": (ids[0], ids[1]), "Blue": (ids[2], ids[3]), "Teal": (ids[4], ids[5])}
    madison(store, friday, pairs, {"Red": 26, "Blue": 50, "Teal": 13})
    made = store.add_standings("Place Omnium", kind=multi_race.PLACES)
    store.update_standings(made.standings_id, event_ids=[friday])
    write_standings_pdf(store, made.standings_id, tmp_path / "p.pdf")
    texts = [d["text"] for d in drawn]
    assert "Team Omnium by Place: 1 Madison raced over 1 event" in texts
    assert (
        "Each team scores points for its place in each Madison, 7-5-3-2-1, and the points are summed."
    ) in texts
    # Blue won (7), Red second (5), Teal third (3): the cells are the place
    # points, not the Madison totals.
    blue_row = next(d["y"] for d in drawn if d["text"] == "Blue")
    assert "7" in [d["text"] for d in drawn if abs(d["y"] - blue_row) < 0.01]
    assert "50" not in texts and "26" not in texts


def scratch(store, event_id, order, *, group="Cat 3", name="Scratch"):
    """A Scratch Race finished in ``order`` (rider ids), marked final; returns its race_id."""
    race = store.add_race(
        event_id, name, "chase", group_label=group, rules=R.placings_rules().to_dict()
    )
    for rider_id in order:
        store.add_race_entry(race.race_id, rider_id)
    s = LiveRace(store, race.race_id)
    for rider_id in order:
        assert s.click(rider_id).ok
    assert s.mark_final().ok
    return race.race_id


def test_a_rider_omnium_prints_bib_and_rider_columns_and_no_swatch(store, tmp_path, drawn):
    ids = riders(store, 3)
    friday = night(store, ids, "Friday", "2026-10-16")
    saturday = night(store, ids, "Saturday", "2026-10-17")
    scratch(store, friday, [ids[0], ids[1], ids[2]])
    scratch(store, saturday, [ids[1], ids[0], ids[2]])
    made = store.add_standings("Cat 3 Omnium", kind=multi_race.OMNIUM)
    store.update_standings(made.standings_id, event_ids=[friday, saturday])
    write_standings_pdf(store, made.standings_id, tmp_path / "r.pdf")
    texts = [d["text"] for d in drawn]
    assert "Bib" in texts and "Rider" in texts and "Team" not in texts
    assert "Omnium by Place: 2 races raced over 2 events" in texts
    assert (
        "Each rider scores points for their place in each race, 7-5-3-2-1, and the points are summed."
    ) in texts
    ada = next(d for d in drawn if d["text"] == "Ada Arden")
    row = [d["text"] for d in drawn if abs(d["y"] - ada["y"]) < 0.01]
    # Place, bib, name, the two races' place points, the total: level with
    # Bram on 12 and on firsts, Ada is 2nd on the last race (USAC 2B19(e)).
    assert row == ["2", "1", "Ada Arden", "7", "5", "12"]


def test_a_four_digit_bib_prints_whole_on_a_podium_row(store, tmp_path, drawn):
    """The roster takes bibs up to 9999; the Bib column holds four digits at the podium size."""
    ids = riders(store, 3)
    friday = store.add_event("Friday", "2026-10-16").event_id
    for rider_id, bib in zip(ids, (8888, 9999, 1111), strict=True):
        store.add_entry(friday, rider_id, bib)
    scratch(store, friday, ids)
    made = store.add_standings("Cat 3 Omnium", kind=multi_race.OMNIUM)
    store.update_standings(made.standings_id, event_ids=[friday])
    write_standings_pdf(store, made.standings_id, tmp_path / "b.pdf")
    texts = [d["text"] for d in drawn]
    for bib in ("8888", "9999", "1111"):
        assert bib in texts, bib
    assert not any(t.endswith(pdf_mod.ELLIPSIS) for t in texts)


def one_race_nights(store, count):
    """An Omnium by Place over ``count`` nights of one Scratch Race each; returns its id."""
    ids = riders(store, 4)
    nights = [night(store, ids, f"Night {k + 1}", f"2026-09-{k + 1:02d}") for k in range(count)]
    for k, event_id in enumerate(nights):
        scratch(store, event_id, [ids[(i + k) % 4] for i in range(4)])
    made = store.add_standings("Season", kind=multi_race.OMNIUM)
    store.update_standings(made.standings_id, event_ids=nights)
    return made.standings_id


def test_a_date_too_wide_for_its_night_prints_in_the_short_form(store, tmp_path, drawn):
    """Over a single race column the full date would be cut; the table heads its nights Sep-01."""
    write_standings_pdf(store, one_race_nights(store, 12), tmp_path / "d.pdf")
    texts = [d["text"] for d in drawn]
    assert [f"Sep-{k:02d}" for k in range(1, 13)] == [
        t for t in texts if re.fullmatch(r"Sep-\d\d", t)
    ]
    assert not any(t.startswith("2026-Sep") or t.endswith(pdf_mod.ELLIPSIS) for t in texts)


def test_a_date_too_wide_even_short_prints_its_month_over_its_day(store, tmp_path, drawn):
    import madtracker.export.standings_pdf as sheet

    made = one_race_nights(store, 4)
    (group,) = multi_race.compute(store, made).groups
    pdf = pdf_mod.new_doc(
        title="x", subtitle="", logo=None, venue="", footer_text="", doc_title="x", landscape=True
    )
    pdf.add_page()
    cols = sheet._columns(pdf, group)
    # Columns narrower than "Sep-04" at the least date size.
    narrow = replace(cols, races=tuple((x, 6.0) for x, _ in cols.races))
    assert sheet._dates(pdf, group, narrow) == [("Sep", f"{k:02d}") for k in range(1, 5)]
    assert sheet._dates(pdf, group, cols) == [(f"2026-Sep-{k:02d}",) for k in range(1, 5)]
    pdf.close_fonts()


def test_a_four_race_refusal_prints_where_the_tables_would_be(store, tmp_path, drawn):
    ids = riders(store, 3)
    friday = night(store, ids, "Friday", "2026-10-16")
    scratch(store, friday, [ids[0], ids[1], ids[2]])
    made = store.add_standings("Omnium", kind=multi_race.FOUR_RACE)
    store.update_standings(made.standings_id, event_ids=[friday])
    write_standings_pdf(store, made.standings_id, tmp_path / "f.pdf")
    texts = [d["text"] for d in drawn]
    refusal = multi_race.compute(store, made.standings_id).refusal
    # The rule wraps over the sheet's lines, then the night's heading and
    # its group's line, each a line of its own.
    assert refusal.nights == (
        ("Friday (2026-Oct-16)", ("Cat 3: no Tempo Race, no Elimination, no Points Race",)),
    )
    assert any(t.startswith("A Four-Race Omnium needs") for t in texts)
    heading = texts.index("Friday (2026-Oct-16)")
    assert texts[heading - 1].endswith("event.")
    assert texts[heading + 1] == "Cat 3: no Tempo Race, no Elimination, no Points Race"
    # No table, and nothing counts, so no "Counted" line either.
    assert "Place" not in texts and not any(t.startswith("Counted") for t in texts)


def test_a_season_of_races_prints_in_bands_with_the_names_whole(store, tmp_path, drawn):
    """Past what fits beside a readable name column, the table repeats as bands
    of races, each with the place, the name, and the total; nothing prints
    over the Bib and Place columns."""
    import madtracker.export.standings_pdf as sheet

    ids = riders(store, 4)
    nights = [night(store, ids, f"Night {k}", f"2026-10-{10 + k:02d}") for k in range(8)]
    # Forty races: the wide page holds about 22 beside a readable name
    # column, fewer here since the totals run to three digits and every
    # race column is sized to the group's widest figure.
    for k in range(40):
        order = [ids[(i + k) % 4] for i in range(4)]
        scratch(store, nights[k % 8], order, name=f"Scratch {k + 1}")
    made = store.add_standings("Season", kind=multi_race.OMNIUM)
    store.update_standings(made.standings_id, event_ids=nights)
    table = multi_race.compute(store, made.standings_id)
    (group,) = table.groups
    pdf = pdf_mod.new_doc(
        title="x", subtitle="", logo=None, venue="", footer_text="", doc_title="x", landscape=True
    )
    bands = sheet._bands(pdf, group)
    assert len(bands) > 1 and sum(len(b.columns) for b in bands) == 40
    for band in bands:
        cols = sheet._columns(pdf, band)
        assert cols.team[1] >= sheet.TEAM_FLOOR
        assert cols.races[0][0] >= cols.team[0] + cols.team[1] - 0.01
        assert all(len(r.per_race) == len(band.columns) for r in band.rows)
    pdf.close_fonts()
    write_standings_pdf(store, made.standings_id, tmp_path / "season.pdf")
    texts = [d["text"] for d in drawn]
    assert f"Races 1 to {len(bands[0].columns)} of 40" in texts
    # Whole or wrapped onto two lines, the name is in every band.
    assert sum(1 for t in texts if t in ("Ada Arden", "Ada")) == len(bands)


def test_a_still_racing_race_is_listed_under_its_own_heading(store, tmp_path, drawn):
    ids = riders(store, 3)
    friday = night(store, ids, "Friday", "2026-10-16")
    scratch(store, friday, ids)
    race = store.add_race(
        friday, "Elim", "elimination", group_label="Cat 3", rules=R.elimination_rules().to_dict()
    )
    for rider_id in ids:
        store.add_race_entry(race.race_id, rider_id)
    assert LiveRace(store, race.race_id).click(ids[2]).ok
    made = store.add_standings("Omnium", kind=multi_race.OMNIUM)
    store.update_standings(made.standings_id, event_ids=[friday])
    write_standings_pdf(store, made.standings_id, tmp_path / "r.pdf")
    texts = [d["text"] for d in drawn]
    assert any(t.startswith("Still racing: ") for t in texts)
    assert "Omnium by Place: 1 of 2 races raced over 1 event" in texts


def test_an_omnium_penalty_prints_in_a_penalty_column(store, tmp_path, drawn):
    import madtracker.export.standings_pdf as sheet

    ids = riders(store, 3)
    friday = night(store, ids, "Friday", "2026-10-16")
    column = multi_race.RaceColumn(1, 1, "Friday", "2026-10-16", "Scratch", "Cat 3", "final", False)
    rows = [
        multi_race.MultiRaceRow(1, "Ada Arden", None, [], [40], 40, "", bib=1, rider_id=ids[0]),
        multi_race.MultiRaceRow(
            2, "Bram Arden", None, [], [38], -2, "", bib=2, penalty=40, rider_id=ids[1]
        ),
    ]
    table = multi_race.MultiRaceTable(
        1, "Four", "four_race_omnium", "Four-Race Omnium", "detail", "final",
        [multi_race.GroupTable("Cat 3", [column], rows, riders=True)], [], [],
        [(friday, "Friday", "2026-10-16")],
    )  # fmt: skip
    monkeypatch_compute = sheet.compute
    sheet.compute = lambda store, sid: table
    try:
        write_standings_pdf(store, 1, tmp_path / "p.pdf")
    finally:
        sheet.compute = monkeypatch_compute
    texts = [d["text"] for d in drawn]
    assert "Penalty" in texts
    bram = next(d for d in drawn if d["text"] == "Bram Arden")
    row = [d["text"] for d in drawn if abs(d["y"] - bram["y"]) < 0.01]
    assert row == ["2", "2", "Bram Arden", "38", pdf_mod.MINUS + "40", pdf_mod.MINUS + "2"]


def test_a_two_night_four_race_sheet_with_a_penalty_stays_one_table(store, tmp_path, drawn):
    """The venue's case: eight races and one 40-point penalty print as one
    table, not two bands; the penalty column is narrow enough to leave the
    name column its floor."""
    import madtracker.export.standings_pdf as sheet

    ids = riders(store, 4)
    cols = [
        multi_race.RaceColumn(i, 1 + i // 4, "Night", f"2026-10-{16 + i // 4:02d}", n, "Cat 3", "final", False, "chase")
        for i, n in enumerate(["Scratch", "Tempo", "Elimination", "Points"] * 2)
    ]  # fmt: skip
    rows = [
        multi_race.MultiRaceRow(k + 1, f"Rider {k}", None, [], [40 - 2 * k] * 8, 320 - 16 * k, "", bib=k + 1, rider_id=ids[k], penalty=40 if k == 1 else 0)
        for k in range(4)
    ]  # fmt: skip
    group = multi_race.GroupTable("Cat 3", cols, rows, riders=True)
    pdf = pdf_mod.new_doc(
        title="x", subtitle="", logo=None, venue="", footer_text="", doc_title="x", landscape=True
    )
    try:
        assert len(sheet._bands(pdf, group)) == 1
        assert sheet._columns(pdf, group).penalty is not None
    finally:
        pdf.close_fonts()


def test_a_team_s_riders_print_beside_its_name_centered_on_the_block(store, tmp_path, drawn):
    seed_demo(store, "2026-10-18")
    (made,) = [s for s in store.list_standings() if s.name == DEMO_STANDINGS]
    write_standings_pdf(store, made.standings_id, tmp_path / "s.pdf")
    table = multi_race.compute(store, made.standings_id)
    starts = set()
    for row in table.groups[0].rows:
        team = next(d for d in drawn if d["text"] == row.team)
        first, second = (next(d for d in drawn if d["text"] == r) for r in row.riders)
        assert first["x"] == second["x"] > team["x"] + team["width"]
        middle = (first["y"] + second["y"] + second["h"]) / 2
        assert team["y"] + team["h"] / 2 == pytest.approx(middle)
        starts.add(round(first["x"], 3))
    assert len(starts) == 1, "every team's riders start one gap after the widest name"


def season(store, races, *, long_first=None):
    """An Omnium by Place over ``races`` Scratch Races on eight nights, five riders, the
    first always winning (renamed ``long_first`` when given); returns the group's table."""
    ids = riders(store, 5)
    if long_first:
        first, last = long_first
        store.update_rider(ids[0], first_name=first, last_name=last)
    nights = [night(store, ids, f"Night {k}", f"2026-10-{10 + k:02d}") for k in range(8)]
    for k in range(races):
        order = [ids[0], *(ids[1 + (i + k) % 4] for i in range(4))]
        scratch(store, nights[k % 8], order, name=f"Scratch {k + 1}")
    made = store.add_standings("Season", kind=multi_race.OMNIUM)
    store.update_standings(made.standings_id, event_ids=nights)
    return made.standings_id, multi_race.compute(store, made.standings_id).groups[0]


def _doc():
    return pdf_mod.new_doc(
        title="x", subtitle="", logo=None, venue="", footer_text="", doc_title="x", landscape=True
    )


def test_a_race_column_is_sized_by_the_race_figures_and_the_total_by_the_totals(store):
    """Three-digit totals over two-digit place points widen the Total alone."""
    import madtracker.export.standings_pdf as sheet
    from madtracker.export import table

    _, group = season(store, 20)
    totals = [pdf_mod.format_number(r.total) for r in group.rows if not r.status]
    assert max(len(t) for t in totals) == 3 and len(sheet._widest(group)) == 2
    pdf = _doc()
    pdf.add_page()
    cols = sheet._columns(pdf, group)
    assert cols.total[1] >= table.figure_w(pdf, max(totals, key=len), table.TOP.size, "B")
    pdf.close_fonts()


def test_a_long_podium_name_takes_a_third_line_before_it_is_cut(store, tmp_path, drawn):
    import madtracker.export.standings_pdf as sheet

    made, group = season(store, 40, long_first=("Wilhelmina", "Ivanova Petrenko"))
    pdf = _doc()
    (band, *_) = sheet._bands(pdf, group)
    pdf.close_fonts()
    write_standings_pdf(store, made, tmp_path / "long.pdf")
    first = [d for d in drawn if d["text"] in ("Wilhelmina", "Ivanova", "Petrenko")]
    # Each band prints the name on three lines, one word each, nothing cut.
    assert [d["text"] for d in first[:3]] == ["Wilhelmina", "Ivanova", "Petrenko"]
    assert first[0]["y"] < first[1]["y"] < first[2]["y"]
    assert len({round(d["x"], 2) for d in first[:3]}) == 1
    assert not any(d["text"].endswith("...") for d in drawn)
    assert len(band.columns) < 40


def test_a_rider_name_is_bold_on_the_podium_and_regular_below(store):
    """As on the results sheet: the podium's names read first."""
    import madtracker.export.standings_pdf as sheet
    from madtracker.export import table

    _, group = season(store, 4)
    pdf = _doc()
    pdf.add_page()
    cols = sheet._columns(pdf, group)
    styles = [
        (tier, sheet._row_text(pdf, row, cols, tier).rider_style)
        for row, tier in table.ordered(group.rows, lambda r: not r.status)
    ]
    pdf.close_fonts()
    assert [s for t, s in styles if t is table.TOP] == ["B"] * 3
    assert {s for t, s in styles if t is table.REST} == {""}
