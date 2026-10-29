"""Random seasons for the multi-race oracle, scored through LiveRace.

A season is riders, one to four events with shuffled bibs and rosters,
a program per event, and one multi-race standings over some of the
events. Every race is scored the way the surface scores it (clicks,
Record Sprint, statuses, laps, penalties, ties, Mark Final), so the log
is a real log. Some races are left in setup, some running, some
provisional, some final. The generator is deterministic by seed.

Nothing here reads madtracker.control.multi_race: the generator only
needs the kind keys, which are spelled out below.

Usage from code: ``build(store, seed) -> Season``.
"""

import random
from collections import Counter
from dataclasses import dataclass, field

from madtracker.control.race import LiveRace
from madtracker.scoring import rules as R
from madtracker.store import Store

TOTALS = "team_omnium"
PLACES = "team_omnium_places"
OMNIUM = "omnium_places"
FOUR_RACE = "four_race_omnium"
KINDS = (TOTALS, PLACES, OMNIUM, FOUR_RACE)
TEAM_KINDS = (TOTALS, PLACES)

# Invented names only.
FIRST = [
    "Ada", "Bram", "Cleo", "Dov", "Esme", "Finn", "Gus", "Hana", "Ivo", "Juno",
    "Kit", "Lior", "Mira", "Nils", "Orla", "Pim", "Quin", "Rue", "Sol", "Tove",
    "Uma", "Vik", "Wren", "Xan", "Yael", "Zed",
]  # fmt: skip
LAST = ["Arden", "Birch", "Corso", "Dunmore", "Ellery", "Faro", "Grieg", "Holm"]
COLORS = [
    "Red", "Blue", "Green", "Black", "White", "Yellow", "Orange", "Purple",
    "Pink", "Silver", "Stars", "Teal", "Gold", "Violet",
]  # fmt: skip
# "Cat 3", "cat 3" and "CAT3" are one group (no spaces, case folded); "" is No Group.
GROUPS = ["Pro", "Cat 3", "cat 3", "CAT3", "Women", "", "SemiPro A"]
RIDER_FORMATS = ["chase", "tempo", "elimination", "points", "handicap", "keirin"]
FOUR = ("chase", "tempo", "elimination", "points")
STATES = ("setup", "running", "provisional", "final")


@dataclass
class Season:
    seed: int
    kind: str
    standings_id: int
    event_ids: list[int]
    race_ids: list[int]
    stats: Counter = field(default_factory=Counter)


def _ok(out) -> bool:
    return bool(out.ok)


def _want_state(rng, mode: str = "mixed") -> str:
    """A race's wanted state; an "all-final" season asks for final every time."""
    if mode == "all-final":
        return "final"
    r = rng.random()
    if r < 0.08:
        return "setup"
    if r < 0.20:
        return "running"
    if r < 0.35:
        return "provisional"
    return "final"


# ----- scoring one race ------------------------------------------------------


def _pre_statuses(live, rng, ids, stats, *, dns=0.06, dnf=0.03, dq=0.02):
    marked = {}
    for eid in ids:
        r = rng.random()
        if r < dns:
            key = "dns"
        elif r < dns + dnf:
            key = "dnf"
        elif r < dns + dnf + dq:
            key = "dq"
        else:
            continue
        if _ok(live.act(eid, key)):
            marked[eid] = key
            stats[f"status:{key}"] += 1
    return marked


def _alive(live, ids):
    st = live.standings()
    out = []
    for eid in ids:
        try:
            if st.by_entrant(eid).status is None:
                out.append(eid)
        except KeyError:
            pass
    return out


def score_placings(live, rng, want, stats) -> None:
    ids = list(live.roster.ids)
    rng.shuffle(ids)
    marked = _pre_statuses(live, rng, ids, stats)
    if want == "setup":
        return
    rest = [e for e in ids if e not in marked]
    complete = want in ("provisional", "final")
    k = len(rest) if complete else rng.randint(0, max(0, len(rest) - 1))
    placed = 0
    for eid in rest[:k]:
        if _ok(live.click(eid)):
            placed += 1
            if placed > 1 and rng.random() < 0.15 and _ok(live.act(eid, "tie_above")):
                stats["tie"] += 1
    if complete:
        if not live.standings().is_complete:
            live.place_rest_together()
        if want == "final" and live.standings().is_complete and _ok(live.mark_final()):
            stats["final"] += 1


def score_elimination(live, rng, want, stats) -> None:
    ids = list(live.roster.ids)
    rng.shuffle(ids)
    marked = _pre_statuses(live, rng, ids, stats, dnf=0.0, dq=0.01)
    if want == "setup":
        return
    rest = [e for e in ids if e not in marked]
    complete = want in ("provisional", "final")
    n_out = max(0, len(rest) - 2)
    if not complete:
        n_out = rng.randint(0, n_out)
    for eid in rest[:n_out]:
        if rng.random() < 0.12 and _ok(live.act(eid, "dnf")):
            stats["elimination-dnf"] += 1
            continue
        live.click(eid)
    if complete:
        alive = _alive(live, rest)
        if alive:
            live.click(rng.choice(alive))
        if not live.standings().is_complete:
            for eid in _alive(live, rest):
                live.click(eid)
        if want == "final" and live.standings().is_complete and _ok(live.mark_final()):
            stats["final"] += 1


def score_sprints(live, rng, want, stats, n_sprints: int) -> None:
    ids = list(live.roster.ids)
    rng.shuffle(ids)
    marked = _pre_statuses(live, rng, ids, stats, dnf=0.0)
    if want == "setup":
        return
    rest = [e for e in ids if e not in marked]
    complete = want in ("provisional", "final")
    stop_after = n_sprints if complete else rng.randint(0, n_sprints)
    for s in range(1, n_sprints + 1):
        if s > stop_after:
            break
        is_final = s == n_sprints
        for eid in _alive(live, rest):
            r = rng.random()
            if r < 0.05:
                if _ok(live.act(eid, "lap_gained")):
                    stats["lap_gained"] += 1
            elif r < 0.09:
                if _ok(live.act(eid, "lap_lost")):
                    stats["lap_lost"] += 1
            elif r < 0.11:
                if _ok(live.act(eid, "dnf")):
                    stats["status:dnf-mid"] += 1
            elif r < 0.13:
                if _ok(live.act(eid, f"points_penalty:{rng.randint(1, 6)}")):
                    stats["points_penalty"] += 1
        alive = _alive(live, rest)
        rng.shuffle(alive)
        if is_final and complete:
            picks = alive
        elif is_final:
            picks = alive[: rng.randint(0, max(0, len(alive) - 1))]
        else:
            picks = alive[: rng.randint(1, min(len(alive), 5))] if alive else []
        n = 0
        for eid in picks:
            if _ok(live.click(eid)):
                n += 1
                if n > 1 and rng.random() < 0.10 and _ok(live.act(eid, "tie_above")):
                    stats["tie"] += 1
        if not is_final:
            live.record_sprint()
    if complete:
        if not live.standings().is_complete:
            for eid in _alive(live, rest):
                live.click(eid)
        if want == "final" and live.standings().is_complete and _ok(live.mark_final()):
            stats["final"] += 1


def score(live, rng, want, stats) -> None:
    fmt = live.format_key
    stats[f"want:{want}"] += 1
    if fmt in ("chase", "handicap", "keirin", "unknown_distance", "chariot"):
        score_placings(live, rng, want, stats)
    elif fmt == "elimination":
        score_elimination(live, rng, want, stats)
    else:
        n = getattr(live.rules, "sprint_count", None) or 1
        score_sprints(live, rng, want, stats, n)


# ----- building a season -----------------------------------------------------


def _rules(fmt: str, rng):
    if fmt in ("chase", "handicap", "keirin"):
        return R.placings_rules()
    if fmt == "elimination":
        return R.elimination_rules()
    if fmt == "points":
        return R.points_race_rules(sprint_count=rng.randint(1, 4))
    if fmt == "tempo":
        return R.tempo_rules(sprint_count=rng.randint(1, 4))
    if fmt == "madison":
        return R.madison_rules(sprint_count=rng.randint(1, 3))
    raise ValueError(fmt)


def _race(store, event_id, name, fmt, group, rng):
    return store.add_race(event_id, name, fmt, group_label=group, rules=_rules(fmt, rng).to_dict())


def _rider_race(store, event_id, fmt, group, field_ids, rng, stats, mode="mixed") -> int:
    # The store wants a name; the UI stores a blank one as group plus format.
    name = rng.choice([f"{group} {fmt}".strip() or fmt, "Feature", "Heat 2", "A" * 40])
    race = _race(store, event_id, name, fmt, group, rng)
    for rid in field_ids:
        store.add_race_entry(race.race_id, rid)
    live = LiveRace(store, race.race_id)
    score(live, rng, _want_state(rng, mode), stats)
    return race.race_id


def _madison(store, event_id, group, pairs, rng, stats, mode="mixed") -> int:
    race = _race(store, event_id, f"{group} Madison".strip(), "madison", group, rng)
    colors = COLORS[:]
    rng.shuffle(colors)
    for i, pair in enumerate(pairs):
        for rid in pair:
            store.add_race_entry(race.race_id, rid)
        color = colors[i % len(colors)]
        # A team name is unique within a race: past the palette the name carries a number.
        made = store.add_team(
            race.race_id,
            color if rng.random() < 0.8 and i < len(colors) else f"Team {color} {i}",
            color=color,
            color_hex=rng.choice([None, "#ff0000", "#00ff00"]),
        )
        for rid in pair:
            store.add_team_member(made.team_id, rid)
    live = LiveRace(store, race.race_id)
    score(live, rng, _want_state(rng, mode), stats)
    return race.race_id


def build(store: Store, seed: int, kind: str | None = None) -> Season:
    """A season in ``store`` from ``seed``; the standings' kind is random unless given."""
    rng = random.Random(seed)
    stats: Counter = Counter()
    kind = kind or rng.choice(KINDS)
    stats[f"kind:{kind}"] += 1
    # A third of seasons are scored to the end, so the Final state and
    # full tables get their share.
    mode = "all-final" if rng.random() < 0.33 else "mixed"
    stats[f"mode:{mode}"] += 1
    n_riders = rng.randint(6, 34)
    riders = [
        store.add_rider(
            FIRST[i % len(FIRST)], f"{LAST[i % len(LAST)]}{i // len(LAST) or ''}"
        ).rider_id
        for i in range(n_riders)
    ]
    # Pairs for the Madisons: a pool that mostly repeats from night to night.
    pool = riders[:]
    rng.shuffle(pool)
    pairs = [tuple(pool[i : i + 2]) for i in range(0, len(pool) - 1, 2)]
    n_events = rng.randint(1, 4)
    dates = sorted(rng.sample(range(1, 28), n_events))
    events = []
    race_ids = []
    with store.transaction():
        for n, day in enumerate(dates):
            event = store.add_event(f"Night {n + 1}", f"2026-{rng.choice(['09', '10'])}-{day:02d}")
            events.append(event.event_id)
            # The roster: most riders, bibs shuffled each night so a rider's
            # bib changes between events.
            roster = [r for r in riders if rng.random() < 0.85] or riders[:3]
            bibs = list(range(1, len(roster) + 1))
            rng.shuffle(bibs)
            for rid, bib in zip(roster, bibs, strict=True):
                store.add_entry(event.event_id, rid, bib, local_group=rng.choice(GROUPS) or None)
            on_roster = set(roster)
            if rng.random() < (0.03 if kind == FOUR_RACE else 0.08):
                stats["empty-event"] += 1
                continue
            groups = rng.sample(GROUPS, rng.randint(1, 3))
            if kind == FOUR_RACE and rng.random() < 0.9:
                # Two spellings of one group on a night double its formats:
                # a refusal, kept as a rare edge rather than the usual case.
                seen, distinct = set(), []
                for g in groups:
                    k = "".join(g.split()).casefold()
                    if k not in seen:
                        seen.add(k)
                        distinct.append(g)
                groups = distinct
            for group in groups:
                if kind in TEAM_KINDS:
                    night_pairs = [p for p in pairs if rng.random() < 0.8 and set(p) <= on_roster]
                    if rng.random() < 0.25 and night_pairs:
                        # One pair changes a rider: another team.
                        i = rng.randrange(len(night_pairs))
                        spare = [r for r in roster if not any(r in p for p in night_pairs)]
                        if spare:
                            night_pairs[i] = (night_pairs[i][0], rng.choice(spare))
                            stats["pair-swapped"] += 1
                    if len(night_pairs) < 2:
                        night_pairs = [p for p in pairs if set(p) <= on_roster][:3]
                    if len(night_pairs) < 2:
                        continue
                    for _ in range(1 if rng.random() < 0.8 else 2):
                        race_ids.append(
                            _madison(store, event.event_id, group, night_pairs, rng, stats, mode)
                        )
                    if rng.random() < 0.3:
                        # A rider race the team kinds must ignore.
                        fld = rng.sample(roster, min(len(roster), rng.randint(3, 8)))
                        race_ids.append(
                            _rider_race(
                                store, event.event_id, "chase", group, fld, rng, stats, mode
                            )
                        )
                else:
                    if kind == FOUR_RACE:
                        formats = list(FOUR)
                        rng.shuffle(formats)
                        r = rng.random()
                        if r < 0.05:
                            formats.remove(rng.choice(formats))
                            stats["four-missing"] += 1
                        elif r < 0.09:
                            formats.append(rng.choice(FOUR))
                            stats["four-doubled"] += 1
                    else:
                        formats = [rng.choice(RIDER_FORMATS) for _ in range(rng.randint(1, 5))]
                    if rng.random() < 0.25:
                        formats.insert(rng.randrange(len(formats) + 1), "madison")
                    # The group's riders: one field, so the omnium's four see
                    # mostly the same riders, with some in and out per race.
                    # Now and then a field past 20, so 21st and below score
                    # 1 in the Four-Race Omnium (R-OMNI-1).
                    most = rng.randint(21, 26) if rng.random() < 0.15 else rng.randint(3, 12)
                    core = rng.sample(roster, min(len(roster), most))
                    for fmt in formats:
                        if fmt == "madison":
                            ps = [p for p in pairs if set(p) <= on_roster][:4]
                            if len(ps) >= 2:
                                race_ids.append(
                                    _madison(store, event.event_id, group, ps, rng, stats, mode)
                                )
                            continue
                        fld = [r for r in core if rng.random() < 0.9] or core[:3]
                        if rng.random() < 0.2:
                            extra = [r for r in roster if r not in fld]
                            if extra:
                                fld.append(rng.choice(extra))
                        race_ids.append(
                            _rider_race(store, event.event_id, fmt, group, fld, rng, stats, mode)
                        )
        # The standings.
        rules = None
        if kind in (PLACES, OMNIUM) and rng.random() < 0.5:
            r = rng.random()
            if r < 0.15:
                table = [0] * rng.randint(1, 4)
            elif r < 0.3:
                table = [rng.randint(0, 999) for _ in range(rng.randint(15, 30))]
            else:
                table = sorted((rng.randint(1, 20) for _ in range(rng.randint(1, 8))), reverse=True)
            rules = {"points_by_place": table}
            stats["custom-table"] += 1
        standings = store.add_standings(f"Season {seed}", kind=kind, rules=rules)
        ticked = [e for e in events if rng.random() < 0.85]
        if not ticked and rng.random() < 0.7:
            ticked = events[:]
        rng.shuffle(ticked)
        excluded = [r for r in race_ids if rng.random() < (0.03 if kind == FOUR_RACE else 0.12)]
        store.update_standings(standings.standings_id, event_ids=ticked, excluded_race_ids=excluded)
        if excluded:
            stats["excluded"] += len(excluded)
        if kind == FOUR_RACE:
            raced = sorted({e.rider_id for r in race_ids for e in store.race_entries(r)}) or riders
            for _ in range(rng.randint(0, 3)):
                rid = rng.choice(raced if rng.random() < 0.85 else riders)
                pts = rng.choice([40, 40, 1, 999, rng.randint(1, 100)])
                store.set_standings_penalty(standings.standings_id, rid, pts)
                stats["penalty"] += 1
            if rng.random() < 0.3:
                # Set, then taken off again.
                rid = rng.choice(riders)
                store.set_standings_penalty(standings.standings_id, rid, 40)
                store.set_standings_penalty(standings.standings_id, rid, 0)
    return Season(seed, kind, standings.standings_id, events, race_ids, stats)
