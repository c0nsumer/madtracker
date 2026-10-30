"""BikeReg import: parsing the export, planning against the database, applying the plan.

Every name and number here is invented.
"""

from dataclasses import replace

import pytest

from madtracker.importers import bikereg
from madtracker.importers.bikereg import (
    STATUS_TEXT,
    ImportFormatError,
    ImportResult,
    ImportRow,
    UnreviewedError,
    apply_import,
    choose,
    derive_group,
    parse,
    plan_import,
    replan,
)
from madtracker.store import Store, StoreError

HEADER = (
    "Entry Date and Time,Last Name,First Name,Bib,Waiver - USAC Online Waiver,"
    "Restriction Override,Age on 12/31/2026,USAC License,License Status,"
    "License Expiration Date,UCI Code,Unique License Number (UCI or USAC),"
    "USAC Category Track,Entry Type,Entry Fee,Coupon Code,Notes,Category Date,166?,"
    "Category,Madison?,Mad166?,WhereMad?"
)
ROWS = [
    # Blank bib, numeric license, Group A from the parentheses.
    "9/20/2026 10:01,Delgado,Marcus,,Yes,,34,512345,Active,12/31/2026,,512345,2,"
    'Online,25,,,9/26/2026,Yes,"Cat 1/2/3 (Group A)",Yes,,',
    # Foreign rider: INTL license, the UCI code carries the id.
    "9/20/2026 10:05,Lindqvist,Ava,,Yes,,27,INTL-CAN,Active,,10012345678,10012345678,,"
    'Online,25,,,9/26/2026,No,"Cat 1/2/3 (Group A)",No,,',
    # Age note in the parentheses: the group is the text before it.
    "9/21/2026 08:00,Pell,Isaac,7,Yes,,13,598765,Active,12/31/2026,,598765,5,"
    'Online,10,,,9/26/2026,No,"Young Juniors (14 and under)",,,',
    # No parentheses at all.
    "9/21/2026 09:00,Yoon,Hana,,Yes,,45,577777,Active,12/31/2026,,577777,3,"
    "Online,25,,,9/26/2026,No,Masters 40+,Yes,,",
]
CSV = "﻿" + "\r\n".join([HEADER, *ROWS]) + "\r\n"


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "t.sqlite")
    yield s
    s.close()


@pytest.fixture
def event_id(store):
    return store.add_event("Race Night 1", "2026-09-26").event_id


def test_parse_reads_every_named_row():
    rows = parse(CSV)
    assert [r.last for r in rows] == ["Delgado", "Lindqvist", "Pell", "Yoon"]
    assert rows[0].first == "Marcus"
    assert rows[0].line == 2


def test_parse_blank_bib_is_none_and_typed_bib_is_int():
    rows = parse(CSV)
    assert rows[0].bib is None
    assert rows[2].bib == 7


def test_parse_intl_license_is_none_and_uci_code_kept():
    ava = parse(CSV)[1]
    assert ava.usac_license is None
    assert ava.uci_id == "10012345678"


def test_parse_birth_year_from_age_header_year():
    rows = parse(CSV)
    assert rows[0].racing_age == 34
    assert rows[0].birth_year == 2026 - 34
    assert rows[2].birth_year == 2013


def test_parse_groups_and_flags():
    rows = parse(CSV)
    assert [r.local_group for r in rows] == [
        "Group A",
        "Group A",
        "Young Juniors",
        "Masters 40+",
    ]
    assert rows[0].category == "Cat 1/2/3 (Group A)"
    assert rows[0].usac_license == "512345"


@pytest.mark.parametrize(
    "category,group",
    [
        ("Cat 1/2/3 (Group A)", "Group A"),
        ("Cat 4/5 (Group C)", "Group C"),
        ("Young Juniors (14 and under)", "Young Juniors"),
        ("Open", "Open"),
        ("", None),
        (None, None),
    ],
)
def test_derive_group(category, group):
    assert derive_group(category) == group


def test_parse_tolerates_missing_optional_columns_and_reads_a_path(tmp_path):
    path = tmp_path / "entries.csv"
    path.write_text("First Name,Last Name\nKenji,Mori\n,\n", encoding="utf-8-sig")
    rows = parse(path)
    assert rows == [ImportRow(first="Kenji", last="Mori", line=2)]
    assert parse(str(path)) == rows


def test_parse_without_names_is_refused():
    with pytest.raises(ImportFormatError) as refused:
        parse("First Name,Bib\nKenji,4\n")
    assert str(refused.value) == (
        "not a BikeReg entries export (no Last Name / First Name columns)"
    )


@pytest.mark.parametrize(
    "encoding", ["utf-16", "utf-16-le", "utf-16-be"], ids=["bom", "le-no-bom", "be-no-bom"]
)
def test_parse_reads_a_utf16_export(tmp_path, encoding):
    """Excel's "Unicode Text" is UTF-16, with or without a byte order mark."""
    path = tmp_path / "entries.csv"
    path.write_bytes(CSV.lstrip("﻿").encode(encoding))
    assert [r.last for r in parse(path)] == ["Delgado", "Lindqvist", "Pell", "Yoon"]


@pytest.mark.parametrize("delimiter", [";", "\t"], ids=["semicolon", "tab"])
def test_parse_reads_a_semicolon_or_tab_separated_export(tmp_path, delimiter):
    path = tmp_path / "entries.csv"
    path.write_text(
        delimiter.join(["Last Name", "First Name", "Bib", "Category"])
        + "\n"
        + delimiter.join(["Mori", "Kenji", "4", '"Cat 4/5, Juniors (Group B)"'])
        + "\n",
        encoding="utf-8",
    )
    (row,) = parse(path)
    assert (row.first, row.last, row.bib, row.local_group) == ("Kenji", "Mori", 4, "Group B")


def test_parse_reads_cp1252_and_a_doubled_quote(tmp_path):
    """Excel's plain "CSV" on Windows; the sniffed delimiter keeps doubled quotes."""
    path = tmp_path / "entries.csv"
    path.write_bytes(
        'Last Name,First Name,Notes,Bib\nNavarro,Rosé,"says ""hi""",8\n'.encode("cp1252")
    )
    (row,) = parse(path)
    assert (row.first, row.bib) == ("Rosé", 8)


def test_parse_refuses_a_file_that_is_not_text(tmp_path):
    path = tmp_path / "entries.csv"
    path.write_bytes(b"PK\x03\x04\x14\x00\x06\x00workbook")
    with pytest.raises(ImportFormatError) as refused:
        parse(path)
    assert str(refused.value) == (
        "not a CSV file. If it is an Excel workbook, save it as CSV first."
    )


def test_parse_reads_a_byte_cp1252_leaves_undefined(tmp_path):
    """0x81 is undefined in cp1252: the name reads with a "?", the file is not refused."""
    path = tmp_path / "entries.csv"
    path.write_bytes(b"Last Name,First Name\nMori,Ke\x81nji\n")
    (row,) = parse(path)
    assert (row.last, row.first) == ("Mori", "Ke?nji")


def test_parse_refuses_a_file_over_the_size_limit(tmp_path, monkeypatch):
    """Checked from the file's size before it is read; the limit is lowered to test it."""
    path = tmp_path / "entries.csv"
    path.write_text("Last Name,First Name\nMori,Kenji\n")
    monkeypatch.setattr(bikereg, "MAX_BYTES", path.stat().st_size - 1)
    with pytest.raises(ImportFormatError) as refused:
        parse(path)
    assert str(refused.value) == "it is larger than 20 MB, so it is not an entries export"


def test_plan_matches_by_license_and_lists_differences(store, event_id):
    # Another first initial, believed on the license because the birth
    # year agrees: a first name that is not just another form of the one
    # on file is a difference to review.
    rider = store.add_rider("Rocco", "Delgado", usac_license="512345", birth_year=1992)
    row = replace(parse(CSV)[0], uci_id="10011122233")
    (plan,) = plan_import(store, event_id, [row])
    assert plan.action == "update"
    assert plan.rider_id == rider.rider_id
    assert plan.matched_by == "license"
    assert set(plan.changes) == {"first_name", "uci_id"}
    # Both have a first name: a difference to review. The UCI ID only
    # fills a blank, so it is applied as it stands.
    assert plan.status == "review"
    assert set(plan.disputes) == {"first_name"} and set(plan.fills) == {"uci_id"}
    assert plan.differences == ["first name: Rocco or Marcus", "UCI ID: none -> 10011122233"]
    plan.resolved = {"first_name": "Rocco"}
    assert plan.differences == ["first name: Rocco kept", "UCI ID: none -> 10011122233"]
    assert plan.fields() == {"uci_id": "10011122233"}


def test_plan_matches_by_uci_then_by_name(store, event_id):
    ava = store.add_rider("Ava", "Lindqvist", uci_id="10012345678", birth_year=1999)
    hana = store.add_rider("HANA", "yoon")
    plans = plan_import(store, event_id, parse(CSV))
    assert (plans[1].matched_by, plans[1].rider_id, plans[1].action) == (
        "uci",
        ava.rider_id,
        "match",
    )
    assert (plans[3].matched_by, plans[3].rider_id) == ("name", hana.rider_id)
    # The names differ only in case, which is no change; the birth year
    # the record lacks is the update.
    assert plans[3].action == "update"
    assert not {"first_name", "last_name"} & set(plans[3].changes)
    assert plans[0].action == "new" and plans[0].rider_id is None


def test_plan_offers_a_name_match_when_only_the_existing_rider_has_a_license(store, event_id):
    """Two people can share a name; with no license on the row to compare,
    the row stays new and the stored rider is offered for the scorer."""
    ava = store.add_rider("Ava", "Lindqvist", usac_license="424242")
    plan = plan_import(store, event_id, parse(CSV))[1]
    assert (plan.matched_by, plan.rider_id, plan.action) == (None, None, "new")
    assert [c.rider.rider_id for c in plan.candidates] == [ava.rider_id]
    assert plan.candidates[0].label == "Same as Ava Lindqvist (USAC License 424242)"
    assert plan.note == (
        "no USAC License (INTL-CAN); created with UCI ID 10012345678;"
        " may be Ava Lindqvist (USAC License 424242)"
    )


def test_plan_offers_near_duplicates_and_never_merges_them(store, event_id):
    """Spelled another way, no id on file: offered, best first, never matched."""
    jose = store.add_rider("José", "García-Lopez", birth_year=1990)
    jo = store.add_rider("Jo", "Garcia Lopez")
    store.add_rider("Ann", "Garcia")
    rows = [ImportRow(first="Jose M.", last="Garcia Lopez", usac_license="600001", line=2)]
    (plan,) = plan_import(store, event_id, rows)
    assert (plan.action, plan.rider_id) == ("new", None)
    assert [c.rider.rider_id for c in plan.candidates] == [jose.rider_id, jo.rider_id]
    assert plan.candidates[0].label == "Same as José García-Lopez (born 1990)"
    assert plan.candidates[1].label == "Same as Jo Garcia Lopez"


def test_choosing_a_candidate_makes_the_row_a_match_of_that_rider(store, event_id):
    jose = store.add_rider("José", "Garcia")
    rows = [
        ImportRow(first="Jose", last="Garcia", usac_license="600001"),
        ImportRow(first="Rosa", last="Navarro", line=3),
    ]
    plans = plan_import(store, event_id, rows)
    chosen = choose(store, event_id, plans, 0, jose.rider_id)
    assert plans[0].rider_id is None, "the original plans are left alone"
    plan = chosen[0]
    assert (plan.action, plan.rider_id, plan.matched_by) == ("update", jose.rider_id, "chosen")
    assert plan.differences == [
        "first name: José or Jose",
        "USAC License: none -> 600001",
    ]
    plan.resolved = {"first_name": "José"}
    assert choose(store, event_id, chosen, 0, None)[0].action == "new"
    applied = replan(plan, bib=8, group=None)
    result = apply_import(store, event_id, [applied, chosen[1]], chosen=[0])
    assert result.updated == [jose.rider_id] and result.created == []
    assert store.rider(jose.rider_id).usac_license == "600001"
    assert store.rider(jose.rider_id).first_name == "José", "the spelling on file was kept"


def test_a_license_on_file_for_another_rider_is_a_conflict_not_a_silent_skip(store, event_id):
    priya = store.add_rider("Priya", "Okafor", usac_license="12345")
    marcus = store.add_rider("Marcus", "Delgado", uci_id="10099999999")
    rows = [ImportRow(first="Marcus", last="Delgado", usac_license="12345", uci_id="10099999999")]
    (plan,) = plan_import(store, event_id, rows)
    # The license is Priya's but the row is plainly Marcus: matched to him
    # by name, with the license left for the scorer.
    assert (plan.rider_id, plan.matched_by) == (marcus.rider_id, "name")
    assert plan.conflict == "USAC License 12345 is on file for Priya Okafor"
    assert (plan.action, plan.changes) == ("match", {})
    assert {c.rider.rider_id for c in plan.candidates} == {priya.rider_id, marcus.rider_id}
    # Choosing Priya instead puts the UCI ID in the wrong place.
    chosen = choose(store, event_id, [plan], 0, priya.rider_id)[0]
    assert chosen.conflict == "UCI ID 10099999999 is on file for Marcus Delgado"
    assert "uci_id" not in chosen.changes and "first_name" in chosen.changes
    # A license match whose name resembles the holder stands, conflict-free.
    rows = [ImportRow(first="P.", last="Okafor", usac_license="12345")]
    (plan,) = plan_import(store, event_id, rows)
    assert (plan.rider_id, plan.matched_by, plan.conflict) == (priya.rider_id, "license", "")


def test_a_license_on_file_for_someone_with_another_name_never_renames_them(store, event_id):
    """A mistyped or reissued license must not rename the stored rider:
    the row is new, unticked, and the holder is offered."""
    ann = store.add_rider("Ann", "Quill", usac_license="733001")
    rows = [ImportRow(first="Bruno", last="Castellan", usac_license="733001", line=2)]
    (plan,) = plan_import(store, event_id, rows)
    assert (plan.action, plan.rider_id, plan.matched_by) == ("new", None, None)
    assert plan.changes == {}
    assert plan.conflict == "USAC License 733001 is on file for Ann Quill"
    assert [c.rider.rider_id for c in plan.candidates] == [ann.rider_id]
    assert plan.note == ""
    # Ticked anyway as new, the row is a new person and the license stays put.
    result = apply_import(store, event_id, [plan], chosen=[0])
    assert store.rider(ann.rider_id).first_name == "Ann"
    (created,) = result.created
    assert store.rider(created).usac_license is None
    assert result.adjusted == [
        "Bruno Castellan added without USAC License 733001; it is on file for another rider"
    ]
    # The same goes for a UCI ID.
    store.update_rider(ann.rider_id, uci_id="10055500011")
    rows = [ImportRow(first="Bruno", last="Ferris", uci_id="10055500011", line=3)]
    (plan,) = plan_import(store, event_id, rows)
    assert (plan.action, plan.rider_id) == ("new", None)
    assert plan.conflict == "UCI ID 10055500011 is on file for Ann Quill"


def test_a_possible_match_already_on_the_roster_is_a_conflict(store, event_id):
    """Importing a second record of a rider already on tonight's roster
    puts one person in a field twice; the row starts unticked."""
    nora = store.add_rider("Nóra", "Brennick")
    store.add_entry(event_id, nora.rider_id, bib=42)
    rows = [ImportRow(first="Nora", last="Brennick", usac_license="744001", line=2)]
    (plan,) = plan_import(store, event_id, rows)
    assert (plan.action, plan.rider_id) == ("new", None)
    assert [c.rider.rider_id for c in plan.candidates] == [nora.rider_id]
    assert plan.conflict == "possible match already on this roster with bib 42"
    assert plan.note == "may be Nóra Brennick"
    # Choosing her clears it; the row is that rider.
    chosen = choose(store, event_id, [plan], 0, nora.rider_id)[0]
    assert (chosen.conflict, chosen.bib) == ("", 42)

    late = store.add_rider("Theo", "Marchetti")
    store.add_entry(event_id, late.rider_id, bib=None)
    rows = [ImportRow(first="Théo", last="Marchetti", line=3)]
    (plan,) = plan_import(store, event_id, rows)
    assert plan.conflict == "possible match already on this roster with no bib yet"
    # Off the roster, the same near-duplicate is only a note.
    store.add_rider("Lise", "Vandermolen")
    (plan,) = plan_import(store, event_id, [ImportRow(first="Lisé", last="Vandermolen")])
    assert (plan.conflict, plan.note) == ("", "may be Lise Vandermolen")


def test_a_name_match_needs_birth_years_within_a_year(store, event_id):
    """A father and son can share a name; a year apart is a late birthday."""
    senior = store.add_rider("Walt", "Okonkwo", birth_year=1960)
    rows = [ImportRow(first="Walt", last="Okonkwo", birth_year=2010, line=2)]
    (plan,) = plan_import(store, event_id, rows)
    assert (plan.action, plan.rider_id) == ("new", None)
    assert [c.rider.rider_id for c in plan.candidates] == [senior.rider_id]
    assert plan.candidates[0].label == "Same as Walt Okonkwo (born 1960)"
    rows = [ImportRow(first="Walt", last="Okonkwo", birth_year=1961, line=2)]
    (plan,) = plan_import(store, event_id, rows)
    assert (plan.rider_id, plan.matched_by) == (senior.rider_id, "name")
    rows = [ImportRow(first="Walt", last="Okonkwo", line=2)]
    assert plan_import(store, event_id, rows)[0].rider_id == senior.rider_id


def test_namesake_labels_carry_what_is_on_file_and_nothing_more(store, event_id):
    """A "#" is a bib in this app, so an id is named; with no id, the birth year."""
    store.add_rider("Ines", "Halvorsen", uci_id="10066600022")
    store.add_rider("Ines", "Halvorsen", birth_year=1988)
    store.add_rider("Ines", "Halvorsen")
    rows = [ImportRow(first="Ines", last="Halvorsen", usac_license="755999", line=2)]
    (plan,) = plan_import(store, event_id, rows)
    assert plan.rider_id is None
    assert sorted(c.label for c in plan.candidates) == [
        "Same as Ines Halvorsen",
        "Same as Ines Halvorsen (UCI ID 10066600022)",
        "Same as Ines Halvorsen (born 1988)",
    ]


def test_one_rider_given_two_licenses_in_the_file_is_a_conflict(store, event_id):
    tess = store.add_rider("Tess", "Gallagher", uci_id="10011111111")
    rows = [
        ImportRow(first="Tess", last="Gallagher", uci_id="10011111111", usac_license="700001"),
        ImportRow(first="Tess", last="Gallagher", uci_id="10011111111", usac_license="700002"),
    ]
    plans = plan_import(store, event_id, rows)
    assert [p.rider_id for p in plans] == [tess.rider_id, tess.rider_id]
    text = "the file gives Tess Gallagher two USAC Licenses (700001, 700002)"
    assert [p.conflict for p in plans] == [text, text]
    assert all("usac_license" not in p.changes for p in plans)


def test_plan_refuses_name_match_with_a_different_license(store, event_id):
    store.add_rider("Hana", "Yoon", usac_license="111")
    assert plan_import(store, event_id, parse(CSV))[3].action == "new"


def test_plan_keeps_the_file_bib_and_never_invents_one(store, event_id):
    """Bibs are the venue's to hand out per event: the plan carries the
    file's bib or none, never a number of its own or last event's."""
    hand = store.add_rider("Omar", "Rahimi")
    store.add_entry(event_id, hand.rider_id, bib=1)
    earlier = store.add_event("Race Night 0", "2026-09-19").event_id
    yoon = store.add_rider("Hana", "Yoon", usac_license="577777")
    store.add_entry(earlier, yoon.rider_id, bib=44)
    plans = plan_import(store, event_id, parse(CSV))
    assert [p.bib for p in plans] == [None, None, 7, None]


def test_plan_group_falls_back_to_the_riders_most_recent_event(store, event_id):
    """A row with no category gets the group Choose riders would suggest: the
    one from the rider's most recent event, not one stored on the rider."""
    omar = store.add_rider("Omar", "Rahimi", usac_license="600002")
    older = store.add_event("Race Night -1", "2026-09-12").event_id
    earlier = store.add_event("Race Night 0", "2026-09-19").event_id
    store.add_entry(older, omar.rider_id, bib=3, local_group="Junior B")
    store.add_entry(earlier, omar.rider_id, bib=5, local_group="Group B")
    rows = [
        ImportRow(first="Omar", last="Rahimi", usac_license="600002", line=2),
        ImportRow(first="Rosa", last="Navarro", line=3),
    ]
    plans = plan_import(store, event_id, rows)
    assert [p.group for p in plans] == ["Group B", None]


def test_plan_keeps_a_file_bib_another_rider_wears_and_an_entered_riders_bib(store, event_id):
    other = store.add_rider("Omar", "Rahimi")
    store.add_entry(event_id, other.rider_id, bib=7)
    isaac = store.add_rider("Isaac", "Pell", usac_license="598765")
    store.add_entry(event_id, isaac.rider_id, bib=12, local_group="Junior B")
    plans = plan_import(store, event_id, parse(CSV))
    assert plans[2].already_entered
    assert (plans[2].bib, plans[2].group) == (12, "Junior B")
    rows = [
        ImportRow(first="Tess", last="Gallagher", bib=7, line=9),
        ImportRow(first="Rosa", last="Navarro", bib=20, line=10),
        ImportRow(first="Kenji", last="Mori", bib=20, line=11),
    ]
    tess, rosa, kenji = plan_import(store, event_id, rows)
    # Riders in different races may share a number: the file's bib is
    # kept, and the race field is where a clash is refused.
    assert (tess.bib, rosa.bib, kenji.bib) == (7, 20, 20)
    assert tess.note == rosa.note == kenji.note == ""


def test_apply_round_trip(store, event_id):
    known = store.add_rider("Rocco", "Delgado", usac_license="512345", birth_year=1992)
    plans = plan_import(store, event_id, parse(CSV))
    plans[0] = replan(plans[0], bib=10, group=plans[0].group)
    plans[1] = replan(plans[1], bib=11, group=plans[1].group)
    plans[3] = replan(plans[3], bib=30, group="Group B")
    # A difference not yet reviewed stops the whole import, before any write.
    with pytest.raises(UnreviewedError, match="Marcus Delgado: review the differences first"):
        apply_import(store, event_id, plans, chosen=[0, 1, 3])
    assert store.entries(event_id) == [] and len(store.riders()) == 1
    plans[0].resolved = {"first_name": "Marcus"}
    result = apply_import(store, event_id, plans, chosen=[0, 1, 3])
    assert result.updated == [known.rider_id]
    assert len(result.created) == 2
    assert result.skipped == [] and result.adjusted == []
    assert sorted(b for _rid, b in result.entered) == [10, 11, 30]

    entries = {e.rider_id: e for e in store.entries(event_id)}
    assert len(entries) == 3
    assert store.rider(known.rider_id).first_name == "Marcus"
    assert entries[known.rider_id].local_group == "Group A"
    hana = next(r for r in store.riders() if r.last_name == "Yoon")
    assert (entries[hana.rider_id].bib, entries[hana.rider_id].local_group) == (30, "Group B")
    assert hana.birth_year == 1981

    # A second import of the same file matches everyone and creates nothing.
    again = plan_import(store, event_id, parse(CSV))
    assert [p.action for p in again[:2]] == ["match", "match"]
    assert again[0].already_entered and not again[2].already_entered
    assert [p.bib for p in again] == [10, 11, 7, 30]


def test_apply_is_one_commit_and_writes_every_row_or_none(store, event_id, monkeypatch):
    """Each commit is an fsync; and a failure partway must not leave half the file in."""
    store.add_race(event_id, "Group A Scratch", "scratch", group_label="Group A")
    commits = []
    store.connection.set_trace_callback(
        lambda sql: commits.append(sql) if sql.lstrip().upper().startswith("COMMIT") else None
    )
    plans = plan_import(store, event_id, parse(CSV))
    result = apply_import(store, event_id, plans, chosen=[0, 1, 2, 3])
    assert len(result.created) == 4 and len(commits) == 1
    # Both Group A riders joined the group's race in that same commit.
    race = store.races(event_id)[0]
    assert len(store.race_entries(race.race_id)) == 2

    other = store.add_event("Race Night 2", "2026-10-03").event_id
    real = store.add_entry
    calls = []

    def fails_third(*args, **kwargs):
        calls.append(args)
        if len(calls) == 3:
            raise StoreError("the data file was not written: disk I/O error")
        return real(*args, **kwargs)

    monkeypatch.setattr(store, "add_entry", fails_third)
    plans = plan_import(store, other, parse(CSV))
    with pytest.raises(StoreError, match="disk I/O error"):
        apply_import(store, other, plans, chosen=[0, 1, 2, 3])
    assert store.entries(other) == [], "the two rows before the failure are not kept"
    assert len(store.riders()) == 4


def test_apply_puts_a_row_with_no_bib_on_the_roster_without_one(store, event_id):
    """The bibs come after registration closes: a blank one is typed in later."""
    plans = plan_import(store, event_id, parse(CSV))
    result = apply_import(store, event_id, plans, chosen=[0, 2])
    assert result.skipped == []
    marcus = store.find_rider_by_license("512345")
    assert marcus is not None
    assert store.entry(event_id, marcus.rider_id).bib is None
    assert sorted(result.entered, key=lambda e: e[1] or 0) == [
        (marcus.rider_id, None),
        (store.find_rider_by_license("598765").rider_id, 7),
    ]
    assert result.no_bib == 1
    assert result.summary().endswith(" 1 rider has no bib yet.")


def test_apply_shares_a_bib_but_never_clashes_in_a_race_field(store, event_id):
    """A number worn by a rider in another race is fine; one worn in the
    rider's own race is refused, and the rider keeps the bib they had."""
    plans = plan_import(store, event_id, parse(CSV))
    plans[0] = replan(plans[0], bib=5, group=plans[0].group)
    late = store.add_rider("Rosa", "Navarro")
    store.add_entry(event_id, late.rider_id, bib=5)
    result = apply_import(store, event_id, plans, chosen=[0])
    marcus = store.find_rider_by_license("512345")
    assert result.skipped == [] and result.entered == [(marcus.rider_id, 5)]

    race = store.add_race(event_id, "Scratch A", "scratch").race_id
    store.add_race_entry(race, marcus.rider_id)
    kenji = store.add_rider("Kenji", "Mori")
    store.add_entry(event_id, kenji.rider_id, bib=9)
    store.add_race_entry(race, kenji.rider_id)
    again = plan_import(store, event_id, parse(CSV))
    again[0] = replan(again[0], bib=9, group=again[0].group)
    result = apply_import(store, event_id, again, chosen=[0])
    assert result.skipped == [
        "Marcus Delgado keeps bib 5; Bib 9 is worn by Kenji Mori in Scratch A."
    ]
    assert store.entry(event_id, marcus.rider_id).bib == 5


def test_plan_notes_a_rider_whose_only_id_is_the_uci_code(store, event_id):
    """An INTL-CAN row says why the license is blank and that its UCI code
    carries the id."""
    rows = parse(CSV)
    assert rows[1].license_text == "INTL-CAN" and rows[1].uci_id == "10012345678"
    new = plan_import(store, event_id, rows)[1]
    assert new.note == "no USAC License (INTL-CAN); created with UCI ID 10012345678"
    ava = store.add_rider("Ava", "Lindqvist", uci_id="10012345678")
    matched = plan_import(store, event_id, rows)[1]
    assert matched.rider_id == ava.rider_id
    assert matched.note == "no USAC License (INTL-CAN); matched by UCI ID 10012345678"
    assert plan_import(store, event_id, rows)[0].note == ""  # a numeric license needs no note


def test_plan_takes_the_event_spelling_of_a_group(store, event_id):
    early = store.add_rider("Lena", "Fischer")
    store.add_entry(event_id, early.rider_id, bib=1, local_group="Group A")
    rows = [
        ImportRow(first="Tess", last="Gallagher", local_group="Group A", line=2),
        ImportRow(first="Omar", last="Rahimi", local_group="groupa", line=3),
        ImportRow(first="Rosa", last="Navarro", local_group="Masters  40+", line=4),
        ImportRow(first="Kenji", last="Mori", local_group="masters 40+", line=5),
    ]
    assert [p.group for p in plan_import(store, event_id, rows)] == [
        "Group A",
        "Group A",
        "Masters 40+",
        "Masters 40+",
    ]


def test_an_import_with_no_event_keeps_the_riders_and_puts_nobody_on_a_roster(store, event_id):
    """The Riders window imports with "No event": the riders only, no bibs or groups."""
    plans = plan_import(store, None, parse(CSV))
    assert all(not p.already_entered for p in plans)
    result = apply_import(store, None, plans, range(len(plans)))
    assert len(result.created) == 4 and result.entered == []
    assert store.entries(event_id) == []
    assert result.summary() == "4 new riders, 0 riders updated."


def _one_row(bib: str = "", age: str = "30", first: str = "Ada", last: str = "Quill") -> str:
    """A minimal export: the two names, a bib and a racing age."""
    return f"Last Name,First Name,Bib,Age on 12/31/2026\r\n{last},{first},{bib},{age}\r\n"


@pytest.mark.parametrize(
    "bib", ["99999999999999999999", "1e30", "inf", "1e400", "10000", "0", "-4"]
)
def test_a_bib_that_is_no_bib_reads_as_blank_and_the_preview_says_why(store, event_id, bib):
    row = parse(_one_row(bib=bib))[0]
    assert row.bib is None
    plan = plan_import(store, event_id, [row])[0]
    assert f'A bib is a number from 1 to 9999; the file has "{bib}"' in plan.note


@pytest.mark.parametrize("age", ["99999999", "-5", "0", "inf"])
def test_an_absurd_age_gives_no_birth_year(age):
    row = parse(_one_row(age=age))[0]
    assert row.racing_age is None and row.birth_year is None


def test_a_quote_never_closed_refuses_the_file_and_names_its_line():
    text = 'Last Name,First Name,Bib\r\nLin,Bo,4\r\nQuill,"Ada,5\r\nMoss,Cy,6\r\n'
    with pytest.raises(ImportFormatError, match="line 3 has a name with a line break"):
        parse(text)


def test_a_field_over_the_csv_limit_is_not_a_csv_file():
    with pytest.raises(ImportFormatError, match="not a CSV file"):
        parse("Last Name,First Name\r\n" + '"' + "x" * 200_000 + '",Ada\r\n')


def test_names_lose_what_steers_or_hides_text_and_an_invisible_name_is_dropped():
    rows = parse(_one_row(first="\u202eAda\u2028", last="Quill") + "\u200b,\u200b,,\r\n")
    assert [(r.first, r.last) for r in rows] == [("Ada", "Quill")]


def test_details_name_the_riders_who_may_be_this_one(store, event_id):
    """The closed Status list hides the candidates; Details names them side by side."""
    store.add_rider("Rafa", "Quint", usac_license="710017")
    store.add_rider("Rafael", "Quint", birth_year=1971)
    (plan,) = plan_import(store, event_id, [ImportRow(first="Rafe", last="Quint", line=2)])
    assert plan.note == "may be Rafa Quint (USAC License 710017) or Rafael Quint (born 1971)"
    # A rider a conflict already names is not named twice.
    store.add_rider("Cora", "Abbott", usac_license="710001")
    rows = [ImportRow(first="Mate", last="Vargas", usac_license="710001", line=2)]
    (plan,) = plan_import(store, event_id, rows)
    assert plan.conflict == "USAC License 710001 is on file for Cora Abbott"
    assert plan.note == ""


def test_two_new_rows_with_one_license_are_a_conflict_and_never_one_rider(store, event_id):
    """A parent registering two children on one number: the later row is unticked, and
    ticked anyway it is a new rider without the number, never folded into the first."""
    rows = [
        ImportRow(first="Ava", last="Lindqvist", usac_license="710050", line=2),
        ImportRow(first="Noor", last="Lindqvist", usac_license="710050", line=3),
    ]
    plans = plan_import(store, event_id, rows)
    assert (plans[0].status, plans[0].conflict) == ("new", "")
    assert plans[1].status == "conflict"
    assert plans[1].conflict == "the file gives USAC License 710050 to Ava Lindqvist too"
    result = apply_import(store, event_id, plans, chosen=[0, 1])
    assert len(result.created) == 2 and len(result.entered) == 2
    ava, noor = (store.rider(i) for i in result.created)
    assert (ava.first_name, ava.usac_license) == ("Ava", "710050")
    assert (noor.first_name, noor.usac_license) == ("Noor", None)
    assert result.adjusted == [
        "Noor Lindqvist added without USAC License 710050; it is on file for another rider"
    ]


def test_two_new_rows_with_one_uci_id_are_a_conflict(store, event_id):
    rows = [
        ImportRow(first="Anne", last="Dubois", uci_id="10099900001", line=2),
        ImportRow(first="Marc", last="Dubois", uci_id="10099900001", line=3),
    ]
    plans = plan_import(store, event_id, rows)
    assert plans[1].conflict == "the file gives UCI ID 10099900001 to Anne Dubois too"
    result = apply_import(store, event_id, plans, chosen=[0, 1])
    assert [store.rider(i).uci_id for i in result.created] == ["10099900001", None]


def test_a_name_that_differs_only_in_case_is_no_change(store, event_id):
    tomas = store.add_rider("Tomas", "Galloway", usac_license="710007")
    rows = [ImportRow(first="tomas", last="GALLOWAY", usac_license="710007", line=2)]
    (plan,) = plan_import(store, event_id, rows)
    assert (plan.rider_id, plan.status, plan.changes) == (tomas.rider_id, "on_file", {})
    apply_import(store, event_id, [plan], chosen=[0])
    kept = store.rider(tomas.rider_id)
    assert (kept.first_name, kept.last_name) == ("Tomas", "Galloway")


def test_the_summary_counts_one_rider_in_the_singular():
    assert ImportResult(created=[1], updated=[2], entered=[(1, None)]).summary() == (
        "1 new rider, 1 rider updated, 1 on the event's roster."
    )
    assert ImportResult(created=[1, 2], event=False).summary() == (
        "2 new riders, 0 riders updated."
    )


def test_one_rider_registered_in_two_groups_notes_each_row_and_holds_the_later(store, event_id):
    """Which category is tonight's is the venue's call; the last row never wins silently."""
    odile = store.add_rider("Odile", "Pelletier", usac_license="710016")
    rows = [
        ImportRow(
            first="Odile", last="Pelletier", usac_license="710016", local_group="Masters 40+"
        ),
        ImportRow(first="Odile", last="Pelletier", usac_license="710016", local_group="Group W"),
    ]
    plans = plan_import(store, event_id, rows)
    assert [p.rider_id for p in plans] == [odile.rider_id, odile.rider_id]
    assert plans[0].note == "also registered as Group W (row 2)"
    assert plans[1].note == "same rider as an earlier row; also registered as Masters 40+ (row 1)"
    assert [p.start_unticked for p in plans] == [False, True]
    # Two bibs for one rider are said the same way.
    rows = [replace(r, bib=b, local_group="Group A") for r, b in zip(rows, (5, 6), strict=True)]
    plans = plan_import(store, event_id, rows)
    assert plans[0].note == "also registered with bib 6 (row 2)"
    assert plans[1].start_unticked
    # Agreeing rows are only the same rider twice.
    plans = plan_import(store, event_id, [rows[0], rows[0]])
    assert [p.start_unticked for p in plans] == [False, False]


def test_a_rostered_riders_file_bib_and_group_are_said_not_applied(store, event_id):
    """The roster's values stay the proposal; Details says what the file has instead."""
    cora = store.add_rider("Cora", "Abbott", usac_license="710001")
    store.add_entry(event_id, cora.rider_id, 1, local_group="Group B")
    row = ImportRow(first="Cora", last="Abbott", usac_license="710001", bib=20, local_group="A")
    (plan,) = plan_import(store, event_id, [row])
    assert (plan.bib, plan.group) == (1, "Group B")
    assert plan.note == "file says bib 20 (roster has 1); file says A (roster has Group B)"
    # Agreeing values say nothing; case and spaces are not a difference.
    row = replace(row, bib=1, local_group="group  b")
    assert plan_import(store, event_id, [row])[0].note == ""


def test_two_new_rows_with_one_name_note_each_other(store, event_id):
    """One person registered twice would be two riders; both stay ticked (twins exist)."""
    rows = [
        ImportRow(first="Adaeze", last="Okafor", birth_year=2001, line=2),
        ImportRow(first="Adaeze N.", last="Okafor", birth_year=2001, line=3),
        ImportRow(first="Chris", last="Novak", usac_license="710041", line=4),
        ImportRow(first="Chris", last="Novak", usac_license="710042", line=5),
    ]
    plans = plan_import(store, event_id, rows)
    assert plans[0].note == "looks like row 2, Adaeze N. Okafor"
    assert plans[1].note == "looks like row 1, Adaeze Okafor"
    assert not plans[0].conflict and not plans[1].conflict
    # Two licenses are two people, as for a name match on file.
    assert plans[2].note == plans[3].note == ""


def test_a_stored_uci_id_the_row_lacks_stops_a_name_match_as_a_license_does(store, event_id):
    tobi = store.add_rider("Tobi", "Ekwe", uci_id="10098700011")
    (plan,) = plan_import(store, event_id, [ImportRow(first="Tobi", last="Ekwe", line=2)])
    # No birth year on either side to tell a namesake apart: offered, held.
    assert (plan.rider_id, plan.status) == (None, "check")
    assert [c.rider.rider_id for c in plan.candidates] == [tobi.rider_id]
    rows = [ImportRow(first="Tobi", last="Ekwe", uci_id="10098700099", line=2)]
    assert plan_import(store, event_id, rows)[0].rider_id is None
    # A UCI ID the rider lacks is still a fill, as a license is.
    bo = store.add_rider("Bo", "Lin")
    rows = [ImportRow(first="Bo", last="Lin", uci_id="10011122233", line=2)]
    (plan,) = plan_import(store, event_id, rows)
    assert (plan.rider_id, plan.fills) == (bo.rider_id, {"uci_id": (None, "10011122233")})


def test_a_swapped_first_and_last_name_offers_the_rider(store, event_id):
    siobhan = store.add_rider("Siobhan", "O'Brien", birth_year=1995)
    (plan,) = plan_import(store, event_id, [ImportRow(first="O'Brien", last="Siobhan", line=2)])
    assert (plan.rider_id, plan.status) == (None, "new")
    assert [c.rider.rider_id for c in plan.candidates] == [siobhan.rider_id]
    assert plan.note == "may be Siobhan O'Brien (born 1995)"
    # A swapped name never makes an id match believable: the holder stays a conflict.
    store.update_rider(siobhan.rider_id, usac_license="710044")
    rows = [ImportRow(first="O'Brien", last="Siobhan", usac_license="710044", line=2)]
    (plan,) = plan_import(store, event_id, rows)
    assert plan.rider_id is None
    assert plan.conflict == "USAC License 710044 is on file for Siobhan O'Brien"


def test_a_usac_license_loses_leading_zeros_and_a_uci_id_keeps_them():
    text = "Last Name,First Name,USAC License,UCI Code\r\nQuill,Ada,0710004,01009870001\r\n"
    (row,) = parse(text)
    assert (row.usac_license, row.uci_id) == ("710004", "01009870001")
    (row,) = parse("Last Name,First Name,USAC License\r\nQuill,Ada,000\r\n")
    assert row.usac_license is None


def test_a_license_typed_with_leading_zeros_matches_the_file(store, event_id):
    """The store and the file spell a license one way, so neither makes a twin."""
    ada = store.add_rider("Ada", "Quill", usac_license="0710004")
    (plan,) = plan_import(
        store, event_id, parse("Last Name,First Name,USAC License\r\nQuill,Ada,710004\r\n")
    )
    assert (plan.rider_id, plan.matched_by) == (ada.rider_id, "license")


def test_an_id_taken_since_the_plan_stays_with_its_holder(store, event_id):
    """The plan is made before the scorer reads it; an id that another row
    or a merge took in the meantime is kept by its holder, and the rest
    of the row applies."""
    ann = store.add_rider("Ann", "Quill", usac_license="733001")
    rows = [
        ImportRow(
            first="Ann",
            last="Quill",
            usac_license="733001",
            uci_id="10055500011",
            birth_year=1990,
            line=2,
        )
    ]
    (plan,) = plan_import(store, event_id, rows)
    assert plan.fields() == {"uci_id": "10055500011", "birth_year": 1990}
    other = store.add_rider("Bruno", "Ferris", uci_id="10055500011")
    result = apply_import(store, event_id, [plan], chosen=[0])
    assert result.adjusted == [
        "Ann Quill kept the old UCI ID; 10055500011 belongs to another rider"
    ]
    kept = store.rider(ann.rider_id)
    assert (kept.uci_id, kept.birth_year) == (None, 1990)
    assert store.rider(other.rider_id).uci_id == "10055500011"


def test_a_new_row_with_a_rider_of_the_same_name_on_file_is_new_and_held(store, event_id):
    """A renewed license or a blank one this week would make a duplicate on a
    plain Import, so the row reads New?, starts unticked and
    names the rider; New or Same as is the scorer's deliberate answer."""
    rafa = store.add_rider("Rafa", "Quint", usac_license="710017")
    rows = [ImportRow(first="Rafa", last="Quint", usac_license="710027", line=2)]
    (plan,) = plan_import(store, event_id, rows)
    assert (plan.rider_id, plan.status, STATUS_TEXT[plan.status]) == (None, "check", "New?")
    assert plan.start_unticked and plan.conflict == ""
    assert plan.note == "may be Rafa Quint (USAC License 710017)"
    # Same as makes it a match.
    chosen = choose(store, event_id, [plan], 0, rafa.rider_id)[0]
    assert (chosen.rider_id, chosen.status, chosen.start_unticked) == (
        rafa.rider_id,
        "review",
        False,
    )
    # New answers the question: a new rider, ticked like any other, and it
    # stays answered when another row's choice settles the plans again.
    (new,) = choose(store, event_id, [chosen], 0, None)
    assert (new.rider_id, new.status, new.start_unticked) == (None, "new", False)
    other = ImportRow(first="Bo", last="Lin", line=3)
    plans = choose(store, event_id, [new, *plan_import(store, event_id, [other])], 1, None)
    assert plans[0].status == "new"
    # Applied as New (ticked), it is a new person; the license stays apart.
    result = apply_import(store, event_id, [plan], chosen=[0])
    assert store.rider(result.created[0]).usac_license == "710027"
    assert store.rider(rafa.rider_id).usac_license == "710017"


def test_a_weaker_candidate_keeps_a_new_row_ticked(store, event_id):
    """Only the same normalized name holds a row. An initial, a birth
    year or swapped names are offered, and the row stays New and ticked."""
    store.add_rider("Rafa", "Quint", usac_license="710017")
    store.add_rider("Odile", "Pelletier", birth_year=1980)
    store.add_rider("Siobhan", "O'Brien")
    rows = [
        ImportRow(first="Rafe", last="Quint", line=2),
        ImportRow(first="Mireille", last="Pelletier", birth_year=1980, line=3),
        ImportRow(first="O'Brien", last="Siobhan", line=4),
        # A spelling that normalizes to the same name is held.
        ImportRow(first="Odile M.", last="Pelletier", line=5),
    ]
    plans = plan_import(store, event_id, rows)
    assert [p.status for p in plans] == ["new", "new", "new", "check"]
    assert [p.start_unticked for p in plans] == [False, False, False, True]
    assert all(p.candidates for p in plans)


def test_a_first_name_of_the_same_initial_on_an_id_match_is_only_noted(store, event_id):
    """On a USAC License or UCI ID match, a
    nickname or a middle initial is not asked about every week. Details says
    what the rider registered as and the record keeps its first name."""
    marius = store.add_rider("Marius", "Fennick", usac_license="710030", birth_year=1990)
    nora = store.add_rider("Nora", "Haven", uci_id="10012300045")
    rows = [
        ImportRow(first="Mario", last="Fennick", usac_license="710030", birth_year=1990),
        ImportRow(first="Nora M.", last="Haven", uci_id="10012300045"),
    ]
    plans = plan_import(store, event_id, rows)
    assert [(p.rider_id, p.status, p.changes) for p in plans] == [
        (marius.rider_id, "on_file", {}),
        (nora.rider_id, "on_file", {}),
    ]
    assert plans[0].note == "registered as Mario"
    assert plans[1].note.endswith("; registered as Nora M.")
    apply_import(store, event_id, plans, chosen=[0, 1])
    assert store.rider(marius.rider_id).first_name == "Marius"
    assert store.rider(nora.rider_id).first_name == "Nora"


def test_another_initial_a_last_name_or_a_birth_year_on_an_id_match_is_still_a_review(
    store, event_id
):
    """The id-match nickname rule covers a first name of the same initial only."""
    store.add_rider("Marius", "Fennick", usac_license="710030", birth_year=1990)
    rows = [
        # Another initial, believed on the birth year: reviewed.
        ImportRow(first="Teo", last="Fennick", usac_license="710030", birth_year=1990),
        # Same initial, the last name spelled another way and another birth
        # year: those are reviewed.
        ImportRow(first="Mario", last="Fénnick", usac_license="710030", birth_year=1991),
    ]
    first, second = (plan_import(store, event_id, [r])[0] for r in rows)
    assert (first.status, set(first.disputes)) == ("review", {"first_name"})
    assert (second.status, set(second.disputes)) == ("review", {"last_name", "birth_year"})
    assert second.note == "registered as Mario"
    # A rider the scorer chose is not an id match: every name difference asks.
    rafa = store.add_rider("Rafa", "Quint")
    (plan,) = plan_import(store, event_id, [ImportRow(first="Rafael", last="Quint")])
    chosen = choose(store, event_id, [plan], 0, rafa.rider_id)[0]
    assert set(chosen.disputes) == {"first_name"} and chosen.note == ""


def test_a_row_with_no_license_matches_a_licensed_rider_when_both_birth_years_agree(
    store, event_id
):
    """A blank license this week is not a
    disagreement once the birth years say the same person. The rider keeps the
    stored license; nothing is written for it."""
    elin = store.add_rider("Elin", "Bergstrom", usac_license="710002", birth_year=1995)
    rows = [
        ImportRow(first="Elin", last="Bergstrom", birth_year=1995, license_text="pending"),
        ImportRow(first="Elin", last="Bergstrom", birth_year=1996),
    ]
    plans = [plan_import(store, event_id, [r])[0] for r in rows]
    assert [(p.rider_id, p.matched_by) for p in plans] == [(elin.rider_id, "name")] * 2
    assert plans[0].status == "on_file" and "usac_license" not in plans[0].changes
    # A year apart is the tolerance the name match already allows, then reviewed.
    assert set(plans[1].disputes) == {"birth_year"}
    apply_import(store, event_id, plans[:1], chosen=[0])
    assert store.rider(elin.rider_id).usac_license == "710002"


def test_a_row_with_no_license_stays_new_when_either_birth_year_is_unknown(store, event_id):
    """The birth-year guard: a namesake junior with no license and a licensed
    parent would otherwise be one rider. The same for a UCI ID."""
    store.add_rider("Elin", "Bergstrom", usac_license="710002", birth_year=1995)
    tobi = store.add_rider("Tobi", "Ekwe", uci_id="10098700011")
    store.add_rider("Kofi", "Mensah", usac_license="710009", birth_year=1970)
    rows = [
        ImportRow(first="Elin", last="Bergstrom"),
        ImportRow(first="Tobi", last="Ekwe", birth_year=2001),
        # Both known but far apart: a parent and a junior.
        ImportRow(first="Kofi", last="Mensah", birth_year=2012),
    ]
    plans = plan_import(store, event_id, rows)
    assert [(p.rider_id, p.status) for p in plans] == [(None, "check")] * 3
    # A UCI ID the row lacks stands aside on agreeing birth years, as a license does.
    store.update_rider(tobi.rider_id, birth_year=2001)
    plan = plan_import(store, event_id, rows[1:2])[0]
    assert (plan.rider_id, plan.matched_by, plan.status) == (tobi.rider_id, "name", "on_file")
