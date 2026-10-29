"""Differential test: each engine against a naive second scorer.

The second scorer here adds up a race the way a person does with a
paper sheet and the rulebook open beside it: a column per sprint, a
column for laps, a total, then sort. It is written from the articles in
docs/research/uci-track-formats.md and usac-track-formats.md, not from
the engine code, so the two only agree when both read the rules the
same way. Thousands of seeded random races (fields, sprints, ties, the
scorer's X, laps, non-finishers, rules values) go through both, and every
entrant's rank, status, total and laps must match.

Where the articles are silent the oracle says so in a comment and either
avoids generating that input or follows the engine's docstring when that
docstring cites an article. Inputs the engine refuses at entry time
(validate_for_format) are skipped and counted; most races must survive.
"""

import random
from collections import Counter

import pytest

from madtracker.scoring import compute_for_format, validate_for_format
from madtracker.scoring.actions import (
    Eliminated,
    FinishOrder,
    LapGained,
    LapLost,
    SprintResult,
    Status,
)
from madtracker.scoring.rules import (
    EliminationRules,
    PlacingsRules,
    SprintPointsRules,
    WinAndOutRules,
)

# Per format. Sized so the whole file runs in well under 20 s.
SEEDS = range(4000)

# The four codes the action model knows. Only DNF is ranked (UCI 3.3.012 A
# group 2); DNS outside heats, DQ and DNP get no rank.
CODES = ("DNF", "DNS", "DQ", "DNP")


class Skip(Exception):
    """The engine refused an entry the generator produced."""


def entrants_for(rng):
    return rng.sample(range(1, 400), rng.randint(2, 24))


def line(rng, riders, *, ties=True, x=False, omit=False):
    """A random order across the line as places groups.

    ties: a few dead heats (equal placing, USAC 1M6(a)).
    x: an empty group now and then, the place the judges could not call.
    omit: the tail may be left out, riders the judges did not place.
    """
    riders = list(riders)
    rng.shuffle(riders)
    if omit and riders and rng.random() < 0.3:
        riders = riders[: rng.randint(1, len(riders))]
    places = []
    i = 0
    while i < len(riders):
        if x and rng.random() < 0.08:
            places.append([])
        size = 1
        if ties and rng.random() < 0.12:
            size = rng.randint(2, 3)
        places.append(riders[i : i + size])
        i += size
    return places


def add(fmt, rules, entrants, actions, action):
    if validate_for_format(fmt, rules, entrants, actions, action):
        raise Skip
    actions.append(action)


def engine_view(standings):
    return {
        row.entrant_id: (row.rank, row.status, row.total_points, row.laps_gained, row.laps_lost)
        for row in standings.rows
    }


def competition_ranks(groups, start=1):
    """1, 1, 3: a group shares the place it tied for and the places it
    used are skipped (USAC 1M6(a), UCI 3.2.118's "same position")."""
    out = {}
    rank = start
    for group in groups:
        if not group:
            continue
        for eid in group:
            out[eid] = rank
        rank += len(group)
    return out, rank


def sheet_basics(entrants, actions):
    """The scorer's margin notes: last status mark per rider and lap ticks."""
    status = {}
    gained = Counter()
    lost = Counter()
    for action in actions:
        if isinstance(action, Status):
            status[action.entrant_id] = action.status
        elif isinstance(action, LapGained):
            gained.update(action.entrant_ids)
        elif isinstance(action, LapLost):
            lost.update(action.entrant_ids)
    return status, gained, lost


def finish_of(actions):
    found = None
    for action in actions:
        if isinstance(action, FinishOrder):
            found = action
    return found


def line_positions(places):
    """Where each rider crossed: a dead heat shares the position, and each
    rider or X uses up one position."""
    pos = {}
    slot = 1
    for group in places:
        for eid in group:
            pos[eid] = slot
        slot += len(group) or 1
    return pos


def compare(fmt, gen, oracle, keep=lambda actions: True):
    """keep picks which generated races this test judges, so one engine's
    finished and provisional standings fail separately."""
    skipped = 0
    failures = []
    for seed in SEEDS:
        # A string seed per format keeps each format's races its own.
        rng = random.Random(f"{fmt}:{seed}")
        try:
            rules, entrants, actions = gen(rng)
        except Skip:
            skipped += 1
            continue
        if not keep(actions):
            continue
        got = engine_view(compute_for_format(fmt, rules, entrants, actions))
        want = oracle(rules, entrants, actions)
        if got != want:
            diff = {e: (want.get(e), got.get(e)) for e in entrants if want.get(e) != got.get(e)}
            failures.append((len(entrants), len(actions), seed, rules, entrants, actions, diff))
    assert skipped < len(SEEDS) / 2, f"{fmt}: {skipped} of {len(SEEDS)} races skipped"
    if failures:
        failures.sort(key=lambda f: (f[0], f[1], f[2]))
        n, _, seed, rules, entrants, actions, diff = failures[0]
        lines = "\n".join(f"  {e!r}" for e in actions)
        pytest.fail(
            f"{fmt}: {len(failures)} of {len(SEEDS)} races disagree. Smallest: seed {seed},"
            f" {n} entrants {entrants}\nrules {rules}\nactions:\n{lines}\n"
            f"entrant: (oracle, engine) as (rank, status, total, gained, lost)\n"
            + "\n".join(f"  {e}: {w} | {g}" for e, (w, g) in diff.items())
        )


# Points race, madison, tempo (and the engine's per-sprint tables)


def gen_sprint_points(fmt):
    def gen(rng):
        entrants = entrants_for(rng)
        count = rng.randint(1, 10)
        style = rng.choice(("known", "known", "unknown", "snowball"))
        inter = tuple(rng.randint(0, 12) for _ in range(rng.randint(1, 6)))
        if fmt == "tempo":
            inter = (rng.randint(1, 2),)
        final = (
            tuple(2 * v for v in inter)
            if rng.random() < 0.5
            else tuple(rng.randint(0, 20) for _ in range(rng.randint(1, 6)))
        )
        table = None
        if style == "snowball":
            table = tuple(
                tuple(rng.randint(0, 10) for _ in range(rng.randint(1, 5))) for _ in range(count)
            )
        rules = SprintPointsRules(
            sprint_count=None if style == "unknown" else count,
            intermediate_points=inter,
            final_points=final,
            points_by_sprint=table,
            lap_gained_points=rng.randint(0, 30),
            lap_lost_points=rng.randint(0, 30),
            tie_break=rng.choice(("final_sprint", "final_sprint", "none")),
            scored_unit="team" if fmt == "madison" else "rider",
        )
        actions = []
        racing = list(entrants)

        def margin(sprint_no):
            for _ in range(rng.choice((0, 0, 1, 2))):
                kind = rng.choice((LapGained, LapLost))
                who = rng.sample(racing, rng.randint(1, min(3, len(racing))))
                if kind is LapGained:
                    at = sprint_no if rng.random() < 0.3 else None
                    add(fmt, rules, entrants, actions, LapGained(who, sprint_no=at))
                else:
                    add(fmt, rules, entrants, actions, LapLost(who))
            if len(racing) > 1 and rng.random() < 0.1:
                eid = rng.choice(racing)
                racing.remove(eid)
                add(fmt, rules, entrants, actions, Status(eid, rng.choice(CODES)))

        # With a known count the final sprint is numbered `count`; with an
        # unknown count every SprintResult is intermediate and the finish
        # is the final sprint.
        intermediates = count - 1
        # A race stopped before the line with an unknown count is left
        # out: the engine then breaks ties by the last sprint ridden, the
        # articles only by the final sprint, and that standing is
        # provisional anyway (reported, not asserted).
        stop_early = style != "unknown" and rng.random() < 0.15
        last = rng.randint(1, max(1, intermediates)) if stop_early else intermediates
        for n in range(1, last + 1):
            margin(n)
            add(fmt, rules, entrants, actions, SprintResult(n, line(rng, racing, x=True)))
        if stop_early:
            return rules, entrants, actions
        margin(count)
        finish = line(rng, racing, omit=True)
        if style != "unknown" and rng.random() < 0.5:
            # The final sprint entered on its own: its scoring places are
            # the head of the same line, since it is one crossing.
            depth = rng.randint(1, len(finish))
            add(fmt, rules, entrants, actions, SprintResult(count, finish[:depth]))
            if rng.random() < 0.2:
                return rules, entrants, actions
        add(fmt, rules, entrants, actions, FinishOrder(finish))
        if rng.random() < 0.1:
            add(fmt, rules, entrants, actions, Status(rng.choice(entrants), "DQ"))
        return rules, entrants, actions

    return gen


def oracle_sprint_points(rules, entrants, actions):
    status, gained, lost = sheet_basics(entrants, actions)
    sprints = {}
    for action in actions:
        if isinstance(action, SprintResult):
            sprints[action.sprint_no] = action.places
    finish = finish_of(actions)

    def awards(sprint_no):
        # UCI 3.2.118, USAC 2M2(f): intermediate table, and the sprint at
        # the full distance doubled; a snowball's own table replaces both.
        if rules.points_by_sprint is not None:
            return rules.points_by_sprint[sprint_no - 1]
        if sprint_no == rules.sprint_count:
            return rules.final_points
        return rules.intermediate_points

    def score(places, table):
        # Tied riders take the points of the place they tied for and the
        # places they used up score for nobody; an X scores for nobody either.
        out = {}
        for eid, pos in line_positions(places).items():
            out[eid] = table[pos - 1] if pos <= len(table) else 0
        return out

    total = Counter()
    for sprint_no, places in sprints.items():
        total.update(score(places, awards(sprint_no)))
    final_no = rules.sprint_count
    if finish is not None and (final_no is None or final_no not in sprints):
        # The line at the end is the last sprint when it was not entered
        # separately (UCI 3.2.118 "the last sprint after the full distance").
        table = rules.final_points if final_no is None else awards(final_no)
        total.update(score(finish.places, table))
    for eid in entrants:
        total[eid] += gained[eid] * rules.lap_gained_points - lost[eid] * rules.lap_lost_points

    # Tie on points: the places in the final sprint (UCI 3.2.119,
    # USAC 2M2(g)), read from the full finish order. With no final sprint
    # ridden yet there is nothing to break the tie with.
    final_line = {}
    if finish is not None:
        final_line = line_positions(finish.places)
    elif final_no is not None and final_no in sprints:
        final_line = line_positions(sprints[final_no])
    nowhere = float("inf")

    def key(eid):
        if rules.tie_break == "final_sprint":
            return (-total[eid], final_line.get(eid, nowhere))
        return (-total[eid],)

    finishers = sorted((eid for eid in entrants if eid not in status), key=key)
    groups = []
    for eid in finishers:
        if groups and key(groups[-1][0]) == key(eid):
            groups[-1].append(eid)
        else:
            groups.append([eid])
    rank, after = competition_ranks(groups)
    # UCI 3.3.012 A: withdrawn riders share the next rank after every
    # finisher, whatever their points. The rest are not ranked.
    for eid in entrants:
        if status.get(eid) == "DNF":
            rank[eid] = after
    return {
        eid: (rank.get(eid), status.get(eid), total[eid], gained[eid], lost[eid])
        for eid in entrants
    }


@pytest.mark.parametrize("fmt", ["points", "madison", "tempo"])
def test_sprint_points_engine_matches_the_paper_sheet(fmt):
    compare(fmt, gen_sprint_points(fmt), oracle_sprint_points)


# Elimination and miss-and-out


def gen_elimination(rng):
    entrants = entrants_for(rng)
    survivors = rng.randint(1, min(4, len(entrants)))
    rules = EliminationRules(
        survivors=survivors, final_by_sprint=survivors > 1 and rng.random() < 0.85
    )
    fmt = "elimination"
    actions = []
    still_in = list(entrants)
    out = []
    marked = set()
    sprint_no = 0
    while len(still_in) > survivors:
        if rng.random() < 0.05:
            return rules, entrants, actions
        roll = rng.random()
        if roll < 0.12:
            # A mark between sprints: an abandon while in, a mark on a
            # rider already out, or a DQ or DNS on anyone.
            pool = [e for e in entrants if e not in marked]
            if not pool:
                continue
            eid = rng.choice(pool)
            code = "DNF" if eid in still_in and rng.random() < 0.6 else rng.choice(CODES)
            add(fmt, rules, entrants, actions, Status(eid, code))
            marked.add(eid)
            if eid in still_in:
                still_in.remove(eid)
            continue
        if rng.random() < 0.85 or sprint_no == 0:
            sprint_no += 1
        if roll < 0.2:
            who = []
        else:
            take = 1 if rng.random() < 0.85 else rng.randint(2, 3)
            who = rng.sample(still_in, min(take, len(still_in) - 1))
        add(fmt, rules, entrants, actions, Eliminated(sprint_no, who))
        for eid in who:
            still_in.remove(eid)
            out.append(eid)
    if rules.final_by_sprint and still_in and rng.random() < 0.9:
        add(fmt, rules, entrants, actions, FinishOrder(line(rng, still_in, omit=True)))
    return rules, entrants, actions


def oracle_elimination(rules, entrants, actions):
    status, _, _ = sheet_basics(entrants, actions)
    # The sheet: each rider's "out at" call number. One call takes one
    # place for everyone named in it: the books give no order between
    # riders out together (USAC20 2E5 "equally"). A rider marked DNF
    # while in is out at that moment, a call of their own, below the
    # next one out (USAC 2E4(a)(ii), 2E4(d); the program's one reading
    # for every DNF, docs/scoring-rules.md "Where the program decides").
    out_at = {}
    call = 0
    for action in actions:
        if isinstance(action, Eliminated):
            call += 1
            for eid in action.entrant_ids:
                out_at.setdefault(eid, call)
        elif isinstance(action, Status):
            eid = action.entrant_id
            if action.status != "DNF" or eid in out_at:
                continue
            call += 1
            out_at[eid] = call

    # DQ, DNS and DNP take no place (UCI 3.3.012 A), so they leave the
    # count entirely, eliminated first or not.
    placed = [e for e in entrants if status.get(e) in (None, "DNF")]
    alive = [e for e in placed if e not in out_at]
    calls = sorted({out_at[e] for e in placed if e in out_at}, reverse=True)
    # Inverse order of elimination (UCI 3.2.223bis, USAC 2E3(e)).
    gone = [[e for e in placed if out_at.get(e) == c] for c in calls]

    finish = finish_of(actions)
    head = None
    if finish is not None:
        # The final sprint places the survivors (UCI 3.2.224, USAC 2E3(f),
        # 2E5); a survivor the judges did not place shares the next place.
        pos = line_positions(finish.places)
        seen = sorted({pos[e] for e in alive if e in pos})
        head = [[e for e in alive if pos.get(e) == p] for p in seen]
        head.append([e for e in alive if e not in pos])
    elif len(alive) <= 1:
        head = [alive]
    elif not rules.final_by_sprint and len(alive) <= rules.survivors:
        # A miss-and-out ridden to N with no sprint: the survivors share.
        head = [alive]

    if head is not None:
        rank, _ = competition_ranks(head + gone)
    else:
        rank, _ = competition_ranks(gone, start=len(alive) + 1)
    return {eid: (rank.get(eid), status.get(eid), 0, 0, 0) for eid in entrants}


def test_elimination_engine_matches_the_paper_sheet():
    compare("elimination", gen_elimination, oracle_elimination)


# Win-and-out, Danish, Belgian


def gen_win_and_out(rng):
    entrants = entrants_for(rng)
    rules = WinAndOutRules(
        places=rng.randint(1, min(5, len(entrants))),
        direction=rng.choice(("forward", "reverse")),
    )
    fmt = "win_and_out"
    actions = []
    racing = list(entrants)
    for lap in range(1, rules.places + 1):
        if rng.random() < 0.08:
            break
        # Marks only on riders who have not taken a place: what happens
        # to a place whose winner is later DQ is not in any source (the
        # engine vacates it, uncited), so the oracle does not guess.
        if len(racing) > 1 and rng.random() < 0.1:
            eid = rng.choice(racing)
            racing.remove(eid)
            add(fmt, rules, entrants, actions, Status(eid, rng.choice(CODES)))
        if not racing:
            break
        winner = rng.choice(racing)
        racing.remove(winner)
        # Single winners only: a dead heat for a lap win is UNVERIFIED in
        # the research and the engine's handling has no article.
        behind = rng.sample(racing, rng.randint(0, min(3, len(racing))))
        add(fmt, rules, entrants, actions, SprintResult(lap, [[winner], *[[e] for e in behind]]))
    if racing and rng.random() < 0.85:
        add(fmt, rules, entrants, actions, FinishOrder(line(rng, racing, omit=True)))
        if rng.random() < 0.1:
            eid = rng.choice(racing)
            add(fmt, rules, entrants, actions, Status(eid, "DQ"))
    return rules, entrants, actions


def oracle_win_and_out(rules, entrants, actions):
    status, _, _ = sheet_basics(entrants, actions)
    announced = {}
    laps_run = 0
    for action in actions:
        if isinstance(action, SprintResult):
            laps_run += 1
            place = (
                action.sprint_no
                if rules.direction == "forward"
                else rules.places + 1 - action.sprint_no
            )
            announced[action.places[0][0]] = place
    finish = finish_of(actions)
    left = [e for e in entrants if e not in status and e not in announced]

    if finish is None:
        # Still racing: the lap winners hold the place the bell gave them,
        # the rest are unranked, and a DNF sits behind everyone still in
        # and behind every place shown (in reverse the held places are the
        # high numbers, which the riders still in fill below).
        rank = {e: p for e, p in announced.items() if e not in status}
        after = max(max(rank.values(), default=0), len(rank) + len(left)) + 1
    else:
        # The riders left fill the open places by the final lap
        # (usac-track-formats.md "Win-and-out family" step 3), first across
        # in the lowest open place. Then the sheet reads top to bottom with
        # equal placings as everywhere else (USAC 1M6(a)).
        taken = set(announced.values())
        open_places = [p for p in range(1, len(entrants) + rules.places + 2) if p not in taken]
        pos = line_positions(finish.places)
        by_line = sorted({pos[e] for e in left if e in pos})
        fill = [[e for e in left if pos.get(e) == p] for p in by_line]
        fill.append([e for e in left if e not in pos])
        slots = []
        cursor = 0
        for group in fill:
            if group:
                slots.append((open_places[cursor], group))
                cursor += len(group)
        slots.extend((p, [e]) for e, p in announced.items() if e not in status)
        slots.sort(key=lambda s: s[0])
        rank, after = competition_ranks([g for _, g in slots])
    for eid in entrants:
        if status.get(eid) == "DNF":
            rank[eid] = after
    return {eid: (rank.get(eid), status.get(eid), 0, 0, 0) for eid in entrants}


def test_win_and_out_engine_matches_the_paper_sheet():
    compare("win_and_out", gen_win_and_out, oracle_win_and_out, keep=finish_of)


def test_win_and_out_provisional_standings_match_the_paper_sheet():
    compare(
        "win_and_out",
        gen_win_and_out,
        oracle_win_and_out,
        keep=lambda action: not finish_of(action),
    )


# Scratch, chase and the other races ranked at the line


def gen_placings(rng):
    entrants = entrants_for(rng)
    rules = PlacingsRules(
        laps_count_for_ranking=rng.random() < 0.8,
        lapped_riders_placed_by_laps=rng.random() < 0.6,
    )
    fmt = "scratch"
    actions = []
    racing = list(entrants)
    for _ in range(rng.randint(0, 6)):
        roll = rng.random()
        if roll < 0.2 and len(racing) > 1:
            eid = rng.choice(racing)
            racing.remove(eid)
            add(fmt, rules, entrants, actions, Status(eid, rng.choice(CODES)))
        else:
            kind = LapGained if roll < 0.6 else LapLost
            who = rng.sample(racing, rng.randint(1, min(3, len(racing))))
            add(fmt, rules, entrants, actions, kind(who))
    if rng.random() < 0.9:
        # No X here: what an unseen place does to the ranks below it is
        # not settled (see the module notes in the report).
        add(fmt, rules, entrants, actions, FinishOrder(line(rng, racing, omit=True)))
    return rules, entrants, actions


def oracle_placings(rules, entrants, actions):
    status, gained, lost = sheet_basics(entrants, actions)
    status = dict(status)
    net = {e: gained[e] - lost[e] for e in entrants}
    if rules.laps_count_for_ranking and not rules.lapped_riders_placed_by_laps:
        # UCI 3.2.177: a lapped rider leaves the track, so ranks as DNF
        # (3.3.012 A) even if the scorer saw them at the line.
        for eid in entrants:
            if eid not in status and net[eid] < 0:
                status[eid] = "DNF"
    finish = finish_of(actions)
    racing = [e for e in entrants if e not in status]
    if finish is None:
        rank = {}
        after = len(racing) + 1
    else:
        # Laps first, then the line (USAC 2C4, 2C5, UCI 3.2.178); riders
        # the judges did not place share the next place on their lap
        # (USAC 1M6(a)).
        pos = line_positions(finish.places)
        nowhere = float("inf")

        def key(eid):
            p = pos.get(eid, nowhere)
            return (-net[eid], p) if rules.laps_count_for_ranking else (p,)

        groups = []
        for eid in sorted(racing, key=key):
            if groups and key(groups[-1][0]) == key(eid):
                groups[-1].append(eid)
            else:
                groups.append([eid])
        rank, after = competition_ranks(groups)
    for eid in entrants:
        if status.get(eid) == "DNF":
            rank[eid] = after
    return {eid: (rank.get(eid), status.get(eid), 0, gained[eid], lost[eid]) for eid in entrants}


def test_placings_engine_matches_the_paper_sheet():
    compare("scratch", gen_placings, oracle_placings)
