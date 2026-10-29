"""The program sheet: every race with its riders by name, for the riders and the announcer."""

import pytest

from madtracker.export import program as prog
from madtracker.scoring import rules as R


@pytest.fixture
def night(store):
    """Two groups, a rider with no group, and one rider without a bib yet."""
    event = store.add_event("Program Night", "2026-03-06", venue="Test Velodrome")
    ids = {}
    people = [
        (1, "Ada", "Wren", "A"),
        (2, "Bo", "Tran", "A"),
        (3, "Cy", "Park", "A"),
        (4, "Di", "Lowe", "A"),
        (7, "Gus", "Hale", "B"),
        (None, "Ike", "Ono", "B"),
        (9, "Jo", "Kerr", ""),
    ]
    for bib, first, last, group in people:
        rider = store.add_rider(first, last)
        store.add_entry(event.event_id, rider.rider_id, bib, local_group=group)
        ids[first] = rider.rider_id
    return event.event_id, ids


def _race(store, event_id, name, fmt, riders, group="", rules=None):
    rules = rules or R.placings_rules()
    race = store.add_race(event_id, name, fmt, rules=rules.to_dict(), group_label=group)
    for rid in riders:
        store.add_race_entry(race.race_id, rid)
    return race


def test_a_race_saved_without_a_name_is_headed_by_its_format_beside_its_group(store, night):
    """The sheet reads "Scratch Race" with the group tag "A", as the window and
    the board do, never "A Scratch Race" beside "A"."""
    event_id, ids = night
    _race(store, event_id, "A Scratch", "scratch", [ids["Ada"]], "A")
    [race] = prog.build_program(store, event_id)
    assert (race.name, race.group) == ("Scratch", "A")
    assert prog.detail_text(race) == race.format_label


def test_every_race_lists_its_whole_field_by_bib_whatever_the_group(store, night):
    """All the riders in each race by name, the group beside the race."""
    event_id, ids = night
    field = [ids[n] for n in ("Jo", "Bo", "Ike", "Gus", "Ada")]
    _race(store, event_id, "Scratch Final", "scratch", field, "A")
    [race] = prog.build_program(store, event_id)
    assert (race.number, race.name, race.group) == (1, "Scratch Final", "A")
    # Bib order, a rider without a bib last; riders from another group or
    # none are listed like the rest.
    assert [r.listed for r in race.riders] == [
        "1 Ada Wren",
        "2 Bo Tran",
        "7 Gus Hale",
        "9 Jo Kerr",
        "Ike Ono",
    ]


def test_an_empty_race_and_a_madison_list_what_they_have(store, night):
    event_id, ids = night
    _race(store, event_id, "Later", "scratch", [], "A")
    madison = store.add_race(event_id, "A Madison", "madison", group_label="A")
    for name, color, pair in (("Red", "Red", "Ada Bo"), ("Fast Pair", "Blue", "Cy Di")):
        team = store.add_team(madison.race_id, name, color=color)
        for first in pair.split():
            store.add_race_entry(madison.race_id, ids[first])
            store.add_team_member(team.team_id, ids[first])
    later, mad = prog.build_program(store, event_id)
    assert later.empty
    # A team named for its color prints the color once.
    # The bibs bare, as the rider grid prints them.
    assert [(t.color, t.name, [r.listed for r in t.riders]) for t in mad.teams] == [
        ("Red", "", ["1 Ada Wren", "2 Bo Tran"]),
        ("Blue", "Fast Pair", ["3 Cy Park", "4 Di Lowe"]),
    ]


def test_scoring_says_what_a_rider_needs():
    points = R.SprintPointsRules(
        sprint_count=3, intermediate_points=(10, 7, 5, 3, 2, 1), final_points=(20, 14, 10, 6, 4, 2)
    )
    assert prog.scoring_text(points) == "3 sprints, 10-7-5-3-2-1, double points for the last sprint"
    plain = R.SprintPointsRules(sprint_count=1, intermediate_points=(1,), final_points=(1,))
    assert prog.scoring_text(plain) == "1 sprint, 1 point to the winner"
    other = R.SprintPointsRules(sprint_count=2, intermediate_points=(5, 3), final_points=(6, 4))
    assert prog.scoring_text(other) == "2 sprints, 5-3, last sprint 6-4"
    assert prog.scoring_text(R.placings_rules()) == ""


def test_the_format_shows_under_every_race_whatever_its_name_says():
    race = prog.ProgramRace(1, "Elimination", "A", "Elimination", "")
    assert prog.detail_text(race) == "Elimination"
    race = prog.ProgramRace(1, "6 Mile Points", "A", "Points Race", "3 sprints, 5-3-2-1")
    assert prog.detail_text(race) == "Points Race  |  3 sprints, 5-3-2-1"


def test_the_program_sheet_is_portrait(store, night, tmp_path, drawn):
    """The program is read down a column of riders, so it keeps the portrait page."""
    event_id, ids = night
    _race(store, event_id, "Scratch", "scratch", [ids["Ada"], ids["Bo"]])
    prog.write_program_pdf(store, event_id, tmp_path / "p.pdf")
    assert drawn and all(d["page_w"] < d["page_h"] for d in drawn)


def _fits(drawn) -> None:
    for d in drawn:
        if "{nb}" in d["text"]:
            continue
        assert d["width"] <= d["w"] - 2 * d["margin"] + 0.01, d
        assert d["y"] + d["h"] <= d["page_h"] + 0.01, d


def test_the_sheet_writes_every_rider_and_nothing_overflows(store, night, tmp_path, drawn):
    event_id, ids = night
    _race(store, event_id, "A Scratch", "scratch", [ids["Ada"], ids["Gus"], ids["Jo"]], "A")
    _race(store, event_id, "B Points", "points", [ids["Gus"], ids["Ike"]], "B",
          R.SprintPointsRules(sprint_count=3))  # fmt: skip
    out = prog.write_program_pdf(store, event_id, tmp_path / "program.pdf")
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and b"pdfaid:part" in data
    texts = [d["text"] for d in drawn]
    assert texts.count("Gus Hale") == 2 and "Jo Kerr" in texts and "Ike Ono" in texts
    assert "3 riders" in texts and "2 riders" in texts
    assert any("Generated " in t for t in texts)
    _fits(drawn)


def test_a_race_starts_on_a_fresh_page_rather_than_split(store, night, tmp_path, drawn):
    event_id, ids = night
    for n in range(14):
        _race(store, event_id, f"Race {n + 1}", "scratch", list(ids.values()))
    prog.write_program_pdf(store, event_id, tmp_path / "long.pdf")
    assert len({d["page"] for d in drawn}) >= 2
    # Each race's heading shares its page with its last rider, Ike (no bib).
    for h in (d for d in drawn if d["text"].startswith("Race ")):
        after = [d for d in drawn if d["page"] == h["page"] and d["y"] > h["y"]]
        assert any(d["text"] == "Ike Ono" for d in after), h["text"]
    _fits(drawn)


def test_long_names_wrap_rather_than_being_cut(store, night, tmp_path, drawn):
    """A long venue, event, series, or race name wraps rather than being cut with "..."."""
    from madtracker.export.pdf import write_results_pdf

    event_id, ids = night
    store.set_setting("venue/name", "Riverside Track Arena Lakeport Michigan")
    store.update_event(
        event_id,
        name="Pro Series Race Night Number Twelve of the Season",
        series="Winter Track League 2026-27 Season",
    )
    race = _race(store, event_id, "Semi-Pro A and B Combined Twelve Mile Scratch Race with Primes",
                 "scratch", [ids["Ada"], ids["Gus"]], "SemiPro A Masters 40 Plus")  # fmt: skip
    from madtracker.control.race import LiveRace

    live = LiveRace(store, race.race_id)
    for rid in (ids["Ada"], ids["Gus"]):
        live.click(rid)
    prog.write_program_pdf(store, event_id, tmp_path / "p.pdf")
    write_results_pdf(store, event_id, tmp_path / "r.pdf")
    cut = [d["text"] for d in drawn if "…" in d["text"]]
    assert not cut
    texts = " ".join(d["text"] for d in drawn)
    assert "Riverside Track Arena Lakeport Michigan" in texts
    _fits(drawn)


def test_the_program_and_the_results_share_one_heading(store, night, tmp_path, drawn):
    """The two sheets' headings share one size and layout."""
    from madtracker.control.race import LiveRace
    from madtracker.export.pdf import write_results_pdf

    event_id, ids = night
    _race(store, event_id, "Warm Up", "scratch", [ids["Ada"]], "A")
    race = _race(store, event_id, "Scratch Final", "scratch", [ids["Ada"], ids["Bo"]], "A")
    live = LiveRace(store, race.race_id)
    for rid in (ids["Ada"], ids["Bo"]):
        live.click(rid)
    prog.write_program_pdf(store, event_id, tmp_path / "p.pdf")
    program = list(drawn)
    drawn.clear()
    write_results_pdf(store, event_id, tmp_path / "r.pdf")
    results = list(drawn)

    def heading(cells):
        name = next(d for d in cells if d["text"] == "Scratch Final")
        number = next(d for d in cells if d["text"] == "2." and d["page"] == name["page"])
        return name["size"], name["x"] - number["x"], number["size"]

    # The program's place number, before the name at the same size and offset.
    assert heading(program) == heading(results)
    assert any("Results" in d["text"] for d in results)
    assert any(d["text"].startswith("Program") for d in program)


def test_the_results_line_reads_as_the_program_plus_the_laps():
    """One wording for both sheets, from the race's own rules."""
    from madtracker.export.summary import rules_line

    rulebook = R.SprintPointsRules(sprint_count=4)
    assert prog.scoring_text(rulebook) == "4 sprints, 5-3-2-1, double points for the last sprint"
    assert (
        rules_line(rulebook)
        == "4 sprints, 5-3-2-1, double points for the last sprint; laps \u00b120"
    )
    tempo = R.SprintPointsRules(
        sprint_count=10,
        intermediate_points=(2,),
        final_points=(2,),
        lap_gained_points=20,
        lap_lost_points=10,
    )
    assert (
        rules_line(tempo) == "10 sprints, 2 points to the winner; lap gained +20, lap lost \u221210"
    )


def test_a_team_line_too_long_for_one_line_lists_a_rider_per_line_and_reports_whole_names(
    store, night, tmp_path, drawn
):
    event_id, ids = night
    store.update_rider(ids["Ada"], first_name="\u674e", last_name="Konstantinopoulou-Papadimitriou")
    store.update_rider(ids["Bo"], first_name="Wolfgang-Amadeus", last_name="Van Der Westhuizen")
    madison = store.add_race(event_id, "A Madison", "madison")
    team = store.add_team(
        madison.race_id, "Extremely Long Sponsored Team Name Racing p/b Sponsors", color="Red"
    )
    for first in ("Ada", "Bo"):
        store.add_race_entry(madison.race_id, ids[first])
        store.add_team_member(team.team_id, ids[first])
    missing: list[str] = []
    prog.write_program_pdf(store, event_id, tmp_path / "t.pdf", unprintable=missing)
    texts = [d["text"] for d in drawn]
    # The team's name on its own line, then each rider whole on a line of
    # their own, as every surface with the height lists a pair; nothing is
    # split around a " / ".
    assert "Extremely Long Sponsored Team Name Racing p/b Sponsors" in texts
    assert "2 Wolfgang-Amadeus Van Der Westhuizen" in texts
    assert not any("/" in t and "Westhuizen" in t for t in texts), texts
    # The export's warning names whole texts, not every trial piece of a line.
    assert missing
    assert not any(a != b and b.startswith(a) for a in missing for b in missing), missing
    _fits(drawn)


def test_a_cut_race_name_keeps_continued_on_its_next_page(store, night, tmp_path, drawn):
    """The suffix goes on after the cut, so a long name keeps it."""
    event_id, _ = night
    event = store.event(event_id)
    riders = []
    for n in range(200):
        rider = store.add_rider(f"Rider{n}", "Test")
        store.add_entry(event.event_id, rider.rider_id, 100 + n)
        riders.append(rider.rider_id)
    name = "Big " + "Extraordinarily Long Sponsored Race Name " * 6
    _race(store, event_id, name.strip(), "scratch", riders)
    prog.write_program_pdf(store, event_id, tmp_path / "cut.pdf")
    later = [d["text"] for d in drawn if d["page"] == 2 and d["size"] >= 11]
    assert any(t.endswith("… (continued)") for t in later), later
    _fits(drawn)
