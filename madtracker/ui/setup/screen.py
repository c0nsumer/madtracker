"""The Edit Event screen: the event, the roster, and the program, top to bottom."""

from PySide6.QtCore import QDate, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from madtracker.control import groups as group_rules
from madtracker.control import program, rulesets
from madtracker.control.formats import TEAM_FORMATS
from madtracker.control.groups import canonical_group, event_spellings
from madtracker.control.riders import USAC_LICENSE
from madtracker.control.roster import roster_bib_refusal, typed_bib
from madtracker.export.glyphs import prints
from madtracker.scoring.replay import FORMAT_ENGINE
from madtracker.store import RosterEntry, Store, StoreError
from madtracker.ui import icons, style
from madtracker.ui.icons import mdi
from madtracker.ui.look import APP_PT
from madtracker.ui.setup._shared import (
    NO_GROUP,
    _refusal_line,
    _refuse,
    _typed,
    _TypingDelegate,
    first_key,
    name_key,
)
from madtracker.ui.setup.groups import GroupsDialog
from madtracker.ui.setup.race import RaceDialog
from madtracker.ui.setup.riders import RidersDialog
from madtracker.ui.widgets import (
    ID_ROLE,
    UNPRINTABLE_NOTE,
    ColumnSort,
    Form,
    GroupCombo,
    align_header,
    apply_style,
    date_edit,
    error_label,
    filling,
    friendly_error,
    input_item,
    note_unprintable,
    number_key,
    rider_name,
    run_dialog,
    selected_id,
    setup_table,
    show_message,
    text_key,
)

BIB, FIRST, LAST, GROUP, LICENSE, AGE = range(6)
ROSTER_HEADERS = ["Bib", "First", "Last", "Group", USAC_LICENSE, "Age"]


def racing_age(birth_year: int | None, event_date: str) -> str:
    """Year-end age, the one racing uses; blank when the birth year is unknown."""
    if birth_year is None or not event_date[:4].isdigit():
        return ""
    return str(int(event_date[:4]) - int(birth_year))


# The program table never shows fewer rows than this while the window
# has room; on a short window it gives way to the roster down to the
# short floor, and scrolls.
PROGRAM_MIN_ROWS = 6
PROGRAM_SHORT_ROWS = 3
# The roster is the list the scorer works down while typing bibs; the
# program gives way to its short rows before the roster goes below
# ROSTER_ROWS. Past that the roster gives way too, down to
# ROSTER_MIN_ROWS, before the screen scrolls: a floor of five would leave
# a 1366 by 768 screen at 100% one program row above the fold, and the
# program is the more used of the two on a race night.
ROSTER_ROWS = 5
ROSTER_MIN_ROWS = 3
PROGRAM_HEADERS = ["Name", "Format", "Group", "Ruleset", "Sprints or Places", "Field"]


def race_number(race) -> str:
    """The one number a race's format needs, as the program table shows it."""
    rules = race.rules or {}
    if FORMAT_ENGINE.get(race.format) == "sprint_points":
        count = rules.get("sprint_count")
        return (f"{count} sprint" if count == 1 else f"{count} sprints") if count else ""
    if FORMAT_ENGINE.get(race.format) == "win_and_out":
        places = rules.get("places")
        return f"{places} places" if places else ""
    return ""


MOVE_UP = "Move up"
MOVE_DOWN = "Move down"


def _arrow_button(icon: str, name: str) -> QPushButton:
    """A square button with a chevron, for moving a row; its tooltip names it."""
    b = QPushButton()
    b.setObjectName("square")
    b.setIcon(mdi(icon, 20))
    b.setIconSize(QSize(20, 20))
    b.setToolTip(name)
    b.setAccessibleName(name)
    return b


class _RosterDelegate(_TypingDelegate):
    """The roster's Bib and Group cells; a group is picked, never typed, in a cell.

    A cell that took typing would make a new group out of every slip
    ("Gruop A" a group of one), and nothing would show it. So the cell offers
    the event's groups and No group; a group is made in Groups (or comes
    from the import), and renamed or merged there.
    """

    def __init__(self, screen: "SetupScreen"):
        super().__init__(screen.roster, screen.roster_typed)
        self.screen = screen

    def createEditor(self, parent, option, index):
        if index.column() != GROUP or self.screen.store is None:
            return super().createEditor(parent, option, index)
        combo = QComboBox(parent)
        combo.addItem(NO_GROUP, "")
        for label in sorted(
            event_spellings(self.screen.store, self.screen.event_id), key=str.casefold
        ):
            combo.addItem(label, label)
        return combo

    def setEditorData(self, editor, index) -> None:
        if isinstance(editor, QComboBox):
            at = editor.findData(index.data() or "")
            editor.setCurrentIndex(max(at, 0))
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index) -> None:
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentData())
        else:
            super().setModelData(editor, model, index)

    def commit(self, editor: QWidget) -> None:
        # Whether this commit is refused is known only once it lands.
        self.screen._refused = False
        super().commit(editor)

    def sizeHint(self, option, index) -> QSize:
        # As wide as the picker needs for the longest group: sized to its
        # text alone, the column would show "Sem" of SemiProB behind the
        # open picker's arrow. The groups are read once per refill, never
        # per measure.
        hint = super().sizeHint(option, index)
        if index.column() != GROUP or not self.screen.group_texts:
            return hint
        fm = option.fontMetrics
        text = max(fm.horizontalAdvance(t) for t in self.screen.group_texts)
        arrow = round(fm.lineSpacing() * 2.2)
        return QSize(max(hint.width(), text + 3 * style.SM + 4 + arrow), hint.height())


class SetupScreen(QWidget):
    """Edit Event: Event, Roster, Program; Score, on the program pane's switch, leaves it."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store: Store | None = None
        self.event_id: int | None = None
        self._loading = False
        # Set when the roster refuses a typed value, so the scorer stays
        # on that cell instead of moving on (_RosterDelegate.commit).
        self._refused = False
        apply_style(self, APP_PT)

        # Event
        self.event_box = QGroupBox("Event")
        # Each section wears its own hue (style.STEP_HUES), so the three
        # steps of setting up read as steps.
        self.event_box.setObjectName("stepEvent")
        self.name = QLineEdit()
        self.name.editingFinished.connect(self._save_event)
        self.date = date_edit(QDate.currentDate())
        self.date.editingFinished.connect(self._save_event)
        # A date is twelve characters; the field is that wide, not the row.
        self.date.setFixedWidth(self.date.fontMetrics().horizontalAdvance("0000-00-00") * 2)
        # A click on its text opens the earlier series, as every typed-into
        # list does; Enter leaves the box, which saves the typed series.
        self.series = GroupCombo()
        self.series.setToolTip("Pick an earlier series or type a new one")
        self.series.lineEdit().setPlaceholderText("Winter Series")
        self.series.lineEdit().editingFinished.connect(self._save_event)
        self.series.activated.connect(lambda _i: self._save_event())
        # Date and Series share a row: a 768-pixel screen needs the line
        # for the roster.
        date_row = QHBoxLayout()
        date_row.addWidget(self.date)
        date_row.addSpacing(style.LG)
        date_row.addWidget(QLabel("Series"))
        date_row.addWidget(self.series, 1)
        form = Form(self.event_box)
        form.addRow("Name", self.name)
        form.addRow("Date", date_row)
        self.event_status = error_label()
        form.addRow("", self.event_status)
        # The empty message row would cost a line a 768-pixel screen needs.
        form.setRowVisible(self.event_status, False)
        self.event_form = form
        note_unprintable(self.name, self.event_status, self._event_message)
        note_unprintable(self.series.lineEdit(), self.event_status, self._event_message)

        # Roster
        self.roster_box = QGroupBox("Roster")
        self.roster_box.setObjectName("stepRoster")
        self.group_texts: list[str] = []
        self.roster = QTableWidget()
        setup_table(self.roster, ROSTER_HEADERS)
        align_header(self.roster, AGE, Qt.AlignmentFlag.AlignHCenter)
        header = self.roster.horizontalHeader()
        header.setStretchLastSection(False)
        for col in (FIRST, LAST):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        # Bib ascending is the default, the order the venue's list and
        # the cards use. The roster keeps whichever sort the scorer picks
        # through every refill, so typing bibs into a list sorted by name
        # leaves it sorted by name. Only the roster and the rider lists
        # sort: the program's order is the program, the result's is the
        # placing, and the import preview stays in file order because its
        # messages name rows by number.
        self.roster_sort = ColumnSort(
            self.roster,
            {
                BIB: lambda row: row[0].bib,
                FIRST: lambda row: first_key(row[1]),
                LAST: lambda row: name_key(row[1]),
                GROUP: lambda row: text_key(row[0].local_group or ""),
                LICENSE: lambda row: number_key(row[1].usac_license or ""),
                AGE: lambda row: number_key(row[2]),
            },
            self._roster_sorted,
            column=BIB,
        )
        # One row at a time: a group is picked in each rider's own cell.
        self.roster.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.roster.itemChanged.connect(self._roster_edited)
        # Gray is where the scorer types, and one click there starts
        # typing. A rider's own details are kept in the Riders window only.
        self.roster.cellClicked.connect(self._roster_clicked)
        typing = _RosterDelegate(self)
        self.roster.setItemDelegateForColumn(BIB, typing)
        self.roster.setItemDelegateForColumn(GROUP, typing)
        self.roster.itemSelectionChanged.connect(self._update_buttons)
        # The roster is a choice from the Riders window, not a place riders come
        # from: one button opens that choice, and an untick there is the
        # only way off (riders are made and imported in the Riders window).
        self.choose_riders_button = QPushButton("Choose Riders...")
        self.choose_riders_button.clicked.connect(self.choose_riders)
        self.groups_button = QPushButton("Edit Groups...")
        self.groups_button.setToolTip("Each group's riders and races; rename or merge a group")
        self.groups_button.clicked.connect(self.manage_groups)
        self.roster_count = QLabel("")
        self.roster_count.setObjectName("hint")
        self.roster_status = _refusal_line()
        roster_buttons = QHBoxLayout()
        for b in (
            self.choose_riders_button,
            self.groups_button,
        ):
            roster_buttons.addWidget(b)
        roster_buttons.addStretch(1)
        roster_buttons.addWidget(self.roster_count)
        roster_lay = QVBoxLayout(self.roster_box)
        roster_lay.addLayout(roster_buttons)
        roster_lay.addWidget(self.roster, 1)
        roster_lay.addWidget(self.roster_status)

        # Program
        self.program_box = QGroupBox("Program")
        self.program_box.setObjectName("stepProgram")
        self.program = QTableWidget()
        setup_table(self.program, PROGRAM_HEADERS)
        self.program.cellDoubleClicked.connect(lambda *_: self.edit_race())
        self.program.itemSelectionChanged.connect(self._update_buttons)
        # The section names what the buttons act on, so "Add...", not
        # "Add race...", and the moves are arrows: with "race" in each
        # word the row would not fit the 1366 px screen.
        self.add_race_button = QPushButton("Add...")
        self.add_race_button.clicked.connect(lambda: self.add_race())
        self.edit_race_button = QPushButton("Edit...")
        self.edit_race_button.clicked.connect(lambda: self.edit_race())
        self.duplicate_race_button = QPushButton("Duplicate...")
        self.duplicate_race_button.clicked.connect(lambda: self.duplicate_race())
        self.remove_race_button = QPushButton("Remove")
        self.remove_race_button.clicked.connect(lambda: self.remove_race())
        self.up_button = _arrow_button("chevron-up", MOVE_UP)
        self.up_button.clicked.connect(lambda: self.move_race(-1))
        self.down_button = _arrow_button("chevron-down", MOVE_DOWN)
        self.down_button.clicked.connect(lambda: self.move_race(1))
        self.program_status = _refusal_line()
        program_buttons = QHBoxLayout()
        for b in (
            self.add_race_button,
            self.edit_race_button,
            self.duplicate_race_button,
            self.remove_race_button,
            self.up_button,
            self.down_button,
        ):
            program_buttons.addWidget(b)
        program_buttons.addStretch(1)
        program_lay = QVBoxLayout(self.program_box)
        program_lay.addLayout(program_buttons)
        program_lay.addWidget(self.program, 1)
        program_lay.addWidget(self.program_status)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.addWidget(self.event_box)
        # The program is as tall as its races, six rows at the least while
        # the window has room; the roster, the long list, takes the rest
        # (_fit_program).
        lay.addWidget(self.roster_box, 1)
        lay.addWidget(self.program_box, 0)
        self._update_buttons()

    # ----- loading ------------------------------------------------------

    def load(self, store: Store, event_id: int) -> None:
        self.store = store
        self.event_id = event_id
        self.refresh()

    def refresh(self) -> None:
        if self.store is None or self.event_id is None:
            return
        self._loading = True
        try:
            event = self.store.event(self.event_id)
            self.name.setText(event.name)
            self.date.setDate(QDate.fromString(event.event_date, "yyyy-MM-dd"))
            names = sorted({m.series for m in self.store.events() if m.series}, key=str.casefold)
            self.series.clear()
            self.series.addItems(names)
            self.series.setCurrentText(event.series)
            self._fill_roster()
            self._fill_program()
        finally:
            self._loading = False

    def _fill_roster(self, select: int | None = None) -> None:
        with_riders = self.store.entries_with_riders(self.event_id)
        entries = [e for e, _r in with_riders]
        event_date = self.store.event(self.event_id).event_date
        wearers: dict[int, list[int]] = {}
        for e in entries:
            if e.bib is not None:
                wearers.setdefault(e.bib, []).append(e.rider_id)
        riders = {e.rider_id: r for e, r in with_riders}
        rows = self.roster_sort.sorted(
            [
                (e, riders[e.rider_id], racing_age(riders[e.rider_id].birth_year, event_date))
                for e in entries
            ]
        )
        # What the Group picker offers, for its column to fit the longest.
        self.group_texts = self._group_texts()
        with filling(self.roster):
            self.roster.setRowCount(len(rows))
            for row, (e, r, age_text) in enumerate(rows):
                bib = input_item("" if e.bib is None else str(e.bib), editable=True)
                bib.setData(ID_ROLE, e.rider_id)
                if e.bib is None:
                    # Still to be typed: the race this rider is in waits for it.
                    bib.setBackground(style.DANGER_TINT)
                else:
                    # Riders in different races may share a number; said, not refused.
                    others = [rid for rid in wearers[e.bib] if rid != e.rider_id]
                    if others:
                        bib.setToolTip(
                            f"Bib {e.bib} is also worn by {rider_name(self.store, others[0])}"
                        )
                self.roster.setItem(row, BIB, bib)
                self.roster.setItem(row, FIRST, input_item(r.first_name, editable=False))
                self.roster.setItem(row, LAST, input_item(r.last_name, editable=False))
                self.roster.setItem(row, GROUP, input_item(e.local_group or "", editable=True))
                self.roster.setItem(row, LICENSE, input_item(r.usac_license or "", editable=False))
                age = input_item(age_text, editable=False)
                age.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.roster.setItem(row, AGE, age)
                if e.rider_id == select:
                    self.roster.selectRow(row)
        self._count_roster(entries)
        self._update_buttons()

    def _count_roster(self, entries: list[RosterEntry]) -> None:
        missing = sum(1 for e in entries if e.bib is None)
        count = f"{len(entries)} riders"
        if missing:
            count += f", {missing} without a bib"
        # Groups are how a race's field is filled, and nothing else on the
        # screen says where they come from; the count names the gap.
        no_group = sum(1 for e in entries if not (e.local_group or "").strip())
        if entries and no_group == len(entries):
            count += ", no groups yet"
        elif no_group:
            count += f", {no_group} without a group"
        self.roster_count.setText(count)

    def _group_texts(self) -> list[str]:
        return [NO_GROUP, *sorted(event_spellings(self.store, self.event_id), key=str.casefold)]

    def _fill_program(self, select: int | None = None) -> None:
        races = self.store.races(self.event_id)
        group_of = {e.rider_id: e.local_group for e in self.store.entries(self.event_id)}
        known = [r.name for r in self.store.rulesets()]
        with filling(self.program):
            self.program.setRowCount(len(races))
            for row, race in enumerate(races):
                if race.format in TEAM_FORMATS:
                    size = f"{len(self.store.teams(race.race_id))} teams"
                else:
                    field = [e.rider_id for e in self.store.race_entries(race.race_id)]
                    size = f"{len(field)} riders" + group_rules.out_of_group(
                        race.group_label, [group_of.get(rid) for rid in field]
                    )
                cells = [
                    race.name,
                    rulesets.race_format_name(race),
                    race.group_label,
                    rulesets.ruleset_shown(race.rules_preset, known) if race.rules_preset else "",
                    race_number(race),
                    size,
                ]
                for col, text in enumerate(cells):
                    item = input_item(text, editable=False)
                    if col == 0:
                        item.setData(ID_ROLE, race.race_id)
                    self.program.setItem(row, col, item)
                if race.race_id == select:
                    self.program.selectRow(row)
        # The ruleset shows as a column only when it tells races apart: on
        # most nights every race has the venue's one ruleset, and the
        # column would cost a 1366-pixel screen a sideways scroll.
        self.program.setColumnHidden(
            PROGRAM_HEADERS.index("Ruleset"), len({r.rules_preset for r in races}) <= 1
        )
        self._fit_program()
        self._update_buttons()

    def _update_buttons(self) -> None:
        """A button that would only be refused is off, with the refusal as its tooltip."""
        race_reasons = self._race_refusals(selected_id(self.program))
        for key, button, name in (
            ("edit", self.edit_race_button, ""),
            ("duplicate", self.duplicate_race_button, ""),
            ("remove", self.remove_race_button, ""),
            # An arrow has no word on it, so its tooltip names it.
            ("up", self.up_button, MOVE_UP),
            ("down", self.down_button, MOVE_DOWN),
        ):
            button.setEnabled(not race_reasons[key])
            button.setToolTip(race_reasons[key] or name)

    def _race_refusals(self, race_id: int | None) -> dict[str, str]:
        """Why Edit, Duplicate, Remove, and the up and down arrows would be refused for this race."""
        return program.race_refusals(self.store, self.event_id, race_id)

    @staticmethod
    def table_height(t: QTableWidget, rows: int) -> int:
        header = t.horizontalHeader().sizeHint().height()
        return header + rows * t.verticalHeader().defaultSectionSize() + 2 * t.frameWidth() + 2

    def program_height(self, rows: int) -> int:
        return self.table_height(self.program, rows)

    def _fit_program(self) -> None:
        self.roster.setMinimumHeight(self.table_height(self.roster, ROSTER_MIN_ROWS))
        # In the window the screen sits in a scroll area and is never
        # shorter than its minimum, so the room is the view's height.
        view = self.parentWidget()
        height = view.height() if view is not None else self.height()
        rows = max(PROGRAM_MIN_ROWS, self.program.rowCount())
        floor = self.program_height(PROGRAM_MIN_ROWS)
        # A long program gives way to the roster at half the screen.
        want = min(self.program_height(rows), max(floor, height // 2))
        # What the program can have with the roster at ROSTER_ROWS: the
        # program's own height is fixed, so the rest of the minimum is
        # everything else on the screen.
        others = self.layout().minimumSize().height() - self.program.height()
        others += self.table_height(self.roster, ROSTER_ROWS) - self.roster.minimumHeight()
        fit = height - others
        if fit < want:
            # Whole rows only; the part row it would cut goes to the roster.
            row = self.program.verticalHeader().defaultSectionSize()
            fit = self.program_height(max(0, fit - self.program_height(0)) // row)
        short = self.program_height(min(PROGRAM_SHORT_ROWS, rows))
        self.program.setFixedHeight(max(short, min(want, fit)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_program()

    # ----- event --------------------------------------------------------

    def _save_event(self) -> None:
        if self._loading or self.store is None:
            return
        name = _typed(self.name)
        series = _typed(self.series.lineEdit())
        # The field shows what the file holds: the tidied value once
        # saved, and the name on file when the typed one is refused.
        if not name:
            self._event_message("The event needs a name.")
            self.name.setText(self.store.event(self.event_id).name)
            return
        try:
            self.store.update_event(
                self.event_id,
                name=name,
                event_date=self.date.date().toString("yyyy-MM-dd"),
                series=series,
            )
        except (StoreError, ValueError) as exc:
            self._event_message(friendly_error(self.store, exc))
            self.name.setText(self.store.event(self.event_id).name)
            return
        self.name.setText(name)
        self.series.setCurrentText(series)
        self._event_message("")
        self.changed.emit()

    def _event_message(self, text: str) -> None:
        show_message(self.event_status, text)
        self.event_form.setRowVisible(self.event_status, bool(text))

    # ----- roster -------------------------------------------------------

    def row_of(self, rider_id: int) -> int:
        for row in range(self.roster.rowCount()):
            if self.roster.item(row, BIB).data(ID_ROLE) == rider_id:
                return row
        return -1

    def _roster_clicked(self, row: int, col: int) -> None:
        item = self.roster.item(row, col)
        if item is not None and item.flags() & Qt.ItemFlag.ItemIsEditable:
            self.roster.editItem(item)

    def _roster_edited(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() not in (BIB, GROUP):
            return
        rider_id = self.roster.item(item.row(), BIB).data(ID_ROLE)
        text = item.text().strip()
        # A refusal answers the edit it came from; left standing under the
        # next edit it would read as that one's.
        _refuse(self.roster_status, "")
        try:
            if item.column() == BIB:
                bib = typed_bib(text)
                # The race field is where a bib must be unique (design section 6).
                problem = roster_bib_refusal(self.store, self.event_id, rider_id, bib)
                if problem:
                    raise ValueError(problem)
                saved_bib = self.store.change_bib(self.event_id, rider_id, bib).bib
                saved = "" if saved_bib is None else str(saved_bib)
            else:
                text = canonical_group(self.store, self.event_id, text, exclude_rider_id=rider_id)
                old = self.store.entry(self.event_id, rider_id).local_group
                # One write with the races it moves the rider between.
                with self.store.transaction():
                    saved = (
                        self.store.set_entry_group(
                            self.event_id, rider_id, text or None
                        ).local_group
                        or ""
                    )
                    # The rider's unscored races follow the group (design section 6).
                    group_rules.follow_group(self.store, self.event_id, [rider_id], old)
        except (StoreError, ValueError, OverflowError) as exc:
            self._refused = True
            _refuse(self.roster_status, friendly_error(self.store, exc))
            entry = self.store.entry(self.event_id, rider_id)
            old_bib = "" if entry.bib is None else str(entry.bib)
            self._set_cell(item, old_bib if item.column() == BIB else entry.local_group or "")
            return
        self._set_cell(item, saved)
        # A group prints on the sheets; one they cannot print is said, not refused.
        unprintable = item.column() == GROUP and not prints(saved)
        _refuse(self.roster_status, UNPRINTABLE_NOTE if unprintable else "")
        self.changed.emit()
        if item.column() == BIB:
            # The table may list in bib order, and the tint, tooltips and
            # count follow the bib; rebuilding it inside the item's
            # own signal would delete the item, so the re-sort waits a turn.
            QTimer.singleShot(0, self, lambda: self._resort(rider_id))
        else:
            # The count names the riders without a group, so it is refreshed as
            # soon as one is typed.
            self._count_roster(self.store.entries(self.event_id))

    def roster_typed(self, row: int, col: int, key: int) -> None:
        """Open the next cell to type in once a Bib or Group is committed.

        Enter in a Bib goes to the next rider still without one, in the
        order shown, then wraps to the first above: bibs are typed off
        the venue's list, and riders who have one need nothing. Tab
        crosses the row, Bib to Group to the next rider's Bib, and
        Shift+Tab goes back. A refused value keeps the scorer on its
        cell. A bib edit rebuilds the table on the next turn
        (_roster_edited), so the target is a rider, found again after
        the rebuild, never a row.
        """
        rows = self.roster.rowCount()
        if not 0 <= row < rows:
            return

        def rider(r: int) -> int | None:
            return self.roster.item(r, BIB).data(ID_ROLE) if 0 <= r < rows else None

        if self._refused:
            rider_id, target = rider(row), col
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if col == BIB:
                order = [*range(row + 1, rows), *range(row)]
                empty = [r for r in order if not self.roster.item(r, BIB).text().strip()]
                rider_id, target = (rider(empty[0]) if empty else None), BIB
            else:
                rider_id, target = rider(row + 1), GROUP
        elif key == Qt.Key.Key_Tab:
            rider_id, target = (rider(row), GROUP) if col == BIB else (rider(row + 1), BIB)
        else:
            rider_id, target = (rider(row), BIB) if col == GROUP else (rider(row - 1), GROUP)
        if rider_id is not None:
            # Queued behind the re-sort a bib edit queues, so the row is found after it.
            QTimer.singleShot(0, self, lambda: self.edit_rider_cell(rider_id, target))

    def edit_rider_cell(self, rider_id: int, col: int) -> bool:
        row = self.row_of(rider_id)
        if row < 0:
            return False
        self.roster.setCurrentCell(row, col)
        self.roster.editItem(self.roster.item(row, col))
        return True

    def _set_cell(self, item: QTableWidgetItem, text: str) -> None:
        self._loading = True
        try:
            item.setText(text)
        finally:
            self._loading = False

    def _resort(self, rider_id: int | None) -> None:
        self._loading = True
        try:
            self._fill_roster(select=rider_id)
        finally:
            self._loading = False

    def _roster_sorted(self) -> None:
        if self.store is not None and self.event_id is not None:
            self._resort(selected_id(self.roster))

    def groups_dialog(self) -> GroupsDialog:
        return GroupsDialog(self.store, self.event_id, self)

    def manage_groups(self, dialog: GroupsDialog | None = None) -> None:
        """The event's groups; a rename shows on the roster and the program at once."""
        dialog = dialog or self.groups_dialog()
        run_dialog(dialog)
        if dialog.changed:
            self.refresh()
            self.changed.emit()

    def choose_riders(self) -> None:
        picker = RidersDialog(self.store, self.event_id, self)
        run_dialog(picker)
        self.riders_chosen(picker)

    def riders_chosen(self, picker: RidersDialog) -> None:
        """Show the roster as Choose Riders left it.

        The dialog writes each tick as it goes and stays open, so Close
        is the only way out; the screen is refilled either way.
        """
        # The roster once, selecting the last rider added, rather than a
        # second fill only for the selection.
        self._loading = True
        try:
            self._fill_roster(select=picker.added[-1] if picker.added else None)
            self._fill_program()
        finally:
            self._loading = False
        if not picker.added and not picker.removed:
            return
        _refuse(self.roster_status, "")
        self.changed.emit()

    # ----- program ------------------------------------------------------

    def _selected_race(self) -> int | None:
        race_id = selected_id(self.program)
        if race_id is None:
            _refuse(self.program_status, "Select a race first.")
        return race_id

    def race_dialog(self, race_id: int | None, copy_of: int | None = None) -> RaceDialog:
        return RaceDialog(self.store, self.event_id, race_id, self, copy_of=copy_of)

    def add_race(self, dialog: RaceDialog | None = None) -> int | None:
        dialog = dialog or self.race_dialog(None)
        if run_dialog(dialog) != QDialog.DialogCode.Accepted:
            return None
        self._program_refill(select=dialog.race_id)
        self.changed.emit()
        return dialog.race_id

    def _program_refill(self, select: int | None = None) -> None:
        """The program after a race was added, edited or removed; the roster only if it must.

        A race changes no roster cell. Only a new group spelling from the
        race's Group box changes what the roster's Group picker lists,
        and with it that column's width. Refilling the whole screen here
        would measure the 360-cell roster twice per Save.
        """
        self._loading = True
        try:
            if self._group_texts() != self.group_texts:
                self._fill_roster(select=selected_id(self.roster))
            self._fill_program(select=select)
        finally:
            self._loading = False

    def duplicate_race(
        self, race_id: int | None = None, dialog: RaceDialog | None = None
    ) -> int | None:
        """A new race filled from the selected one, saved right after it; nothing until Save."""
        race_id = race_id if race_id is not None else self._selected_race()
        if race_id is None:
            return None
        dialog = dialog or self.race_dialog(None, copy_of=race_id)
        if run_dialog(dialog) != QDialog.DialogCode.Accepted:
            return None
        try:
            program.place_after(self.store, self.event_id, dialog.race_id, race_id)
        except StoreError as exc:
            # The race is saved; only its place failed, so it stays last.
            _refuse(self.program_status, friendly_error(self.store, exc))
        self._program_refill(select=dialog.race_id)
        self.changed.emit()
        return dialog.race_id

    def edit_race(self, race_id: int | None = None) -> bool:
        race_id = race_id if race_id is not None else self._selected_race()
        if race_id is None:
            return False
        if run_dialog(self.race_dialog(race_id)) != QDialog.DialogCode.Accepted:
            return False
        self._program_refill(select=race_id)
        self.changed.emit()
        return True

    def remove_race(self, race_id: int | None = None, confirm: bool = True) -> bool:
        race_id = race_id if race_id is not None else self._selected_race()
        if race_id is None:
            return False
        race = self.store.race(race_id)
        refusal = self._race_refusals(race_id)["remove"]
        if refusal:
            _refuse(self.program_status, refusal)
            return False
        if confirm and not icons.ask(
            self, "Remove Race", f"Remove {race.name} from the program?", verb="Remove"
        ):
            return False
        try:
            self.store.delete_race(race_id)
        except StoreError as exc:
            _refuse(self.program_status, friendly_error(self.store, exc))
            return False
        self._program_refill()
        _refuse(self.program_status, "")
        self.changed.emit()
        return True

    def move_race(self, step: int, race_id: int | None = None) -> bool:
        race_id = race_id if race_id is not None else self._selected_race()
        if race_id is None:
            return False
        try:
            refusal = program.move_race(self.store, self.event_id, race_id, step)
        except StoreError as exc:
            refusal = friendly_error(self.store, exc)
        if refusal:
            if refusal != program.NO_RACE:
                _refuse(self.program_status, refusal)
            return False
        self._fill_program(select=race_id)
        self.changed.emit()
        return True
