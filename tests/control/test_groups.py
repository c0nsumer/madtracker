"""An event's groups as a list: rename, merge and delete, and when each is refused."""

import pytest

from madtracker.control import groups


@pytest.fixture
def night(store):
    event = store.add_event("Race Night 1", "2026-09-26")
    ids = []
    for n, label in enumerate(["Group b", "Group b", "GroupB", "Juniors"]):
        rider = store.add_rider("Rider", f"R{n}")
        store.add_entry(event.event_id, rider.rider_id, n + 1, local_group=label)
        ids.append(rider.rider_id)
    return event.event_id, ids


def _use(store, event_id, label):
    return next(u for u in groups.group_uses(store, event_id) if groups.same_group(u.label, label))


def test_one_row_per_group_whatever_the_spelling(store, night):
    event_id, ids = night
    uses = groups.group_uses(store, event_id)
    assert [(u.label, len(u.riders)) for u in uses] == [("Group b", 3), ("Juniors", 1)]


def test_a_rename_reaches_every_spelling_and_can_respell_the_group_itself(store, night):
    event_id, ids = night
    target = groups.rename_group(store, event_id, _use(store, event_id, "Group b"), "Group B")
    assert target == "Group B"
    assert [store.entry(event_id, i).local_group for i in ids[:3]] == ["Group B"] * 3


def test_a_rename_into_another_group_merges_them(store, night):
    event_id, ids = night
    target = groups.rename_group(store, event_id, _use(store, event_id, "Juniors"), "groupb")
    assert target == "Group b"
    assert [u.label for u in groups.group_uses(store, event_id)] == ["Group b"]


def test_a_race_holds_the_group_against_delete_and_a_scored_one_against_rename(store, night):
    event_id, ids = night
    race = store.add_race(event_id, "Chase", "chase", group_label="Juniors")
    store.add_race_entry(race.race_id, ids[3])
    use = _use(store, event_id, "Juniors")
    assert groups.delete_refusal(use) == "Used by a race" and groups.rename_refusal(use) == ""
    with pytest.raises(ValueError):
        groups.delete_group(store, event_id, use)
    groups.rename_group(store, event_id, use, "Junior Men")
    assert store.race(race.race_id).group_label == "Junior Men"
    assert _field(store, race.race_id) == [ids[3]], "the race keeps its field"
    store.append_action(race.race_id, "status", {"entrant_id": ids[3], "status": "DNS"}, 1)
    use = _use(store, event_id, "Junior Men")
    assert use.raced and groups.rename_refusal(use) == "Has raced"
    with pytest.raises(ValueError):
        groups.rename_group(store, event_id, use, "Juniors")


def test_a_race_undone_to_its_start_follows_its_group_and_lets_it_be_renamed(store, night):
    """Undo back to the start list leaves no entry standing: the group is
    not history, and the race's field follows the group again."""
    from madtracker.control.race import LiveRace

    event_id, ids = night
    race = store.add_race(event_id, "Chase", "chase", group_label="Juniors")
    store.add_race_entry(race.race_id, ids[3])
    live = LiveRace(store, race.race_id)
    assert live.act(ids[3], "dns").ok
    use = _use(store, event_id, "Juniors")
    assert use.raced and groups.rename_refusal(use) == "Has raced"
    store.set_entry_group(event_id, ids[0], "Juniors")
    groups.follow_group(store, event_id, [ids[0]], "Group b")
    assert _field(store, race.race_id) == [ids[3]], "a scored race's field is fixed"
    assert live.undo().ok
    use = _use(store, event_id, "Juniors")
    assert not use.raced and groups.rename_refusal(use) == ""
    groups.follow_group(store, event_id, [ids[0]], "Group b")
    assert _field(store, race.race_id) == [ids[0], ids[3]]
    groups.rename_group(store, event_id, use, "Junior Men")
    assert store.race(race.race_id).group_label == "Junior Men"


def test_a_rename_carries_a_default_race_name_and_category_with_it(store, night):
    """A blank Name and Category saved as the group; they follow it, a typed one stays."""
    event_id, ids = night
    unnamed = store.add_race(
        event_id, "Juniors Scratch Race", "chase", group_label="Juniors", usac_category="Juniors"
    )
    typed = store.add_race(
        event_id, "Juniors Final", "chase", group_label="Juniors", usac_category="Cat 3/4"
    )
    groups.rename_group(store, event_id, _use(store, event_id, "Juniors"), "Junior Men")
    unnamed, typed = store.race(unnamed.race_id), store.race(typed.race_id)
    assert (unnamed.name, unnamed.usac_category) == ("Junior Men Scratch Race", "Junior Men")
    assert (typed.name, typed.usac_category) == ("Juniors Final", "Cat 3/4")
    assert typed.group_label == unnamed.group_label == "Junior Men"


def test_delete_leaves_the_riders_with_no_group(store, night):
    event_id, ids = night
    groups.delete_group(store, event_id, _use(store, event_id, "Group b"))
    assert [store.entry(event_id, i).local_group for i in ids] == [None, None, None, "Juniors"]


def test_a_new_group_is_listed_before_anyone_is_in_it_and_follows_a_rename(store, night):
    event_id, ids = night
    assert groups.add_group(store, event_id, " Semi  Pro ") == "Semi Pro"
    # A pasted zero-width space or a tab is cleaned as it is in every
    # other typed name, so it cannot make a second "Semi Pro".
    with pytest.raises(ValueError, match="a group named Semi Pro already exists"):
        groups.add_group(store, event_id, "Semi\u200b\tPro")
    with pytest.raises(ValueError, match="a group named Semi Pro already exists"):
        groups.add_group(store, event_id, "semipro")
    with pytest.raises(ValueError):
        groups.add_group(store, event_id, "   ")
    use = _use(store, event_id, "Semi Pro")
    assert use.riders == () and use.races == ()
    groups.rename_group(store, event_id, use, "Semi-Pro")
    assert "Semi-Pro" in groups.event_spellings(store, event_id)
    assert "Semi Pro" not in groups.event_spellings(store, event_id)
    groups.delete_group(store, event_id, _use(store, event_id, "Semi-Pro"))
    assert groups.declared(store, event_id) == []


def _field(store, race_id):
    return sorted(e.rider_id for e in store.race_entries(race_id))


def test_a_copied_programs_races_fill_as_riders_join_their_groups(store):
    """A new event from an earlier program has races for Group A and B and
    an empty roster; riders added later reach the races. Until a race is
    scored, its field follows its group."""
    from madtracker.control.copying import copy_program
    from madtracker.control.roster import enter_on_roster

    old = store.add_event("Night 1", "2026-10-01").event_id
    store.add_race(old, "A Chase", "placings", group_label="Group A")
    store.add_race(old, "B Chase", "placings", group_label="Group B")
    new = store.add_event("Night 2", "2026-10-08").event_id
    copy_program(store, old, new)
    a_race, b_race = store.races(new)
    ann, bob, cy = (store.add_rider("R", n).rider_id for n in ("Ann", "Bob", "Cy"))
    enter_on_roster(store, new, ann, None, "group a")
    enter_on_roster(store, new, bob, None, "Group B")
    enter_on_roster(store, new, cy, None, "")
    assert _field(store, a_race.race_id) == [ann]
    assert _field(store, b_race.race_id) == [bob]
    # A group change moves the rider between the unscored races.
    store.set_entry_group(new, ann, "Group B")
    groups.follow_group(store, new, [ann], "Group A")
    assert _field(store, a_race.race_id) == [] and _field(store, b_race.race_id) == [ann, bob]
    # A rider put in another group's race by hand stays there.
    store.add_race_entry(a_race.race_id, cy)
    store.set_entry_group(new, cy, "Group B")
    groups.follow_group(store, new, [cy], None)
    assert cy in _field(store, a_race.race_id) and cy in _field(store, b_race.race_id)
    # Once a race is scored its field is fixed.
    store.append_action(b_race.race_id, "status", {"entrant_id": bob, "status": "DNS"}, 1)
    store.set_entry_group(new, bob, "Group A")
    groups.follow_group(store, new, [bob], "Group B")
    assert bob in _field(store, b_race.race_id) and bob in _field(store, a_race.race_id)


def test_a_merge_of_groups_fills_the_merged_groups_races(store, night):
    event_id, ids = night
    race = store.add_race(event_id, "Juniors Chase", "placings", group_label="Juniors")
    store.add_race_entry(race.race_id, ids[3])
    groups.rename_group(store, event_id, _use(store, event_id, "Group b"), "Juniors")
    assert _field(store, race.race_id) == sorted(ids)


def test_out_of_group_counts_riders_from_other_groups():
    """A Junior in the Pro race is seen where the program is set up."""
    assert groups.out_of_group("Pro", ["Pro", "pro ", "Juniors"]) == ", 1 from Juniors"
    assert groups.out_of_group("Pro", ["Juniors", "Masters", "Juniors", None]) == (
        ", 2 from Juniors, 1 from Masters, 1 with no group"
    )
    assert groups.out_of_group("Pro", ["Pro"]) == ""
    assert groups.out_of_group("", ["Juniors"]) == "", "a race without a group says nothing"


def test_a_plain_rename_leaves_a_field_trimmed_by_hand(store, night):
    """A rename never refills the field: riders the scorer took out stay out."""
    event_id, ids = night
    race = store.add_race(event_id, "B Chase", "placings", group_label="Group B")
    # Two of the group's three riders, and a rider from Juniors ticked in.
    for rid in (ids[0], ids[1], ids[3]):
        store.add_race_entry(race.race_id, rid)
    groups.rename_group(store, event_id, _use(store, event_id, "Group b"), "Seniors")
    assert store.race(race.race_id).group_label == "Seniors"
    assert _field(store, race.race_id) == sorted([ids[0], ids[1], ids[3]])


def test_a_merge_adds_the_other_groups_riders_and_keeps_hand_trims(store, night):
    """A merge never refills both groups' races: riders trimmed by hand stay out."""
    event_id, ids = night
    b_race = store.add_race(event_id, "B Chase", "placings", group_label="Group B")
    # One of Group b's three riders was taken out by hand.
    for rid in (ids[0], ids[1]):
        store.add_race_entry(b_race.race_id, rid)
    j_race = store.add_race(event_id, "Juniors Chase", "placings", group_label="Juniors")
    groups.rename_group(store, event_id, _use(store, event_id, "Group b"), "Juniors")
    assert store.race(b_race.race_id).group_label == "Juniors"
    # The B race gains the Junior and still leaves out the rider trimmed.
    assert _field(store, b_race.race_id) == sorted([ids[0], ids[1], ids[3]])
    # The Juniors race (empty by hand) gains Group b's riders only.
    assert _field(store, j_race.race_id) == sorted(ids[:3])
