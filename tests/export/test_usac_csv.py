import csv

from madtracker.control.formats import FORMATS
from madtracker.export import write_usac_csv
from madtracker.export.usac_csv import DISCIPLINE_BY_FORMAT, HEADERS, discipline_for
from madtracker.scoring import rules as R

# USAC's "2024 Results template.csv", character for character
# (docs/research/usac-results-export.md, "The column list").
HEADER_LINE = (
    "Race Date,Race discipline,Race Category,Race Gender,Race Class,Race Age Group,"
    "Rider License,Rider First Name,Rider Last Name,Rider Place"
)


def read(path):
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    return raw, list(csv.reader(text.split("\r\n")[:-1]))


def test_the_file_is_the_template_header_crlf_and_no_bom(store, event, seeded, tmp_path):
    out = tmp_path / "usac.csv"
    report = write_usac_csv(store, event[0], out)
    raw, rows = read(out)
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\r\n") and raw.count(b"\n") == raw.count(b"\r\n")
    assert raw.decode().split("\r\n")[0] == HEADER_LINE
    assert tuple(rows[0]) == HEADERS and len(HEADERS) == 10
    body = rows[1:]
    assert all(len(r) == 10 for r in body)
    assert report.rows_written == len(body) == 12
    assert [f[0] for f in report.race_fields] == ["Chase A", "Points B", "Madison C"]

    chase = body[:4]
    # Defaults: the format's code, Mixed, blank category, class and age group.
    assert chase[0] == ["3/6/2026", "SR", "", "Mixed", "", "", "100001", "Ada", "Wren", "1"]
    # Tied ranks repeat, the next place skips, and a missing license is blank.
    assert [r[9] for r in chase] == ["1", "2", "2", "4"]
    assert chase[2][6] == "" and chase[2][7:9] == ["Bo", "Tran"]
    assert chase[1][8] == "Łukasik"


def test_every_offered_format_has_a_usac_results_site_code():
    assert {f.key for f in FORMATS} == set(DISCIPLINE_BY_FORMAT)
    assert DISCIPLINE_BY_FORMAT == {
        "chase": "SR",
        "handicap": "SR",
        "elimination": "ER",
        "match_sprint": "SPR",
        "keirin": "KEIR",
        "points": "PR",
        "madison": "MAD",
        "tempo": "TMPR",
        "unknown_distance": "SR",
        "chariot": "SR",
        "win_and_out": "SR",
    }


def test_a_row_per_race_carries_its_format_code_and_the_override_wins(
    store, event, seeded, tmp_path
):
    event_id, _ids = event
    for fmt, code in DISCIPLINE_BY_FORMAT.items():
        assert discipline_for(store.add_race(event_id, f"Test {fmt}", fmt)) == code
    assert discipline_for(store.add_race(event_id, "Odd", "some_new_format")) == "SR"

    out = tmp_path / "usac.csv"
    write_usac_csv(store, event_id, out)
    _, rows = read(out)
    # The points race's stored override ("pr") is written as the scorer set it.
    assert [r[1] for r in rows[1:]] == ["SR"] * 4 + ["pr"] * 4 + ["MAD"] * 4
    store.update_race(seeded["points"], usac_discipline=None)
    write_usac_csv(store, event_id, out, races=[seeded["points"]])
    _, rows = read(out)
    assert {r[1] for r in rows[1:]} == {"PR"}


def test_explicit_fields_status_and_text_age_group(store, event, seeded, tmp_path):
    out = tmp_path / "usac.csv"
    write_usac_csv(store, event[0], out, races=[seeded["points"]])
    _, rows = read(out)
    body = rows[1:]
    assert len(body) == 4
    assert all(r[1:6] == ["pr", "Cat 3", "Women", "Senior", "9-14"] for r in body)
    assert {r[8]: r[9] for r in body}["Park"] == "DNF"
    assert [r[9] for r in body if r[9] != "DNF"] == ["1", "2", "3"]


def test_values_are_trimmed(store, event, seeded, tmp_path):
    store.update_race(seeded["chase"], usac_category="  Cat 3/4 ", usac_class=" Junior  ")
    out = tmp_path / "usac.csv"
    write_usac_csv(store, event[0], out, races=[seeded["chase"]])
    _, rows = read(out)
    assert {tuple(r[2:5]) for r in rows[1:]} == {("Cat 3/4", "Mixed", "Junior")}


def test_madison_members_share_the_team_place(store, event, seeded, tmp_path):
    out = tmp_path / "usac.csv"
    report = write_usac_csv(store, event[0], out, races=[seeded["mad"]])
    _, rows = read(out)
    body = rows[1:]
    assert all(r[1] == "MAD" and r[3] == "Mixed" for r in body)
    by_last = {r[8]: r[9] for r in body}
    assert by_last["Wren"] == by_last["Łukasik"]
    assert by_last["Tran"] == by_last["Park"]
    assert {by_last["Wren"], by_last["Tran"]} == {"1", "2"}
    assert any("fewer than 3" in w or "finisher" in w for w in report.race_notes)


def test_the_report_keeps_the_unfinished_and_the_unlicensed_apart(store, event, seeded, tmp_path):
    report = write_usac_csv(store, event[0], tmp_path / "usac.csv")
    # The left-out races, the race notes and the riders with no license
    # each come apart for the message box.
    assert "Elimination D" not in [f[0] for f in report.race_fields]
    assert report.left_out == ("Elimination D",)
    assert report.unlicensed == ("Bo Tran",)
    assert not any("Elimination D" in n or "Bo Tran" in n for n in report.race_notes)


def test_the_report_names_each_race_as_usac_files_it(store, event, seeded, tmp_path):
    report = write_usac_csv(store, event[0], tmp_path / "usac.csv")
    assert report.race_fields == (
        ("Chase A", "SR", "", "", "Mixed"),
        ("Points B", "pr", "Cat 3", "Senior", "Women"),
        ("Madison C", "MAD", "", "", "Mixed"),
    )


def test_an_unfinished_race_writes_no_rows(store, event, seeded, tmp_path):
    from madtracker.control.race import LiveRace

    s = LiveRace(store, seeded["elim"])
    assert s.click(s.roster.ids[0]).ok
    out = tmp_path / "usac.csv"
    report = write_usac_csv(store, event[0], out, races=[seeded["elim"]])
    assert report.rows_written == 0
    assert report.left_out == ("Elimination D",)


def test_blank_category_warns_once_per_race_and_licenses_once_per_rider(
    store, event, seeded, tmp_path
):
    """Bo Tran's missing license is listed once, not once per race, and a
    blank Race Category is mentioned."""
    report = write_usac_csv(store, event[0], tmp_path / "usac.csv")
    blank = [w for w in report.race_notes if "no Category" in w]
    assert sorted(w.split(":")[0] for w in blank) == ["Chase A", "Madison C"]
    assert report.unlicensed.count("Bo Tran") == 1


def test_race_gender_is_written_as_stored_and_mixed_when_never_set(store, event, seeded, tmp_path):
    store.update_race(seeded["chase"], usac_gender=None)
    store.update_race(seeded["points"], usac_gender="Women")
    out = tmp_path / "usac.csv"
    write_usac_csv(store, event[0], out, races=[seeded["chase"], seeded["points"]])
    _, rows = read(out)
    assert {r[3] for r in rows[1:5]} == {"Mixed"}
    assert {r[3] for r in rows[5:]} == {"Women"}


def test_a_shared_bib_and_a_rider_without_one_export_as_they_stand(store, event, seeded, tmp_path):
    """Bibs are unique per race, not per event, and a roster entry may still lack one.

    The file has no bib column, so both riders are written by name alone.
    """
    from madtracker.control.race import LiveRace
    from madtracker.export import write_results_pdf
    from madtracker.scoring import rules as R

    event_id, ids = event
    eve = store.add_rider("Eve", "Sol").rider_id
    store.add_entry(event_id, eve, 2, local_group="Cat 3")
    store.add_entry(event_id, store.add_rider("Fay", "Nobib").rider_id, None)
    race = store.add_race(event_id, "Scratch D", "scratch", rules=R.placings_rules().to_dict())
    store.add_race_entry(race.race_id, eve)
    store.add_race_entry(race.race_id, ids[4])
    s = LiveRace(store, race.race_id)
    assert s.click(eve).ok and s.click(ids[4]).ok
    out = tmp_path / "usac.csv"
    write_usac_csv(store, event_id, out)
    _raw, rows = read(out)
    names = {(r[7], r[8]) for r in rows[1:]}
    assert ("Eve", "Sol") in names and ("Zoe", "Łukasik") in names
    assert ("Fay", "Nobib") not in names, "never raced, so in no race's rows"
    write_results_pdf(store, event_id, tmp_path / "results.pdf")


def test_races_usac_cannot_tell_apart_are_named_before_uploading(store, event, seeded, tmp_path):
    """Two chariot races of one group can share the same six fields;
    the template has no race name, so USAC may file them as one."""
    from madtracker.control.race import LiveRace

    event_id, ids = event
    twin = store.add_race(event_id, "Chase A2", "chase", rules=R.placings_rules().to_dict())
    for bib in (1, 2, 3, 4):
        store.add_race_entry(twin.race_id, ids[bib])
    s = LiveRace(store, twin.race_id)
    for bib in (1, 2, 3, 4):
        assert s.click(ids[bib]).ok
    report = write_usac_csv(store, event_id, tmp_path / "usac.csv")
    note = (
        "Chase A and Chase A2 have the same USAC details, so USAC may file them as one race."
        " To keep them apart, edit one, change its Category, Class, or Age group, and export again."
    )
    assert note in report.race_notes
    # Case alone does not tell them apart; a Class does.
    store.update_race(twin.race_id, usac_class="Junior")
    report = write_usac_csv(store, event_id, tmp_path / "usac.csv")
    assert not any("same USAC details" in n for n in report.race_notes)
    # Only races in the file are compared: the unfinished elimination is not.
    assert not any("Elimination D" in n for n in report.race_notes)


def test_the_look_alike_note_lists_three_with_a_serial_comma():
    from madtracker.export.usac_csv import look_alike_note

    assert look_alike_note(["A", "B", "C"]).startswith("A, B, and C have the same")


def test_the_file_has_the_shape_of_an_upload_usac_accepted(store, event, seeded, tmp_path):
    """A two-day event's file that USAC's upload accepted has these traits,
    apart from the Age Group column (the template's, left blank here):
    nine of our ten headers in its order, M/D/YYYY dates without leading
    zeros, CRLF, plain ASCII with nothing quoted, SR, ER, and MAD as the
    discipline codes, numeric places, a blank license where a rider has
    none, and a Madison written as one row per rider with the team's place
    on both. The venue files every race as Category Open with the group,
    distance, and format in Class."""
    out = tmp_path / "usac.csv"
    write_usac_csv(store, event[0], out)
    raw, rows = read(out)
    accepted_headers = [
        "Race Date",
        "Race discipline",
        "Race Category",
        "Race Gender",
        "Race Class",
        "Rider License",
        "Rider First Name",
        "Rider Last Name",
        "Rider Place",
    ]
    assert [h for h in rows[0] if h != "Race Age Group"] == accepted_headers
    body = rows[1:]
    for r in body:
        month, day, year = r[0].split("/")
        assert month == str(int(month)) and day == str(int(day)) and len(year) == 4
    assert {discipline_for(race) for race in store.races(event[0])} >= {"SR", "MAD"}
    assert DISCIPLINE_BY_FORMAT["elimination"] == "ER"
    assert b'"' not in raw.replace(b'"\xc5\x81ukasik"', b"")
    madison = [r for r in body if r[1] == "MAD"]
    assert len(madison) == 4
    places = [r[9] for r in madison]
    assert places == ["1", "1", "2", "2"]
    assert all(r[6] == "" or r[6].isdigit() for r in body)
    # The template's own value sets: Race Gender is one of its words, and
    # Rider Place is a number or one of its four status words, never blank.
    assert {r[3] for r in body} <= {"Men", "Women", "Both", "Mixed", "Male", "Female", "M", "W"}
    assert all(r[9].isdigit() or r[9] in ("DNF", "DNS", "DQ", "DNP") for r in body)
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.count(b"\n") == raw.count(b"\r\n") == len(rows)
