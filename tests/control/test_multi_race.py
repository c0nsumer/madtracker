"""Multi-race standings: the Team Omnium over Madisons from several events.

Each Madison is scored through ``LiveRace`` the way the surface scores
it (laps gained and lost, then the final sprint, then Mark Final), so
the standings replay the real path. The scorer's sheet only gives each
team's Madison total, so ``madison`` makes a race that lands on exactly
that total: the tens as laps at 10 a lap (the venue's value), the rest
as the final sprint's points, from a one-sprint table built for the
race. The goldens are the scorer's Oktoberfest 2026 sheet ("PRO OMNIUM"
tab, Day 1) and the venue's published "2 Day Omnium", with invented
names.
"""

import pytest

from madtracker.control import multi_race
from madtracker.control.race import LiveRace
from madtracker.scoring import rules as R
from madtracker.store import Store

FIRST = ["Ada", "Bram", "Cleo", "Dov", "Esme", "Finn", "Gus", "Hana"]
LAST = ["Arden", "Birch", "Corso", "Dunmore", "Ellery", "Faro"]


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "multi_race.sqlite")
    yield s
    s.close()


@pytest.fixture
def riders(store):
    """Thirty-two invented riders: riders[i] is a rider_id."""
    return [
        store.add_rider(FIRST[i % len(FIRST)], LAST[i // len(FIRST)]).rider_id for i in range(32)
    ]


def night(store, riders, name, date):
    """An event with every rider on its roster; bib i + 1 for riders[i]."""
    event = store.add_event(name, date)
    for i, rider_id in enumerate(riders):
        store.add_entry(event.event_id, rider_id, i + 1)
    return event.event_id


def madison(store, event_id, teams, totals, *, group="Pro", name="", final=True):
    """A Madison whose teams finish on ``totals``; returns its race_id.

    ``teams`` is name -> (rider_id, rider_id), in the order the teams
    were set up; ``totals`` is name -> the Madison total.
    """
    # -39 is four laps down and 1 point; Python's % keeps the points 0 to 9.
    points = {team: total % 10 for team, total in totals.items()}
    order = sorted(totals, key=lambda team: -points[team])
    rules = R.SprintPointsRules(
        points_by_sprint=(tuple(points[t] for t in order),),
        lap_gained_points=10,
        lap_lost_points=10,
        scored_unit="team",
    )
    race = store.add_race(
        event_id, name or f"{group} Madison", "madison", group_label=group, rules=rules.to_dict()
    )
    ids = {}
    for team, pair in teams.items():
        for rider_id in pair:
            store.add_race_entry(race.race_id, rider_id)
        made = store.add_team(race.race_id, team, color=team)
        for rider_id in pair:
            store.add_team_member(made.team_id, rider_id)
        ids[team] = made.team_id
    s = LiveRace(store, race.race_id)
    for team, total in totals.items():
        laps = (total - points[team]) // 10
        for _ in range(abs(laps)):
            out = s.act(ids[team], "lap_gained" if laps > 0 else "lap_lost")
            assert out.ok, out.message
    for team in order:
        out = s.click(ids[team])
        assert out.ok, out.message
    # The last click of the final sprint records it, as on the surface.
    assert s.standings().is_complete
    by_id = {r.entrant_id: r.total_points for r in s.standings().rows}
    assert {t: by_id[i] for t, i in ids.items()} == totals, "the race lands on the sheet's totals"
    if final:
        assert s.mark_final().ok
    return race.race_id


def standings(store, event_ids, excluded=(), name="Weekend Omnium"):
    made = store.add_standings(name)
    store.update_standings(
        made.standings_id, event_ids=list(event_ids), excluded_race_ids=list(excluded)
    )
    return made.standings_id


def table(rows):
    return [(r.rank, r.team, r.per_race, r.total) for r in rows]


def test_golden_oktoberfest_pro_day_one(store, riders):
    """The scorer's PRO OMNIUM tab, Day 1: eight teams, sorted by total, negatives last."""
    names = ["Stars", "Red", "Green", "White", "Purple", "Yellow", "Black", "Silver"]
    totals = [60, 28, 1, 15, 10, -30, 2, -39]
    teams = {n: (riders[2 * i], riders[2 * i + 1]) for i, n in enumerate(names)}
    friday = night(store, riders, "Oktoberfest Day 1", "2026-10-16")
    madison(store, friday, teams, dict(zip(names, totals, strict=True)))
    got = multi_race.compute(store, standings(store, [friday]))
    assert got.kind_label == "Team Omnium by Points" and got.state == "final"
    assert got.detail == "Each team's Madison totals are summed."
    assert got.counted == "1 Madison raced over 1 event"
    assert got.events == [(friday, "Oktoberfest Day 1", "2026-10-16")]
    (pro,) = got.groups
    assert pro.group == "Pro" and [c.race_name for c in pro.columns] == ["Madison"]
    assert table(pro.rows) == [
        (1, "Stars", [60], 60),
        (2, "Red", [28], 28),
        (3, "White", [15], 15),
        (4, "Purple", [10], 10),
        (5, "Black", [2], 2),
        (6, "Green", [1], 1),
        (7, "Yellow", [-30], -30),
        (8, "Silver", [-39], -39),
    ]
    stars = pro.rows[0]
    assert stars.color == "stars" and stars.status == ""
    assert stars.riders == ["Ada Arden", "Bram Arden"]


def test_golden_two_day_omnium_sums_each_pair_over_both_nights(store, riders):
    """The venue's 2 Day Omnium: Purple 26 + 42 = 68 beats 50 + 10 = 60."""
    # Saturday is set up first, so its event id is lower: columns still go by date.
    saturday = night(store, riders, "Oktoberfest Day 2", "2026-10-17")
    friday = night(store, riders, "Oktoberfest Day 1", "2026-10-16")
    purple, gold, teal = (riders[0], riders[1]), (riders[2], riders[3]), (riders[4], riders[5])
    # The pair rode Friday as Violet: the row takes Saturday's name.
    madison(store, friday, {"Violet": purple, "Gold": gold, "Teal": teal},
            {"Violet": 26, "Gold": 50, "Teal": 30})  # fmt: skip
    madison(store, saturday, {"Purple": purple, "Gold": gold}, {"Purple": 42, "Gold": 10},
            final=False)  # fmt: skip
    got = multi_race.compute(store, standings(store, [saturday, friday]))
    (pro,) = got.groups
    assert [c.event_name for c in pro.columns] == ["Oktoberfest Day 1", "Oktoberfest Day 2"]
    # Teal rode Friday alone: left out, as the venue's sheet left out a
    # team that rode one night of two.
    assert table(pro.rows) == [
        (1, "Purple", [26, 42], 68),
        (2, "Gold", [50, 10], 60),
    ]
    assert got.state == "provisional", "Saturday's Madison is not final yet"
    assert got.counted == "2 Madisons raced over 2 events"
    assert [e[0] for e in got.events] == [friday, saturday]


def test_a_pair_that_changes_a_rider_is_another_team(store, riders):
    friday = night(store, riders, "Friday", "2026-10-16")
    saturday = night(store, riders, "Saturday", "2026-10-17")
    madison(store, friday, {"Red": (riders[0], riders[1]), "Blue": (riders[2], riders[3])},
            {"Red": 20, "Blue": 5})  # fmt: skip
    madison(store, saturday, {"Red": (riders[0], riders[4]), "Blue": (riders[2], riders[3])},
            {"Red": 12, "Blue": 7})  # fmt: skip
    (pro,) = multi_race.compute(store, standings(store, [friday, saturday])).groups
    # Matched by name, Red would lead on 20 + 12 = 32. Each Red pair rode
    # one night, so each is left out, and Blue has the table to itself.
    assert table(pro.rows) == [(1, "Blue", [5, 7], 12)]


def test_a_team_that_rode_one_night_of_two_is_left_out(store, riders):
    """A team that rode one night of two is left out, as the venue's VIII
    Anniversary sheet does: its one night against the others' two is no
    standing. A team that did not finish rode, and stays."""
    friday = night(store, riders, "Friday", "2026-10-16")
    saturday = night(store, riders, "Saturday", "2026-10-17")
    red, blue, green = riders[0:2], riders[2:4], riders[4:6]
    madison(store, friday, {"Red": red, "Blue": blue, "Green": green},
            {"Red": 40, "Blue": 5, "Green": 60})  # fmt: skip
    madison(store, saturday, {"Red": red, "Blue": blue}, {"Red": 2, "Blue": 20})
    (pro,) = multi_race.compute(store, standings(store, [friday, saturday])).groups
    assert table(pro.rows) == [(1, "Red", [40, 2], 42), (2, "Blue", [5, 20], 25)]
    assert all(None not in r.per_race for r in pro.rows), "every row rode every Madison"


def test_two_groups_in_the_same_events_are_two_tables(store, riders):
    friday = night(store, riders, "Friday", "2026-10-16")
    saturday = night(store, riders, "Saturday", "2026-10-17")
    pro = {"Red": (riders[0], riders[1]), "Blue": (riders[2], riders[3])}
    semi = {"Green": (riders[10], riders[11]), "White": (riders[12], riders[13])}
    madison(store, friday, semi, {"Green": 3, "White": 9}, group="SemiPro A")
    madison(store, friday, pro, {"Red": 30, "Blue": 10})
    madison(store, saturday, pro, {"Red": 0, "Blue": 25})
    # The label typed another way on Saturday is still the same group.
    madison(store, saturday, semi, {"Green": 8, "White": 1}, group="semipro a")
    got = multi_race.compute(store, standings(store, [friday, saturday]))
    assert [g.group for g in got.groups] == ["SemiPro A", "Pro"], "in the order they first race"
    semi_t, pro_t = got.groups
    assert table(semi_t.rows) == [(1, "Green", [3, 8], 11), (2, "White", [9, 1], 10)]
    assert table(pro_t.rows) == [(1, "Blue", [10, 25], 35), (2, "Red", [30, 0], 30)]
    assert got.counted == "4 Madisons raced over 2 events"


def test_an_unticked_race_is_left_out_and_changes_the_totals(store, riders):
    friday = night(store, riders, "Friday", "2026-10-16")
    saturday = night(store, riders, "Saturday", "2026-10-17")
    teams = {"Red": (riders[0], riders[1]), "Blue": (riders[2], riders[3])}
    first = madison(store, friday, teams, {"Red": 40, "Blue": 5})
    madison(store, saturday, teams, {"Red": 2, "Blue": 20})
    sid = standings(store, [friday, saturday])
    (both,) = multi_race.compute(store, sid).groups
    assert table(both.rows) == [(1, "Red", [40, 2], 42), (2, "Blue", [5, 20], 25)]
    store.update_standings(sid, excluded_race_ids=[first])
    got = multi_race.compute(store, sid)
    (only,) = got.groups
    assert [c.race_id for c in got.left_out] == [first] and got.left_out[0].excluded
    assert [c.event_name for c in only.columns] == ["Saturday"]
    assert table(only.rows) == [(1, "Blue", [20], 20), (2, "Red", [2], 2)]
    assert [c.race_id for c in multi_race.candidate_races(store, store.get_standings(sid))] == [
        first,
        only.columns[0].race_id,
    ]


def test_a_race_still_in_setup_is_not_yet_raced(store, riders):
    friday = night(store, riders, "Friday", "2026-10-16")
    teams = {"Red": (riders[0], riders[1]), "Blue": (riders[2], riders[3])}
    madison(store, friday, teams, {"Red": 6, "Blue": 4})
    later = store.add_race(friday, "Pro Madison 2", "madison", group_label="Pro")
    store.add_race(friday, "Scratch", "scratch", group_label="Pro")
    got = multi_race.compute(store, standings(store, [friday]))
    assert [c.race_id for c in got.not_yet_raced] == [later.race_id]
    assert (
        got.not_yet_raced[0].state == "setup" and got.not_yet_raced[0].race_name == "Pro Madison 2"
    )
    (pro,) = got.groups
    assert len(pro.columns) == 1 and table(pro.rows) == [
        (1, "Red", [6], 6),
        (2, "Blue", [4], 4),
    ]
    assert got.state == "provisional", "a Madison still to race can change every total"
    store.update_standings(got.standings_id, excluded_race_ids=[later.race_id])
    got = multi_race.compute(store, got.standings_id)
    assert (
        got.state == "final"
        and got.not_yet_raced == []
        and got.left_out[0].race_id == later.race_id
    )


def test_removing_an_event_drops_it_from_the_definition(store, riders):
    friday = night(store, riders, "Friday", "2026-10-16")
    madison(store, friday, {"Red": (riders[0], riders[1])}, {"Red": 6})
    spare = store.add_event("Rained Out", "2026-10-17").event_id
    unrun = store.add_race(spare, "Madison", "madison", group_label="Pro")
    sid = standings(store, [friday, spare], excluded=[unrun.race_id])
    assert len(multi_race.compute(store, sid).events) == 2
    store.delete_event(spare)
    got = multi_race.compute(store, sid)
    assert [e[0] for e in got.events] == [friday] and got.left_out == []
    assert store.get_standings(sid).excluded_race_ids == []


def test_no_events_ticked_is_an_empty_provisional_table(store):
    got = multi_race.compute(store, store.add_standings("Season").standings_id)
    assert got.groups == [] and got.state == "provisional"
    assert got.counted == "no Madisons raced yet"


def test_stored_values_sit_over_the_kinds_defaults(store):
    made = store.add_standings("Season", rules={"absent_points": -5})
    rules = multi_race.rules_for(made)
    assert rules.absent_points == -5 and rules.points_by_place is None
    assert multi_race.rules_for(store.add_standings("Plain")) == R.team_omnium_rules()
    odd = store.add_standings("Odd", kind="points_by_place")
    with pytest.raises(ValueError):
        multi_race.compute(store, odd.standings_id)


def place_standings(store, event_ids, rules=None, name="Place Omnium"):
    made = store.add_standings(name, kind=multi_race.PLACES, rules=rules)
    store.update_standings(made.standings_id, event_ids=list(event_ids))
    return made.standings_id


def test_golden_team_omnium_by_place_ties_on_most_firsts_then_the_last_race(store, riders):
    """USAC 2B19(e): points for each place, 7-5-3-2-1 by default, summed over the Madisons.

    Red wins Friday and is second Saturday, Blue the other way round:
    7 + 5 = 12 each, one first each, one second each, so the last race
    decides and Blue's Saturday win puts Blue first. Green is third
    twice, 3 + 3 = 6.
    """
    friday = night(store, riders, "Friday", "2026-10-16")
    saturday = night(store, riders, "Saturday", "2026-10-17")
    teams = {"Red": (riders[0], riders[1]), "Blue": (riders[2], riders[3]),
             "Green": (riders[4], riders[5])}  # fmt: skip
    madison(store, friday, teams, {"Red": 33, "Blue": 22, "Green": 11})
    madison(store, saturday, teams, {"Red": 22, "Blue": 33, "Green": 11})
    got = multi_race.compute(store, place_standings(store, [friday, saturday]))
    assert got.kind_label == "Team Omnium by Place" and got.state == "final"
    assert got.detail == (
        "Each team scores points for its place in each Madison, 7-5-3-2-1, "
        "and the points are summed."
    )
    assert got.counted == "2 Madisons raced over 2 events"
    (pro,) = got.groups
    assert table(pro.rows) == [
        (1, "Blue", [5, 7], 12),
        (2, "Red", [7, 5], 12),
        (3, "Green", [3, 3], 6),
    ]
    # The same races summed as totals: 55 each, still Blue on the last race.
    totals = multi_race.compute(store, standings(store, [friday, saturday]))
    assert [r.total for r in totals.groups[0].rows] == [55, 55, 22]


def test_a_stored_place_table_sits_over_the_default(store, riders):
    friday = night(store, riders, "Friday", "2026-10-16")
    teams = {"Red": (riders[0], riders[1]), "Blue": (riders[2], riders[3]),
             "Green": (riders[4], riders[5])}  # fmt: skip
    madison(store, friday, teams, {"Red": 33, "Blue": 22, "Green": 11})
    sid = place_standings(store, [friday], rules={"points_by_place": [5, 4, 3, 2, 1]})
    rules = multi_race.rules_for(store.get_standings(sid))
    assert rules.points_by_place == (5, 4, 3, 2, 1)
    assert rules.tie_break == "most_firsts_then_last_race" and rules.points_beyond_table == 0
    got = multi_race.compute(store, sid)
    assert got.detail == (
        "Each team scores points for its place in each Madison, 5-4-3-2-1, "
        "and the points are summed."
    )
    assert table(got.groups[0].rows) == [
        (1, "Red", [5], 5),
        (2, "Blue", [4], 4),
        (3, "Green", [3], 3),
    ]
    # A team past the end of the table scores nothing.
    store.update_standings(sid, rules={"points_by_place": [2, 1]})
    assert [r.total for r in multi_race.compute(store, sid).groups[0].rows] == [2, 1, 0]
    assert (
        multi_race.rules_for(store.add_standings("Plain", kind=multi_race.PLACES))
        == R.usac_omnium_rules()
    )


def test_the_demo_has_a_weekend_omnium_half_raced(store):
    from madtracker.control.demo import DEMO_STANDINGS, OPENING_NIGHT, seed_demo

    tonight = seed_demo(store, "2026-10-17")
    assert store.events()[0].event_id == tonight, "the later night, the one the app opens"
    (made,) = [s for s in store.list_standings() if s.name == DEMO_STANDINGS]
    got = multi_race.compute(store, made.standings_id)
    assert got.name == DEMO_STANDINGS and got.state == "provisional"
    assert [e[1] for e in got.events] == [OPENING_NIGHT, "Demo Race Night"]
    (group,) = got.groups
    assert [c.state for c in group.columns] == ["final", "final"]
    # Tonight's Madisons are still in setup, so only the opening night
    # counts and its five teams, Green among them, rode every Madison.
    assert len(group.rows) == 5 and [r.rank for r in group.rows] == [1, 2, 3, 4, 5]
    assert "Green" in [r.team for r in group.rows]
    assert [c.race_name for c in got.not_yet_raced] == ["8 Mile Madison", "4 Mile Madison"]


def test_the_demo_runs_every_format_both_nights(store):
    """Tonight to explore, the night before scored, the same program on both."""
    from madtracker.control.demo import NO_GROUP, OPENING_NIGHT, seed_demo
    from madtracker.control.formats import FORMATS

    tonight = seed_demo(store, "2026-10-17")
    (opening,) = [e for e in store.events() if e.name == OPENING_NIGHT]
    races = store.races(tonight)
    assert sorted({r.format for r in races}) == sorted(f.key for f in FORMATS)
    before = store.races(opening.event_id)
    assert [(r.name, r.format, r.group_label) for r in before] == [
        (r.name, r.format, r.group_label) for r in races
    ]
    assert {r.state for r in races} == {"setup"} and {r.state for r in before} == {"final"}
    no_group = {e.rider_id for e in store.entries(tonight) if e.local_group is None}
    assert len(no_group) == len(NO_GROUP)
    assert any(no_group & {e.rider_id for e in store.race_entries(r.race_id)} for r in races)

    def teams(race):
        return {t.name for t in store.teams(race.race_id)}

    mads = [
        (teams(a), teams(b)) for a, b in zip(races, before, strict=True) if a.format == "madison"
    ]
    assert len(mads) == 2
    for now, then in mads:
        assert now - then == {"Black"} and then - now == {"Green"}


def test_the_demo_opening_night_shows_each_entry_beside_the_placings(store):
    """One of each entry a night can need, on the night that is scored."""
    from madtracker.control.demo import OPENING_NIGHT, PENALTY_BIB, seed_demo
    from madtracker.control.race import LiveRace

    seed_demo(store, "2026-10-17")
    (opening,) = [e for e in store.events() if e.name == OPENING_NIGHT]
    races = {r.name: LiveRace(store, r.race_id) for r in store.races(opening.event_id)}

    def rows(name):
        live = races[name]
        return {live.label(r.entrant_id): r for r in live.standings().rows}

    chase = rows("2 Mile Chase")
    maya = chase[f"#{PENALTY_BIB} Maya Petrakis"]
    assert maya.withdrawn and maya.rank == 9, "after the eight finishers"
    assert chase["#45 Isaac Pell"].status == "DNF"
    tempo = rows("4 Mile Tempo")
    # Jack after the first sprint, Rosa after the second: the later higher.
    assert tempo["#38 Rosa Navarro"].withdrawn and tempo["#38 Rosa Navarro"].rank == 9
    assert tempo["#33 Jack Moreau"].withdrawn and tempo["#33 Jack Moreau"].rank == 10
    points = races["6 Mile Points"].standings()
    assert points.sprint_count == 2 and races["6 Mile Points"].rules.sprint_count == 3
    assert rows("6 Mile Points")["#22 Lena Fischer"].out_of_finish
    assert rows("6 Mile Points")["#12 Tess Gallagher"].laps_gained == 1
    madison = races["8 Mile Madison"]
    assert madison.standings().ended and max(madison.recorded_sprints()) == 2
    assert rows("Keirin Final")["#14 Luis Ferreira"].status == "DNS"
    assert [r.status for r in rows("Handicap").values()].count("DQ") == 1
    assert rows("Unknown Distance")["#19 Omar Rahimi"].laps_not_counted == 1
    assert {live.race.state for live in races.values()} == {"final"}


def _lap_only_madison(store, event_id, riders):
    """A Madison with one lap gained and no sprint recorded: running, unranked."""
    rules = R.SprintPointsRules(
        points_by_sprint=((5, 3),), lap_gained_points=10, lap_lost_points=10, scored_unit="team"
    )
    race = store.add_race(
        event_id, "Pro Madison", "madison", group_label="Pro", rules=rules.to_dict()
    )
    ids = {}
    for team, pair in {"Red": riders[0:2], "Blue": riders[2:4]}.items():
        for rider_id in pair:
            store.add_race_entry(race.race_id, rider_id)
        made = store.add_team(race.race_id, team, color=team)
        for rider_id in pair:
            store.add_team_member(made.team_id, rider_id)
        ids[team] = made.team_id
    live = LiveRace(store, race.race_id)
    assert live.act(ids["Red"], "lap_gained").ok
    return race.race_id, ids


def test_a_lap_gained_before_the_first_sprint_counts(store, riders):
    """A running Madison with laps and no sprint never sums to 0 for all."""
    event = night(store, riders, "Night 1", "2026-10-16")
    _lap_only_madison(store, event, riders)
    got = multi_race.compute(store, standings(store, [event]))
    rows = {r.team: r for r in got.groups[0].rows}
    assert rows["Red"].per_race == [10] and rows["Red"].total == 10 and rows["Red"].rank == 1
    assert rows["Blue"].per_race == [0] and rows["Blue"].total == 0
    assert got.state == "provisional" and got.groups[0].columns[0].state == "running"


def test_a_stale_final_state_is_settled_before_it_is_read(store, riders):
    """A race left marked final with an incomplete log reads provisional, and the same way twice.

    The standings read the race as its log says and write nothing: the
    stored state is the scoring window's to settle.
    """
    event = night(store, riders, "Night 1", "2026-10-16")
    race_id, _ids = _lap_only_madison(store, event, riders)
    store.append_batch(race_id, state="final")
    assert store.race(race_id).state == "final"
    sid = standings(store, [event])
    first = multi_race.compute(store, sid)
    second = multi_race.compute(store, sid)
    assert first.state == second.state == "provisional"
    assert store.race(race_id).state == "final", "a standings read writes nothing"


def test_a_team_that_did_not_start_did_not_ride_and_is_left_out(store, riders):
    event = night(store, riders, "Night 1", "2026-10-16")
    teams = {"Red": riders[0:2], "Blue": riders[2:4], "Green": riders[4:6]}
    rules = R.SprintPointsRules(
        points_by_sprint=((5, 3, 1),), lap_gained_points=10, lap_lost_points=10, scored_unit="team"
    )
    race = store.add_race(event, "Pro Madison", "madison", group_label="Pro", rules=rules.to_dict())
    ids = {}
    for team, pair in teams.items():
        for rider_id in pair:
            store.add_race_entry(race.race_id, rider_id)
        made = store.add_team(race.race_id, team, color=team)
        for rider_id in pair:
            store.add_team_member(made.team_id, rider_id)
        ids[team] = made.team_id
    live = LiveRace(store, race.race_id)
    assert live.act(ids["Green"], "dns").ok
    for team in ("Red", "Blue"):
        assert live.click(ids[team]).ok
    assert live.standings().is_complete
    got = multi_race.compute(store, standings(store, [event]))
    rows = {r.team: r for r in got.groups[0].rows}
    assert rows["Red"].per_race == [5] and rows["Blue"].per_race == [3]
    assert "Green" not in rows and [r.rank for r in got.groups[0].rows] == [1, 2]


def test_every_madison_left_out_says_so_not_that_none_raced(store, riders):
    """Unticking every race says so, not "no Madisons raced yet"."""
    friday = night(store, riders, "Friday", "2026-10-16")
    raced = madison(store, friday, {"Red": (riders[0], riders[1])}, {"Red": 6})
    got = multi_race.compute(store, standings(store, [friday], excluded=[raced]))
    assert got.counted == "every Madison left out"
    assert got.counted == "every Madison left out"


def test_a_madison_in_setup_is_not_yet_raced_even_beside_one_left_out(store, riders):
    friday = night(store, riders, "Friday", "2026-10-16")
    raced = madison(store, friday, {"Red": (riders[0], riders[1])}, {"Red": 6})
    store.add_race(friday, "Later Madison", "madison", group_label="Pro")
    got = multi_race.compute(store, standings(store, [friday], excluded=[raced]))
    assert got.counted == "no Madisons raced yet"


def test_the_count_alone_is_kept_for_the_dialog(store, riders):
    friday = night(store, riders, "Friday", "2026-10-16")
    madison(store, friday, {"Red": (riders[0], riders[1])}, {"Red": 6})
    got = multi_race.compute(store, standings(store, [friday]))
    assert got.counted == "1 Madison raced over 1 event"
    assert got.detail.endswith(".")


# ----- the rider kinds ---------------------------------------------------------


def rider_standings(store, event_ids, kind=multi_race.OMNIUM, excluded=(), rules=None):
    name = f"Rider Omnium {len(store.list_standings()) + 1}"
    made = store.add_standings(name, kind=kind, rules=rules)
    store.update_standings(
        made.standings_id, event_ids=list(event_ids), excluded_race_ids=list(excluded)
    )
    return made.standings_id


def entered(store, event_id, format_key, rules, field, *, group="Cat 3", name=""):
    race = store.add_race(
        event_id,
        name or f"{group} {format_key}",
        format_key,
        group_label=group,
        rules=rules.to_dict(),
    )
    for rider_id in field:
        store.add_race_entry(race.race_id, rider_id)
    return LiveRace(store, race.race_id)


def finish(live, order, *, dns=(), dnf=(), final=True):
    """Statuses first, then every click of a finish order; the race ends on the last."""
    for rider_id in dns:
        assert live.act(rider_id, "dns").ok
    for rider_id in dnf:
        assert live.act(rider_id, "dnf").ok
    for rider_id in order:
        out = live.click(rider_id)
        assert out.ok, out.message
    assert live.standings().is_complete
    if final:
        assert live.mark_final().ok
    return live.race_id


def scratch(store, event_id, order, *, dns=(), dnf=(), group="Cat 3", name="", final=True):
    """A Scratch Race finished in ``order`` (rider ids); returns its race_id."""
    field = [*order, *dns, *dnf]
    live = entered(store, event_id, "chase", R.placings_rules(), field, group=group, name=name)
    return finish(live, order, dns=dns, dnf=dnf, final=final)


def sprints(
    store, event_id, format_key, rules, placings, field, *, penalty=None, group="Cat 3", name=""
):
    """A sprint-points race: each sprint's placings clicked and recorded, the last one the finish.

    ``penalty`` is (rider_id, points) recorded as a Points Penalty before
    the final sprint.
    """
    live = entered(store, event_id, format_key, rules, field, group=group, name=name)
    for order in placings[:-1]:
        for rider_id in order:
            assert live.click(rider_id).ok
        assert live.record_sprint().ok
    if penalty is not None:
        rider_id, points = penalty
        out = live.act(rider_id, f"points_penalty:{points}")
        assert out.ok, out.message
    return finish(live, placings[-1])


def points_race(store, event_id, placings, field, **kw):
    rules = R.points_race_rules(sprint_count=len(placings))
    return sprints(store, event_id, "points", rules, placings, field, **kw)


def tempo(store, event_id, placings, field, **kw):
    rules = R.tempo_rules(sprint_count=len(placings))
    return sprints(store, event_id, "tempo", rules, placings, field, **kw)


def elimination(store, event_id, out_order, winner, *, group="Cat 3", name=""):
    """Riders out in ``out_order`` down to the last two, then the winner's click."""
    field = [*out_order, winner, *[r for r in [] if r]]
    live = entered(
        store, event_id, "elimination", R.elimination_rules(), field, group=group, name=name
    )
    for rider_id in out_order[:-1]:
        assert live.click(rider_id).ok
    return finish(live, [winner])


def rider_table(rows):
    return [(r.rank, r.bib, r.team, r.per_race, r.total, r.status) for r in rows]


def test_omnium_by_place_sums_each_riders_place_points_over_the_nights(store, riders):
    """USAC 2B19(e) omnium scoring for riders: 7-5-3-2-1 by place in each race, summed.

    Ada wins both Scratch Races (7 + 7) and is 2nd in both Points Races
    (5 + 5) for 24; Bram the other way round for 24; Cleo is 3rd in all
    four for 12. Level on total, firsts, and seconds, Ada and Bram go to
    the last race, Saturday's Points Race, where Bram won.
    """
    ada, bram, cleo = riders[0:3]
    friday = night(store, riders, "Friday", "2026-10-16")
    saturday = night(store, riders, "Saturday", "2026-10-17")
    scratch(store, friday, [ada, bram, cleo], name="Scratch")
    points_race(
        store, friday, [[bram, ada, cleo], [bram, ada, cleo]], [ada, bram, cleo], name="Points"
    )
    scratch(store, saturday, [ada, bram, cleo], name="Scratch")
    points_race(
        store, saturday, [[bram, ada, cleo], [bram, ada, cleo]], [ada, bram, cleo], name="Points"
    )
    got = multi_race.compute(store, rider_standings(store, [friday, saturday]))
    assert got.kind_label == "Omnium by Place" and got.state == "final"
    assert got.detail == (
        "Each rider scores points for their place in each race, 7-5-3-2-1, "
        "and the points are summed."
    )
    assert got.counted == "4 races raced over 2 events"
    (cat3,) = got.groups
    assert cat3.riders and cat3.group == "Cat 3"
    assert [(c.event_name, c.race_name) for c in cat3.columns] == [
        ("Friday", "Scratch"),
        ("Friday", "Points"),
        ("Saturday", "Scratch"),
        ("Saturday", "Points"),
    ]
    assert rider_table(cat3.rows) == [
        (1, 2, "Bram Arden", [5, 7, 5, 7], 24, ""),
        (2, 1, "Ada Arden", [7, 5, 7, 5], 24, ""),
        (3, 3, "Cleo Arden", [3, 3, 3, 3], 12, ""),
    ]
    assert all(r.riders == [] and r.color is None for r in cat3.rows)


def test_a_rider_shows_under_the_bib_they_raced_under_last(store, riders):
    ada, bram = riders[0:2]
    friday = night(store, riders, "Friday", "2026-10-16")
    saturday = store.add_event("Saturday", "2026-10-17").event_id
    # Saturday's roster hands out other bibs.
    store.add_entry(saturday, ada, 41)
    store.add_entry(saturday, bram, 42)
    scratch(store, friday, [ada, bram])
    scratch(store, saturday, [ada, bram])
    (cat3,) = multi_race.compute(store, rider_standings(store, [friday, saturday])).groups
    assert [(r.bib, r.team) for r in cat3.rows] == [(41, "Ada Arden"), (42, "Bram Arden")]


def test_a_rider_who_rode_one_night_stays_in_with_nothing_for_the_other(store, riders):
    """No minimum: a rider who rode one race of three is in
    the table on that race's points alone; the races not ridden add nothing."""
    ada, bram, cleo = riders[0:3]
    friday = night(store, riders, "Friday", "2026-10-16")
    saturday = night(store, riders, "Saturday", "2026-10-17")
    scratch(store, friday, [ada, bram, cleo])
    scratch(store, saturday, [bram, ada], name="Scratch 1")
    scratch(store, saturday, [ada, bram], name="Scratch 2")
    (cat3,) = multi_race.compute(store, rider_standings(store, [friday, saturday])).groups
    assert rider_table(cat3.rows) == [
        (1, 1, "Ada Arden", [7, 5, 7], 19, ""),
        (2, 2, "Bram Arden", [5, 7, 5], 17, ""),
        (3, 3, "Cleo Arden", [3, None, None], 3, ""),
    ]


def test_a_dns_rider_did_not_ride_and_a_dnf_rider_scores_nothing_and_stays(store, riders):
    ada, bram, cleo, dov = riders[0:4]
    friday = night(store, riders, "Friday", "2026-10-16")
    scratch(store, friday, [ada, bram], dns=[dov], dnf=[cleo], name="Scratch")
    scratch(store, friday, [cleo, ada, bram], name="Scratch 2")
    (cat3,) = multi_race.compute(store, rider_standings(store, [friday])).groups
    rows = {r.team: r for r in cat3.rows}
    assert rows["Cleo Arden"].per_race == [0, 7], "a DNF rode and scored nothing there"
    assert "Dov Arden" not in rows, "a DNS in the only race entered did not ride"


def test_a_madison_never_counts_in_a_rider_omnium(store, riders):
    """A Madison's entrants are teams; it is no candidate for a rider kind, and
    no race but the Madison is a candidate for a team kind."""
    friday = night(store, riders, "Friday", "2026-10-16")
    mad = madison(store, friday, {"Red": (riders[0], riders[1])}, {"Red": 6}, group="Cat 3")
    one = scratch(store, friday, [riders[0], riders[1]])
    for kind in (multi_race.OMNIUM, multi_race.FOUR_RACE):
        sid = rider_standings(store, [friday], kind=kind)
        assert [c.race_id for c in multi_race.candidate_races(store, store.get_standings(sid))] == [
            one
        ]
    for kind in (multi_race.TOTALS, multi_race.PLACES):
        sid = rider_standings(store, [friday], kind=kind)
        assert [c.race_id for c in multi_race.candidate_races(store, store.get_standings(sid))] == [
            mad
        ]
    assert multi_race.race_counts(multi_race.FOUR_RACE, "handicap") is False, (
        "the four formats alone"
    )


def test_the_rider_kinds_count_races_not_madisons(store, riders):
    friday = night(store, riders, "Friday", "2026-10-16")
    raced = scratch(store, friday, [riders[0], riders[1]])
    store.add_race(friday, "Later Scratch", "chase", group_label="Cat 3")
    sid = rider_standings(store, [friday])
    assert multi_race.compute(store, sid).counted == "1 of 2 races raced over 1 event"
    store.update_standings(sid, excluded_race_ids=[raced])
    assert multi_race.compute(store, sid).counted == "no races raced yet"
    store.update_standings(sid, event_ids=[friday], excluded_race_ids=[raced])
    later = [
        c for c in multi_race.candidate_races(store, store.get_standings(sid)) if c.race_id != raced
    ]
    store.update_standings(sid, excluded_race_ids=[raced, later[0].race_id])
    assert multi_race.compute(store, sid).counted == "every race left out"


def four_races(store, event_id, riders, *, program_order=False, penalty=None):
    """One of each of the omnium's formats, Ada winning the first three and Bram the Points Race.

    Added in program order Points, Elimination, Tempo, Scratch when
    ``program_order`` is on, so the omnium's own order shows.
    """
    ada, bram, cleo = riders

    def do_scratch():
        return scratch(store, event_id, [ada, bram, cleo], name="Scratch")

    def do_tempo():
        return tempo(store, event_id, [[ada], [ada, bram, cleo]], [ada, bram, cleo], name="Tempo")

    def do_elimination():
        return elimination(store, event_id, [cleo, bram], ada, name="Elimination")

    def do_points():
        return points_race(
            store, event_id, [[bram, cleo, ada], [bram, ada, cleo]], [ada, bram, cleo],
            name="Points", penalty=penalty,
        )  # fmt: skip

    steps = [do_scratch, do_tempo, do_elimination, do_points]
    if program_order:
        steps.reverse()
    return [step() for step in steps]


def test_four_race_omnium_scores_the_rulebook_table_and_adds_the_points_race(store, riders):
    """USAC 2O3(a), 2O3(b); UCI 3.2.250, 3.2.251: 40-38-36 by place in the Scratch Race,
    Tempo Race, and Elimination, then the Points Race's own points added.

    Ada wins the first three (120). Bram is 2nd in each (114) and wins the
    Points Race (5 then 10 in the doubled final sprint, 15) against Ada's
    2 + 6 = 8: Ada 128, Bram 129, Cleo 108 + 3 + 4 = 115. The columns
    run in the order the omnium is ridden, whatever the program's.
    """
    ada, bram, cleo = riders[0:3]
    friday = night(store, riders, "Friday", "2026-10-16")
    four_races(store, friday, (ada, bram, cleo), program_order=True)
    got = multi_race.compute(store, rider_standings(store, [friday], kind=multi_race.FOUR_RACE))
    assert got.kind_label == "Four-Race Omnium" and got.state == "final" and got.refusal is None
    assert got.detail == (
        "Places in the Scratch Race, Tempo Race, and Elimination score 40, 38, 36 and so on "
        "down to 2, then 1 from 21st, and the Points Race's own points are added. "
        "A rider who does not start, does not finish, or is disqualified in any race "
        "is listed after the ranked riders, as DNF or DQ."
    )
    assert got.counted == "4 races raced over 1 event"
    (cat3,) = got.groups
    assert [c.race_name for c in cat3.columns] == ["Scratch", "Tempo", "Elimination", "Points"]
    assert rider_table(cat3.rows) == [
        (1, 2, "Bram Arden", [38, 38, 38, 15], 129, ""),
        (2, 1, "Ada Arden", [40, 40, 40, 8], 128, ""),
        (3, 3, "Cleo Arden", [36, 36, 36, 7], 115, ""),
    ]


def test_four_race_omnium_refuses_a_program_short_of_a_format_or_with_one_doubled(store, riders):
    """A ticked set is the omnium's four races per event and group, or it is
    refused and the line says which event and group is short; never guessed."""
    ada, bram, cleo = riders[0:3]
    friday = night(store, riders, "Friday", "2026-10-16")
    scratch(store, friday, [ada, bram, cleo], name="Scratch")
    first = points_race(store, friday, [[bram, ada, cleo]], [ada, bram, cleo], name="Points")
    second = points_race(store, friday, [[ada, bram, cleo]], [ada, bram, cleo], name="Points 2")
    sid = rider_standings(store, [friday], kind=multi_race.FOUR_RACE)
    got = multi_race.compute(store, sid)
    assert got.refusal.text == (
        "A Four-Race Omnium needs one Scratch Race, one Tempo Race, one Elimination, and one "
        "Points Race for every group on each event.\n"
        "\n"
        "Friday (2026-Oct-16)\n"
        "Cat 3: no Tempo Race, no Elimination, 2 Points Races"
    )
    assert got.groups == [] and got.state == "provisional"
    assert got.counted == "3 races raced over 1 event"
    # The races still to run count toward the four: a program set up for
    # the omnium passes before its first race.
    store.update_standings(sid, excluded_race_ids=[second])
    store.add_race(friday, "Tempo", "tempo", group_label="Cat 3")
    store.add_race(friday, "Elimination", "elimination", group_label="Cat 3")
    got = multi_race.compute(store, sid)
    assert got.refusal is None and len(got.groups) == 1
    assert [c.race_name for c in got.groups[0].columns] == ["Scratch", "Points"]
    assert [c.race_name for c in got.not_yet_raced] == ["Tempo", "Elimination"]
    # Another group on the night needs its own four, and only the group
    # short of them has a line.
    scratch(store, friday, [riders[5], riders[6]], group="Juniors", name="Junior Scratch")
    got = multi_race.compute(store, sid)
    assert got.refusal.nights == (
        ("Friday (2026-Oct-16)", ("Juniors: no Tempo Race, no Elimination, no Points Race",)),
    )
    assert first in {c.race_id for c in multi_race.candidate_races(store, store.get_standings(sid))}


def test_four_race_omnium_stands_on_three_races_when_the_points_race_is_left_out(store, riders):
    """USAC 2O4: a Points Race that can't be run, or that stops under 80 percent
    and can't restart, drops out and the standings after the Elimination are
    the final classification. The scorer unticks it; a program with no Points
    Race at all is still refused, and a tie with no final sprint to break it
    shares the place (USAC 1M6(a))."""
    ada, bram, cleo = riders[0:3]
    friday = night(store, riders, "Friday", "2026-10-16")
    scratch(store, friday, [ada, bram, cleo], name="Scratch")
    tempo(store, friday, [[bram], [bram], [bram, ada, cleo]], [ada, bram, cleo], name="Tempo")
    elimination(store, friday, [cleo, ada], bram, name="Elimination")
    sid = rider_standings(store, [friday], kind=multi_race.FOUR_RACE)
    got = multi_race.compute(store, sid)
    assert got.refusal.nights == (("Friday (2026-Oct-16)", ("Cat 3: no Points Race",)),)
    points = store.add_race(friday, "Points", "points", group_label="Cat 3").race_id
    got = multi_race.compute(store, sid)
    assert got.refusal is None and got.state == "provisional"
    assert [c.race_name for c in got.not_yet_raced] == ["Points"]
    assert got.counted == "3 of 4 races raced over 1 event"
    store.update_standings(sid, excluded_race_ids=[points])
    got = multi_race.compute(store, sid)
    assert got.refusal is None and got.state == "final"
    assert [c.race_name for c in got.left_out] == ["Points"]
    assert got.counted == "3 races raced over 1 event"
    assert [c.race_name for c in got.groups[0].columns] == ["Scratch", "Tempo", "Elimination"]
    # Ada 40 + 38 + 38 and Bram 38 + 40 + 40: Bram wins outright; Cleo is
    # third in each. With a tie, nothing breaks it: see below.
    assert [(r.rank, r.bib, r.per_race, r.total) for r in got.groups[0].rows] == [
        (1, 2, [38, 40, 40], 118),
        (2, 1, [40, 38, 38], 116),
        (3, 3, [36, 36, 36], 108),
    ]
    # Leaving out any of the other three is a refusal, as before.
    tempo_id = next(c.race_id for c in got.groups[0].columns if c.race_name == "Tempo")
    store.update_standings(sid, excluded_race_ids=[points, tempo_id])
    got = multi_race.compute(store, sid)
    assert got.refusal.nights == (("Friday (2026-Oct-16)", ("Cat 3: no Tempo Race",)),)


def test_a_three_race_omnium_tie_shares_the_place(store, riders):
    """With the Points Race left out (USAC 2O4) there is no final sprint, so a
    tie on the total is an equal placing (USAC 1M6(a)), not the Elimination's
    final."""
    ada, bram, cleo = riders[0:3]
    friday = night(store, riders, "Friday", "2026-10-16")
    scratch(store, friday, [ada, bram, cleo], name="Scratch")
    tempo(store, friday, [[bram], [cleo], [bram, cleo, ada]], [ada, bram, cleo], name="Tempo")
    elimination(store, friday, [cleo, bram], ada, name="Elimination")
    points = store.add_race(friday, "Points", "points", group_label="Cat 3").race_id
    sid = rider_standings(store, [friday], kind=multi_race.FOUR_RACE, excluded=[points])
    got = multi_race.compute(store, sid)
    assert got.refusal is None and got.state == "final"
    # Ada 40 + 36 + 40 and Bram 38 + 40 + 38, level on 116; Ada won the
    # Elimination's final, which breaks nothing here.
    assert [(r.rank, r.bib, r.total) for r in got.groups[0].rows] == [
        (1, 1, 116),
        (1, 2, 116),
        (3, 3, 110),
    ]


def test_four_race_refusal_reads_night_by_night_in_program_order(store, riders):
    """The nights in the ticked order, each group in the order it first races
    that night, a group with no label as "No Group"; a group with its four
    has no line."""
    friday = night(store, riders, "Friday", "2026-10-16")
    saturday = night(store, riders, "Saturday", "2026-10-17")
    four_races(store, saturday, tuple(riders[0:3]))
    scratch(store, saturday, [riders[3], riders[4]], group="", name="Open Scratch")
    scratch(store, friday, [riders[5], riders[6]], group="Juniors", name="Junior Scratch")
    scratch(store, friday, riders[0:3], name="Scratch")
    store.add_race(friday, "Elimination", "elimination", group_label="Juniors")
    store.add_race(friday, "Elimination 2", "elimination", group_label="Juniors")
    got = multi_race.compute(
        store, rider_standings(store, [friday, saturday], kind=multi_race.FOUR_RACE)
    )
    assert got.refusal.nights == (
        (
            "Friday (2026-Oct-16)",
            (
                "Juniors: no Tempo Race, 2 Eliminations, no Points Race",
                "Cat 3: no Tempo Race, no Elimination, no Points Race",
            ),
        ),
        ("Saturday (2026-Oct-17)", ("No Group: no Tempo Race, no Elimination, no Points Race",)),
    )


def test_four_race_omnium_lists_a_rider_out_of_any_race_as_dnf_after_every_finisher(store, riders):
    """USAC 2O2(c), 2O3(d); UCI 3.2.251bis: a rider who misses or abandons a race is
    out of the omnium and listed as DNF after every finisher."""
    ada, bram, cleo, dov = riders[0:4]
    friday = night(store, riders, "Friday", "2026-10-16")
    scratch(store, friday, [ada, bram, cleo], dnf=[dov], name="Scratch")
    tempo(store, friday, [[dov], [dov, ada, bram, cleo]], [ada, bram, cleo, dov], name="Tempo")
    elimination(store, friday, [cleo, bram, ada], dov, name="Elimination")
    points_race(store, friday, [[dov, ada, bram, cleo]], [ada, bram, cleo, dov], name="Points")
    got = multi_race.compute(store, rider_standings(store, [friday], kind=multi_race.FOUR_RACE))
    (cat3,) = got.groups
    assert [(r.rank, r.team, r.status) for r in cat3.rows] == [
        (1, "Ada Arden", ""),
        (2, "Bram Arden", ""),
        (3, "Cleo Arden", ""),
        (None, "Dov Arden", "DNF"),
    ]
    assert cat3.rows[-1].total == 0 + 40 + 40 + 10, "the sheet prints no figures for a DNF row"


def test_a_points_penalty_in_the_points_race_flows_into_the_omnium_total(store, riders):
    """USAC 2O3(b); UCI 3.2.251: the Points Race's total goes into the omnium
    as it stands, a penalty recorded there included."""
    ada, bram, cleo = riders[0:3]
    friday = night(store, riders, "Friday", "2026-10-16")
    four_races(store, friday, (ada, bram, cleo), penalty=(bram, 40))
    got = multi_race.compute(store, rider_standings(store, [friday], kind=multi_race.FOUR_RACE))
    (cat3,) = got.groups
    assert rider_table(cat3.rows) == [
        (1, 1, "Ada Arden", [40, 40, 40, 8], 128, ""),
        (2, 3, "Cleo Arden", [36, 36, 36, 7], 115, ""),
        (3, 2, "Bram Arden", [38, 38, 38, 15 - 40], 89, ""),
    ]


def test_the_place_table_is_the_scorers_for_omnium_by_place_and_the_rulebooks_for_four_race(
    store,
):
    by_place = store.add_standings(
        "Place", kind=multi_race.OMNIUM, rules={"points_by_place": [3, 1]}
    )
    assert multi_race.rules_for(by_place).points_by_place == (3, 1)
    assert multi_race.rules_for(store.add_standings("Plain", kind=multi_race.OMNIUM)) == (
        R.usac_omnium_rules()
    )
    four = multi_race.rules_for(store.add_standings("Four", kind=multi_race.FOUR_RACE))
    assert four == R.uci_omnium_rules() and four.must_finish_all
    assert multi_race.PLACE_KINDS == {multi_race.PLACES, multi_race.OMNIUM}
    assert [multi_race.rider_kind(k) for k in multi_race.KINDS] == [False, False, True, True]


def test_an_elimination_dnf_scores_the_place_the_race_sheet_prints(store, riders):
    """USAC 2E3(d)(i), 2E4: a rider who abandons an Elimination is out at that
    moment with the next place, and the race sheet prints it; the omnium
    scores that place, not a DNF's nothing."""
    ada, bram, cleo, dov = riders[0:4]
    friday = night(store, riders, "Friday", "2026-10-16")
    live = entered(store, friday, "elimination", R.elimination_rules(), [ada, bram, cleo, dov])
    assert live.act(dov, "dnf").ok, "out first, 4th"
    assert live.click(cleo).ok, "out next, 3rd"
    finish(live, [ada])
    (cat3,) = multi_race.compute(store, rider_standings(store, [friday])).groups
    rows = {r.team: r for r in cat3.rows}
    assert rows["Dov Arden"].per_race == [2] and rows["Cleo Arden"].per_race == [3]
    assert [r.team for r in cat3.rows][-1] == "Dov Arden", "4th ranks below 3rd, not off the table"


def test_a_running_race_is_no_column_in_a_place_kind_until_it_has_placed_everyone(store, riders):
    """An Elimination half run has placed the riders out and nobody still in:
    scored as it stands, the riders already out would lead. A place kind
    waits for the race; a race that ranks everyone as it runs (a Points
    Race, by points held) counts as it stands."""
    ada, bram, cleo, dov = riders[0:4]
    friday = night(store, riders, "Friday", "2026-10-16")
    scratch(store, friday, [ada, bram, cleo, dov], name="Scratch")
    live = entered(store, friday, "elimination", R.elimination_rules(), [ada, bram, cleo, dov])
    assert live.click(dov).ok and live.state == "running"
    sid = rider_standings(store, [friday])
    got = multi_race.compute(store, sid)
    assert [c.race_name for c in got.racing] == ["Elimination"]
    assert [c.race_name for c in got.groups[0].columns] == ["Scratch"]
    assert got.counted == "1 of 2 races raced over 1 event" and got.state == "provisional"
    assert got.groups[0].rows[0].team == "Ada Arden"
    # Complete, the race is a column and the sheet says nothing of racing.
    assert live.click(cleo).ok and live.click(ada).ok and live.state == "provisional"
    got = multi_race.compute(store, sid)
    assert got.racing == [] and len(got.groups[0].columns) == 2
    assert got.counted == "2 races raced over 1 event"
    # A Points Race one sprint in ranks everyone by points held: a column.
    live = entered(store, friday, "points", R.points_race_rules(sprint_count=2), [ada, bram])
    assert live.click(ada).ok and live.record_sprint().ok and live.state == "running"
    got = multi_race.compute(store, sid)
    assert got.racing == [] and len(got.groups[0].columns) == 3


def test_four_race_refuses_a_ticked_event_with_none_of_its_four(store, riders):
    """R-RIDER-4: a ticked event with no race of the four (empty, a Madison
    alone, or every race unticked) is refused by name, not quietly skipped."""
    ada, bram, cleo = riders[0:3]
    friday = night(store, riders, "Friday", "2026-10-16")
    saturday = night(store, riders, "Saturday", "2026-10-17")
    sunday = store.add_event("Sunday", "2026-10-18").event_id
    four_races(store, friday, (ada, bram, cleo))
    madison(store, saturday, {"Red": (riders[5], riders[6])}, {"Red": 5}, group="Cat 3")
    got = multi_race.compute(
        store, rider_standings(store, [friday, saturday, sunday], kind=multi_race.FOUR_RACE)
    )
    none = "No Scratch Race, Tempo Race, Elimination, or Points Race"
    assert got.refusal.lead == multi_race.FOUR_RACE_NEED
    assert got.refusal.nights == (
        ("Saturday (2026-Oct-17)", (none,)),
        ("Sunday (2026-Oct-18)", (none,)),
    )
    assert got.groups == [] and got.state == "provisional"


def test_the_four_race_table_is_the_rulebooks_whatever_the_stored_values(store, riders):
    ada, bram, cleo = riders[0:3]
    friday = night(store, riders, "Friday", "2026-10-16")
    four_races(store, friday, (ada, bram, cleo))
    sid = rider_standings(
        store, [friday], kind=multi_race.OMNIUM, rules={"points_by_place": [7, 5, 3]}
    )
    store.update_standings(sid, kind=multi_race.FOUR_RACE)
    (cat3,) = multi_race.compute(store, sid).groups
    assert cat3.rows[1].per_race[:3] == [40, 40, 40]


def test_a_long_place_table_is_described_not_printed_on_the_detail_line(store):
    assert multi_race.place_table_text((7, 5, 3, 2, 1)) == "7-5-3-2-1"
    assert multi_race.place_table_text(tuple(range(40, 0, -1))) == "40 places, 40 down to 1"
    assert multi_race.place_table_text(()) == "no place points"


def test_a_four_race_tail_lists_dnf_then_dq(store, riders):
    ada, bram, cleo, dov, esme = riders[0:5]
    friday = night(store, riders, "Friday", "2026-10-16")
    scratch(store, friday, [ada, bram, cleo], dnf=[dov, esme], name="Scratch")
    live = entered(
        store, friday, "tempo", R.tempo_rules(sprint_count=1), [ada, bram, cleo, dov, esme]
    )
    assert live.act(dov, "dq").ok
    finish(live, [ada, bram, cleo, esme])
    elimination(store, friday, [esme, dov, cleo, bram], ada, name="Elimination")
    points_race(store, friday, [[ada, bram, cleo, dov, esme]], [ada, bram, cleo, dov, esme])
    (cat3,) = multi_race.compute(
        store, rider_standings(store, [friday], kind=multi_race.FOUR_RACE)
    ).groups
    assert [(r.team, r.status) for r in cat3.rows][3:] == [
        ("Esme Arden", "DNF"),
        ("Dov Arden", "DQ"),
    ]


def test_two_laps_down_is_an_omnium_penalty_off_the_total_and_the_points_race_stands(store, riders):
    """USAC 2O3(e); UCI 3.2.251bis: a rider two laps down in the Scratch Race or
    Tempo Race is withdrawn, takes the next place, and loses 40 omnium
    points. The penalty is on the standings: Bram's 129 becomes 89 and he
    drops to 3rd, while the Points Race he won still shows him 1st."""
    ada, bram, cleo = riders[0:3]
    friday = night(store, riders, "Friday", "2026-10-16")
    ids = four_races(store, friday, (ada, bram, cleo))
    sid = rider_standings(store, [friday], kind=multi_race.FOUR_RACE)
    store.set_standings_penalty(sid, bram, 40)
    (cat3,) = multi_race.compute(store, sid).groups
    assert [(r.rank, r.team, r.total, r.penalty) for r in cat3.rows] == [
        (1, "Ada Arden", 128, 0),
        (2, "Cleo Arden", 115, 0),
        (3, "Bram Arden", 89, 40),
    ]
    assert cat3.rows[2].per_race == [38, 38, 38, 15], "the race figures are untouched"
    assert LiveRace(store, ids[3]).standings().by_entrant(bram).rank == 1
    # The other rider kind has no article for one: the penalty is not applied.
    store.update_standings(sid, kind=multi_race.OMNIUM, rules={})
    (cat3,) = multi_race.compute(store, sid).groups
    assert all(r.penalty == 0 for r in cat3.rows)


def test_the_demo_has_a_rider_omnium_and_a_four_race_omnium_with_a_penalty(store):
    """Both nights for the riders too: an Omnium by Place over every race but
    the Madisons, and the Four-Race Omnium over Group B's four, Group A's
    Eliminations left out, with one rider's 40-point penalty showing."""
    from madtracker.control.demo import (
        DEMO_FOUR_RACE_STANDINGS,
        DEMO_RIDER_STANDINGS,
        PENALTY_BIB,
        PENALTY_POINTS,
        seed_demo,
    )

    seed_demo(store, "2026-10-17")
    by_name = {s.name: s for s in store.list_standings()}
    riders = multi_race.compute(store, by_name[DEMO_RIDER_STANDINGS].standings_id)
    assert riders.kind == multi_race.OMNIUM and riders.state == "provisional"
    assert riders.counted == "11 of 22 races raced over 2 events"
    assert [g.group for g in riders.groups] == ["Group B", "Group A"]
    four = multi_race.compute(store, by_name[DEMO_FOUR_RACE_STANDINGS].standings_id)
    assert (
        four.kind == multi_race.FOUR_RACE and four.refusal is None and four.state == "provisional"
    )
    assert [(c.race_name, c.group) for c in four.left_out] == [
        ("Elimination", "Group A"),
        ("Elimination", "Group A"),
    ]
    (group_b,) = four.groups
    assert [c.race_name for c in group_b.columns] == [
        "2 Mile Chase",
        "4 Mile Tempo",
        "Miss-and-Out",
        "6 Mile Points",
    ]
    assert four.counted == "4 of 8 races raced over 2 events"
    (penalized,) = [r for r in group_b.rows if r.bib == int(PENALTY_BIB)]
    assert penalized.penalty == PENALTY_POINTS
    assert sum(p or 0 for p in penalized.per_race) - PENALTY_POINTS == penalized.total
    # Withdrawn 9th of 10 in the Scratch Race, placed rather than DNF, so
    # the penalty is against a placed rider: 40 - 2 * 8 = 24 place points,
    # then 32 in the Tempo Race, 36 in the Miss-and-Out, 0 in the Points
    # Race, less the 40: 24 + 32 + 36 + 0 - 40 = 52.
    assert penalized.per_race == [24, 32, 36, 0] and penalized.total == 52
