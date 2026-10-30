"""A race undone to its start list is set up again (design section 6), tried hard.

Every kind of entry a race takes is recorded and undone back to the empty
log; the race's field, teams, or count then change as Edit Race changes
them; and the race is scored to the end. A twin built fresh with the
same setup and scored the same way has no dead rows, so the two must
agree on the standings, the board feed, and the sheets' rows: nothing of
the first run reaches the result. The rest of the file is the paths
around that: the rider the dead rows name deleted and their id reused,
a merge, a duplicate, a copied program, a second window.
"""

from dataclasses import asdict

import pytest

from madtracker.control import board_feed
from madtracker.control.program import ever_scored, is_scored
from madtracker.control.race import LiveRace
from madtracker.export.summary import build_summary
from madtracker.scoring import rules as R
from madtracker.store import EntryInUseError, RaceHasActionsError, Store, StoreError

TEAMS = [("Blue", 3, 24), ("Red", 5, 36), ("Orange", 8, 12)]


@pytest.fixture
def ids(event):
    return event[1]


def ok(outcome):
    assert outcome.ok, outcome.message
    return outcome


def play(live, script):
    """Score ``live`` by a script of bibs or team names, so a twin takes the same one."""
    for step in script:
        op, *args = step
        if op == "click":
            out = live.click(live.roster.resolve(args[0]))
        elif op == "record":
            out = live.record_sprint()
        elif op == "act":
            out = live.act(live.roster.resolve(args[0]), args[1])
        elif op == "review":
            out = live.review(live.roster.resolve(args[0]), args[1])
        elif op == "move":
            out = live.move_staged(live.roster.resolve(args[0]), args[1])
        elif op == "reopen":
            out = live.reopen_sprint(args[0])
        elif op == "cancel":
            live.cancel_edit()
            continue
        elif op == "end":
            out = live.end_race()
        elif op == "shorten":
            out = live.shorten_race(args[0])
        elif op == "place_last":
            out = live.place_last(live.roster.resolve(args[0]))
        elif op == "rest":
            out = live.place_rest_together()
        elif op == "final":
            out = live.mark_final()
        elif op == "reopen_race":
            out = live.reopen()
        else:
            raise ValueError(op)
        assert out.ok, (step, out.message)


def undo_to_start(live):
    for _ in range(200):
        if not live.can_undo():
            break
        ok(live.undo())
    assert live.rows() == [] and live.staged() == [] and live.staged_tail() == []
    assert live.state == "setup" and not live.editing
    assert live.store.last_action(live.race_id) is not None, "the dead rows are kept"


def result_shape(store, race_id):
    s = build_summary(store, store.race(race_id))
    rows = [
        (
            r.place,
            r.status,
            tuple(x.name for x in r.riders),
            r.team,
            r.sprint_points,
            r.laps_gained,
            r.laps_lost,
            r.adjust_points,
            r.total_points,
            r.note,
        )
        for r in s.rows
    ]
    return (s.kind, s.rules_line, s.sprint_count, s.sprints_run, s.ended_after, s.shortened, rows)


def board_shape(live):
    layout, payload = board_feed.board_for(live.view())
    shape = asdict(payload)
    shape["header"].update(race_id=0, title="")
    return layout, shape


def standings_shape(live):
    st = live.standings()
    return [
        (live.name(r.entrant_id), r.rank, r.status, r.total_points, r.net_laps, r.placed)
        for r in st.rows
    ], st.is_complete


def same_as_twin(store, live, twin):
    assert standings_shape(live) == standings_shape(twin)
    assert board_shape(live) == board_shape(twin)
    assert result_shape(store, live.race_id) == result_shape(store, twin.race_id)
    assert {r.entrant_id for r in live.standings().rows} == set(live.roster.ids)
    assert len(store.actions(live.race_id)) > len(live.rows())
    # The log's words are read for every row, dead ones included.
    assert len(live.log_rows()) == len(store.actions(live.race_id))


def twin_of(store, race_id, teams=None):
    """A race set up as ``race_id`` now is, with no log."""
    race = store.race(race_id)
    twin = store.add_race(
        race.event_id,
        race.name + " twin",
        race.format,
        rules=race.rules,
        group_label=race.group_label,
    )
    for e in store.race_entries(race_id):
        store.add_race_entry(twin.race_id, e.rider_id)
    for t in store.teams(race_id):
        team = store.add_team(twin.race_id, t.name, color=t.color, color_hex=t.color_hex)
        for rider_id in t.members:
            store.add_team_member(team.team_id, rider_id)
    return LiveRace(store, twin.race_id)


# ----- every entry kind, undone, then the setup changed ----------------------


def house_points(house, n):
    return house.points(n)


SCENARIOS = {
    # Points Race: every kind of entry, then End Race.
    "points ended": (
        "points",
        lambda house: house.points(4),
        [7, 12, 33, 9, 19],
        [
            ("click", "7"),
            ("click", "12"),
            ("click", "33"),
            ("record",),
            ("act", "9", "lap_gained"),
            ("act", "9", "lap_not_counted"),
            ("act", "19", "lap_lost"),
            ("act", "7", "points_penalty:5"),
            ("act", "12", "withdrawn"),
            ("act", "33", "dnf"),
            ("act", "33", "dq"),
            ("end",),
        ],
    ),
    # Points Race: shortened, with a DNS before the start.
    "points shortened": (
        "points",
        lambda house: house.points(4),
        [7, 12, 33, 9, 19],
        [
            ("act", "19", "dns"),
            ("click", "7"),
            ("click", "12"),
            ("record",),
            ("shorten", 2),
            ("click", "33"),
            ("click", "7"),
            ("click", "12"),
            ("click", "9"),
        ],
    ),
    # Points Race: a correction of Sprint 1 after Sprint 2, then everything undone.
    "points corrected": (
        "points",
        lambda house: house.points(4),
        [7, 12, 33, 9, 19],
        [
            ("click", "7"),
            ("click", "12"),
            ("record",),
            ("click", "33"),
            ("click", "9"),
            ("record",),
            ("reopen", 1),
            ("move", "12", "move_up"),
            ("record",),
        ],
    ),
    # Points Race: marked final, reopened, then everything undone.
    "points final and reopened": (
        "points",
        lambda house: house.points(2),
        [7, 12, 33],
        [
            ("click", "7"),
            ("record",),
            ("click", "12"),
            ("click", "7"),
            ("click", "33"),
            ("final",),
            ("reopen_race",),
        ],
    ),
    "tempo": (
        "tempo",
        lambda house: R.tempo_rules(sprint_count=3),
        [7, 12, 33, 9],
        [("click", "7"), ("record",), ("act", "33", "withdrawn"), ("click", "12"), ("record",)],
    ),
    "elimination": (
        "elimination",
        lambda house: house.elimination(),
        [7, 12, 33, 9, 19],
        [("click", "7"), ("act", "12", "dnf"), ("click", "33"), ("review", "33", "dq")],
    ),
    "chase placed from both ends": (
        "chase",
        lambda house: R.placings_rules(),
        [7, 12, 33, 9, 19],
        [("click", "7"), ("place_last", "19"), ("rest",)],
    ),
    "win and out": (
        "win_and_out",
        lambda house: R.win_and_out_rules(2),
        [7, 12, 33, 9],
        [("click", "7"), ("act", "12", "dnf")],
    ),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_each_entry_kind_undone_to_the_start_then_a_new_field_and_count(
    store, make_race, ids, house, name
):
    fmt, rules_of, bibs, first_run = SCENARIOS[name]
    rules = rules_of(house)
    race_id = make_race(fmt, bibs, rules)
    live = LiveRace(store, race_id)
    play(live, first_run)
    assert is_scored(store, store.race(race_id))
    undo_to_start(live)
    race = store.race(race_id)
    assert not is_scored(store, race) and ever_scored(store, race)
    # Edit Race: the last rider out, a new one in, and a count of two
    # where the format takes a count.
    out, new = ids[bibs[-1]], ids[24]
    field = [ids[b] for b in bibs[:-1]] + [new]
    changed = dict(race.rules)
    if "sprint_count" in changed:
        changed["sprint_count"] = 2
    if "places" in changed:
        changed["places"] = 1
    store.save_race(race.event_id, race_id, {"rules": changed}, field)
    live.reload()
    assert out not in live.roster.ids and new in live.roster.ids
    assert live.undo_text() == "Nothing to Undo" and live.staged() == []
    assert live.state == "setup" and live.standings().rows
    # The second run over the new field: the new rider wins the first
    # sprint or lap, and the rest follow in bib order.
    now = ["24", *(str(b) for b in bibs[:-1])]
    second_run = {
        "points": [("click", "24"), ("click", now[1]), ("record",)] + [("click", b) for b in now],
        "tempo": [("click", "24"), ("record",)] + [("click", b) for b in now],
        "elimination": [("click", b) for b in now[1:-1]] + [("click", "24")],
        "chase": [("click", b) for b in now],
        "win_and_out": [("click", b) for b in now],
    }[fmt]
    play(live, second_run)
    assert live.standings().is_complete and live.state == "provisional"
    ok(live.mark_final())
    twin = twin_of(store, race_id)
    play(twin, [*second_run, ("final",)])
    same_as_twin(store, live, twin)


def test_a_madison_undone_to_the_start_with_a_team_made_over_and_its_id_reused(
    store, make_race, ids, house
):
    """A team whose riders change is taken out and the next team added
    takes its id, so the dead rows name the new team: it starts from nothing."""
    race_id = make_race("madison", [3, 24, 5, 36, 8, 12], house.madison(3), teams=TEAMS)
    live = LiveRace(store, race_id)
    play(
        live,
        [
            ("click", "Orange"),
            ("click", "Blue"),
            ("record",),
            ("act", "Orange", "lap_gained"),
            ("act", "Red", "points_penalty:3"),
        ],
    )
    orange = live.roster.resolve("Orange")
    assert live.standings().by_entrant(orange).total_points == 15
    undo_to_start(live)
    race = store.race(race_id)
    assert not is_scored(store, race)
    teams = [
        ("Blue", "Blue", None, [ids[3], ids[24]]),
        ("Red", "Red", None, [ids[5], ids[36]]),
        ("Green", "Green", None, [ids[8], ids[7]]),
    ]
    store.save_race(
        race.event_id, race_id, {}, [ids[3], ids[24], ids[5], ids[36], ids[8], ids[7]], teams
    )
    live.reload()
    green = live.roster.resolve("Green")
    assert green == orange, "the file hands the taken-out team's id to the new one"
    assert live.roster.resolve("Orange") is None
    assert live.undo_text() == "Nothing to Undo"
    assert live.standings().by_entrant(green).total_points == 0
    second_run = [
        ("click", "Green"),
        ("click", "Red"),
        ("record",),
        ("act", "Blue", "lap_gained"),
        ("click", "Blue"),
        ("click", "Green"),
        ("record",),
        ("click", "Red"),
        ("click", "Blue"),
        ("click", "Green"),
        ("final",),
    ]
    play(live, second_run)
    twin = twin_of(store, race_id)
    play(twin, second_run)
    same_as_twin(store, live, twin)
    assert live.standings().by_entrant(green).total_points > 0


# ----- the rider the dead rows name -----------------------------------------


def test_the_rider_a_dead_row_names_can_leave_and_be_deleted_and_their_id_reused(
    store, make_race, ids, event
):
    """Out of the field, the rider is in no race with an entry (section 12),
    so Edit Riders deletes them; the next rider added takes the id. The
    dead rows now name that rider, and nothing reads them but the log's
    words, so the race scores as a fresh one."""
    from madtracker.control.roster import enter_on_roster

    event_id, _ = event
    zed = store.add_rider("Zed", "Zulu")
    enter_on_roster(store, event_id, zed.rider_id, 99)
    race_id = make_race("chase", [7, 12], R.placings_rules())
    store.add_race_entry(race_id, zed.rider_id)
    live = LiveRace(store, race_id)
    play(live, [("click", "99"), ("click", "7"), ("click", "12")])
    assert live.state == "provisional"
    assert store.raced_in(zed.rider_id) == "Test Race Night"
    undo_to_start(live)
    assert store.raced_in(zed.rider_id) == "Test Race Night", "still in the field"
    with pytest.raises(EntryInUseError):
        store.delete_rider(zed.rider_id)
    store.save_race(event_id, race_id, {}, [ids[7], ids[12]])
    assert store.raced_in(zed.rider_id) is None
    store.remove_entry(event_id, zed.rider_id)
    store.delete_rider(zed.rider_id)
    new = store.add_rider("Yara", "Young")
    assert new.rider_id == zed.rider_id, "SQLite hands the freed id on"
    enter_on_roster(store, event_id, new.rider_id, 98)
    store.save_race(event_id, race_id, {}, [ids[7], ids[12], new.rider_id])
    live.reload()
    assert live.name(new.rider_id) == "Yara Young"
    play(live, [("click", "7"), ("click", "98"), ("click", "12"), ("final",)])
    twin = twin_of(store, race_id)
    play(twin, [("click", "7"), ("click", "98"), ("click", "12"), ("final",)])
    same_as_twin(store, live, twin)
    # The dead row's words name whoever wears the id now; the live log is
    # what the result is read from.
    dead = [row for row in live.log_rows() if row.voided]
    assert dead and all("Yara Young" in row.text for row in dead)


def test_merge_and_delete_follow_the_field_not_the_dead_rows(store, make_race, ids, event):
    event_id, _ = event
    race_id = make_race("chase", [7, 12, 33], R.placings_rules())
    live = LiveRace(store, race_id)
    play(live, [("click", "7"), ("act", "12", "dnf")])
    undo_to_start(live)
    assert store.merge_refusal(ids[7]) and store.merge_refusal(ids[12])
    assert store.raced_in(ids[33]) == "Test Race Night"
    store.save_race(event_id, race_id, {}, [ids[12], ids[33]])
    assert store.merge_refusal(ids[7]) == ""
    assert store.merge_refusal(ids[12]) and store.raced_in(ids[33]) == "Test Race Night"
    spare = store.add_rider("Maya", "Petrakis")
    store.merge_riders(spare.rider_id, ids[7])
    assert store.rider(spare.rider_id).first_name == "Maya"


def test_a_race_undone_to_its_start_has_nothing_announced_until_ridden_again(store, make_race, ids):
    """The sheet's "announced" time is the first time the result went
    provisional in this run: a partial Undo and a click back keep it, an
    Undo to the start list clears it, and the next result stamps its own."""
    race_id = make_race("chase", [7, 12, 33], R.placings_rules())
    live = LiveRace(store, race_id)
    play(live, [("act", "7", "dnf"), ("click", "12"), ("click", "33")])
    first = store.race(race_id).announced_utc
    assert store.race(race_id).state == "provisional" and first is not None
    ok(live.undo())
    assert store.race(race_id).state == "running"
    play(live, [("click", "33")])
    assert store.race(race_id).announced_utc == first
    undo_to_start(live)
    assert store.race(race_id).announced_utc is None
    play(live, [("click", "12"), ("click", "7"), ("click", "33")])
    again = store.race(race_id)
    assert again.state == "provisional" and again.announced_utc is not None
    assert again.announced_utc >= first


# ----- the program around it --------------------------------------------------


def test_a_copy_or_duplicate_of_an_undone_race_is_a_fresh_race(store, make_race, ids, event):
    from madtracker.control.copying import copy_program

    event_id, _ = event
    race_id = make_race("chase", [7, 12, 33], R.placings_rules())
    live = LiveRace(store, race_id)
    play(live, [("act", "7", "dnf")])
    undo_to_start(live)
    with pytest.raises(RaceHasActionsError):
        store.delete_race(race_id)
    with pytest.raises(EntryInUseError):
        store.delete_event(event_id)
    later = store.add_event("Later Night", "2026-10-17")
    assert copy_program(store, event_id, later.event_id, with_roster=True) == 1
    copy = store.races(later.event_id)[0]
    assert store.last_action(copy.race_id) is None
    assert not is_scored(store, copy) and not ever_scored(store, copy)
    assert {e.rider_id for e in store.race_entries(copy.race_id)} == {ids[7], ids[12], ids[33]}
    store.delete_race(copy.race_id)
    store.delete_event(later.event_id)


def test_a_rename_and_a_regroup_reach_an_undone_race(store, make_race, ids, event):
    from madtracker.control import groups

    event_id, _ = event
    race = store.add_race(event_id, "Juniors Chase", "chase", group_label="Juniors")
    store.set_entry_group(event_id, ids[7], "Juniors")
    store.add_race_entry(race.race_id, ids[7])
    live = LiveRace(store, race.race_id)
    play(live, [("act", "7", "dns")])
    use = next(u for u in groups.group_uses(store, event_id) if u.label == "Juniors")
    assert use.raced
    undo_to_start(live)
    use = next(u for u in groups.group_uses(store, event_id) if u.label == "Juniors")
    assert not use.raced
    groups.rename_group(store, event_id, use, "Junior Men")
    assert store.race(race.race_id).group_label == "Junior Men"
    store.set_entry_group(event_id, ids[12], "Junior Men")
    groups.follow_group(store, event_id, [ids[12]], None)
    live.reload()
    assert set(live.roster.ids) == {ids[7], ids[12]}


def test_a_second_window_meets_the_edit_as_a_conflict_and_reloads(store, make_race, ids, tmp_path):
    race_id = make_race("chase", [7, 12, 33], R.placings_rules())
    live = LiveRace(store, race_id)
    other_store = Store.open(store.path)
    try:
        other = LiveRace(other_store, race_id)
        play(live, [("click", "7"), ("click", "12"), ("click", "33")])
        assert live.state == "provisional"
        undo_to_start(live)
        other.reload()
        assert other.roster.ids == live.roster.ids
        store.save_race(store.race(race_id).event_id, race_id, {}, [ids[12], ids[33]])
        live.reload()
        # The other window still shows the old field; its next write
        # meets the cleared settings as a conflict and reloads.
        with pytest.raises(StoreError):
            other.click(ids[12])
        assert other.roster.ids == live.roster.ids == [ids[12], ids[33]]
        ok(other.click(ids[12]))
        live.reload()
        assert live.staged() == [[ids[12]]]
    finally:
        other_store.close()
