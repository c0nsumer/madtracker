"""Standings to board payloads, one test per layout, no widgets."""

from madtracker.board import payloads as P
from madtracker.control import board_feed as bf
from madtracker.control.race import LiveRace
from madtracker.scoring import rules as R

TEAMS = [("Blue", 3, 24), ("Red", 5, 36), ("Orange", 8, 12)]


def live(store, make_race, fmt, bibs, rules, teams=None):
    return LiveRace(store, make_race(fmt, bibs, rules, teams=teams, name="Test race"))


def ids_of(event):
    return event[1]


def clicks(s, ids, *bibs):
    for bib in bibs:
        out = s.click(ids[bib])
        assert out.ok, out.message


def sprint(s, ids, *bibs):
    clicks(s, ids, *bibs)
    assert s.record_sprint().ok


def test_pre_race_lists_the_start_list(store, make_race):
    s = live(store, make_race, "chase", [12, 7, 33], R.placings_rules())
    layout, payload = bf.board_for(s.view())
    assert layout == "pre_race"
    assert isinstance(payload, P.PreRace)
    assert [e.bibs for e in payload.roster] == [["7"], ["12"], ["33"]]
    assert payload.roster[0].names == ["Maya Petrakis"]
    assert payload.header.title == "Test race"
    assert payload.header.status == "Start list"


def test_elimination_remaining_last_out_and_out_earlier(store, make_race, event, house):
    ids = ids_of(event)
    s = live(store, make_race, "elimination", [3, 5, 7, 8, 9], house.elimination())
    clicks(s, ids, 3, 5, 7)
    layout, payload = bf.board_for(s.view())
    assert layout == "elimination"
    assert [e.bibs[0] for e in payload.remaining] == ["8", "9"]
    assert payload.remaining[0].names == ["Tom Kowalczyk"]
    assert payload.last_eliminated.bibs == ["7"]
    assert [e.bibs[0] for e in payload.eliminated] == ["3", "5"]
    assert payload.header.status == "Final sprint"
    clicks(s, ids, 9)
    layout, payload = bf.board_for(s.view())
    assert layout == "finish"
    assert [(p.place, p.entry.bibs[0]) for p in payload.placings] == [
        (1, "9"), (2, "8"), (3, "7"), (4, "5"), (5, "3"),
    ]  # fmt: skip
    assert payload.header.status == "Provisional"


def test_sprint_points_columns_overlay_and_provisional(store, make_race, event, house):
    ids = ids_of(event)
    s = live(store, make_race, "points", [7, 12, 33, 19], house.points(3))
    layout, payload = bf.board_for(s.view())
    assert layout == "pre_race"
    sprint(s, ids, 12, 7, 33)
    assert s.act(ids[19], "lap_gained").ok
    layout, payload = bf.board_for(s.view(), overlay=True)
    assert layout == "sprint_points"
    assert payload.sprint_count == 3
    assert payload.current_sprint == 1
    # The last entry was a lap, not a sprint, so there is no card to show.
    assert payload.sprint_result is None
    rows = {r.entry.bibs[0]: r for r in payload.rows}
    assert rows["12"].sprints == [10, None, None]
    assert rows["19"].laps == 1 and rows["19"].lap_points == 10 and rows["19"].total == 10
    assert payload.header.status == "After Sprint 1 of 3"

    sprint(s, ids, 7, 12)
    layout, payload = bf.board_for(s.view(), overlay=True)
    assert payload.current_sprint == 2
    card = payload.sprint_result
    assert card.number == 2
    assert card.of == 3
    assert [(place, e.bibs[0], pts) for place, e, pts in card.placings] == [
        (1, "7", 10),
        (2, "12", 7),
    ]

    clicks(s, ids, 7, 12, 33, 19)
    layout, payload = bf.board_for(s.view(), overlay=True)
    assert payload.current_sprint == 3
    assert payload.sprint_result.number == 3
    # The finish order is the final sprint; the page words it from number == of.
    assert payload.sprint_result.of == 3
    assert payload.sprint_result.placings[0][2] == 20
    assert payload.header.status == "Provisional"
    assert [r.rank for r in payload.rows] == [1, 2, 3, 4]


def test_a_race_ended_with_its_results_standing_shows_the_sprints_ridden(
    store, make_race, event, house
):
    """USAC 2M6: the board's table stops at the sprints ridden, no empty
    columns for the rest, and no sprint card for the end itself."""
    ids = ids_of(event)
    s = live(store, make_race, "points", [7, 12, 33, 19], house.points(4))
    sprint(s, ids, 12, 7, 33)
    sprint(s, ids, 7, 12)
    assert s.end_race().ok
    layout, payload = bf.board_for(s.view(), overlay=True)
    assert layout == "sprint_points"
    assert payload.sprint_count == 2
    assert payload.sprint_result is None
    rows = {r.entry.bibs[0]: r for r in payload.rows}
    assert rows["12"].sprints == [10, 7] and rows["7"].sprints == [7, 10]
    assert payload.header.status == "Provisional"


def test_a_shortened_race_shows_the_count_it_rides_to(store, make_race, event, house):
    """USAC 1G4(b): set for 4 sprints and shortened to 3, the board shows
    three sprint columns, After Sprint 2 of 3, and the finish's card as
    the final sprint, doubled."""
    ids = ids_of(event)
    s = live(store, make_race, "points", [7, 12, 33, 19], house.points(4))
    sprint(s, ids, 12, 7, 33)
    sprint(s, ids, 7, 12)
    assert s.shorten_race(3).ok
    layout, payload = bf.board_for(s.view())
    assert layout == "sprint_points"
    assert payload.sprint_count == 3
    assert payload.header.status == "After Sprint 2 of 3"
    clicks(s, ids, 33, 7, 12, 19)
    layout, payload = bf.board_for(s.view(), overlay=True)
    assert payload.sprint_count == 3
    assert payload.sprint_result.number == 3 and payload.sprint_result.of == 3
    assert payload.sprint_result.placings[0][2] == 20, "the new final sprint doubles"
    rows = {r.entry.bibs[0]: r for r in payload.rows}
    assert rows["33"].sprints == [5, 0, 20]


def test_madison_rows_carry_team_and_color(store, make_race, house):
    s = live(store, make_race, "madison", [3, 24, 5, 36, 8, 12], house.madison(4), teams=TEAMS)
    teams = {s.name(t): t for t in s.roster.ids}
    assert s.click(teams["Orange"]).ok and s.click(teams["Blue"]).ok and s.record_sprint().ok
    layout, payload = bf.board_for(s.view())
    assert layout == "madison"
    assert payload.sprint_count == 4
    top = payload.rows[0]
    assert top.entry.team == "Orange" and top.entry.color == "orange"
    assert top.entry.bibs == ["8", "12"]
    assert top.sprints == [5, None, None, None]
    assert payload.header.detail == "Madison", "the kind of race, not its numbers (2026-10-11)"


def test_finish_recap_lists_the_placed_and_drops_a_statused_rider(store, make_race, event):
    ids = ids_of(event)
    s = live(store, make_race, "chase", [7, 12, 33, 9], R.placings_rules())
    assert bf.finish(s.view()).placings == [], "nobody placed, nothing to recap"
    assert s.act(ids[9], "dnf").ok
    clicks(s, ids, 33, 7, 12)
    layout, payload = bf.board_for(s.view())
    assert layout == "finish"
    # The board drops a statused rider without comment.
    assert [(p.place, p.entry.bibs[0], p.note) for p in payload.placings] == [
        (1, "33", ""), (2, "7", ""), (3, "12", ""),
    ]  # fmt: skip


def test_finish_recap_notes_a_withdrawn_rider_at_the_place_the_rule_gives(store, make_race, event):
    """USAC 2O3(e), 1M6(d): a withdrawn rider is placed after every finisher,
    the later withdrawn higher, and the recap says why beside the name."""
    ids = ids_of(event)
    s = live(store, make_race, "chase", [7, 12, 33, 9], R.placings_rules())
    assert s.act(ids[9], "withdrawn").ok
    assert s.act(ids[12], "withdrawn").ok
    clicks(s, ids, 33, 7)
    layout, payload = bf.board_for(s.view())
    assert layout == "finish"
    assert [(p.place, p.entry.bibs[0], p.note) for p in payload.placings] == [
        (1, "33", ""), (2, "7", ""), (3, "12", "Withdrawn"), (4, "9", "Withdrawn"),
    ]  # fmt: skip


def test_between_shows_next_race_and_last_result(store, make_race, event):
    ids = ids_of(event)
    done = live(store, make_race, "chase", [7, 12, 33], R.placings_rules())
    clicks(done, ids, 12, 7, 33)
    assert done.mark_final().ok
    nxt = live(store, make_race, "elimination", [3, 5], R.elimination_rules())
    payload = bf.between("Test Race Night", nxt.view(), done.view(), "Race 2 of 2")
    assert payload.header.title == "Test Race Night" and payload.header.status == "Race 2 of 2"
    assert payload.next_title == "Test race"
    assert [e.bibs[0] for e in payload.next_roster] == ["3", "5"]
    assert [p.entry.bibs[0] for p in payload.last_placings] == ["12", "7", "33"]
    assert bf.header(done.view()).status == "Final"
    empty = bf.between("Test Race Night", None, None)
    assert empty.next_title == "Results" and empty.last_placings == []


def test_payloads_coerce_cleanly(store, make_race, event, house):
    ids = ids_of(event)
    s = live(store, make_race, "points", [7, 12], house.points(2))
    sprint(s, ids, 7, 12)
    layout, payload = bf.board_for(s.view(), overlay=True)
    assert P.coerce(P.LAYOUT_PAYLOADS[layout], payload) is payload


# ----- statused riders are absent from every audience layout ----------------


def bibs_on(payload) -> list[str]:
    rows = getattr(payload, "roster", None)
    if rows is None:
        rows = [r.entry for r in getattr(payload, "rows", [])] or [
            p.entry for p in payload.placings
        ]
    return [e.bibs[0] for e in rows]


def test_pre_race_drops_a_dns_in_silence(store, make_race, event):
    ids = ids_of(event)
    s = live(store, make_race, "chase", [12, 7, 33], R.placings_rules())
    assert s.act(ids[7], "dns").ok
    layout, payload = bf.board_for(s.view())
    assert layout == "pre_race" and s.state == "setup"
    assert bibs_on(payload) == ["12", "33"]
    assert "DNS" not in repr(payload)


def test_standings_drop_a_dnf_and_a_dq(store, make_race, event, house):
    ids = ids_of(event)
    s = live(store, make_race, "points", [7, 12, 33, 19], house.points(3))
    sprint(s, ids, 12, 7, 33, 19)
    assert s.act(ids[33], "dnf").ok and s.act(ids[19], "dq").ok
    layout, payload = bf.board_for(s.view())
    assert layout == "sprint_points"
    assert bibs_on(payload) == ["12", "7"]
    assert all(r.status == "" for r in payload.rows)


def test_win_and_out_recap_drops_a_dnf(store, make_race, event):
    ids = ids_of(event)
    s = live(store, make_race, "win_and_out", [7, 12, 33, 9], R.win_and_out_rules(places=2))
    clicks(s, ids, 7)
    assert s.act(ids[9], "dnf").ok
    layout, payload = bf.board_for(s.view())
    assert layout == "finish"
    assert bibs_on(payload) == ["7"]
    clicks(s, ids, 12, 33)
    layout, payload = bf.board_for(s.view())
    assert layout == "finish" and bibs_on(payload) == ["7", "12", "33"]


def test_elimination_recap_keeps_a_dnf_at_the_place_it_was_out(store, make_race, event, house):
    """A DNF in an elimination is out at that moment and placed (USAC 2E4),
    but it leaves the recap: never the big Eliminated spotlight, never in
    Out earlier, and not counted as remaining (design section 10: a rider
    who leaves a race for any reason disappears from the board). The
    result keeps the place, so the finish page lists it there, without the reason."""
    ids = ids_of(event)
    s = live(store, make_race, "elimination", [3, 5, 7, 8, 9], house.elimination())
    clicks(s, ids, 3)
    assert s.act(ids[5], "dnf").ok
    layout, payload = bf.board_for(s.view())
    assert layout == "elimination"
    assert payload.last_eliminated.bibs == ["3"], "the last rider the bell put out"
    assert payload.eliminated == []
    assert sorted(e.bibs[0] for e in payload.remaining) == ["7", "8", "9"]
    clicks(s, ids, 8)
    layout, payload = bf.board_for(s.view())
    assert payload.last_eliminated.bibs == ["8"]
    assert [e.bibs for e in payload.eliminated] == [["3"]], "the DNF is not among the outs"
    clicks(s, ids, 7)
    layout, payload = bf.board_for(s.view())
    assert layout == "finish"
    assert bibs_on(payload) == ["7", "9", "8", "5", "3"]
    assert [(p.place, p.note) for p in payload.placings if p.entry.bibs[0] == "5"] == [
        (4, "Did not finish")
    ]


# ----- a final race stays on the board labeled Final in every format --------


def test_final_label_in_every_format(store, make_race, event, house):
    ids = ids_of(event)
    chase = live(store, make_race, "chase", [12, 7], R.placings_rules())
    clicks(chase, ids, 12, 7)
    points = live(store, make_race, "points", [7, 12], house.points(3))
    sprint(points, ids, 7, 12)
    sprint(points, ids, 12, 7)
    clicks(points, ids, 7, 12)
    madison = live(store, make_race, "madison", [3, 24, 5, 36, 8, 12], house.madison(2), teams=TEAMS)  # fmt: skip
    teams = {madison.name(t): t for t in madison.roster.ids}
    for color in ("Orange", "Blue", "Red"):
        assert madison.click(teams[color]).ok
    assert madison.record_sprint().ok
    for color in ("Blue", "Orange", "Red"):
        assert madison.click(teams[color]).ok
    wao = live(store, make_race, "win_and_out", [7, 12, 33], R.win_and_out_rules(places=2))
    clicks(wao, ids, 7, 12, 33)
    expected = {"chase": "finish", "points": "sprint_points", "madison": "madison", "wao": "finish"}
    for name, s in (("chase", chase), ("points", points), ("madison", madison), ("wao", wao)):
        assert s.state == "provisional", name
        assert s.mark_final().ok
        layout, payload = bf.board_for(s.view())
        assert layout == expected[name], name
        assert payload.header.status == "Final", name


def test_a_chase_lap_shows_on_the_start_list_then_on_the_finish(store, make_race, event):
    ids = ids_of(event)
    s = live(store, make_race, "chase", [12, 7, 33], R.placings_rules())
    layout, payload = bf.board_for(s.view())
    assert layout == "pre_race" and payload.laps == []
    assert s.act(ids[33], "lap_gained").ok
    clicks(s, ids, 7)
    layout, payload = bf.board_for(s.view())
    assert layout == "pre_race"
    by_bib = dict(zip((e.bibs[0] for e in payload.roster), payload.laps, strict=True))
    assert by_bib == {"7": 0, "12": 0, "33": 1}
    clicks(s, ids, 12, 33)
    layout, payload = bf.board_for(s.view())
    assert layout == "finish"
    assert {p.entry.bibs[0]: p.laps for p in payload.placings} == {"7": 0, "12": 0, "33": 1}


def test_one_spelling_of_a_lap_count():
    assert (P.lap_text(1), P.lap_text(-2), P.lap_text(0)) == ("+1", "−2", "")
    assert (P.lap_words(1), P.lap_words(-2), P.lap_words(0)) == ("+1 lap", "−2 laps", "")


def test_one_sprint_reads_singular_in_the_rules_line():
    from types import SimpleNamespace

    from madtracker.export.summary import rules_line

    one = R.points_race_rules(sprint_count=1)
    assert rules_line(one).startswith("1 sprint, ")
    assert rules_line(R.points_race_rules(sprint_count=2)).startswith("2 sprints")
    # The board's line is the format alone; the sheet keeps the numbers.
    view = SimpleNamespace(
        rules=one, format_key="points", format_name="Points Race", title="6 Mile Points"
    )
    assert bf.rules_detail(view) == "Points Race"
    # An unnamed race's title is the format already, so the line is blank.
    view.title = "Points Race"
    assert bf.rules_detail(view) == ""


def test_a_points_race_keeps_its_start_list_until_a_sprint_or_lap_counts(
    store, make_race, event, house
):
    """A table of zeros ranked 1 to 4 in start order would read as a result."""
    ids = ids_of(event)
    s = live(store, make_race, "points", [7, 12, 33, 19], house.points(3))
    assert s.act(ids[33], "dnf").ok
    assert s.state != "setup"
    layout, payload = bf.board_for(s.view())
    assert layout == "pre_race"
    assert s.act(ids[19], "lap_gained").ok
    assert bf.board_for(s.view())[0] == "sprint_points"
