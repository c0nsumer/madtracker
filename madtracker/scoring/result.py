"""Standings: what every engine returns.

One row per entrant, in display order: ranked rows first, then the DNF
group, then the unranked statuses. Ranks are shared on true ties (1, 1,
3) because USAC 1M6(a) gives a group the judges cannot separate an equal
placing and UCI 3.3.012 A ranks non-finisher groups the same way.

Rows carry the work behind the total (per-sprint points, laps, lap
points, place in the final sprint) so the result table and the printed
sheet can show it and a second person can check it against the
officials' sheet. Published club sheets contain arithmetic
errors, which is the whole argument for showing the work.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Standing:
    """One entrant's line in the standings.

    rank: shared on ties, None while unranked (still racing, DNS, DQ, DNP).
    status: None for a finisher or a rider still in, else a STATUSES code.
    final_sprint_place: place across the line at the end (the finish
    order for placings races, the final sprint for points races).
    eliminated_at: 1 for the first rider out, 2 for the next, and so on.
    tied: this row shares its rank with at least one other.
    out_of_finish: a mishap kept the rider out of the final sprint and
    they are placed on the points and laps held before it (USAC 2M7(b),
    2M8(a)). Not a status: the row ranks among the finishers.
    withdrawn: the rider was withdrawn, or is classified as though they
    had been, and ranks after every finisher by the moment of it (USAC
    2O3(e), 1M6(d)). Not a status: the row prints its number.
    adjust_points: the officials' rulings on points, summed; negative
    for a penalty (USAC 8D5(b)). Part of total_points, shown on its own
    so the sheet's arithmetic can be checked.
    """

    entrant_id: int
    rank: int | None = None
    status: str | None = None
    total_points: int | float = 0
    sprint_points: tuple[int, ...] = ()
    laps_gained: int = 0
    laps_lost: int = 0
    lap_points: int = 0
    adjust_points: int = 0
    # Laps gained that the officials ruled not to count (USAC 8D5(b)):
    # the gain is struck from laps_gained, and the sheet notes the ruling
    # beside the name.
    laps_not_counted: int = 0
    final_sprint_place: int | None = None
    eliminated_at: int | None = None
    tied: bool = False
    out_of_finish: bool = False
    withdrawn: bool = False
    notes: tuple[str, ...] = ()

    @property
    def net_laps(self) -> int:
        return self.laps_gained - self.laps_lost

    @property
    def placed(self) -> bool:
        """Whether this row holds a place the sheet prints as a number.

        A rank alone is not enough: every engine ranks the DNF group after
        the finishers so the table has an order, and the sheet prints the
        code there, not the number. The elimination is the exception: a
        rider who abandons or crashes out is eliminated at that moment
        (USAC 2E3(d)(i), 2E4(a)(ii), 2E4(d)) and takes the next place out
        like any rider the bell put out, so that row prints its number
        with the reason beside it.
        """
        return self.rank is not None and (self.status is None or self.eliminated_at is not None)

    def with_note(self, note: str) -> "Standing":
        return replace(self, notes=(*self.notes, note))


@dataclass(frozen=True)
class Standings:
    """Ordered rows plus what the live UI needs to drive the next entry."""

    rows: tuple[Standing, ...] = ()
    next_sprint_no: int = 1
    remaining_entrants: tuple[int, ...] = ()
    is_complete: bool = False
    # Complete by the officials' call to let the results stand (USAC 2M6,
    # 2N5), with no final sprint: the sheet says so beside the state.
    ended: bool = False
    # The sprint count in force in a Points Race, Madison, or Tempo Race:
    # the rules' count, or the one the officials shortened the race to
    # (USAC 1G4(b)). The sheet, the board, and the task read it from here,
    # since the race's own count stays as it was set. None in a format
    # without sprints, or before the count is set.
    sprint_count: int | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def by_entrant(self, entrant_id: int) -> Standing:
        for row in self.rows:
            if row.entrant_id == entrant_id:
                return row
        raise KeyError(entrant_id)

    def ranked(self) -> tuple[Standing, ...]:
        return tuple(row for row in self.rows if row.rank is not None)

    def ranks(self) -> dict[int, int | None]:
        return {row.entrant_id: row.rank for row in self.rows}


def rank_groups(
    groups: Iterable[Sequence[Standing]], *, start: int = 1
) -> tuple[list[Standing], int]:
    """Assign shared ranks to ordered groups of rows.

    Each group takes the rank ``start`` plus the number of rows ranked
    ahead of it, so two tied for first are followed by third
    (USAC 1M6(a)). Returns the ranked rows and the next free rank.
    """
    out: list[Standing] = []
    rank = start
    for group in groups:
        if not group:
            continue
        tied = len(group) > 1
        for row in group:
            out.append(replace(row, rank=rank, tied=tied))
        rank += len(group)
    return out, rank
