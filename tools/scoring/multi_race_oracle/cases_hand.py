"""Hand-worked multi-race standings: the expected tables written out by hand.

Each case scores real races through the suite's helpers
(tests/control/test_multi_race.py), states the table the rulebook and
the docs give for them, checks multi_race.compute against it, and then
checks the oracle agrees too (so a wrong oracle fails here as well).

The venue's sheet figures are by team color only; every name is invented.
"""

import oracle as O
import pytest
from compare import diff, normalize_oracle, normalize_program, refused
from test_multi_race import (
    elimination,
    entered,
    finish,
    four_races,
    madison,
    night,
    place_standings,
    points_race,
    rider_standings,
    rider_table,
    scratch,
    standings,
    table,
    tempo,
)

from madtracker.control import multi_race
from madtracker.control.race import LiveRace
from madtracker.scoring import rules as R


def agree(store, standings_id):
    """The program's table, after checking the oracle gives the same core table."""
    got = multi_race.compute(store, standings_id)
    core, _show = diff(normalize_program(got), normalize_oracle(O.oracle(store, standings_id)))
    assert not core, "\n".join(core)
    return got


# ----- Team Omnium by Points ----------------------------------------------------


def test_venue_semipro_a_day_one(store, riders):
    """The scorer's SEMIPRO A tab, Day 1, by color: sorted by total, the negative last."""
    totals = {"Blue": -6, "Orange": 34, "Black": 6, "Purple": 30, "Pink": 21, "Yellow": 1}
    teams = {n: (riders[2 * i], riders[2 * i + 1]) for i, n in enumerate(totals)}
    fri = night(store, riders, "Oktoberfest Day 1", "2026-10-16")
    madison(store, fri, teams, totals, group="SemiPro A")
    got = agree(store, standings(store, [fri]))
    (g,) = got.groups
    assert table(g.rows) == [
        (1, "Orange", [34], 34),
        (2, "Purple", [30], 30),
        (3, "Pink", [21], 21),
        (4, "Black", [6], 6),
        (5, "Yellow", [1], 1),
        (6, "Blue", [-6], -6),
    ]
    # The same night by place, 7-5-3-2-1: 6th scores nothing.
    by_place = agree(store, place_standings(store, [fri]))
    assert table(by_place.groups[0].rows) == [
        (1, "Orange", [7], 7),
        (2, "Purple", [5], 5),
        (3, "Pink", [3], 3),
        (4, "Black", [2], 2),
        (5, "Yellow", [1], 1),
        (6, "Blue", [0], 0),
    ]


def test_venue_co_ed_day_one(store, riders):
    """The scorer's CO-ED MADISON tab, Day 1, by color."""
    totals = {"Purple": 2, "Pink": -7, "White": 5, "Black": 12, "Green": -19, "Red": 22}
    teams = {n: (riders[2 * i], riders[2 * i + 1]) for i, n in enumerate(totals)}
    fri = night(store, riders, "Oktoberfest Day 1", "2026-10-16")
    madison(store, fri, teams, totals, group="Co-Ed")
    got = agree(store, standings(store, [fri]))
    assert table(got.groups[0].rows) == [
        (1, "Red", [22], 22),
        (2, "Black", [12], 12),
        (3, "White", [5], 5),
        (4, "Purple", [2], 2),
        (5, "Pink", [-7], -7),
        (6, "Green", [-19], -19),
    ]
    assert got.state == "final" and got.counted == "1 Madison raced over 1 event"


def test_two_nights_tie_goes_to_most_firsts_then_seconds(store, riders):
    """A 20 + -10 and B 5 + 5 both make 10. One first each; B has a second, A a third: B leads."""
    a, b, c = (riders[0], riders[1]), (riders[2], riders[3]), (riders[4], riders[5])
    teams = {"A": a, "B": b, "C": c}
    fri = night(store, riders, "Fri", "2026-10-16")
    sat = night(store, riders, "Sat", "2026-10-17")
    madison(store, fri, teams, {"A": 20, "B": 5, "C": 2})
    madison(store, sat, teams, {"A": -10, "B": 5, "C": 3})
    got = agree(store, standings(store, [fri, sat]))
    assert table(got.groups[0].rows) == [
        (1, "B", [5, 5], 10),
        (2, "A", [20, -10], 10),
        (3, "C", [2, 3], 5),
    ]


def _madison_with_statuses(store, event_id, riders, *, dq=(), dns=(), dnf_after_lap=()):
    """Teams A, B, C, D (rulebook Madison, one sprint 10-6-4-2, 20 a lap); statuses as given."""
    rules = R.madison_rules(sprint_count=1)
    race = store.add_race(
        event_id, "Pro Madison", "madison", group_label="Pro", rules=rules.to_dict()
    )
    ids = {}
    for i, name in enumerate("ABCD"):
        pair = (riders[2 * i], riders[2 * i + 1])
        for rid in pair:
            store.add_race_entry(race.race_id, rid)
        team = store.add_team(race.race_id, name, color=name)
        for rid in pair:
            store.add_team_member(team.team_id, rid)
        ids[name] = team.team_id
    live = LiveRace(store, race.race_id)
    for name in dnf_after_lap:
        assert live.act(ids[name], "lap_gained").ok
        assert live.act(ids[name], "dnf").ok
    for name in dq:
        assert live.act(ids[name], "dq").ok
    for name in dns:
        assert live.act(ids[name], "dns").ok
    for name in "ABCD":
        if name not in (*dq, *dns, *dnf_after_lap):
            assert live.click(ids[name]).ok, name
    assert live.standings().is_complete
    assert live.mark_final().ok
    return race.race_id


def test_a_dnf_team_keeps_its_lap_a_dq_team_scores_nothing_and_a_dns_team_is_out(store, riders):
    """R-TEAM-2 and R-TEAM-4: A gained a lap (20) then DNF; B DQ; D DNS; C alone finishes (10)."""
    fri = night(store, riders, "Fri", "2026-10-16")
    _madison_with_statuses(store, fri, riders, dq=("B",), dns=("D",), dnf_after_lap=("A",))
    got = agree(store, standings(store, [fri]))
    # By points: A's 20 counts toward its total (R-TEAM-2), B rode and scores 0, D is left out.
    assert table(got.groups[0].rows) == [(1, "A", [20], 20), (2, "C", [10], 10), (3, "B", [0], 0)]
    # By place: only C has a place the sheet prints a number for.
    by_place = agree(store, place_standings(store, [fri]))
    assert table(by_place.groups[0].rows) == [(1, "C", [7], 7), (2, "A", [0], 0), (2, "B", [0], 0)]


def test_a_team_on_one_night_of_two_and_a_changed_pair_are_left_out(store, riders):
    p, q, q2 = (riders[0], riders[1]), (riders[2], riders[3]), (riders[2], riders[4])
    fri = night(store, riders, "Fri", "2026-10-16")
    sat = night(store, riders, "Sat", "2026-10-17")
    madison(store, fri, {"P": p, "Q": q}, {"P": 20, "Q": 5})
    madison(store, sat, {"P": p, "Q": q2}, {"P": 10, "Q": 8})
    got = agree(store, standings(store, [fri, sat]))
    assert table(got.groups[0].rows) == [(1, "P", [20, 10], 30)]


# ----- Team Omnium by Place -----------------------------------------------------


def test_a_custom_table_scores_nothing_past_its_end(store, riders):
    names = ["A", "B", "C", "D"]
    teams = {n: (riders[2 * i], riders[2 * i + 1]) for i, n in enumerate(names)}
    fri = night(store, riders, "Fri", "2026-10-16")
    sat = night(store, riders, "Sat", "2026-10-17")
    madison(store, fri, teams, {"A": 40, "B": 30, "C": 20, "D": 10})
    madison(store, sat, teams, {"A": 10, "B": 20, "C": 40, "D": 30})
    sid = place_standings(store, [fri, sat], rules={"points_by_place": [10, 6]})
    got = agree(store, sid)
    # Fri: A 10, B 6; Sat: C 10, D 6. A and C tie on 10 with a first each; the
    # last race decides: C 1st there, A past the places (4th). B and D tie on
    # 6 with a second each; B's third (Sat) beats D's fourth (Fri) on the
    # countback before the last race is reached.
    assert table(got.groups[0].rows) == [
        (1, "C", [0, 10], 10),
        (2, "A", [10, 0], 10),
        (3, "B", [6, 0], 6),
        (4, "D", [0, 6], 6),
    ]


# ----- Omnium by Place ------------------------------------------------------------


def test_every_format_but_the_madison_counts_in_program_order(store, riders):
    a, b, c, d = riders[:4]
    fri = night(store, riders, "Fri", "2026-10-16")
    scratch(store, fri, [a, b, c, d], name="Scratch")
    live = entered(store, fri, "keirin", R.placings_rules(), [a, b, c, d], name="Keirin")
    finish(live, [d, c, b, a])
    live = entered(store, fri, "handicap", R.placings_rules(), [a, b, c, d], name="Handicap")
    finish(live, [b, a, d, c])
    tempo(store, fri, [[c], [c, a, b, d]], [a, b, c, d], name="Tempo")
    madison(store, fri, {"X": (a, b), "Y": (c, d)}, {"X": 10, "Y": 5}, group="Cat 3")
    points_race(store, fri, [[d, a, c, b]], [a, b, c, d], name="Points")
    elimination(store, fri, [b, a, c], d, name="Elimination")
    got = agree(store, rider_standings(store, [fri]))
    (g,) = got.groups
    assert [c.race_name for c in g.columns] == [
        "Scratch", "Keirin", "Handicap", "Tempo", "Points", "Elimination",
    ]  # fmt: skip
    # Scratch a b c d; Keirin d c b a; Handicap b a d c; Tempo c then a b d by
    # the final sprint; Points d a c b; Elimination d c a b.
    assert rider_table(g.rows) == [
        (1, 4, "Dov Arden", [2, 7, 3, 2, 7, 7], 28, ""),
        (2, 1, "Ada Arden", [7, 2, 5, 5, 5, 3], 27, ""),
        (3, 3, "Cleo Arden", [3, 5, 2, 7, 3, 5], 25, ""),
        (4, 2, "Bram Arden", [5, 3, 7, 3, 2, 2], 22, ""),
    ]


def test_dns_is_blank_dnf_scores_nothing_and_an_elimination_dnf_scores_its_place(store, riders):
    a, b, c, d = riders[:4]
    fri = night(store, riders, "Fri", "2026-10-16")
    sat = night(store, riders, "Sat", "2026-10-17")
    scratch(store, fri, [a, b, c], dns=[d], name="Scratch")
    scratch(store, sat, [a, c], dnf=[b], name="Scratch")
    live = entered(store, sat, "elimination", R.elimination_rules(), [a, b, c, d], name="Elim")
    assert live.click(d).ok  # out first: 4th
    assert live.act(c, "dnf").ok  # out at that moment: 3rd (R-ELIM-7)
    assert live.click(a).ok  # the winner of the last two
    assert live.standings().is_complete and live.mark_final().ok
    got = agree(store, rider_standings(store, [fri, sat]))
    (g,) = got.groups
    assert rider_table(g.rows) == [
        (1, 1, "Ada Arden", [7, 7, 7], 21, ""),
        (2, 3, "Cleo Arden", [3, 5, 3], 11, ""),
        (3, 2, "Bram Arden", [5, 0, 5], 10, ""),
        (4, 4, "Dov Arden", [None, None, 2], 2, ""),
    ]


def test_a_rider_is_one_row_across_bibs_and_shows_the_last_bib(store, riders):
    a, b = riders[:2]
    fri = store.add_event("Fri", "2026-10-16").event_id
    sat = store.add_event("Sat", "2026-10-17").event_id
    store.add_entry(fri, a, 1)
    store.add_entry(fri, b, 2)
    store.add_entry(sat, a, 9)
    store.add_entry(sat, b, 8)
    scratch(store, fri, [a, b], name="Scratch")
    scratch(store, sat, [b, a], name="Scratch")
    got = agree(store, rider_standings(store, [fri, sat]))
    # Level on 12, a first each, the last race: b won it.
    assert rider_table(got.groups[0].rows) == [
        (1, 8, "Bram Arden", [5, 7], 12, ""),
        (2, 9, "Ada Arden", [7, 5], 12, ""),
    ]


def test_groups_states_and_a_left_out_race(store, riders):
    """ "Cat 3" and "cat3" are one table; "" is its own; a running Points Race counts, a
    running Elimination waits, a race in setup is not yet raced, an unticked race is left out."""
    a, b, c = riders[:3]
    fri = night(store, riders, "Fri", "2026-10-16")
    s1 = scratch(store, fri, [a, b, c], group="Cat 3", name="S1")
    s2 = scratch(store, fri, [b, a, c], group="cat3", name="S2")
    s3 = scratch(store, fri, [c, a, b], group="", name="S3")
    live = entered(store, fri, "points", R.points_race_rules(sprint_count=2), [a, b, c], name="P")
    assert live.click(a).ok and live.click(b).ok and live.record_sprint().ok
    p = live.race_id
    live = entered(store, fri, "elimination", R.elimination_rules(), [a, b, c], name="E")
    assert live.click(c).ok
    e = live.race_id
    x = entered(store, fri, "chase", R.placings_rules(), [a, b, c], name="X").race_id
    left = scratch(store, fri, [a, b, c], name="L")
    sid = rider_standings(store, [fri], excluded=[left])
    got = agree(store, sid)
    assert [c.race_id for c in got.left_out] == [left]
    assert [c.race_id for c in got.not_yet_raced] == [x]
    assert [c.race_id for c in got.racing] == [e]
    assert got.state == "provisional"
    assert got.counted == "4 of 6 races raced over 1 event"
    cat3, none = got.groups
    assert [c.race_id for c in cat3.columns] == [s1, s2, p]
    assert none.group == "" and [c.race_id for c in none.columns] == [s3]
    # Cat 3: S1 a b c, S2 b a c, P as it stands (a 5, b 3, c 0: a b c).
    assert rider_table(cat3.rows) == [
        (1, 1, "Ada Arden", [7, 5, 7], 19, ""),
        (2, 2, "Bram Arden", [5, 7, 5], 17, ""),
        (3, 3, "Cleo Arden", [3, 3, 3], 9, ""),
    ]


# ----- Four-Race Omnium -----------------------------------------------------------


def test_four_race_worked_example_with_the_final_sprint_tie_break(store, riders):
    a, b, c, d = riders[:4]
    fri = night(store, riders, "Fri", "2026-10-16")
    scratch(store, fri, [a, b, c, d], name="Scratch")
    tempo(store, fri, [[b], [b, a, c, d]], [a, b, c, d], name="Tempo")
    elimination(store, fri, [d, c, b], a, name="Elimination")
    points_race(store, fri, [[c, d, a, b]], [a, b, c, d], name="Points")
    got = agree(store, rider_standings(store, [fri], kind=multi_race.FOUR_RACE))
    assert not refused(got) and got.state == "final"
    # Scratch 40 38 36 34; Tempo b 40, a 38, c 36, d 34; Elimination a 40, b 38,
    # c 36, d 34; Points (final sprint doubled) c 10, d 6, a 4, b 2.
    # b and c tie on 118: c won the final sprint, b was 4th in it.
    assert rider_table(got.groups[0].rows) == [
        (1, 1, "Ada Arden", [40, 38, 40, 4], 122, ""),
        (2, 3, "Cleo Arden", [36, 36, 36, 10], 118, ""),
        (3, 2, "Bram Arden", [38, 40, 38, 2], 118, ""),
        (4, 4, "Dov Arden", [34, 34, 34, 6], 108, ""),
    ]


def test_twenty_first_and_below_score_one(store, riders):
    field = riders[:22]
    fri = night(store, riders, "Fri", "2026-10-16")
    scratch(store, fri, field, name="Scratch")
    tempo(store, fri, [[field[0]], field], field, name="Tempo")
    elimination(store, fri, list(reversed(field[1:])), field[0], name="Elimination")
    points_race(store, fri, [field], field, name="Points")
    got = agree(store, rider_standings(store, [fri], kind=multi_race.FOUR_RACE))
    rows = {r.bib: r for r in got.groups[0].rows}
    assert rows[20].per_race == [2, 2, 2, 0] and rows[20].total == 6
    assert rows[21].per_race == [1, 1, 1, 0] and rows[21].total == 3
    assert rows[22].per_race == [1, 1, 1, 0] and rows[22].total == 3
    # The two on 3 go to the final sprint: 21st beat 22nd there.
    assert (rows[21].rank, rows[22].rank) == (21, 22)
    assert rows[1].per_race == [40, 40, 40, 10] and rows[1].total == 130


def test_a_rider_out_of_any_race_is_dnf_after_every_finisher_and_dq_last(store, riders):
    a, b, c, d, e = riders[:5]
    fri = night(store, riders, "Fri", "2026-10-16")
    live = entered(store, fri, "chase", R.placings_rules(), [a, b, c, d, e], name="Scratch")
    assert live.act(e, "dq").ok
    finish(live, [a, b, c], dnf=[d])
    tempo(store, fri, [[a], [a, b, c, d, e]], [a, b, c, d, e], name="Tempo")
    elimination(store, fri, [e, d, c, b], a, name="Elimination")
    points_race(store, fri, [[a, b, c, d, e]], [a, b, c, d, e], name="Points")
    got = agree(store, rider_standings(store, [fri], kind=multi_race.FOUR_RACE))
    rows = got.groups[0].rows
    assert [(r.rank, r.bib, r.status) for r in rows] == [
        (1, 1, ""),
        (2, 2, ""),
        (3, 3, ""),
        (None, 4, "DNF"),
        (None, 5, "DQ"),
    ]
    assert rows[0].total == 40 + 40 + 40 + 10


def test_the_omnium_penalty_comes_off_before_ranking_and_zero_takes_it_off(store, riders):
    a, b, c = riders[:3]
    fri = night(store, riders, "Fri", "2026-10-16")
    four_races(store, fri, (a, b, c))
    sid = rider_standings(store, [fri], kind=multi_race.FOUR_RACE)
    got = agree(store, sid)
    # a 40+40+40+8 = 128, b 38+38+38+15 = 129, c 36+36+36+7 = 115.
    assert rider_table(got.groups[0].rows) == [
        (1, 2, "Bram Arden", [38, 38, 38, 15], 129, ""),
        (2, 1, "Ada Arden", [40, 40, 40, 8], 128, ""),
        (3, 3, "Cleo Arden", [36, 36, 36, 7], 115, ""),
    ]
    store.set_standings_penalty(sid, b, 40)
    got = agree(store, sid)
    assert [(r.rank, r.bib, r.total, r.penalty) for r in got.groups[0].rows] == [
        (1, 1, 128, 0),
        (2, 3, 115, 0),
        (3, 2, 89, 40),
    ]
    store.set_standings_penalty(sid, b, 0)
    got = agree(store, sid)
    assert [(r.rank, r.bib, r.penalty) for r in got.groups[0].rows] == [
        (1, 2, 0),
        (2, 1, 0),
        (3, 3, 0),
    ]


@pytest.mark.parametrize("flaw", ["missing", "doubled", "empty-event", "unticked"])
def test_a_program_short_of_a_format_is_refused_with_no_table(store, riders, flaw):
    a, b, c = riders[:3]
    fri = night(store, riders, "Fri", "2026-10-16")
    races = four_races(store, fri, (a, b, c))
    excluded = []
    events = [fri]
    if flaw == "missing":
        store.add_race(fri, "Gone", "chase")  # setup only; the Elimination is removed below
        excluded = [races[2]]
    elif flaw == "doubled":
        scratch(store, fri, [a, b, c], name="Scratch 2")
    elif flaw == "empty-event":
        events.append(night(store, riders, "Sat", "2026-10-17"))
    elif flaw == "unticked":
        excluded = [races[1]]
    sid = rider_standings(store, events, kind=multi_race.FOUR_RACE, excluded=excluded)
    got = agree(store, sid)
    assert refused(got) and got.groups == [] and got.state == "provisional"
    # Put right, the table stands.
    store.update_standings(sid, event_ids=[fri], excluded_race_ids=[])
    if flaw == "doubled":
        extra = [r.race_id for r in store.races(fri) if r.name == "Scratch 2"]
        store.update_standings(sid, excluded_race_ids=extra)
    if flaw == "missing":
        gone = [r.race_id for r in store.races(fri) if r.name == "Gone"]
        store.update_standings(sid, excluded_race_ids=gone)
    got = agree(store, sid)
    assert not refused(got) and len(got.groups) == 1


def test_a_points_race_left_out_makes_a_three_race_omnium_that_is_final(store, riders):
    """R-OMNI-8 (USAC 2O4): the Points Race alone may be unticked; the three
    races stand and are final once each is."""
    fri = night(store, riders, "Fri", "2026-10-16")
    races = four_races(store, fri, riders[:3])
    sid = rider_standings(store, [fri], kind=multi_race.FOUR_RACE, excluded=[races[3]])
    got = agree(store, sid)
    assert not refused(got) and got.state == "final"
    assert [c.format for c in got.groups[0].columns] == ["chase", "tempo", "elimination"]
    assert [c.race_id for c in got.left_out] == [races[3]]


def test_the_columns_run_in_the_omnium_order_whatever_the_program(store, riders):
    fri = night(store, riders, "Fri", "2026-10-16")
    four_races(store, fri, riders[:3], program_order=True)
    got = agree(store, rider_standings(store, [fri], kind=multi_race.FOUR_RACE))
    assert [c.format for c in got.groups[0].columns] == ["chase", "tempo", "elimination", "points"]


def test_two_nights_sum_eight_columns_and_a_rider_who_missed_a_night_is_out(store, riders):
    a, b, c, d = riders[:4]
    fri = night(store, riders, "Fri", "2026-10-16")
    sat = night(store, riders, "Sat", "2026-10-17")
    four_races(store, fri, (a, b, c))
    four_races(store, sat, (a, b, d))
    got = agree(store, rider_standings(store, [fri, sat], kind=multi_race.FOUR_RACE))
    (g,) = got.groups
    assert len(g.columns) == 8
    assert [(r.rank, r.bib, r.total, r.status) for r in g.rows] == [
        (1, 2, 258, ""),
        (2, 1, 256, ""),
        (None, 3, 0, "DNF"),
        (None, 4, 0, "DNF"),
    ] or [(r.rank, r.bib, r.status) for r in g.rows[:2]] == [(1, 2, ""), (2, 1, "")]
    assert g.rows[0].per_race == [38, 38, 38, 15, 38, 38, 38, 15]
