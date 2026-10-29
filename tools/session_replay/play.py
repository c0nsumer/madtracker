"""Scoring a race through the window's controls, as the officials call it.

``Player.advance`` takes one step a scorer would take next: a card
clicked, Record Sprint, Mark Final. The messy night adds its scripted
mishaps (``Mishaps``) and, now and then, any control the screen offers,
picked at random (``Player.anything``). Every step goes through
``Session.step``, so the invariants are checked after each one.
"""

from __future__ import annotations

from harness import REC, Session, _Penalty

# A race that takes more steps than this is stuck: a break, not a hang.
MAX_STEPS = 600
# The rarer outcomes weigh less in a random pick, so a messy race still
# has riders left to score.
WEIGHTS = {"dns": 0.15, "dnf": 0.25, "dq": 0.2, "out_of_finish": 0.3, "withdrawn": 0.2}
SPRINT_KINDS = ("points", "madison")


class Player:
    def __init__(self, s: Session) -> None:
        self.s = s
        self.c = s.c
        self.rng = s.rng
        self.form: dict[int, float] = {}
        self.jostle: dict[int, float] = {}

    @property
    def screen(self):
        return self.c.live.screen()

    def name(self, eid: int) -> str:
        return self.c.live.label(eid)

    def begin(self, race_id: int) -> bool:
        """Select the race as the program pane does."""
        c = self.c
        name = next(r.name for r in c.races if r.race_id == race_id)
        ok = self.s.step(
            f"select {name}",
            lambda: c.select_race(race_id) or (c.live is not None and c.live.race_id == race_id),
            undo_check=False,
        )
        if ok:
            ids = list(c.live.roster.ids)
            self.rng.shuffle(ids)
            self.form = {e: i for i, e in enumerate(ids)}
            self.jostle = {}
        return ok

    def _order(self, cards) -> list:
        """The unbadged cards in the order the bunch crosses the line."""

        def key(card):
            e = card.entrant_id
            if e not in self.jostle:
                self.jostle[e] = self.form.get(e, 0) + self.rng.uniform(0, 6)
            return self.jostle[e]

        return sorted(cards, key=key)

    def click(self, card) -> bool:
        c = self.c
        eid = card.entrant_id
        return self.s.step(f"click {self.name(eid)}", lambda: c.click(eid))

    def advance(self) -> bool:
        """One ordinary step; False once the race is final or cannot go on."""
        c = self.c
        sc = self.screen
        task = sc.task
        if task.kind == "final":
            return False
        if task.kind in ("review",) or (sc.mark_final and not task.editing):
            return self.s.step("Mark Final", c.mark_final)
        if task.kind in ("none", "blocked"):
            if sc.mark_final:
                return self.s.step("Mark Final", c.mark_final)
            REC.add("race stuck", f"task {task.kind}: {task.text}")
            return False
        free = [cd for cd in sc.cards if cd.badge is None]
        if not any(cd.badge is not None for cd in sc.cards):
            self.jostle = {}
        if task.kind == "sprint":
            badged = sum(1 for cd in sc.cards if cd.badge is not None)
            if task.editing:
                if sc.record_enabled:
                    return self.s.step("Record Sprint (correction)", c.record_sprint)
                if not free:
                    REC.add("correction cannot be recorded", task.text)
                    return False
                return self.click(self._order(free)[0])
            places = c.live.scoring_places(task.sprint_no) or 1
            left = len(c.live.standings().remaining_entrants)
            if badged >= min(places, left) or not free:
                return self.s.step(f"Record Sprint {task.sprint_no}", c.record_sprint)
            return self.click(self._order(free)[0])
        if not free:
            if sc.rest_together:
                return self.s.step("Place the Rest Together", c.place_rest_together)
            REC.add("no card to click", f"task {task.kind}: {task.text}")
            return False
        if task.kind == "out":
            return self.click(self._order(free)[-1])
        return self.click(self._order(free)[0])

    def finish(self, mishaps: Mishaps | None = None, wild: float = 0.0) -> None:
        """Score the race to Final, with the night's mishaps and random picks."""
        for _ in range(MAX_STEPS):
            if mishaps is not None and mishaps.maybe():
                continue
            if self.screen.task.kind == "final":
                return
            if wild and self.rng.random() < wild:
                self.anything()
                continue
            if not self.advance() and self.screen.task.kind != "final":
                # A refused ordinary step: try a random control, then go on.
                if not self.anything():
                    REC.add("race cannot go on", self.screen.task.text)
                    return
        REC.add("race did not finish", f"{MAX_STEPS} steps; task {self.screen.task.text!r}")

    # Any control the screen offers ---------------------------------------

    def offers(self) -> list[tuple[float, str, object]]:
        """(weight, label, action) for every control on the screen now."""
        c = self.c
        sc = self.screen
        out: list[tuple[float, str, object]] = []
        for card in sc.cards:
            eid = card.entrant_id
            if card.badge is None:
                out.append((1.0, f"click {self.name(eid)}", lambda e=eid: c.click(e)))
            for key, label in card.actions:
                out.append(
                    (
                        WEIGHTS.get(key, 0.6),
                        f"card {self.name(eid)}: {label}",
                        self._rider(eid, key, c.rider_action),
                    )
                )
        for row in sc.rows:
            if row.entrant_id is None:
                continue
            for key, label in row.actions:
                out.append(
                    (
                        WEIGHTS.get(key, 0.6),
                        f"row {self.name(row.entrant_id)}: {label}",
                        self._rider(row.entrant_id, key, c.row_action),
                    )
                )
        for key, label in sc.race_actions:
            out.append((0.3, f"race: {label}", lambda k=key: c.race_action(k)))
        for n in sc.open_sprints:
            out.append((0.3, f"reopen Sprint {n}", lambda n=n: c.reopen_sprint(n)))
        if sc.task.editing:
            out.append((0.3, "Cancel Correction", c.cancel_edit))
        if sc.record and sc.record_enabled:
            out.append((1.0, "Record Sprint", c.record_sprint))
        if sc.rest_together:
            out.append((0.5, "Place the Rest Together", c.place_rest_together))
        if sc.mark_final:
            out.append((0.5, "Mark Final", c.mark_final))
        if sc.reopen:
            out.append((0.5, "Reopen", c.reopen_race))
        if sc.undo_enabled:
            out.append((0.4, f"Undo ({sc.undo_text})", c.undo))
        return out

    def _rider(self, eid: int, key: str, call):
        if key == "points_penalty":
            from madtracker.scoring._common import penalty_of

            # Chosen once, so a redo after Undo enters the same number.
            standing = penalty_of(self.c.live.actions(), eid)
            points = self.rng.choice([p for p in (0, 2, 3, 5, 10, 20) if p != standing])

            def act():
                _Penalty.points = points
                return call(eid, key)

            return act
        return lambda: call(eid, key)

    def anything(self) -> bool:
        offers = self.offers()
        if not offers:
            return False
        weights = [w for w, _, _ in offers]
        _, label, action = self.rng.choices(offers, weights)[0]
        self.s.step(label, action)
        return True

    def do(self, label_part: str, *, rows: bool = False) -> bool:
        """The first card (or row) control whose label has ``label_part``, if offered."""
        sc = self.screen
        c = self.c
        for item in sc.rows if rows else sc.cards:
            if item.entrant_id is None:
                continue
            for key, label in item.actions:
                if label_part == key or label_part in label:
                    call = c.row_action if rows else c.rider_action
                    where = "row" if rows else "card"
                    return self.s.step(
                        f"{where} {self.name(item.entrant_id)}: {label}",
                        self._rider(item.entrant_id, key, call),
                    )
        return False


class Mishaps:
    """The messy night's script for one race: each mishap fires once, when it can.

    ``maybe`` looks at the screen and does the first mishap whose moment
    has come; True when it took a step.
    """

    def __init__(self, p: Player) -> None:
        self.p = p
        self.c = p.c
        self.done: set[str] = set()
        live = self.c.live
        self.fmt = live.format_key
        self.kind = live.kind
        self.ended = 0

    def once(self, name: str) -> bool:
        if name in self.done:
            return False
        self.done.add(name)
        self.current = name
        return True

    def maybe(self) -> bool:
        self.current = None
        took = self._maybe()
        if took and self.current:
            REC.coverage[f"{self.fmt}: {self.current}"] += 1
        return took

    def _maybe(self) -> bool:
        p, c = self.p, self.c
        sc = p.screen
        task = sc.task
        recorded = sorted(c.live.recorded_sprints()) if self.kind in SPRINT_KINDS else []
        nothing_staged = not any(cd.badge is not None for cd in sc.cards)
        if task.kind == "final":
            if self.once("reopen"):
                return p.s.step("Reopen", c.reopen_race)
            return False
        if "reopen" in self.done and sc.review and self.once("dq after reopen"):
            # A protest upheld: a placed rider disqualified on a reopened result.
            placed = [
                r
                for r in sc.rows
                if r.entrant_id is not None
                and not r.status
                and any(k == "dq" for k, _ in r.actions)
            ]
            if placed:
                row = placed[len(placed) // 2]
                return p.s.step(
                    f"row {p.name(row.entrant_id)}: Disqualify",
                    lambda: c.row_action(row.entrant_id, "dq"),
                )
            return False
        if "end race" in self.done and self.once("end race undo"):
            return p.s.step("Undo the end", c.undo)
        if "end race undo" in self.done and sc.race_actions and self.once("end race again"):
            return p.s.step("End Race again", lambda: c.race_action("end_race"))
        if sc.review and not task.editing:
            # Corrections in review: a move and a tie on the result rows.
            if self.once("review move"):
                return p.do("move_down", rows=True) or p.do("move_up", rows=True)
            if self.once("review tie"):
                return p.do("tie_above", rows=True)
            if self.once("review move to"):
                return p.do("Move to", rows=True)
            return False
        if self.kind in SPRINT_KINDS:
            return self._sprints(sc, task, recorded, nothing_staged)
        if self.kind == "elimination":
            if task.kind == "out" and len(sc.rows) >= 1 and self.once("crash"):
                # A crash: the rider is clicked out of the race as a DNF.
                return p.do("dnf")
            if "crash" in self.done and self.once("crash undo"):
                return p.s.step("Undo the crash", c.undo)
            if "crash undo" in self.done and self.once("crash again"):
                return p.do("dnf")
            return False
        if self.kind == "placings":
            free = [cd for cd in sc.cards if cd.badge is None]
            nothing_staged = not (c.live.staged() or c.live.staged_tail())
            if task.kind == "order" and len(free) >= 4 and self.once("place last"):
                return p.do("Place Last")
            if task.kind == "order" and not nothing_staged and self.once("mid dnf"):
                return p.do("dnf")
            if task.kind == "order" and len(free) >= 3 and self.once("withdrawn"):
                # Pulled before the line: placed after every finisher by the
                # moment (USAC 1M6(d)), so a rider with no badge yet.
                return p.do("withdrawn")
            if sc.rest_together and self.once("rest together"):
                return p.s.step("Place the Rest Together", c.place_rest_together)
            if task.kind == "order" and not nothing_staged and self.once("staged move"):
                return p.do("move_up", rows=True) or p.do("tie_above", rows=True)
            return False
        if self.kind == "win_and_out":
            if task.kind == "lap" and len(sc.rows) >= 1 and self.once("mid dnf"):
                return p.do("dnf")
            return False
        return False

    def _sprints(self, sc, task, recorded, nothing_staged) -> bool:
        p, c = self.p, self.c
        free = [cd for cd in sc.cards if cd.badge is None]
        if task.editing:
            # The correction: move a badge, tie two, then Record (advance does).
            if self.once("edit move"):
                return p.do("move_down") or p.do("move_up")
            if self.once("edit tie"):
                return p.do("tie_above")
            return False
        if task.kind == "sprint" and not recorded and nothing_staged and self.once("short"):
            # Sprint 1 recorded with one rider placed: the ask says yes.
            ok = p.click(p._order(free)[0])
            return p.s.step("Record Sprint 1 short", c.record_sprint) or ok
        if len(recorded) >= 1 and self.once("dnf"):
            return p.do("dnf")
        # Two withdrawals a sprint apart, so the later one ranks above the
        # earlier (USAC 2O3(e)).
        if len(recorded) >= 1 and nothing_staged and self.once("withdrawn"):
            return p.do("withdrawn")
        if len(recorded) >= 2 and "withdrawn" in self.done and self.once("withdrawn again"):
            return p.do("withdrawn")
        if len(recorded) >= 1 and self.once("lap gained"):
            return p.do("lap_gained")
        if "lap gained" in self.done and self.once("lap lost"):
            return p.do("lap_lost")
        if len(recorded) >= 1 and self.once("penalty set"):
            _Penalty.points = 5
            return self._penalty(5)
        if "penalty set" in self.done and self.once("penalty changed"):
            return self._penalty(3)
        if "penalty changed" in self.done and self.once("penalty removed"):
            return self._penalty(0)
        if len(recorded) >= 2 and nothing_staged and sc.open_sprints and self.once("reopen sprint"):
            n = sc.open_sprints[-1]
            return p.s.step(f"reopen Sprint {n}", lambda: c.reopen_sprint(n))
        if (
            "reopen sprint" in self.done
            and nothing_staged
            and sc.open_sprints
            and self.once("reopen and cancel")
        ):
            n = sc.open_sprints[0]
            ok = p.s.step(f"reopen Sprint {n}", lambda: c.reopen_sprint(n))
            return p.s.step("Cancel Correction", c.cancel_edit) or ok
        if task.kind == "final_sprint" and self.once("out of finish"):
            return p.do("out_of_finish")
        # Stopped after 80 percent: the results stand on the sprints ridden,
        # then Undo, then ended again (USAC 2M6, 2N5).
        if self.fmt in ("points", "madison") and len(recorded) >= 2 and sc.race_actions:
            if self.once("end race"):
                return p.s.step("End Race, Results Stand", lambda: c.race_action("end_race"))
        return False

    def _penalty(self, points: int) -> bool:
        p, c = self.p, self.c
        live = c.live
        st = live.standings()
        target = getattr(self, "penalized", None)
        if target is None:
            racing = [r.entrant_id for r in st.rows if r.status is None]
            if not racing:
                return False
            target = self.penalized = racing[0]
        from madtracker.scoring._common import penalty_of

        if penalty_of(live.actions(), target) == points:
            return False
        sc = p.screen
        where = [r for r in sc.rows if r.entrant_id == target] + [
            cd for cd in sc.cards if cd.entrant_id == target
        ]
        if not any(k == "points_penalty" for item in where for k, _ in item.actions):
            return False

        def act():
            _Penalty.points = points
            return c.row_action(target, "points_penalty")

        return p.s.step(f"row {p.name(target)}: Points Penalty {points}", act)
