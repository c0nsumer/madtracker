"""The three nights: clean, messy, and switch.

Each plays every race of the demo's program (one of every format the
demo has) on its own copy of the demo file, through the controller
methods the window calls, then exports everything the File menu offers.
"""

from __future__ import annotations

from harness import REC, Session, diff_text
from play import Mishaps, Player


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
