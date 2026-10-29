"""The window: the program over the TV preview on the left, the surface beside them, a bar along the bottom.

The bar is under the columns, each control under what it governs: Edit |
Score as wide as the program, Undo across the surface. The preview
under the program is the TV's one control: a click on it switches the
TV between the logo and the race. The middle shows the
setup screen, the scoring surface for the selected race, or a line
saying what to do when there is no event yet. The menus hold only what
is rare: File, Scoreboard, Help. The window emits signals and draws
what it is given; ``madtracker.app`` does the wiring.
"""

import sys

from PySide6.QtCore import QByteArray, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from madtracker import APP_NAME, applog
from madtracker.control.race import NOTHING_TO_UNDO_LABEL, Screen
from madtracker.dates import show_date
from madtracker.displays import AUTOMATIC, NO_DISPLAY, NONE_LABEL
from madtracker.ui import style
from madtracker.ui.help import HELP_HERE
from madtracker.ui.help import PAGES as HELP_PAGES
from madtracker.ui.icons import ask, set_button_icon
from madtracker.ui.program import ProgramPane, ProgramRow
from madtracker.ui.setup import SetupScreen
from madtracker.ui.surface import Surface
from madtracker.ui.tv import TvPane
from madtracker.ui.widgets import UndoButton, run_dialog, settings_word

BODY_PT = 12
# Help pages whose first letter another item took: Demo Data File has the M.
HELP_LETTERS = {"multi_race": "Multi-Race S&tandings"}
NO_EVENT = "No event yet"
NO_RACES = "No races yet. Edit Event > Program."
# The program follows the window's width, never narrower than this: the
# pane fits a race name and its tag, and the switch under it fits "Edit"
# and "Score" in Inter.
PROGRAM_MIN_W = 264
PROGRAM_SHARE = 0.18
# A narrower window gives the surface the room instead: with the full
# floor a 1080p laptop at 150% (1280 wide) would keep one column of cards,
# four riders of ten in view, and a 1366 by 768 one at 125% (about 1090
# wide) could not fit the window at all. Below NARROW_W the program takes
# a smaller floor; 1366 at 100%, the layout everything is checked at, is
# above it.
NARROW_W = 1300
PROGRAM_NARROW_W = 240
BAR_H = 48


def window_name() -> str:
    """The title bar's name: the app's alone, since a version there distracts.

    The version is in About.
    """
    return APP_NAME


def window_title(name: str, date: str, platform: str | None = None) -> str:
    """The event first, as a document's window names it, in each platform's way.

    Windows and Linux: ``Race Night 12 (2026-Oct-16) - MadTracker``. macOS:
    ``Race Night 12 (2026-Oct-16)``, the document alone, since the menu bar
    names the app. The date in parentheses, so a comma
    never reads as part of the event's name. With no event, the app's name.
    """
    if not name:
        return window_name()
    when = show_date(date) if date else ""
    document = f"{name} ({when})" if when else name
    platform = sys.platform if platform is None else platform
    if platform == "darwin":
        return document
    return f"{document} - {window_name()}"


def settings_in_file_menu(platform: str | None = None) -> bool:
    """Whether Settings... shows on the File menu.

    On macOS Qt moves an item with the Preferences role to the
    application menu, so the File menu has no Settings there.
    """
    platform = sys.platform if platform is None else platform
    return platform != "darwin"


def place_window(main: QWidget, saved: object, screens: list[QRect] | None = None) -> None:
    """Put the window where it was last closed, or maximized on the primary screen. Call before show().

    The scorer runs the app maximized on a laptop, so a first start
    opens that way rather than at a size picked for a desk monitor.
    A saved place that no screen's available area touches (a display
    since unplugged) would open the window out of reach, so it is
    dropped for the first-start placement. ``screens`` is the list of
    available areas, read from the running screens when not given.
    """
    if screens is None:
        screens = [s.availableGeometry() for s in QGuiApplication.screens()]
    if isinstance(saved, bytes):
        saved = QByteArray(saved)
    if isinstance(saved, QByteArray) and not saved.isEmpty() and main.restoreGeometry(saved):
        if any(main.geometry().intersects(area) for area in screens):
            return
    primary = QGuiApplication.primaryScreen()
    area = primary.availableGeometry() if primary is not None else QRect(0, 0, 1600, 900)
    # The normal size behind the maximized window, for when the scorer
    # restores it: never larger than the screen it opens on.
    normal = QSize(min(1600, area.width()), min(900, area.height()))
    main.setWindowState(Qt.WindowState.WindowNoState)
    main.setGeometry(
        QRect(area.topLeft(), normal).translated(
            (area.width() - normal.width()) // 2, (area.height() - normal.height()) // 2
        )
    )
    main.setWindowState(Qt.WindowState.WindowMaximized)


class MainWindow(QMainWindow):
    # The surface
    race_selected = Signal(int)
    setup_requested = Signal()
    setup_done = Signal()
    card_clicked = Signal(int)
    rider_action = Signal(int, str)
    race_action = Signal(str)
    record_requested = Signal()
    rest_together_requested = Signal()
    row_action = Signal(int, str)
    sprint_clicked = Signal(int)
    final_requested = Signal()
    reopen_requested = Signal()
    cancel_edit_requested = Signal()
    # The TV region
    live_toggled = Signal(bool)
    undo_requested = Signal()
    # File
    new_event_requested = Signal()
    open_event_requested = Signal()
    riders_requested = Signal()
    new_file_requested = Signal()
    open_file_requested = Signal()
    open_demo_requested = Signal()
    export_program_requested = Signal()
    export_pdf_requested = Signal()
    export_csv_requested = Signal()
    standings_requested = Signal()
    backup_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()
    open_data_folder_requested = Signal()
    # Scoreboard: a display's name, None for Automatic, NO_DISPLAY for off.
    display_chosen = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(window_name())
        self.setFont(style.ui_font(BODY_PT))
        self.setStyleSheet(style.stylesheet(BODY_PT))
        self.resize(1600, 900)

        self.program = ProgramPane()
        self.program.race_selected.connect(self.race_selected)
        self.program.setup_requested.connect(self.setup_requested)

        self.surface = Surface()
        self.surface.card_clicked.connect(self.card_clicked)
        self.surface.rider_action.connect(self.rider_action)
        self.surface.race_action.connect(self.race_action)
        self.surface.record_requested.connect(self.record_requested)
        self.surface.rest_together_requested.connect(self.rest_together_requested)
        self.surface.row_action.connect(self.row_action)
        self.surface.sprint_clicked.connect(self.sprint_clicked)
        self.surface.final_requested.connect(self.final_requested)
        self.surface.reopen_requested.connect(self.reopen_requested)
        self.surface.cancel_requested.connect(self.cancel_edit_requested)
        self.setup = SetupScreen()
        # Score, the program pane's switch while setup is open.
        self.program.score_requested.connect(self.setup_done)
        # On a 768-pixel screen the setup screen (six program rows at the
        # least) can be taller than the window; it scrolls rather than
        # forcing the whole window, and the scoring surface, taller.
        self.setup_scroll = QScrollArea()
        self.setup_scroll.setObjectName("central")
        self.setup_scroll.setWidgetResizable(True)
        self.setup_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # Sideways only when the middle is narrower than the screen's
        # widest row (the program's buttons), so nothing is out of reach.
        self.setup_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setup_scroll.setWidget(self.setup)
        self.empty = QWidget()
        self.empty.setObjectName("pane")
        self.empty_text = QLabel(NO_EVENT)
        self.empty_text.setObjectName("hint")
        self.empty_text.setFont(style.ui_font(14))
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_text.setWordWrap(True)
        # A first night's three steps, in order, as buttons on the empty
        # screen rather than directions to the File menu: the venue's
        # name for the sheets, the riders, then the event. Each is the
        # File menu's own item; a step already done carries a check.
        self.welcome = QWidget()
        steps = QVBoxLayout(self.welcome)
        steps.setContentsMargins(0, 0, 0, 0)
        steps.setSpacing(style.SM)
        self.welcome_settings = QPushButton(f"{settings_word()}...")
        self.welcome_settings.clicked.connect(self.settings_requested)
        self.welcome_riders = QPushButton("Edit Riders...")
        self.welcome_riders.clicked.connect(self.riders_requested)
        self.welcome_event = QPushButton("New Event...")
        self.welcome_event.setObjectName("primary")
        self.welcome_event.clicked.connect(self.new_event_requested)
        for b in (self.welcome_settings, self.welcome_riders, self.welcome_event):
            b.setFont(style.ui_font(13))
            b.setMinimumHeight(44)
            b.setMinimumWidth(240)
            b.setIconSize(QSize(20, 20))
            steps.addWidget(b)
        empty_lay = QVBoxLayout(self.empty)
        empty_lay.addStretch(1)
        empty_lay.addWidget(self.empty_text)
        empty_lay.addSpacing(style.LG)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.welcome)
        row.addStretch(1)
        empty_lay.addLayout(row)
        empty_lay.addStretch(1)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.surface)
        self.stack.addWidget(self.setup_scroll)

        self.tv = TvPane()
        self.board_preview = self.tv.canvas
        self.program.place_preview(self.tv)
        self.tv.live_toggled.connect(self._face_chosen)
        # Undo names what it takes back and is cut to the room it has, so
        # a long name never widens the bar. No focus: after a click it
        # would keep it, and Space or Enter would undo once more.
        self.undo = UndoButton(NOTHING_TO_UNDO_LABEL)
        self.undo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.undo.setObjectName("undo")
        set_button_icon(self.undo, "undo", lift=1)
        # Both the bar's height exactly: a minimum alone would leave Undo two
        # pixels under the switch, centered a pixel off its row.
        self.undo.setFixedHeight(BAR_H)
        self.undo.setFont(style.ui_font(12, bold=True))
        self.undo.setEnabled(False)
        self.undo.clicked.connect(self.undo_requested)
        # The platform's Undo key (Command-Z, Ctrl+Z) is the button. A text
        # field with the focus keeps the key for its own undo, as Qt
        # offers it the key first.
        self.undo_key = QAction(self)
        self.undo_key.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_key.triggered.connect(self._undo_key)
        self.addAction(self.undo_key)
        self.program.mode.setFixedHeight(BAR_H)
        self._hidden = False
        self._live_ready = True

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.program)
        self.splitter.addWidget(self.stack)
        self.program.setMinimumWidth(PROGRAM_NARROW_W)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)
        # The columns as far apart as the panes in a column, and as the
        # window's margin: one gap everywhere, not Qt's narrower handle.
        self.splitter.setHandleWidth(style.SM)
        # Once the scorer drags a divider, their widths stand.
        self._split_by_hand = False
        self.splitter.splitterMoved.connect(self._split_moved)
        central = QWidget()
        central.setObjectName("central")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # The icon's rainbow, once, edge to edge under the menu bar: the
        # one place the window wears it, so it brands without decorating.
        band = QFrame()
        band.setObjectName("rainbow")
        band.setFixedHeight(style.RAINBOW_PX)
        outer.addWidget(band)
        lay = QVBoxLayout()
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        lay.addWidget(self.splitter, 1)
        # The bar: each control under the column it governs. Edit | Score
        # keeps the program's width (set with the splitter); Undo takes
        # the surface's.
        self.bar = QHBoxLayout()
        self.bar.setSpacing(style.SM)
        self.bar.addWidget(self.program.mode)
        self.bar.addWidget(self.undo, 1)
        lay.addLayout(self.bar)
        outer.addLayout(lay, 1)
        self.setCentralWidget(central)
        self._build_menus()
        self._screens: list[tuple[str, str]] = []

    def _split_moved(self, *_args) -> None:
        self._split_by_hand = True
        self._fit_bar()

    def program_width(self, width: int) -> int:
        """The program's width for a window ``width`` wide."""
        floor = PROGRAM_NARROW_W if width < NARROW_W else PROGRAM_MIN_W
        return max(floor, round(width * PROGRAM_SHARE))

    def _fit_bar(self) -> None:
        """Edit | Score as wide as the program's column, whatever the divider says."""
        width = self.program.width() if self.program.isVisible() else 0
        self.program.mode.setFixedWidth(width or self.program_width(self.width()))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit_bar()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._split_by_hand:
            total = sum(self.splitter.sizes()) or self.splitter.width()
            left = self.program_width(self.width())
            self.splitter.blockSignals(True)
            self.splitter.setSizes([left, max(1, total - left)])
            self.splitter.blockSignals(False)
        # After the splitter has laid the columns out at the new width.
        QTimer.singleShot(0, self, self._fit_bar)

    # ----- menus --------------------------------------------------------

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        # Grouped by the job and ordered by how often: the event and its
        # riders, the end-of-night exports, Backup Now (a safety copy, not
        # an export, so it stands alone), Settings (set once), then the
        # data files, rare and the most far-reaching, kept away from a
        # quick reach for Open Event.
        # Each item has its own letter after Alt+F, as Windows users expect.
        self.new_event_action = self._action(file_menu, "&New Event...", self.new_event_requested)
        self.open_event_action = self._action(
            file_menu, "&Open Event...", self.open_event_requested
        )
        # The riders belong to the venue, like the data file, not to an event.
        self.riders_action = self._action(file_menu, "Edit &Riders...", self.riders_requested)
        file_menu.addSeparator()
        # Before the night, then after it: who rides what, then the results.
        self.export_program_action = self._action(
            file_menu, "Export Pro&gram PDF...", self.export_program_requested
        )
        self.export_pdf_action = self._action(
            file_menu, "Export Res&ults PDF...", self.export_pdf_requested
        )
        self.export_csv_action = self._action(
            file_menu, "Export USAC &CSV...", self.export_csv_requested
        )
        # After the night's own exports: a standings sums Madisons over
        # several nights, an end-of-night job that is also a season's.
        self.standings_action = self._action(
            file_menu, "Multi-Race S&tandings...", self.standings_requested
        )
        file_menu.addSeparator()
        self.backup_action = self._action(file_menu, "&Backup Now...", self.backup_requested)
        file_menu.addSeparator()
        self.settings_action = self._action(file_menu, "&Settings...", self.settings_requested)
        # On macOS this goes to the application menu as Preferences..., with
        # Cmd+, (Qt names it); explicit, so a reworded item keeps the role.
        self.settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        # Command-comma on macOS; the key is none elsewhere.
        self.settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        # Where Settings leaves for the application menu, its own closing
        # divider would sit against Backup Now's, a doubled line.
        if settings_in_file_menu():
            file_menu.addSeparator()
        self._action(file_menu, "New &Data File...", self.new_file_requested)
        self.open_file_action = self._action(
            file_menu, "Open Data &File...", self.open_file_requested
        )
        file_menu.addSeparator()
        self.quit_action = self._action(file_menu, "&Quit", self.request_quit, "Ctrl+Q")
        self.file_menu = file_menu
        self._file_usable = True
        self._has_event = False
        self._sync_exports()

        board_menu = bar.addMenu("&Scoreboard")
        # One list of where the board goes: Automatic, each display with
        # what the board is there, None for off. The
        # entries are rebuilt by set_screens before this separator.
        self.display_group = QActionGroup(self)
        self.display_group.setExclusive(True)
        self._display_end = board_menu.addSeparator()
        self._chosen: str | None = None
        self._shown = True
        # Logo and Live are one choice; the check marks are kept by hand
        # so the menu and the preview's click never disagree.
        self.logo_action = QAction("&Logo", self)
        self.logo_action.setCheckable(True)
        self.logo_action.setChecked(True)
        self.live_action = QAction("Li&ve", self)
        self.live_action.setCheckable(True)
        self.logo_action.triggered.connect(lambda: self._face_chosen(False))
        self.live_action.triggered.connect(lambda: self._face_chosen(True))
        board_menu.addAction(self.logo_action)
        board_menu.addAction(self.live_action)
        self.board_menu = board_menu
        self.set_screens([], None)

        help_menu = bar.addMenu("&Help")
        self.help_window = None
        # One item per help page, by its title. F1 is apart from them: it
        # opens the help for the screen in view, not always the first page.
        self.help_actions = {}
        for key, title, _name in HELP_PAGES:
            # A page's Alt letter is its first unless another page took it.
            lettered = HELP_LETTERS.get(key, "&" + title)
            self.help_actions[key] = self._action(
                help_menu, lettered, lambda _=False, k=key: self.open_help(k)
            )
        self.help_here = QAction(self)
        # F1 everywhere, and the platform's help key where that is another
        # (Command-? on macOS).
        keys = {
            k.toString(): k
            for k in (
                QKeySequence(Qt.Key.Key_F1),
                QKeySequence(QKeySequence.StandardKey.HelpContents),
            )
        }
        self.help_here.setShortcuts(list(keys.values()))
        self.help_here.triggered.connect(self.open_help_here)
        self.addAction(self.help_here)
        help_menu.addSeparator()
        # A sample data file for a new scorer to try every format in: under
        # the help pages, as it is a way to learn the program and rarely
        # used once a venue has its own file. The ellipsis, as it
        # asks Open Previous or Create New before it opens anything.
        self.open_demo_action = self._action(
            help_menu, "De&mo Data File...", self.open_demo_requested
        )
        help_menu.addSeparator()
        # Where the log and the backups are, for a scorer asked to send
        # them; the folder is hidden on Windows and macOS.
        self.data_folder_action = self._action(
            help_menu, "Open Data &Folder", self.open_data_folder_requested
        )
        self.about_action = self._action(help_menu, f"&About {APP_NAME}", self.show_about)
        self.help_menu = help_menu

    def _action(self, menu: QMenu, text: str, slot, shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def set_screens(self, screens: list[tuple[str, str]], chosen: str | None) -> None:
        """Rebuild the Scoreboard menu's list: Automatic, each display, None; one ticked.

        ``chosen`` is the stored display's name, or None for Automatic;
        None (the entry) is ticked while the board is off.
        """
        self._screens = list(screens)
        self._chosen = chosen
        for action in self.display_group.actions():
            self.display_group.removeAction(action)
            self.board_menu.removeAction(action)
        # A display with no name (the offscreen platform's) cannot be
        # remembered, so it is not offered: Automatic still finds it.
        # No Alt letters here: the board's display is never switched from
        # the keyboard, and a display's name is the
        # driver's, so it carries no letter of its own.
        entries: list[tuple[str | None, str]] = [
            (None, AUTOMATIC),
            *[s for s in screens if s[0]],
            (NO_DISPLAY, NONE_LABEL),
        ]
        for name, label in entries:
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda _c=False, n=name: self.display_chosen.emit(n))
            self.display_group.addAction(action)
            self.board_menu.insertAction(self._display_end, action)
        self._tick_display()

    def _tick_display(self) -> None:
        """None while the board is off; else the chosen display, else Automatic."""
        for action in self.display_group.actions():
            action.setChecked(False)
        actions = self.display_group.actions()
        if not actions:
            return
        if not self._shown:
            actions[-1].setChecked(True)
            return
        names = [None, *[s[0] for s in self._screens if s[0]], NO_DISPLAY]
        at = names.index(self._chosen) if self._chosen in names else 0
        actions[at].setChecked(True)

    @property
    def none_action(self) -> QAction:
        """The list's None entry, the board off."""
        return self.display_group.actions()[-1]

    def display_labels(self) -> list[str]:
        return [a.text() for a in self.display_group.actions()]

    def set_board_shown(self, shown: bool) -> None:
        self._shown = shown
        self._tick_display()
        self.tv.set_board_hidden(not shown)
        self._hidden = not shown
        self._offer_live()

    def _offer_live(self) -> None:
        """Logo and Live in the menu, like the picture's click: not while the board is hidden,
        and Live not before there is a race to show. A display picked in the list is the
        one way back, to what was behind the veil."""
        self.logo_action.setEnabled(not self._hidden)
        self.live_action.setEnabled(self._live_ready and not self._hidden)

    def _face_chosen(self, live: bool) -> None:
        """Logo or Live from the menu or a click on the preview: both follow, and the app hears."""
        self.set_board_live(live)
        self.live_toggled.emit(live)

    def set_live_ready(self, ready: bool) -> None:
        """Live is offered only once the program has a race to show."""
        self.tv.set_ready(ready)
        self._live_ready = ready
        self._offer_live()

    def set_board_live(self, live: bool) -> None:
        """The preview and the menu agree, without re-emitting."""
        self.tv.set_live(live)
        for action, on in ((self.live_action, live), (self.logo_action, not live)):
            if action.isChecked() != on:
                action.blockSignals(True)
                action.setChecked(on)
                action.blockSignals(False)

    # ----- the middle ---------------------------------------------------

    def show_screen(self, screen: Screen) -> None:
        self.program.set_setup_open(False)
        self.surface.show_screen(screen)
        self.stack.setCurrentWidget(self.surface)

    def show_setup(self) -> None:
        self.program.set_setup_open(True)
        # Undo changes the race the setup screen hides; Score first.
        self.undo.setEnabled(False)
        self.stack.setCurrentWidget(self.setup_scroll)
        self.setup_scroll.verticalScrollBar().setValue(0)

    def show_empty(self, text: str, welcome: bool = False) -> None:
        self.program.set_setup_open(False)
        self.empty_text.setText(text)
        self.welcome.setVisible(welcome)
        if welcome:
            # Focus on the next step, New Event, not the first button:
            # a focus ring on Settings would read as Settings being selected.
            self.welcome_event.setFocus()
        self.surface.show_screen(None)
        self.stack.setCurrentWidget(self.empty)

    def set_welcome_done(self, settings: bool, riders: bool) -> None:
        """A check on each first-night step already done."""
        for button, done in ((self.welcome_settings, settings), (self.welcome_riders, riders)):
            if done:
                set_button_icon(button, "check", style.ACCENT, size=20)
            else:
                button.setIcon(QIcon())

    def showing(self) -> str:
        """Which middle screen is up: setup, surface or empty."""
        w = self.stack.currentWidget()
        if w is self.setup_scroll:
            return "setup"
        return "surface" if w is self.surface else "empty"

    def show_problem(self, text: str | None) -> None:
        if text:
            applog.info(f"Refused: {text}")
        self.surface.show_problem(text)

    def set_file_usable(self, usable: bool) -> None:
        """Off while the file is damaged or none is open: only another file, Help and Quit.

        With a damaged file left on, Edit Riders would read a bad page and
        raise out of the click.
        """
        for action in (
            self.new_event_action,
            self.open_event_action,
            self.riders_action,
            self.standings_action,
            self.backup_action,
            self.settings_action,
        ):
            action.setEnabled(usable)
        for button in (self.welcome_settings, self.welcome_riders, self.welcome_event):
            button.setEnabled(usable)
        self._file_usable = usable
        self._sync_exports()

    def _sync_exports(self) -> None:
        """The event's exports: on with a usable file and an event open, else grayed."""
        on = self._file_usable and self._has_event
        for action in (self.export_program_action, self.export_pdf_action, self.export_csv_action):
            action.setEnabled(on)

    def report_failure(self, text: str, title: str = "Problem", name: str = "") -> None:
        """A failure the scorer must know about is a message box, and there is no status bar.

        A bar that appeared only on a failure would move the whole window
        the first time it showed, and a strip that is always there is a
        thing to watch for nothing. A box is seen, read and
        dismissed; a refusal that answers a click goes on the surface's
        red line instead, through show_problem.
        """
        from madtracker.ui import icons

        applog.warning(f"{title}: {text}")
        icons.warn(self, title, text, name)

    def set_undo(self, text: str, enabled: bool, who: str = "") -> None:
        """``who`` is the rider or team the label names, set apart in the button's drawing."""
        self.undo.set_label(text, who)
        self.undo.setEnabled(enabled)

    def set_event(self, name: str, date: str) -> None:
        """The open event, or none for a blank name: an event always has one."""
        self.program.set_event(name, date)
        self.setWindowTitle(window_title(name, date))
        self._has_event = bool(name)
        self._sync_exports()

    def set_races(
        self,
        rows: list[ProgramRow],
        current: int | None,
    ) -> None:
        self.program.set_races(rows, current)

    # ----- help and quit ------------------------------------------------

    def show_about(self) -> None:
        from madtracker.ui.about import AboutDialog

        run_dialog(AboutDialog(self))

    def _undo_key(self) -> None:
        if self.undo.isEnabled():
            self.undo_requested.emit()

    def open_help(self, key: str = "start", section: str | None = None) -> None:
        """One help window for every Help item; it stays open beside the race."""
        from madtracker.ui.help import HelpWindow

        if self.help_window is None:
            self.help_window = HelpWindow(self)
        self.help_window.show_page(key, section)

    def open_help_here(self) -> None:
        """F1: the help for the screen in view, at its section."""
        self.open_help(*HELP_HERE[self.showing()])

    def confirm_quit(self) -> bool:
        return ask(self, "Quit", f"Quit {APP_NAME}?", verb="Quit")

    def request_quit(self) -> None:
        if self.confirm_quit():
            self.quit_requested.emit()

    def closeEvent(self, event) -> None:
        if event.spontaneous():
            event.ignore()
            self.request_quit()
            return
        event.accept()
