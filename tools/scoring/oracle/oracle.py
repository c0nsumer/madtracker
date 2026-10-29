"""An independent second scorer for MadTracker's formats.

Written from docs/scoring-rules.md (the rule register), the research notes
in docs/research/, and the USA Cycling Rulebook 8-25 text, without reading
the engine modules (placings, elimination, sprint_points, win_and_out,
aggregate, _common, replay). Lists, dicts, and Counters only.

Every function returns a plain dict per entrant:

    {entrant_id: {"rank": int|None, "status": str|None, "total": number,
                  "gained": int, "lost": int, "adjust": int,
                  "not_counted": int, "out_of_finish": bool,
                  "withdrawn": bool, "final_place": int|None,
                  "eliminated_at": int|None}}

plus an ordered list of rank groups (lists of entrant ids), finishers
first, then the withdrawn one to a group, the latest withdrawn first
(R-NF-3, R-OMNI-5), then the DNF group, then DNP, DQ, DNS (R-NF-2,
"Where the program decides"). The comparison reads both.

Where the register is ambiguous the choice is written down beside the code
with "AMBIGUITY:" so the report can list it.
"""

from collections import Counter

from madtracker.scoring.actions import (
    Eliminated,
    FinishOrder,
    LapGained,
    LapLost,
    LapNotCounted,
    OutOfFinish,
    PointsAdjusted,
    SprintResult,
    Status,
    Withdrawn,
)

# The order the unranked statuses are listed in after the DNF group
# (register, "Where the program decides", R-NF-2).
UNRANKED_ORDER = ("DNP", "DQ", "DNS")


# ---------------------------------------------------------------- helpers


def row(entrant_id):
    return {
        "entrant": entrant_id,
        "rank": None,
        "status": None,
        "total": 0,
        "gained": 0,
        "lost": 0,
        "adjust": 0,
        "not_counted": 0,
        "out_of_finish": False,
        "withdrawn": False,
        "final_place": None,
        "eliminated_at": None,
    }


def last_status(actions):
    """The last status mark per entrant. AMBIGUITY: the register never
    says a second mark replaces the first; R-ELIM-8 says a mark on a rider
    already out "changes only the mark", so the newest one is taken."""
    status = {}
    for a in actions:
        if isinstance(a, Status):
            status[a.entrant_id] = a.status
    return status


def lap_counts(actions):
    """Laps gained and lost per entrant, and how many gains the officials
    struck (R-LAP-4: a Lap Not Counted cancels one lap gained and its
    points; a Lap Lost is a second event and leaves both laps)."""
    gained = Counter()
    lost = Counter()
    struck = Counter()
    for a in actions:
        if isinstance(a, LapGained):
            gained.update(a.entrant_ids)
        elif isinstance(a, LapLost):
            lost.update(a.entrant_ids)
        elif isinstance(a, LapNotCounted):
            struck.update(a.entrant_ids)
    return gained, lost, struck


def finish_of(actions):
    found = None
    for a in actions:
        if isinstance(a, FinishOrder):
            found = a
    return found


def line_positions(places):
    """Place number per entrant across a line. A dead heat shares the
    place and the next place is skipped (R-TIE-1, USAC 1M6(a), 2M2(f)(i)).
    An empty group is not expected in a log (actions.py says keep it out)
    and is treated as taking no place."""
    pos = {}
    slot = 1
    for group in places:
        for e in group:
            pos[e] = slot
        slot += len(group)
    return pos


def competition_ranks(groups, start=1):
    """1, 2, 2, 4 over ordered groups; returns the ranks and the next free rank."""
    ranks = {}
    rank = start
    for group in groups:
        if not group:
            continue
        for e in group:
            ranks[e] = rank
        rank += len(group)
    return ranks, rank


def group_by_key(items, key):
    """Consecutive items with an equal key become one group, sorted by key."""
    groups = []
    for item in sorted(items, key=key):
        if groups and key(groups[-1][0]) == key(item):
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


def withdrawn_order(actions):
    """Entrants withdrawn, in the order the entries were made. The log's
    order is the riders' relative positions when withdrawn (R-NF-3); a
    second withdrawal of the same rider is refused, so the first stands."""
    order = []
    for a in actions:
        if isinstance(a, Withdrawn) and a.entrant_id not in order:
            order.append(a.entrant_id)
    return order


def place_withdrawn(gone, status, rows, start):
    """The withdrawn rank after every finisher from ``start`` on, each
    with its own rank, the latest withdrawn highest: each takes "the next
    available rank determined by the number of riders remaining on the
    track at this moment" (USAC 2O3(e)), and a later withdrawal leaves
    fewer on the track. A status entered after the withdrawal wins and the
    row is listed by it (R-NF-3: "A later Disqualify wins").
    AMBIGUITY: the register names only the DQ as following a withdrawal;
    a DNP the validation lets through is read the same way, as any status
    wins. Returns the groups, one rider each, and the next free rank."""
    groups = []
    rank = start
    for e in reversed(gone):
        if e in status:
            continue
        rows[e]["rank"] = rank
        rows[e]["withdrawn"] = True
        groups.append([e])
        rank += 1
    return groups, rank


def tail_groups(entrants, status, rows, after):
    """The DNF group shares the rank right after the last finisher and keeps
    its points (R-NF-2, UCI 3.3.012 A group 2); then DNP, DQ, DNS unranked
    in that order. Returns the ordered tail groups."""
    tail = []
    dnf = [e for e in entrants if status.get(e) == "DNF"]
    if dnf:
        for e in dnf:
            rows[e]["rank"] = after
        tail.append(dnf)
    for code in UNRANKED_ORDER:
        group = [e for e in entrants if status.get(e) == code]
        if group:
            tail.append(group)
    return tail


def finish_rows(entrants, status, rows):
    for e in entrants:
        rows[e]["status"] = status.get(e)


# ---------------------------------------------------------------- placings


def score_placings(rules, entrants, actions):
    """Scratch Race and everything placed by the line (R-CHASE-1 to 5, R-LAP-2)."""
    status = dict(last_status(actions))
    gone = withdrawn_order(actions)
    gained, lost, struck = lap_counts(actions)
    rows = {e: row(e) for e in entrants}
    for e in entrants:
        rows[e]["gained"] = gained[e] - struck[e]
        rows[e]["lost"] = lost[e]
        rows[e]["not_counted"] = struck[e]
    net = {e: rows[e]["gained"] - rows[e]["lost"] for e in entrants}

    if rules.laps_count_for_ranking and not rules.lapped_riders_placed_by_laps:
        # UCI 3.2.177 reading (register "If you race under UCI"): a rider on
        # negative laps still recorded at the line is marked DNF.
        # AMBIGUITY: a withdrawn rider on negative laps. The register says
        # laps never reorder the withdrawn (R-NF-3) and a DNF is refused
        # for them, so the rank by the moment stands.
        for e in entrants:
            if e not in status and e not in gone and net[e] < 0:
                status[e] = "DNF"

    finish = finish_of(actions)
    # A withdrawn rider is out of the field from the entry's moment
    # (R-NF-3), so only the riders still racing take the line.
    racing = [e for e in entrants if e not in status and e not in gone]
    groups = []
    if finish is None:
        # Nobody is ranked until the line (no article; the program's shape).
        after = len(racing) + 1
        groups = [list(racing)]
    else:
        pos = line_positions(finish.places)
        far = float("inf")

        def key(e):
            if rules.laps_count_for_ranking:
                return (-net[e], pos.get(e, far))
            return (pos.get(e, far),)

        # Laps first, then the line (R-LAP-2, USAC 2C4, 2C5); riders the
        # judges did not place share the next place on their lap (R-CHASE-1).
        groups = group_by_key(racing, key)
        ranks, after = competition_ranks(groups)
        for e, r in ranks.items():
            rows[e]["rank"] = r
        # OBSERVED: a rider with a status loses the line position in a
        # placings race (the points engines keep it); shape only.
        for e in racing:
            rows[e]["final_place"] = pos.get(e)
    # Before the line the withdrawn already hold their rank behind the
    # riders still racing: "with four still racing, the rider is 5th"
    # (R-NF-3, "Where the program decides").
    held, after = place_withdrawn(gone, status, rows, after)
    groups += held
    finish_rows(entrants, status, rows)
    groups += tail_groups(entrants, status, rows, after)
    return rows, groups


# ---------------------------------------------------------- sprint points


def sprint_table(rules, sprint_no):
    """R-POINTS-1: the intermediate table, and the sprint numbered
    sprint_count doubled (final_points); an explicit per-sprint table
    replaces both. A sprint past the table scores nothing."""
    if rules.points_by_sprint is not None:
        if 1 <= sprint_no <= len(rules.points_by_sprint):
            return rules.points_by_sprint[sprint_no - 1]
        return ()
    if rules.sprint_count is not None and sprint_no == rules.sprint_count:
        return rules.final_points
    return rules.intermediate_points


def sprint_points(places, table):
    """R-POINTS-2: tied riders take the place they tied for and its points,
    and the places they used up score for nobody."""
    out = {}
    for e, pos in line_positions(places).items():
        out[e] = table[pos - 1] if pos <= len(table) else 0
    return out


def score_sprint_points(rules, entrants, actions):
    """Points Race, Madison (teams as entrants), Tempo Race."""
    status = last_status(actions)
    gone = withdrawn_order(actions)
    gained, lost, struck = lap_counts(actions)
    rows = {e: row(e) for e in entrants}
    sprints = {}
    adjust = Counter()
    out_of_finish = set()
    for a in actions:
        if isinstance(a, SprintResult):
            # AMBIGUITY: the register does not say what a second entry of
            # the same sprint number means; the newest is taken (a
            # reopened sprint is "recorded as one replacement").
            sprints[a.sprint_no] = a.places
        elif isinstance(a, PointsAdjusted):
            adjust[a.entrant_id] += a.points
        elif isinstance(a, OutOfFinish):
            out_of_finish.add(a.entrant_id)
    finish = finish_of(actions)
    count = rules.sprint_count

    points = Counter()
    for no, places in sprints.items():
        points.update(sprint_points(places, sprint_table(rules, no)))
    if finish is not None and count not in sprints:
        # The finish order is the final sprint, entered as the full order
        # ("What the scorer enters"); when the final was not entered on
        # its own the line awards the final table.
        points.update(sprint_points(finish.places, sprint_table(rules, count)))

    for e in entrants:
        rows[e]["gained"] = gained[e] - struck[e]
        rows[e]["lost"] = lost[e]
        rows[e]["not_counted"] = struck[e]
        rows[e]["adjust"] = adjust[e]
        # A status entered after Out of the finish (a DQ is allowed, R-POINTS-5's
        # pinned test) takes the row out of the finishers, so the flag goes.
        rows[e]["out_of_finish"] = e in out_of_finish and e not in status
        lap_points = (
            rows[e]["gained"] * rules.lap_gained_points - rows[e]["lost"] * rules.lap_lost_points
        )
        rows[e]["total"] = points[e] + lap_points + adjust[e]

    # R-POINTS-4: level on points, the places in the final sprint decide,
    # read from the full finish order. AMBIGUITY: with a known count but
    # no finish yet, the register says only that nothing breaks the tie
    # (the final sprint has not been ridden), so ties share.
    final_line = {}
    if finish is not None:
        final_line = line_positions(finish.places)
    elif count in sprints:
        final_line = line_positions(sprints[count])
    far = float("inf")

    def key(e):
        if rules.tie_break == "final_sprint":
            # AMBIGUITY: a rider with no final place against one with a
            # place, level on points. The register only says riders with
            # no place "between them" share; a placed rider is put ahead.
            return (-rows[e]["total"], final_line.get(e, far))
        return (-rows[e]["total"],)

    # The withdrawn keep their points and laps as figures, which never
    # reorder them (R-NF-3): they rank after every finisher, and a rider
    # out of the finish is a finisher (R-POINTS-5).
    finishers = [e for e in entrants if e not in status and e not in gone]
    if sprints or finish is not None:
        groups = group_by_key(finishers, key)
        ranks, after = competition_ranks(groups)
        for e, r in ranks.items():
            rows[e]["rank"] = r
    else:
        # OBSERVED (not in the register): nothing is ranked until a sprint
        # or the finish is recorded, even with a lap gained on the sheet.
        groups = [list(finishers)]
        after = len(finishers) + 1
    # AMBIGUITY: a withdrawal before any sprint is recorded. The register
    # says the rank shows from the moment on, since the rule fixes it
    # then, so the withdrawn rank behind everyone still racing even while
    # the finishers are not yet ranked.
    held, after = place_withdrawn(gone, status, rows, after)
    groups += held
    for e in entrants:
        rows[e]["final_place"] = final_line.get(e)
    finish_rows(entrants, status, rows)
    groups += tail_groups(entrants, status, rows, after)
    return rows, groups


# ------------------------------------------------------------- elimination


def score_elimination(rules, entrants, actions):
    """R-ELIM-1 to R-ELIM-8 with the program's readings from "Where the
    program decides": one Eliminated entry is one call and its riders share
    a place; a DNF while in is out at that moment in a call of its own; a
    DQ, DNS, or DNP is never placed and the places close up."""
    status = last_status(actions)
    rows = {e: row(e) for e in entrants}
    out_at = {}
    call = 0
    for a in actions:
        if isinstance(a, Eliminated):
            if not a.entrant_ids:
                continue  # green flag: no place taken
            call += 1
            for e in a.entrant_ids:
                out_at.setdefault(e, call)
        elif isinstance(a, Status) and a.status == "DNF":
            if a.entrant_id in out_at:
                continue  # R-ELIM-8: changes only the mark
            call += 1
            out_at[a.entrant_id] = call

    placed = [e for e in entrants if status.get(e) in (None, "DNF")]
    alive = [e for e in placed if e not in out_at]
    calls = sorted({out_at[e] for e in placed if e in out_at}, reverse=True)
    gone = [[e for e in placed if out_at.get(e) == c] for c in calls]
    # eliminated_at counts the calls that still place someone, 1 for the
    # first rider out, among the riders the race placed.
    order = sorted(calls)
    for n, c in enumerate(order, start=1):
        for e in placed:
            if out_at.get(e) == c:
                rows[e]["eliminated_at"] = n

    finish = finish_of(actions)
    head = None
    if finish is not None:
        # R-ELIM-4, R-ELIM-5: the final sprint places the survivors; a
        # survivor the judges did not place shares the next place (R-TIE-1).
        pos = line_positions(finish.places)
        seen = sorted({pos[e] for e in alive if e in pos})
        head = [[e for e in alive if pos.get(e) == p] for p in seen]
        head.append([e for e in alive if e not in pos])
        for e in alive:
            rows[e]["final_place"] = pos.get(e)
    elif len(alive) <= 1:
        # "R-ELIM-4 and R-ELIM-5, one survivor": the last rider standing
        # wins with no final sprint.
        head = [alive]
    elif not rules.final_by_sprint and len(alive) <= rules.survivors:
        # AMBIGUITY: a miss-and-out to N survivors with no final sprint
        # entered and final_by_sprint off; the survivors share.
        head = [alive]

    groups = []
    if head is not None:
        groups = [g for g in head if g] + gone
        ranks, after = competition_ranks(groups)
    else:
        # Still racing: the riders out count down from the field
        # (R-ELIM-2, test_mid_race_ranks_count_down_from_the_field).
        groups = [list(alive)] + gone
        ranks, after = competition_ranks(gone, start=len(alive) + 1)
    for e, r in ranks.items():
        rows[e]["rank"] = r
    finish_rows(entrants, status, rows)
    # A DNF rider the race placed keeps the place; the tail is the
    # unranked statuses only.
    for code in UNRANKED_ORDER:
        group = [e for e in entrants if status.get(e) == code]
        if group:
            groups.append(group)
    return rows, groups


# ------------------------------------------------------------- win-and-out


def score_win_and_out(rules, entrants, actions):
    """R-WIN-1 to R-WIN-5: each bell decides the next open place from the
    top (forward) or the bottom (reverse); a dead heat is an equal placing
    that uses one place per rider (USAC 1M6(a), 1M4(b)), so the next bell
    is for the next open place; a lap winner later marked DNF or DQ
    vacates the place and the later places close up; the riders left fill
    the open places by the line, and a shortened race fills from the first
    place no bell decided."""
    status = last_status(actions)
    rows = {e: row(e) for e in entrants}
    by_lap = {}
    for a in actions:
        if isinstance(a, SprintResult) and a.places:
            # AMBIGUITY: riders listed behind the lap's first group are
            # not in any rule; only the first group takes the place.
            # AMBIGUITY: the same lap entered twice; the newest is taken.
            by_lap[a.sprint_no] = list(a.places[0])
    decided = {}  # place -> (width, riders entered)
    used = 0
    for lap in sorted(by_lap):
        entered = by_lap[lap]
        width = max(1, len(entered))
        if rules.direction == "forward":
            place = used + 1
        else:
            place = max(1, rules.places - used - width + 1)
        decided[place] = (width, entered)
        used += width
    # A statused winner vacates a place; a vacated place is deleted and
    # the places after it move up ("the later places close up"). The
    # places are sets, not counts: in reverse a dead heat for the top
    # place is clamped to 1st and its two places can overlap a place an
    # earlier bell decided, and a place still held by a tied rider is
    # not vacated even when the bell's own winner is out.
    numbered = []
    taken = set()
    held = set()
    for place in sorted(decided):
        width, entered = decided[place]
        taken.update(range(place, place + width))
        winners = [e for e in entered if e not in status]
        if winners:
            numbered.append((place, winners))
            held.update(range(place, place + len(winners)))
    vacated = taken - held
    numbered = [(place - sum(1 for v in vacated if v < place), g) for place, g in numbered]
    placed = {w for _, g in numbered for w in g}
    left = [e for e in entrants if e not in status and e not in placed]
    finish = finish_of(actions)

    if finish is None:
        # Running: the lap winners hold the place the bell gave them
        # (less the vacated places above); the rest are unranked.
        groups = [list(left)]
        for place, group in numbered:
            for e in group:
                rows[e]["rank"] = place
            groups.append(list(group))
        # The DNF group ranks after every place shown and every rider
        # placed or racing, whichever is more (in reverse the held places
        # are the high numbers and the riders racing fill below them).
        top = max((p for p, _ in numbered), default=0)
        after = max(top, len(placed) + len(left)) + 1
    else:
        # OBSERVED: the line positions are read with statused riders
        # taken out of the finish order (shape only; the placings engine
        # keeps the raw positions).
        trimmed = [[e for e in g if e not in status] for g in finish.places]
        pos = line_positions(trimmed)
        slot_after = 1 + sum(len(g) for g in trimmed)
        fill = group_by_key(left, lambda e: pos.get(e, slot_after))
        for e in left:
            rows[e]["final_place"] = pos.get(e, slot_after)
        # R-WIN-4: fill the open places in finish order; R-WIN-5: a tie at
        # the line shares the place and skips the next.
        open_places = [p for p in range(1, len(entrants) + len(taken) + 2) if p not in taken]
        slots = [(p, g, "lap") for p, g in numbered]
        cursor = 0
        for group in fill:
            slots.append((open_places[cursor], group, "fill"))
            cursor += len(group)
        slots.sort(key=lambda s: s[0])
        # Once the finish is in the ranks are read top to bottom with no
        # gap (a vacated place and an open place nobody filled close up),
        # every tie advancing the rank by its size (R-TIE-1, R-WIN-5).
        groups = []
        rank = 1
        for _, group, _kind in slots:
            for e in group:
                rows[e]["rank"] = rank
            groups.append(list(group))
            rank += len(group)
        after = rank
    finish_rows(entrants, status, rows)
    groups += tail_groups(entrants, status, rows, after)
    return rows, groups


# ------------------------------------------------------------- aggregate


def score_aggregate(rules, entrants, race_views):
    """R-TEAM-1 to R-TEAM-3, R-TEAM-5, R-OMNI-1 to R-OMNI-4 over per-race
    views [{entrant: (rank, status, total, final_place)}]; an entrant
    missing from a view did not enter that race.

    Summed totals (points_by_place None) or a place table with
    points_beyond_table past its end; the indexes in sum_total_races add
    their raw total instead (the omnium's Points Race, R-OMNI-2); a DNF
    keeps the points it scored where totals are summed (R-TEAM-2) and takes
    dnf_points where a table converts the place; absent_points for a race
    not entered. must_finish_all leaves a non-finisher or absentee out,
    marked DNF (DQ when disqualified somewhere), after the ranked rows
    (R-OMNI-4). Ties: most firsts, then seconds, ..., then the better
    place in the last race where one of them placed (R-TEAM-3); or the
    last race's final sprint (R-OMNI-3); or none.
    """
    rows = {e: row(e) for e in entrants}
    table = rules.points_by_place
    total = {}
    places = {e: [] for e in entrants}
    out = {}
    for e in entrants:
        t = 0
        for i, view in enumerate(race_views):
            if e not in view:
                t += rules.absent_points
                places[e].append(None)
                if rules.must_finish_all:
                    out.setdefault(e, "DNF")
                continue
            rank, status, race_total, _, out_at = (*view[e], False)[:5]
            # An Elimination rider out by a DNF holds the place they went
            # out in, and a place table scores it (R-OMNI, Standing.placed).
            placed = rank is not None and (status is None or out_at)
            places[e].append(rank if placed else None)
            if status is not None and rules.must_finish_all:
                out[e] = "DQ" if status == "DQ" or out.get(e) == "DQ" else out.get(e, "DNF")
            summed = table is None or i in rules.sum_total_races
            if summed:
                # AMBIGUITY: the rules docstring keeps a DNF's points where
                # the total is summed; the register (R-TEAM-2) says the same
                # for the Team Omnium. Other statuses take status_points.
                if status in (None, "DNF"):
                    t += race_total * rules.multiplier(i)
                else:
                    t += rules.status_points(status)
            elif placed:
                pts = table[rank - 1] if rank <= len(table) else rules.points_beyond_table
                t += pts * rules.multiplier(i)
            else:
                t += rules.status_points(status)
        total[e] = t
        rows[e]["total"] = t

    ranked = [e for e in entrants if e not in out]
    sign = -1 if rules.direction == "high" else 1

    def profile(e):
        # Most firsts, then most seconds, and so on (R-TEAM-3). AMBIGUITY:
        # a shared first counts as a first for each entrant sharing it.
        return tuple(-sum(1 for r in places[e] if r == p) for p in range(1, len(entrants) + 1))

    def primary(e):
        if rules.tie_break == "most_firsts_then_last_race":
            return (sign * total[e], profile(e))
        return (sign * total[e],)

    groups = group_by_key(ranked, primary)
    final = []
    far = float("inf")
    for g in groups:
        if len(g) == 1 or rules.tie_break == "none":
            final.append(g)
            continue
        if rules.tie_break == "most_firsts_then_last_race":
            # R-TEAM-3: "the better place in the last race (or the nearest
            # race where one of them placed)", read pairwise: for each two,
            # the nearest race from the end where either placed decides.
            def cmp(a, b):
                for i in range(len(race_views) - 1, -1, -1):
                    pa, pb = places[a][i], places[b][i]
                    if pa is None and pb is None:
                        continue
                    pa = far if pa is None else pa
                    pb = far if pb is None else pb
                    return (pa > pb) - (pa < pb)
                return 0

            import functools

            ordered = sorted(g, key=functools.cmp_to_key(cmp))
            sub = []
            for e in ordered:
                if sub and cmp(sub[-1][0], e) == 0:
                    sub[-1].append(e)
                else:
                    sub.append([e])
            final.extend(sub)
        else:
            # last_race_final_sprint (R-OMNI-3): the final sprint of the last race
            last = race_views[-1] if race_views else {}

            def fs(e, last=last):
                v = last.get(e)
                return v[3] if v is not None and v[3] is not None else far

            final.extend(group_by_key(g, fs))
    ranks, _ = competition_ranks(final)
    for e, r in ranks.items():
        rows[e]["rank"] = r
    for e, code in out.items():
        rows[e]["status"] = code
    tail = [e for e in entrants if e in out]
    if tail:
        final.append(tail)
    return rows, final


score_team_omnium = score_aggregate


# ------------------------------------------------------------- dispatch

PLACINGS_KEYS = {
    "scratch",
    "chase",
    "unknown_distance",
    "chariot",
    "handicap",
    "keirin",
    "match_sprint",
    "placings",
}
SPRINT_KEYS = {"points", "madison", "tempo", "sprint_points"}


def score(format_key, rules, entrants, actions):
    if format_key in PLACINGS_KEYS:
        return score_placings(rules, entrants, actions)
    if format_key in SPRINT_KEYS:
        return score_sprint_points(rules, entrants, actions)
    if format_key == "elimination":
        return score_elimination(rules, entrants, actions)
    if format_key == "win_and_out":
        return score_win_and_out(rules, entrants, actions)
    raise ValueError(format_key)
