"""Standings to scoreboard payloads.

Pure functions over a ``RaceView``: no store, no widgets, so every
layout's content is testable as plain data. The same payloads drive the
board and its preview; the scorer's result table draws from
``LiveRace.screen()`` instead and is not fed from here.

A rider with a status (DNF, DNS, DQ, DNP) is absent from every running
layout, without comment: a DNF may be an injury and a DQ a protest still
being argued, and neither is the TV's to announce. An Elimination DNF
keeps the place USAC 2E4 gives, so the result page lists it there with
nothing beside the name. The result table and the printed sheet keep the
row with its code.
"""

from madtracker.board import payloads as P
from madtracker.control.describe import OUT_OF_FINISH, STATUS_WORDS, WITHDRAWN
from madtracker.control.race import RaceView, starts_race
from madtracker.control.roster import Entrant
from madtracker.export.summary import rules_in_force, sprints_run
from madtracker.scoring._common import place_map
from madtracker.scoring.actions import FinishOrder, SprintResult
from madtracker.scoring.result import Standing
from madtracker.scoring.rules import SprintPointsRules, _Rules
from madtracker.scoring.sprint_points import award

# The board labels a result Provisional or Final and nothing more (design section 10).
STATE_STATUS = {"provisional": "Provisional", "final": "Final"}


def entry(e: Entrant) -> P.Entry:
    color = e.color_hex or (e.color.lower() if e.color else None)
    return P.Entry(
        bibs=[str(b) for b in e.bibs],
        names=list(e.names),
        team=e.team,
        color=color if e.is_team else None,
    )


def _entry_for(view: RaceView, entrant_id: int) -> P.Entry:
    e = view.roster.get(entrant_id)
    if e is None:
        return P.Entry(bibs=[], names=[f"#{entrant_id}"])
    return entry(e)


def rules_detail(view: RaceView) -> str:
    """The line under the race title: the format, so the stands know the kind of race.

    Blank when the title is the format already (an unnamed race): the
    line would only say it twice.
    """
    return "" if view.title == view.format_name else view.format_name


def _rules(view: RaceView) -> _Rules:
    """The race's rules with the sprint count in force: a shortened race
    (USAC 1G4(b)) is shown on the count it rides to."""
    return rules_in_force(view.rules, view.standings)


def _sprints_run(view: RaceView) -> tuple[frozenset[int], int | None]:
    """Sprint numbers already scored, and the number the finish order scores as."""
    return sprints_run(_rules(view), view.actions)


def _out_order(view: RaceView) -> list[int]:
    """Riders the bell put out, first out first.

    A DNF is out at that moment and keeps that place in the result (USAC
    2E4), but it is not an elimination the stands should see: a rider who
    leaves a race for any reason leaves the board, since a DNF may be an
    injury. So a rider with a status is left out here even when placed,
    and a DQ, DNS or DNP has no place anyway.
    """
    rows = [
        r
        for r in view.standings.rows
        if r.eliminated_at is not None and r.placed and r.status is None
    ]
    rows.sort(key=lambda r: r.eliminated_at)
    return [r.entrant_id for r in rows]


def _start_list(view: RaceView) -> bool:
    """Whether the race has not started: setup, with no entry that starts it.

    The same test the controller settles its state by (``starts_race``):
    a DNS is a pre-race call, so the TV keeps the start list.
    """
    return view.state == "setup" and not any(starts_race(e) for e in view.actions)


def header(view: RaceView) -> P.Header:
    st = view.standings
    status = STATE_STATUS.get(view.state, "")
    if not status:
        if _start_list(view):
            status = "Start list"
        elif view.engine == "elimination":
            # No "N of M out" count: the out-earlier list already says it,
            # and a DNF or DQ leaves the field without changing the count.
            survivors = getattr(view.rules, "survivors", 2)
            if not st.is_complete and 0 < len(st.remaining_entrants) <= survivors:
                status = "Final sprint"
            else:
                status = "Racing"
        elif view.engine == "sprint_points":
            run, _ = _sprints_run(view)
            count = getattr(_rules(view), "sprint_count", None)
            if run:
                status = f"After Sprint {max(run)}" + (f" of {count}" if count else "")
            else:
                status = "Racing"
        elif view.engine == "win_and_out":
            laps = st.next_sprint_no - 1
            places = getattr(view.rules, "places", 0)
            status = f"{laps} of {places} places decided" if laps else "Racing"
        else:
            status = "Racing"
    return P.Header(
        title=view.title,
        group=view.group,
        detail=rules_detail(view),
        status=status,
        race_id=view.race_id,
    )


def _statused(view: RaceView) -> set[int]:
    return {r.entrant_id for r in view.standings.rows if r.status}


def pre_race(view: RaceView) -> P.PreRace:
    # A DNS before the start leaves the start list on the TV in silence.
    gone = _statused(view)
    shown = [e for e in view.roster.entrants if e.entrant_id not in gone]
    # A lap taken before the finish shows on the start list, the page the
    # stands see until the result is in.
    net = {r.entrant_id: r.net_laps for r in view.standings.rows}
    laps = [net.get(e.entrant_id, 0) for e in shown]
    return P.PreRace(
        header=header(view),
        roster=[entry(e) for e in shown],
        laps=laps if any(laps) else [],
    )


def elimination(view: RaceView) -> P.Elimination:
    out = _out_order(view)
    remaining = [_entry_for(view, eid) for eid in view.standings.remaining_entrants]
    last = _entry_for(view, out[-1]) if out else None
    return P.Elimination(
        header=header(view),
        remaining=remaining,
        last_eliminated=last,
        eliminated=[_entry_for(view, eid) for eid in out[:-1]],
    )


def _rank(row: Standing, index: int) -> int:
    # Before the first sprint nobody has a rank; the board lists them in
    # start-list order and numbers the lines rather than printing "None".
    return row.rank if row.rank is not None else index + 1


def standings(view: RaceView, *, overlay: bool = False) -> P.Standings:
    """The points and madison table in the house sheet's column order.

    ``overlay`` adds the sprint-result card for the entry just made, if
    it was a sprint.
    """
    st = view.standings
    run, final_no = _sprints_run(view)
    count = getattr(_rules(view), "sprint_count", None)
    columns = max([count or 0, max(run, default=0)] + [len(r.sprint_points) for r in st.rows])
    if st.ended:
        # Results stand on the sprints ridden (USAC 2M6, 2N5): no empty columns for the rest.
        columns = max(run, default=0)
    rows = []
    for i, r in enumerate(st.rows):
        if r.status:
            continue
        sprints: list[int | None] = []
        for j in range(columns):
            if j + 1 in run:
                sprints.append(r.sprint_points[j] if j < len(r.sprint_points) else 0)
            else:
                sprints.append(None)
        rows.append(
            P.StandingRow(
                rank=_rank(r, i),
                entry=_entry_for(view, r.entrant_id),
                sprints=sprints,
                laps=r.net_laps,
                lap_points=int(r.lap_points),
                penalty=int(r.adjust_points),
                total=int(r.total_points),
                status=r.status or "",
            )
        )
    result = sprint_result(view, final_no) if overlay else None
    return P.Standings(
        header=header(view),
        sprint_count=columns,
        rows=rows,
        current_sprint=max(run) if run else None,
        sprint_result=result,
    )


def sprint_result(view: RaceView, final_no: int | None = None) -> P.SprintResult | None:
    """The card for the newest scoring entry, when that entry was a sprint."""
    rules = _rules(view)
    if not isinstance(rules, SprintPointsRules) or not view.actions:
        return None
    last = view.actions[-1]
    if isinstance(last, SprintResult):
        number, places = last.sprint_no, last.places
        table = rules.points_for_sprint(number)
        of = rules.sprint_count
    elif isinstance(last, FinishOrder) and final_no is not None:
        number, places = final_no, last.places
        count = rules.sprint_count
        table = rules.final_points if count is None else rules.points_for_sprint(number)
        # The finish order is the last sprint even when the race ran with
        # sprints as called, so the count is known from here on.
        of = number
    else:
        return None
    points = award(places, table)
    where = place_map(places)
    placings = [
        (where[eid], _entry_for(view, eid), pts)
        for eid, pts in sorted(points.items(), key=lambda kv: where[kv[0]])
        if pts > 0
    ]
    return P.SprintResult(number=number, placings=placings, of=of)


def finish(view: RaceView) -> P.Finish:
    """The result recap: the placed rows, with a word for a placed status."""
    placings = []
    for row in view.standings.rows:
        if row.status and not row.placed:
            continue
        note = row.status or ""
        if row.placed and row.status:
            # An elimination places a rider who left the race (USAC 2E4);
            # a place with DNF beside it would read as a slip, so the
            # note says what happened in words.
            note = STATUS_WORDS.get(row.status, row.status)
        elif row.out_of_finish:
            # Placed on points without a final-sprint place (USAC 2M8(a)).
            note = OUT_OF_FINISH
        elif row.withdrawn:
            # Placed by the moment of the withdrawal (USAC 2O3(e), 1M6(d)).
            note = WITHDRAWN
        if row.rank is None:
            continue
        who = _entry_for(view, row.entrant_id)
        placings.append(P.Placing(row.rank, who, note, row.net_laps))
    return P.Finish(header=header(view), placings=placings)


def between(
    event_name: str,
    next_view: RaceView | None,
    last_view: RaceView | None,
    position: str = "",
    last_count: int = 6,
) -> P.Between:
    """Next race up and the last result, for the gap between races."""
    nxt_title = next_view.title if next_view else "Results"
    last = finish(last_view).placings[:last_count] if last_view else []
    return P.Between(
        header=P.Header(title=event_name, status=position),
        next_title=nxt_title,
        next_group=next_view.group if next_view else "",
        next_detail=rules_detail(next_view) if next_view else "",
        next_roster=[entry(e) for e in next_view.roster.entrants] if next_view else [],
        last_title=last_view.title if last_view else "",
        last_group=last_view.group if last_view else "",
        last_placings=last,
    )


def _points_scored(view: RaceView) -> bool:
    """Whether a points race or madison has a sprint, a lap or a result in yet."""
    run, _final = _sprints_run(view)
    st = view.standings
    return bool(run) or st.is_complete or any(r.net_laps or r.lap_points for r in st.rows)


def board_for(view: RaceView, *, overlay: bool = False) -> tuple[str, object]:
    """(layout name, payload) the scoreboard shows for the race as it stands."""
    if _start_list(view):
        return "pre_race", pre_race(view)
    if view.engine == "elimination":
        if view.standings.is_complete:
            return "finish", finish(view)
        return "elimination", elimination(view)
    if view.engine == "sprint_points":
        if not _points_scored(view):
            # A table of zeros ranked 1 to 10 in start order would read as a
            # result; until a sprint or a lap counts, the start list stays.
            return "pre_race", pre_race(view)
        name = "madison" if view.roster.is_team else "sprint_points"
        return name, standings(view, overlay=overlay)
    if view.standings.is_complete or (view.engine == "win_and_out" and view.standings.ranked()):
        # A win-and-out's places fill in during the race, so the recap is
        # the live layout: each lap winner appears as their place is decided.
        return "finish", finish(view)
    return "pre_race", pre_race(view)
