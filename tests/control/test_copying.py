"""A new file from the open one, and a new event from an earlier program (design sections 6, 12)."""

from madtracker.control import rulesets, venue
from madtracker.control.copying import CopyChoice, copy_program, copy_venue
from madtracker.scoring import rules as R
from madtracker.store import Store


def test_new_file_takes_settings_logo_rulesets_and_riders_never_events(store, event, tmp_path):
    event_id, ids = event
    venue.save(store, logo=b"PNG", name="Riverside", backup="", rider_label="names")
    doc = rulesets.apply_values(rulesets.builtin_ruleset(), lap_points=10)
    doc["name"] = "House"
    rulesets.save_ruleset(store, doc)
    rulesets.set_default_ruleset(store, "House")
    store.update_rider(ids[3], usac_license="123456")
    store.add_race(event_id, "Chase", "chase", rules=R.placings_rules().to_dict())

    with Store.open(tmp_path / "new.sqlite") as new:
        counts = copy_venue(store, new)
        assert counts == {"settings": 4, "logo": 1, "rulesets": 1, "riders": len(ids)}
        assert venue.venue_name(new) == "Riverside" and venue.show_bibs(new) is False
        assert venue.logo_setting(new) == b"PNG"
        assert rulesets.default_ruleset_name(new) == "House"
        assert new.ruleset_by_name("House").doc["points_lap_gained"] == 10
        assert new.find_rider_by_license("123456") is not None
        assert len(new.riders()) == len(ids)
        assert new.events() == [], "events are never copied"

    with Store.open(tmp_path / "bare.sqlite") as bare:
        counts = copy_venue(store, bare, CopyChoice(settings=False, logo=False, rulesets=False))
        assert counts["riders"] == len(ids) and counts["logo"] == 0
        assert venue.logo_setting(bare) is None and bare.rulesets() == []


def test_new_event_starts_from_an_earlier_program_with_empty_fields(store, event, make_race):
    event_id, ids = event
    make_race("points", [7, 12], R.SprintPointsRules(sprint_count=3), name="6 Mile Points")
    madison = make_race("madison", [3, 24, 5, 36], R.madison_rules(sprint_count=2), teams=[("Blue", 3, 24)], name="Madison")  # fmt: skip
    store.update_race(madison, usac_gender="Women")
    new = store.add_event("Next night", "2026-10-17")
    assert copy_program(store, event_id, new.event_id) == 2
    races = store.races(new.event_id)
    assert [(r.name, r.format, r.rules["sprint_count"]) for r in races] == [
        ("6 Mile Points", "points", 3),
        ("Madison", "madison", 2),
    ]
    assert [r.usac_gender for r in races] == [None, "Women"]
    assert all(store.race_entries(r.race_id) == [] for r in races)
    assert all(store.teams(r.race_id) == [] for r in races)
    assert store.entries(new.event_id) == []


def test_new_event_may_take_the_roster_bibs_fields_and_teams_too(store, event, make_race):
    """The second night of a two-day event wants
    last night's riders, bibs, fields, and teams, not only its races."""
    event_id, ids = event
    make_race("points", [7, 12], R.SprintPointsRules(sprint_count=3), name="6 Mile Points")
    make_race("madison", [3, 24, 5, 36], R.madison_rules(sprint_count=2), teams=[("Blue", 3, 24), ("Red", 5, 36)], name="Madison")  # fmt: skip
    store.set_entry_group(event_id, ids[7], "Group A")
    new = store.add_event("Day two", "2026-10-17")
    # A rider already entered keeps the entry as it is.
    store.add_entry(new.event_id, ids[12], 99)
    assert copy_program(store, event_id, new.event_id, with_roster=True) == 2
    was = {e.rider_id: (e.bib, e.local_group) for e in store.entries(event_id)}
    now = {e.rider_id: (e.bib, e.local_group) for e in store.entries(new.event_id)}
    assert set(now) == set(was) and now[ids[7]] == (7, "Group A") and now[ids[12]] == (99, None)
    points, madison = store.races(new.event_id)
    assert sorted(e.rider_id for e in store.race_entries(points.race_id)) == sorted(
        [ids[7], ids[12]]
    )
    teams = store.teams(madison.race_id)
    assert [(t.name, t.color, sorted(t.members)) for t in teams] == [
        ("Blue", "Blue", sorted([ids[3], ids[24]])),
        ("Red", "Red", sorted([ids[5], ids[36]])),
    ]
    assert store.teams(store.races(event_id)[1].race_id)[0].members, "the source keeps its teams"
