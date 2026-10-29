"""The app under replay: building it, the patched dialogs, the breaks, and the invariants.

Everything here reads the app through what the window reads (the
controller's screen, the store, the window's own widgets) and drives it
through the AppController methods the window's signals call. A break is
a fact that should hold and did not, recorded with the step that broke
it and what was seen before and after.
"""

from __future__ import annotations

import csv
import dataclasses
import random
import resource
import shutil
import sqlite3
import traceback
from collections import Counter
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The resident size a session may reach; the suite's whole run is ~1.6 GB.
MAX_RSS_MB = 1500


@dataclasses.dataclass
class Break:
    session: str
    step: str
    kind: str
    facts: str

    def line(self) -> str:
        return f"[{self.session}] {self.step}: {self.kind}\n    " + self.facts.replace(
            "\n", "\n    "
        )


class Recorder:
    """The breaks of a run, and the dialogs the app raised, by session."""

    def __init__(self) -> None:
        self.breaks: list[Break] = []
        self.session = ""
        self.step = ""
        self.asked: list[str] = []
        self.warned: list[str] = []
        self.informed: list[str] = []
        self.problems: list[str] = []
        # The warn boxes a step expects (a refusal it provokes on purpose).
        self.expect_warn = False
        # The ask boxes answer yes unless a step says otherwise.
        self.answer = True
        self.trace = False
        # The mishaps that fired, by format: what a run exercised.
        self.coverage: Counter = Counter()

    def add(self, kind: str, facts: str = "", step: str | None = None) -> None:
        self.breaks.append(Break(self.session, step or self.step, kind, facts))


REC = Recorder()


# The penalty the fake Points Penalty dialog answers with; the step sets it.
class _Penalty:
    points = 0


def install_patches() -> None:
    """Answer every box the app raises, and make a box nobody expected a break.

    A modal dialog in a headless replay would hang the run, so every
    exec the session does not drive is refused and recorded.
    """
    from PySide6.QtWidgets import QDialog, QFileDialog

    from madtracker import applog
    from madtracker.ui import icons, penalty, settings, shorten, widgets

    def ask(parent, title, text, verb="OK"):
        REC.asked.append(f"{title}: {text}")
        return REC.answer

    def choose(parent, title, text, verbs, primary, disabled=()):
        REC.asked.append(f"{title}: {text}")
        return primary

    def warn(parent, title, text, name=""):
        REC.warned.append(f"{title}: {text}")
        if not REC.expect_warn:
            REC.add("warning box", f"{title}: {text}")

    def inform(parent, title, text, *a, **k):
        REC.informed.append(f"{title}: {text}")

    icons.ask = ask
    icons.choose = choose
    icons.warn = warn
    icons.inform = inform
    widgets.run_menu = lambda menu, where: None

    class FakePenalty:
        DialogCode = QDialog.DialogCode

        def __init__(self, who, current=0, parent=None):
            self.current = current

        def exec(self):
            return QDialog.DialogCode.Accepted

        def points(self):
            return _Penalty.points

        def deleteLater(self):
            # The app lets every dialog go after it closes; a stand-in
            # has nothing to delete.
            pass

    penalty.PointsPenaltyDialog = FakePenalty

    class FakeShorten:
        """Shorten Race... answered with the fewest sprints the box allows,
        so the storm reaches the new final sprint soonest."""

        DialogCode = QDialog.DialogCode

        def __init__(self, fewest, most, parent=None):
            self.fewest = fewest

        def exec(self):
            return QDialog.DialogCode.Accepted

        def count(self):
            return self.fewest

        def deleteLater(self):
            pass

    shorten.ShortenRaceDialog = FakeShorten
    # A fresh file with no settings of its own opens Settings; Cancel.
    settings.open_settings = lambda *a, **k: False

    def no_exec(self, *a, **k):
        REC.add("modal dialog opened", type(self).__name__)
        return 0

    QDialog.exec = no_exec

    def no_file_box(*a, **k):
        REC.add("file dialog opened", repr(a[1:3]))
        return "", ""

    QFileDialog.getSaveFileName = staticmethod(no_file_box)
    QFileDialog.getOpenFileName = staticmethod(no_file_box)

    error = applog.error

    def logged_error(text: str) -> None:
        REC.add("applog error", text[-3000:])
        error(text)

    applog.error = logged_error


def seed_template(workdir: Path) -> Path:
    """The demo seeded once; each session opens a copy, as tests/apps.demo_data_dir does."""
    from madtracker.control.demo import seed_demo
    from madtracker.store import Store
    from madtracker.store.paths import DATABASE_FILE_NAME

    template = workdir / "demo-template"
    if not template.exists():
        template.mkdir(parents=True)
        store = Store.open(template / DATABASE_FILE_NAME)
        try:
            seed_demo(store)
        finally:
            store.close()
    return template


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def strip_undo(screen):
    return dataclasses.replace(screen, undo_text="", undo_enabled=False, undo_who="")


def diff_text(a, b, limit: int = 2500) -> str:
    """The fields two dataclasses (or anything) differ in, briefly."""
    if dataclasses.is_dataclass(a) and dataclasses.is_dataclass(b) and type(a) is type(b):
        parts = []
        for f in dataclasses.fields(a):
            x, y = getattr(a, f.name), getattr(b, f.name)
            if x != y:
                if isinstance(x, tuple) and isinstance(y, tuple):
                    for i, (p, q) in enumerate(zip(x, y, strict=False)):
                        if p != q:
                            parts.append(f"{f.name}[{i}]: {diff_text(p, q, 800)}")
                            break
                    else:
                        parts.append(f"{f.name}: length {len(x)} -> {len(y)}")
                else:
                    parts.append(f"{f.name}: {x!r:.600} -> {y!r:.600}")
        return ("; ".join(parts))[:limit]
    return f"{a!r:.{limit // 2}} -> {b!r:.{limit // 2}}"


class Session:
    """One app on one data folder, with its invariants checked after every step."""

    def __init__(
        self, qapp, workdir: Path, template: Path, name: str, rng: random.Random, undo_rate: float
    ) -> None:
        from PySide6.QtCore import QSettings

        from madtracker.app import AppController
        from madtracker.store.paths import DATABASE_FILE_NAME

        self.name = name
        self.rng = rng
        self.undo_rate = undo_rate
        self.workdir = workdir / name
        self.workdir.mkdir(parents=True)
        data = self.workdir / "data"
        shutil.copytree(template, data)
        self.home = data / DATABASE_FILE_NAME
        settings = QSettings(str(self.workdir / "machine.ini"), QSettings.Format.IniFormat)
        REC.session = name
        REC.step = "start"
        self.c = AppController(qapp, settings=settings, data_dir=data)
        self.log_folders = {data}
        self._wrap_window()
        self.rows_seen: dict[str, dict[int, tuple]] = {}
        self.steps = 0
        self.undo_checks = 0
        self.exports = 0
        self.check("start")

    def _wrap_window(self) -> None:
        main = self.c.main
        shown = main.show_problem

        def show_problem(text):
            if text:
                REC.problems.append(text)
                from madtracker.control.race_words import CONFLICT_TEXT

                if CONFLICT_TEXT in text:
                    REC.add("second-window conflict line", text)
                if "something went wrong" in text:
                    REC.add("unexpected-error line", text)
            self.last_problem = text
            shown(text)

        self.last_problem = None
        main.show_problem = show_problem

    def close(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "tests"))
        from apps import dispose_app

        dispose_app(self.c)
        for folder in self.log_folders:
            log = folder / "madtracker.log"
            if log.exists():
                text = log.read_text(encoding="utf-8", errors="replace")
                if "Traceback" in text:
                    REC.add(
                        "traceback in madtracker.log",
                        text[text.index("Traceback") - 400 :][:3000],
                        step="end",
                    )

    # Steps ---------------------------------------------------------------

    def snap(self):
        c = self.c
        if c.live is None:
            return None
        return (strip_undo(c.live.screen()), c.store.race(c.live.race_id).state)

    def stack_len(self) -> int:
        live = self.c.live
        return len(live._staged.stack) if live is not None else 0

    def step(
        self, label: str, fn: Callable[[], object], *, offered: bool = True, undo_check: bool = True
    ) -> bool:
        """Do one scorer's action, check every invariant, and sometimes Undo it and do it again.

        ``offered`` is an action the screen offered: a refusal of it is a break.
        """
        self.steps += 1
        live = self.c.live
        where = f"{live.race.name}" if live is not None else "-"
        # The step's number and race, so a break can be replayed with --trace.
        label = f"{self.steps} [{where}] {label}"
        REC.step = label
        if REC.trace:
            print(f"  {label}", flush=True)
        self.last_problem = None
        before = self.snap()
        depth = self.stack_len()
        race_id = self.c.live.race_id if self.c.live else None
        try:
            ok = bool(fn())
        except Exception as exc:  # the window's slot would have swallowed it
            REC.add(
                "exception out of the controller",
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-3000:],
            )
            return False
        if not ok and offered:
            REC.add("offered action refused", f"red line: {self.last_problem!r}")
        self.check(label)
        if not ok or not undo_check or before is None:
            return ok
        if self.c.live is None or self.c.live.race_id != race_id:
            return ok
        if self.stack_len() != depth + 1 or self.rng.random() >= self.undo_rate:
            return ok
        after = self.snap()
        if after[0].task.editing and not before[0].task.editing:
            # A reopened sprint stacks one entry per badge, so one Undo
            # takes one badge off; it is not one step to take back.
            return ok
        after_undo_text = self.c.live.screen().undo_text
        REC.step = f"{label} [undo]"
        self.undo_checks += 1
        try:
            undone = self.c.undo()
        except Exception as exc:
            REC.add(
                "exception out of undo",
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-3000:],
            )
            return ok
        if not undone:
            REC.add(
                "undo refused after a step",
                f"label {after_undo_text!r}, red line {self.last_problem!r}",
            )
            return ok
        self.check(f"{label} [undo]")
        now = self.snap()
        if now != before:
            REC.add(
                "undo did not restore the screen",
                f"undo label {after_undo_text!r}\nstate {before[1]} -> {now[1]}\n"
                + diff_text(before[0], now[0]),
            )
        REC.step = f"{label} [redo]"
        try:
            again = bool(fn())
        except Exception as exc:
            REC.add(
                "exception on redo",
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-3000:],
            )
            return ok
        if not again:
            REC.add("redo after undo refused", f"red line {self.last_problem!r}")
            return ok
        self.check(f"{label} [redo]")
        redone = self.snap()
        if redone != after:
            REC.add(
                "redo after undo differs from the first time",
                f"state {after[1]} -> {redone[1]}\n" + diff_text(after[0], redone[0]),
            )
        return ok

    # Invariants --------------------------------------------------------

    def check(self, label: str) -> None:
        REC.step = label
        try:
            self._check()
        except Exception as exc:
            REC.add(
                "exception while checking",
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-3000:],
            )
        if rss_mb() > MAX_RSS_MB:
            REC.add("memory", f"max RSS {rss_mb():.0f} MB")

    def _check(self) -> None:
        from madtracker.control.race import STAGED_KEY, LiveRace

        c = self.c
        self._check_append_only()
        if c.live is None or c.store is None:
            return
        live = c.live
        screen = live.screen()
        # The window draws what the controller would draw now.
        if c.main.showing() == "surface":
            shown = c.main.surface.screen
            if shown != screen:
                REC.add("window shows a stale screen", diff_text(shown, screen))
            if c.main.surface.state.text() != screen.state_label:
                REC.add(
                    "state pill differs",
                    f"{c.main.surface.state.text()!r} vs {screen.state_label!r}",
                )
            if c.main.undo.isEnabled() != screen.undo_enabled:
                REC.add(
                    "Undo button enabled differs",
                    f"{c.main.undo.isEnabled()} vs {screen.undo_enabled} ({screen.undo_text!r})",
                )
            # The widgets are the cards the screen says, in its order: a
            # card left behind or out of its slot is one the scorer can hit.
            drawn = [w.card for w in c.main.surface.cards.cards]
            if drawn != list(screen.cards):
                REC.add(
                    "card widgets differ from the screen's cards",
                    f"{[k.entrant_id for k in drawn]} vs {[k.entrant_id for k in screen.cards]}",
                )
        # The file read afresh is the same race: nothing lives only in memory.
        fresh = LiveRace(c.store, live.race_id, settle=False)
        again = fresh.screen()
        if again != screen:
            REC.add("race read again from the file differs", diff_text(screen, again))
        # The stored state is the state the log says.
        stored = c.store.race(live.race_id).state
        if fresh.race.state != stored:
            REC.add(
                "stored state is not the log's", f"stored {stored}, log says {fresh.race.state}"
            )
        if live.race.state != stored:
            REC.add("controller's state is not the file's", f"{live.race.state} vs {stored}")
        # The staged order in the file is the controller's.
        value = c.store.get_setting(STAGED_KEY.format(race_id=live.race_id))
        mine = {**live._staged.to_json(), "format": live.format_key}
        if value is not None and _norm(value) != _norm(mine):
            REC.add(
                "staged setting differs from the controller", f"{value!r:.800} vs {mine!r:.800}"
            )
        self._check_rows(live, screen)
        self._check_cards(live, screen)

    def _check_cards(self, live, screen) -> None:
        """The fixed grid: every entrant's card in bib order, each done card
        matching its row, and a click on one refused with nothing written."""
        from madtracker.control.race import STAGED_KEY
        from madtracker.control.race_words import DONE_MARKS

        if not screen.cards:
            return
        shown = [cd.entrant_id for cd in screen.cards]
        want = sorted(live.roster.ids, key=live._sort_key)
        if shown != want:
            REC.add("cards are not the field in bib order", f"{shown} vs {want}")
        rows = {r.entrant_id: r for r in screen.rows if r.entrant_id is not None}
        st = live.standings()
        key = STAGED_KEY.format(race_id=live.race_id)
        for card in screen.cards:
            if not card.done:
                continue
            eid = card.entrant_id
            row = rows.get(eid)
            standing = st.by_entrant(eid)
            if card.done_status:
                code = standing.status
                if code is None and standing.out_of_finish:
                    code = "out_of_finish"
                elif code is None and standing.withdrawn:
                    code = "withdrawn"
                if code is None or (card.done_text, card.done_tip) != DONE_MARKS[code]:
                    REC.add(
                        "done card's status differs from the rider's",
                        f"{live.name(eid)}: {card.done_text!r} vs {code!r}",
                    )
            elif row is None or (card.done_text, card.tied) != (row.place_text, row.tied):
                REC.add(
                    "done card's place differs from its row",
                    f"{live.name(eid)}: {(card.done_text, card.tied)!r} vs "
                    f"{(row.place_text, row.tied) if row else None!r}",
                )
            # A probe: harmless when the click is refused, a finding when not.
            before = (len(live.rows()), live.store.get_setting(key))
            out = live.click(eid)
            after = (len(live.rows()), live.store.get_setting(key))
            if out.ok or after != before:
                REC.add(
                    "a click on a done card was not refused",
                    f"{live.name(eid)}: {out!r}, log and staged row {before!r} -> {after!r}",
                )

    def _check_rows(self, live, screen) -> None:
        """Every row the table shows against a replay of the live log."""
        from dataclasses import replace

        from madtracker.scoring import compute_for_format

        actions = live.actions()
        st = compute_for_format(live.format_key, live.rules, live.roster.ids, actions)
        if (
            not st.is_complete
            and live.kind != "win_and_out"
            and live.roster.ids
            and not [
                r for r in st.rows if r.status is None and not r.out_of_finish and not r.withdrawn
            ]
        ):
            st = replace(st, remaining_entrants=(), is_complete=True)
        ids = [r.entrant_id for r in screen.rows if r.entrant_id is not None]
        if len(ids) != len(set(ids)):
            REC.add("an entrant shows twice in the table", repr(ids))
        if screen.points:
            if sorted(ids) != sorted(live.roster.ids):
                REC.add(
                    "points table is not the field", f"{sorted(ids)} vs {sorted(live.roster.ids)}"
                )
        elif screen.review and sorted(ids) != sorted(live.roster.ids):
            REC.add("result table is not the field", f"{sorted(ids)} vs {sorted(live.roster.ids)}")
        for row in screen.rows:
            if row.entrant_id is None or row.staged:
                continue
            want = st.by_entrant(row.entrant_id)
            if (row.status or None) != want.status:
                REC.add(
                    "row status differs from the replay",
                    f"{live.name(row.entrant_id)}: {row.status!r} vs {want.status!r}",
                )
            if screen.points:
                if row.total != int(want.total_points):
                    REC.add(
                        "row total differs from the replay",
                        f"{live.name(row.entrant_id)}: {row.total} vs {want.total_points}",
                    )
                text = want.status or (str(want.rank) if want.rank is not None else "")
                if row.place_text != text:
                    REC.add(
                        "row place differs from the replay",
                        f"{live.name(row.entrant_id)}: {row.place_text!r} vs {text!r}",
                    )
            elif not row.status or want.placed:
                if want.rank is not None and row.place_text != str(want.rank):
                    REC.add(
                        "row place differs from the replay",
                        f"{live.name(row.entrant_id)}: {row.place_text!r} vs {want.rank}",
                    )
        if screen.review != (st.is_complete and not screen.task.editing):
            REC.add("review flag differs from the replay", f"{screen.review} vs {st.is_complete}")

    def _check_append_only(self) -> None:
        """No race_action row ever changes or goes; new rows only come after."""
        c = self.c
        if c.store is None:
            return
        key = str(c.data_path)
        rows = {
            r[0]: tuple(r[1:])
            for r in c.store.connection.execute(
                "SELECT action_id, action_uuid, race_id, recorded_utc, kind, schema_ver,"
                " payload_json, voids_action_id, operator_note FROM race_action"
            )
        }
        seen = self.rows_seen.get(key)
        if seen is not None:
            gone = [i for i in seen if i not in rows]
            changed = [i for i in seen if i in rows and rows[i] != seen[i]]
            if gone or changed:
                REC.add("race_action rows changed", f"gone {gone[:10]}, changed {changed[:10]}")
            top = max(seen, default=0)
            new = [i for i in rows if i not in seen]
            if any(i < top for i in new):
                REC.add("race_action id reused", repr([i for i in new if i < top][:10]))
        voided = [v[6] for v in rows.values() if v[6] is not None]
        if len(voided) != len(set(voided)):
            REC.add("a row is voided twice", "")
        self.rows_seen[key] = rows

    def check_all_races(self, label: str) -> None:
        """Every race of the open event: its stored state is its log's."""
        from madtracker.control.race import LiveRace

        c = self.c
        REC.step = label
        for race in c.store.races(c.event.event_id):
            fresh = LiveRace(c.store, race.race_id, settle=False)
            if fresh.race.state != race.state:
                REC.add(
                    "stored state is not the log's",
                    f"{race.name}: stored {race.state}, log says {fresh.race.state}",
                )

    # Exports -------------------------------------------------------------

    def export_all(self, label: str) -> None:
        """Every export the File menu has, each checked against the shared rows."""
        REC.step = f"{label} exports"
        out = self.workdir / f"exports-{self.exports}"
        self.exports += 1
        out.mkdir()
        try:
            self._export_results(out)
            self._export_csv(out)
            self._export_program(out)
            self._export_standings(out)
        except Exception as exc:
            REC.add(
                "exception in an export",
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-3000:],
            )

    def _capture(self, write: Callable[[], object]) -> tuple[object, list[str]]:
        import madtracker.export.pdf as pdf_mod

        seen: list[str] = []
        original = pdf_mod._Doc.cell

        def cell(doc, *args, **kwargs):
            text = kwargs.get("text") or (args[2] if len(args) > 2 else "")
            seen.append(str(text))
            return original(doc, *args, **kwargs)

        pdf_mod._Doc.cell = cell
        try:
            return write(), seen
        finally:
            pdf_mod._Doc.cell = original

    def _pdf_ok(self, what: str, path, texts: list[str]) -> bool:
        if path is None:
            REC.add(f"{what} not written", "")
            return False
        data = Path(path).read_bytes()
        if not data.startswith(b"%PDF"):
            REC.add(f"{what} is not a PDF", repr(data[:20]))
        bad = [t for t in texts if "None" in t]
        if bad:
            REC.add(f"'None' on the {what}", repr(bad[:5]))
        return True

    def _finished(self):
        from madtracker.export.summary import FINISHED_STATES, build_summary

        c = self.c
        return [
            build_summary(c.store, r)
            for r in c.store.races(c.event.event_id)
            if r.state in FINISHED_STATES
        ]

    def _export_results(self, out: Path) -> None:
        from madtracker.control.race import LiveRace
        from madtracker.export.summary import place_text

        c = self.c
        path, texts = self._capture(lambda: c.export_pdf(out / "results.pdf", whole=True))
        if not self._pdf_ok("results PDF", path, texts):
            return
        started = [r for r in c.store.races(c.event.event_id) if r.state != "setup"]
        # Each race's part of the sheet: from its heading to the next race's.
        starts, pos = {}, 0
        for race in started:
            try:
                pos = texts.index(race.name, pos)
            except ValueError:
                REC.add("results PDF lacks a race", race.name)
                continue
            starts[race.race_id] = pos
            pos += 1
        bounds = sorted(starts.values()) + [len(texts)]
        for summary in self._finished():
            fresh = LiveRace(c.store, summary.race.race_id, settle=False).standings()
            for row in summary.rows:
                want = fresh.by_entrant(row.entrant_id)
                if row.place != place_text(want):
                    REC.add(
                        "sheet row's place is not the replay's",
                        f"{summary.race.name}: {row.place} vs {place_text(want)}",
                    )
            start = starts.get(summary.race.race_id)
            if start is None:
                continue
            end = next(b for b in bounds if b > start)
            self._sheet_rows(summary, texts[start:end], "results PDF")
        if c.live is not None:
            one, texts = self._capture(
                lambda: c.export_pdf(out / "race.pdf", race_id=c.live.race_id)
            )
            if self._pdf_ok("race PDF", one, texts):
                for summary in self._finished():
                    if summary.race.race_id == c.live.race_id:
                        self._sheet_rows(summary, texts, "race PDF")

    @staticmethod
    def _sheet_rows(summary, texts: list[str], what: str) -> None:
        """Every placed row's place and total, and every status, in the race's part of a sheet."""
        from madtracker.export.summary import format_number

        have = Counter(texts)
        want = Counter()
        for row in summary.rows:
            want[row.place] += 1
            if row.placed and summary.kind in ("points", "madison"):
                want[format_number(row.total_points)] += 1
        short = want - have
        if short:
            REC.add(
                f"{what} lacks figures of a race",
                f"{summary.race.name} ({summary.race.state}): {dict(short)}",
            )

    def _export_csv(self, out: Path) -> None:
        from madtracker.export.usac_csv import HEADERS

        c = self.c
        path = c.export_csv(out / "usac.csv")
        if path is None:
            REC.add("USAC CSV not written", "")
            return
        with open(path, encoding="utf-8", newline="") as handle:
            table = list(csv.reader(handle))
        if tuple(table[0]) != HEADERS:
            REC.add("USAC CSV header", repr(table[0]))
        body = table[1:]
        if any("None" in cell for row in body for cell in row):
            REC.add("'None' in the USAC CSV", repr([r for r in body if "None" in "".join(r)][:3]))
        want = [
            (rider.first, rider.last, row.place)
            for summary in self._finished()
            for row in summary.rows
            for rider in row.riders
        ]
        got = [(r[7], r[8], r[9]) for r in body]
        if got != want:
            REC.add(
                "USAC CSV disagrees with the sheet's rows",
                f"{len(got)} rows vs {len(want)};"
                f" first difference {next((p for p in zip(got, want, strict=False) if p[0] != p[1]), None)}",
            )

    def _export_program(self, out: Path) -> None:
        path, texts = self._capture(lambda: self.c.export_program(out / "program.pdf"))
        self._pdf_ok("program PDF", path, texts)

    def _export_standings(self, out: Path) -> None:
        from madtracker.control import multi_race
        from madtracker.export.summary import format_number
        from madtracker.ui.standings import StandingsDialog

        c = self.c
        written: list[int] = []

        def export(standings_id):
            path = c.export_standings(standings_id, out / f"standings-{standings_id}.pdf")
            written.append(standings_id)
            return path

        dialog = StandingsDialog(c.store, c.main, export=export)
        try:
            for made in c.store.list_standings():
                dialog.select(made.name)
                if dialog.selected_id() != made.standings_id:
                    REC.add("standings dialog did not select", made.name)
                    continue
                cells = [x for preview in dialog.standings_views for x in preview.cells()]
                if any("None" in str(x) for x in cells):
                    REC.add("'None' in the standings dialog", made.name)
                table = multi_race.compute(c.store, made.standings_id)
                for preview, group in zip(dialog.standings_views, table.groups, strict=False):
                    if "Total" not in preview.full_headers:
                        continue
                    shown = preview.column("Total")
                    want = ["" if r.status else format_number(r.total) for r in group.rows]
                    if shown != want:
                        REC.add(
                            "standings dialog totals differ from compute",
                            f"{made.name} {group.group}: {shown} vs {want}",
                        )
                path, texts = self._capture(lambda d=dialog: d.export_pdf())
                path = out / f"standings-{made.standings_id}.pdf"
                if not path.exists():
                    REC.add("standings PDF not written", made.name)
                    continue
                self._pdf_ok("standings PDF", path, texts)
                have = set(texts)
                for group in table.groups:
                    for row in group.rows:
                        if not row.status and format_number(row.total) not in have:
                            REC.add(
                                "standings PDF lacks a total",
                                f"{made.name}: {row.team} {row.total}",
                            )
        finally:
            dialog.deleteLater()


def _norm(value):
    """A setting read back from JSON, and the controller's dict, alike (tuples are lists)."""
    import json

    return json.loads(json.dumps(value))


def sqlite_rows(path: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()
