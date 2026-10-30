"""An independent multi-race standings, computed from the store and the race logs.

Written from docs/scoring-rules.md (R-TEAM-1 to R-TEAM-5, R-RIDER-1 to
R-RIDER-4, R-OMNI-1 to R-OMNI-5), docs/design.md section 8a, and the
help page madtracker/help/multi-race-standings.md. It never imports
madtracker.control.multi_race. A race's own result (ranks, totals,
statuses, final sprint place, eliminated_at) is taken from the scoring
engine through LiveRace, which the brief allows; everything over the
races is this file's own code:

- which races are candidates for a kind, which are left out, which are
  not yet raced, which are still racing, and the Four-Race refusal;
- who rode (from the log's last status), rider identity by rider id and
  team identity by its pair of riders;
- the team minimum, the place tables, the 40-38-36 table with 1 from
  21st, the Points Race carried raw, DNF out, the omnium penalty;
- the USAC 2B19(e) countback and the Four-Race final sprint tie-break,
  shared ranks, and the DNF-then-DQ tail;
- the Final state and the count line.

``oracle(store, standings_id) -> OTable``.
"""

import re
from dataclasses import dataclass, field
from functools import cmp_to_key

from madtracker.control.race import LiveRace, starts_race
from madtracker.scoring.actions import Status
from madtracker.store import Store

TOTALS = "team_omnium"
PLACES = "team_omnium_places"
OMNIUM = "omnium_places"
FOUR_RACE = "four_race_omnium"
TEAM_KINDS = (TOTALS, PLACES)

DEFAULT_TABLE = (7, 5, 3, 2, 1)  # USAC16 2O1, the help page's default
# USAC 2O3(a): 40, 38, ... 2 for places 1 to 20, then 1 (R-OMNI-1).
FOUR_TABLE = tuple(40 - 2 * i for i in range(20))
FOUR_ORDER = ("chase", "tempo", "elimination", "points")  # USAC 2O1, ridden order
NOT_RODE = ("DNS", "DNP")


@dataclass
class ORow:
    key: object  # rider id, or tuple of the pair's names (a team)
    rank: int | None
    status: str  # "" or DNF / DQ
    per_race: list
    total: int | float
    penalty: int = 0
    bib: int | None = None
    name: str = ""
    color: str | None = None
    riders: tuple = ()


@dataclass
class OGroup:
    label: str
    race_ids: list[int]
    rows: list[ORow]


@dataclass
class OTable:
    kind: str
    refused: bool
    state: str
    counted: str
    groups: list[OGroup]
    left_out: list[int]
    not_yet_raced: list[int]
    racing: list[int]
    events: list[int]
    notes: list[str] = field(default_factory=list)


def gkey(label: str | None) -> str:
    """A label typed two ways is one group: no spaces, case folded (design 8a)."""
    return re.sub(r"\s+", "", label or "").casefold()


def counts(kind: str, fmt: str) -> bool:
    """R-RIDER-3, R-RIDER-4: the Madisons for the team kinds, the rest (or the four) for riders."""
    if kind in TEAM_KINDS:
        return fmt == "madison"
    if kind == FOUR_RACE:
        return fmt in FOUR_ORDER
    return fmt != "madison"


def race_state(store: Store, live: LiveRace, notes: list[str] | None = None) -> str:
    """Setup with nothing scored, running, provisional once complete, final when marked so.

    A complete result counts even when the log holds only DNS marks: a
    one-rider race is a race, the rider left takes 1st and scores the
    place. ``notes`` is kept for the call shape.
    """
    actions = live.actions()
    if actions and live.standings().is_complete:
        return "final" if store.race(live.race_id).state == "final" else "provisional"
    if not any(starts_race(a) for a in actions):
        return "setup"
    return "running"


def last_status(live: LiveRace, entrant_id: int) -> str | None:
    """The entrant's status from the log: a later status replaces an earlier one."""
    out = None
    for a in live.actions():
        if isinstance(a, Status) and a.entrant_id == entrant_id:
            out = a.status
    return out


def rode(live: LiveRace, entrant_id: int) -> bool:
    """A DNF or DQ rode; a DNS or DNP did not (R-TEAM-4, R-RIDER-2)."""
    return last_status(live, entrant_id) not in NOT_RODE


def placed(row) -> bool:
    """A place the sheet prints as a number: a rank, and no status unless the
    Elimination put the rider out at that moment (R-RIDER-2, R-ELIM-7)."""
    return row.rank is not None and (row.status is None or row.eliminated_at is not None)


def table_points(table, beyond: int, row) -> int:
    if not placed(row):
        return 0
    return table[row.rank - 1] if row.rank <= len(table) else beyond


def everyone_placed(live: LiveRace) -> bool:
    return all(r.rank is not None for r in live.standings().rows if r.status is None)


# ----- ranking ------------------------------------------------------------


def _rank_sorted(keys, cmp) -> dict:
    """Competition ranks, 1, 1, 3, over keys ordered by ``cmp``; equal keys share."""
    ordered = sorted(keys, key=cmp_to_key(cmp))
    ranks = {}
    rank = 1
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and cmp(ordered[i], ordered[j + 1]) == 0:
            j += 1
        for k in ordered[i : j + 1]:
            ranks[k] = rank
        rank += j - i + 1
        i = j + 1
    return ranks


def countback_cmp(totals, places, n_cols):
    """USAC 2B19(e): higher total; most firsts, then seconds, ...; then the better
    place in the last race where either placed (R-TEAM-3)."""
    max_place = max((p for ps in places.values() for p in ps if p is not None), default=0)

    def cmp(a, b):
        if totals[a] != totals[b]:
            return -1 if totals[a] > totals[b] else 1
        for p in range(1, max_place + 1):
            ca = sum(1 for x in places[a] if x == p)
            cb = sum(1 for x in places[b] if x == p)
            if ca != cb:
                return -1 if ca > cb else 1
        for i in reversed(range(n_cols)):
            pa, pb = places[a][i], places[b][i]
            if pa is None and pb is None:
                continue
            if pa is None:
                return 1
            if pb is None:
                return -1
            if pa != pb:
                return -1 if pa < pb else 1
            return 0
        return 0

    return cmp


def final_sprint_cmp(totals, finals):
    """USAC 2O3(g): a tie on the total goes to the final sprint of the Points Race (R-OMNI-3)."""

    def cmp(a, b):
        if totals[a] != totals[b]:
            return -1 if totals[a] > totals[b] else 1
        fa, fb = finals[a], finals[b]
        if fa == fb:
            return 0
        if fa is None:
            return 1
        if fb is None:
            return -1
        return -1 if fa < fb else 1

    return cmp


# ----- the tables ---------------------------------------------------------


def _team_table(store, kind, table, label, cols, lives) -> OGroup:
    teams: dict = {}  # key -> dict(name, color, riders, cells: {race_id: (row, rode)})
    for c in cols:
        live = lives[c["race_id"]]
        st = live.standings()
        for t in store.teams(c["race_id"]):
            key = frozenset(t.members) if t.members else ("team", t.team_id)
            rec = teams.setdefault(key, {"cells": {}, "name": "", "color": None, "riders": ()})
            ent = live.roster.get(t.team_id)
            if ent is not None:
                rec["name"] = ent.team or ent.short
                rec["color"] = ent.color_hex or (ent.color.lower() if ent.color else None)
                rec["riders"] = tuple(ent.names)
            try:
                row = st.by_entrant(t.team_id)
            except KeyError:
                row = None
            rec["cells"][c["race_id"]] = (row, row is not None and rode(live, t.team_id))
    # R-TEAM-4: a team that rode fewer than every counting Madison is left out.
    kept = {
        key: rec
        for key, rec in teams.items()
        if all(rec["cells"].get(c["race_id"], (None, False))[1] for c in cols)
    }
    per_race, totals, places = {}, {}, {}
    for key, rec in kept.items():
        cells, pl = [], []
        for c in cols:
            row, _ = rec["cells"][c["race_id"]]
            if kind == TOTALS:
                # R-TEAM-1, R-TEAM-2: the Madison total as printed, a DNF
                # keeping its points; a team with another status and no
                # place scores nothing there.
                if row.status is None or row.status == "DNF" or placed(row):
                    pts = row.total_points
                else:
                    pts = 0
            else:
                pts = table_points(table, 0, row)  # R-TEAM-5: past the table scores 0
            cells.append(pts)
            pl.append(row.rank if placed(row) else None)
        per_race[key] = cells
        totals[key] = sum(cells)
        places[key] = pl
    ranks = _rank_sorted(list(kept), countback_cmp(totals, places, len(cols)))
    rows = [
        ORow(
            key=tuple(sorted(rec["riders"])) or ("team", rec["name"]),
            rank=ranks[key],
            status="",
            per_race=per_race[key],
            total=totals[key],
            name=rec["name"],
            color=rec["color"],
            riders=rec["riders"],
        )
        for key, rec in kept.items()
    ]
    rows.sort(key=lambda r: (r.rank, r.key))
    return OGroup(label, [c["race_id"] for c in cols], rows)


def _rider_table(store, kind, table, label, cols, lives, penalties) -> OGroup:
    riders: dict = {}  # rider_id -> dict(name, bib, cells)
    for c in cols:
        live = lives[c["race_id"]]
        st = live.standings()
        for rid in live.roster.ids:
            ent = live.roster.get(rid)
            rec = riders.setdefault(rid, {"cells": {}, "name": "", "bib": None})
            rec["name"] = ent.names[0] if ent.names else ent.short
            rec["bib"] = ent.bibs[0] if ent.bibs else None
            try:
                row = st.by_entrant(rid)
            except KeyError:
                row = None
            rec["cells"][c["race_id"]] = (row, row is not None and rode(live, rid))
    # R-RIDER-2: everyone who rode any counting race is in, no minimum.
    # R-OMNI-4: the Four-Race Omnium keeps everyone on any field, so a
    # rider who started none of its races is listed DNF (USAC 2O2(c)).
    if kind == FOUR_RACE:
        kept = dict(riders)
    else:
        kept = {rid: rec for rid, rec in riders.items() if any(v[1] for v in rec["cells"].values())}
    per_race, totals, places, finals, out = {}, {}, {}, {}, {}
    for rid, rec in kept.items():
        cells, pl = [], []
        mark = None
        for c in cols:
            row, did = rec["cells"].get(c["race_id"], (None, False))
            if kind == FOUR_RACE:
                # R-OMNI-4: out of the omnium on any race not started or
                # not finished (any status, or not entered at all).
                if row is None or row.status is not None:
                    mark = (
                        "DQ" if (row is not None and row.status == "DQ") or mark == "DQ" else "DNF"
                    )
                if row is None or not did:
                    cells.append(None)
                elif c["format"] == "points":
                    cells.append(row.total_points)  # R-OMNI-2: carried raw
                else:
                    cells.append(table_points(FOUR_TABLE, 1, row))  # R-OMNI-1
            else:
                cells.append(None if (row is None or not did) else table_points(table, 0, row))
            pl.append(row.rank if (row is not None and placed(row)) else None)
        per_race[rid] = cells
        pen = int(penalties.get(rid, 0)) if kind == FOUR_RACE else 0
        totals[rid] = sum(v for v in cells if v is not None) - pen
        places[rid] = pl
        out[rid] = mark
        # R-OMNI-3: the final sprint that decides is the last Points Race's
        # in the standings, which is the last column only when no later
        # Points Race was left out (R-OMNI-8).
        deciders = [c for c in cols if c["format"] == "points"] if kind == FOUR_RACE else cols
        last = rec["cells"].get(deciders[-1]["race_id"], (None, False))[0] if deciders else None
        finals[rid] = last.final_sprint_place if last is not None else None
    ranked_ids = [rid for rid in kept if out[rid] is None]
    if kind == FOUR_RACE and any(c["format"] == "points" for c in cols):
        cmp = final_sprint_cmp(totals, finals)
    elif kind == FOUR_RACE:
        # R-OMNI-8: no Points Race, no final sprint; a tie shares (1M6(a)).
        cmp = final_sprint_cmp(totals, dict.fromkeys(finals))
    else:
        cmp = countback_cmp(totals, places, len(cols))
    ranks = _rank_sorted(ranked_ids, cmp)
    rows = []
    for rid, rec in kept.items():
        rows.append(
            ORow(
                key=rid,
                rank=ranks.get(rid),
                status=out[rid] or "",
                per_race=per_race[rid],
                total=totals[rid],
                penalty=int(penalties.get(rid, 0)) if kind == FOUR_RACE else 0,
                bib=rec["bib"],
                name=rec["name"],
            )
        )
    # Ranked rows by rank, then the DNF group, then DQ (R-NF-2).
    rows.sort(key=lambda r: (r.rank is None, r.rank or 0, r.status == "DQ", r.key))
    return OGroup(label, [c["race_id"] for c in cols], rows)


# ----- the whole ----------------------------------------------------------


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def counted_words(kind, counting, left_out, waiting, n_events) -> str:
    word = "Madison" if kind in TEAM_KINDS else "race"
    if counting:
        raced = len(counting)
        total = raced + len(waiting)
        head = f"{raced} of {_plural(total, word)}" if total > raced else _plural(raced, word)
        return f"{head} raced over {_plural(n_events, 'event')}"
    if left_out and not waiting:
        return f"every {word} left out"
    return f"no {word}s raced yet"


def four_race_refused(ticked, left_out, event_ids) -> bool:
    """R-RIDER-4: each ticked event, and each group in it, has one of each of the four.

    R-OMNI-8 (USAC 2O4): a group's Points Race may be left out, so an
    unticked Points Race makes a three-race group; a group with no Points
    Race at all is still refused."""
    for event_id in event_ids:
        mine = [c for c in ticked if c["event_id"] == event_id]
        if not mine:
            return True
        groups: dict = {}
        for c in mine:
            groups.setdefault(gkey(c["group"]), []).append(c["format"])
        spare = {
            gkey(c["group"])
            for c in left_out
            if c["event_id"] == event_id and c["format"] == "points"
        }
        for group, formats in groups.items():
            want = list(FOUR_ORDER)
            if group in spare and "points" not in formats:
                want.remove("points")
            if sorted(formats) != sorted(want):
                return True
    return False


def oracle(store: Store, standings_id: int) -> OTable:
    sd = store.get_standings(standings_id)
    kind = sd.kind
    table = None
    if kind in (PLACES, OMNIUM):
        table = tuple(sd.rules.get("points_by_place") or DEFAULT_TABLE)
    # The ticked events, oldest first, as the store gives them.
    event_ids = list(sd.event_ids)
    excluded = set(sd.excluded_race_ids)
    cols, lives = [], {}
    notes: list[str] = []
    for event_id in event_ids:
        for race in store.races(event_id):
            if not counts(kind, race.format):
                continue
            live = LiveRace(store, race.race_id)
            lives[race.race_id] = live
            cols.append(
                {
                    "race_id": race.race_id,
                    "event_id": event_id,
                    "format": race.format,
                    "group": race.group_label,
                    "state": race_state(store, live, notes),
                    "excluded": race.race_id in excluded,
                }
            )
    for c in cols:
        live = lives[c["race_id"]]
        for row in live.standings().rows:
            if (last_status(live, row.entrant_id) or None) != row.status and not (
                row.status == "DNF" and last_status(live, row.entrant_id) is None
            ):
                notes.append(
                    f"race {c['race_id']} entrant {row.entrant_id}: log status "
                    f"{last_status(live, row.entrant_id)} vs engine {row.status}"
                )
    left_out = [c for c in cols if c["excluded"]]
    ticked = [c for c in cols if not c["excluded"]]
    not_yet = [c for c in ticked if c["state"] == "setup"]
    racing = []
    if kind != TOTALS:
        # A place kind waits for a running race until it has placed
        # everyone still in; the totals kind sums a running Madison.
        racing = [
            c
            for c in ticked
            if c["state"] == "running" and not everyone_placed(lives[c["race_id"]])
        ]
    counting = [c for c in ticked if c["state"] != "setup" and c not in racing]
    refused = False
    if kind == FOUR_RACE:
        refused = four_race_refused(ticked, left_out, event_ids)
        counting.sort(key=lambda c: (event_ids.index(c["event_id"]), FOUR_ORDER.index(c["format"])))
    by_group: dict = {}
    for c in counting:
        by_group.setdefault(gkey(c["group"]), []).append(c)
    groups = []
    if not refused:
        for cs in by_group.values():
            label = cs[0]["group"]
            if kind in TEAM_KINDS:
                groups.append(_team_table(store, kind, table, label, cs, lives))
            else:
                pen = sd.penalties if kind == FOUR_RACE else {}
                groups.append(_rider_table(store, kind, table, label, cs, lives, pen))
    final = (
        bool(counting)
        and not refused
        and not not_yet
        and not racing
        and all(c["state"] == "final" for c in counting)
    )
    return OTable(
        kind=kind,
        refused=refused,
        state="final" if final else "provisional",
        counted=counted_words(kind, counting, left_out, not_yet + racing, len(event_ids)),
        groups=groups,
        left_out=[c["race_id"] for c in left_out],
        not_yet_raced=[c["race_id"] for c in not_yet],
        racing=[c["race_id"] for c in racing],
        events=event_ids,
        notes=notes,
    )
