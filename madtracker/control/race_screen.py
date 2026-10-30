"""The scoring surface as plain data: what ``LiveRace.screen()`` returns.

Each function takes the race first and reads it; none writes to it or
to the store.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import count
from typing import TYPE_CHECKING

from madtracker.board import payloads as P
from madtracker.control import rulesets
from madtracker.control.describe import row_note
from madtracker.control.race_words import (
    DONE_MARKS,
    NOTHING_TO_UNDO_LABEL,
    REVIEW_ACTIONS,
    RIDER_ACTIONS,
    UNDO,
)
from madtracker.scoring._common import with_results
from madtracker.scoring.actions import Action, Withdrawn
from madtracker.scoring.result import Standing, Standings
from madtracker.store import Action as Row

if TYPE_CHECKING:
    from madtracker.control.race import LiveRace, Task


@dataclass(frozen=True)
class Card:
    entrant_id: int
    entry: P.Entry
    badge: int | None
    actions: tuple[tuple[str, str], ...]
    # Net laps gained, shown on the card: a lap before the finish has no
    # result row yet, and the card is where the scorer clicked.
    laps: int = 0
    # The badge's place is shared with another card (a dead heat).
    tied: bool = False
    # The badge's place is past the places this sprint awards: it scores nothing.
    past_awarded: bool = False
    # The entrant takes no click now (placed, out, or marked), and the card
    # holds its slot so no other card moves.
    done: bool = False
    # What sits where the badge sits on a done card: the bare place, as the
    # result row numbers it, or the status's short word.
    done_text: str = ""
    # The done text is a status word, drawn as a chip; otherwise it is a
    # place, drawn as the place badge.
    done_status: bool = False
    # The status's long name, for the chip's tooltip; "" on a placed card.
    done_tip: str = ""


@dataclass(frozen=True)
class ResultRow:
    """One line of the result so far: a place, filled or still open."""

    place: int
    entrant_id: int | None = None
    entry: P.Entry | None = None
    place_text: str = ""
    sprints: tuple[int | None, ...] = ()
    laps: int = 0
    lap_points: int = 0
    # The officials' points rulings, signed as the engine sums them:
    # negative for a penalty, 0 when there is none. The table writes it
    # as the laps column writes a lap lost ("−5").
    penalty: int = 0
    total: int | None = None
    status: str = ""
    # Words beside a placed row that is not a plain finish: a mishap kept
    # the rider out of the final sprint and they are placed on points.
    note: str = ""
    tied: bool = False
    staged: bool = False
    actions: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Screen:
    """The scoring surface as plain data: the test asserts it, the widgets draw it."""

    race_id: int
    title: str
    group: str
    detail: str
    # The ruleset's one line about the format, blank unless the venue wrote one.
    description: str
    state_label: str
    task: Task
    noun: str
    # The field's size in words ("12 riders", "5 teams"): the scorer's
    # quick check that everyone is at the rail.
    field: str
    team: bool
    points: bool
    review: bool
    final: bool
    cards: tuple[Card, ...] = ()
    rows: tuple[ResultRow, ...] = ()
    sprint_columns: tuple[int, ...] = ()
    sprint_headers_open: bool = False
    # The recorded sprints whose column header reopens them for correction.
    open_sprints: tuple[int, ...] = ()
    current_sprint: int | None = None
    record: bool = False
    record_enabled: bool = False
    # Place the Rest Together, in Record Sprint's slot: a finish order
    # with someone placed and two or more still to place.
    rest_together: bool = False
    # The race's own menu, on the task line's ⋯: every item with why it
    # is closed, or None; a format with no menu has no strip.
    race_menu: tuple[tuple[str, str, str | None], ...] = ()
    # The items open now, (key, label).
    race_actions: tuple[tuple[str, str], ...] = ()
    mark_final: bool = False
    reopen: bool = False
    undo_text: str = NOTHING_TO_UNDO_LABEL
    undo_enabled: bool = False
    # The rider or team ``undo_text`` names, as the label spells it, so
    # the button can set the name apart from the verb and the action; ""
    # when the label names nobody ("Undo: Swap", "Nothing to Undo").
    undo_who: str = ""


def screen(race: LiveRace) -> Screen:
    # One read of the live log for the whole screen, passed down rather
    # than kept on the object: another window may write between screens.
    log = race.rows()
    live = race.actions(log)
    results = with_results(live)
    recorded = race.recorded_sprints(log)
    st = race._live_standings(log)
    task = race.task(st)
    label = race.state_label(st)
    final = race.race.state == "final"
    review = st.is_complete and not task.editing
    points = race.kind in ("points", "madison")
    rows = result_rows(race, st, task, live, results, recorded)
    cards = (
        _cards(race, st, task, live, results, {r.entrant_id: r for r in rows})
        if cards_shown(st, task)
        else ()
    )
    opening = points and not final and not task.editing
    open_sprints = tuple(sorted(recorded)) if opening else ()
    undo_text = race.undo_text(st)
    race_menu = tuple(race.race_menu(st, task))
    return Screen(
        race_id=race.race_id,
        title=rulesets.race_short_name(race.race),
        group=race.race.group_label,
        detail=race.detail(),
        description=description(race),
        state_label=label,
        task=task,
        noun=race.noun,
        field=field_text(race),
        team=race.roster.is_team,
        points=points,
        review=review,
        final=final,
        cards=tuple(cards),
        rows=tuple(rows),
        sprint_columns=tuple(race.sprint_columns(st, recorded)),
        sprint_headers_open=bool(open_sprints),
        open_sprints=open_sprints,
        current_sprint=_current_sprint(race, recorded),
        record=task.record,
        record_enabled=task.record_enabled,
        rest_together=race._rest_offered(st, task),
        race_menu=race_menu,
        race_actions=tuple((key, label) for key, label, why in race_menu if why is None),
        mark_final=review and race.race.state == "provisional",
        reopen=final,
        undo_text=undo_text,
        undo_enabled=race.can_undo(st),
        undo_who=undo_who(race, undo_text),
    )


def undo_who(race: LiveRace, text: str) -> str:
    """The rider or team an Undo label names, matched against this race's own labels.

    The label is free text on the stack ("Undo: #51 Hana Yoon placed 10th",
    "Undo: #19 Omar Rahimi gained a lap", "Undo: Blue placed 2nd"), and a
    name may hold any word, so the race's labels are tried, longest
    first, as a whole word of the text.
    """
    if not text.startswith(UNDO):
        return ""
    padded = f" {text[len(UNDO) :]} "
    labels = sorted((race.label(e) for e in race.roster.ids), key=len, reverse=True)
    return next((label for label in labels if label and f" {label} " in padded), "")


def field_text(race: LiveRace) -> str:
    """The field's size in words, as the board's start list counts it."""
    n = len(race.roster.entrants)
    return f"{n} {race.noun}" if n == 1 else f"{n} {race.noun}s"


def description(race: LiveRace) -> str:
    """The ruleset's line about the format, for the surface under the header."""
    return rulesets.race_format_description(race.race)


def _current_sprint(race: LiveRace, recorded: dict[int, Row]) -> int | None:
    if race.kind not in ("points", "madison"):
        return None
    return max(recorded, default=None)


def cards_shown(st: Standings, task: Task) -> bool:
    """Whether the surface shows cards: from the start list until the result completes.

    A reopened sprint shows them again, for the correction.
    """
    review = st.is_complete and not task.editing
    return not review and task.kind not in ("final", "none")


def result_rows(
    race: LiveRace,
    st: Standings,
    task: Task,
    live: Sequence[Action],
    results: set[int],
    recorded: dict[int, Row],
) -> list[ResultRow]:
    """The result table: sprint points by rider, or the places decided so far."""
    if race.kind in ("points", "madison"):
        return _points_rows(race, st, task, live, results, recorded)
    review = st.is_complete and not task.editing
    return _place_rows(race, st, task, review, live, results)


def live_ids(race: LiveRace, st: Standings, task: Task) -> list[int]:
    """The entrants a click does the task on now; every other card is done.

    Unsorted: the cards sort by bib.
    """
    if task.kind == "blocked":
        # Nothing scores until the field is fixed, so nobody is done yet.
        return list(race.roster.ids)
    if task.editing:
        # Exactly what the sprint scored, plus anyone it could place
        # now. A rider out of the finish rode every earlier sprint, so
        # a correction of one may place them; the finish itself may not.
        # A rider who did not finish, or withdrew, rode only the sprints
        # before it.
        field = race.edit_field()
        if race.correcting_finish_order():
            racing = set(race._active(st))
        else:
            racing = {
                r.entrant_id
                for r in st.rows
                if (
                    r.status is None
                    and (not r.withdrawn or race._racing_at_edit(r.entrant_id, Withdrawn.kind))
                )
                or (r.status == "DNF" and race._racing_at_edit(r.entrant_id, "DNF"))
            }
        return [r.entrant_id for r in st.rows if r.entrant_id in racing or r.entrant_id in field]
    if task.kind in ("sprint", "final_sprint"):
        return race._active(st)
    if task.kind == "order":
        placed = race._placed_ids(st)
        return [e for e in race._field_left(st) if e not in placed]
    return list(st.remaining_entrants)


def done_ids(race: LiveRace, st: Standings, task: Task) -> set[int]:
    """The entrants whose card is done now; none while no cards show."""
    if not cards_shown(st, task):
        return set()
    return set(race.roster.ids) - set(live_ids(race, st, task))


def done_rows(race: LiveRace, st: Standings, task: Task) -> dict[int, ResultRow | None]:
    """Each done entrant and their result row (None when they have no row), read afresh.

    For a single entrant's menu or refusal; the screen builds its cards
    from the rows it already has.
    """
    done = done_ids(race, st, task)
    if not done:
        return {}
    log = race.rows()
    live = race.actions(log)
    rows = result_rows(race, st, task, live, with_results(live), race.recorded_sprints(log))
    by_id = {r.entrant_id: r for r in rows}
    return {e: by_id.get(e) for e in done}


def done_mark(standing: Standing, row: ResultRow | None) -> tuple[str, bool, str]:
    """A done card's (text, is a status, tooltip).

    A status first, then a mishap, then a withdrawal, since each takes
    the rider out of the field whatever place they hold; otherwise the
    place as the result row numbers it, so the card and the table agree
    as the scorer moves rows.
    """
    if standing.status:
        code = standing.status
    elif standing.out_of_finish:
        code = "out_of_finish"
    elif standing.withdrawn:
        code = "withdrawn"
    else:
        return (row.place_text if row is not None else "", False, "")
    word, name = DONE_MARKS[code]
    return word, True, name


def done_actions(
    race: LiveRace,
    entrant_id: int,
    row: ResultRow | None,
    st: Standings,
    live: Sequence[Action] | None = None,
    task: Task | None = None,
    results: set[int] | None = None,
) -> tuple[tuple[str, str], ...]:
    """A done card's menu: its result row's, so the card and the row are two doors to one menu."""
    if row is not None:
        return row.actions
    return tuple(race.review_actions(entrant_id, st, actions=live, task=task, results=results))


def _cards(
    race: LiveRace,
    st: Standings,
    task: Task,
    live: Sequence[Action],
    results: set[int],
    rows: dict[int | None, ResultRow],
) -> list[Card]:
    """One card per entrant in the field, in bib order, live or done.

    The grid never reflows while the race runs: a click that places or
    puts out a rider turns the card done in its slot, and Undo turns it
    live again in the same slot.
    """
    groups = race.staged(st)
    live_set = set(live_ids(race, st, task))
    cards = []
    # In an ordinary sprint, the places the ruleset awards.
    awarded = None
    if task.kind == "sprint" and task.sprint_no is not None:
        count = race.sprint_count
        if count is None or task.sprint_no < count:
            awarded = race.scoring_places(task.sprint_no)
    for eid in sorted(race.roster.ids, key=race._sort_key):
        standing = st.by_entrant(eid)
        laps = standing.net_laps
        if eid not in live_set:
            row = rows.get(eid)
            text, status, tip = done_mark(standing, row)
            actions = done_actions(race, eid, row, st, live, task, results)
            # A shared place shows on the badge; a status chip is no place.
            tied = row is not None and row.tied and not status
            cards.append(
                Card(
                    eid,
                    race.entry(eid),
                    None,
                    actions,
                    laps,
                    tied,
                    done=True,
                    done_text=text,
                    done_status=status,
                    done_tip=tip,
                )
            )
            continue
        badge = race._staged_place(eid, groups) if task.stages else None
        actions = tuple(
            race.rider_actions(eid, st, actions=live, task=task, results=results, known_live=True)
        )
        tied = badge is not None and any(eid in g and len(g) > 1 for g in groups)
        past_awarded = badge is not None and awarded is not None and badge > awarded
        cards.append(Card(eid, race.entry(eid), badge, actions, laps, tied, past_awarded))
    return cards


def _place_rows(
    race: LiveRace,
    st: Standings,
    task: Task,
    review: bool,
    live: Sequence[Action],
    results: set[int],
) -> list[ResultRow]:
    """The places decided so far, in place order, then the riders with a status.

    The staged order fills the open places from the top: a chase from
    1st, an elimination's final sprint from 1st while the bell's
    places sit at the bottom, a win-and-out's rest after the lap
    winners. A place nobody has yet is not a row.

    Rows are ordered by place and appended, never written into a slot
    numbered from the place: a tie uses one place per rider (1, 1,
    3), from the line and from a win-and-out's bell alike, so slots
    numbered from the place would collide and a
    rider would drop out of the table.
    """
    # A rider an elimination placed after a DNF keeps the place, in
    # the ranked rows with the status on, not in the tail.
    statused = [r for r in st.rows if r.status and not r.placed]
    field = [r for r in st.rows if r.status is None or r.placed]
    ranked = [r for r in field if r.rank is not None]
    # (place, order, row): sorted by place, ties kept in table order.
    placed: list[tuple[int, int, ResultRow]] = []
    used: set[int] = set()
    for group in race._place_groups(ranked):
        rank = st.by_entrant(group[0]).rank or 1
        used.update(range(rank, rank + len(group)))
        for eid in group:
            row = ResultRow(
                place=0,
                entrant_id=eid,
                entry=race.entry(eid),
                place_text=str(rank),
                laps=st.by_entrant(eid).net_laps,
                status=st.by_entrant(eid).status or "",
                note=row_note(
                    False, st.by_entrant(eid).laps_not_counted, st.by_entrant(eid).withdrawn
                ),
                tied=len(group) > 1,
                actions=tuple(
                    race.review_actions(eid, st, actions=live, task=task, results=results)
                ),
            )
            placed.append((rank, len(placed), row))
    if task.stages and not task.editing:
        # A staged group takes the first open place and one open place
        # per rider, as the finish order will when it is recorded.
        open_places = (p for p in count(1) if p not in used)
        groups = race.staged(st)
        first = None
        for i, group in enumerate(groups):
            rank = next(open_places)
            first = rank if first is None else first
            for _ in range(len(group) - 1):
                next(open_places)
            for eid in group:
                # A staged row moves as a result row does (move_staged):
                # the finish order is still being built, so the moves
                # stay among the places clicked from the front.
                actions = race._moves(groups, i)
                actions += race._long_moves(groups, i, eid, first - 1)
                if i > 0 and eid == group[0]:
                    actions.append(("tie_above", REVIEW_ACTIONS["tie_above"]))
                if eid == group[-1] and i + 1 < len(groups):
                    actions.append(("tie_below", REVIEW_ACTIONS["tie_below"]))
                actions += _staged_row_own(race, eid, st, live, task)
                row = ResultRow(
                    place=0,
                    entrant_id=eid,
                    entry=race.entry(eid),
                    place_text=str(rank),
                    laps=st.by_entrant(eid).net_laps,
                    tied=len(group) > 1,
                    staged=True,
                    actions=tuple(actions),
                )
                placed.append((rank, len(placed), row))
        # The back of the order counts down from the last place the
        # field left would fill, so a DNF after a mark closes it up.
        back = len(race._field_left(st))
        tail = race.staged_tail(st)
        for j, group in enumerate(tail):
            rank = back - len(group) + 1
            back -= len(group)
            for eid in group:
                # Last place first in the tail, so its moves are read
                # from the front, where up is a better place.
                actions = race._moves(list(reversed(tail)), len(tail) - 1 - j)
                actions += _staged_row_own(race, eid, st, live, task)
                row = ResultRow(
                    place=0,
                    entrant_id=eid,
                    entry=race.entry(eid),
                    place_text=str(rank),
                    laps=st.by_entrant(eid).net_laps,
                    tied=len(group) > 1,
                    staged=True,
                    actions=tuple(actions),
                )
                placed.append((rank, len(placed), row))
    placed.sort(key=lambda item: item[:2])
    rows = [replace(row, place=n) for n, (_, _, row) in enumerate(placed, start=1)]
    for r in statused:
        rows.append(
            ResultRow(
                place=len(rows) + 1,
                entrant_id=r.entrant_id,
                entry=race.entry(r.entrant_id),
                place_text=r.status or "",
                laps=r.net_laps,
                status=r.status or "",
                actions=(
                    tuple(race.review_actions(r.entrant_id, st, actions=live, results=results))
                    if review
                    else ()
                ),
            )
        )
    return rows


def _staged_row_own(
    race: LiveRace, entrant_id: int, st: Standings, live: Sequence[Action], task: Task
) -> list[tuple[str, str]]:
    """A staged row's own actions after its moves: a lap, a ruling, Disqualify.

    The click that placed the rider turned their card done, and the done
    card offers this row's menu, so the two act on the rider alike before
    the order is recorded.
    """
    if race._staged.editing:
        return []
    own = race._rider_keys(entrant_id, st, live, task, placed=True)
    return [(k, RIDER_ACTIONS[k]) for k in own]


def _points_rows(
    race: LiveRace,
    st: Standings,
    task: Task,
    live: Sequence[Action],
    results: set[int],
    recorded: dict[int, Row],
) -> list[ResultRow]:
    columns = race.sprint_columns(st, recorded)
    run = set(recorded)
    rows = []
    ordered = sorted(st.rows, key=lambda r: (r.status is not None, r.rank or 0))
    for i, r in enumerate(ordered, start=1):
        sprints = tuple(
            (r.sprint_points[n - 1] if n - 1 < len(r.sprint_points) else 0) if n in run else None
            for n in columns
        )
        actions = tuple(
            race.review_actions(r.entrant_id, st, actions=live, task=task, results=results)
        )
        rows.append(
            ResultRow(
                place=i,
                entrant_id=r.entrant_id,
                entry=race.entry(r.entrant_id),
                # No rank before the first sprint: a number would read
                # as a result.
                place_text=r.status or (str(r.rank) if r.rank is not None else ""),
                sprints=sprints,
                laps=r.net_laps,
                lap_points=int(r.lap_points),
                penalty=int(r.adjust_points),
                total=int(r.total_points),
                status=r.status or "",
                note=row_note(r.out_of_finish, r.laps_not_counted, r.withdrawn),
                tied=r.tied,
                actions=actions,
            )
        )
    return rows
