"""Store behavior: riders, events, entries, races, teams, the action log, settings, backup."""

import sqlite3

import pytest

from madtracker.store import (
    Action,
    DuplicateEntryError,
    DuplicateLicenseError,
    DuplicateRulesetNameError,
    DuplicateTeamNameError,
    DuplicateUciError,
    EntryInUseError,
    NotFoundError,
    RaceHasActionsError,
    Store,
    StoreError,
    VoidError,
    disk_refusal,
)
from madtracker.store.store import ConflictError


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "t.sqlite")
    yield s
    s.close()


@pytest.fixture
def race(store):
    """An event with two entered riders and one race both are in."""
    ann = store.add_rider("Ann", "Alpha", usac_license="100")
    bob = store.add_rider("Bob", "Bravo", usac_license="200")
    event = store.add_event("Race Night 1", "2026-09-26")
    store.add_entry(event.event_id, ann.rider_id, bib=1, local_group="GroupA")
    store.add_entry(event.event_id, bob.rider_id, bib=2, local_group="GroupB")
    r = store.add_race(event.event_id, "Chase", "placings", group_label="GroupA")
    store.add_race_entry(r.race_id, ann.rider_id)
    store.add_race_entry(r.race_id, bob.rider_id)
    return r


# ----- riders ----------------------------------------------------------------


def test_rider_round_trip_and_search(store):
    r = store.add_rider(
        " Jane ", "Jaskula", usac_license=" 12345 ", uci_id="10012345678", birth_year=1990
    )
    assert r.first_name == "Jane" and r.usac_license == "12345"
    assert store.rider(r.rider_id) == r
    assert store.find_rider_by_license("12345") == r
    assert store.find_rider_by_license("") is None
    assert store.search_riders("jan") == [r]
    assert store.search_riders("JASK") == [r]
    assert store.search_riders("zzz") == []
    assert store.search_riders("") == [r]
    assert store.search_riders("%") == []
    # The one filter rule: each word anywhere in the first or last name.
    assert store.search_riders("Jane J") == [r]
    assert store.search_riders("kula") == [r]
    assert store.search_riders("jane zzz") == []
    assert store.search_riders("#7") == [], "a bib means nothing where the list has none"


def test_a_usac_license_is_stored_as_usac_prints_it(store):
    from madtracker.inputs import LICENSE_RULE

    typed = store.add_rider("Ada", "Quill", usac_license="0710004")
    assert typed.usac_license == "710004"
    assert store.find_rider_by_license("0710004") == typed
    assert store.find_rider_by_license("710 004") == typed
    with pytest.raises(DuplicateLicenseError):
        store.add_rider("Ada", "Quill", usac_license="710004")
    assert store.update_rider(typed.rider_id, usac_license="000").usac_license is None
    with pytest.raises(ValueError, match=LICENSE_RULE[:20]):
        store.add_rider("Ava", "Lindqvist", usac_license="INTL-CAN")
    with pytest.raises(ValueError, match=LICENSE_RULE[:20]):
        store.update_rider(typed.rider_id, usac_license="pending")
    assert store.find_rider_by_license("INTL-CAN") is None


def test_a_uci_id_belongs_to_one_rider(store):
    a = store.add_rider("Ann", "Alpha", uci_id="10012345678")
    b = store.add_rider("Bo", "Beta")
    c = store.add_rider("Cy", "Gamma", uci_id="10087654321")
    with pytest.raises(DuplicateUciError, match="10012345678 already belongs to rider"):
        store.add_rider("Dee", "Delta", uci_id="10012345678")
    with pytest.raises(DuplicateUciError):
        store.update_rider(b.rider_id, uci_id="10012345678")
    a = store.update_rider(a.rider_id, uci_id="10012345678")
    assert a.uci_id == "10012345678"
    with pytest.raises(DuplicateUciError):
        store.merge_riders(b.rider_id, a.rider_id, values={"uci_id": c.uci_id})
    assert store.rider(a.rider_id) == a, "a refused merge changes nothing"
    # The dropped record's own UCI ID moves to the kept one.
    assert store.merge_riders(b.rider_id, a.rider_id).uci_id == "10012345678"


def test_rider_update_and_license_uniqueness(store):
    a = store.add_rider("A", "One", usac_license="1")
    b = store.add_rider("B", "Two", usac_license="")
    assert b.usac_license is None
    updated = store.update_rider(b.rider_id, usac_license="2", birth_year=1990)
    assert updated.usac_license == "2" and updated.birth_year == 1990
    assert updated.updated_utc >= b.updated_utc
    with pytest.raises(DuplicateLicenseError):
        store.update_rider(b.rider_id, usac_license="1")
    with pytest.raises(DuplicateLicenseError):
        store.add_rider("C", "Three", usac_license="1")
    # Foreign riders without a license never collide with each other.
    store.add_rider("D", "Four")
    store.add_rider("E", "Five")
    with pytest.raises(ValueError):
        store.update_rider(a.rider_id, created_utc="never")
    with pytest.raises(NotFoundError):
        store.rider(999)


# ----- events and entries ----------------------------------------------------


def test_events_list_newest_first_and_validate_date(store):
    old = store.add_event("Old", "2025-05-01")
    new = store.add_event("New", "2026-05-01", venue="Velodrome Park")
    assert [m.event_id for m in store.events()] == [new.event_id, old.event_id]
    with pytest.raises(ValueError):
        store.add_event("Bad", "26/05/2026")
    assert store.update_event(old.event_id, name="Older").name == "Older"


def test_no_two_events_share_a_name_and_date(store):
    first = store.add_event("Race Night", "2026-05-01")
    with pytest.raises(StoreError, match="already exists"):
        store.add_event("  race night ", "2026-05-01")
    other = store.add_event("Race Night", "2026-05-08")
    # A rename or a new date is refused onto another event, as an add is.
    with pytest.raises(StoreError, match="already exists"):
        store.update_event(other.event_id, event_date="2026-05-01")
    second = store.add_event("Second Night", "2026-05-01")
    with pytest.raises(StoreError, match="already exists"):
        store.update_event(second.event_id, name=" RACE NIGHT ")
    assert store.event(second.event_id).name == "Second Night"
    # The event itself is not its own twin: saving it unchanged, or with
    # only its case changed, goes through.
    assert store.update_event(first.event_id, name="Race Night", notes="x").notes == "x"
    assert store.update_event(first.event_id, name="RACE NIGHT ").name == "RACE NIGHT"


def test_bib_may_repeat_or_be_empty_and_rider_once_per_event(store):
    a = store.add_rider("A", "One")
    b = store.add_rider("B", "Two")
    c = store.add_rider("C", "Three")
    event = store.add_event("M", "2026-01-01")
    other = store.add_event("N", "2026-01-02")
    store.add_entry(event.event_id, a.rider_id, bib=5)
    # Riders who never share a race may wear one number; the race field
    # refuses a clash (control/roster.py), not the roster.
    assert store.add_entry(event.event_id, b.rider_id, bib=5).bib == 5
    with pytest.raises(DuplicateEntryError):
        store.add_entry(event.event_id, a.rider_id, bib=6)
    store.add_entry(other.event_id, b.rider_id, bib=5)
    # No bib yet: the venue hands the numbers out after registration.
    assert store.add_entry(event.event_id, c.rider_id, bib=None).bib is None
    assert store.change_bib(event.event_id, b.rider_id, 7).bib == 7
    assert store.change_bib(event.event_id, b.rider_id, 7).bib == 7  # same bib is fine
    # A rider without a bib sorts after every numbered one.
    assert [e.bib for e in store.entries(event.event_id)] == [5, 7, None]
    assert store.change_bib(event.event_id, c.rider_id, 5).bib == 5
    assert sorted(e.bib for e in store.entries(event.event_id)) == [5, 5, 7]
    assert store.change_bib(event.event_id, c.rider_id, None).bib is None
    with pytest.raises(ValueError):
        store.add_entry(other.event_id, a.rider_id, bib=0)
    with pytest.raises(ValueError):
        store.change_bib(event.event_id, a.rider_id, -1)
    # A failed write leaves no transaction open and the next write works.
    assert store.connection.in_transaction is False
    store.remove_entry(event.event_id, b.rider_id)
    assert [e.bib for e in store.entries(event.event_id)] == [5, None]


def test_entry_group_belongs_to_the_entry(store):
    """The group is a fact about one event; the rider record has none (design section 6)."""
    r = store.add_rider("A", "One")
    first = store.add_event("M1", "2026-01-01")
    second = store.add_event("M2", "2026-01-08")
    assert (
        store.add_entry(first.event_id, r.rider_id, bib=1, local_group="GroupC").local_group
        == "GroupC"
    )
    assert store.add_entry(second.event_id, r.rider_id, bib=1).local_group is None
    assert store.set_entry_group(second.event_id, r.rider_id, "GroupB").local_group == "GroupB"
    assert store.entry(first.event_id, r.rider_id).local_group == "GroupC"


# ----- races, entries, teams -------------------------------------------------


def test_race_fields_sequence_and_state(store):
    event = store.add_event("M", "2026-01-01")
    r1 = store.add_race(
        event.event_id, "Chase", "placings", rules={"laps": 8}, rules_preset="house"
    )
    r2 = store.add_race(event.event_id, "Elim", "elimination")
    assert (r1.seq_in_event, r2.seq_in_event) == (1, 2)
    assert r1.rules == {"laps": 8} and r1.state == "setup"
    assert [r.race_id for r in store.races(event.event_id)] == [r1.race_id, r2.race_id]
    updated = store.update_race(
        r1.race_id, rules={"laps": 10}, usac_discipline="SR", seq_in_event=3
    )
    assert updated.rules == {"laps": 10} and updated.usac_discipline == "SR"
    assert [r.race_id for r in store.races(event.event_id)] == [r2.race_id, r1.race_id]
    with pytest.raises(ValueError):
        store.update_race(r1.race_id, state="final")

    running = store.set_state(r1.race_id, "running")
    assert running.state == "running" and running.announced_utc is None
    provisional = store.set_state(r1.race_id, "provisional")
    assert provisional.announced_utc is not None
    final = store.set_state(r1.race_id, "final")
    assert final.announced_utc == provisional.announced_utc
    with pytest.raises(ValueError):
        store.set_state(r1.race_id, "done")


def test_race_entries_resolve_bib_through_event_entry(store, race):
    entries = store.race_entries(race.race_id)
    assert [(e.bib, e.last_name, e.local_group) for e in entries] == [
        (1, "Alpha", "GroupA"),
        (2, "Bravo", "GroupB"),
    ]
    ann = entries[0].rider_id
    with pytest.raises(DuplicateEntryError):
        store.add_race_entry(race.race_id, ann)
    stranger = store.add_rider("Zed", "Zulu")
    with pytest.raises(NotFoundError):
        store.add_race_entry(race.race_id, stranger.rider_id)
    # Removing the roster entry drops the rider from an unscored race's field
    # (docs/design.md section 12, Removing riders).
    store.remove_entry(race.event_id, ann)
    assert [e.bib for e in store.race_entries(race.race_id)] == [2]


def test_remove_entry_is_refused_once_the_rider_is_in_a_scored_race(store, race):
    entries = store.race_entries(race.race_id)
    ann = entries[0].rider_id
    store.append_action(race.race_id, "status", {"entrant_id": ann, "status": "DNS"}, 1)
    with pytest.raises(EntryInUseError, match="has been scored"):
        store.remove_entry(race.event_id, ann)
    # The entry, the field and the log are exactly as they were.
    assert store.entry(race.event_id, ann).rider_id == ann
    assert [e.rider_id for e in store.race_entries(race.race_id)][0] == ann


def test_remove_entry_drops_the_rider_from_a_race_undone_to_its_start(store, race):
    """A void on every row leaves no entry standing: the field is open
    again, as the race dialog's is. The rider's record, the event and the
    race themselves stay, since the dead rows name them."""
    ann, bob = (e.rider_id for e in store.race_entries(race.race_id))
    action_id = store.append_action(race.race_id, "status", {"entrant_id": ann, "status": "DNS"}, 1)
    assert store.has_live_actions(race.race_id)
    store.void_action(race.race_id, action_id)
    assert not store.has_live_actions(race.race_id)
    assert store.last_action(race.race_id) is not None
    store.remove_entry(race.event_id, ann)
    assert [e.rider_id for e in store.race_entries(race.race_id)] == [bob]
    # The strict rules still count the dead rows.
    with pytest.raises(RaceHasActionsError):
        store.delete_race(race.race_id)
    with pytest.raises(EntryInUseError, match="scored race"):
        store.delete_event(race.event_id)
    assert store.raced_in(bob) == "Race Night 1"
    with pytest.raises(EntryInUseError, match="has raced"):
        store.delete_rider(bob)
    assert store.merge_refusal(bob)
    # Out of every field, the rider the dead rows name is no longer held
    # by them: the live log is what is replayed, and a dead row is not.
    assert store.raced_in(ann) is None


def test_has_live_actions_sees_through_voids_only(store, race):
    ann = store.race_entries(race.race_id)[0].rider_id
    assert not store.has_live_actions(race.race_id)
    first = store.append_action(race.race_id, "status", {"entrant_id": ann, "status": "DNS"}, 1)
    second = store.append_action(race.race_id, "status", {"entrant_id": ann, "status": "DQ"}, 1)
    store.void_action(race.race_id, second)
    assert store.has_live_actions(race.race_id), "the first entry stands"
    store.void_action(race.race_id, first)
    assert not store.has_live_actions(race.race_id)
    # A race that left setup is scored whatever its log holds.
    store.set_state(race.race_id, "running")
    with pytest.raises(EntryInUseError, match="has been scored"):
        store.remove_entry(race.event_id, ann)


def test_remove_entry_drops_the_rider_from_unscored_teams_and_leaves_other_events(store, race):
    entries = store.race_entries(race.race_id)
    ann, bob = entries[0].rider_id, entries[1].rider_id
    team = store.add_team(race.race_id, "Red", color="Red")
    store.add_team_member(team.team_id, ann)
    store.add_team_member(team.team_id, bob)
    other = store.add_event("Other night", "2026-02-02")
    store.add_entry(other.event_id, ann, 9)
    store.remove_entry(race.event_id, ann)
    assert store.team(team.team_id).members == (bob,)
    assert store.entry(other.event_id, ann).bib == 9


def test_merge_moves_entries_and_unscored_races_and_fills_blank_ids(store, race):
    """Two records of one person: the spare one's roster entries and its
    places in unscored races move over with their bibs, and the ids the
    kept record lacks come from it (design section 12)."""
    keep = store.add_rider("José", "Garcia")
    spare = store.add_rider(
        "Jose", "Garcia", usac_license="300", uci_id="10012345678", birth_year=1990
    )
    store.add_entry(race.event_id, spare.rider_id, bib=7, local_group="GroupA")
    store.add_race_entry(race.race_id, spare.rider_id)
    team = store.add_team(race.race_id, "Red", color="Red")
    store.add_team_member(team.team_id, spare.rider_id)
    earlier = store.add_event("Race Night 0", "2026-09-19")
    store.add_entry(earlier.event_id, keep.rider_id, bib=40)
    assert store.merge_refusal(spare.rider_id, keep.rider_id) == ""

    kept = store.merge_riders(keep.rider_id, spare.rider_id)
    assert (kept.first_name, kept.usac_license, kept.uci_id, kept.birth_year) == (
        "José",
        "300",
        "10012345678",
        1990,
    )
    with pytest.raises(NotFoundError):
        store.rider(spare.rider_id)
    entry = store.entry(race.event_id, keep.rider_id)
    assert (entry.bib, entry.local_group) == (7, "GroupA")
    assert keep.rider_id in [e.rider_id for e in store.race_entries(race.race_id)]
    assert store.team(team.team_id).members == (keep.rider_id,)
    assert store.entry(earlier.event_id, keep.rider_id).bib == 40
    assert store.find_rider_by_license("300").rider_id == keep.rider_id


def test_merge_keeps_the_ids_already_on_the_kept_rider(store):
    keep = store.add_rider("Ann", "Alpha", usac_license="100")
    spare = store.add_rider("Ann", "Alpha", usac_license="101", birth_year=1980)
    kept = store.merge_riders(keep.rider_id, spare.rider_id)
    assert (kept.usac_license, kept.birth_year) == ("100", 1980)
    assert store.find_rider_by_license("101") is None


def test_merge_is_refused_for_a_rider_in_a_scored_race(store, race):
    ann, bob = (e.rider_id for e in store.race_entries(race.race_id))
    spare = store.add_rider("Ann", "Alpha")
    store.append_action(race.race_id, "status", {"entrant_id": ann, "status": "DNS"}, 1)
    text = "has raced in Race Night 1; merge the other record into this one instead"
    assert store.merge_refusal(ann) == f"rider {ann} {text}"
    with pytest.raises(EntryInUseError, match=text):
        store.merge_riders(spare.rider_id, ann)
    assert store.rider(ann).rider_id == ann
    assert [e.rider_id for e in store.race_entries(race.race_id)] == [ann, bob]
    assert len(store.actions(race.race_id)) == 1


def test_merge_settles_a_roster_both_are_on(store, race):
    """The kept entry stays and fills its blanks from the spare's; a race
    both are in keeps one place, the kept rider's."""
    ann, bob = (e.rider_id for e in store.race_entries(race.race_id))
    spare = store.add_rider("Ann", "Alpha")
    event = store.add_event("Race Night 2", "2026-10-03")
    store.add_entry(event.event_id, ann, bib=None, local_group="GroupA")
    store.add_entry(event.event_id, spare.rider_id, bib=9, local_group="GroupB")
    tonight = store.add_race(event.event_id, "Scratch", "placings")
    store.add_race_entry(tonight.race_id, ann)
    store.add_race_entry(tonight.race_id, spare.rider_id)
    assert store.merge_refusal(spare.rider_id, ann) == ""
    store.merge_riders(ann, spare.rider_id)
    entry = store.entry(event.event_id, ann)
    assert (entry.bib, entry.local_group) == (9, "GroupA")
    assert [e.rider_id for e in store.race_entries(tonight.race_id)] == [ann]
    assert [e.rider_id for e in store.entries(event.event_id)] == [ann]
    assert store.merge_refusal(ann, ann) == "choose another rider to keep"


def test_merge_applies_the_values_chosen_in_one_transaction(store):
    """Merge riders' choices override the kept-wins rules: the merged record
    reads as the page did, whichever row survives."""
    keep = store.add_rider("Ann", "Alpha", usac_license="100").rider_id
    spare = store.add_rider("Anne", "Alpha", usac_license="101").rider_id
    other = store.add_rider("Bo", "Beta").rider_id
    event = store.add_event("Night", "2026-10-03").event_id
    store.add_entry(event, keep, 7, local_group="Group A")
    store.add_entry(event, spare, 9, local_group="Group B")
    store.add_entry(event, other, 11)
    race = store.add_race(event, "Madison", "madison").race_id
    blue = store.add_team(race, "Blue", color="Blue").team_id
    red = store.add_team(race, "Red", color="Red").team_id
    for team, rid in ((blue, keep), (red, spare), (red, other)):
        store.add_race_entry(race, rid)
        store.add_team_member(team, rid)
    kept = store.merge_riders(
        keep,
        spare,
        values={"first_name": "Anne", "usac_license": "101"},
        entries={event: {"bib": 9, "local_group": "Group B"}},
        teams={race: red},
    )
    assert (kept.first_name, kept.usac_license) == ("Anne", "101")
    entry = store.entry(event, keep)
    assert (entry.bib, entry.local_group) == (9, "Group B")
    assert set(store.team(red).members) == {keep, other}
    assert store.team(blue).members == ()
    with pytest.raises(ValueError, match="unknown rider fields"):
        store.merge_riders(keep, other, values={"bib": 3})


def test_two_records_that_have_both_raced_are_not_merged(store, race):
    ann, bob = (e.rider_id for e in store.race_entries(race.race_id))
    store.append_action(race.race_id, "status", {"entrant_id": ann, "status": "DNS"}, 1)
    assert store.merge_refusal(ann, bob) == (
        f"rider {ann} and rider {bob} have both raced, so they can't be merged"
    )
    spare = store.add_rider("Ann", "Alpha")
    assert store.merge_refusal(ann, spare.rider_id).endswith(
        "merge the other record into this one instead"
    )


def test_rider_who_raced_is_never_deleted(store, race):
    ann, bob = (e.rider_id for e in store.race_entries(race.race_id))
    store.append_action(race.race_id, "status", {"entrant_id": ann, "status": "DNS"}, 1)
    with pytest.raises(EntryInUseError, match="has raced in Race Night 1"):
        store.delete_rider(ann)
    assert store.update_rider(ann, first_name="Anne").first_name == "Anne"
    # The corrected name is the person's, so it reaches the race's field too.
    assert store.race_entries(race.race_id)[0].first_name == "Anne"
    stranger = store.add_rider("Zed", "Zulu")
    store.delete_rider(stranger.rider_id)


def test_a_rider_who_has_not_raced_is_deleted_off_rosters_and_fields(store):
    """A tick onto a roster or a place in a race not yet run names nobody in a log."""
    event = store.add_event("Race Night 1", "2026-09-26")
    zed = store.add_rider("Zed", "Zulu")
    store.add_entry(event.event_id, zed.rider_id, bib=4)
    race = store.add_race(event.event_id, "Madison", "madison")
    store.add_race_entry(race.race_id, zed.rider_id)
    team = store.add_team(race.race_id, "Red", color="Red")
    store.add_team_member(team.team_id, zed.rider_id)
    assert store.raced_in(zed.rider_id) is None
    store.delete_rider(zed.rider_id)
    assert store.entries(event.event_id) == [] and store.race_entries(race.race_id) == []
    assert store.teams(race.race_id)[0].members == ()


def test_event_series_round_trips(store):
    event = store.add_event("Night 3", "2026-01-03", series=" Winter Series ")
    assert event.series == "Winter Series"
    assert store.update_event(event.event_id, series="Spring").series == "Spring"
    assert store.add_event("Plain", "2026-01-04").series == ""


def test_teams(store, race):
    ann, bob = (e.rider_id for e in store.race_entries(race.race_id))
    yellow = store.add_team(race.race_id, "Yellow", color="Yellow", color_hex="#FFD700")
    red = store.add_team(race.race_id, "Red")
    assert (yellow.seq, red.seq) == (1, 2)
    with pytest.raises(DuplicateTeamNameError):
        store.add_team(race.race_id, "Yellow")
    yellow = store.add_team_member(yellow.team_id, ann)
    assert yellow.members == (ann,)
    with pytest.raises(DuplicateEntryError):
        store.add_team_member(red.team_id, ann)
    stranger = store.add_rider("Zed", "Zulu")
    with pytest.raises(NotFoundError):
        store.add_team_member(red.team_id, stranger.rider_id)
    store.add_team_member(red.team_id, bob)
    assert [t.members for t in store.teams(race.race_id)] == [(ann,), (bob,)]
    # Leaving the race leaves the team as well.
    store.remove_race_entry(race.race_id, bob)
    assert store.team(red.team_id).members == ()
    store.remove_team(red.team_id)
    assert [t.name for t in store.teams(race.race_id)] == ["Yellow"]


def test_delete_race_only_before_any_action(store, race):
    store.add_team(race.race_id, "Yellow")
    other = store.add_race(race.event_id, "Elim", "elimination")
    store.append_action(other.race_id, "started", {}, 1)
    with pytest.raises(RaceHasActionsError):
        store.delete_race(other.race_id)
    store.delete_race(race.race_id)
    assert [r.race_id for r in store.races(race.event_id)] == [other.race_id]


def _commits(store) -> list[str]:
    """The COMMITs the store sends from here on: each is an fsync of the WAL."""
    seen: list[str] = []

    def trace(sql: str) -> None:
        if sql.lstrip().upper().startswith("COMMIT"):
            seen.append(sql)

    store.connection.set_trace_callback(trace)
    return seen


def test_a_transaction_is_one_commit_and_writes_all_or_nothing(store, race):
    ann = store.race_entries(race.race_id)[0].rider_id
    commits = _commits(store)
    with store.transaction():
        store.set_setting("a", 1)
        store.set_setting("b", 2)
    assert len(commits) == 1
    assert (store.get_setting("a"), store.get_setting("b")) == (1, 2)
    # A refusal inside ends the whole block with nothing written.
    with pytest.raises(DuplicateEntryError), store.transaction():
        store.set_setting("c", 3)
        store.add_race_entry(race.race_id, ann)
    assert store.get_setting("c") is None
    assert store.connection.in_transaction is False
    # A refusal the caller catches undoes only that one write.
    with store.transaction():
        store.set_setting("d", 4)
        with pytest.raises(DuplicateEntryError):
            store.add_race_entry(race.race_id, ann)
        store.set_setting("e", 5)
    assert (store.get_setting("d"), store.get_setting("e")) == (4, 5)
    assert len(commits) == 2


def test_save_race_writes_the_race_its_field_and_teams_in_one_commit(store, race):
    ann, bob = (e.rider_id for e in store.race_entries(race.race_id))
    before = store.races(race.event_id)
    commits = _commits(store)
    fields = {"name": "Madison", "format": "madison", "group_label": "GroupA"}
    made = store.save_race(
        race.event_id, None, fields, [ann, bob], [("Red", "Red", None, [ann, bob])]
    )
    assert len(commits) == 1
    assert [(t.name, t.members) for t in store.teams(made.race_id)] == [("Red", (ann, bob))]
    assert {e.rider_id for e in store.race_entries(made.race_id)} == {ann, bob}
    # An edit that renames the team: still one commit, the team rewritten.
    store.save_race(
        race.event_id,
        made.race_id,
        {"name": "Madison 2"},
        [ann, bob],
        [("Blue", "Blue", None, [ann, bob])],
    )
    assert len(commits) == 2
    assert [t.name for t in store.teams(made.race_id)] == ["Blue"]
    # A refusal partway (a rider not on the roster) leaves no half a race.
    stranger = store.add_rider("Cy", "Charlie").rider_id
    with pytest.raises(NotFoundError):
        store.save_race(race.event_id, None, {"name": "Chase 2", "format": "placings"}, [ann, stranger])  # fmt: skip
    assert [r.race_id for r in store.races(race.event_id)] == [
        *(r.race_id for r in before),
        made.race_id,
    ]


# ----- actions ---------------------------------------------------------------


def test_append_and_read_actions(store, race):
    first = store.append_action(race.race_id, "started", {"bibs": [1, 2]}, 1)
    second = store.append_action(
        race.race_id, "finish_order", {"order": [2, 1]}, 1, operator_note="radio"
    )
    assert second == first + 1
    assert store.last_commit_ms > 0
    actions = store.actions(race.race_id)
    assert [e.action_id for e in actions] == [first, second]
    e = actions[1]
    assert isinstance(e, Action)
    assert e.kind == "finish_order" and e.payload == {"order": [2, 1]} and e.schema_ver == 1
    assert e.operator_note == "radio" and e.voids_action_id is None
    assert len(e.action_uuid) == 36
    assert store.last_action(race.race_id) == e
    with pytest.raises(NotFoundError):
        store.append_action(999, "started", {}, 1)
    with pytest.raises(ValueError):
        store.append_action(race.race_id, "void", {}, 1)


def test_void_semantics(store, race):
    a = store.append_action(race.race_id, "eliminated", {"bib": 1}, 1)
    b = store.append_action(race.race_id, "eliminated", {"bib": 2}, 1)
    v = store.void_action(race.race_id, a, note="wrong bib")
    assert store.last_action(race.race_id).action_id == v
    assert [e.action_id for e in store.actions(race.race_id)] == [a, b, v]
    void_row = store.actions(race.race_id)[-1]
    assert void_row.kind == "void" and void_row.voids_action_id == a
    assert void_row.operator_note == "wrong bib"
    assert [e.action_id for e in store.live_actions(race.race_id)] == [b]

    with pytest.raises(VoidError, match="already voided"):
        store.void_action(race.race_id, a)
    with pytest.raises(VoidError, match="is a void"):
        store.void_action(race.race_id, v)
    with pytest.raises(NotFoundError):
        store.void_action(race.race_id, 999)
    other = store.add_race(race.event_id, "Other", "placings")
    with pytest.raises(VoidError, match="belongs to race"):
        store.void_action(other.race_id, b)
    # Redo is a fresh append; the log stays a straight line.
    c = store.append_action(race.race_id, "eliminated", {"bib": 1}, 1, operator_note="redo")
    assert [e.action_id for e in store.live_actions(race.race_id)] == [b, c]


def test_live_actions_match_a_plain_filter_of_the_log(store, race):
    # Two races' logs interleave in one table, each with voids, a redo,
    # and a batch that voids and appends at once, so the live query's race
    # filter and its voided set are both exercised. A void of a void and a
    # void across races are refused by the store, so they never reach it.
    other = store.add_race(race.event_id, "Other", "placings")
    a, b = race.race_id, other.race_id
    ids = {a: [], b: []}
    for n in range(12):
        for rid in (a, b):
            ids[rid].append(store.append_action(rid, "eliminated", {"bib": n}, 1))
    for rid in (a, b):
        store.void_action(rid, ids[rid][0])
        store.void_action(rid, ids[rid][5])
        store.append_action(rid, "eliminated", {"bib": 0}, 1, operator_note="redo")
    store.append_batch(a, appends=[("eliminated", {"bib": 99}, 1, None)], voids=[(ids[a][7], None)])
    store.void_action(b, ids[b][11])
    with pytest.raises(VoidError):
        store.void_action(a, ids[b][3])

    for rid in (a, b):
        log = store.actions(rid)
        voided = {r.voids_action_id for r in log if r.kind == "void"}
        expected = [r for r in log if r.kind != "void" and r.action_id not in voided]
        assert store.live_actions(rid) == expected
    assert len(store.live_actions(a)) == 12 - 3 + 2
    assert len(store.live_actions(b)) == 12 - 3 + 1
    assert store.live_actions(other.race_id + 1000) == []


def test_append_batch_is_one_transaction(store, race):
    rid = race.race_id
    a = store.append_action(rid, "eliminated", {"bib": 1}, 1)
    ids = store.append_batch(
        rid,
        appends=[("eliminated", {"bib": 2}, 1, "[action 1]")],
        voids=[(a, "corrected [action 1]")],
        state="provisional",
        settings={"race/x": {"n": 1}, "gone": None},
        expect={"race/x": None},
    )
    rows = store.actions(rid)
    # The returned ids follow the arguments, appends then voids; the rows
    # follow the scorer: the old row's void, then its replacement.
    new_id, void_id = ids
    assert [r.action_id for r in rows] == [a, void_id, new_id]
    assert rows[1].voids_action_id == a and rows[2].operator_note == "[action 1]"
    assert [r.payload for r in store.live_actions(rid)] == [{"bib": 2}]
    assert store.race(rid).state == "provisional" and store.race(rid).announced_utc
    assert store.get_setting("race/x") == {"n": 1}

    # Any refusal inside the batch leaves nothing of it behind.
    count = len(store.actions(rid))
    with pytest.raises(VoidError, match="already voided"):
        store.append_batch(
            rid,
            appends=[("note", {}, 1, None)],
            voids=[(a, None)],
            state="final",
            settings={"race/x": {"n": 2}},
        )
    assert len(store.actions(rid)) == count and store.race(rid).state == "provisional"
    assert store.get_setting("race/x") == {"n": 1}
    assert store.connection.in_transaction is False

    # A setting another writer changed since it was read refuses the batch.
    with pytest.raises(ConflictError):
        store.append_batch(rid, appends=[("note", {}, 1, None)], expect={"race/x": {"n": 0}})
    assert len(store.actions(rid)) == count
    with pytest.raises(ValueError):
        store.append_batch(rid, appends=[("void", {}, 1, None)])


def test_append_batch_reports_a_database_error_as_a_store_error(store, race):
    store.connection.execute(
        "CREATE TEMP TRIGGER refuse BEFORE INSERT ON setting BEGIN SELECT RAISE(ABORT, 'nope'); END"
    )
    with pytest.raises(StoreError, match="nope"):
        store.append_batch(race.race_id, appends=[("note", {}, 1, None)], settings={"k": 1})
    assert store.actions(race.race_id) == []


def test_race_action_rejects_update_and_delete(store, race):
    eid = store.append_action(race.race_id, "started", {}, 1)
    conn = store.connection
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE race_action SET kind = 'x' WHERE action_id = ?", (eid,))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM race_action WHERE action_id = ?", (eid,))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM race_action")
    assert [e.action_id for e in store.actions(race.race_id)] == [eid]
    # The trigger backstop also refuses a raw void of the wrong shape.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO race_action (action_uuid, race_id, recorded_utc, kind, schema_ver, "
            "payload_json, voids_action_id) VALUES ('u', ?, 'now', 'void', 1, '{}', NULL)",
            (race.race_id,),
        )


def test_failed_write_rolls_back_and_store_keeps_working(store, race):
    # The check fails after BEGIN IMMEDIATE, so the rollback path is exercised.
    with pytest.raises(NotFoundError):
        store.void_action(race.race_id, 10_000)
    assert store.connection.in_transaction is False
    assert store.append_action(race.race_id, "note", {}, 1) > 0


# ----- settings and backup ---------------------------------------------------


def test_settings(store):
    assert store.get_setting("missing") is None
    assert store.get_setting("missing", "x") == "x"
    store.set_setting("board", {"name": "Velodrome Park", "logo": "C:/logo.png"})
    assert store.get_setting("board") == {"name": "Velodrome Park", "logo": "C:/logo.png"}
    store.set_setting("board", [1, 2])
    assert store.get_setting("board") == [1, 2]
    store.delete_setting("board")
    assert store.get_setting("board") is None


# ----- rulesets ----------------------------------------------------------------


def test_ruleset_crud_and_name_unique_without_case(store):
    doc = {"points_table": [5, 3, 2, 1], "lap_gained": 20}
    assert store.rulesets() == []
    assert store.ruleset_by_name("Club") is None
    club = store.add_ruleset("Club", doc)
    assert club.name == "Club" and club.doc["name"] == "Club"
    assert club.doc["points_table"] == doc["points_table"]
    assert store.ruleset(club.ruleset_id) == club
    assert store.ruleset_by_name("  club ") == club
    with pytest.raises(DuplicateRulesetNameError):
        store.add_ruleset("CLUB", doc)
    with pytest.raises(ValueError):
        store.add_ruleset("   ", doc)

    other = store.add_ruleset("Away", doc)
    assert [r.name for r in store.rulesets()] == ["Away", "Club"]
    with pytest.raises(DuplicateRulesetNameError):
        store.update_ruleset(other.ruleset_id, name="club")
    renamed = store.update_ruleset(club.ruleset_id, name="House", doc={"lap_gained": 10})
    assert (renamed.name, renamed.doc) == ("House", {"lap_gained": 10, "name": "House"})
    assert renamed.created_utc == club.created_utc
    assert store.update_ruleset(club.ruleset_id).name == "House"

    store.delete_ruleset(other.ruleset_id)
    assert [r.name for r in store.rulesets()] == ["House"]
    with pytest.raises(NotFoundError):
        store.delete_ruleset(other.ruleset_id)
    with pytest.raises(NotFoundError):
        store.ruleset(other.ruleset_id)


def test_backup_round_trip_is_self_contained(store, race, tmp_path):
    ids = [store.append_action(race.race_id, "note", {"n": n}, 1) for n in range(5)]
    store.set_setting("k", "v")
    dest = tmp_path / "backups" / "copy.sqlite"
    assert store.backup_to(dest) == dest
    assert not (tmp_path / "backups" / "copy.sqlite.partial").exists()
    assert not (tmp_path / "backups" / "copy.sqlite-wal").exists()
    # The live store keeps running after the backup.
    store.append_action(race.race_id, "note", {"n": 99}, 1)

    raw = sqlite3.connect(dest)
    try:
        assert raw.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert raw.execute("SELECT count(*) FROM race_action").fetchone()[0] == 5
    finally:
        raw.close()
    copy = Store.open(dest)
    try:
        assert [e.action_id for e in copy.actions(race.race_id)] == ids
        assert copy.get_setting("k") == "v"
        assert copy.race_entries(race.race_id) == store.race_entries(race.race_id)
        assert copy.integrity_check() == []
    finally:
        copy.close()


def test_store_context_manager(tmp_path):
    with Store.open(tmp_path / "t.sqlite") as s:
        s.add_event("M", "2026-01-01")
    with pytest.raises(sqlite3.ProgrammingError):
        s.events()


def test_a_constraint_the_schema_refuses_is_a_store_error(tmp_path):
    """A write SQLite refuses reaches the scorer as a store refusal, never a traceback."""
    with Store.open(tmp_path / "t.sqlite") as store:
        event = store.add_event("Night", "2026-10-09", venue="x")
        with pytest.raises(StoreError, match="refused the write"):
            with store._write() as conn:
                conn.execute(
                    "INSERT INTO roster_entry (event_id, rider_id, bib) VALUES (?, 999, 1)",
                    (event.event_id,),
                )


def test_a_write_lock_held_by_another_program_is_a_store_error(tmp_path):
    """A second copy of the app holding the file past busy_timeout is a refusal, not a traceback."""
    path = tmp_path / "t.sqlite"
    with Store.open(path) as store:
        store.connection.execute("PRAGMA busy_timeout = 50")
        other = sqlite3.connect(path, autocommit=True)
        try:
            other.execute("BEGIN IMMEDIATE")
            with pytest.raises(StoreError, match="the data file is busy"):
                store.set_setting("k", 1)
            other.execute("ROLLBACK")
        finally:
            other.close()
        assert store.connection.in_transaction is False
        store.set_setting("k", 2)
        assert store.get_setting("k") == 2


def test_a_commit_the_disk_refuses_is_a_store_error_and_the_next_write_lands(tmp_path):
    """Disk full at COMMIT: nothing is kept, and the file takes the next write once there is room."""

    class FullDisk:
        def __init__(self, real):
            self.real = real

        def execute(self, sql, *args):
            if sql.strip().upper().startswith("COMMIT"):
                raise sqlite3.OperationalError("database or disk is full")
            return self.real.execute(sql, *args)

        def __getattr__(self, name):
            return getattr(self.real, name)

    with Store.open(tmp_path / "t.sqlite") as store:
        real = store._conn
        store._conn = FullDisk(real)
        try:
            with pytest.raises(StoreError, match="database or disk is full"):
                store.set_setting("k", 1)
        finally:
            store._conn = real
        assert store.connection.in_transaction is False
        assert store.get_setting("k") is None
        store.set_setting("k", 2)
        assert store.get_setting("k") == 2


def test_a_disk_refusal_is_told_from_a_refusal_of_the_entry(tmp_path):
    def refused(cause):
        try:
            raise StoreError("the data file was not written") from cause
        except StoreError as exc:
            return exc

    path = tmp_path / "ro.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    conn.close()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError) as readonly:
            conn.execute("INSERT INTO t VALUES (1)")
    finally:
        conn.close()
    assert disk_refusal(refused(readonly.value)) == "unwritable"
    assert disk_refusal(refused(sqlite3.OperationalError("database or disk is full"))) == "full"
    assert disk_refusal(refused(sqlite3.OperationalError("disk I/O error"))) == "unwritable"
    assert disk_refusal(refused(sqlite3.OperationalError("database is locked"))) is None
    assert disk_refusal(refused(sqlite3.IntegrityError("UNIQUE constraint failed"))) is None
    assert disk_refusal(StoreError("The data file is read-only.")) is None


def test_a_second_event_with_the_same_name_and_date_is_refused(store):
    store.add_event("Race Night 4", "2026-10-10")
    with pytest.raises(StoreError, match="An event named Race Night 4 on 2026-Oct-10 already"):
        store.add_event(" race night 4 ", "2026-10-10")
    assert len(store.events()) == 1
    # Either one different is a different event.
    store.add_event("Race Night 4", "2026-10-17")
    store.add_event("Race Night 5", "2026-10-10")
    assert len(store.events()) == 3


def _skip_unless_chmod_protects():
    import os
    import sys

    if sys.platform == "win32":
        pytest.skip("chmod does not make a file read-only to SQLite on Windows")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root writes into a read-only file")


@pytest.mark.parametrize("folder_too", [False, True], ids=["file", "file and folder"])
def test_a_read_only_file_opens_to_read_and_refuses_writes(tmp_path, folder_too):
    _skip_unless_chmod_protects()
    folder = tmp_path / "archive"
    path = folder / "night.sqlite"
    with Store.open(path) as s:
        s.add_event("Race Night 9", "2026-09-05")
        assert s.read_only is False
    path.chmod(0o444)
    if folder_too:
        folder.chmod(0o555)
    try:
        with Store.open(path) as s:
            assert s.read_only is True
            assert [m.name for m in s.events()] == ["Race Night 9"]
            with pytest.raises(StoreError, match="The data file is read-only."):
                s.add_event("Race Night 10", "2026-09-12")
            assert [m.name for m in s.events()] == ["Race Night 9"]
    finally:
        folder.chmod(0o755)
        path.chmod(0o644)


def test_an_event_nobody_raced_in_is_deleted_with_its_program_and_roster(store, race):
    """A mistaken or test event can go; its riders stay in the venue's list."""
    event_id = race.event_id
    ann = store.race_entries(race.race_id)[0].rider_id
    team = store.add_team(race.race_id, "Red", color="Red")
    store.add_team_member(team.team_id, ann)
    store.set_setting(f"event/{event_id}/groups", ["Juniors"])
    store.set_setting(f"race/{race.race_id}/staged", [[ann]])
    other = store.add_event("Race Night 2", "2026-10-03").event_id
    store.set_setting(f"event/{other}/groups", ["Seniors"])
    assert store.event_raced(event_id) is None
    store.delete_event(event_id)
    assert [m.event_id for m in store.events()] == [other]
    assert store.get_setting(f"event/{event_id}/groups") is None
    assert store.get_setting(f"race/{race.race_id}/staged") is None
    assert store.get_setting(f"event/{other}/groups") == ["Seniors"]
    assert store.rider(ann).rider_id == ann, "riders are the venue's"


def test_an_event_with_any_log_row_is_never_deleted(store, race):
    ann = store.race_entries(race.race_id)[0].rider_id
    # Even an entry Undo took back: its rows are in the log for good.
    action_id = store.append_action(race.race_id, "status", {"entrant_id": ann, "status": "DNS"}, 1)
    store.void_action(race.race_id, action_id)
    assert store.event_raced(race.event_id) == race.name
    with pytest.raises(EntryInUseError, match="scored race"):
        store.delete_event(race.event_id)
    assert store.event(race.event_id).event_id == race.event_id


def test_a_rider_taken_out_of_a_field_takes_the_staged_clicks_with_them(store, race):
    """A rider deleted after leaving the field frees an id a new rider may get,
    and the staged click would then be the new rider's."""
    ann = store.race_entries(race.race_id)[0].rider_id
    store.set_setting(f"race/{race.race_id}/staged", {"groups": [[ann]]})
    store.remove_race_entry(race.race_id, ann)
    assert store.get_setting(f"race/{race.race_id}/staged") is None


def test_a_removed_race_takes_its_settings_so_a_reused_id_starts_clean(store, race):
    """SQLite reuses the newest race's id: a race removed and added again
    must not open with the old one's staged clicks and Undo."""
    event_id, race_id = race.event_id, race.race_id
    store.set_setting(f"race/{race_id}/staged", {"groups": [[1]]})
    store.delete_race(race_id)
    again = store.add_race(event_id, "Chase again", "placings")
    assert again.race_id == race_id
    assert store.get_setting(f"race/{race_id}/staged") is None


def test_a_backup_never_lands_on_the_open_file_or_its_side_files(tmp_path):
    from madtracker.store.db import BackupError

    path = tmp_path / "venue.sqlite"
    live = Store.open(path)
    try:
        live.add_rider("Ann", "Alpha")
        for name in ("venue.sqlite", "venue.sqlite-wal", "venue.sqlite-shm"):
            with pytest.raises(BackupError, match="open data file"):
                live.backup_to(tmp_path / name)
        live.add_rider("Bob", "Bravo")
    finally:
        live.close()
    again = Store.open(path)
    try:
        assert len(again.riders()) == 2
    finally:
        again.close()


def test_a_rollback_that_fails_does_not_hide_why_the_write_stopped(tmp_path):
    """The error that ended the block reaches the caller even when ROLLBACK errors too."""

    class BrokenRollback:
        def __init__(self, real):
            self.real = real

        def execute(self, sql, *args):
            if sql.strip().upper() == "ROLLBACK":
                raise sqlite3.OperationalError("disk I/O error")
            return self.real.execute(sql, *args)

        def __getattr__(self, name):
            return getattr(self.real, name)

    with Store.open(tmp_path / "t.sqlite") as store:
        real = store._conn
        store._conn = BrokenRollback(real)
        try:
            with pytest.raises(ValueError, match="the original"):
                with store._write():
                    raise ValueError("the original")
        finally:
            store._conn = real
            if real.in_transaction:
                real.execute("ROLLBACK")
        store.set_setting("k", 1)
        assert store.get_setting("k") == 1
