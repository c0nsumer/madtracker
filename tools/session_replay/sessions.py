"""The nights: clean, messy, switch, storm, and the scorer personas.

Each plays every race of the demo's program (one of every format the
demo has) on its own copy of the demo file, through the controller
methods the window calls, then exports everything the File menu offers.
The personas (careful, click-happy, careless, panicked, fast finish, fat
finger, late change, corrector) are the scorer under stress: each adds
its own habits between the ordinary steps and checks what those habits
must leave as they found it.
"""

from __future__ import annotations

from harness import REC, Session, diff_text
from play import SPRINT_KINDS, Mishaps, Player


def clean_night(s: Session) -> None:
    """Every race scored as the officials call it, marked final, and exported."""
    c = s.c
    p = Player(s)
    races = list(c.races)
    for i, race in enumerate(races):
        if not p.begin(race.race_id):
            continue
        p.finish()
        if i == len(races) // 2:
            s.export_all("half the night")
    s.check_all_races("end of night")
    s.export_all("end of night")
    s.step("Backup Now", lambda: c.backup_now(s.workdir / "end.sqlite"), undo_check=False)


def messy_night(s: Session) -> None:
    """Every mishap the script knows, random controls between, a race left and come back to."""
    c = s.c
    p = Player(s)
    races = list(c.races)
    for i, race in enumerate(races):
        if not p.begin(race.race_id):
            continue
        mishaps = Mishaps(p)
        if i in (2, 3) and i + 1 < len(races):
            # Leave a race mid-scoring for the next one, answer Switch, and come back.
            for _ in range(6):
                if mishaps.maybe() or p.advance():
                    continue
                break
            if c.live.in_progress and not c.live.editing:
                before = c.live.screen()
                nxt = races[i + 1].race_id
                s.step(
                    "switch to the next race mid-race",
                    lambda nxt=nxt: c.select_race(nxt) or c.live.race_id == nxt,
                    undo_check=False,
                )
                s.step(
                    "and back",
                    lambda rid=race.race_id: c.select_race(rid) or c.live.race_id == rid,
                    undo_check=False,
                )
                after = c.live.screen()
                if after != before:
                    REC.add("race left and come back to differs", diff_text(before, after))
        if i == 4:
            for _ in range(5):
                if not (mishaps.maybe() or p.advance()):
                    break
            s.export_all("mid-race")
        p.finish(mishaps, wild=getattr(s, "wild", 0.08))
    s.check_all_races("end of night")
    s.export_all("end of night")


def storm_night(s: Session) -> None:
    """Most steps any offered control, the statuses as likely as a click, every step undone once."""
    import play

    c = s.c
    p = Player(s)
    s.undo_rate = 1.0
    saved = dict(play.WEIGHTS)
    play.WEIGHTS.update({"dns": 0.6, "dnf": 0.8, "dq": 0.8, "out_of_finish": 0.8, "withdrawn": 0.6})
    try:
        for race in list(c.races):
            if p.begin(race.race_id):
                p.finish(Mishaps(p), wild=0.7)
    finally:
        play.WEIGHTS.clear()
        play.WEIGHTS.update(saved)
    s.check_all_races("end of night")
    s.export_all("end of night")


def _file_facts(store) -> dict:
    """Every race's live log, state, and staged order: what a backup must hold."""
    from madtracker.control.race import STAGED_KEY

    facts = {}
    for event in store.events():
        for race in store.races(event.event_id):
            facts[race.race_id] = (
                race.state,
                [(r.action_uuid, r.kind, r.payload) for r in store.live_actions(race.race_id)],
                store.get_setting(STAGED_KEY.format(race_id=race.race_id)),
            )
    return facts


def switch_night(s: Session) -> None:
    """Half a race scored, another file opened, back again; a mid-race backup restored and compared."""
    from madtracker.control.copying import CopyChoice

    c = s.c
    p = Player(s)
    other = s.workdir / "other" / "other.sqlite"
    other.parent.mkdir()
    s.log_folders.add(other.parent)
    made = False
    races = list(c.races)
    for i, race in enumerate(races):
        if not p.begin(race.race_id):
            continue
        if c.live.kind == "madison" and i > 3:
            _madison_rename(s, p, race.race_id)
        for _ in range(s.rng.randint(3, 12)):
            if not p.advance():
                break
        if c.live.screen().task.kind == "final" or c.live.editing:
            p.finish()
            continue
        before = c.live.screen()
        if i % 3 == 0:
            s.step(
                "Edit Event, then Score",
                lambda: (c.open_setup(), c.close_setup()) and c.main.showing() == "surface",
                undo_check=False,
            )
            _same(c, race.race_id, before, "Edit Event and back")
            _setup_round(s, race.race_id)
            _same(c, race.race_id, before, "the race edited, duplicated, moved, and back")
        if not made:
            s.step(
                "New Data File", lambda: c.new_data_file(other, copy=CopyChoice()), undo_check=False
            )
            made = True
        else:
            s.step("Open the other file", lambda: c.open_data_file(other), undo_check=False)
        if c.data_path != other:
            REC.add("the other file did not open", str(c.data_path))
        s.step("Open the night's file again", lambda: c.open_data_file(s.home), undo_check=False)
        _same(c, race.race_id, before, "another file and back")
        if i % 4 == 1:
            dest = s.workdir / f"backup-{i}.sqlite"
            s.step("Backup Now mid-race", lambda d=dest: c.backup_now(d), undo_check=False)
            facts = _file_facts(c.store)
            target = s.workdir / f"restored-{i}" / "restored.sqlite"
            target.parent.mkdir()
            s.log_folders.add(target.parent)
            s.step(
                "Restore the backup as a new file",
                lambda d=dest, t=target: c.open_data_file(path=d, restore_to=t),
                undo_check=False,
            )
            if c.data_path != target:
                REC.add("the restored file did not open", str(c.data_path))
            else:
                got = _file_facts(c.store)
                if got != facts:
                    bad = [k for k in facts if facts.get(k) != got.get(k)]
                    REC.add(
                        "restored backup differs from the file it copied",
                        f"races {bad[:5]}: {facts.get(bad[0]) if bad else ''!r:.600} vs"
                        f" {got.get(bad[0]) if bad else ''!r:.600}",
                    )
                _same(c, race.race_id, before, "restored backup")
                # A step scored in the restored file stays there.
                p.advance()
            s.step(
                "Open the night's file again", lambda: c.open_data_file(s.home), undo_check=False
            )
            _same(c, race.race_id, before, "restored file and back")
        if i % 4 == 3:
            _restore_over_open(s, p, race.race_id, i)
        if i == 5:
            _demo_and_back(s, race.race_id)
        if i == 6:
            _refusals(s, race.race_id)
        p.finish()
    s.check_all_races("end of night")
    s.export_all("end of night")


def _restore_over_open(s: Session, p: Player, race_id: int, i: int) -> None:
    """A backup taken, one more step scored, then the backup restored over the open file."""
    c = s.c
    dest = s.workdir / f"over-{i}.sqlite"
    s.step("Backup Now", lambda: c.backup_now(dest), undo_check=False)
    facts = _file_facts(c.store)
    before = c.live.screen()
    p.advance()
    # The log is replaced on purpose, so the rows seen since the backup go.
    s.step(
        "Restore the backup over the open file",
        lambda: (
            s.rows_seen.pop(str(s.home), None) is None
            or c.open_data_file(path=dest, restore_to=s.home)
        ),
        undo_check=False,
    )
    if c.data_path != s.home:
        REC.add("the night's file is not open after a restore over it", str(c.data_path))
        return
    got = _file_facts(c.store)
    if got != facts:
        bad = [k for k in facts if facts.get(k) != got.get(k)]
        REC.add("backup restored over the open file differs", f"races {bad[:5]}")
    _same(c, race_id, before, "restore over the open file")


def _demo_and_back(s: Session, race_id: int) -> None:
    """Help > Demo Data File... (Create New), then the night's file again."""
    c = s.c
    before = c.live.screen()
    s.step("Help > Demo Data File...", c.open_demo_file, undo_check=False)
    s.log_folders.add(c.data_dir)
    if c.event is None or c.live is None:
        REC.add("the demo opened on no race", str(c.data_path))
    s.step("Open the night's file again", lambda: c.open_data_file(s.home), undo_check=False)
    _same(c, race_id, before, "the demo and back")


def _refusals(s: Session, race_id: int) -> None:
    """Files that must be refused, each leaving the night's file open as it was."""
    c = s.c
    before = c.live.screen()
    empty = s.workdir / "empty.sqlite"
    empty.write_bytes(b"")
    text = s.workdir / "notes.sqlite"
    text.write_text("not a database\n" * 50)
    cases = [
        ("a file that is not there", lambda: c.open_data_file(s.workdir / "gone.sqlite")),
        ("an empty file", lambda: c.open_data_file(empty)),
        ("a text file", lambda: c.open_data_file(text)),
        ("a new file over the open one", lambda: c.new_data_file(s.home)),
    ]
    for what, open_it in cases:
        REC.expect_warn = True
        warned = len(REC.warned)
        try:
            s.step(f"open {what}", open_it, offered=False, undo_check=False)
        finally:
            REC.expect_warn = False
        if len(REC.warned) == warned:
            REC.add(f"no refusal for {what}", str(c.data_path))
        if c.data_path != s.home or c.store is None:
            REC.add(f"{what} let the night's file go", str(c.data_path))
            c.open_data_file(s.home)
        _same(c, race_id, before, f"after refusing {what}")


def _madison_rename(s: Session, p: Player, race_id: int) -> None:
    """Two teams clicked into Sprint 1, then a team renamed in its race's dialog and saved.

    A team is its riders, so the rename keeps its id and the staged
    clicks; nothing scored changes.
    """
    c = s.c
    for _ in range(2):
        p.advance()
    staged = c.live.staged()
    teams = [(t.team_id, t.members) for t in c.store.teams(race_id)]
    log = [(r.action_uuid, r.payload) for r in c.store.live_actions(race_id)]
    s.step("Edit Event", lambda: c.open_setup() or c.main.showing() == "setup", undo_check=False)
    setup = c.main.setup
    dialog = _saving(setup.race_dialog(race_id))
    s.step("rename a team", lambda: dialog.edit_team(0, name="Renamed Pair"), undo_check=False)
    setup.race_dialog = lambda *a, **k: dialog
    try:
        s.step("Save the race", lambda: setup.edit_race(race_id), undo_check=False)
    finally:
        del setup.race_dialog
    s.step("Score", lambda: c.close_setup() or c.main.showing() == "surface", undo_check=False)
    after = [(t.team_id, t.members) for t in c.store.teams(race_id)]
    if after != teams:
        REC.add("a renamed team lost its id or riders", f"{teams} -> {after}")
    if c.live is None or c.live.staged() != staged:
        REC.add(
            "a team rename dropped the staged clicks",
            f"{staged} -> {c.live.staged() if c.live else None}",
        )
    if [(r.action_uuid, r.payload) for r in c.store.live_actions(race_id)] != log:
        REC.add("a team rename changed the log", "")
    names = [t.name for t in c.store.teams(race_id)]
    if "Renamed Pair" not in names:
        REC.add("the rename was not saved", repr(names))


def _saving(dialog):
    """A race dialog whose exec presses Save, as the scorer would with nothing changed."""
    from PySide6.QtWidgets import QDialog

    def exec_():
        return QDialog.DialogCode.Accepted if dialog.save() else QDialog.DialogCode.Rejected

    dialog.exec = exec_
    return dialog


def _setup_round(s: Session, race_id: int) -> None:
    """Mid-race in Edit Event: the race saved unchanged, duplicated, moved, the copy removed."""
    c = s.c
    s.step("Edit Event", lambda: c.open_setup() or c.main.showing() == "setup", undo_check=False)
    setup = c.main.setup
    s.step("Edit... the race, Save unchanged", lambda: _edit(setup, race_id), undo_check=False)
    copies = []

    def duplicate():
        made = setup.duplicate_race(
            race_id, dialog=_saving(setup.race_dialog(None, copy_of=race_id))
        )
        if made is not None:
            copies.append(made)
        return made is not None

    s.step("Duplicate... the race", duplicate, undo_check=False)
    s.step("move the race down", lambda: setup.move_race(1, race_id), undo_check=False)
    s.step("and up", lambda: setup.move_race(-1, race_id), undo_check=False)
    for made in copies:
        s.step("Remove the copy", lambda m=made: setup.remove_race(m), undo_check=False)
    s.step("Score", lambda: c.close_setup() or c.main.showing() == "surface", undo_check=False)


def _edit(setup, race_id: int) -> bool:
    dialog = _saving(setup.race_dialog(race_id))
    setup.race_dialog = lambda *a, **k: dialog
    try:
        return setup.edit_race(race_id)
    finally:
        del setup.race_dialog


def _same(c, race_id: int, before, what: str) -> None:
    if c.live is None or c.live.race_id != race_id:
        REC.add(
            f"{what}: not back on the race",
            f"live {getattr(c.live, 'race_id', None)}, wanted {race_id}",
        )
        return
    after = c.live.screen()
    if after != before:
        REC.add(f"{what}: the race differs", diff_text(before, after))


# ----- the personas: the scorer under stress ---------------------------------
#
# Each persona plays every race of the night with its own habits between
# the ordinary steps (``Player.finish`` asks its ``maybe`` before each
# one). A habit that must mean what one entry means is checked against a
# twin: the open file copied as it stood before the habit, given that one
# entry through the controller alone.

# Invented names only: never a real rider.
FIRST = ["Arlo", "Bexa", "Corin", "Dalia", "Emrys", "Fenna", "Galo", "Hesper", "Ivo", "Juna",
         "Kael", "Lisbet", "Moro", "Nell", "Oskel", "Pim"]  # fmt: skip
LAST = ["Quillan", "Rendt", "Sorvik", "Tamsk", "Ulbrin", "Vesk", "Wrenfold", "Yarrow",
        "Zelkin", "Abernook", "Brisk", "Coldmere"]  # fmt: skip
# The fields a careful or late-change night sets its races to, each in
# turn: None keeps the demo's own field.
RIDER_SIZES = (None, 4, 12, 20, 30)
TEAM_SIZES = (None, 3, 6, 12)
# The window size the window-driven personas use: the venue's laptop.
LAPTOP = (1366, 740)


def _pump() -> None:
    """What the event loop does between two of the scorer's clicks."""
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    for _ in range(2):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()


def _quiet(mode, context, message) -> None:
    # The offscreen platform says it cannot propagate size hints for
    # every shown window resized; that line is noise, every other is kept.
    import sys

    if "propagateSizeHints" not in message:
        sys.stderr.write(message + "\n")


def _show(s: Session) -> None:
    """The window shown at the laptop's size, so a click lands on real geometry."""
    from PySide6.QtCore import qInstallMessageHandler

    main = s.c.main
    if not main.isVisible():
        qInstallMessageHandler(_quiet)
        main.resize(*LAPTOP)
        main.show()
    _pump()


def _tap(w, at=None) -> None:
    """A left click on a widget, on the card's plate unless ``at`` says where."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    if at is None:
        at = QPoint(max(4, w.width() // 5), w.height() // 2)
    QTest.mouseClick(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at)


def _double_click(w, at=None) -> None:
    """A real double-click: press, release, the second press as Qt's double-click event, release.

    QTest.mouseDClick on a widget sends a press and the double-click
    event with no release, so a button never clicks at all. A person's
    double-click clicks a plain button twice, and the one-click buttons
    (the cards, Undo, Record Sprint) once, since they drop the second
    press.
    """
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    if at is None:
        at = QPoint(max(4, w.width() // 5), w.height() // 2)
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    kinds = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
             QEvent.Type.MouseButtonDblClick, QEvent.Type.MouseButtonRelease)  # fmt: skip
    for kind in kinds:
        held = none if kind == QEvent.Type.MouseButtonRelease else left
        event = QMouseEvent(
            kind,
            QPointF(at),
            QPointF(w.mapToGlobal(at)),
            left,
            held,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(w, event)


def _hit(root, at) -> object:
    """A left click at a point of ``root``, delivered to whatever widget is there.

    A finger that misses a card's plate lands on the child under it (the
    strip, a lap button) or on the next card, as a real press would.
    """
    target = root.childAt(at) or root
    _tap(target, target.mapFrom(root, at))
    return target


def _widget(c, eid: int):
    from shiboken6 import isValid

    return next(
        (w for w in c.main.surface.cards.cards if isValid(w) and w.card.entrant_id == eid), None
    )


def _log_len(store, race_id: int) -> int:
    """Every row of the race's log, voids included: what one entry adds to."""
    return len(store.actions(race_id))


def _outcome(live) -> tuple:
    """Everything an entry decides: the screen, the live log, the staged order, the correction."""
    from harness import strip_undo

    return (
        strip_undo(live.screen()),
        [(r.kind, r.payload) for r in live.rows()],
        live.staged(),
        live.staged_tail(),
        live.editing_sprint,
    )


def _result(live) -> tuple:
    """What the scorer sees decided, without the log's own words for how it got there.

    A fix by moves writes moves where the right clicks wrote none, so it
    is compared on the places, statuses, totals, and cards alone.
    """
    sc = live.screen()
    return (
        sc.task.kind,
        sc.task.text,
        tuple((r.entrant_id, r.place_text, r.status, r.total, r.tied) for r in sc.rows),
        tuple((k.entrant_id, k.badge, k.done, k.done_text, k.done_status) for k in sc.cards),
        [sorted(g) for g in live.staged()],
        [sorted(g) for g in live.staged_tail()],
    )


def _differs(got: tuple, want: tuple) -> str:
    parts = [diff_text(got[0], want[0])] if got[0] != want[0] else []
    for i, (a, b) in enumerate(zip(got[1:], want[1:], strict=False), 1):
        if a != b:
            parts.append(f"part {i}: {a!r:.500} vs {b!r:.500}")
    return "\n".join(parts)


class Twin:
    """The open file copied as it stands, with its own race on the same race id.

    What the scorer meant is given to the twin through ``LiveRace`` alone,
    then the open race is compared with it.
    """

    def __init__(self, s: Session) -> None:
        import sqlite3

        from madtracker.control.race import LiveRace
        from madtracker.store import Store

        s.twins = getattr(s, "twins", 0) + 1
        self.folder = s.workdir / f"twin-{s.twins}"
        self.folder.mkdir()
        path = self.folder / "twin.sqlite"
        dest = sqlite3.connect(path)
        try:
            s.c.store.connection.backup(dest)
        finally:
            dest.close()
        self.race_id = s.c.live.race_id
        self.store = Store.open(path)
        self.live = LiveRace(self.store, self.race_id)
        self.start = _log_len(self.store, self.race_id)

    def click(self, eid: int) -> bool:
        return self.live.click(eid).ok

    def record(self, *, short_ok: bool) -> bool:
        """Record Sprint as the window does: a short sprint asks, and ``short_ok`` answers."""
        out = self.live.record_sprint(ask_short=True)
        if out.short is not None:
            if not short_ok:
                return False
            out = self.live.record_sprint()
        return out.ok

    def added(self) -> int:
        return _log_len(self.store, self.race_id) - self.start

    def close(self) -> None:
        import shutil

        self.store.close()
        shutil.rmtree(self.folder, ignore_errors=True)


def _against_twin(s: Session, twin: Twin, start: int, what: str, *, loose: bool = False) -> None:
    """The open race against the twin: the same outcome, and as many log rows written."""
    c = s.c
    if loose:
        got, want = _result(c.live), _result(twin.live)
        if got != want:
            REC.add(
                f"{what}: the result differs from the right entries made once",
                repr(got)[:1200] + "\n vs " + repr(want)[:1200],
            )
        return
    got, want = _outcome(c.live), _outcome(twin.live)
    if got != want:
        REC.add(f"{what}: differs from the one entry it means", _differs(got, want))
    added = _log_len(c.store, c.live.race_id) - start
    if added != twin.added():
        REC.add(f"{what}: wrote {added} log rows where one entry writes {twin.added()}", "")


def _next_card(p: Player):
    """The card the ordinary step would click now, or None when it would not click one."""
    sc = p.screen
    task = sc.task
    if task.editing or task.kind not in ("order", "out", "lap", "winner", "sprint", "final_sprint"):
        return None
    free = [cd for cd in sc.cards if cd.badge is None and not cd.done]
    if not free:
        return None
    order = p._order(free)
    return order[-1] if task.kind == "out" else order[0]


def _playable(sc) -> bool:
    return sc.task.kind not in ("final", "review", "none", "blocked")


# ----- fields of every size -----


def _field_of(s: Session, race, size: int, team: bool) -> tuple[list[int], list | None]:
    """The race's field set to ``size`` riders or teams, riders added to the roster as needed.

    The race's own riders stay first, then the roster's in bib order, then
    invented riders with bibs nobody holds; a bib is unique in the field.
    """
    from madtracker.control.formats import TEAM_COLORS

    store = s.c.store
    current = [e.rider_id for e in store.race_entries(race.race_id)]
    pairs = store.entries_with_riders(race.event_id)
    bibs = {e.rider_id: e.bib for e, _ in pairs}
    pool = list(current)
    held = {bibs.get(r) for r in current}
    for entry, _ in pairs:
        if entry.rider_id not in pool and entry.bib is not None and entry.bib not in held:
            pool.append(entry.rider_id)
            held.add(entry.bib)
    used = {e.bib for e, _ in pairs if e.bib is not None}
    need = 2 * size if team else size
    while len(pool) < need:
        bib = next(b for b in range(100, 1000) if b not in used)
        used.add(bib)
        n = s.invented = getattr(s, "invented", 0) + 1
        rider = store.add_rider(FIRST[n % len(FIRST)], f"{LAST[n % len(LAST)]}{n}")
        store.add_entry(race.event_id, rider.rider_id, bib)
        pool.append(rider.rider_id)
    if not team:
        return pool[:size], None
    shapes = [(t.name, t.color, t.color_hex, list(t.members)) for t in store.teams(race.race_id)]
    shapes = shapes[:size]
    inside = {m for t in shapes for m in t[3]}
    spare = [r for r in pool if r not in inside]
    taken = {t[0] for t in shapes} | {t[1] for t in shapes}
    colors = [k for k in TEAM_COLORS if k not in taken]
    while len(shapes) < size:
        color = colors.pop(0)
        shapes.append((color, color, TEAM_COLORS[color], [spare.pop(0), spare.pop(0)]))
    return [m for t in shapes for m in t[3]], shapes


def _set_field(s: Session, size: int | None) -> bool:
    """Edit Event, the race's field set to ``size``, and Score: what Edit Race allows before a result.

    A race with an entry that stands keeps its field (the dialog locks it),
    so a scored race is left as it is.
    """
    from madtracker.control.program import is_scored

    c = s.c
    if size is None or c.live is None:
        return True
    race = c.store.race(c.live.race_id)
    if is_scored(c.store, race):
        REC.coverage["Edit Race keeps a scored race's field"] += 1
        return False
    team = c.live.team_format

    def edit() -> bool:
        c.open_setup()
        try:
            field, teams = _field_of(s, race, size, team)
            rules = dict(race.rules or {})
            fields = {}
            # A win-and-out names fewer lap winners than it has riders.
            if rules.get("places") is not None and rules["places"] >= size:
                rules["places"] = size - 1
                fields["rules"] = rules
            c.store.save_race(race.event_id, race.race_id, fields, field, teams)
        finally:
            c.close_setup()
        return (
            c.live is not None
            and c.live.race_id == race.race_id
            and (len(c.live.roster.ids) == size)
        )

    noun = "teams" if team else "riders"
    REC.coverage[f"field of {size} {noun}"] += 1
    return s.step(f"Edit Race: {size} {noun}", edit, undo_check=False)


def _sizes(s: Session):
    """Each race's size in turn, so one night sees every size, from a start the night draws."""
    start = s.rng.randrange(len(RIDER_SIZES) * len(TEAM_SIZES))

    def size(i: int, team: bool):
        sizes = TEAM_SIZES if team else RIDER_SIZES
        return sizes[(start + i) % len(sizes)]

    return size


def _night_end(s: Session) -> None:
    s.check_all_races("end of night")
    s.export_all("end of night")


# ----- the careful scorer -----


def careful_night(s: Session) -> None:
    """The clean night over fields of every size: the baseline the others are measured by."""
    c = s.c
    p = Player(s)
    races = list(c.races)
    size = _sizes(s)
    for i, race in enumerate(races):
        if not p.begin(race.race_id):
            continue
        _set_field(s, size(i, c.live.team_format))
        p.begin(race.race_id)
        p.finish()
        if i == len(races) // 2:
            s.export_all("half the night")
    _night_end(s)
    s.step("Backup Now", lambda: c.backup_now(s.workdir / "end.sqlite"), undo_check=False)


# ----- the click-happy scorer -----


class ClickHappy:
    """Double clicks, bursts on one card, a done card first, Record Sprint and Undo twice.

    Each is pressed through the window's own widgets and checked against a
    twin given what one press means.
    """

    TRICKS = ("double", "burst", "done first", "record twice", "undo twice", "dots")

    def __init__(self, p: Player, rate: float = 0.3) -> None:
        self.p, self.s, self.c = p, p.s, p.c
        self.rate = rate

    def maybe(self) -> bool:
        s, c = self.s, self.c
        sc = self.p.screen
        if not _playable(sc) or c.main.showing() != "surface" or s.rng.random() >= self.rate:
            return False
        _pump()
        trick = s.rng.choice(self.TRICKS)
        took = getattr(self, "_" + trick.replace(" ", "_"))(sc)
        if took:
            REC.coverage[f"click-happy: {trick}"] += 1
        return took

    def _target(self):
        card = _next_card(self.p)
        if card is None:
            return None, None
        return card.entrant_id, _widget(self.c, card.entrant_id)

    def _pressed(self, label: str, press, twin: Twin, *, loose: bool = False) -> bool:
        c = self.c
        start = _log_len(c.store, c.live.race_id)
        self.s.step(label, lambda: press() or True, offered=False, undo_check=False)
        _pump()
        _against_twin(self.s, twin, start, label, loose=loose)
        twin.close()
        return True

    def _double(self, sc) -> bool:
        eid, w = self._target()
        if w is None:
            return False
        twin = Twin(self.s)
        twin.click(eid)
        return self._pressed(f"double-click {self.p.name(eid)}", lambda: _double_click(w), twin)

    def _burst(self, sc) -> bool:
        eid, w = self._target()
        if w is None:
            return False
        twin = Twin(self.s)
        twin.click(eid)
        after = twin.live.screen()
        still = next((k for k in after.cards if k.entrant_id == eid), None)
        if still is not None and not still.done:
            # A sprint's badged card is live: a second tap takes the badge
            # off by design, so a burst there is a double-click.
            twin.close()
            REC.coverage["click-happy: a sprint's second tap takes the badge off"] += 1
            return self._double(sc)
        n = self.s.rng.randint(2, 5)

        def press():
            for _ in range(n):
                w2 = _widget(self.c, eid)
                if w2 is None or not w2.isVisible():
                    # The result completed and the cards left: the
                    # next tap lands on the table, not on a card.
                    break
                _tap(w2)

        return self._pressed(f"{n} taps on {self.p.name(eid)}", press, twin)

    def _done_first(self, sc) -> bool:
        done = [k for k in sc.cards if k.done]
        eid, w = self._target()
        if w is None or not done:
            return False
        miss = self.s.rng.choice(done).entrant_id
        twin = Twin(self.s)
        twin.click(eid)

        def press():
            c = self.c
            start = _log_len(c.store, c.live.race_id)
            line = c.main.surface.problem.text()
            _tap(_widget(c, miss))
            _pump()
            # A done card's click does nothing: no entry, and no red line.
            shown = c.main.surface.problem.text()
            if _log_len(c.store, c.live.race_id) != start or shown != line:
                REC.add(
                    "a click on a done card did something",
                    f"{self.p.name(miss)}: red line {line!r} to {shown!r}",
                )
            _tap(_widget(c, eid))

        return self._pressed(f"done {self.p.name(miss)}, then {self.p.name(eid)}", press, twin)

    def _record_twice(self, sc) -> bool:
        c = self.c
        if not (sc.record and sc.record_enabled) or sc.task.kind != "sprint" or sc.task.editing:
            return False
        twin = Twin(self.s)
        # A question in a burst is answered by its default: Cancel.
        twin.record(short_ok=False)
        button = c.main.surface.record_button
        double = self.s.rng.random() < 0.5

        def press():
            REC.answer = False
            try:
                if double:
                    _double_click(button, button.rect().center())
                else:
                    _tap(button, button.rect().center())
                    _tap(button, button.rect().center())
            finally:
                REC.answer = True

        how = "double-click" if double else "two presses"
        return self._pressed(f"Record Sprint, {how}", press, twin)

    def _undo_twice(self, sc) -> bool:
        c = self.c
        if not sc.undo_enabled:
            return False
        double = self.s.rng.random() < 0.5
        twin = Twin(self.s)
        twin.live.undo()
        if not double:
            # Two presses are two Undos; a double-click is one press.
            twin.live.undo()
        button = c.main.undo

        def press():
            if double:
                _double_click(button, button.rect().center())
            else:
                _tap(button, button.rect().center())
                _tap(button, button.rect().center())

        how = "double-click" if double else "two presses"
        return self._pressed(f"Undo, {how}", press, twin)

    def _dots(self, sc) -> bool:
        c = self.c
        strips = [w for w in c.main.surface.cards.cards if w.dots.isVisible()]
        if not strips:
            return False
        w = self.s.rng.choice(strips)
        before = _outcome(c.live)
        name = self.p.name(w.card.entrant_id)
        self.s.step(
            f"⋯ of {name} opened and closed",
            lambda: _tap(w.dots, w.dots.rect().center()) or True,
            offered=False,
            undo_check=False,
        )
        _pump()
        after = _outcome(c.live)
        if after != before:
            REC.add("a ⋯ closed without a pick changed the race", _differs(after, before))
        if w.property("lit"):
            REC.add("a card stays lit after its ⋯ closed", name)
        return True


def click_happy_night(s: Session) -> None:
    """Every race scored with the click-happy scorer's habits pressed through the window."""
    _show(s)
    c = s.c
    p = Player(s)
    for race in list(c.races):
        if p.begin(race.race_id):
            p.finish(ClickHappy(p))
    _night_end(s)


# ----- the careless scorer -----


class Careless:
    """The wrong rider noticed a few clicks on and fixed; both ends of a Chase; a status on a placed rider."""

    def __init__(self, p: Player) -> None:
        self.p, self.s, self.c = p, p.s, p.c
        self.done: set[str] = set()
        live = self.c.live
        self.kind = live.kind
        self.ends = self.kind == "placings" and self.s.rng.random() < 0.5

    def maybe(self) -> bool:
        p, s = self.p, self.s
        sc = p.screen
        if not _playable(sc) or sc.task.editing:
            return False
        if self.ends and "ends" not in self.done and sc.task.kind == "order":
            self.done.add("ends")
            if self._both_ends(sc):
                return True
        if "swap" not in self.done and s.rng.random() < 0.25 and self._swap(sc):
            self.done.add("swap")
            return True
        if "status" not in self.done and s.rng.random() < 0.3 and self._status(sc):
            self.done.add("status")
            return True
        return False

    def _intended(self, sc, n: int) -> list[int]:
        free = [cd for cd in sc.cards if cd.badge is None and not cd.done]
        order = [cd.entrant_id for cd in self.p._order(free)]
        if sc.task.kind == "out":
            order.reverse()
        return order[:n]

    def _swap(self, sc) -> bool:
        """Clicks b where a was meant, one to four more, then a; fixed by Undo or by moves."""
        p, s, c = self.p, self.s, self.c
        kind = sc.task.kind
        if kind not in ("order", "out", "sprint", "lap"):
            return False
        for j in range(s.rng.randint(0, 3), -1, -1):
            meant = self._intended(sc, j + 2)
            if len(meant) < j + 2:
                continue
            twin = Twin(s)
            if not all(twin.click(e) for e in meant):
                twin.close()
                continue
            after = twin.live.screen()
            if after.task.kind != kind or after.review:
                # The right clicks would end this stage: the fix would
                # be a correction of a result, not of clicks.
                twin.close()
                continue
            break
        else:
            return False
        wrong = [meant[-1], *meant[1:-1], meant[0]]
        start = _log_len(c.store, c.live.race_id)
        for e in wrong:
            s.step(f"click {p.name(e)}", lambda e=e: c.click(e), undo_check=False)
        fixes = ["undo"]
        if kind in ("order", "out"):
            fixes += ["row", "card"]
        elif kind == "sprint":
            fixes.append("card")
        fix = s.rng.choice(fixes)
        REC.coverage[f"careless: {kind} wrong by {len(wrong) - 1}, fixed by {fix}"] += 1
        if fix == "undo":
            for _ in wrong:
                s.step("Undo the wrong clicks", c.undo, undo_check=False)
            for e in meant:
                s.step(f"click {p.name(e)}", lambda e=e: c.click(e), undo_check=False)
            _against_twin(s, twin, start, "wrong rider fixed by Undo", loose=True)
            got = [(r.kind, r.payload) for r in c.live.rows()]
            if got != [(r.kind, r.payload) for r in twin.live.rows()]:
                REC.add("wrong rider fixed by Undo: the live log differs from the right clicks", "")
        else:
            self._moves(meant, fix)
            _against_twin(s, twin, start, f"wrong rider fixed by the {fix}'s moves", loose=True)
        twin.close()
        return True

    def _order_now(self) -> list[int]:
        """The placed entrants best first: the staged order, else the result rows."""
        live = self.c.live
        staged = [e for g in live.staged() for e in g]
        if staged:
            return staged
        return [r.entrant_id for r in live.screen().rows if r.entrant_id is not None]

    def _moves(self, meant: list[int], fix: str) -> None:
        """Each meant entrant moved up a place at a time into the place it was meant to have."""
        p, s, c = self.p, self.s, self.c
        out = c.live.screen().task.kind == "out"
        # Best first: an Elimination's later out holds the better place.
        target = list(reversed(meant)) if out else list(meant)
        call = c.row_action if fix == "row" else c.rider_action
        for want_at, eid in enumerate(target):
            for _ in range(len(target) + 1):
                order = self._order_now()
                block = [e for e in order if e in target]
                if block.index(eid) <= want_at:
                    break
                where = c.live.screen()
                items = (
                    [r for r in where.rows if r.entrant_id == eid]
                    if fix == "row"
                    else [k for k in where.cards if k.entrant_id == eid]
                )
                keys = {k for item in items for k, _ in item.actions}
                if "move_up" not in keys:
                    REC.add(
                        f"careless: Move Up is not offered on the {fix} the fix needs",
                        f"{p.name(eid)}: {sorted(keys)}",
                    )
                    return
                s.step(
                    f"{fix} {p.name(eid)}: Move Up",
                    lambda e=eid: call(e, "move_up"),
                    undo_check=False,
                )

    def _both_ends(self, sc) -> bool:
        """A Chase placed from the front and the back at once, against the order clicked from the front."""
        from madtracker.control.race import PLACE_LAST

        p, s, c = self.p, self.s, self.c
        if c.live.staged() or c.live.staged_tail():
            return False
        free = [cd for cd in sc.cards if cd.badge is None and not cd.done]
        if len(free) < 4:
            return False
        meant = [cd.entrant_id for cd in p._order(free)]
        twin = Twin(s)
        for e in meant:
            twin.click(e)
        start = _log_len(c.store, c.live.race_id)
        front, back = 0, len(meant) - 1
        while front <= back and c.live.screen().task.kind == "order":
            card = next(k for k in c.live.screen().cards if k.entrant_id == meant[back])
            last = any(k == PLACE_LAST for k, _ in card.actions)
            if last and front < back and s.rng.random() < 0.5:
                e = meant[back]
                s.step(
                    f"card {p.name(e)}: Place Last",
                    lambda e=e: c.rider_action(e, PLACE_LAST),
                    undo_check=False,
                )
                back -= 1
            else:
                e = meant[front]
                s.step(f"click {p.name(e)}", lambda e=e: c.click(e), undo_check=False)
                front += 1
        REC.coverage["careless: a Chase placed from both ends"] += 1
        _against_twin(s, twin, start, "both ends of a Chase", loose=True)
        twin.close()
        return True

    def _status(self, sc) -> bool:
        """A status marked from the row of a rider already placed, where the row offers one."""
        p, s, c = self.p, self.s, self.c
        offers = [
            (r.entrant_id, k)
            for r in sc.rows
            if r.entrant_id is not None and (r.staged or r.place_text.isdigit())
            for k, _ in r.actions
            if k in ("dnf", "dq", "withdrawn", "out_of_finish")
        ]
        if not offers:
            return False
        eid, key = s.rng.choice(offers)
        twin = Twin(s)
        twin.live.act(eid, key)
        start = _log_len(c.store, c.live.race_id)
        s.step(
            f"row {p.name(eid)}: {key} after placing",
            lambda: c.row_action(eid, key),
            undo_check=False,
        )
        REC.coverage[f"careless: {key} on a placed rider's row"] += 1
        _against_twin(s, twin, start, f"{key} on a placed rider's row")
        twin.close()
        return True


def careless_night(s: Session) -> None:
    """Every race with a wrong click noticed late and fixed, as the careless scorer does."""
    c = s.c
    p = Player(s)
    for race in list(c.races):
        if p.begin(race.race_id):
            p.finish(Careless(p))
    _night_end(s)


# ----- the panicked scorer -----


def _to_result(p: Player) -> None:
    from play import MAX_STEPS

    for _ in range(MAX_STEPS):
        sc = p.screen
        if sc.review or sc.task.kind == "final":
            return
        if not p.advance():
            return


def _undo_to_start(s: Session, label: str) -> None:
    """Undo until there is nothing to undo, then the start list's facts."""
    from madtracker.control.program import is_scored
    from madtracker.control.race import STAGED_KEY
    from madtracker.store.store import VOID_KIND

    c = s.c
    for _ in range(3000):
        if not c.live.screen().undo_enabled:
            break
        s.step(f"Undo ({label})", c.undo, undo_check=False)
    rid = c.live.race_id
    if c.live.rows():
        REC.add("undone to the start, the live log is not empty", f"{len(c.live.rows())} rows")
    staged = c.store.get_setting(STAGED_KEY.format(race_id=rid))
    if staged and (staged.get("groups") or staged.get("tail") or staged.get("sprint") is not None):
        REC.add("undone to the start, the staged setting row is not empty", repr(staged)[:600])
    if is_scored(c.store, c.store.race(rid)):
        REC.add("undone to the start, Edit Race still keeps the field", c.store.race(rid).state)
    rows = c.store.actions(rid)
    ids = [r.action_id for r in rows]
    voided = [r.voids_action_id for r in rows if r.kind == VOID_KIND]
    entries = {r.action_id for r in rows if r.kind != VOID_KIND}
    if ids != sorted(ids) or sorted(voided) != sorted(entries) or len(set(voided)) != len(voided):
        REC.add(
            "undone to the start, the log has a gap",
            f"entries {sorted(entries)[:20]}, voided {sorted(voided)[:20]}",
        )


def panicked_night(s: Session) -> None:
    """Every race scored to its result, undone to the start, and scored again, twice."""
    import random

    from harness import strip_undo

    c = s.c
    p = Player(s)
    for race in list(c.races):
        if not p.begin(race.race_id):
            continue
        seed = s.rng.random()
        form = dict(p.form)
        ends = []
        for k in range(3):
            # The officials call the same race again: the same form and luck.
            p.rng = random.Random(seed)
            p.form, p.jostle = dict(form), {}
            _to_result(p)
            ends.append(strip_undo(c.live.screen()))
            if k < 2:
                _undo_to_start(s, f"pass {k + 1}")
        p.rng = s.rng
        REC.coverage["panicked: undone to the start twice"] += 1
        for k in (1, 2):
            if ends[k] != ends[0]:
                REC.add(f"pass {k + 1} ends at another result", diff_text(ends[0], ends[k]))
        p.finish()
    _night_end(s)


# ----- the fast finish -----


def _fast_clicks(s: Session, p: Player, n: int) -> None:
    """``n`` clicks on the cards with no event-loop turn between, then the order checked."""
    c = s.c
    sc = p.screen
    kind = sc.task.kind
    rid = c.live.race_id
    first = len(c.live.actions())
    free = [
        cd.entrant_id for cd in p._order([k for k in sc.cards if k.badge is None and not k.done])
    ]
    if kind == "out":
        free.reverse()
    clicked = []
    for eid in free[:n]:
        if c.live.screen().task.kind != kind:
            break
        w = _widget(c, eid)
        if w is None:
            break
        if s.step(
            f"fast click {p.name(eid)}",
            lambda w=w: _tap(w) or True,
            offered=False,
            undo_check=False,
        ):
            clicked.append(eid)
    REC.coverage[f"fast finish: {len(clicked)} clicks in a {kind}"] += 1
    if kind == "sprint" and c.live.screen().record_enabled:
        s.step("Record Sprint", c.record_sprint, undo_check=False)
    acts = c.live.actions()[first:]
    if kind == "out":
        got = [e for a in acts if a.kind == "eliminated" for e in a.entrant_ids]
    elif kind == "lap":
        got = [e for a in acts if a.kind == "sprint_result" for g in a.places for e in g]
    else:
        done = [a for a in acts if a.kind in ("finish_order", "sprint_result")]
        got = (
            [e for g in done[-1].places for e in g]
            if done
            else [e for g in c.live.staged() for e in g]
        )
    if got[: len(clicked)] != clicked:
        REC.add(
            "the order recorded is not the order clicked",
            f"race {rid} {kind}: clicked {clicked}, recorded {got}",
        )


def fast_finish_night(s: Session) -> None:
    """Twelve clicks as fast as the loop allows in every race's finish, on fields big enough for them."""
    _show(s)
    c = s.c
    p = Player(s)
    for race in list(c.races):
        if not p.begin(race.race_id):
            continue
        team = c.live.team_format
        _set_field(s, 12 if team else 14)
        p.begin(race.race_id)
        live = c.live
        if live.kind in SPRINT_KINDS:
            # The earlier sprints as called, then the final one fast.
            for _ in range(600):
                sc = p.screen
                last = sc.task.kind == "final_sprint" or sc.task.sprint_no == live.sprint_count
                if not _playable(sc) or last:
                    break
                if not p.advance():
                    break
        sc = p.screen
        if _playable(sc) and not sc.task.editing:
            _fast_clicks(s, p, 12)
        p.finish()
    _night_end(s)


# ----- the fat finger -----


class FatFinger:
    """A click meant for a card that lands on its ⋯ strip, a lap button, the next card, or a done badge."""

    def __init__(self, p: Player, rate: float = 0.3) -> None:
        self.p, self.s, self.c = p, p.s, p.c
        self.rate = rate

    def maybe(self) -> bool:
        from PySide6.QtCore import QPoint

        p, s, c = self.p, self.s, self.c
        sc = p.screen
        if not _playable(sc) or s.rng.random() >= self.rate:
            return False
        _pump()
        grid = c.main.surface.cards
        card = _next_card(p)
        w = _widget(c, card.entrant_id) if card is not None else None
        misses = []
        if w is not None:
            if w.dots.isVisible():
                misses.append(("⋯ strip", w, w.dots.geometry().center()))
            for lap in (w.lap_up, w.lap_down):
                if lap.isVisible():
                    misses.append((f"{lap.text()} button", w, lap.geometry().center()))
            at = grid.cards.index(w)
            for k in (at - 1, at + 1):
                if 0 <= k < len(grid.cards):
                    other = grid.cards[k]
                    misses.append(("the card beside it", other, other.rect().center()))
        for other in grid.cards:
            if other.card.done and other.badge_rect() is not None:
                misses.append(("a done card's badge", other, other.badge_rect().center()))
                break
        if not misses:
            return False
        what, where, local = s.rng.choice(misses)
        grid.ensureWidgetVisible(where)
        _pump()
        at: QPoint = where.mapTo(grid.body, local)
        before = _outcome(c.live)
        start = _log_len(c.store, c.live.race_id)
        line = c.main.surface.problem.text()
        hit = []
        s.step(
            f"meant a card, hit {what}",
            lambda: hit.append(_hit(grid.body, at)) or True,
            offered=False,
            undo_check=False,
        )
        _pump()
        REC.coverage[f"fat finger: {what}"] += 1
        if what == "a done card's badge":
            # A done card's click does nothing: no entry, and no red line.
            shown = c.main.surface.problem.text()
            if (
                _log_len(c.store, c.live.race_id) != start
                or _outcome(c.live) != before
                or shown != line
            ):
                REC.add(
                    "a miss on a done card's badge did something",
                    f"red line {line!r} to {shown!r}\n" + _differs(_outcome(c.live), before),
                )
            return True
        if _log_len(c.store, c.live.race_id) == start and _outcome(c.live) == before:
            return True
        s.step("Undo the miss", c.undo, undo_check=False)
        after = _outcome(c.live)
        if after != before:
            REC.add(
                f"a miss on {what} takes more than one Undo",
                f"hit {type(hit[0]).__name__ if hit else '?'}\n" + _differs(after, before),
            )
        return True


def fat_finger_night(s: Session) -> None:
    """Every race scored with the fat finger's misses, each landed through the window's geometry."""
    _show(s)
    c = s.c
    p = Player(s)
    for race in list(c.races):
        if p.begin(race.race_id):
            p.finish(FatFinger(p))
    _night_end(s)


# ----- the late change -----


class _Renaming:
    """File > Edit Riders answered with one rider renamed, as the dialog's Save does."""

    rider_id = 0
    first = ""

    @classmethod
    def make(cls):
        from PySide6.QtWidgets import QDialog

        class Dialog(QDialog):
            def __init__(self, store, _event, parent=None, **_k):
                super().__init__(parent)
                self.store = store

            def exec(self):
                self.store.update_rider(cls.rider_id, first_name=cls.first)
                return QDialog.DialogCode.Accepted

        return Dialog


class LateChange:
    """A rider added or taken out where Edit Race allows it, a rider renamed, a bib changed."""

    def __init__(self, p: Player, changes: int = 2) -> None:
        self.p, self.s, self.c = p, p.s, p.c
        self.left = changes

    def maybe(self) -> bool:
        from madtracker.control.program import is_scored

        p, s, c = self.p, self.s, self.c
        sc = p.screen
        if self.left <= 0 or not _playable(sc) or sc.task.editing or s.rng.random() >= 0.12:
            return False
        self.left -= 1
        options = ["rename", "bib"]
        if is_scored(c.store, c.store.race(c.live.race_id)):
            # Edit Race locks a scored race's field: no rider in or out.
            REC.coverage["late change: a scored race keeps its field"] += 1
        else:
            options += ["add", "remove"]
        what = s.rng.choice(options)
        return self._change(what, sc)

    def _riders(self) -> list[int]:
        c = self.c
        return [e.rider_id for e in c.store.race_entries(c.live.race_id)]

    def _change(self, what: str, sc) -> bool:
        p, s, c = self.p, self.s, self.c
        rid = c.live.race_id
        marks = {
            k.entrant_id: (k.done, k.done_text, k.done_status, k.done_tip, k.badge)
            for k in sc.cards
        }
        do = getattr(self, "_" + what)()
        if do is None:
            return False
        label, write, expect = do
        grid = c.main.surface.cards
        seen: list[list[int]] = []
        draw = grid.set_cards

        def spy(cards):
            seen.append([k.entrant_id for k in cards])
            return draw(cards)

        grid.set_cards = spy
        try:
            s.step(label, write, undo_check=False)
            _pump()
        finally:
            del grid.set_cards
        REC.coverage[f"late change: {what}"] += 1
        if c.live is None or c.live.race_id != rid:
            REC.add(f"late change {what}: not back on the race", "")
            return True
        now = c.live.screen()
        # Each new field the grid was given; the setup screen's empty
        # surface in between is no field.
        drawn: list[list[int]] = []
        for ids in seen:
            if ids and (not drawn or ids != drawn[-1]):
                drawn.append(ids)
        if len(drawn) > 2 or (drawn and drawn[-1] != [k.entrant_id for k in now.cards]):
            REC.add(
                f"late change {what}: the grid took the field more than once", repr(drawn)[:800]
            )
        if what == "remove":
            # The store lets the staged clicks go with a rider taken out
            # (they name riders by id); an unscored race has nothing else.
            if any(k.done for k in now.cards) or c.live.staged() or c.live.staged_tail():
                REC.add("late change remove: clicks stand after a rider was taken out", "")
        else:
            for k in now.cards:
                mark = (k.done, k.done_text, k.done_status, k.done_tip, k.badge)
                if k.entrant_id in marks and marks[k.entrant_id] != mark:
                    REC.add(
                        f"late change {what}: a card changed its state",
                        f"{p.name(k.entrant_id)}: {marks[k.entrant_id]} -> {mark}",
                    )
        if expect is not None:
            expect(now)
        return True

    def _in_setup(self, write):
        c = self.c

        def go() -> bool:
            c.open_setup()
            try:
                write()
            finally:
                c.close_setup()
            return True

        return go

    def _add(self):
        c = self.c
        race = c.store.race(c.live.race_id)
        team = c.live.team_format
        size = len(c.live.roster.ids) + 1
        field, teams = _field_of(self.s, race, size, team)
        write = self._in_setup(
            lambda: c.store.save_race(race.event_id, race.race_id, {}, field, teams)
        )

        def expect(now):
            if len(now.cards) != size:
                REC.add("late change add: the grid lacks the new entrant", f"{len(now.cards)}")

        return ("Edit Race: one more " + ("team" if team else "rider"), write, expect)

    def _remove(self):
        c = self.c
        race = c.store.race(c.live.race_id)
        team = c.live.team_format
        if len(c.live.roster.ids) <= 3:
            return None
        if team:
            shapes = [
                (t.name, t.color, t.color_hex, list(t.members)) for t in c.store.teams(race.race_id)
            ]
            shapes.pop(self.s.rng.randrange(len(shapes)))
            field, teams = [m for t in shapes for m in t[3]], shapes
        else:
            field = self._riders()
            field.remove(self.s.rng.choice(field))
            teams = None
        write = self._in_setup(
            lambda: c.store.save_race(race.event_id, race.race_id, {}, field, teams)
        )
        return ("Edit Race: one " + ("team" if team else "rider") + " out", write, None)

    def _rename(self):
        from madtracker.ui import setup

        c = self.c
        rider = self.s.rng.choice(self._riders())
        old = c.store.rider(rider)
        first = next(f for f in FIRST if f != old.first_name)
        _Renaming.rider_id, _Renaming.first = rider, first
        dialog = _Renaming.make()

        def write() -> bool:
            real = setup.RidersDialog
            setup.RidersDialog = dialog
            try:
                c.manage_riders()
            finally:
                setup.RidersDialog = real
            return True

        def expect(now):
            if c.live.team_format:
                return
            card = next((k for k in now.cards if k.entrant_id == rider), None)
            if card is not None and first not in card.entry.names[0]:
                REC.add("late change rename: the card keeps the old name", card.entry.names[0])

        return (f"Edit Riders: {old.first_name} {old.last_name} renamed {first}", write, expect)

    def _bib(self):
        from madtracker.control.roster import roster_bib_refusal
        from madtracker.ui.setup.screen import BIB

        c = self.c
        sc = c.live.screen()
        live_ids = {k.entrant_id for k in sc.cards if not k.done and k.badge is None}
        if c.live.team_format:
            riders = [
                m for t in c.store.teams(c.live.race_id) if t.team_id in live_ids for m in t.members
            ]
        else:
            riders = [r for r in self._riders() if r in live_ids]
        if not riders:
            return None
        rider = self.s.rng.choice(riders)
        event_id = c.live.race.event_id
        used = {e.bib for e in c.store.entries(event_id) if e.bib is not None}
        bib = next(b for b in range(1, 1000) if b not in used and b % 7 == self.s.rng.randrange(7))
        if roster_bib_refusal(c.store, event_id, rider, bib):
            return None

        def write() -> bool:
            c.open_setup()
            try:
                setup = c.main.setup
                row = setup.row_of(rider)
                setup.roster.item(row, BIB).setText(str(bib))
                _pump()
            finally:
                c.close_setup()
            return c.store.entry(event_id, rider).bib == bib

        def expect(now):
            if c.live.team_format:
                return
            card = next((k for k in now.cards if k.entrant_id == rider), None)
            if card is None or card.entry.bibs[0] != str(bib):
                REC.add(
                    "late change bib: the card keeps the old bib", repr(card and card.entry.bibs)
                )

        return (f"Edit Event: {c.live.name(rider)} takes bib {bib}", write, expect)


def late_change_night(s: Session) -> None:
    """Fields of every size, each race changed mid-race where the app allows it."""
    c = s.c
    p = Player(s)
    races = list(c.races)
    size = _sizes(s)
    for i, race in enumerate(races):
        if not p.begin(race.race_id):
            continue
        _set_field(s, size(i, c.live.team_format))
        p.begin(race.race_id)
        p.finish(LateChange(p))
    _night_end(s)


# ----- the corrector -----


def _leavers_before(live, sprint: int) -> set[int]:
    """Who had left the race (a status, a withdrawal, a mishap) before the sprint was recorded."""
    out: set[int] = set()
    for a in live.actions():
        if a.kind == "sprint_result" and a.sprint_no == sprint:
            return out
        if a.kind in ("status", "withdrawn", "out_of_finish"):
            out.add(a.entrant_id)
    return out


def _check_reopened(s: Session, sprint: int) -> None:
    c = s.c
    sc = c.live.screen()
    want = _leavers_before(c.live, sprint) & set(c.live.roster.ids)
    got = {k.entrant_id for k in sc.cards if k.done}
    if got != want:
        REC.add(
            f"reopened Sprint {sprint}: the done cards are not who had left by then",
            f"done {sorted(got)}, left by then {sorted(want)}",
        )


def _until(p: Player, sprints: int) -> bool:
    """Ordinary steps until ``sprints`` are recorded; False if the race ends or sticks first."""
    for _ in range(600):
        if len(p.c.live.recorded_sprints()) >= sprints:
            return True
        if not _playable(p.screen) or not p.advance():
            return False
    return False


def _corrector(s: Session, p: Player) -> None:
    """A DNF before Sprint 2, a withdrawal at Sprint 3, then Sprint 2 reopened after Sprint 4."""
    from harness import strip_undo

    c = s.c

    def mark(key: str) -> None:
        sc = p.screen
        racing = [
            k
            for k in sc.cards
            if not k.done and k.badge is None and any(a == key for a, _ in k.actions)
        ]
        if racing:
            e = s.rng.choice(racing).entrant_id
            s.step(f"card {p.name(e)}: {key}", lambda: c.rider_action(e, key), undo_check=False)

    if not _until(p, 1):
        return
    mark("dnf")
    if not _until(p, 2):
        return
    mark("withdrawn")
    if not _until(p, 4):
        return
    if 2 not in p.screen.open_sprints:
        return
    s.step("reopen Sprint 2", lambda: c.reopen_sprint(2), undo_check=False)
    _check_reopened(s, 2)
    REC.coverage["corrector: Sprint 2 reopened after Sprint 4"] += 1
    for _ in range(s.rng.randint(1, 3)):
        p.do("move_down") or p.do("move_up")
    s.step("Record Sprint (correction)", c.record_sprint, undo_check=False)
    sc = p.screen
    if 3 in sc.open_sprints and not sc.task.editing:
        before = strip_undo(sc)
        s.step("reopen Sprint 3", lambda: c.reopen_sprint(3), undo_check=False)
        _check_reopened(s, 3)
        p.do("move_up")
        s.step("Cancel Correction", c.cancel_edit, undo_check=False)
        after = strip_undo(p.screen)
        if after != before:
            REC.add("a cancelled correction left the race changed", diff_text(before, after))
        REC.coverage["corrector: Sprint 3 reopened and cancelled"] += 1


def _set_sprints(s: Session, count: int) -> None:
    """Edit Race's sprint count raised to ``count`` before the race is scored, as the dialog allows."""
    from madtracker.control.program import is_scored

    c = s.c
    race = c.store.race(c.live.race_id)
    rules = dict(race.rules or {})
    if is_scored(c.store, race) or (rules.get("sprint_count") or count) >= count:
        return

    def edit() -> bool:
        c.open_setup()
        try:
            rules["sprint_count"] = count
            field = [e.rider_id for e in c.store.race_entries(race.race_id)]
            c.store.save_race(race.event_id, race.race_id, {"rules": rules}, field)
        finally:
            c.close_setup()
        return c.live is not None and c.live.sprint_count == count

    s.step(f"Edit Race: {count} sprints", edit, undo_check=False)


def corrector_night(s: Session) -> None:
    """Every race scored; each sprint race given five sprints and corrected as the corrector does."""
    c = s.c
    p = Player(s)
    for race in list(c.races):
        if not p.begin(race.race_id):
            continue
        if c.live.kind in SPRINT_KINDS:
            _set_sprints(s, 5)
            p.begin(race.race_id)
            _corrector(s, p)
        p.finish()
    _night_end(s)


PERSONAS = {
    "careful": careful_night,
    "click-happy": click_happy_night,
    "careless": careless_night,
    "panicked": panicked_night,
    "fast-finish": fast_finish_night,
    "fat-finger": fat_finger_night,
    "late-change": late_change_night,
    "corrector": corrector_night,
}
