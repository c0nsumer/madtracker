"""A sample venue seeded into a real store, for ``--demo`` and the wiring tests.

Unlike ``madtracker.board.sample``, which is pictures, this is live data:
riders, rosters, races with rules and teams, so the demo exercises
exactly the code a race night does. All names are invented and come
from the board sample so the two stay recognizably the same night.

Two nights with the same program, a race of every format:

- "Demo Race Night" (the date given, today by default) is the one the
  app opens, with nothing scored, for exploring how each format scores.
- "Demo Opening Night", the day before, has every race scored and
  final, for the results pages, the PDF, and the USAC CSV. It carries
  each entry a night can need beside the placings, where a scorer
  would meet it: a lap gained, a lap not counted, a DNS, a DNF, a DQ
  after the finish, a points penalty, a rider out of the finish
  (mishap), withdrawn riders in the Scratch Race and the Tempo Race,
  a Points Race shortened, and a Madison ended with its result as-is.

The roster is Group A, Group B, and three riders with no group; the
Keirin Final and the Chariot take riders from outside their group.
Both nights run two Madisons with five teams. Four teams are the same
pairs both nights and the fifth is not (Green the first night, Black
tonight), so once tonight's Madisons are raced the multi-race standings
over both nights, "Demo 2 Day Omnium", leaves out the two teams that
rode one night of two. Two more standings cover both nights for the
riders: "Demo Rider Omnium", an Omnium by Place over every race but
the Madisons, and "Demo Four-Race Omnium", the Four-Race Omnium over
Group B's Scratch Race, Tempo Race, Miss-and-Out, and Points Race
(Group A's Eliminations left out, since Group A runs no other of the
four), with a 40-point Omnium Penalty on one rider, so the Penalty
column and the provisional half-raced weekend are there to see.

The races score under a stored ruleset, "Demo house rules", that the
seed writes into its own database and sets as the default: a lap worth
10 and a points race awarding 10-7-5-3-2-1 with double points for the last sprint.
Those are club-style values rather than the rulebook's, so the demo
looks like a club night; the venue's own ruleset is a file it imports,
not something the code knows.
"""

import random
from datetime import date, timedelta

from madtracker.board import sample
from madtracker.control import multi_race, rulesets
from madtracker.control.formats import TEAM_COLORS
from madtracker.scoring import RULES_VERSION
from madtracker.store import Store

DEMO_RULESET = "Demo house rules"
SPARE_RIDER = "Walt Mercer"
OPENING_NIGHT = "Demo Opening Night"
DEMO_STANDINGS = "Demo 2 Day Omnium"
DEMO_RIDER_STANDINGS = "Demo Rider Omnium"
DEMO_FOUR_RACE_STANDINGS = "Demo Four-Race Omnium"
# The rider the Four-Race Omnium's penalty is on: withdrawn two laps
# down in the opening night's Scratch Race, as the rulebook has it
# (USAC 2O3(e)).
PENALTY_BIB = "7"
PENALTY_POINTS = 40

# Bib, name: on both rosters with no group, as a guest or a rider not yet
# placed in one would be.
NO_GROUP = [("60", "Felix Arango"), ("61", "Wren Castillo"), ("62", "Gus Lindgren")]
# The opening night's fifth Madison team: two Group A riders who do not
# pair up tonight, so the omnium has a team short of a night.
OPENING_TEAM = ("Green", "17", "42")


def seed_demo_ruleset(store: Store) -> str:
    """Store the demo ruleset if it is not there yet and make it the default."""
    if store.ruleset_by_name(DEMO_RULESET) is None:
        doc = rulesets.apply_values(
            rulesets.builtin_ruleset(), points_table=(10, 7, 5, 3, 2, 1), lap_points=10
        )
        doc["name"] = DEMO_RULESET
        rulesets.save_ruleset(store, doc)
    rulesets.set_default_ruleset(store, DEMO_RULESET)
    return DEMO_RULESET


def seed_demo(store: Store, event_date: str | None = None) -> int:
    """Create the demo event, the night before it, and the omnium over both; return the event_id.

    The returned event is the one the app opens: it is the later of the
    two, so it is also first in the event list. The seed is one write:
    on its own each rider, race, team, and scored action would be a
    commit and an fsync, over five hundred of them, which is seconds on
    a laptop disk with a virus scanner watching the folder, and the
    demo is built every time Help > Demo Data File makes a new one.
    """
    with store.transaction():
        return _seed(store, event_date)


def _seed(store: Store, event_date: str | None) -> int:
    ruleset = seed_demo_ruleset(store)
    event = store.add_event(
        sample.EVENT_NAME, event_date or date.today().isoformat(), venue=sample.VENUE_NAME
    )
    mid = event.event_id
    ids: dict[str, int] = {}
    for group, field in (("Group A", sample.GROUP_A), ("Group B", sample.GROUP_B)):
        for bib, name in field:
            first, last = name.split(" ", 1)
            # The group is a roster fact for this event, not the rider's.
            # Two birth years, so the roster's age column has something to show.
            born = {"3": 1998, "7": 2008}.get(bib)
            rider = store.add_rider(first, last, birth_year=born)
            store.add_entry(mid, rider.rider_id, int(bib), local_group=group)
            ids[bib] = rider.rider_id

    # Someone on no event's roster, so the Riders window has a rider Delete
    # works on.
    store.add_rider(*SPARE_RIDER.split(" ", 1), birth_year=1979)
    # After the spare, so the riders above keep the ids the mockups and
    # the walk were written against.
    for bib, name in NO_GROUP:
        rider = store.add_rider(*name.split(" ", 1))
        store.add_entry(mid, rider.rider_id, int(bib))
        ids[bib] = rider.rider_id

    def race(name, fmt, group, bibs, event_id, **overrides):
        rules = rulesets.rules_for(store, ruleset, fmt, **overrides)
        r = store.add_race(
            event_id,
            name,
            fmt,
            group_label=group,
            # What the race editor saves for a blank Category.
            usac_category=group,
            rules_preset=ruleset,
            rules=rules.to_dict(),
            rules_version=RULES_VERSION,
        )
        for bib in bibs:
            store.add_race_entry(r.race_id, ids[bib])
        return r.race_id

    def program(event_id: int, teams: list[tuple[str, str, str]]) -> list[int]:
        """The night's races in program order; both nights run the same one."""
        a = [bib for bib, _ in sample.GROUP_A]
        b = [bib for bib, _ in sample.GROUP_B]

        def madison(name: str, sprints: int) -> int:
            field = [bib for _, x, y in teams for bib in (x, y)]
            mad = race(name, "madison", "Group A", field, event_id, sprint_count=sprints)
            for color, x, y in teams:
                team = store.add_team(mad, color, color=color, color_hex=TEAM_COLORS[color])
                store.add_team_member(team.team_id, ids[x])
                store.add_team_member(team.team_id, ids[y])
            return mad

        no_laps = {"laps_count_for_ranking": False}
        return [
            race("2 Mile Chase", "chase", "Group B", b, event_id),
            race("Elimination", "elimination", "Group A", a, event_id),
            # The sample sheet's three-sprint points race and four-sprint madison.
            race("6 Mile Points", "points", "Group B", b, event_id, sprint_count=3),
            madison("8 Mile Madison", 4),
            race("Win-and-Out", "win_and_out", "Group B", b, event_id, places=5),
            # A second madison, so a night with two team races is exercised.
            madison("4 Mile Madison", 2),
            race("Handicap", "handicap", "Group B", b, event_id),
            # The rest of the formats after these, so the rows above keep
            # their places in the mockups and the walk.
            race("4 Mile Tempo", "tempo", "Group B", b, event_id, sprint_count=3),
            race("Sprint Final", "match_sprint", "Group B", b[:4], event_id, **no_laps),
            # Riders from outside the race's group: one with no group in
            # the Keirin, and one from Group A and two with no group in the
            # Chariot.
            race("Keirin Final", "keirin", "Group A", [*a[:5], "62"], event_id, **no_laps),
            race("Chariot", "chariot", "Group B", [*b[:5], "42", "60", "61"], event_id, **no_laps),
            # The whole of Group B, so it walks the Scratch Race's steps.
            race("Unknown Distance", "unknown_distance", "Group B", b, event_id),
            # Group B's Elimination, under the name USAC 2E5 also gives it,
            # so Group B has the Four-Race Omnium's four races.
            race("Miss-and-Out", "elimination", "Group B", b, event_id),
        ]

    program(mid, list(sample.MADISON_TEAMS))
    _seed_opening_night(store, event, program)
    return mid


def _seed_opening_night(store: Store, event, program) -> None:
    """The night before: the same roster and program, every race scored and final.

    Made after tonight's races so tonight's riders and races keep the
    ids the mockups and the walk were written against.
    """
    from madtracker.control.race import LiveRace

    day_before = (date.fromisoformat(event.event_date) - timedelta(days=1)).isoformat()
    opening = store.add_event(OPENING_NIGHT, day_before, venue=sample.VENUE_NAME)
    for entry in store.entries(event.event_id):
        store.add_entry(opening.event_id, entry.rider_id, entry.bib, entry.local_group)
    teams = [*sample.MADISON_TEAMS[:4], OPENING_TEAM]
    race_ids = program(opening.event_id, teams)
    # One seed for the night, so every run scores it the same way.
    rng = random.Random(1016)
    for race_id in race_ids:
        live = LiveRace(store, race_id)
        _extras(live)
        _play(live, rng)
    nights = [opening.event_id, event.event_id]
    standings = store.add_standings(DEMO_STANDINGS)
    store.update_standings(standings.standings_id, event_ids=nights)
    riders = store.add_standings(DEMO_RIDER_STANDINGS, kind=multi_race.OMNIUM)
    store.update_standings(riders.standings_id, event_ids=nights)
    four = store.add_standings(DEMO_FOUR_RACE_STANDINGS, kind=multi_race.FOUR_RACE)
    # Group A's Eliminations are left out: Group A runs none of the other three.
    group_a = [
        r.race_id
        for night in nights
        for r in store.races(night)
        if r.format == "elimination" and r.group_label == "Group A"
    ]
    store.update_standings(four.standings_id, event_ids=nights, excluded_race_ids=group_a)
    (penalized,) = [
        e.rider_id for e in store.entries(opening.event_id) if e.bib == int(PENALTY_BIB)
    ]
    store.set_standings_penalty(four.standings_id, penalized, PENALTY_POINTS)


def _do(outcome) -> None:
    # A seed that scores wrong would show a half-scored night; fail loudly.
    if not outcome.ok:
        raise RuntimeError(f"demo scoring refused: {outcome.message}")


def _extras(live) -> None:
    """What a night has besides placings, entered before the first click:
    a lap, a lap taken back, a DNF, a DNS, a withdrawal, a penalty."""
    by_name = {live.name(e): e for e in live.roster.ids}
    name = live.race.name
    if name == "6 Mile Points":
        _do(live.act(by_name["Tess Gallagher"], "lap_gained"))
    elif name == "2 Mile Chase":
        _do(live.act(by_name["Isaac Pell"], "dnf"))
        # Pulled two laps down before anyone finishes: the next place after
        # every finisher, and the Four-Race Omnium's penalty on the same
        # rider (USAC 2O3(e)).
        (pulled,) = [e for e in live.roster.ids if live.entry(e).bibs == [PENALTY_BIB]]
        _do(live.act(pulled, "withdrawn"))
    elif name == "8 Mile Madison":
        _do(live.act(by_name["Blue"], "lap_gained"))
        _do(live.act(by_name["Red"], "points_penalty:2"))
    elif name == "4 Mile Madison":
        _do(live.act(by_name["Orange"], "lap_gained"))
    elif name == "Unknown Distance":
        # A lap the officials then rule out, so a sheet shows the note.
        _do(live.act(by_name["Omar Rahimi"], "lap_gained"))
        _do(live.act(by_name["Omar Rahimi"], "lap_not_counted"))
    elif name == "Keirin Final":
        _do(live.act(by_name["Luis Ferreira"], "dns"))


def _moment(live, st, task, done: set[str]) -> bool:
    """An entry made partway through a race, once, at the point it needs;
    True when one was made, so the caller reads the race again.

    Each waits on what is recorded, never on the shuffle, so the night
    stays the same on every run.
    """
    name = live.race.name
    ridden = st.next_sprint_no - 1 if task.kind in ("sprint", "final_sprint") else None
    fresh = not any(live.staged(st))

    def rider(who: str) -> int:
        return next(e for e in live.roster.ids if live.name(e) == who)

    moments = []
    if name == "6 Mile Points" and fresh:
        # Shortened after the first sprint, so the second is the doubled
        # final, and a crash in it: placed on points (USAC 2M8(a)).
        if ridden == 1 and task.kind == "sprint":
            moments.append(("shorten", lambda: live.shorten_race(2)))
        if task.kind == "final_sprint":
            moments.append(("mishap", lambda: live.act(rider("Lena Fischer"), "out_of_finish")))
    elif name == "8 Mile Madison" and fresh and ridden == 2:
        moments.append(("end", live.end_race))
    elif name == "4 Mile Tempo" and fresh and ridden in (1, 2):
        # Two withdrawals a sprint apart, so the later one ranks higher.
        who = {1: "Jack Moreau", 2: "Rosa Navarro"}[ridden]
        moments.append((f"withdrawn {who}", lambda: live.act(rider(who), "withdrawn")))
    elif name == "Handicap" and task.kind == "review":
        # Disqualified after the finish, as a protest would be, so the
        # riders below move up a place.
        (second,) = [r.entrant_id for r in st.rows if r.rank == 2]
        moments.append(("dq", lambda: live.act(second, "dq")))
    for key, make in moments:
        if key not in done:
            done.add(key)
            _do(make())
            return True
    return False


def _play(live, rng: random.Random) -> None:
    """Score the race to the end the way the surface does, then mark it final.

    Each race gets one shuffled order of its field, its form for the
    night, and each sprint or finish jostles that order a little, so
    the strong riders usually lead without winning every sprint.
    """
    form = list(live.roster.ids)
    rng.shuffle(form)
    rank = {e: i for i, e in enumerate(form)}
    order: dict[int, float] = {}
    done: set[str] = set()
    for _ in range(10 * len(form) + 50):
        st = live.standings()
        task = live.task(st)
        if _moment(live, st, task, done):
            continue
        if task.kind in ("review", "final", "none"):
            break
        staged = {e for group in live.staged(st) for e in group}
        if not staged:
            # A new sprint or step: a new jostle, kept until it is recorded.
            order = {e: rank[e] + rng.uniform(0, 6) for e in form}
        # A rider withdrawn or out of the finish is no longer in the field
        # to click.
        gone = {r.entrant_id for r in st.rows if r.withdrawn or r.out_of_finish}
        field = [e for e in st.remaining_entrants if e not in gone]
        left = sorted((e for e in field if e not in staged), key=order.__getitem__)
        if task.kind == "sprint":
            places = live.scoring_places(task.sprint_no) or 1
            if len(staged) >= min(places, len(field)):
                _do(live.record_sprint())
                continue
        _do(live.click(left[-1] if task.kind == "out" else left[0]))
    _do(live.mark_final())
