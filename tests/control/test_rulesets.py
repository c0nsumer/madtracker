"""Named rulesets: the rulebook, stored pages, the default, and the JSON file round trip."""

import json
import os
import sys

import pytest

from madtracker.control import rulesets
from madtracker.scoring import rules as R
from madtracker.scoring.replay import FORMAT_ENGINE
from madtracker.store import Store

HOUSE = dict(points_table=(10, 7, 5, 3, 2, 1), lap_points=10)


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "r.sqlite")
    yield s
    s.close()


def house_doc(name="Club") -> dict:
    doc = rulesets.apply_values(rulesets.builtin_ruleset(), **HOUSE)
    doc["name"] = name
    return doc


def test_a_points_table_is_one_comma_list_in_every_field():
    """A table reads "10, 7, 5, 3, 2, 1" in the Rulesets and the Multi-Race Standings
    fields alike; typed with spaces, semicolons, or a sheet's hyphens it still
    parses, and a leading minus stays with its number for the check to refuse."""
    assert rulesets.table_text((10, 7, 5, 3, 2, 1)) == "10, 7, 5, 3, 2, 1"
    assert rulesets.table_text(()) == ""
    for typed in ("10, 7, 5, 3, 2, 1", "10 7 5 3 2 1", "10-7-5-3-2-1", " 10;7, 5  3,2 1 "):
        assert rulesets.split_table(typed) == ["10", "7", "5", "3", "2", "1"], typed
    assert rulesets.split_table("7, -1") == ["7", "-1"]
    assert rulesets.split_table("  ") == []


def test_every_format_key_has_a_family():
    assert {k for keys in rulesets.FAMILIES.values() for k in keys} == set(FORMAT_ENGINE)
    assert rulesets.family_for("handicap") == "placings"
    # Only keys with a USAC article or a documented club source are formats.
    for gone in ("miss_and_out", "snowball", "point_a_lap", "danish", "belgian", "kabaddi"):
        with pytest.raises(ValueError):
            rulesets.family_for(gone)


def test_the_rulebook_is_built_in():
    doc = rulesets.builtin_ruleset()
    assert rulesets.validate_ruleset(doc) == []
    assert set(doc) == {"name", *rulesets.PAGE_KEYS}
    assert doc["points_table"] == [5, 3, 2, 1] and doc["points_last_double"] is True
    assert {doc[k] for k in rulesets.LAP_KEYS} == {20} and doc["survivors"] == 2
    assert (doc["places"], doc["direction"], doc["lapped_riders_placed"]) == (3, "forward", True)
    points = rulesets.rules_for(None, "rulebook", "points", sprint_count=3)
    assert points == R.points_race_rules(sprint_count=3)
    assert rulesets.rules_for(None, "Rulebook", "madison").scored_unit == "team"
    assert rulesets.rules_for(None, "rulebook", "tempo").intermediate_points == (1,)
    assert rulesets.is_builtin(" Rulebook ") and not rulesets.is_builtin("usac")
    # The stored key stays "rulebook"; the scorer sees the edition's name.
    assert rulesets.ruleset_label("rulebook") == "USAC 2025 + Club formats"
    assert rulesets.is_builtin("usac 2025 + CLUB FORMATS")
    assert rulesets.rules_for(None, "USAC 2025 + Club formats", "tempo").intermediate_points == (1,)
    # The win-and-out's values are a club's, the rest the rulebook's.
    assert rulesets.FAMILY_SOURCE == {
        "placings": "USAC 2025",
        "points": "USAC 2025",
        "madison": "USAC 2025",
        "tempo": "USAC 2025",
        "elimination": "USAC 2025",
        "win_and_out": "Club",
    }
    assert rulesets.ruleset_label("uci") == "uci"
    assert rulesets.ruleset_label("Club") == "Club"


def test_rules_for_a_stored_ruleset_with_per_race_overrides(store):
    row = rulesets.save_ruleset(store, house_doc())
    assert rulesets.ruleset_names(store) == ["rulebook", "Club"]
    assert rulesets.ruleset_for(store, "club") == row.doc

    points = rulesets.rules_for(store, "Club", "points", sprint_count=3)
    assert isinstance(points, R.SprintPointsRules)
    assert points.sprint_count == 3
    assert points.intermediate_points == (10, 7, 5, 3, 2, 1)
    assert points.final_points == (20, 14, 10, 6, 4, 2)
    assert points.lap_gained_points == points.lap_lost_points == 10
    madison = rulesets.rules_for(store, "Club", "madison", sprint_count=4)
    assert madison.intermediate_points == (5, 3, 2, 1) and madison.lap_gained_points == 10
    assert madison.scored_unit == "team" and madison.sprint_count == 4
    elim = rulesets.rules_for(store, "Club", "elimination", survivors=1)
    assert (elim.survivors, elim.final_by_sprint) == (1, False)
    keirin = rulesets.rules_for(store, "Club", "keirin", laps_count_for_ranking=False)
    assert keirin.laps_count_for_ranking is False
    assert rulesets.rules_for(store, "Club", "win_and_out", places=5).places == 5

    with pytest.raises(rulesets.UnknownRulesetError):
        rulesets.rules_for(store, "Nobody", "points")
    with pytest.raises(rulesets.UnknownRulesetError):
        rulesets.rules_for(None, "Club", "points")


def test_last_sprint_not_doubled_and_lapped_riders_sent_off():
    doc = rulesets.apply_values(
        rulesets.builtin_ruleset(),
        points_last_double=False,
        madison_table=(7, 5, 3, 2, 1),
        tempo_points=2,
        lapped_riders_placed=False,
        survivors=1,
        places=5,
        direction="reverse",
    )
    doc["name"] = "Odd"
    assert rulesets.validate_ruleset(doc) == []
    formats = rulesets.formats_for(doc)
    assert formats["points"]["final_points"] == (5, 3, 2, 1)
    assert formats["madison"]["final_points"] == (14, 10, 6, 4, 2)
    assert formats["tempo"]["intermediate_points"] == formats["tempo"]["final_points"] == (2,)
    assert formats["placings"]["lapped_riders_placed_by_laps"] is False
    assert formats["elimination"]["final_by_sprint"] is False
    assert (formats["win_and_out"]["places"], formats["win_and_out"]["direction"]) == (5, "reverse")
    with pytest.raises(ValueError, match="not ruleset values"):
        rulesets.apply_values(doc, sprint_every_laps=20)


def test_default_ruleset_setting(store):
    assert rulesets.default_ruleset_name(store) == "rulebook"
    rulesets.set_default_ruleset(store, " Rulebook ")
    assert rulesets.default_ruleset_name(store) == "rulebook"
    with pytest.raises(rulesets.UnknownRulesetError):
        rulesets.set_default_ruleset(store, "Club")
    club = rulesets.save_ruleset(store, house_doc())
    rulesets.set_default_ruleset(store, "club")
    assert rulesets.default_ruleset_name(store) == "Club"
    assert store.get_setting(rulesets.DEFAULT_SETTING) == "club"
    # The default cannot be deleted; renamed in the editor, the default follows the name.
    with pytest.raises(rulesets.DefaultRulesetError):
        rulesets.delete_ruleset(store, club.ruleset_id)
    rulesets.save_ruleset(store, house_doc("House"), club.ruleset_id)
    assert rulesets.default_ruleset_name(store) == "House"
    rulesets.set_default_ruleset(store, "rulebook")
    rulesets.delete_ruleset(store, club.ruleset_id)
    assert rulesets.ruleset_names(store) == ["rulebook"]
    # A setting that names a ruleset which is gone falls back to the rulebook.
    store.set_setting(rulesets.DEFAULT_SETTING, "House")
    assert rulesets.default_ruleset_name(store) == "rulebook"


def test_copy_and_save_refuse_built_in_and_taken_names(store):
    copy = rulesets.copy_ruleset(store, "rulebook", "Ours")
    assert copy.doc == {**rulesets.builtin_ruleset(), "name": "Ours"}
    with pytest.raises(rulesets.RulesetExistsError):
        rulesets.copy_ruleset(store, "rulebook", "ours")
    with pytest.raises(rulesets.RulesetError, match="built in"):
        rulesets.copy_ruleset(store, "Ours", "RULEBOOK")
    with pytest.raises(rulesets.RulesetError, match="built in"):
        rulesets.save_ruleset(store, house_doc("rulebook"))
    second = rulesets.copy_ruleset(store, "Ours", "Second")
    assert {k: v for k, v in second.doc.items() if k != "name"} == {
        k: v for k, v in copy.doc.items() if k != "name"
    }


def test_validation_names_the_value_and_the_problem():
    doc = house_doc()
    doc["points_table"] = []
    doc["madison_table"] = [5, "three"]
    doc["survivors"] = 0
    doc["direction"] = "sideways"
    doc["madison_lap_lost"] = -1
    del doc["places"]
    problems = rulesets.validate_ruleset(doc)
    assert problems == ["Missing: Win-and-Out places"]
    doc["places"] = 3
    problems = rulesets.validate_ruleset(doc)
    assert "Points Race sprint points: needs at least one value" in problems
    assert "Madison sprint points: must be whole numbers from 0 to 999" in problems
    assert "Elimination riders in the final sprint: must be a whole number from 1 to 20" in problems
    assert "Win-and-Out direction: must be forward or reverse" in problems
    assert "Madison lap lost: must be a whole number from 0 to 100" in problems
    assert rulesets.validate_ruleset("nope") == ["The file does not hold a ruleset"]
    assert rulesets.validate_ruleset({"name": "x"})[0].startswith("Missing: ")
    with pytest.raises(rulesets.RulesetError):
        rulesets.save_ruleset(None, doc)


def test_import_refuses_what_the_editor_cannot_hold(tmp_path):
    """A file is held to the editor's ranges, so an imported page opens and saves as it is."""
    doc = house_doc()
    doc.update(
        points_table=[rulesets.TABLE_MAX] * rulesets.MAX_COUNT,
        tempo_points=100,
        survivors=20,
        places=rulesets.MAX_COUNT,
    )
    assert rulesets.validate_ruleset(doc) == []
    doc.update(
        points_table=[rulesets.TABLE_MAX] * (rulesets.MAX_COUNT + 1),
        madison_table=[1000, 3],
        tempo_points=10**12,
        points_lap_gained=101,
        survivors=21,
        places=rulesets.MAX_COUNT + 1,
    )
    path = tmp_path / "big.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(rulesets.RulesetError) as refused:
        rulesets.read_ruleset_file(path)
    assert str(refused.value) == (
        "Could not import big.json. Points Race sprint points: must be 50 values or fewer;"
        " Madison sprint points: must be whole numbers from 0 to 999;"
        " Tempo Race points per sprint: must be a whole number from 0 to 100;"
        " Points Race lap gained: must be a whole number from 0 to 100;"
        " Elimination riders in the final sprint: must be a whole number from 1 to 20;"
        " Win-and-Out places: must be a whole number from 1 to 50"
    )


def test_a_deeply_nested_file_is_refused_as_unreadable(tmp_path):
    path = tmp_path / "deep.json"
    path.write_text("[" * 200_000 + "]" * 200_000)
    with pytest.raises(rulesets.RulesetError) as refused:
        rulesets.read_ruleset_file(path)
    assert str(refused.value) == "Could not read deep.json: it is not a ruleset file"


@pytest.mark.parametrize(
    ("make", "sentence"),
    [
        (lambda p: None, "Could not find club rules.json"),
        (lambda p: p.mkdir(), "Could not read club rules.json: it is a folder"),
        (lambda p: p.write_text(""), "Could not read club rules.json: it is not a ruleset file"),
        (
            lambda p: p.write_text("{nope"),
            "Could not read club rules.json: it is not a ruleset file",
        ),
        (
            lambda p: p.write_text("[1, 2]"),
            "Could not read club rules.json: it is not a ruleset file",
        ),
        (
            lambda p: p.write_bytes(b"\xff\xfe\x00garbage"),
            "Could not read club rules.json: it is not a ruleset file",
        ),
    ],
)
def test_an_unreadable_file_is_one_sentence_that_keeps_its_name(tmp_path, make, sentence):
    # The name stays as spelled, and no Python or JSON error text gets through.
    path = tmp_path / "club rules.json"
    make(path)
    with pytest.raises(rulesets.RulesetError) as refused:
        rulesets.read_ruleset_file(path)
    assert str(refused.value) == sentence


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod does not take read permission away here",
)
def test_a_file_without_read_permission_says_so(tmp_path):
    path = tmp_path / "club rules.json"
    path.write_text(json.dumps(house_doc()))
    path.chmod(0)
    try:
        with pytest.raises(rulesets.RulesetError) as refused:
            rulesets.read_ruleset_file(path)
    finally:
        path.chmod(0o600)
    assert str(refused.value) == "Could not read club rules.json: permission denied"


def test_a_file_that_opens_with_a_byte_order_mark_imports(store, tmp_path):
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(house_doc("Bom")).encode())
    assert rulesets.import_ruleset(store, path).name == "Bom"


def test_export_then_import_round_trip_and_name_clash(store, tmp_path):
    club = rulesets.save_ruleset(store, house_doc())
    path = rulesets.export_ruleset(club.doc, tmp_path / "out" / "club.json")
    assert json.loads(path.read_text()) == club.doc

    other = Store.open(tmp_path / "other.sqlite")
    try:
        imported = rulesets.import_ruleset(other, path)
        assert imported.doc == club.doc
        assert rulesets.rules_for(other, "Club", "points").lap_gained_points == 10
        # Same name again: refused unless replacing, and replacing keeps the row.
        with pytest.raises(rulesets.RulesetExistsError):
            rulesets.import_ruleset(other, path)
        changed = rulesets.apply_values(club.doc, lap_points=5)
        again = rulesets.export_ruleset(changed, tmp_path / "club2.json")
        replaced = rulesets.import_ruleset(other, again, replace=True)
        assert replaced.ruleset_id == imported.ruleset_id
        assert rulesets.rules_for(other, "Club", "madison").lap_lost_points == 5
    finally:
        other.close()

    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(
        rulesets.RulesetError, match="^Could not read bad.json: it is not a ruleset file$"
    ):
        rulesets.import_ruleset(store, bad)
    builtin = tmp_path / "rulebook.json"
    rulesets.export_ruleset(rulesets.builtin_ruleset(), builtin)
    with pytest.raises(rulesets.RulesetError, match="built in"):
        rulesets.import_ruleset(store, builtin)


def test_make_ruleset_tool_writes_a_valid_file(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_ruleset", "tools/make_ruleset.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = tmp_path / "house.json"
    argv = [
        "--name", "Tool house", "--points-table", "10,7,5,3,2,1", "--madison-table", "5-3-2-1",
        "--lap-points", "10", "--madison-last-single", "--out", str(out),
    ]  # fmt: skip
    assert module.main(argv) == 0
    doc = json.loads(out.read_text())
    assert doc["name"] == "Tool house"
    assert rulesets.validate_ruleset(doc) == []
    assert doc["points_table"] == [10, 7, 5, 3, 2, 1] and doc["points_last_double"] is True
    assert doc["madison_table"] == [5, 3, 2, 1] and doc["madison_last_double"] is False
    assert {doc[k] for k in rulesets.LAP_KEYS} == {10}
    assert doc["survivors"] == 2 and doc["places"] == 3


def test_every_page_value_sits_on_exactly_one_tab():
    placed = [k for keys in rulesets.FAMILY_KEYS.values() for k in keys]
    assert sorted(placed) == sorted(rulesets.PAGE_KEYS)
    assert len(placed) == len(set(placed))
    # Every offered format is named on exactly one tab.
    from madtracker.control.formats import FORMATS

    named = [f.key for family in rulesets.FAMILIES for f in rulesets.family_formats(family)]
    assert sorted(named) == sorted(f.key for f in FORMATS)


def test_a_shown_as_word_is_cut_where_a_name_is_and_a_description_later(store):
    """The venue's name for a format is drawn on cards and the board; a description is a tip."""
    doc = rulesets.apply_values(
        house_doc(),
        format_names={"madison": "M" * 100},
        format_descriptions={"madison": "D" * 700},
    )
    saved = rulesets.save_ruleset(store, doc).doc
    assert len(saved["format_names"]["madison"]) == rulesets.WORD_LIMITS["format_names"] == 60
    assert len(saved["format_descriptions"]["madison"]) == 600


def test_a_ruleset_may_name_its_formats_and_a_race_keeps_the_word(store):
    """Blank means the rulebook's label; a word set travels with the race it was made with."""
    rulebook = rulesets.builtin_ruleset()
    assert not any(k in rulebook for k in rulesets.WORD_KEYS)
    assert rulesets.format_name(rulebook, "elimination") == "Elimination"
    assert rulesets.format_description(rulebook, "elimination") == ""

    doc = rulesets.apply_values(
        house_doc(),
        format_names={"elimination": " Devil ", "chase": ""},
        format_descriptions={"elimination": "Last rider over the line every 2 laps is out"},
    )
    assert doc["format_names"] == {"elimination": "Devil"}, "blank words are dropped"
    assert rulesets.validate_ruleset(doc) == []
    club = rulesets.save_ruleset(store, doc)
    assert club.doc["format_names"] == {"elimination": "Devil"}
    assert rulesets.format_name(club.doc, "elimination") == "Devil"
    assert rulesets.format_name(club.doc, "chase") == "Scratch Race"
    assert rulesets.words_for(store, "Club", "elimination") == {
        "format_name": "Devil",
        "format_description": "Last rider over the line every 2 laps is out",
    }
    assert rulesets.words_for(store, "Club", "chase") == {}
    assert rulesets.words_for(store, "gone", "elimination") == {}, "a lost ruleset says nothing"
    # The scoring rules are untouched by the words.
    assert rulesets.rules_for(store, "Club", "elimination").survivors == doc["survivors"]

    bad = dict(doc, format_names={"snowball": "x"}, format_descriptions=["no"])
    assert rulesets.validate_ruleset(bad) == [
        "Shown as: not a format: snowball",
        "Description: must be text per format",
    ]

    event = store.add_event("Night", "2026-10-12")
    rules = rulesets.rules_for(store, "Club", "elimination").to_dict()
    race = store.add_race(event.event_id, "Devil", "elimination", rules_preset="Club",
        rules={**rules, **rulesets.words_for(store, "Club", "elimination")})  # fmt: skip
    assert rulesets.race_format_name(race) == "Devil"
    assert rulesets.race_format_description(race).startswith("Last rider")
    plain = store.add_race(event.event_id, "Plain", "elimination", rules=rules)
    assert rulesets.race_format_name(plain) == "Elimination"
    assert rulesets.race_format_description(plain) == ""
    # Renaming the format afterwards leaves the race as it was made.
    rulesets.save_ruleset(store, rulesets.apply_values(club.doc, format_names={}), club.ruleset_id)
    assert "format_names" not in store.ruleset(club.ruleset_id).doc
    assert rulesets.race_format_name(store.race(race.race_id)) == "Devil"


def test_an_unnamed_race_shows_as_its_format_beside_its_group(store):
    """A blank Name saves as group plus format; the board and program show the format alone."""
    event = store.add_event("Night", "2026-10-14")
    unnamed = store.add_race(event.event_id, "Juniors Scratch Race", "chase", group_label="Juniors")
    assert rulesets.race_short_name(unnamed) == "Scratch Race"
    spaced = store.add_race(event.event_id, "juniors  scratch race", "chase", group_label="Juniors")
    assert rulesets.race_short_name(spaced) == "Scratch Race"
    named = store.add_race(event.event_id, "Juniors Final", "chase", group_label="Juniors")
    assert rulesets.race_short_name(named) == "Juniors Final"
    # Moved to another group after it was saved: its name is no longer the default.
    moved = store.add_race(event.event_id, "Juniors Scratch Race", "chase", group_label="Cat 4")
    assert rulesets.race_short_name(moved) == "Juniors Scratch Race"
    no_group = store.add_race(event.event_id, "Scratch Race", "chase")
    assert rulesets.race_short_name(no_group) == "Scratch Race"


def test_words_survive_the_file_round_trip(store, tmp_path):
    doc = rulesets.apply_values(house_doc(), format_names={"madison": "Mad"})
    club = rulesets.save_ruleset(store, doc)
    path = rulesets.export_ruleset(club.doc, tmp_path / "club.json")
    assert rulesets.read_ruleset_file(path)["format_names"] == {"madison": "Mad"}


def test_each_sprint_format_prices_its_own_laps(store):
    doc = rulesets.apply_values(house_doc(), lap_points=10, madison_lap_gained=15, lap_lost=12)
    assert (doc["points_lap_gained"], doc["points_lap_lost"]) == (10, 12)
    assert (doc["madison_lap_gained"], doc["madison_lap_lost"]) == (15, 12)
    assert (doc["tempo_lap_gained"], doc["tempo_lap_lost"]) == (10, 12)
    rulesets.save_ruleset(store, doc)
    assert rulesets.rules_for(store, "Club", "madison").lap_gained_points == 15
    assert rulesets.rules_for(store, "Club", "points").lap_gained_points == 10
    assert rulesets.rules_for(store, "Club", "tempo").lap_lost_points == 12


def test_each_tab_says_whose_values_it_holds():
    assert rulesets.family_source_line("points") == "USAC 2025, article 2M"
    assert rulesets.family_source_line("win_and_out") == "Club format"
    assert rulesets.family_source_line("placings") == "", "the table says it per row"
    from madtracker.control.formats import FORMATS

    texts = {f.key: f.source_text for f in FORMATS}
    assert texts["chase"] == "Scratch Race (USAC 2C)"
    assert texts["chariot"] == "Chariot (Club)"
