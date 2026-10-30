"""Aggregates: team omnium, overall-for-the-day, UCI omnium table."""

from dataclasses import replace

from madtracker.scoring import aggregate
from madtracker.scoring.result import Standing, Standings
from madtracker.scoring.rules import (
    AggregateRules,
    team_omnium_rules,
    uci_omnium_rules,
    usac_omnium_rules,
)


def race(*rows, complete=True):
    """Build a finished Standings from (entrant, rank, total[, status[, final place]])."""
    built = []
    for spec in rows:
        eid, rank, total = spec[:3]
        status = spec[3] if len(spec) > 3 else None
        final = spec[4] if len(spec) > 4 else None
        built.append(
            Standing(
                entrant_id=eid,
                rank=rank,
                total_points=total,
                status=status,
                final_sprint_place=final,
            )
        )
    return Standings(rows=tuple(built), is_complete=complete)


def ranks(standings):
    return {row.entrant_id: row.rank for row in standings.rows}


def test_team_omnium_sums_madison_totals():
    """A published 2025 result sheet: Stars & Stripes 50 + 21 + 38 = 109."""
    races = [
        race((1, 1, 50), (2, 2, 30)),
        race((1, 2, 21), (2, 1, 40)),
        race((1, 1, 38), (2, 2, 20)),
    ]
    standings = aggregate.compute(team_omnium_rules(), [1, 2], races)
    assert standings.by_entrant(1).total_points == 109
    assert standings.by_entrant(1).sprint_points == (50, 21, 38)
    assert standings.by_entrant(2).total_points == 90
    assert ranks(standings) == {1: 1, 2: 2}
    assert standings.is_complete


def test_place_table_scores_each_rank():
    """USAC 2B19(e) omnium scoring with the older 7-5-3-2-1 table (USAC16 2O1)."""
    races = [race((1, 1, 0), (2, 2, 0), (3, 6, 0)), race((1, 2, 0), (2, 1, 0), (3, 3, 0))]
    standings = aggregate.compute(usac_omnium_rules(), [1, 2, 3], races)
    assert standings.by_entrant(1).total_points == 12
    assert standings.by_entrant(3).total_points == 3  # 6th is off the table
    assert standings.by_entrant(3).sprint_points == (0, 3)


def test_tie_broken_by_most_firsts_then_last_race():
    """USAC 2B19(e): most firsts, then seconds, and so on; then the last race."""
    # 1 and 2 both have 7 + 5 = 12 with one first each; 2 placed better in the last race.
    races = [race((1, 1, 0), (2, 2, 0)), race((1, 2, 0), (2, 1, 0))]
    standings = aggregate.compute(usac_omnium_rules(), [1, 2], races)
    assert ranks(standings) == {2: 1, 1: 2}
    # Most firsts beats the last race: 3 has two firsts and 4 has one first
    # and two seconds, both 14 on a 7-5-3 table.
    races = [
        race((3, 1, 0), (4, 2, 0)),
        race((3, 1, 0), (4, 2, 0)),
        race((3, 5, 0), (4, 1, 0)),
    ]
    standings = aggregate.compute(usac_omnium_rules((7, 5, 3, 2, 1)), [3, 4], races)
    assert standings.by_entrant(3).total_points == 15
    assert standings.by_entrant(4).total_points == 17
    # Equal totals needed for the tie-break: give 3 a 2-point bump via a 4th race.
    races.append(race((3, 4, 0), (4, 10, 0)))
    standings = aggregate.compute(usac_omnium_rules((7, 5, 3, 2, 1)), [3, 4], races)
    assert standings.by_entrant(3).total_points == standings.by_entrant(4).total_points == 17
    assert ranks(standings) == {3: 1, 4: 2}


def test_tie_break_skips_races_where_neither_placed():
    """USAC 2B19(e): if neither placed in the last race, use the nearest race where one did."""
    races = [
        race((1, 2, 0), (2, 1, 0)),
        race((1, 1, 0), (2, 2, 0)),
        race((1, None, 0, "DNS"), (2, None, 0, "DNS")),
    ]
    standings = aggregate.compute(usac_omnium_rules(), [1, 2], races)
    assert ranks(standings) == {1: 1, 2: 2}


def test_identical_records_share_the_rank():
    races = [race((1, 1, 0), (2, 1, 0)), race((1, 2, 0), (2, 2, 0))]
    standings = aggregate.compute(usac_omnium_rules(), [1, 2], races)
    assert ranks(standings) == {1: 1, 2: 1}
    assert standings.by_entrant(1).tied


def test_must_finish_all_leaves_non_finishers_unranked():
    """San Diego's rule: ride every race or no omnium place."""
    rules = AggregateRules(points_by_place=(5, 3, 2, 1), must_finish_all=True)
    races = [race((1, 1, 0), (2, 2, 0)), race((2, 1, 0), (1, None, 0, "DNF"))]
    standings = aggregate.compute(rules, [1, 2], races)
    assert standings.by_entrant(1).rank is None
    assert standings.by_entrant(2).rank == 1
    assert standings.rows[-1].entrant_id == 1


def test_absent_and_non_finisher_points_are_configurable():
    rules = AggregateRules(points_by_place=(5, 3), dnf_points=1, absent_points=-1)
    races = [race((1, 1, 0), (2, None, 0, "DNF")), race((1, 1, 0))]
    standings = aggregate.compute(rules, [1, 2], races)
    assert standings.by_entrant(2).sprint_points == (1, -1)
    assert standings.by_entrant(2).total_points == 0


def test_multipliers_weight_races():
    rules = AggregateRules(points_by_place=(10, 8), multipliers=(1, 2.5))
    races = [race((1, 1, 0), (2, 2, 0)), race((1, 2, 0), (2, 1, 0))]
    standings = aggregate.compute(rules, [1, 2], races)
    assert standings.by_entrant(2).total_points == 33
    assert standings.by_entrant(1).total_points == 30


def test_low_points_direction():
    """USAC 7C3: junior omnium, 1 point for 1st, lowest total wins."""
    rules = AggregateRules(points_by_place=tuple(range(1, 25)), direction="low")
    races = [race((1, 1, 0), (2, 2, 0)), race((1, 3, 0), (2, 2, 0))]
    standings = aggregate.compute(rules, [1, 2], races)
    assert standings.by_entrant(1).total_points == 4
    assert standings.by_entrant(2).total_points == 4
    # Tie on 4: most firsts wins (USAC 7C3(g) uses the same order).
    assert ranks(standings) == {1: 1, 2: 2}


def test_uci_omnium_table_and_points_race_carried_in():
    """UCI 3.2.250, 3.2.251, 3.2.252: 40-38-36 for three races, raw points race
    added on, ties by the points race's final sprint."""
    rules = uci_omnium_rules()
    entrants = list(range(1, 23))
    first_three = [race(*((eid, eid, 0) for eid in entrants)) for _ in range(3)]
    # Rider 2 scores 25 raw points in the final points race and overtakes
    # rider 1, who leads 120 to 114 going in (UCI 3.2.251: raw points add on).
    points_race = Standings(
        rows=tuple(
            Standing(entrant_id=eid, rank=eid, total_points=25 if eid == 2 else 0)
            for eid in entrants
        ),
        is_complete=True,
    )
    standings = aggregate.compute(rules, entrants, first_three + [points_race])
    assert standings.by_entrant(1).total_points == 120
    assert standings.by_entrant(2).total_points == 3 * 38 + 25
    assert standings.by_entrant(21).total_points == 3  # 21st and below score 1
    assert standings.by_entrant(22).total_points == 3
    assert ranks(standings)[2] == 1
    assert ranks(standings)[1] == 2


def test_uci_omnium_tie_broken_by_final_sprint_of_points_race():
    rules = uci_omnium_rules()
    first_three = [
        race((1, 1, 0), (2, 2, 0)),
        race((2, 1, 0), (1, 2, 0)),
        race((1, 1, 0), (2, 1, 0)),
    ]
    points_race = race((1, 1, 10, None, 2), (2, 1, 10, None, 1))
    standings = aggregate.compute(rules, [1, 2], first_three + [points_race])
    assert standings.by_entrant(1).total_points == standings.by_entrant(2).total_points
    assert ranks(standings) == {2: 1, 1: 2}


def test_validate_flags_missing_races_and_strangers():
    rules = AggregateRules(points_by_place=(5, 3), multipliers=(1,), sum_total_races=(5,))
    races = [race((1, 1, 0), (9, 2, 0)), race((1, 1, 0), complete=False)]
    problems = aggregate.validate(rules, [1, 2], races)
    assert any("multipliers" in p for p in problems)
    assert any("entrant 9" in p for p in problems)
    assert any("not complete" in p for p in problems)
    assert any("sum_total_races" in p for p in problems)


def test_validate_flags_a_final_sprint_race_past_the_last_race():
    races = [race((1, 1, 0), (2, 2, 0)), race((1, 1, 0), (2, 2, 0))]
    rules = AggregateRules(tie_break="last_race_final_sprint", final_sprint_race=1)
    assert not aggregate.validate(rules, [1, 2], races)
    rules = AggregateRules(tie_break="last_race_final_sprint", final_sprint_race=2)
    problems = aggregate.validate(rules, [1, 2], races)
    assert problems == ["final_sprint_race names race 2 but only 2 were given"]


def test_team_omnium_dnf_keeps_its_madison_points():
    """UCI 3.3.012 A: a team that DNFs a madison keeps the points it
    scored there, so the team omnium sums them like everyone else's."""
    races = [race((1, 1, 10), (2, 2, -20), (3, 3, -35, "DNF"))]
    standings = aggregate.compute(team_omnium_rules(), [1, 2, 3], races)
    assert standings.by_entrant(3).total_points == -35
    assert ranks(standings) == {1: 1, 2: 2, 3: 3}
    # Summed, the DNF's points count: 30 - 5 beats 10 + 10.
    races = [race((1, 1, 30), (2, 2, 10)), race((2, 1, 10), (1, 2, -5, "DNF"))]
    standings = aggregate.compute(team_omnium_rules(), [1, 2], races)
    assert standings.by_entrant(1).total_points == 25
    assert ranks(standings) == {1: 1, 2: 2}


def test_uci_omnium_abandon_is_out_and_listed_dnf_after_every_finisher():
    """UCI 3.2.251bis, USAC 2O2(c), 2O3(d): a rider who does not start or
    abandons any race is out of the omnium, placed after the last rider as
    DNF, however many points the earlier races gave."""
    rules = uci_omnium_rules()
    first_three = [
        race((1, 1, 0), (2, 2, 0), (3, 3, 0)),
        race((1, 1, 0), (2, 2, 0), (3, 3, 0)),
        race((1, 1, 0), (2, 2, 0), (3, 3, 0)),
    ]
    points_race = race((2, 1, 10, None, 1), (3, 2, 0, None, 2), (1, 3, 30, "DNF"))
    standings = aggregate.compute(rules, [1, 2, 3], first_three + [points_race])
    assert [row.entrant_id for row in standings.rows] == [2, 3, 1]
    assert ranks(standings) == {2: 1, 3: 2, 1: None}
    assert standings.by_entrant(1).status == "DNF"


def test_a_rider_out_of_the_points_race_finish_by_a_mishap_stays_in_the_four_race_omnium():
    """USAC 2M7(b), 2M8(a) via 2O2: a rider the mishap rule keeps out of the
    finish is placed by the Points Race on the points held, with no status,
    so the omnium ranks them (2O3(d) covers abandons, which are DNF)."""
    rules = uci_omnium_rules()
    first_three = [race((1, 1, 0), (2, 2, 0), (3, 3, 0))] * 3
    out_by_mishap = race((2, 1, 10, None, 1), (3, 2, 4, None, 2), (1, 3, 6))
    out_by_mishap = Standings(
        rows=tuple(
            replace(row, out_of_finish=True) if row.entrant_id == 1 else row
            for row in out_by_mishap.rows
        ),
        is_complete=True,
    )
    standings = aggregate.compute(rules, [1, 2, 3], first_three + [out_by_mishap])
    assert standings.by_entrant(1).status is None
    assert ranks(standings) == {1: 1, 2: 2, 3: 3}
    assert standings.by_entrant(1).total_points == 40 * 3 + 6
    abandoned = race((2, 1, 10, None, 1), (3, 2, 4, None, 2), (1, 3, 6, "DNF"))
    standings = aggregate.compute(rules, [1, 2, 3], first_three + [abandoned])
    assert standings.by_entrant(1).status == "DNF" and ranks(standings)[1] is None


def test_team_omnium_tie_level_in_the_last_race_shares_the_rank():
    """USAC 2B19(e): level on total and on firsts and seconds, the tie goes
    to the last race; level there too, the rule stops and the teams share,
    even though they placed differently earlier."""
    races = [
        race((1, 1, 20), (2, 2, 10)),
        race((2, 1, 20), (1, 2, 10)),
        race((1, 3, 5), (2, 3, 5)),
    ]
    standings = aggregate.compute(team_omnium_rules(), [1, 2], races)
    assert standings.by_entrant(1).total_points == standings.by_entrant(2).total_points == 35
    assert ranks(standings) == {1: 1, 2: 1}
    assert standings.by_entrant(1).tied


def test_a_summed_race_carries_an_unranked_row_total():
    """A Madison with a lap gained and no sprint yet: its rows have no rank, but the
    lap's points are in the total and the team omnium sums the total (R-TEAM-1)."""
    races = [race((1, None, 10), (2, None, -10), complete=False)]
    standings = aggregate.compute(team_omnium_rules(), [1, 2], races)
    assert standings.by_entrant(1).total_points == 10
    assert standings.by_entrant(2).total_points == -10
    # A place table has no place to convert, so an unranked row scores nothing there.
    tabled = aggregate.compute(usac_omnium_rules(), [1, 2], races)
    assert tabled.by_entrant(1).total_points == 0


def test_a_place_the_race_gave_a_dnf_rider_scores_from_the_table():
    """An Elimination puts a DNF out at that moment and gives the next place
    (USAC 2E3(d)(i), 2E4): the row is placed, and a place table scores that
    place, as the race sheet prints it. A DNF the race did not place scores
    the DNF points, and is no place in the countback."""
    placed_dnf = Standing(entrant_id=1, rank=4, total_points=0, status="DNF", eliminated_at=2)
    plain_dnf = Standing(entrant_id=2, rank=4, total_points=0, status="DNF")
    finisher = Standing(entrant_id=3, rank=3, total_points=0)
    races = [Standings(rows=(placed_dnf, plain_dnf, finisher), is_complete=True)]
    rules = usac_omnium_rules(points_by_place=(7, 5, 3, 2, 1))
    standings = aggregate.compute(rules, [1, 2, 3], races)
    assert standings.by_entrant(1).total_points == 2
    assert standings.by_entrant(2).total_points == 0
    assert ranks(standings) == {3: 1, 1: 2, 2: 3}


def test_the_unranked_tail_lists_the_dnf_group_then_dq():
    """Out of the omnium, the rows follow the finishers as DNF then DQ,
    whatever order the entrants came in (R-NF-2)."""
    rules = uci_omnium_rules()
    first = race((1, 1, 0, "DQ"), (2, 2, 0, "DNF"), (3, 3, 0), (4, 4, 0, "DNF"))
    standings = aggregate.compute(rules, [1, 2, 3, 4], [first])
    assert [(r.entrant_id, r.status) for r in standings.rows] == [
        (3, None),
        (2, "DNF"),
        (4, "DNF"),
        (1, "DQ"),
    ]


def test_an_omnium_penalty_comes_off_the_total_before_ranking():
    """USAC 2O3(e): 40 omnium points off, the rider staying in; carried as a
    negative adjustment so the sheet can show it, and no race's own result
    changes."""
    rules = uci_omnium_rules()
    first_three = [race((1, 1, 0), (2, 2, 0)) for _ in range(3)]
    points_race = race((1, 1, 10, None, 1), (2, 2, 6, None, 2))
    standings = aggregate.compute(rules, [1, 2], first_three + [points_race], {1: 40})
    assert standings.by_entrant(1).total_points == 120 + 10 - 40
    assert standings.by_entrant(1).adjust_points == -40
    assert standings.by_entrant(2).total_points == 114 + 6
    assert standings.by_entrant(2).adjust_points == 0
    assert ranks(standings) == {2: 1, 1: 2}


def test_a_withdrawn_rider_is_placed_by_the_race_and_stays_in_the_four_race_omnium():
    """USAC 2O3(e): the withdrawn rider takes the next available rank in the
    Scratch Race or Tempo Race and stays in the omnium; the 40 is the
    scorer's Omnium Penalty, never the race's doing (R-OMNI-5). The place
    points follow the rank the race gave."""
    rules = uci_omnium_rules()
    withdrawn = race((2, 1, 0), (3, 2, 0), (1, 3, 0))
    withdrawn = Standings(
        rows=tuple(replace(r, withdrawn=True) if r.entrant_id == 1 else r for r in withdrawn.rows),
        is_complete=True,
    )
    plain = [race((1, 1, 0), (2, 2, 0), (3, 3, 0))] * 2
    points_race = race((1, 1, 30, None, 1), (2, 2, 20, None, 2), (3, 3, 10, None, 3))
    standings = aggregate.compute(rules, [1, 2, 3], [withdrawn, *plain, points_race])
    one = standings.by_entrant(1)
    assert one.status is None and one.total_points == 36 + 40 + 40 + 30
