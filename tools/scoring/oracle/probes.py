"""Hand probes behind the report's observations. Run and read; each
block prints what the engine or its validation does with one input."""

from madtracker.scoring import compute_for_format as C
from madtracker.scoring import validate_for_format as V
from madtracker.scoring.actions import (
    Eliminated,
    FinishOrder,
    LapGained,
    LapLost,
    LapNotCounted,
    PointsAdjusted,
    SprintResult,
    Status,
    Withdrawn,
)
from madtracker.scoring.rules import (
    EliminationRules,
    PlacingsRules,
    SprintPointsRules,
    WinAndOutRules,
)


def show(tag, st):
    print(
        f"  {tag}:",
        [(r.entrant_id, r.rank, r.status, r.total_points, r.final_sprint_place) for r in st.rows],
        "complete" if st.is_complete else "running",
    )


print("1. Reverse win-and-out, running: the DNF rank against the held places")
W = WinAndOutRules(places=5, direction="reverse")
show(
    "lap 1 only (67 holds 5th), 2 DNF, 3 racing",
    C("win_and_out", W, [67, 2, 3], [SprintResult(1, [[67]]), Status(2, "DNF")]),
)
show(
    "laps 1 and 2 (67 5th, 4 4th), 2 DNF, 3 racing",
    C(
        "win_and_out",
        W,
        [67, 2, 3, 4],
        [SprintResult(1, [[67]]), SprintResult(2, [[4]]), Status(2, "DNF")],
    ),
)
show(
    "same, then an empty finish",
    C("win_and_out", W, [67, 2], [SprintResult(1, [[67]]), Status(2, "DNF"), FinishOrder([])]),
)
Wf = WinAndOutRules(places=5, direction="forward")
show(
    "forward for comparison",
    C("win_and_out", Wf, [67, 2, 3], [SprintResult(1, [[67]]), Status(2, "DNF")]),
)

print("2. Win-and-out dead heat on a place lap: the rank step after it")
show(
    "forward 3: lap 1 (1,2), lap 2 3, fill 4, 5",
    C(
        "win_and_out",
        WinAndOutRules(places=3),
        [1, 2, 3, 4, 5],
        [SprintResult(1, [[1, 2]]), SprintResult(2, [[3]]), FinishOrder([[4], [5]])],
    ),
)
show(
    "reverse 3: lap 1 1, lap 2 (2,3), fill 4",
    C(
        "win_and_out",
        WinAndOutRules(places=3, direction="reverse"),
        [1, 2, 3, 4],
        [SprintResult(1, [[1]]), SprintResult(2, [[2, 3]]), FinishOrder([[4]])],
    ),
)
show(
    "reverse 3: lap 1 1, lap 2 2, fill (4,3) tied",
    C(
        "win_and_out",
        WinAndOutRules(places=3, direction="reverse"),
        [1, 2, 3, 4],
        [SprintResult(1, [[1]]), SprintResult(2, [[2]]), FinishOrder([[4, 3]])],
    ),
)
show(
    "reverse 3: lap 1 1, lap 2 (2,3), nobody left (empty finish)",
    C(
        "win_and_out",
        WinAndOutRules(places=3, direction="reverse"),
        [1, 2, 3],
        [SprintResult(1, [[1]]), SprintResult(2, [[2, 3]]), FinishOrder([])],
    ),
)

print("3. Points race: nothing ranked until a sprint or the finish is in")
R = SprintPointsRules(sprint_count=2)
show("a lap gained, no sprint yet", C("points", R, [1, 2, 3], [LapGained([1])]))
show("one sprint", C("points", R, [1, 2, 3], [SprintResult(1, [[1], [2]])]))

print("4. A finish order that contradicts the final sprint entered on its own")
R1 = SprintPointsRules(sprint_count=1)
log = [SprintResult(1, [[1], [2]])]
print("  validation:", V("points", R1, [1, 2, 3], log, FinishOrder([[2], [1], [3]])))
show(
    "points from the sprint, tie-break from the finish",
    C("points", R1, [1, 2, 3], log + [FinishOrder([[2], [1], [3]])]),
)

print("5. An empty place group (the X) is accepted and read differently per engine")
print(
    "  points:",
    V("points", R, [1, 2, 3], [], SprintResult(1, [[1], [], [2]])),
    "scratch:",
    V("scratch", PlacingsRules(), [1, 2, 3], [], FinishOrder([[1], [], [2]])),
)
show(
    "scratch [[1], [], [2]]",
    C("scratch", PlacingsRules(), [1, 2, 3], [FinishOrder([[1], [], [2]])]),
)
show("points sprint [[1], [], [2]]", C("points", R, [1, 2, 3], [SprintResult(1, [[1], [], [2]])]))

print("6. Laps off the ranking: a lap is accepted, the ruling on it is refused")
P = PlacingsRules(laps_count_for_ranking=False)
print(
    "  LapGained:",
    V("scratch", P, [1, 2], [], LapGained([1])),
    "LapNotCounted:",
    V("scratch", P, [1, 2], [LapGained([1])], LapNotCounted([1])),
)
show(
    "the lap shows and does not rank",
    C("scratch", P, [1, 2, 3], [LapGained([3]), FinishOrder([[1], [2], [3]])]),
)

print("7. A second status with a different code")
print("  DNF then DQ:", V("points", R, [1, 2], [Status(1, "DNF")], Status(1, "DQ")))
print(
    "  penalty on a DNF rider:", V("points", R, [1, 2], [Status(1, "DNF")], PointsAdjusted(1, -3))
)

print("8. Elimination: the bell may go below the survivor count")
E = EliminationRules(survivors=2)
print("  validation:", V("elimination", E, [1, 2, 3], [Eliminated(1, [3])], Eliminated(2, [2])))
show(
    "survivors 2, one left",
    C("elimination", E, [1, 2, 3], [Eliminated(1, [3]), Eliminated(2, [2])]),
)

print("9. Tempo Race: two withdrawn, the later withdrawal ranks higher (R-OMNI-5)")
T = SprintPointsRules(
    sprint_count=4, intermediate_points=(1,), final_points=(1,), lap_gained_points=20
)
show(
    "3 withdrawn after sprint 1, then 1 after sprint 2; 2 and 4 still racing",
    C(
        "tempo",
        T,
        [1, 2, 3, 4],
        [
            SprintResult(1, [[3]]),
            Withdrawn(3),
            SprintResult(2, [[1]]),
            Withdrawn(1),
        ],
    ),
)
print(
    "  a sprint naming 3 after the mark:",
    V("tempo", T, [1, 2, 3, 4], [Withdrawn(3)], SprintResult(1, [[3]])),
)

print("10. A withdrawal, then a DQ: the status wins and the row has no rank")
show(
    "2 withdrawn then DQ, finish 1, 3",
    C(
        "scratch",
        PlacingsRules(),
        [1, 2, 3],
        [Withdrawn(2), Status(2, "DQ"), FinishOrder([[1], [3]])],
    ),
)
print(
    "  DNF after the mark:",
    V("scratch", PlacingsRules(), [1, 2, 3], [Withdrawn(2)], Status(2, "DNF")),
)

print("11. UCI lapped switch: a withdrawn rider on negative laps")
U = PlacingsRules(laps_count_for_ranking=True, lapped_riders_placed_by_laps=False)
show(
    "3 a lap down then withdrawn, finish 1, 2",
    C("scratch", U, [1, 2, 3], [LapLost([3]), Withdrawn(3), FinishOrder([[1], [2]])]),
)
print(
    "  each row's withdrawn flag:",
    [
        (r.entrant_id, r.withdrawn)
        for r in C("scratch", U, [1, 2, 3], [LapLost([3]), Withdrawn(3)]).rows
    ],
)
