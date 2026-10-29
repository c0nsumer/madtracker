"""Riders who may be the same person: the ranking behind the import preview and Merge into.

Every name here is invented.
"""

import pytest

from madtracker.control.riders import (
    SAME_BIRTH_YEAR,
    SAME_INITIAL,
    SAME_NAME,
    SWAPPED_NAME,
    candidates,
    name_key,
    rank,
)
from madtracker.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "r.sqlite")
    yield s
    s.close()


@pytest.mark.parametrize(
    "a, b",
    [
        (("Zoë", "Ñúñez"), ("zoe", "NUNEZ")),
        (("Ana", "Smith-Jones"), ("Ana", "Smith Jones")),
        (("Liam", "O'Brien"), ("Liam", "OBrien")),
        (("Liam", "O’Brien"), ("liam", "o brien")),
        (("Marcus J.", "Delgado"), ("Marcus", "Delgado")),
        (("Marcus", "Delgado"), ("Marcus James", "Delgado")),
        (("  Tess ", "Gallagher  "), ("Tess", "Gallagher")),
    ],
)
def test_names_that_differ_only_in_writing_are_equal(a, b):
    assert name_key(*a) == name_key(*b)


def test_rank_by_name_initial_and_birth_year(store):
    r = store.add_rider("Matthew", "Kowalski", birth_year=1988)
    assert rank("Matthew", "Kowalski", None, r) == SAME_NAME
    assert rank("Matt", "Kowalski", None, r) == SAME_INITIAL
    assert rank("M.", "Kowalski", None, r) == SAME_INITIAL
    assert rank("Pat", "Kowalski", 1988, r) == SAME_BIRTH_YEAR
    assert rank("Pat", "Kowalski", 1990, r) is None
    assert rank("Pat", "Kowalski", None, r) is None
    assert rank("Matthew", "Kowalsky", 1988, r) is None


def test_a_swapped_name_is_the_weakest_rank(store):
    r = store.add_rider("Siobhan", "O'Brien")
    assert rank("OBrien", "Siobhan", None, r) == SWAPPED_NAME
    assert rank("O'Brien", "Sinead", None, r) is None
    # A name that reads the same both ways is a plain match, not a swap.
    same = store.add_rider("Lee", "Lee")
    assert rank("Lee", "Lee", None, same) == SAME_NAME


def test_candidates_best_first_at_most_three(store):
    ids = {
        name: store.add_rider(*name.split(), birth_year=1990).rider_id
        for name in ("Mia Novak", "Milo Novak", "Max Novak", "Ben Novak", "Mia Nowak")
    }
    found = candidates("Mia", "Novak", 1990, store.riders())
    assert [c.rider.rider_id for c in found] == [
        ids["Mia Novak"],
        ids["Max Novak"],
        ids["Milo Novak"],
    ]
    assert [c.rank for c in found] == [SAME_NAME, SAME_INITIAL, SAME_INITIAL]
    everyone = candidates("Mia", "Novak", 1990, store.riders(), limit=None)
    assert [c.rider.rider_id for c in everyone][-1] == ids["Ben Novak"]
    assert ids["Mia Nowak"] not in [c.rider.rider_id for c in everyone]
    alone = candidates("Mia", "Novak", 1990, store.riders(), exclude=[ids["Mia Novak"]])
    assert ids["Mia Novak"] not in [c.rider.rider_id for c in alone]


def test_candidate_label_names_the_id_on_file(store):
    usac = store.add_rider("Rosa", "Navarro", usac_license="12345", uci_id="10012345678")
    uci = store.add_rider("Rosa", "Navarro", uci_id="10087654321")
    born = store.add_rider("Rosa", "Navarro", birth_year=1990)
    bare = store.add_rider("Rosa", "Navarro")
    labels = {
        c.rider.rider_id: c.label
        for c in candidates("Rosa", "Navarro", None, store.riders(), limit=None)
    }
    # "#" is a bib everywhere in the app, so an id is named for what it is.
    assert labels == {
        usac.rider_id: "Same as Rosa Navarro (USAC License 12345)",
        uci.rider_id: "Same as Rosa Navarro (UCI ID 10087654321)",
        born.rider_id: "Same as Rosa Navarro (born 1990)",
        bare.rider_id: "Same as Rosa Navarro",
    }


def test_merge_values_keep_what_agrees_and_ask_about_what_differs(store):
    """After JOSM: a blank is not a disagreement; a bib,
    group or team is a choice only where both records have one there."""
    from madtracker.control.riders import merge_choices, merge_values

    ann = store.add_rider("Ann", "Alpha", usac_license="100").rider_id
    anne = store.add_rider("Anne", "Alpha", birth_year=1990).rider_id
    bo = store.add_rider("Bo", "Beta").rider_id
    cy = store.add_rider("Cy", "Gamma").rider_id
    early = store.add_event("Night 1", "2026-09-01").event_id
    late = store.add_event("Night 2", "2026-09-08").event_id
    store.add_entry(early, ann, 5)
    store.add_entry(late, ann, 7, local_group="Group A")
    store.add_entry(late, anne, 9, local_group="Group A")
    store.add_entry(late, bo, 11)
    store.add_entry(late, cy, 12)
    race = store.add_race(late, "Madison", "madison").race_id
    teams = {}
    for name, members in (("Blue", (ann, bo)), ("Red", (anne, cy))):
        teams[name] = store.add_team(race, name, color=name).team_id
        for rid in members:
            store.add_race_entry(race, rid)
            store.add_team_member(teams[name], rid)
    lines = merge_values(store, ann, anne)
    assert [(line.label, line.texts) for line in lines] == [
        ("First name", ("Ann", "Anne")),
        ("Last name", ("Alpha",)),
        ("USAC License", ("100",)),
        ("UCI ID", ()),
        ("Birth year", ("1990",)),
        ("Bib, Night 2", ("7", "9")),
        ("Team, Madison", ("Blue", "Red")),
        ("Events", ("Night 1, Night 2",)),
    ]
    values, entries, chosen_teams = merge_choices(lines, {0: 1, 5: 1, 6: 1})
    assert values == {
        "first_name": "Anne",
        "last_name": "Alpha",
        "usac_license": "100",
        "birth_year": 1990,
    }
    assert entries == {late: {"bib": 9}} and chosen_teams == {race: teams["Red"]}
