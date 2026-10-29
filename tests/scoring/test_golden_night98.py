"""Golden tests from a venue's real sheets (bibs and team colors only).

Sources: a venue's race night 98 sheets (2026-09-26) and a published
2025 result sheet. These pin that the engines reproduce what the
venue's workbook produced, and where the workbook needed a hand edit (a DNF overtyped on a rider at
-35), that the software gives the same answer by rule.

The house values are spelled out here rather than taken from a preset:
nothing in the app knows them (a venue keeps them in a stored
ruleset), and the tests must keep pinning the real sheets regardless.
"""

from madtracker.scoring import compute_for_format
from madtracker.scoring.actions import FinishOrder, LapGained, LapLost, SprintResult, Status
from madtracker.scoring.rules import SprintPointsRules

# The venue's workbook: a lap worth 10, the points race
# awarding 10-7-5-3-2-1 with the last sprint doubled, the madison sheet
# awarding 5-3-2-1 doubled. The sheets ran sprints every 20 laps, so the
# 60-lap points race had 3 and the 80-lap madison 4.
HOUSE_LAP = 10
HOUSE_POINTS_TABLE = (10, 7, 5, 3, 2, 1)


def house_points_rules(sprints: int) -> SprintPointsRules:
    return SprintPointsRules(
        sprint_count=sprints,
        intermediate_points=HOUSE_POINTS_TABLE,
        final_points=tuple(2 * p for p in HOUSE_POINTS_TABLE),
        lap_gained_points=HOUSE_LAP,
        lap_lost_points=HOUSE_LAP,
    )


def house_madison_rules(sprints: int) -> SprintPointsRules:
    return SprintPointsRules(
        sprint_count=sprints,
        intermediate_points=(5, 3, 2, 1),
        final_points=(10, 6, 4, 2),
        lap_gained_points=HOUSE_LAP,
        lap_lost_points=HOUSE_LAP,
        scored_unit="team",
    )


def test_night98_group_b_six_mile_points():
    """Night 98 Group B, "6 Mile Points, 3 sprints, 10,7,5,3,2,1 pts, dpls".

    The workbook's PLACE column had DNF typed over bib 22's -35; here the
    DNF is a status and the rider still shows the points, ranked last.
    """
    rules = house_points_rules(3)
    assert rules.sprint_count == 3
    bibs = [12, 35, 4, 18, 22]
    actions = [
        SprintResult(1, [[35], [12], [18], [4], [22]]),
        SprintResult(2, [[35], [18], [12], [22]]),
        LapGained([35]),
        LapGained([35]),
        LapLost([22]),
        LapLost([22]),
        LapLost([22]),
        LapLost([22]),
        Status(22, "DNF", "four laps down"),
        SprintResult(3, [[35], [18], [12]]),
        FinishOrder([[35], [18], [12], [4]]),
    ]
    standings = compute_for_format("points", rules, bibs, actions)
    totals = {row.entrant_id: row.total_points for row in standings.rows}
    assert totals == {35: 60, 18: 26, 12: 22, 4: 3, 22: -35}
    assert [row.entrant_id for row in standings.rows] == [35, 18, 12, 4, 22]
    assert [row.rank for row in standings.rows] == [1, 2, 3, 4, 5]
    assert standings.by_entrant(22).status == "DNF"
    assert standings.by_entrant(35).sprint_points == (10, 10, 20)
    assert standings.by_entrant(35).lap_points == 20
    assert standings.by_entrant(22).lap_points == -40
    assert standings.is_complete


def test_night98_group_a_eight_mile_madison():
    """Night 98 Group A 8 Mile Madison: 4 sprints, 5-3-2-1 then 10-6-4-2, lap 10.

    Per-sprint places are derived from the sheet's points columns:
    Blue 1,2,2,0; Red 0,1,0,6; Orange 3,0,1,2; Yellow 5,5,3,10; Black 2,3,5,4.
    """
    BLUE, RED, ORANGE, YELLOW, BLACK = 1, 2, 3, 4, 5
    rules = house_madison_rules(4)
    assert rules.sprint_count == 4
    teams = [BLUE, RED, ORANGE, YELLOW, BLACK]
    actions = [
        SprintResult(1, [[YELLOW], [ORANGE], [BLACK], [BLUE]]),
        SprintResult(2, [[YELLOW], [BLACK], [BLUE], [RED]]),
        SprintResult(3, [[BLACK], [YELLOW], [BLUE], [ORANGE]]),
        *[LapLost([RED]) for _ in range(4)],
        *[LapLost([ORANGE]) for _ in range(3)],
        SprintResult(4, [[YELLOW], [RED], [BLACK], [ORANGE]]),
        FinishOrder([[YELLOW], [RED], [BLACK], [ORANGE], [BLUE]]),
    ]
    standings = compute_for_format("madison", rules, teams, actions)
    totals = {row.entrant_id: row.total_points for row in standings.rows}
    assert totals == {YELLOW: 23, BLACK: 14, BLUE: 5, ORANGE: -24, RED: -33}
    assert [row.entrant_id for row in standings.rows] == [YELLOW, BLACK, BLUE, ORANGE, RED]
    assert [row.rank for row in standings.rows] == [1, 2, 3, 4, 5]
    assert standings.by_entrant(BLUE).sprint_points == (1, 2, 2, 0)
    assert standings.by_entrant(RED).sprint_points == (0, 1, 0, 6)
    assert standings.by_entrant(RED).lap_points == -40


def test_dec_2025_pro_100_lap_madison_stars_and_stripes():
    """A published 2025 result sheet: sprints 3+5+5+5+10 = 28, lap +10, total 38."""
    STARS, OTHER = 7, 8
    rules = house_madison_rules(5)
    assert rules.sprint_count == 5
    actions = [
        SprintResult(1, [[OTHER], [STARS]]),
        SprintResult(2, [[STARS], [OTHER]]),
        SprintResult(3, [[STARS], [OTHER]]),
        SprintResult(4, [[STARS], [OTHER]]),
        LapGained([STARS]),
        SprintResult(5, [[STARS], [OTHER]]),
        FinishOrder([[STARS], [OTHER]]),
    ]
    standings = compute_for_format("madison", rules, [STARS, OTHER], actions)
    stars = standings.by_entrant(STARS)
    assert stars.sprint_points == (3, 5, 5, 5, 10)
    assert stars.lap_points == 10
    assert stars.total_points == 38
    assert stars.rank == 1
