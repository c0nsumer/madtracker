"""Invented sample data for the demo mode, the mockups and the UI tests.

All names are made up. Totals are computed here from the per-sprint values
rather than typed, so the sample can never show the kind of arithmetic
slip the published sheets have. This is not the scoring engine: it sums
and sorts just enough to make a believable picture.
"""

from madtracker.board.payloads import (
    Elimination,
    Entry,
    Finish,
    Header,
    Placing,
    PreRace,
    SprintResult,
    StandingRow,
    Standings,
)

VENUE_NAME = ""
EVENT_NAME = "Demo Race Night"

# Bib, name. Group A and Group B are separate fields, as on a real night.
GROUP_A = [
    ("3", "Marcus Delgado"),
    ("5", "Priya Okafor"),
    ("8", "Tom Kowalczyk"),
    ("11", "Jenna Whitfield"),
    ("14", "Luis Ferreira"),
    ("17", "Dana Brooks"),
    ("21", "Sam Ostrowski"),
    ("24", "Kenji Mori"),
    ("27", "Ava Lindqvist"),
    ("31", "Ray Duchene"),
    ("36", "Nora Haddad"),
    ("42", "Eli Brandt"),
]
GROUP_B = [
    ("4", "Corey Abernathy"),
    ("7", "Maya Petrakis"),
    ("9", "Ben Szymanski"),
    ("12", "Tess Gallagher"),
    ("19", "Omar Rahimi"),
    ("22", "Lena Fischer"),
    ("33", "Jack Moreau"),
    ("38", "Rosa Navarro"),
    ("45", "Isaac Pell"),
    ("51", "Hana Yoon"),
]


def _rider(bib: str, field: list[tuple[str, str]]) -> Entry:
    name = dict(field)[bib]
    return Entry(bibs=[bib], names=[name])


def pre_race() -> PreRace:
    return PreRace(
        header=Header(
            title="6 Mile Points",
            group="Group B",
            detail="Points Race",
            status="Start list",
        ),
        roster=[Entry(bibs=[b], names=[n]) for b, n in GROUP_B],
    )


def elimination() -> Elimination:
    out_order = ["42", "17", "31", "8"]
    remaining = [_rider(b, GROUP_A) for b, _ in GROUP_A if b not in out_order]
    return Elimination(
        header=Header(
            title="Elimination",
            group="Group A",
            detail="Elimination",
            status=f"{len(out_order)} of {len(GROUP_A)} out",
        ),
        remaining=remaining,
        last_eliminated=_rider(out_order[-1], GROUP_A),
        eliminated=[_rider(b, GROUP_A) for b in out_order[:-1]],
    )


def _rank(rows: list[StandingRow]) -> list[StandingRow]:
    # Ties go to the better place in the latest sprint run, which is close
    # enough to the house rule for a picture.
    def latest(row: StandingRow) -> int:
        run = [s for s in row.sprints if s is not None]
        return run[-1] if run else 0

    rows.sort(key=lambda r: (-r.total, -latest(r)))
    for i, row in enumerate(rows, start=1):
        row.rank = i
    return rows


def _rows(entries, sprints_by_key, laps_by_key, lap_value, sprint_count, key):
    rows = []
    for entry in entries:
        k = key(entry)
        sprints = list(sprints_by_key.get(k, []))
        sprints += [None] * (sprint_count - len(sprints))
        laps = laps_by_key.get(k, 0)
        lap_points = laps * lap_value
        total = sum(s for s in sprints if s is not None) + lap_points
        rows.append(StandingRow(0, entry, sprints, laps=laps, lap_points=lap_points, total=total))
    return _rank(rows)


def sprint_points(with_result: bool = False) -> Standings:
    # After Sprint 2 of 3; 10-7-5-3-2-1 per sprint.
    s = {
        "12": [10, 7],
        "7": [7, 10],
        "33": [5, 0],
        "4": [3, 5],
        "19": [0, 3],
        "22": [2, 0],
        "9": [1, 2],
        "38": [0, 1],
        "45": [0, 0],
        "51": [0, 0],
    }
    laps = {"19": 1, "51": -1}
    entries = [Entry(bibs=[b], names=[n]) for b, n in GROUP_B]
    rows = _rows(entries, s, laps, 10, 3, key=lambda e: e.bibs[0])
    result = None
    if with_result:
        order = ["7", "12", "4", "19", "9", "38"]
        result = SprintResult(
            number=2,
            of=3,
            placings=[
                (i + 1, _rider(b, GROUP_B), pts)
                for i, (b, pts) in enumerate(zip(order, [10, 7, 5, 3, 2, 1], strict=True))
            ],
        )
    return Standings(
        header=Header(
            title="6 Mile Points",
            group="Group B",
            detail="Points Race",
            status="After Sprint 2 of 3",
        ),
        sprint_count=3,
        rows=rows,
        current_sprint=2,
        sprint_result=result,
    )


MADISON_TEAMS = [
    ("Blue", "3", "24"),
    ("Red", "5", "36"),
    ("Orange", "8", "27"),
    ("Yellow", "11", "21"),
    ("Black", "14", "31"),
]


def finish() -> Finish:
    order = ["7", "12", "33", "4", "22", "9", "19", "45", "38", "51"]
    return Finish(
        header=Header(
            title="2 Mile Chase",
            group="Group B",
            detail="12 laps",
            status="Final results",
        ),
        placings=[Placing(i + 1, _rider(b, GROUP_B)) for i, b in enumerate(order)],
    )
