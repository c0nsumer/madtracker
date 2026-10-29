"""Process entry point and the wiring between the store, the window and the TV.

``main`` parses arguments and starts Qt. ``AppController`` owns the
store, the live race, the window and the scoreboard, and routes every
signal of the window to the controller and every change back to the
screens. It stays thin: what a click means lives in
``madtracker.control.race``, what a screen shows in ``madtracker.ui``.
"""

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from madtracker import APP_NAME, applog

SCREEN_KEY = "scoreboard/screen_name"
SELF_TEST_LOG = "self-test.log"
EVENT_KEY = "ui/event_id"
# The data file last opened on this machine. A per-machine QSettings
# value, not a store setting: it says where the store is.
DATA_FILE_KEY = "data/file"
# The race that was live, kept in the file so a copy opened on another
# laptop selects it too (design section 12).
LIVE_RACE_KEY = "ui/live_race_id"
# The scoring window's place and maximized state when last quit, from
# QWidget.saveGeometry(). Where the window sits is a fact about this
# machine and its displays, so it lives here and never in the data file,
# which travels between laptops; and it is not in the Settings dialog,
# which holds venue values only.
WINDOW_KEY = "window/geometry"
DATA_FILE_FILTER = "MadTracker Data Files (*.sqlite);;All Files (*)"
BACKUP_FAILED = "Automatic backup failed"
# The disconnect box's title, which also finds it to close when the board is back.
LOST_DISPLAY_TITLE = "Scoreboard Display"
# The box is found again by this name: a window title is not kept by a
# QMessageBox on macOS, where it has no title bar.
LOST_DISPLAY_BOX = "lostDisplayBox"
ALREADY_OPEN = (
    f"{APP_NAME} is already open on this file (another window). Use that window, or close it first."
)
# Notices about the data file, one paragraph each: a path has a line of
# its own, as a message box otherwise breaks it after "C:".
NOTICE_GAP = "\n\n"
# Help > Demo Data File... builds its sample data file in this folder,
# under the folder the app started with, under its own name: a second
# madtracker.sqlite reads as a copy of the venue's file.
DEMO_FOLDER = "demo"
DEMO_FILE_NAME = "demo.sqlite"
# The two answers: the demo as it was last left, or built again (the
# same riders, events, and results every time). The path on a line of
# its own, as every notice shows one.
OPEN_PREVIOUS = "Open Previous"
CREATE_NEW = "Create New"
DEMO_QUESTION = (
    "Open or create a new demo data file?\n\nA new demo data file contains sample riders, two"
    f" events, and a race of every format. The next time {APP_NAME} starts it returns to"
    " your own data file. You can manually reopen the demo at:\n{path}"
)
# The empty window after a failed rebuild of the demo, which was let go first.
NO_FILE_OPEN = "No data file is open. Choose one: File > Open Data File..."
# A crashed copy leaves its lock file behind. QLockFile treats a lock
# whose process is gone as stale at once, and one older than this as
# stale only when the holder no longer has it locked natively (flock on
# Unix, an open handle on Windows), so a live window keeps its file
# however long the night runs and a crash never locks the scorer out.
STALE_LOCK_MS = 30_000
SLOW_COMMIT_MS = 200.0
# A result's backup waits this long after the click that made it, so the
# screen and the board show the result first: the backup and its check
# would be most of that click (131 ms of it on a season-sized file). A
# timer with no delay runs before the repaint, as Qt posts paints at low
# priority; a real interval lets the posted layout and paint rounds go
# first on every platform's event loop.
RESULT_BACKUP_DELAY_MS = 50
# An unexpected error, said once per distinct traceback in a session: a
# bug in a repaint would otherwise raise a box per frame. It may come
# after the entry was written (a redraw, say), so it says only what is
# known: the race on screen is what the file holds.
CRASH_TEXT = (
    "Something went wrong. Check the current race before entering anything again."
    "\n\nThe details are in the log file:\n{log}"
)
# The red line for a bug inside a click, by whether the log grew during it
# (None when that could not be read).
UNEXPECTED_LINE = {
    True: "Recorded, but something went wrong ({kind}). Check the current race."
    " Details are in {log}.",
    False: "Not recorded: something went wrong ({kind}). Details are in {log}.",
    None: "Something went wrong ({kind}). Check the current race before entering"
    " anything again. Details are in {log}.",
}
# A disk that refuses the file fails every click until the scorer acts, so
# the red line names the cause and one box a session says what to do.
DISK_LINE = {
    "full": "Not recorded: the disk is full.",
    "unwritable": "Not recorded: the data file could not be written.",
}
DISK_BOX = {
    "full": (
        "Disk Full",
        "The data file could not be written (the disk is full). Nothing is recorded"
        " until there is room. Free some space, or quit and move the data file to"
        " another disk.",
    ),
    "unwritable": (
        "Data File Not Written",
        "The data file could not be written. Nothing is recorded until it can be"
        " written again. Check that the drive it is on is still connected, or quit and"
        " move the data file to another disk.",
    ),
}
READ_ONLY_NOTICE = (
    "This data file is read-only, so nothing can be scored or changed in it:\n{path}"
    "\n\nYou can look at it and export its results. To score, copy it to a folder you"
    " can write to, then open the copy (File > Open Data File...)."
)


def damaged_notice(path: Path, data_dir: Path) -> str:
    """What a file that will not open (or opened damaged) tells the scorer to do next.

    The raw SQLite text ("btreeInitPage() returns error code 11") goes to
    the log; the scorer gets the next step and the folder it is in, since
    the backups sit in a hidden per-user folder on Windows and macOS.
    """
    from madtracker.control import venue

    return (
        f"The data file could not be opened; it may be damaged:\n{path}\n\n"
        "Open its newest backup: File > Open Data File..., then the folder:\n"
        f"{venue.automatic_backup_dir(data_dir)}\n\n"
        "The backup opens as a new data file; see Help > Backups."
    )


def needs_update_notice(path: Path) -> str:
    """A file from an earlier version that this copy cannot update in place: not damaged."""
    return (
        f"The data file is from an earlier version of {APP_NAME} and needs updating,"
        f" but it cannot be written here:\n{path}\n\n"
        "If another program has it open, close that first. If the file or its folder"
        " is read-only, copy it to a folder you can write to, then open the copy"
        " (File > Open Data File...)."
    )


def no_wal_notice(path: Path) -> str:
    """A file on a drive that cannot do WAL journaling: not damaged, only in the wrong place."""
    return (
        f"The data file cannot be opened where it is:\n{path}\n\n"
        f"The drive it is on does not allow the journaling {APP_NAME} needs,"
        " which is usual for a network share. Copy it to a folder on this"
        " computer, then open the copy (File > Open Data File...)."
    )


def cannot_create_notice(path: Path) -> str:
    return (
        f"The data file could not be created:\n{path}\n\n"
        "The folder may be missing or read-only. Choose another file or folder"
        " (File > New Data File... or File > Open Data File...)."
    )


# The rider actions that ask first, by the title and verb of the question.
OUTCOME_ASKS = {
    "dnf": "Did Not Finish",
    "dns": "Did Not Start",
    "out_of_finish": "Out of the Finish (Mishap)",
    "withdrawn": "Withdrawn",
}
# The verb where the title is not one: the question names the mark, the
# button what the scorer does.
OUTCOME_VERBS = {"withdrawn": "Withdraw"}
# The race's own call (USAC 2M6, 2N5), asked in the shape of the others.
END_RACE_QUESTION = "End the race now? Results will be recorded as-is."


def _clear_beside(data_file: Path) -> None:
    """Remove a data file's -wal, -shm, and clean-close marker before the file is replaced.

    A -wal left beside a replaced file would be applied to the new one
    at its first open, which corrupts it; a marker would report the old
    file's unclean close as the new file's.
    """
    from madtracker.control.backups import marker_path

    for extra in (Path(f"{data_file}-wal"), Path(f"{data_file}-shm"), marker_path(data_file)):
        extra.unlink(missing_ok=True)


# What _newest_action gives when the log cannot be read.
_UNREAD = object()


@dataclass(frozen=True)
class _Unexpected:
    """A bug inside a scorer's action, with whether the race's log grew during it.

    ``recorded`` is None when the log could not be read, so the red line
    claims neither way.
    """

    error: Exception
    recorded: bool | None


@dataclass
class _Switch:
    """A file switch in progress, carried from the checks through the swap.

    ``still`` is the refusal's "Still open" suffix, blank once the open
    file is let go. A restore sets ``restored``, where the backup is put
    back, and ``incoming``, its copy beside that target until the swap;
    ``saved`` is the copy taken of what the target held, so a failed open
    can put it back.
    """

    path: Path
    create: bool
    title: str
    still: str
    copy: object
    restore_to: Path | None
    remember: bool
    restored: Path | None = None
    incoming: Path | None = None
    saved: Path | None = None
    replacing_open: bool = False


def _same_file(a: Path, b: Path) -> bool:
    """Whether two paths name one file, however each is spelled.

    Comparing the paths misses "Backups\\x.sqlite" against "backups\\x.sqlite"
    on Windows and macOS, and a ".." or a link anywhere: a restore would
    then go over the backup it was restoring, or over the open file without
    letting it go first.
    """
    try:
        return os.path.samefile(a, b)
    except OSError:
        return Path(a).absolute() == Path(b).absolute()


class AppController:
    """Owns the store, both windows, and the race being scored."""

    def __init__(self, app, demo: bool = False, settings=None, data_dir=None) -> None:
        from PySide6.QtCore import QSettings

        from madtracker.board.window import ScoreboardWindow
        from madtracker.store.paths import DATABASE_FILE_NAME
        from madtracker.ui.window import MainWindow

        self.app = app
        self.settings = settings if settings is not None else QSettings("madtracker", "madtracker")
        self.main = MainWindow()
        self.board = ScoreboardWindow()
        self.boards = (self.board, self.main.board_preview)
        self.board_screen: str | None = None
        self.board_wanted = True
        self._lost_display = False
        # A disconnect box posted and not yet opened, so a fast unplug,
        # replug, and unplug posts one box, not two.
        self._lost_box_posted = False
        self._slow_disk_reported = False
        self._disk_refusal_reported = False
        # Every launch starts on the logo so the TV cannot show last
        # week's race until the scorer flips it.
        self.board_live = False
        for b in self.boards:
            b.set_live(False)

        self.store = None
        # The QLockFile beside the open file; see _take_lock.
        self._lock = None
        self.event = None
        self.races: list = []
        self.live = None
        self._known_state: dict[int, str] = {}
        # A result's backup waiting for its timer; see _run_result_backup.
        self._backup_pending = False
        self._notice: str | None = None
        self.recovered = False
        # The open file failed its integrity check; no event is opened from it.
        self.damaged = False

        self.demo = demo
        self.remember_file = data_dir is None and not demo
        expected = None
        if data_dir is not None:
            self.data_path = Path(data_dir) / DATABASE_FILE_NAME
        elif demo:
            self.data_path = Path(tempfile.mkdtemp(prefix="madtracker-demo-")) / DATABASE_FILE_NAME
        else:
            self.data_path, expected = self._remembered_file()
        # Where Help > Open Demo Data File builds, fixed for the session. For a
        # plain start it is the per-user folder, not the remembered file's:
        # the remembered file can be the demo itself, opened by hand, and
        # the next demo would otherwise be built inside its folder.
        if data_dir is not None or demo:
            self.base_dir = self.data_path.parent
        else:
            from madtracker.store.paths import default_data_dir

            self.base_dir = default_data_dir()

        applog.use_folder(self.data_dir)
        self._connect()
        self.open_store(expected)
        self._log_session()
        if self.store is not None and not self.damaged:
            if demo:
                from madtracker.control.demo import seed_demo

                self._open_guarded(lambda: self.open_event(seed_demo(self.store)))
            else:
                self._open_guarded(self._open_last_event)

    @property
    def data_dir(self) -> Path:
        return self.data_path.parent

    def _log_session(self) -> None:
        from PySide6.QtGui import QGuiApplication

        displays = [
            f"{s.name() or 'unnamed'} {s.geometry().width()}x{s.geometry().height()}"
            f" at {s.devicePixelRatio():g}x"
            for s in QGuiApplication.screens()
        ]
        applog.session_start(self.data_path, displays)

    def _open_guarded(self, open_it) -> bool:
        """Open an event from the file; a file that fails its first reads opens as damaged.

        A table dropped by another tool passes every check, then the first
        read of it fails at startup, and the file is remembered, so every
        start after that would fail too.
        """
        import sqlite3

        from madtracker.store import StoreError

        try:
            open_it()
        except (StoreError, sqlite3.Error, ValueError) as exc:
            applog.error(
                f"Could not read {self.data_path}\n"
                + applog.traceback_text(type(exc), exc, exc.__traceback__)
            )
            self._show_damaged()
            self.main.report_failure(self._notice, title="Data File")
            return False
        return True

    def _show_damaged(self) -> None:
        self.damaged = True
        self._notice = damaged_notice(self.data_path, self.data_dir)
        self.event = None
        self.races = []
        self.live = None
        self.main.set_event("", "")
        self.main.set_races([], None)
        self.main.show_empty(self._notice)
        self._sync_live()
        self._sync_menus()

    def _sync_menus(self) -> None:
        """A damaged file, or none, offers only another file: everything else would read it."""
        self.main.set_file_usable(self.store is not None and not self.damaged)

    def _remembered_file(self) -> tuple[Path, Path | None]:
        from madtracker.store.paths import default_database_path

        default = default_database_path()
        value = self.settings.value(DATA_FILE_KEY, None)
        if not value:
            return default, None
        path = Path(str(value))
        if path.is_file():
            return path, None
        return default, path

    def _connect(self) -> None:
        m = self.main
        m.race_selected.connect(self.select_race)
        m.setup_requested.connect(self.open_setup)
        m.setup_done.connect(self.close_setup)
        m.setup.changed.connect(self._after_setup_change)
        m.card_clicked.connect(self.click)
        m.rider_action.connect(self.rider_action)
        m.race_action.connect(self.race_action)
        m.record_requested.connect(self.record_sprint)
        m.rest_together_requested.connect(self.place_rest_together)
        m.row_action.connect(self.row_action)
        m.sprint_clicked.connect(self.reopen_sprint)
        m.final_requested.connect(self.mark_final)
        m.reopen_requested.connect(self.reopen_race)
        m.cancel_edit_requested.connect(self.cancel_edit)
        m.live_toggled.connect(self.choose_board_face)
        m.undo_requested.connect(self.undo)
        m.new_event_requested.connect(self.new_event)
        m.open_event_requested.connect(self.pick_event)
        m.riders_requested.connect(self.manage_riders)
        m.new_file_requested.connect(self.new_data_file)
        m.open_file_requested.connect(self.open_data_file)
        m.open_demo_requested.connect(self.open_demo_file)
        m.export_program_requested.connect(self.export_program)
        m.export_pdf_requested.connect(self.export_pdf)
        m.export_csv_requested.connect(self.export_csv)
        m.standings_requested.connect(self.open_standings)
        m.backup_requested.connect(self.backup_now)
        m.settings_requested.connect(self.edit_settings)
        m.quit_requested.connect(self.quit)
        m.open_data_folder_requested.connect(self.open_data_folder)
        m.display_chosen.connect(self.choose_screen)
        self.app.screenAdded.connect(self._screen_added)
        self.app.screenRemoved.connect(self._screen_removed)
        # Closing the scoreboard's window takes it down, as Scoreboard >
        # None does; only the operator window quits the program.
        self.board.close_requested.connect(lambda: self.show_board(False))
        self.app.aboutToQuit.connect(self.close)
        # The Display menu says where the board would go from the first
        # look, before start() places it; the board's shown state waits
        # for start(), since it is not up yet.
        from madtracker.board.window import screen_infos

        self.main.set_screens(*self._screen_entries(screen_infos()))

    # Displays ----------------------------------------------------------

    def preferred_screen_name(self) -> str | None:
        value = self.settings.value(SCREEN_KEY, None)
        return str(value) if value else None

    def place_board(self, exclude: str | None = None) -> str | None:
        """Pick a display and, if the scorer wants it up, show the board there."""
        from madtracker.board.window import screen_by_name, screen_infos
        from madtracker.displays import choose_scoreboard_screen

        infos = [s for s in screen_infos() if s.name != exclude]
        choice = choose_scoreboard_screen(infos, self.preferred_screen_name())
        self.board_screen = choice.name if choice else None
        if self.board_wanted:
            screen = screen_by_name(self.board_screen)
            here = self.main.screen()
            # By name: Qt on Windows can hand back two wrappers for one
            # display, and an identity test then never matches.
            if screen is not None and here is not None and screen.name() == here.name():
                applog.info(
                    f"Scoreboard on {screen.name()}, the scoring window's display: windowed"
                )
                # The scoring window's own display: full screen there would
                # cover the controls, so the board opens as a window beside
                # them, as on one display. The pick stays, and the board
                # fills that display again once the scoring window leaves.
                screen = None
            self.board.show_on(screen, self.main.frameGeometry())
        self._list_screens(infos)
        return self.board_screen

    def _main_screen_changed(self, _screen) -> None:
        if self.board_wanted and self.board_screen is not None:
            self.place_board()

    def _screen_entries(self, infos) -> tuple[list[tuple[str, str]], str | None]:
        """The Scoreboard menu's displays, each with what the board is there, and the chosen one."""
        from madtracker.displays import screen_label

        # The scoring window's display: the board can only be a window
        # there, and the entry says so.
        here = self.main.screen()
        here_name = here.name() if here is not None else None
        return [(s.name, screen_label(s, here_name)) for s in infos], self.preferred_screen_name()

    def _list_screens(self, infos) -> None:
        self.main.set_screens(*self._screen_entries(infos))
        self.main.set_board_shown(self.board.isVisible())

    def show_board(self, shown: bool) -> None:
        """Scoreboard > None (off), a display picked again, or the window's close button.

        Shown again, the board comes back to what is behind the veil: the
        preview kept drawing the race or the logo, grayed, while the TV
        was off, so that picture is what the scorer expects to see go up
        rather than the logo. While it is off the preview's click and the
        menu's Logo and Live do nothing, so what comes back is what went
        down; picking a display is the one way back.
        """
        self.board_wanted = shown
        self._lost_display = False
        if shown:
            self.place_board()
        else:
            self.board.hide()
            self.main.set_board_shown(False)

    def choose_board_face(self, live: bool) -> None:
        """The scorer picked Logo or Live, on the picture or in the menu."""
        self.set_board_live(live)

    def set_board_live(self, live: bool) -> None:
        self.board_live = bool(live)
        for b in self.boards:
            b.set_live(self.board_live)
        self.main.set_board_live(self.board_live)

    def choose_screen(self, name) -> None:
        """A pick from the Scoreboard menu's list: a display, None for Automatic, or off."""
        from madtracker.displays import NO_DISPLAY

        if name == NO_DISPLAY:
            self.show_board(False)
            return
        if name is None:
            self.settings.remove(SCREEN_KEY)
        else:
            self.settings.setValue(SCREEN_KEY, str(name))
        self.board_wanted = True
        self.place_board()

    def _screen_removed(self, screen) -> None:
        from PySide6.QtCore import QTimer

        from madtracker.board.window import screen_infos

        name = screen.name()
        remaining = [s for s in screen_infos() if s.name != name]
        if name == self.board_screen:
            self.board_screen = None
            if self.board.isVisible():
                # The TV going away must never drop the board onto the
                # laptop screen over the operator window.
                self.board.hide()
                self._lost_display = True
                label = screen_infos([screen])[0].shown
                # Once the signal returns: on macOS it arrives inside AppKit's
                # teardown of the full-screen board's Space, and a modal box
                # run there spins in AppKit's modal loop and never paints.
                if not self._lost_box_posted:
                    self._lost_box_posted = True
                    QTimer.singleShot(0, self.main, lambda: self._report_lost_display(label))
        self._list_screens(remaining)

    def _report_lost_display(self, label: str) -> None:
        self._lost_box_posted = False
        # A display back before the box opens leaves nothing to report,
        # and a box already up says it once.
        if not self._lost_display or self._lost_display_boxes():
            return
        self.main.report_failure(
            f"Scoreboard display {label} disconnected. Reconnect it, or choose "
            "another on the Scoreboard menu.",
            title=LOST_DISPLAY_TITLE,
            name=LOST_DISPLAY_BOX,
        )

    @staticmethod
    def _lost_display_boxes() -> list:
        from PySide6.QtWidgets import QApplication, QMessageBox

        return [
            w
            for w in QApplication.topLevelWidgets()
            if isinstance(w, QMessageBox) and w.isVisible() and w.objectName() == LOST_DISPLAY_BOX
        ]

    def _close_lost_display_box(self) -> None:
        """The disconnect box goes once the board is back: left up, it reports a
        failure that is over, and the scorer would dismiss it for nothing."""
        from PySide6.QtWidgets import QMessageBox

        for w in self._lost_display_boxes():
            w.done(QMessageBox.StandardButton.Ok)

    def _screen_added(self, screen) -> None:
        from madtracker.board.window import screen_infos
        from madtracker.displays import choose_scoreboard_screen

        if self._lost_display:
            self.board_wanted = True
        if self.board_wanted and self.board_screen is None:
            choice = choose_scoreboard_screen(screen_infos(), self.preferred_screen_name())
            if choice is not None:
                self._lost_display = False
                self.place_board()
                self._close_lost_display_box()
                return
        self._list_screens(screen_infos())

    # Store and event ---------------------------------------------------

    def start(self) -> None:
        from madtracker.ui.window import place_window

        place_window(self.main, self.settings.value(WINDOW_KEY, None))
        self.main.show()
        # The native window exists once shown; dragging the scoring window
        # onto the scoreboard's display, or off it, places the board again.
        self.main.windowHandle().screenChanged.connect(self._main_screen_changed)
        self.place_board()
        self.main.activateWindow()

    def open_store(self, expected: Path | None = None) -> None:
        import sqlite3

        from madtracker.store import NeedsUpdateError, NoWalError, Store, StoreError

        path = self.data_path
        notices = []
        if expected is not None:
            # Say what happened: the usual case is the remembered file
            # being the default one, deleted, and then nothing is
            # "opened instead", a new file is made in its place.
            if path.is_file():
                notices.append(f"Data file not found:\n{expected}\n\nOpened instead:\n{path}")
            elif path == expected:
                notices.append(f"Data file not found, so a new one was created:\n{expected}")
            else:
                notices.append(
                    f"Data file not found:\n{expected}\n\nA new one was created:\n{path}"
                )
        lock, held = self._take_lock(path)
        if held:
            # Shown as a damaged file is: an empty surface with the notice,
            # and no store, so this copy can neither score into the file
            # nor drop the other window's clean-close marker on quit.
            self.store = None
            self._notice = NOTICE_GAP.join([*notices, ALREADY_OPEN])
            self.main.show_empty(self._notice)
            self._sync_menus()
            return
        try:
            store = Store.open(path)
        except (StoreError, OSError, sqlite3.Error) as exc:
            self._release(lock)
            self.store = None
            applog.error(f"Could not open {path}: {exc}")
            existed = path.is_file()
            self.damaged = existed and not isinstance(exc, (NeedsUpdateError, NoWalError))
            if isinstance(exc, NeedsUpdateError):
                notice = needs_update_notice(path)
            elif isinstance(exc, NoWalError):
                notice = no_wal_notice(path)
            elif existed:
                notice = damaged_notice(path, self.data_dir)
            else:
                notice = cannot_create_notice(path)
            self._notice = NOTICE_GAP.join([*notices, notice])
            self.main.show_empty(self._notice)
            self._sync_menus()
            # A box as well as the empty screen: the screen's text is easy
            # to read past as a first-run message.
            self.main.report_failure(self._notice, title="Data File")
            return
        self._install_store(store, path, notices, self.remember_file, lock)

    def _take_lock(self, path: Path):
        """Lock ``path`` for this window; return (lock or None, held by another window).

        Two copies on one file would each score into it, each drive its own
        scoreboard, and the first to quit would remove the other's
        clean-close marker, so the lock refuses the second copy.
        A lock that cannot be written for any other reason (a read-only
        folder) is not a refusal: the store's own open decides then.
        """
        from PySide6.QtCore import QLockFile

        from madtracker.control.backups import lock_path

        target = lock_path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None, False
        lock = QLockFile(str(target))
        lock.setStaleLockTime(STALE_LOCK_MS)
        if lock.tryLock(0):
            return lock, False
        if lock.error() != QLockFile.LockError.LockFailedError:
            return None, False
        # Held, says Qt; but a lock left by a crashed copy names a process
        # that is gone, and Qt's own staleness rule differs by platform.
        if not self._lock_holder_alive(lock) and lock.removeStaleLockFile() and lock.tryLock(0):
            return lock, False
        return None, True

    @staticmethod
    def _lock_holder_alive(lock) -> bool:
        from PySide6.QtCore import QSysInfo

        from madtracker.control.backups import pid_alive

        try:
            info = lock.getLockInfo()
        except (TypeError, ValueError):
            return True
        # PySide6 hands back (pid, host, app); an older binding adds the
        # success flag in front.
        if len(info) == 4:
            if not info[0]:
                return True
            info = info[1:]
        pid, host, _app = info
        if host and host != QSysInfo.machineHostName():
            # Another machine's lock on a shared folder: nothing to check here.
            return True
        return pid_alive(int(pid))

    @staticmethod
    def _release(lock) -> None:
        if lock is not None:
            lock.unlock()

    def _install_store(
        self, store, path: Path, notices: list[str], remember: bool, lock=None
    ) -> bool:
        """Make ``store`` the open file; False when it is damaged and no event should open."""
        import sqlite3

        from madtracker.control.backups import UNCLEAN_NOTICE, mark_open
        from madtracker.store import BACKUP_KEY, StoreError

        self.store = store
        self.data_path = Path(path)
        self._lock = lock
        # A file opened to score into is a data file, even one that began
        # as a backup: a restored copy, or a backup put back by hand.
        try:
            if store.get_setting(BACKUP_KEY) is not None and not store.read_only:
                store.clear_backup_mark()
        except (StoreError, sqlite3.Error):
            # A damaged settings page: the integrity check below says so.
            pass
        try:
            self.recovered = mark_open(self.data_path)
        except OSError:
            self.recovered = False
        applog.use_folder(self.data_dir)
        applog.info(f"Opened {self.data_path}" + (" (read-only)" if store.read_only else ""))
        if self.recovered:
            applog.warning("The last session did not close cleanly; recovered.")
            notices.append(UNCLEAN_NOTICE)
        problems = self.store.integrity_check()
        if problems:
            applog.error("Integrity check failed: " + "; ".join(problems[:10]))
            notices.append(damaged_notice(self.data_path, self.data_dir))
        elif store.read_only:
            # Said once, when it opens: otherwise the scorer learns it from
            # the red line at the first click, mid-race.
            notices.append(READ_ONLY_NOTICE.format(path=self.data_path))
        self._notice = NOTICE_GAP.join(notices) or None
        if self._notice:
            self.main.report_failure(self._notice, title="Data File")
        if remember:
            self.settings.setValue(DATA_FILE_KEY, str(self.data_path))
            # A file that cannot be remembered still opens; the next start
            # opens the default file, and the log says why.
            self.settings.sync()
            if self.settings.status() != self.settings.Status.NoError:
                applog.warning(f"Could not remember the data file: {self.settings.status().name}")
        self.damaged = bool(problems)
        self._sync_menus()
        if problems:
            # Opening an event would read the damaged pages and die there,
            # with no window; the notice and File > Open Data File let the
            # scorer pick a backup instead.
            self.main.set_event("", "")
            self.main.set_races([], None)
            self.main.show_empty(self._notice)
            return False
        try:
            self.apply_venue()
        except (StoreError, sqlite3.Error) as exc:
            applog.error(f"Could not read the venue settings: {exc}")
            self._show_damaged()
            self.main.report_failure(self._notice, title="Data File")
            return False
        return True

    def apply_venue(self) -> None:
        """Logo, venue name and the bibs setting from the store onto the board."""
        from madtracker.control import venue

        if self.store is None:
            return
        # Only the venue's own image: with none, the board draws the
        # app's wordmark as vectors, sharp on any TV, instead of the PNG.
        data = venue.logo_setting(self.store)
        name = venue.venue_name(self.store, self.event.venue if self.event else "")
        for b in self.boards:
            b.set_logo_bytes(data)
            b.set_rider_label(venue.rider_label(self.store))
            b.set_accent(venue.accent(self.store))
            b.set_venue_name(name)

    def quit(self) -> None:
        """File > Quit: the end-of-night backup while the window is still up, then quit.

        Here and not in close(): Qt runs aboutToQuit when no interaction
        is possible any more, and the one time a failed stick copy
        matters is that box at the end of the night.
        """
        self.save_window()
        self.final_backup()
        self.board.hide()
        self.app.quit()

    def save_window(self) -> None:
        """Keep the scoring window's place for the next start on this machine.

        In quit(), which both File > Quit and the window's close button
        reach, while the window is still up: by aboutToQuit it may not be.
        Synced at once, as the process ends right after.
        """
        self.settings.setValue(WINDOW_KEY, self.main.saveGeometry())
        self.settings.sync()

    def final_backup(self) -> None:
        """The end-of-night copies: beside the file, and to the chosen folder.

        Not for a damaged file (its backup would copy the damage and only
        add a failure box) or a read-only one (it cannot have changed).
        """
        self._run_result_backup()
        if self.store is None or self.damaged or self.store.read_only:
            return
        self.auto_backup(extra=True, closing=True)

    def close(self) -> None:
        """Clean close: close the store (checkpoints the WAL), drop the marker, release the lock.

        Every step runs whatever the one before did: a close that stopped
        at a failed checkpoint (a full disk) would leave the app on a closed
        connection, where every click raises until a restart.
        """
        import sqlite3

        from madtracker.control.backups import mark_closed
        from madtracker.store import StoreError

        self._run_result_backup()
        store, self.store = self.store, None
        if store is None:
            return
        self.live = None
        try:
            store.close()
        except (StoreError, sqlite3.Error) as exc:
            # The WAL stays valid and is folded in at the next open.
            applog.warning(f"Closing {self.data_path}: {exc}")
        try:
            mark_closed(self.data_path)
        except OSError:
            pass
        # Last, after the marker: the next window to take the file
        # must find it closed cleanly.
        self._release(self._lock)
        self._lock = None
        applog.info(f"Closed {self.data_path}")

    def auto_backup(self, extra: bool = False, closing: bool = False) -> Path | None:
        """Back up beside the file and, with ``extra``, to the chosen folder too. A failure is shown, never raised.

        Every race result backs up beside the file, where rotation keeps
        the folder at one night. The chosen folder is never pruned, so it
        gets only the end-of-night copies, on close and on Backup Now:
        the file is cumulative, so one copy a night holds the whole night,
        and a stick does not fill with twenty copies of each.
        """
        import sqlite3

        from madtracker.control import venue
        from madtracker.control.backups import run_backup
        from madtracker.store import StoreError

        # A read-only file cannot have changed since it was opened, and its
        # folder usually cannot take the copy: a box saying so is only noise.
        if self.store is None or self.store.read_only:
            return None
        try:
            result = run_backup(
                self.store,
                venue.automatic_backup_dir(self.data_dir),
                venue.chosen_backup_dir(self.store) if extra else None,
                event=self.event.name if self.event else "",
            )
        except (StoreError, OSError, sqlite3.Error) as exc:
            # The system's words and the path, not "[Errno 17]": the scorer
            # reads which folder or file is in the way.
            if isinstance(exc, OSError) and exc.strerror:
                reason = f"{exc.strerror}: {exc.filename}" if exc.filename else exc.strerror
            else:
                reason = str(exc).rstrip(".")
            # At the end of the night nothing "continues"; what the scorer
            # needs then is that the entries themselves are safe.
            after = (
                "Everything entered is saved in the data file." if closing else "Scoring continues."
            )
            self.main.report_failure(f"{BACKUP_FAILED}: {reason}. {after}", title="Backup")
            return None
        applog.info(f"Backup written: {result.automatic}")
        if result.extra is not None:
            applog.info(f"Backup written: {result.extra}")
        if result.warning:
            self.main.report_failure(result.warning, title="Backup")
        return result.automatic

    # Data files --------------------------------------------------------

    def open_data_file(self, path=None, restore_to=None) -> bool:
        """File > Open Data File; ``restore_to`` restores a backup there without asking."""
        if path is None:
            from PySide6.QtWidgets import QFileDialog

            chosen, _ = QFileDialog.getOpenFileName(
                self.main, "Open Data File", str(self.data_dir), DATA_FILE_FILTER
            )
            if not chosen:
                return False
            path = chosen
        return self._switch_file(
            Path(path), create=False, restore_to=Path(restore_to) if restore_to else None
        )

    def new_data_file(self, path=None, copy=None) -> bool:
        """File > New Data File; ``copy`` is a CopyChoice, asked for when a file is open."""
        if path is None:
            from PySide6.QtWidgets import QFileDialog

            chosen, _ = QFileDialog.getSaveFileName(
                self.main,
                "New Data File",
                str(self.data_dir),
                DATA_FILE_FILTER,
                options=QFileDialog.Option.DontConfirmOverwrite,
            )
            if not chosen:
                return False
            path = Path(chosen)
            if not path.suffix:
                path = path.with_suffix(".sqlite")
        path = Path(path)
        # Refused before the copy question, or the scorer answers it and
        # only then hears the name was taken.
        refusal = self._new_file_refusal(path)
        if refusal:
            return self._refuse("New Data File", refusal)
        if copy is None and self.store is not None:
            from madtracker.ui.setup import CopyFileDialog
            from madtracker.ui.widgets import run_dialog

            dialog = CopyFileDialog(self.main)
            if run_dialog(dialog) != dialog.DialogCode.Accepted:
                return False
            copy = dialog.choice()
        return self._switch_file(path, create=True, copy=copy)

    def _new_file_refusal(self, path: Path) -> str | None:
        path = path.absolute()
        if self.store is not None and path == self.data_path.absolute():
            # The save box opens where the open file sits, and a click
            # on it fills in its name; silence here would read as a failure.
            return f"{path.name} is the open data file. Choose another name."
        if path.exists():
            return f"This file already exists:\n{path}\n\nUse File > Open Data File..."
        return None

    def _refuse(self, title: str, text: str) -> bool:
        from madtracker.ui import icons

        icons.warn(self.main, title, text)
        return False

    def _restore_target(self, mark: dict, restore_to: Path | None) -> Path | None:
        """Where a backup being opened is copied to; None when the scorer cancels.

        A backup is never scored into: it may sit in the automatic folder,
        where rotation deletes it, or on a stick that gets pulled. So
        restoring copies it out to a data file of its own and opens that.
        """
        if restore_to is not None:
            return restore_to.absolute()
        from datetime import date

        from PySide6.QtWidgets import QFileDialog

        from madtracker.control.backups import restore_question
        from madtracker.ui import icons

        if not icons.ask(self.main, "Open Data File", restore_question(mark), "Restore"):
            return None
        default = self.data_dir / f"madtracker-restored-{date.today().isoformat()}.sqlite"
        chosen, _ = QFileDialog.getSaveFileName(
            self.main,
            "Restore Backup As",
            str(default),
            DATA_FILE_FILTER,
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not chosen:
            return None
        target = Path(chosen)
        if not target.suffix:
            target = target.with_suffix(".sqlite")
        return target.absolute()

    def _switch_file(
        self,
        path: Path,
        create: bool,
        copy=None,
        restore_to=None,
        *,
        title: str | None = None,
        remember: bool | None = None,
    ) -> bool:
        """Open ``path`` in place of the current file.

        Four steps, each of which may refuse: the checks that change
        nothing, staging a restore beside its target, the questions, and
        the swap and open. A refusal before the current file is let go
        leaves it open; a file that fails its check once opened leaves
        nothing open and the damaged notice up, as a bad file found at
        start does.

        ``title`` names the refusals; ``remember`` False opens for the
        session only, as the demo is.
        """
        title = title or ("New Data File" if create else "Open Data File")
        remember = self.remember_file if remember is None else remember
        path = path.absolute()
        if create:
            refusal = self._new_file_refusal(path)
            if refusal:
                return self._refuse(title, refusal)
        elif self.store is not None and _same_file(path, self.data_path):
            return True
        still = f"\n\nStill open:\n{self.data_path}" if self.store is not None else ""
        switch = _Switch(path, create, title, still, copy, restore_to, remember)
        refusal = self._switch_refusal(switch)
        if refusal is not None:
            return self._refuse(title, refusal)
        if not self._stage_restore(switch):
            return False
        if not self._ask_to_switch(switch):
            return False
        return self._swap_and_open(switch)

    @staticmethod
    def _switch_refusal(switch: _Switch) -> str | None:
        """Why ``switch.path`` cannot be opened, found by reading alone; None when it can."""
        from madtracker.store import is_empty_database

        path, still = switch.path, switch.still
        if not switch.create and not path.is_file():
            return f"This file was not found:\n{path}"
        try:
            # Store.open would build the schema in an empty file and turn
            # it into a blank venue; an empty file the scorer picked is
            # a mistake (a failed copy, the wrong file), not a new venue.
            empty = not switch.create and path.stat().st_size == 0
        except OSError as exc:
            return f"Could not open ({exc}):\n{path}{still}"
        if empty:
            return f"This is not a MadTracker data file:\n{path}{still}"
        if not switch.create and is_empty_database(path):
            # What a copy of the live file alone looks like while the night
            # is still in the -wal beside the original: opened, it would
            # quietly become a blank venue.
            return (
                f"This data file is empty:\n{path}\n\nA copy of the data file made while"
                f" {APP_NAME} had it open can be empty. Open a backup instead; see Help >"
                f" Backups.{still}"
            )
        return None

    def _stage_restore(self, switch: _Switch) -> bool:
        """When ``switch.path`` is a backup, copy it beside the file it restores; False when refused.

        A plain data file stages nothing and the switch goes on to open it
        where it is.
        """
        import shutil

        from madtracker.store import file_problems, read_backup_mark

        path, title, still = switch.path, switch.title, switch.still
        mark = None if switch.create else read_backup_mark(path)
        if mark is None:
            return True
        # Checked before anything is asked or copied: a backup that
        # would open as damaged must never replace a file first.
        problems = file_problems(path)
        if problems:
            applog.error(f"Backup refused, {path}: " + "; ".join(problems[:10]))
            if problems[0].startswith(("predates", "made by a newer")):
                # Another version's file, whole: an older backup would be
                # no better, and a newer one needs the newer program.
                return self._refuse(
                    title,
                    f"This backup can't be restored:\n{path}\n\nIt was written by a version of"
                    f" {APP_NAME} this one can't read. Nothing was changed.{still}",
                )
            return self._refuse(
                title,
                f"This backup can't be restored:\n{path}\n\nIt is damaged, or this version of"
                f" {APP_NAME} can't read it. Nothing was changed. Try an older backup.{still}",
            )
        restored = self._restore_target(mark, switch.restore_to)
        if restored is None:
            return False
        if _same_file(restored, path):
            return self._refuse(
                title, f"That is the backup itself:\n{path}\n\nChoose another name."
            )
        # Copied beside the target before anything else, so a failed
        # copy leaves the file being replaced as it was; and before the
        # backup _may_replace takes, whose rotation would delete the chosen
        # backup when it is the oldest one kept beside the open file.
        incoming = restored.with_name(restored.name + ".restoring")
        try:
            restored.parent.mkdir(parents=True, exist_ok=True)
            # copyfile, not copy2: a backup on a write-protected stick
            # is read-only, and its copy must not be.
            shutil.copyfile(path, incoming)
        except OSError as exc:
            incoming.unlink(missing_ok=True)
            return self._refuse(title, f"Could not copy ({exc}):\n{path}\n\nto:\n{restored}{still}")
        switch.restored = restored
        switch.incoming = incoming
        return True

    def _ask_to_switch(self, switch: _Switch) -> bool:
        """The questions before the swap: leaving a race mid-scoring, and replacing a file; False on No."""
        restored, incoming = switch.restored, switch.incoming
        # The same question as switching races: the staged clicks are in
        # the file and come back, but leaving a race mid-scoring is asked
        # the same way everywhere. Asked before Replace, whose backup a
        # No here would make for nothing; a restore over the open file names
        # the backup, since the target's name is the file already open.
        switch.replacing_open = (
            restored is not None and self.store is not None and _same_file(restored, self.data_path)
        )
        leaving = switch.path if switch.replacing_open or restored is None else restored
        if not self._may_leave(leaving.name):
            if restored is not None:
                incoming.unlink(missing_ok=True)
            return False
        if restored is not None and restored.exists():
            switch.saved = self._may_replace(switch.title, restored, ask=switch.restore_to is None)
            if switch.saved is None:
                incoming.unlink(missing_ok=True)
                return False
        return True

    def _swap_and_open(self, switch: _Switch) -> bool:
        """Put a staged restore in place, open the file, and install it; False when refused."""
        import sqlite3

        from madtracker.control.copying import copy_venue
        from madtracker.store import NoWalError, Store, StoreError

        path, title, still = switch.path, switch.title, switch.still
        restored, incoming, saved = switch.restored, switch.incoming, switch.saved
        let_go = None
        if restored is not None:
            if switch.replacing_open:
                # Replacing the open file: it is let go first, its last
                # state already in its backups folder (_may_replace).
                let_go = (self.data_path, self.settings.value(EVENT_KEY, None))
                self._drop_edit()
                self.close()
                self._forget_file()
                still = ""
            try:
                _clear_beside(restored)
                os.replace(incoming, restored)
            except OSError as exc:
                incoming.unlink(missing_ok=True)
                # Not replaced (on Windows a virus scanner holding the file
                # is enough): the file is as it was, so it opens again on
                # its event rather than leaving an empty window.
                still = self._open_again(let_go, still)
                return self._refuse(title, f"Could not replace ({exc}):\n{restored}{still}")
            path = restored
        lock, held = self._take_lock(path)
        if held:
            still = self._open_again(let_go, still)
            return self._refuse(title, ALREADY_OPEN + still)
        try:
            store = Store.open(path)
        except (StoreError, OSError, sqlite3.Error) as exc:
            self._release(lock)
            if isinstance(exc, NoWalError):
                failed = no_wal_notice(path)
            else:
                failed = f"Could not open ({exc}):\n{path}"
            if saved is not None:
                # The file it replaced was a data file, maybe the open one:
                # deleting the copy deletes it. What it held goes back.
                if self._put_back(saved, path):
                    failed += "\n\nIt was put back as it was."
                else:
                    failed += f"\n\nWhat it held before is in:\n{saved}"
            elif restored is not None:
                # The copy was made only to be opened; a failed open
                # leaves nothing behind for the scorer to wonder about.
                restored.unlink(missing_ok=True)
            still = self._open_again(let_go, still)
            return self._refuse(title, failed + still)
        copied = {}
        if switch.create and switch.copy is not None and self.store is not None:
            try:
                copied = copy_venue(self.store, store, switch.copy)
            except (StoreError, OSError, sqlite3.Error) as exc:
                # The new file is let go again, lock and all, and the
                # current one stays open, as for any failed switch.
                self._discard(store, lock)
                path.unlink(missing_ok=True)
                return self._refuse(title, f"Could not copy into ({exc}):\n{path}{still}")
        self._leave_file()
        # --demo and --data-dir runs never become the file a plain start opens.
        if not self._install_store(store, path, [], remember=switch.remember, lock=lock):
            return True
        if not self._open_guarded(self._open_last_event):
            return True
        if switch.create and not copied.get("settings"):
            # A fresh file has no venue name or logo of its own, so the
            # scorer meets Settings first; Cancel keeps the defaults.
            self.edit_settings()
        return True

    def _leave_file(self) -> None:
        """Let the open file go cleanly, with its end-of-night backup, before another is installed."""
        self._drop_edit()
        self.final_backup()
        self.close()
        self._forget_file()

    def open_demo_file(self) -> bool:
        """Help > Open Demo Data File: the last demo opened again, or a new one built and opened.

        A new one every time it is asked for, so a scorer can start over
        without a fresh install, and the last one kept, so a night of
        trying things is not lost to a second look; its own file, beside
        but never in place of the venue's, so its automatic backups go to
        its own backups folder and never touch the venue's or its stick.
        It is open for the session only and never remembered: a start
        that came up in the demo would read as the venue's file replaced.
        """
        import sqlite3

        from madtracker.control.demo import seed_demo
        from madtracker.store import Store, StoreError
        from madtracker.ui import icons

        title = "Open Demo Data File"
        path = (self.base_dir / DEMO_FOLDER / DEMO_FILE_NAME).absolute()
        # Nothing to open again until a demo exists, or while it is open.
        in_demo = self.store is not None and _same_file(path, self.data_path)
        previous = path.is_file() and not in_demo
        choice = icons.choose(
            self.main,
            title,
            DEMO_QUESTION.format(path=path),
            [OPEN_PREVIOUS, CREATE_NEW],
            CREATE_NEW,
            disabled=() if previous else (OPEN_PREVIOUS,),
        )
        if choice is None:
            return False
        if choice == OPEN_PREVIOUS:
            return self._switch_file(path, create=False, title=title, remember=False)
        if not self._may_leave("the demo data file"):
            return False
        # The demo open here is let go before its file is removed; any
        # other file stays open until the new demo is built, so a failure
        # leaves it as it was.
        rebuilding = in_demo
        if rebuilding:
            self._leave_file()
        still = f"\n\nStill open:\n{self.data_path}" if self.store is not None else ""
        lock, held = self._take_lock(path)
        if held:
            return self._demo_failed(title, ALREADY_OPEN + still)
        store = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _clear_beside(path)
            path.unlink(missing_ok=True)
            store = Store.open(path)
            event_id = seed_demo(store)
        except (StoreError, OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
            # The seed refuses with RuntimeError or ValueError when its
            # own scoring is wrong; the file is let go, not left locked.
            if store is not None:
                self._discard(store, lock)
            else:
                self._release(lock)
            return self._demo_failed(title, f"Could not build ({exc}):\n{path}{still}")
        if not rebuilding:
            self._leave_file()
        if not self._install_store(store, path, [], remember=False, lock=lock):
            return True
        self._open_guarded(lambda: self.open_event(event_id))
        return True

    def _demo_failed(self, title: str, text: str) -> bool:
        """Refuse; with no file left open (the demo was let go to rebuild it), say so on the window."""
        if self.store is None:
            self.main.show_empty(NO_FILE_OPEN)
            self._sync_menus()
        return self._refuse(title, text)

    def _may_replace(self, title: str, target: Path, ask: bool = True) -> Path | None:
        """The copy of what ``target`` holds, taken before a backup is restored over it; None when not.

        Asked, since a data file is a venue's whole history; refused when
        another window has the file open. What the file holds goes to its
        own backups folder first, through the backup API, so its -wal is
        in the copy and a wrong pick can be undone from Help > Backups.
        The copy is one rotation keeps (``before_restore``): as an
        ordinary backup it would be gone after twenty more results that night.
        """
        import sqlite3

        from madtracker.control import venue
        from madtracker.control.backups import take_backup
        from madtracker.store import Store, StoreError
        from madtracker.ui import icons

        is_open = self.store is not None and _same_file(target, self.data_path)
        if not is_open:
            lock, held = self._take_lock(target)
            if held:
                self._refuse(title, ALREADY_OPEN)
                return None
            self._release(lock)
        folder = venue.automatic_backup_dir(target.parent)
        if ask and not icons.ask(
            self.main,
            title,
            f"This file already exists:\n{target}\n\nReplace it? Its current contents are"
            " backed up first.",
            "Replace",
        ):
            return None
        try:
            if is_open:
                saved = take_backup(
                    self.store,
                    folder,
                    automatic_folder=True,
                    event=self.event.name if self.event else "",
                    before_restore=True,
                )
            else:
                store = Store.open(target)
                try:
                    saved = take_backup(store, folder, automatic_folder=True, before_restore=True)
                finally:
                    store.close()
        except (StoreError, OSError, sqlite3.Error) as exc:
            # Not a data file of ours, or one that cannot be read: it is
            # not replaced without its copy.
            self._refuse(title, f"Could not back up ({exc}):\n{target}\n\nIt was not replaced.")
            return None
        applog.info(f"Backup written before replacing {target}: {saved}")
        if is_open:
            # The open file closes for the restore without final_backup
            # (its last state is this copy), so the end-of-night copy to
            # the chosen folder is taken here or not at all.
            self._extra_copy()
        return saved

    def _extra_copy(self) -> None:
        """The chosen folder's copy of the open file, as a close writes it; a failure is a warning."""
        import sqlite3

        from madtracker.control import venue
        from madtracker.control.backups import take_backup
        from madtracker.store import StoreError

        chosen = venue.chosen_backup_dir(self.store)
        if chosen is None or self.damaged or self.store.read_only:
            return
        try:
            if chosen.resolve() == venue.automatic_backup_dir(self.data_dir).resolve():
                return
            extra = take_backup(
                self.store,
                chosen,
                automatic_folder=False,
                event=self.event.name if self.event else "",
            )
        except (StoreError, OSError, sqlite3.Error) as exc:
            self.main.report_failure(f"The extra backup failed ({exc}):\n{chosen}", title="Backup")
            return
        applog.info(f"Backup written: {extra}")

    def _put_back(self, saved: Path, target: Path) -> bool:
        """Put the copy ``_may_replace`` took back in place of ``target``, as a data file again."""
        import shutil
        import sqlite3

        from madtracker.store import BACKUP_KEY

        incoming = target.with_name(target.name + ".restoring")
        try:
            shutil.copyfile(saved, incoming)
            # Unmarked, or opening it again would ask to restore it.
            conn = sqlite3.connect(incoming)
            try:
                conn.execute("DELETE FROM setting WHERE key = ?", (BACKUP_KEY,))
                conn.commit()
            finally:
                conn.close()
            _clear_beside(target)
            os.replace(incoming, target)
        except (OSError, sqlite3.Error) as exc:
            applog.error(f"Could not put {saved} back as {target}: {exc}")
            try:
                incoming.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        applog.info(f"Put back {target} from {saved}")
        return True

    def _open_again(self, let_go, still: str) -> str:
        """After a failed restore over the open file, open it again on its event; the "Still open" line."""
        if let_go is None:
            return still
        from madtracker.store import read_backup_mark

        data_path, event = let_go
        if read_backup_mark(data_path) is not None:
            # Still the backup's copy, which would not open and could not
            # be put back: opening it again would ask to restore it.
            return ""
        if event is not None:
            self.settings.setValue(EVENT_KEY, event)
        self._switch_file(data_path, create=False)
        if self.store is None:
            return ""
        return f"\n\nStill open:\n{self.data_path}"

    def _discard(self, store, lock) -> None:
        """Let go of a store that was opened but will not be used."""
        import sqlite3

        from madtracker.store import StoreError

        try:
            store.close()
        except (StoreError, sqlite3.Error):
            pass
        self._release(lock)

    def _forget_file(self) -> None:
        from madtracker.control import board_feed
        from madtracker.control.race import NOTHING_TO_UNDO_LABEL

        self.event = None
        self.races = []
        self.live = None
        self._known_state = {}
        self.settings.remove(EVENT_KEY)
        self.main.set_event("", "")
        self.main.set_races([], None)
        self.main.set_undo(NOTHING_TO_UNDO_LABEL, False)
        self._sync_live()
        self.set_board_live(False)
        for b in self.boards:
            b.set_event_name("")
        self._set_board("between", board_feed.between("", None, None))

    def _show_welcome(self) -> None:
        """The empty window's first-night steps, each checked once done."""
        from madtracker.control import venue
        from madtracker.ui.window import NO_EVENT

        self.main.show_empty(NO_EVENT, welcome=True)
        self.main.set_welcome_done(bool(venue.venue_name(self.store)), bool(self.store.riders()))

    def _open_last_event(self) -> None:
        events = self.store.events()
        if not events:
            self.main.set_event("", "")
            self.main.set_races([], None)
            self._show_welcome()
            return
        wanted = self.settings.value(EVENT_KEY, None)
        ids = [m.event_id for m in events]
        try:
            event_id = int(wanted) if wanted is not None else ids[0]
        except (TypeError, ValueError):
            event_id = ids[0]
        self.open_event(event_id if event_id in ids else ids[0])

    def open_event(self, event_id: int) -> None:
        """Open an event with its live race selected: the one the file remembers, else the newest."""
        from madtracker.control.race import live_race_id

        if self.event is None or self.event.event_id != event_id:
            # Another event goes up on the logo, as another file does: a
            # board left Live would send last week's race to the TV the moment
            # the scorer opened it to read. Off stays off, and comes back
            # on the logo too.
            self.set_board_live(False)
        self.event = self.store.event(event_id)
        self.settings.setValue(EVENT_KEY, event_id)
        for b in self.boards:
            b.set_event_name(self.event.name)
        self.main.set_event(self.event.name, self.event.event_date)
        self.apply_venue()
        self.live = None
        self._reload_races()
        remembered = self.store.get_setting(LIVE_RACE_KEY)
        ids = [r.race_id for r in self.races]
        race_id = remembered if remembered in ids else live_race_id(self.store, event_id)
        if race_id is None:
            # Nothing to select, so nothing redraws the right pane: without
            # this the last event's race stays on the board (live on the
            # TVs) and its last entry on the Undo button, under tonight's name.
            from madtracker.control import board_feed
            from madtracker.control.race import NOTHING_TO_UNDO_LABEL

            self.main.set_undo(NOTHING_TO_UNDO_LABEL, False)
            self._set_board("between", board_feed.between("", None, None))
            self._show_program()
            self.open_setup()
            return
        self.select_race(race_id)

    def _reload_races(self) -> None:
        self.races = self.store.races(self.event.event_id) if self.event else []

    def _show_program(self) -> None:
        from madtracker.control import rulesets
        from madtracker.ui.program import ProgramRow

        self._sync_live()
        if self.event is None:
            return
        rows = [
            ProgramRow(
                r.race_id, rulesets.race_short_name(r), r.group_label, self._program_state(r)
            )
            for r in self.races
        ]
        current = self.live.race_id if self.live is not None else None
        self.main.set_races(rows, current)

    def _program_state(self, race) -> str:
        """The row's state word: Racing from the first staged click, as the surface says it.

        A race with clicks staged and no entry yet is still "setup" in
        the file, but the surface calls it Racing and leaving it asks
        first, so the list tags it the same.
        """
        from madtracker.control.race import STAGED_KEY

        if race.state != "setup":
            return race.state
        staged = self.store.get_setting(STAGED_KEY.format(race_id=race.race_id))
        if isinstance(staged, dict) and (staged.get("groups") or staged.get("tail")):
            return "running"
        return race.state

    def _sync_live(self) -> None:
        """Live only with something to show: a race selected.

        With no race the live board would be an empty "Up next" page, so
        Live waits for the program's first race, and a
        board left on Live goes back to the logo.
        """
        ready = self.live is not None
        self.main.set_live_ready(ready)
        if not ready and self.board_live:
            self.set_board_live(False)

    # Race selection and refresh ---------------------------------------

    def select_race(self, race_id: int) -> None:
        from madtracker.control.race import LiveRace
        from madtracker.store import StoreError
        from madtracker.ui.widgets import friendly_error

        if self.store is None or self.event is None:
            return
        if self.live is not None and self.live.race_id == race_id:
            if self.main.showing() != "surface":
                self.refresh()
            return
        target = next((r.name for r in self.races if r.race_id == race_id), "this race")
        if not self._may_leave(target):
            return
        # A sprint reopened for correction and left is abandoned, not
        # kept half-edited for when the scorer comes back.
        self._drop_edit()
        try:
            self.live = LiveRace(self.store, race_id)
        except (ValueError, StoreError) as exc:
            # A damaged page or a log this app cannot read: an empty
            # surface that says so, never a traceback out of the slot.
            applog.error(
                f"Race {race_id} would not open\n"
                + applog.traceback_text(type(exc), exc, exc.__traceback__)
            )
            self.live = None
            self.main.show_empty(friendly_error(self.store, exc))
            self._sync_live()
            return
        try:
            self.store.set_setting(LIVE_RACE_KEY, race_id)
        except StoreError:
            # Remembering the race is a convenience; a read-only or locked
            # file still shows it, and the first scoring write says why not.
            pass
        self._known_state[race_id] = self.live.state
        self.main.show_problem(None)
        self.refresh()

    def _may_leave(self, target: str) -> bool:
        """Leaving a race mid-scoring asks first; a No puts the program back on it.

        Selecting a race is how the scorer moves on, and the board follows,
        so a stray click mid-race would score and show the wrong race.
        """
        if self.live is None or not self.live.in_progress:
            return True
        from madtracker.ui import icons

        name = self.live.race.name
        text = f"{name} is still being scored. Switch to {target}?"
        if icons.ask(self.main, "Switch Race", text, verb="Switch"):
            return True
        # set_races rebuilds the list with signals held, so the restored
        # selection does not come back here as another switch.
        self._show_program()
        return False

    def refresh(self, overlay: bool = False) -> None:
        """Recompute from the log and redraw the surface, the program, the TV and the board."""
        from madtracker.control import board_feed

        if self.live is None:
            return
        screen = self.live.screen()
        known = self._known_state.get(screen.race_id)
        self._known_state[screen.race_id] = self.live.state
        self.main.show_screen(screen)
        self.main.set_undo(screen.undo_text, screen.undo_enabled, screen.undo_who)
        self._reload_races()
        self._show_program()
        self._set_board(*board_feed.board_for(self.live.view(), overlay=overlay))
        # A result just became provisional or final: back it up, the
        # moment it would hurt most to lose (design section 12). After the
        # redraw has reached the screen, so the screen and the board
        # already show the result the file holds, whatever the backup
        # folder does. The entries are committed already; only the copy
        # waits.
        if (
            known is not None
            and known != self.live.state
            and self.live.state in ("provisional", "final")
        ):
            self._schedule_result_backup()

    def _schedule_result_backup(self) -> None:
        from PySide6.QtCore import QTimer

        if self._backup_pending:
            return
        self._backup_pending = True
        QTimer.singleShot(RESULT_BACKUP_DELAY_MS, self.main, self._run_result_backup)

    def _run_result_backup(self) -> None:
        """The waiting result's backup and checkpoint, now; nothing when none waits.

        On the GUI thread like every other store use, so it never runs
        alongside a write. Every write, close, and file switch calls this
        first, so the copy holds the file as the result left it, even
        when the scorer's next click (an Undo, say) beats the timer.
        """
        if not self._backup_pending:
            return
        self._backup_pending = False
        if self.store is None:
            return
        self.auto_backup()
        # And into the main file: the .sqlite alone (copied by hand,
        # or left after a crash) then holds every result to here.
        self.store.checkpoint()

    def _set_board(self, layout: str, payload) -> None:
        for b in self.boards:
            b.set_layout(layout, payload)

    # Clicks ------------------------------------------------------------

    def _apply(self, outcome, *, overlay: bool = False) -> bool:
        """Show a refusal in the red line, or redraw everything after a change."""
        from madtracker.store import StoreError, disk_refusal

        if isinstance(outcome, (Exception, _Unexpected)):
            # The controller may have reloaded itself (another window wrote
            # first): redraw so the screen shows what the file now holds.
            if self.live is not None:
                try:
                    self.live.reload()
                    self.refresh()
                except Exception as exc:  # the red line below still answers
                    self._log_exception(exc)
            if isinstance(outcome, _Unexpected):
                line = UNEXPECTED_LINE[outcome.recorded]
                kind = type(outcome.error).__name__
                self.main.show_problem(line.format(kind=kind, log=applog.LOG_NAME))
            elif (disk := disk_refusal(outcome)) is not None:
                self.main.show_problem(DISK_LINE[disk])
                if not self._disk_refusal_reported:
                    self._disk_refusal_reported = True
                    title, body = DISK_BOX[disk]
                    self.main.report_failure(body, title=title)
            elif isinstance(outcome, StoreError):
                self.main.show_problem(f"Not recorded: {outcome}")
            else:
                kind = type(outcome).__name__
                self.main.show_problem(UNEXPECTED_LINE[None].format(kind=kind, log=applog.LOG_NAME))
            return False
        if not outcome.ok:
            self.main.show_problem(outcome.message)
            return False
        self.main.show_problem(None)
        self.refresh(overlay=overlay)
        slow = self.store is not None and self.store.last_commit_ms > SLOW_COMMIT_MS
        if slow:
            applog.warning(f"Slow commit: {self.store.last_commit_ms:.0f} ms")
        if slow and not self._slow_disk_reported:
            # Once a session: the scorer can do nothing about it mid-race,
            # and a box per click would be the slow disk's worst effect.
            self._slow_disk_reported = True
            self.main.report_failure(
                f"The disk is slow ({self.store.last_commit_ms:.0f} ms per entry). Scoring"
                " continues; expect a pause after each click.",
                title="Slow Disk",
            )
        return True

    def _guard(self, action):
        """Run a scorer's action; an error comes back to be shown, never raised out of the click."""
        from madtracker.store import StoreError

        if self.live is None:
            from madtracker.control.race import Outcome

            return Outcome(False, "Select a race first.")
        self._run_result_backup()
        race_id = self.live.race_id
        before = self._newest_action(race_id)
        try:
            return action()
        except StoreError as exc:
            return exc
        except Exception as exc:  # a bug must still answer the click
            # Not the store refusing but something unforeseen: the click
            # is answered on the red line and the traceback is logged. The
            # log is append-only, so a newer last row means the action
            # wrote before it failed.
            self._log_exception(exc)
            after = self._newest_action(race_id)
            known = _UNREAD not in (before, after)
            return _Unexpected(exc, (after != before) if known else None)

    def _newest_action(self, race_id: int) -> object:
        """The race's newest log row id, None for an empty log, _UNREAD when it cannot be read."""
        try:
            last = self.store.last_action(race_id)
        except Exception:  # the answer is only a better red line
            return _UNREAD
        return None if last is None else last.action_id

    @staticmethod
    def _log_exception(exc: BaseException) -> None:
        applog.error(
            "Unexpected error\n" + applog.traceback_text(type(exc), exc, exc.__traceback__)
        )

    def click(self, entrant_id: int) -> bool:
        before = self.live.state if self.live else None
        outcome = self._guard(lambda: self.live.click(entrant_id))
        overlay = self.live is not None and before != self.live.state
        return self._apply(outcome, overlay=overlay)

    def rider_action(self, entrant_id: int, key: str) -> bool:
        if self.live is None:
            return self._apply(self._guard(lambda: None))
        from madtracker.control.race import PENALTY
        from madtracker.scoring._common import penalty_of
        from madtracker.ui.icons import ask

        if key == "dq":
            who = self.live.label(entrant_id)
            if not ask(self.main, "Disqualify", f"Disqualify {who}?", verb="Disqualify"):
                return False
        elif key == "points_penalty":
            # The menu names the ruling; the number comes from the dialog,
            # and the key the controller records carries it.
            from madtracker.ui.penalty import PointsPenaltyDialog
            from madtracker.ui.widgets import run_dialog

            standing = penalty_of(self.live.actions(), entrant_id)
            dialog = PointsPenaltyDialog(self.live.label(entrant_id), standing, parent=self.main)
            if run_dialog(dialog) != dialog.DialogCode.Accepted:
                return False
            key = f"{PENALTY}{dialog.points()}"
        elif key in OUTCOME_ASKS:
            # A rider out of the race is a result, not a routine entry like
            # a lap, so a stray menu pick must not record one.
            title = OUTCOME_ASKS[key]
            who = self.live.label(entrant_id)
            verb = OUTCOME_VERBS.get(key, title)
            if not ask(self.main, title, f"Mark {who} {title}?", verb=verb):
                return False
        return self._apply(self._guard(lambda: self.live.act(entrant_id, key)))

    def race_action(self, key: str) -> bool:
        """The task line's ⋯: the officials' call on the race as a whole."""
        if self.live is None:
            return self._apply(self._guard(lambda: None))
        from madtracker.control.race import Outcome
        from madtracker.ui.icons import ask

        if key == "shorten_race":
            return self._shorten_race()
        if key != "end_race":
            return self._apply(Outcome(False, f"Unknown action {key!r}."))
        # Ending a race is a result, not a routine entry, so a stray menu
        # pick must not record one.
        if not ask(self.main, "End Race", END_RACE_QUESTION, verb="End Race"):
            return False
        return self._apply(self._guard(lambda: self.live.end_race()), overlay=True)

    def _shorten_race(self) -> bool:
        """Shorten Race...: the new sprint count from its box, then the entry (USAC 1G4(b))."""
        from madtracker.control.race import Outcome
        from madtracker.ui.shorten import ShortenRaceDialog
        from madtracker.ui.widgets import run_dialog

        asked = self._guard(lambda: (self.live.shorten_refusal(), self.live.shorten_bounds()))
        if not isinstance(asked, tuple):
            return self._apply(asked)
        refusal, (fewest, most) = asked
        if refusal is not None:
            return self._apply(Outcome(False, refusal))
        dialog = ShortenRaceDialog(fewest, most, parent=self.main)
        if run_dialog(dialog) != dialog.DialogCode.Accepted:
            return False
        count = dialog.count()
        return self._apply(self._guard(lambda: self.live.shorten_race(count)))

    def record_sprint(self) -> bool:
        # One replay checks the shortfall and records; a short sprint comes
        # back unrecorded, and the question is asked outside the controller.
        outcome = self._guard(lambda: self.live.record_sprint(ask_short=True))
        short = getattr(outcome, "short", None)
        if short is not None:
            # Fewer placed than the sprint awards is nearly always an early
            # tap: ask, Cancel the default (LiveRace.sprint_shortfall).
            from madtracker.ui.icons import ask

            have, need, n = short
            body = f"Only {have} of {need} places are clicked. Record Sprint {n} anyway?"
            if not ask(self.main, "Record Sprint", body, verb="Record"):
                return False
            outcome = self._guard(lambda: self.live.record_sprint())
        if getattr(outcome, "edit_gone", False):
            cancelled = self._guard(lambda: self.live.cancel_edit())
            if cancelled is not None:
                return self._apply(cancelled)
            self.refresh()
        return self._apply(outcome, overlay=True)

    def place_rest_together(self) -> bool:
        return self._apply(self._guard(lambda: self.live.place_rest_together()), overlay=True)

    def row_action(self, entrant_id: int, key: str) -> bool:
        if self.live is None:
            return self._apply(self._guard(lambda: None))
        from madtracker.control.race import MOVE_TO, MOVES, PENALTY, RIDER_ACTIONS, TIES

        moves = key in (*TIES, *MOVES) or key.startswith(MOVE_TO)
        if moves and not self.live.standings().is_complete:
            # A staged row's tie or move (a chase's clicks, from either end)
            # changes the staged order; an Elimination's out rows offer the
            # same keys while the race runs, and those are review moves.
            live = self.live
            staged = {e for g in [*live.staged(), *live.staged_tail()] for e in g}
            if entrant_id in staged:
                return self._apply(self._guard(lambda: live.move_staged(entrant_id, key)))

        if key in RIDER_ACTIONS or key.startswith(PENALTY):
            # The same entry as on the card, with the same question or dialog.
            return self.rider_action(entrant_id, key)
        return self._apply(self._guard(lambda: self.live.review(entrant_id, key)))

    def reopen_sprint(self, number: int) -> bool:
        return self._apply(self._guard(lambda: self.live.reopen_sprint(number)))

    def cancel_edit(self) -> bool:
        """Cancel on a reopened sprint: back to the result as it was."""
        if self.live is None or not self.live.editing:
            return False
        # Through the guard like every other write: a busy file or another
        # window's change is the red line, never a traceback from the slot.
        # The cancel answers nothing on success, so anything it answers is
        # a refusal or an error for _apply to show.
        outcome = self._guard(lambda: self.live.cancel_edit())
        if outcome is not None:
            return self._apply(outcome)
        self.main.show_problem(None)
        self.refresh()
        return True

    def _drop_edit(self) -> None:
        from madtracker.store import StoreError

        if self.live is not None and self.live.editing:
            self._run_result_backup()
            try:
                self.live.cancel_edit()
            except StoreError:
                # Leaving the race goes ahead; the correction stays staged
                # in the file and the race opens on it again, so nothing
                # entered is lost and the scorer can cancel it there.
                pass

    def undo(self) -> bool:
        return self._apply(self._guard(lambda: self.live.undo()))

    def mark_final(self) -> bool:
        return self._apply(self._guard(lambda: self.live.mark_final()))

    def reopen_race(self) -> bool:
        return self._apply(self._guard(lambda: self.live.reopen()))

    # Setup -------------------------------------------------------------

    def open_setup(self) -> None:
        if self.store is None or self.event is None:
            return
        self._drop_edit()
        self.main.setup.load(self.store, self.event.event_id)
        self.main.show_setup()

    def close_setup(self) -> None:
        """Score, on the program pane's switch: back to the race the scorer was on, else the first (design section 6)."""
        # The race is built afresh from the file below, so reloading it
        # first would only read every race again.
        self._after_setup_change(reload_live=False)
        self._select_after_change()

    def _select_after_change(self) -> None:
        """Show the race the scorer was on, else the first; the empty line when there is none."""
        if not self.races:
            from madtracker.ui.window import NO_RACES

            self.main.show_empty(NO_RACES)
            return
        target = self.races[0].race_id
        ids = [r.race_id for r in self.races]
        # Setup mid-night is for a late rider or a fix in a later race;
        # Score goes back to where the scorer was, not to the top of the
        # program. _after_setup_change drops a race that was removed.
        if self.live is not None and self.live.race_id in ids:
            target = self.live.race_id
        if self.live is not None and self.live.race_id == target:
            self.live = None
        self.select_race(target)

    def _after_setup_change(self, *, show: bool = True, reload_live: bool = True) -> None:
        """The event, the races and the live race as the file now holds them.

        ``show`` False leaves the program pane to the caller's own redraw;
        ``reload_live`` False is for a caller that builds the live race
        again anyway (Score), where reloading it first is wasted work.
        """
        if self.event is None:
            return
        name = self.event.name
        self.event = self.store.event(self.event.event_id)
        self.main.set_event(self.event.name, self.event.event_date)
        if self.event.name != name:
            # Each board repaints for its name; a bib or a race changes nothing there.
            for b in self.boards:
                b.set_event_name(self.event.name)
        self._reload_races()
        if self.live is not None and self.live.race_id in [r.race_id for r in self.races]:
            if reload_live:
                self.live.reload()
        else:
            self.live = None
        if show:
            self._show_program()

    # File menu ---------------------------------------------------------

    def new_event(self, name: str | None = None, date: str | None = None) -> int | None:
        """File > New Event: a name and a date, then the setup screen."""
        from madtracker.control import venue

        if self.store is None:
            return None
        if name is None:
            from madtracker.ui.setup import NewEventDialog
            from madtracker.ui.widgets import run_dialog

            dialog = NewEventDialog(self.store, self.main)
            if run_dialog(dialog) != dialog.DialogCode.Accepted or dialog.event_id is None:
                return None
            event_id = dialog.event_id
        else:
            event = self.store.add_event(name, date or "", venue=venue.venue_name(self.store))
            event_id = event.event_id
        self.open_event(event_id)
        # A program copied from an earlier event still has empty fields:
        # the setup screen is where they are filled, as for an empty one.
        if self.main.showing() != "setup":
            self.open_setup()
        return event_id

    def pick_event(self, event_id: int | None = None) -> None:
        from madtracker.ui import icons

        if self.store is None:
            return
        events = self.store.events()
        if not events:
            icons.inform(self.main, "Open Event", "No events yet: File > New Event...")
            return
        if event_id is None:
            from madtracker.ui.setup import OpenEventDialog
            from madtracker.ui.widgets import run_dialog

            current = self.event.event_id if self.event else None
            dialog = OpenEventDialog(self.store, current, self.main)
            accepted = run_dialog(dialog) == dialog.DialogCode.Accepted
            if current is not None and current in dialog.deleted:
                # The open event is gone: the newest left, or the empty start.
                self._forget_file()
                self._open_last_event()
            if not accepted or dialog.event_id is None:
                return
            event_id = dialog.event_id
        self.open_event(event_id)

    def open_data_folder(self) -> bool:
        """Help > Open Data Folder: the folder of the open file, with its log and backups.

        The default folder is hidden on Windows and macOS, and a scorer
        asked for the log on the phone should not need a typed path.
        """
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        folder = self.data_dir
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            return True
        self.main.report_failure(
            f"The data folder could not be opened:\n{folder}", "Open Data Folder"
        )
        return False

    def backup_now(self, dest: Path | None = None) -> Path | None:
        """File > Backup Now...: a copy where the scorer chooses, and the usual one beside the file.

        The one backup the scorer asks for goes where they say: a stick to
        take home, another laptop's share. The save dialog starts in the
        venue's backup folder (Settings), else Documents, with the
        dated backup name, so Enter puts it where the end-of-night copies
        go. The automatic copy beside the file is written as for any
        backup; the backup folder gets no second copy, since the scorer
        just chose where this one goes.
        """
        import sqlite3

        from madtracker.store import StoreError
        from madtracker.ui import icons

        if self.store is None:
            return None
        if dest is None:
            dest = self._backup_destination()
            if dest is None:
                return None
        if not dest.parent.is_dir():
            # A stick pulled after the save box chose it: making the folder
            # again would put the copy on whatever disk now has that path,
            # and say it was written.
            self.main.report_failure(
                f"The backup could not be written (the folder is not there any more):\n{dest}",
                title="Backup Now",
            )
            self.auto_backup()
            return None
        refusal = self._open_file_refusal(dest)
        if refusal:
            icons.warn(self.main, "Backup Now", refusal)
            return None
        self.auto_backup()
        try:
            path = self.store.backup_to(dest, self.event.name if self.event else "")
        except (StoreError, OSError, sqlite3.Error) as exc:
            reason = str(exc).rstrip(".")
            self.main.report_failure(
                f"The backup could not be written ({reason}):\n{dest}", title="Backup Now"
            )
            return None
        applog.info(f"Backup written: {path}")
        icons.inform(self.main, "Backup Now", f"Backup written to:\n{path}")
        return path

    def _backup_destination(self) -> Path | None:
        from PySide6.QtWidgets import QFileDialog

        from madtracker.control import venue
        from madtracker.control.backups import backup_name
        from madtracker.control.exports import documents_dir

        chosen = venue.chosen_backup_dir(self.store)
        folder = chosen if chosen is not None and os.path.isdir(chosen) else documents_dir()
        name = backup_name()
        path, _ = QFileDialog.getSaveFileName(
            self.main, "Backup Now", str(folder / name), DATA_FILE_FILTER
        )
        return Path(path) if path else None

    def _export_path(self, title: str, name: str, filter_: str) -> Path | None:
        from PySide6.QtWidgets import QFileDialog

        from madtracker.control import venue
        from madtracker.ui import icons

        chosen, _ = QFileDialog.getSaveFileName(
            self.main, title, str(venue.export_dir(self.store) / name), filter_
        )
        if not chosen:
            return None
        refusal = self._open_file_refusal(Path(chosen))
        if refusal:
            icons.warn(self.main, title, refusal)
            return None
        return Path(chosen)

    def _open_file_refusal(self, path: Path) -> str | None:
        """Why a save over ``path`` would wreck the open file, or None."""
        from madtracker.control.backups import open_file_refusal

        if self.store is None:
            return None
        return open_file_refusal(path, self.data_path)

    def _pdf_choice(self) -> tuple[list[tuple[int, str]], int | None, bool]:
        """The races the PDF dialog lists, the one it shows, and whether that race is the default.

        The list is the races that have started, as the whole event
        prints them. It shows the selected race; for one not started yet,
        the nearest started race before it, and the whole event is the
        default.
        """
        races = self.store.races(self.event.event_id)
        started = [(r.race_id, r.name) for r in races if r.state != "setup"]
        ids = [race_id for race_id, _ in started]
        selected = None if self.live is None else self.live.race_id
        if selected in ids:
            return started, selected, True
        order = [r.race_id for r in races]
        before = [i for i in ids if selected is None or order.index(i) < order.index(selected)]
        default = before[-1] if before else (ids[0] if ids else None)
        return started, default, False

    def _export_failed(self, title: str, path: Path | None, exc: Exception) -> None:
        """Say a failed export in a box where the scorer is looking.

        The scorer just asked for the file and waits for it; on Windows the
        usual cause is last time's copy still open in a PDF viewer or Excel,
        which holds it locked.
        """
        from madtracker.ui import icons

        reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
        # No path yet when the file failed while the name was suggested.
        where = f":\n{path}" if path is not None else "."
        icons.warn(
            self.main,
            title,
            f"Could not write ({reason}){where}\n\nIf the file is open in another"
            " program, close it and try again.",
        )
        return None

    def export_pdf(self, path=None, race_id=None, whole=False) -> Path | None:
        """File > Export Results PDF: the whole event, or one race picked from those started.

        With ``path`` given there are no dialogs: ``race_id`` names the race,
        or ``whole`` asks for the event.
        """
        from madtracker.control.exports import default_file_name, race_file_name
        from madtracker.export import write_results_pdf

        if self.event is None or self.store is None:
            self.main.report_failure("Open an event before exporting its results.", title="Export")
            return None
        if path is None:
            from madtracker.ui.setup import ExportPdfDialog
            from madtracker.ui.widgets import run_dialog

            races, default, race_first = self._pdf_choice()
            dialog = ExportPdfDialog(
                races, default=default, race_first=race_first, parent=self.main
            )
            if run_dialog(dialog) != dialog.DialogCode.Accepted:
                return None
            race_id = dialog.race_id()
            whole = race_id is None
        elif race_id is None:
            whole = True
        races = None if whole else [race_id]
        if path is None:
            if whole:
                suggested = default_file_name(self.event, "pdf")
            else:
                suggested = race_file_name(self.event, self.store.race(race_id).name)
            path = self._export_path("Export Results PDF", suggested, "PDF Files (*.pdf)")
            if path is None:
                return None
        path = Path(path)
        from fpdf.errors import FPDFException

        from madtracker.store import StoreError
        from madtracker.ui.widgets import busy

        missing: list[str] = []
        try:
            with busy():
                write_results_pdf(
                    self.store, self.event.event_id, path, races=races, unprintable=missing
                )
        except (OSError, ValueError, FPDFException, StoreError) as exc:
            # fpdf2's own refusals are plain Exceptions; one escaping the
            # slot would make Export Results PDF do nothing anyone could see.
            return self._export_failed("Export Results PDF", path, exc)
        if missing:
            from madtracker.ui import icons

            # The sheet is the archive copy: a name it cannot print is said
            # now, while the scorer can still write it in by hand.
            shown = "\n".join(missing[:8]) + ("\n..." if len(missing) > 8 else "")
            icons.warn(
                self.main,
                "Export Results PDF",
                f"The PDF was written, but its font has no letters for some of these, so they"
                f" show as ? in their place:\n{shown}",
            )
        return path

    def open_standings(self) -> None:
        """File > Multi-Race Standings: the dialog; its Export PDF... comes back to export_standings."""
        import sqlite3

        from madtracker.store import StoreError
        from madtracker.ui.standings import open_standings

        if self.store is None:
            return
        try:
            open_standings(self.store, self.main, export=self.export_standings)
        except (StoreError, sqlite3.Error) as exc:
            # A file that fails a read the dialog's own slots do not guard
            # closes the dialog with the reason, in place of the crash box.
            self.main.report_failure(str(exc), title="Multi-Race Standings")

    def export_standings(self, standings_id: int, path=None) -> Path | None:
        """A standings' PDF, with the save box, folder, and failure boxes of Export Results PDF."""
        from fpdf.errors import FPDFException

        # Imported here: the sheet's module is its own package of work, and
        # the dialog opens without it.
        from madtracker.control import multi_race
        from madtracker.export.standings_pdf import suggested_standings_name, write_standings_pdf
        from madtracker.store import StoreError
        from madtracker.ui import icons
        from madtracker.ui.widgets import busy

        title = "Export Standings PDF"
        if self.store is None:
            return None
        missing: list[str] = []
        try:
            if path is None:
                # The suggested name reads the file, so a refusal there is
                # the same failed export as one while writing.
                table = multi_race.compute(self.store, standings_id)
                path = self._export_path(
                    title, suggested_standings_name(table), "PDF Files (*.pdf)"
                )
                if path is None:
                    return None
            path = Path(path)
            with busy():
                write_standings_pdf(self.store, standings_id, path, unprintable=missing)
        except (OSError, ValueError, FPDFException, StoreError) as exc:
            return self._export_failed(title, path, exc)
        if missing:
            shown = "\n".join(missing[:8]) + ("\n..." if len(missing) > 8 else "")
            icons.warn(
                self.main,
                title,
                f"The PDF was written, but its font has no letters for some of these, so they"
                f" show as ? in their place:\n{shown}",
            )
        return path

    def export_program(self, path=None) -> Path | None:
        """File > Export Program PDF: who starts in which race, for the riders and the announcer."""
        from fpdf.errors import FPDFException

        from madtracker.control.exports import default_file_name
        from madtracker.export.program import write_program_pdf
        from madtracker.store import StoreError
        from madtracker.ui import icons
        from madtracker.ui.widgets import busy

        if self.event is None or self.store is None:
            self.main.report_failure("Open an event before exporting its program.", title="Export")
            return None
        if path is None:
            path = self._export_path(
                "Export Program PDF", default_file_name(self.event, "program"), "PDF Files (*.pdf)"
            )
            if path is None:
                return None
        path = Path(path)
        missing: list[str] = []
        try:
            with busy():
                write_program_pdf(self.store, self.event.event_id, path, unprintable=missing)
        except (OSError, ValueError, FPDFException, StoreError) as exc:
            return self._export_failed("Export Program PDF", path, exc)
        if missing:
            shown = "\n".join(missing[:8]) + ("\n..." if len(missing) > 8 else "")
            icons.warn(
                self.main,
                "Export Program PDF",
                f"The PDF was written, but its font has no letters for some of these, so they"
                f" show as ? in their place:\n{shown}",
            )
        return path

    def export_csv(self, path=None) -> Path | None:
        """File > Export USAC CSV: the finished races, uploaded once at the end."""
        from madtracker.control.exports import (
            default_file_name,
            usac_report_plain,
            usac_report_text,
        )
        from madtracker.export import write_usac_csv
        from madtracker.ui import icons

        if self.event is None or self.store is None:
            self.main.report_failure("Open an event before exporting its results.", title="Export")
            return None
        if path is None:
            path = self._export_path(
                "Export USAC CSV", default_file_name(self.event, "csv"), "CSV Files (*.csv)"
            )
            if path is None:
                return None
        path = Path(path)
        from madtracker.store import StoreError
        from madtracker.ui.widgets import busy

        try:
            with busy():
                report = write_usac_csv(self.store, self.event.event_id, path)
        except (OSError, ValueError, StoreError) as exc:
            return self._export_failed("Export USAC CSV", path, exc)
        icons.inform(
            self.main,
            "Export USAC CSV",
            usac_report_text(report),
            chars=64,
            copy=usac_report_plain(report),
            rich=True,
        )
        return path

    def manage_riders(self) -> None:
        """File > Edit Riders: the venue's riders, kept with or without an event open."""
        from madtracker.ui.setup import RidersDialog
        from madtracker.ui.widgets import run_dialog

        if self.store is None:
            return
        # An import offers to put its riders on the open event's roster.
        event_id = self.event.event_id if self.event is not None else None
        if not self._open_guarded(
            lambda: run_dialog(RidersDialog(self.store, None, self.main, import_event=event_id))
        ):
            return
        if self.event is None:
            self._show_welcome()
            return
        # A renamed rider must read the new way everywhere a name shows;
        # the race caches its field, so it is re-read before the redraw.
        # refresh draws the program pane, so each branch draws it once.
        self._after_setup_change(show=False)
        if self.main.showing() == "setup":
            self.main.setup.refresh()
            self._show_program()
        elif self.live is not None:
            self.refresh()
        else:
            self._show_program()

    def edit_settings(self) -> None:
        from madtracker.ui.settings import open_settings

        if self.store is None:
            return
        if open_settings(self.store, self.data_dir, self.main):
            self.apply_venue()
            if self.event is None and not self.damaged:
                self._show_welcome()
            if self.live is not None:
                self.live.reload()
            if self.main.showing() == "setup":
                # As Edit Riders does: the setup screen stays, refreshed.
                self.main.setup.refresh()
            elif self.live is not None:
                self.refresh()


def install_excepthook(controller: AppController | None = None) -> None:
    """Every exception that escapes a click: logged, and said once in a box.

    PySide6 hands an exception raised in a slot to sys.excepthook and
    carries on. The packaged program is windowed, with no console, so
    without this a click that hit a bug would do nothing and say nothing.
    Installed before the controller exists, so a failure while it is
    built reaches the log; the box needs a window, so until
    ``set_excepthook_controller`` names one the hook only logs.
    """
    seen: set[str] = set()
    busy = [False]

    def hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        text = applog.traceback_text(exc_type, exc, tb)
        applog.error("Unexpected error\n" + text)
        applog.flush()
        if text in seen or busy[0]:
            return
        seen.add(text)
        busy[0] = True
        try:
            target = _HOOK_TARGET[0]
            if target is not None:
                log = applog.log_path() or applog.LOG_NAME
                target.main.report_failure(CRASH_TEXT.format(log=log), title="Problem")
        except Exception:  # a box that fails must not loop back here
            pass
        finally:
            busy[0] = False

    _HOOK_TARGET[0] = controller
    sys.excepthook = hook


# The controller whose window the hook's box opens on; None until one is built.
_HOOK_TARGET: list[AppController | None] = [None]


def set_excepthook_controller(controller: AppController) -> None:
    _HOOK_TARGET[0] = controller


def _say(lines: list[str]) -> None:
    """Print when there is a console; the packaged exe is windowed and has none."""
    out = sys.stdout
    if out is None:
        return
    try:
        out.write("\n".join(lines) + "\n")
        out.flush()
    except (OSError, ValueError):
        pass


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from madtracker import APP_NAME

    parser = argparse.ArgumentParser(prog="madtracker", description=APP_NAME)
    parser.add_argument(
        "--demo", action="store_true", help="seed a sample event into a temporary folder"
    )
    parser.add_argument("--data-dir", metavar="DIR", help="folder holding the data file")
    parser.add_argument("--mockup", metavar="DIR", help="write screenshots to DIR and exit")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="check the store and the exports in a scratch folder, print PASS or the failures",
    )
    args, qt_args = parser.parse_known_args(sys.argv[1:] if argv is None else list(argv))

    if args.self_test:
        from madtracker.control.selftest import run_full_selftest
        from madtracker.store.paths import default_data_dir

        failures = run_full_selftest()
        lines = ["FAIL", *(f"  {f}" for f in failures)] if failures else ["PASS"]
        data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
        log = data_dir / SELF_TEST_LOG
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            lines.append(f"  could not write {log}: {exc}")
        _say(lines)
        return 1 if failures else 0

    from madtracker.platform_name import claim_process_name, sets_window_icon

    claim_process_name(APP_NAME)
    app = QApplication.instance() or QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    from madtracker.assets import app_icon
    from madtracker.ui.look import apply_look

    apply_look(app)
    if sets_window_icon():
        app.setWindowIcon(app_icon())

    if args.mockup:
        from madtracker.ui.mockup import render_mockups

        _say([str(path) for path in render_mockups(args.mockup)])
        return 0

    # Only the normal start shows a splash: --self-test and --mockup have
    # returned above, and the tests build AppController directly.
    from madtracker.ui.splash import show_splash

    splash = show_splash(app)
    install_excepthook()
    controller = AppController(app, demo=args.demo, data_dir=args.data_dir)
    set_excepthook_controller(controller)
    controller.start()
    # Here, not in AppController: the tests build the controller and must
    # never hold the test machine's displays on.
    from madtracker.keep_awake import hold

    if not hold(APP_NAME):
        applog.warning("The system did not agree to keep the displays on.")
    splash.finish(controller.main)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
