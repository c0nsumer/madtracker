"""Random race generators per format.

Each generator builds a log one action at a time and offers each action
to the engine's validate_for_format first. A refused action is dropped
and counted by its reason; the race goes on. The oracle's own idea of a
bad entry (oracle_valid, from the register's "What the scorer enters"
rules) is asked the same question, and the four-way agreement is
counted so the report can say where the two disagree on validity.
"""

import random
import re
from collections import Counter

from madtracker.scoring import validate_for_format
from madtracker.scoring.actions import (
    SCORING_KINDS,
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
from madtracker.scoring.rules import (
    EliminationRules,
    PlacingsRules,
    SprintPointsRules,
    WinAndOutRules,
)

CODES = ("DNF", "DNS", "DQ", "DNP")
PLACINGS_FORMATS = (
    "scratch",
    "chase",
    "handicap",
    "unknown_distance",
    "chariot",
    "keirin",
    "match_sprint",
)
NO_LAP_FORMATS = ("chariot", "keirin", "match_sprint")
SPRINT_FORMATS = ("points", "madison", "tempo")


def normalize(msg):
    """A refusal message with its numbers and names blanked, for counting."""
    return re.sub(r"#?\d+", "N", msg)


# ----------------------------------------------------------- oracle validity


def oracle_valid(fmt, rules, entrants, actions, new):
    """What the register says the scorer may enter. Returns a list of
    short reason tags; empty means the entry is allowed."""
    reasons = []
    ids = set(entrants)
    status = {}
    touched = set()  # riders with a place, lap, bell or mishap recorded
    finish = None
    sprints = set()
    out_of_finish = set()
    withdrawn = set()
    gained = Counter()
    struck = Counter()
    adjust = Counter()
    for a in actions:
        if isinstance(a, Status):
            status[a.entrant_id] = a.status
        elif isinstance(a, FinishOrder):
            finish = a
            touched.update(e for g in a.places for e in g)
        elif isinstance(a, SprintResult):
            sprints.add(a.sprint_no)
            touched.update(e for g in a.places for e in g)
        elif isinstance(a, (LapGained, LapLost, Eliminated, LapNotCounted)):
            touched.update(a.entrant_ids)
            if isinstance(a, LapGained):
                gained.update(a.entrant_ids)
            if isinstance(a, LapNotCounted):
                struck.update(a.entrant_ids)
        elif isinstance(a, OutOfFinish):
            out_of_finish.add(a.entrant_id)
            touched.add(a.entrant_id)
        elif isinstance(a, Withdrawn):
            withdrawn.add(a.entrant_id)
        elif isinstance(a, PointsAdjusted):
            adjust[a.entrant_id] += a.points

    def named(action):
        if isinstance(action, (SprintResult, FinishOrder)):
            flat = [e for g in action.places for e in g]
        elif isinstance(action, (LapGained, LapLost, Eliminated, LapNotCounted)):
            flat = list(action.entrant_ids)
        else:
            flat = [action.entrant_id]
        return flat

    flat = named(new)
    if any(e not in ids for e in flat):
        reasons.append("unknown entrant")
    if len(set(flat)) != len(flat):
        reasons.append("entrant named twice")
    if isinstance(new, (SprintResult, FinishOrder)) and any(not g for g in new.places):
        reasons.append("empty place group")

    is_sprint_fmt = fmt in SPRINT_FORMATS
    if is_sprint_fmt and rules.sprint_count is None:
        reasons.append("no sprint count")

    if new.kind in SCORING_KINDS:
        if finish is not None:
            reasons.append("scoring entry after the finish order")
        if any(status.get(e) for e in flat):
            reasons.append("scoring entry for a rider with a status")
        if any(e in out_of_finish for e in flat):
            reasons.append("scoring entry for a rider out of the finish")
        # R-NF-3: nothing entered after the mark places a withdrawn rider,
        # a second withdrawal included, since it would move the moment.
        if any(e in withdrawn for e in flat):
            reasons.append("scoring entry for a withdrawn rider")

    if isinstance(new, Status):
        if new.status == "DNS" and new.entrant_id in touched:
            reasons.append("DNS for a rider with a result")
        if new.status in ("DNS", "DNF") and finish is not None:
            reasons.append("DNS or DNF after the finish order")
        if new.status in ("DNS", "DNF") and new.entrant_id in out_of_finish:
            reasons.append("DNS or DNF for a rider out of the finish")
        # The rule places a withdrawn rider; only a DQ may follow
        # ("What the scorer enters").
        if new.status in ("DNS", "DNF") and new.entrant_id in withdrawn:
            reasons.append("DNS or DNF for a withdrawn rider")
        # A second mark on a rider is a DQ after a protest (R-ELIM-8, R-NF-5);
        # the window offers nothing else on a marked rider, so the
        # generator never writes another (``unoffered``), and the oracle
        # reads only what it is given.

    if isinstance(new, (LapGained, LapLost, LapNotCounted)):
        if fmt == "elimination":
            reasons.append("laps in an elimination")
        if fmt in NO_LAP_FORMATS or (fmt in PLACINGS_FORMATS and not rules.laps_count_for_ranking):
            reasons.append("laps where they do not count")
        if fmt == "win_and_out":
            reasons.append("laps where they do not count")
    if isinstance(new, LapNotCounted):
        if any(gained[e] - struck[e] < 1 for e in flat):
            reasons.append("no lap to cancel")
    if isinstance(new, Withdrawn) and fmt in ("elimination", "win_and_out"):
        # An Elimination clicks the rider out (R-ELIM-7) and a Win-and-Out
        # has no rule for it ("Where the program decides").
        reasons.append("withdrawn in an elimination or a win-and-out")
    if isinstance(new, (PointsAdjusted, OutOfFinish)) and not is_sprint_fmt:
        reasons.append("points ruling outside a points format")
    if isinstance(new, PointsAdjusted):
        if status.get(new.entrant_id) in ("DNS", "DQ", "DNP"):
            reasons.append("penalty on a DNS, DQ, or DNP rider")
        if adjust[new.entrant_id] + new.points > 0:
            reasons.append("penalty sum above zero")
    if isinstance(new, OutOfFinish) and is_sprint_fmt:
        count = rules.sprint_count or 0
        if not all(n in sprints for n in range(1, count)):
            reasons.append("out of the finish before the final sprint")
        if new.entrant_id in out_of_finish:
            reasons.append("out of the finish twice")
        if status.get(new.entrant_id):
            reasons.append("out of the finish for a rider with a status")
    if is_sprint_fmt and isinstance(new, SprintResult):
        count = rules.sprint_count or 0
        if not 1 <= new.sprint_no <= count:
            reasons.append("sprint number outside the race")
        if any(n not in sprints for n in range(1, new.sprint_no)):
            reasons.append("an earlier sprint is unrecorded")
    if is_sprint_fmt and isinstance(new, FinishOrder):
        count = rules.sprint_count or 0
        if any(n not in sprints for n in range(1, count)):
            reasons.append("finish while an earlier sprint is unrecorded")
    if fmt == "elimination":
        out = set()
        for a in actions:
            if isinstance(a, Eliminated):
                out.update(a.entrant_ids)
        if isinstance(new, Eliminated) and any(e in out for e in flat):
            reasons.append("eliminating a rider already out")
        if isinstance(new, (FinishOrder, Eliminated)):
            still_in = [e for e in entrants if e not in out and not status.get(e)]
            if isinstance(new, FinishOrder):
                if any(e in out for e in flat):
                    reasons.append("finish names a rider out")
                if len(still_in) > rules.survivors:
                    reasons.append("finish before the survivors are reached")
            if isinstance(new, Eliminated) and len(still_in) - len(flat) < rules.survivors and flat:
                # AMBIGUITY: the register never says the bell stops at the
                # survivor count; an Eliminated that drops below it is
                # likely refused by the engine.
                reasons.append("elimination below the survivor count")
        if isinstance(new, SprintResult):
            reasons.append("sprint result in an elimination")
    if fmt == "win_and_out":
        if isinstance(new, SprintResult) and not 1 <= new.sprint_no <= rules.places:
            reasons.append("lap number outside the places")
        if isinstance(new, Eliminated):
            reasons.append("elimination in a win-and-out")
    if fmt in PLACINGS_FORMATS and isinstance(new, (SprintResult, Eliminated)):
        reasons.append("sprint or elimination in a placings race")
    return reasons


# ----------------------------------------------------------- the generator


def unoffered(actions, new):
    """Why the scorer's window would never offer this entry, or None.

    The engines' validation is wider than the window: a marked rider's
    row offers only Disqualify, and the controller refuses any other mark
    on them before the engine sees it. A log with such an entry is one no
    scorer can make, so it is not offered to either side; a disagreement
    on it would only hide a real one.
    """
    if isinstance(new, Status) and new.status != "DQ":
        marked = {a.entrant_id for a in actions if isinstance(a, Status)}
        if new.entrant_id in marked:
            return "a mark other than DQ on a marked rider"
    return None


class Log:
    """One race's log under construction, with the refusal counters."""

    def __init__(self, fmt, rules, entrants, stats):
        self.fmt = fmt
        self.rules = rules
        self.entrants = entrants
        self.actions = []
        self.stats = stats

    def add(self, action):
        why = unoffered(self.actions, action)
        if why is not None:
            self.stats["unoffered"][why] += 1
            return False
        problems = validate_for_format(self.fmt, self.rules, self.entrants, self.actions, action)
        mine = oracle_valid(self.fmt, self.rules, self.entrants, self.actions, action)
        key = (bool(problems), bool(mine))
        self.stats["agreement"][key] += 1
        if problems and not mine:
            self.stats["engine_only"][normalize(problems[0])] += 1
        if mine and not problems:
            self.stats["oracle_only"][mine[0]] += 1
        if problems:
            self.stats["refused"][normalize(problems[0])] += 1
            return False
        self.actions.append(action)
        self.stats["accepted"][action.kind] += 1
        return True


def new_stats():
    return {
        "agreement": Counter(),
        "engine_only": Counter(),
        "oracle_only": Counter(),
        "refused": Counter(),
        "accepted": Counter(),
        "unoffered": Counter(),
    }


def entrants_for(rng):
    return rng.sample(range(1, 80), rng.randint(3, 20))


def line(rng, riders, *, ties=0.15, omit=0.25, bigtie=0.05):
    riders = list(riders)
    rng.shuffle(riders)
    if riders and rng.random() < omit:
        riders = riders[: rng.randint(0, len(riders))]
    places = []
    i = 0
    while i < len(riders):
        size = 1
        r = rng.random()
        if r < bigtie:
            size = rng.randint(3, 5)
        elif r < ties + bigtie:
            size = 2
        places.append(riders[i : i + size])
        i += size
    return places


def status_mark(rng, log, pool, codes=CODES):
    if not pool:
        return None
    eid = rng.choice(pool)
    code = rng.choice(codes)
    if log.add(Status(eid, code, "")):
        return eid, code
    return None


def withdraw_step(rng, log, racing, gone, laps=True):
    """Usually withdraws a rider still racing; now and then names one
    already withdrawn again, to see the refusals (a lap, a second
    withdrawal, DNS or DNF) and the DQ that is allowed to follow."""
    if gone and rng.random() < 0.3:
        e = rng.choice(gone)
        pick = rng.random()
        if pick < 0.3:
            log.add(Withdrawn(e))
        elif pick < 0.55:
            log.add(Status(e, rng.choice(("DNS", "DNF")), ""))
        elif pick < 0.75:
            log.add(Status(e, "DQ", ""))
        elif laps and pick < 0.9:
            log.add(rng.choice((LapGained, LapLost))([e]))
        else:
            log.add(LapNotCounted([e]))
        return
    if len(racing) > 1:
        e = rng.choice(racing)
        if log.add(Withdrawn(e)):
            racing.remove(e)
            gone.append(e)


# ---- placings


def gen_placings(rng, stats, entrants=None, fmt=None):
    fmt = fmt or rng.choice(PLACINGS_FORMATS)
    no_laps = fmt in NO_LAP_FORMATS
    rules = PlacingsRules(
        laps_count_for_ranking=not no_laps and rng.random() < 0.85,
        lapped_riders_placed_by_laps=rng.random() < 0.6,
    )
    entrants = list(entrants) if entrants is not None else entrants_for(rng)
    log = Log(fmt, rules, entrants, stats)
    racing = list(entrants)
    gone = []
    for _ in range(rng.randint(0, 8)):
        r = rng.random()
        if r < 0.12:
            withdraw_step(rng, log, racing, gone, laps=not no_laps)
            continue
        r = (r - 0.12) / 0.88
        if r < 0.2 and len(racing) > 1:
            got = status_mark(rng, log, racing)
            if got:
                racing.remove(got[0])
        elif r < 0.3 and racing:
            # a mark on a rider already marked, or a lap on one
            status_mark(rng, log, [e for e in entrants if e not in racing] or racing)
        elif r < 0.65 and racing:
            who = rng.sample(racing, rng.randint(1, min(4, len(racing))))
            log.add(LapGained(who, sprint_no=None))
        elif r < 0.9 and racing:
            who = rng.sample(racing, rng.randint(1, min(4, len(racing))))
            log.add(LapLost(who))
        elif racing:
            who = rng.sample(racing, 1)
            log.add(LapNotCounted(who))
    if rng.random() < 0.92:
        log.add(FinishOrder(line(rng, racing)))
        for _ in range(rng.choice((0, 0, 0, 1, 2))):
            r = rng.random()
            if r < 0.5 and racing:
                status_mark(rng, log, racing, ("DQ", "DNF", "DNS", "DNP"))
            elif racing:
                log.add(LapNotCounted(rng.sample(racing, 1)))
    return fmt, rules, entrants, log.actions


# ---- sprint points


def sprint_rules(rng, fmt):
    count = rng.randint(1, 8)
    style = rng.choice(("rulebook", "rulebook", "house", "random", "snowball", "none"))
    unit = "team" if fmt == "madison" else "rider"
    if fmt == "tempo":
        pts = rng.choice((1, 1, 1, 2, 3))
        return SprintPointsRules(
            sprint_count=count,
            intermediate_points=(pts,),
            final_points=(pts,),
            lap_gained_points=rng.choice((20, 20, 10, 4)),
            lap_lost_points=rng.choice((20, 20, 10, 4)),
            tie_break=rng.choice(("final_sprint", "final_sprint", "none")),
            scored_unit=unit,
        )
    if style == "rulebook":
        return SprintPointsRules(sprint_count=count, scored_unit=unit)
    if style == "house":
        table = (10, 7, 5, 3, 2, 1)
        return SprintPointsRules(
            sprint_count=count,
            intermediate_points=table,
            final_points=tuple(2 * p for p in table),
            lap_gained_points=10,
            lap_lost_points=10,
            scored_unit=unit,
        )
    if style == "snowball":
        table = tuple(
            tuple(rng.randint(0, 10) for _ in range(rng.randint(1, 5))) for _ in range(count)
        )
        return SprintPointsRules(
            sprint_count=count,
            points_by_sprint=table,
            lap_gained_points=rng.randint(0, 30),
            lap_lost_points=rng.randint(0, 30),
            scored_unit=unit,
        )
    inter = tuple(rng.randint(0, 12) for _ in range(rng.randint(1, 6)))
    final = (
        tuple(2 * v for v in inter)
        if rng.random() < 0.5
        else tuple(rng.randint(0, 20) for _ in range(rng.randint(1, 6)))
    )
    return SprintPointsRules(
        sprint_count=count,
        intermediate_points=inter,
        final_points=final,
        lap_gained_points=rng.randint(0, 30),
        lap_lost_points=rng.randint(0, 30),
        tie_break="none" if style == "none" else "final_sprint",
        scored_unit=unit,
    )


def gen_sprint_points(fmt):
    def gen(rng, stats, entrants=None):
        rules = sprint_rules(rng, fmt)
        entrants = list(entrants) if entrants is not None else entrants_for(rng)
        log = Log(fmt, rules, entrants, stats)
        racing = list(entrants)
        gone = []
        count = rules.sprint_count

        def margin(sprint_no):
            for _ in range(rng.choice((0, 0, 1, 1, 2, 3))):
                r = rng.random()
                if r < 0.1:
                    withdraw_step(rng, log, racing, gone)
                    continue
                r = (r - 0.1) / 0.9
                if r < 0.3 and racing:
                    who = rng.sample(racing, rng.randint(1, min(3, len(racing))))
                    at = sprint_no if rng.random() < 0.3 else None
                    log.add(LapGained(who, sprint_no=at))
                elif r < 0.55 and racing:
                    who = rng.sample(racing, rng.randint(1, min(3, len(racing))))
                    log.add(LapLost(who))
                elif r < 0.65 and racing:
                    log.add(LapNotCounted(rng.sample(racing, 1)))
                elif r < 0.8 and len(racing) > 1:
                    got = status_mark(rng, log, racing)
                    if got:
                        racing.remove(got[0])
                elif r < 0.88 and racing:
                    status_mark(rng, log, [e for e in entrants if e not in racing] or racing)
                elif racing:
                    log.add(
                        PointsAdjusted(rng.choice(entrants), rng.choice((-1, -2, -5, -20, 1, 2, 5)))
                    )

        def sprint_line(places_awarded):
            # The scoring places, with ties, sometimes fewer than awarded,
            # sometimes more than awarded, sometimes with a rider not racing.
            depth = places_awarded
            r = rng.random()
            if r < 0.25:
                depth = rng.randint(0, max(0, places_awarded - 1))
            elif r < 0.5:
                depth = places_awarded + rng.randint(1, 3)
            pool = list(racing)
            if rng.random() < 0.05 and len(entrants) > len(racing):
                pool = list(entrants)
            full = line(rng, pool, omit=0)
            out = []
            n = 0
            for g in full:
                if n >= depth:
                    break
                out.append(g)
                n += len(g)
            return out

        stop_at = count if rng.random() < 0.85 else rng.randint(0, count)
        for n in range(1, min(stop_at, count - 1) + 1):
            margin(n)
            table = sprint_table_len(rules, n)
            log.add(SprintResult(n, sprint_line(table)))
            if rng.random() < 0.05:
                # the same sprint entered again (a correction)
                log.add(SprintResult(n, sprint_line(table)))
        if stop_at < count:
            return fmt, rules, entrants, log.actions
        margin(count)
        # Out of the finish during the final sprint
        if racing and rng.random() < 0.15:
            e = rng.choice(racing)
            if log.add(OutOfFinish(e)):
                racing.remove(e)
                if rng.random() < 0.2:
                    # refused: a rider out of the finish is placed on points
                    log.add(Withdrawn(e))
        if gone and rng.random() < 0.05:
            # refused: a withdrawn rider is placed by the moment
            log.add(OutOfFinish(rng.choice(gone)))
        if rng.random() < 0.08:
            # a status during the final
            got = status_mark(rng, log, racing)
            if got:
                racing.remove(got[0])
        finish = line(rng, racing, omit=0.2)
        if rng.random() < 0.4:
            # The final sprint on its own first: usually the head of the
            # same line, now and then a different order to see what the
            # engine does with a disagreement.
            if rng.random() < 0.85:
                depth = rng.randint(0, len(finish))
                head = finish[:depth]
            else:
                head = sprint_line(sprint_table_len(rules, count))
            log.add(SprintResult(count, head))
            if rng.random() < 0.15:
                return fmt, rules, entrants, log.actions
        log.add(FinishOrder(finish))
        for _ in range(rng.choice((0, 0, 1, 2))):
            r = rng.random()
            if r < 0.4 and racing:
                status_mark(rng, log, entrants, ("DQ", "DNF", "DNS", "DNP"))
            elif r < 0.7:
                log.add(PointsAdjusted(rng.choice(entrants), rng.choice((-1, -3, -20, 1, 3))))
            elif racing:
                log.add(LapNotCounted(rng.sample(racing, 1)))
        return fmt, rules, entrants, log.actions

    return gen


def sprint_table_len(rules, sprint_no):
    if rules.points_by_sprint is not None:
        return len(rules.points_by_sprint[sprint_no - 1])
    if sprint_no == rules.sprint_count:
        return len(rules.final_points)
    return len(rules.intermediate_points)


# ---- elimination


def gen_elimination(rng, stats, entrants=None):
    entrants = list(entrants) if entrants is not None else entrants_for(rng)
    survivors = rng.randint(1, min(4, len(entrants)))
    rules = EliminationRules(
        survivors=survivors, final_by_sprint=survivors > 1 and rng.random() < 0.85
    )
    fmt = "elimination"
    log = Log(fmt, rules, entrants, stats)
    still_in = list(entrants)
    sprint_no = 0
    guard = 0
    while len(still_in) > survivors and guard < 200:
        guard += 1
        if rng.random() < 0.04:
            return fmt, rules, entrants, log.actions
        if rng.random() < 0.03:
            # refused: a rider who leaves is clicked out (R-ELIM-7)
            log.add(Withdrawn(rng.choice(still_in)))
        r = rng.random()
        if r < 0.15:
            pool = list(entrants)
            eid = rng.choice(pool)
            code = "DNF" if eid in still_in and rng.random() < 0.6 else rng.choice(CODES)
            if log.add(Status(eid, code, "")) and eid in still_in:
                still_in.remove(eid)
            continue
        if r < 0.2:
            log.add(LapGained(rng.sample(still_in, 1)))
            continue
        if rng.random() < 0.85 or sprint_no == 0:
            sprint_no += 1
        if r < 0.27:
            log.add(Eliminated(sprint_no, []))
            continue
        take = 1 if rng.random() < 0.8 else rng.randint(2, 3)
        who = rng.sample(still_in, min(take, len(still_in)))
        if log.add(Eliminated(sprint_no, who)):
            for e in who:
                still_in.remove(e)
    if rng.random() < 0.1 and still_in:
        # a DNF after the last bell
        eid = rng.choice(still_in)
        if log.add(Status(eid, "DNF", "")):
            still_in.remove(eid)
    if rng.random() < 0.9 and still_in:
        log.add(FinishOrder(line(rng, still_in, omit=0.2)))
        if rng.random() < 0.15:
            status_mark(rng, log, entrants, ("DQ", "DNF", "DNS"))
    return fmt, rules, entrants, log.actions


# ---- win-and-out


def gen_win_and_out(rng, stats):
    entrants = entrants_for(rng)
    rules = WinAndOutRules(
        places=rng.randint(1, min(5, len(entrants))),
        direction=rng.choice(("forward", "reverse")),
    )
    fmt = "win_and_out"
    log = Log(fmt, rules, entrants, stats)
    racing = list(entrants)
    winners = []
    for lap in range(1, rules.places + 1):
        if rng.random() < 0.08:
            break
        if rng.random() < 0.12:
            got = status_mark(rng, log, racing)
            if got:
                racing.remove(got[0])
        if winners and rng.random() < 0.12:
            # a lap winner marked after the fact
            status_mark(rng, log, winners, ("DNF", "DQ", "DNS"))
        if not racing:
            break
        if rng.random() < 0.04:
            # refused: a Win-and-Out has no rule for a withdrawal
            log.add(Withdrawn(rng.choice(racing)))
        n_win = 2 if rng.random() < 0.08 and len(racing) > 1 else 1
        group = rng.sample(racing, n_win)
        behind = rng.sample(
            [e for e in racing if e not in group], rng.randint(0, min(3, len(racing) - n_win))
        )
        places = [group, *[[e] for e in behind]]
        if log.add(SprintResult(lap, places)):
            for e in group:
                racing.remove(e)
                winners.append(e)
        if rng.random() < 0.04:
            log.add(SprintResult(lap, [[rng.choice(racing or entrants)]]))
    if rng.random() < 0.85:
        log.add(FinishOrder(line(rng, racing)))
        if rng.random() < 0.2:
            status_mark(rng, log, entrants, ("DQ", "DNF", "DNS"))
    return fmt, rules, entrants, log.actions


GENERATORS = {
    "placings": gen_placings,
    "points": gen_sprint_points("points"),
    "madison": gen_sprint_points("madison"),
    "tempo": gen_sprint_points("tempo"),
    "elimination": gen_elimination,
    "win_and_out": gen_win_and_out,
}


def generate(family, seed, stats, entrants=None):
    rng = random.Random(f"{family}:{seed}")
    if entrants is None:
        return GENERATORS[family](rng, stats)
    return GENERATORS[family](rng, stats, entrants)
