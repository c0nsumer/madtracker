"""The BikeReg import: the preview of every row and the review of a conflict."""

from collections import Counter

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from madtracker.control.groups import event_spellings, group_key, same_group
from madtracker.control.riders import RIDER_VALUES, UCI_ID, USAC_LICENSE, MergeValue
from madtracker.control.roster import typed_bib
from madtracker.dates import show_date
from madtracker.export.glyphs import prints
from madtracker.importers.bikereg import (
    STATUS_TEXT,
    ImportPlan,
    ImportResult,
    apply_import,
    choose,
    plan_import,
    replan,
)
from madtracker.inputs import clean_line
from madtracker.store import Store, StoreError
from madtracker.ui import icons, style
from madtracker.ui.setup._shared import NO_GROUP, ValueLines, _TypingDelegate
from madtracker.ui.widgets import (
    RowToggleDelegate,
    apply_style,
    button_row,
    error_label,
    filling,
    fit_popup,
    fit_to_screen,
    friendly_error,
    input_item,
    rider_name,
    run_dialog,
    setup_table,
    show_message,
    unprintable_words,
)

USE, ACTION, P_FIRST, P_LAST, P_LICENSE, UCI, P_BIB, P_GROUP, DETAILS = range(9)
PREVIEW_HEADERS = [
    "Import",
    "Status",
    "First",
    "Last",
    USAC_LICENSE,
    UCI_ID,
    "Bib",
    "Group",
    "Details",
]
# The characters a Status choice is sized to: "Conflict" with room to spare.
STATUS_CHARS = 10
# How the count line names each status, singular and plural.
STATUS_COUNT = {
    "new": ("new", "new"),
    "check": ("to check", "to check"),
    "on_file": ("on file", "on file"),
    "update": ("to update", "to update"),
    "review": ("to review", "to review"),
    "conflict": ("conflict", "conflicts"),
}


class _WrapDelegate(QStyledItemDelegate):
    """Measures a wrapped cell at the width it is painted at.

    Qt's own measure wraps at the column width, but the style sheet's
    cell padding paints the text narrower, so a row sized by it is a
    line short and the last line is elided.
    """

    def sizeHint(self, option, index) -> QSize:
        hint = super().sizeHint(option, index)
        view = self.parent()
        # The cell's padding and the delegate's margin: SM a side.
        width = view.columnWidth(index.column()) - 2 * style.SM
        text = index.data() or ""
        flags = Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft
        lines = option.fontMetrics.boundingRect(QRect(0, 0, max(width, 1), 1 << 20), flags, text)
        return QSize(hint.width(), max(hint.height(), lines.height() + 2 * style.XS))


class _PreviewDelegate(_TypingDelegate):
    """The import preview's Bib and Group cells; the Group cell is the roster's picker.

    As on the roster, a typed cell would make a new group out of every slip.
    The list is the event's groups and the file's, No group first. It
    still takes typing, since a group the file does not give may be
    tonight's; what is typed takes an existing group's spelling when it
    is one, case and spaces aside.
    """

    def __init__(self, preview: "ImportPreview"):
        super().__init__(preview.table, preview._typed)
        self.preview = preview
        # The widest group text, by the list and font it was measured for.
        self._widest: tuple[list[str], str, int] | None = None

    def createEditor(self, parent, option, index):
        if index.column() != P_GROUP:
            return super().createEditor(parent, option, index)
        combo = QComboBox(parent)
        combo.setEditable(True)
        # A typed name goes into the cell, never into the list.
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.addItem(NO_GROUP, "")
        for label in self.preview.group_choices():
            combo.addItem(label, label)
        # The view filters only the editor it knows, the combo; Tab and
        # Enter land on the line edit inside, so it is filtered too.
        combo.lineEdit().installEventFilter(self)
        return combo

    def setEditorData(self, editor, index) -> None:
        if isinstance(editor, QComboBox):
            text = index.data() or ""
            at = editor.findData(text)
            if at >= 0:
                editor.setCurrentIndex(at)
            else:
                editor.setEditText(text)
            editor.lineEdit().selectAll()
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index) -> None:
        if isinstance(editor, QComboBox):
            model.setData(index, self.preview.group_typed(editor.currentText()))
        else:
            super().setModelData(editor, model, index)

    def sizeHint(self, option, index) -> QSize:
        # As wide as the picker: sized to its text alone, the column would
        # clip the open picker's text behind the arrow.
        hint = super().sizeHint(option, index)
        if index.column() != P_GROUP:
            return hint
        fm = option.fontMetrics
        # Every row's Group cell asks the same question: measuring each group
        # text once per cell would cost a sixth of opening a 300-row preview.
        texts, font = self.preview.group_texts, option.font.key()
        if self._widest is None or self._widest[0] is not texts or self._widest[1] != font:
            self._widest = (texts, font, max(fm.horizontalAdvance(t) for t in texts))
        text = self._widest[2]
        # The style sheet's field padding and focus border, and its arrow
        # box, which is a control height wide.
        arrow = round(fm.lineSpacing() * 2.2)
        return QSize(max(hint.width(), text + 2 * style.SM + 4 + arrow), hint.height())


class ImportPreview(QDialog):
    """The plan, one row per registration, before anything is written.

    The program never assigns a bib: a row's Bib cell is empty unless
    the file had one. An empty one is tinted as still to be filled, and
    the rider is imported without a bib if it stays empty; the numbers
    often come after registration closes. A number someone else on the
    roster or another row already has is said in Details, for
    information only: riders in different races may share one.

    An unticked row's Bib and Group are read-only, since Import would
    drop what was typed there. A rider already on tonight's roster is the
    exception: re-importing the same file to type the bibs that came
    after registration is a real use, so that row's cells stay editable
    while its tick stays off, and a bib or group that differs from the
    roster's is applied regardless of the tick.

    The import belongs to the Riders window, the one door riders come in by.
    Registration is also who is racing, so the preview names an event
    whose roster the riders go on, with their bibs and groups; "No
    event" keeps the riders only, and the Bib and Group columns go.
    Changing the event plans the file again against that roster.
    """

    def __init__(
        self,
        store: Store,
        event_id: int | None,
        plans: list[ImportPlan],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.store = store
        self.event_id = event_id
        self.plans = plans
        self.result: ImportResult | None = None
        # The scorer's picks in each row's review, by row: kept through a
        # Cancel, so going on again asks nothing twice.
        self.picks: dict[int, dict[int, int]] = {}
        self._shown = False
        self.setWindowTitle("Import from BikeReg")
        apply_style(self)
        self.event = QComboBox()
        for m in store.events():
            self.event.addItem(f"{m.name} ({show_date(m.event_date)})", m.event_id)
        self.event.addItem("No Event", None)
        self.event.setCurrentIndex(self.event.findData(event_id))
        self.event.activated.connect(lambda _i: self.set_event(self.event.currentData()))
        event_row = QHBoxLayout()
        event_row.addWidget(QLabel("Put on the roster of"))
        event_row.addWidget(self.event)
        event_row.addStretch(1)
        # The whole file at once, as Choose Riders offers; Select New is
        # the re-import of a file that grew, where only the new rows matter.
        self.select_all = QPushButton("Select All")
        self.select_all.clicked.connect(lambda: self.tick_rows("all"))
        self.select_new = QPushButton("Select New")
        self.select_new.clicked.connect(lambda: self.tick_rows("new"))
        self.select_none = QPushButton("Select None")
        self.select_none.clicked.connect(lambda: self.tick_rows("none"))
        # Enter in the table passes up to the dialog, where an auto-default
        # button would take it and redo the ticks.
        for b in (self.select_all, self.select_new, self.select_none):
            b.setAutoDefault(False)
            event_row.addWidget(b)
        self._reset_for_event()
        self.intro = QLabel()
        self.intro.setWordWrap(True)
        self._count()
        self.table = QTableWidget()
        setup_table(self.table, PREVIEW_HEADERS)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        # Details is what the import will change, the point of the preview:
        # it takes the room the other columns leave and wraps instead of
        # being elided. setup_table sizes the other columns to their
        # contents, and the Action combo's own size hint is its longest
        # label. Details is sized here rather than by stretching, because a
        # stretched last section shrinks to nothing on a narrow screen;
        # this one keeps a readable width and the table scrolls sideways.
        self.table.setWordWrap(True)
        self.table.setItemDelegateForColumn(DETAILS, _WrapDelegate(self.table))
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(DETAILS, QHeaderView.ResizeMode.Fixed)
        header.sectionResized.connect(self._column_resized)
        self.table.viewport().installEventFilter(self)
        self._fit_pending = False
        # Rows filled but not yet measured, left for the pending fit.
        self._rows_stale = False
        typing = _PreviewDelegate(self)
        self.table.setItemDelegateForColumn(P_BIB, typing)
        self.table.setItemDelegateForColumn(P_GROUP, typing)
        # The whole Import cell is the tick, not only the box inside it.
        self.table.setItemDelegateForColumn(USE, RowToggleDelegate(self.table))
        self.table.cellClicked.connect(self._cell_clicked)
        self.error = error_label()
        buttons, made = button_row("Import", self.apply, self.reject)
        self.apply_button = made["primary"]
        # Import is a click, never the Enter that ends a typed bib.
        self.apply_button.setDefault(False)
        self.apply_button.setAutoDefault(False)
        lay = QVBoxLayout(self)
        lay.addLayout(event_row)
        lay.addWidget(self.intro)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.error)
        lay.addLayout(buttons)
        self._show_roster_columns()
        with filling(self.table):
            self._fill()
        self.table.itemChanged.connect(self._check)
        self._check(measure=False)
        self._size_to()
        self.table.resizeRowsToContents()

    def _reset_for_event(self) -> None:
        """What the preview checks a row against: the chosen event's roster, or nothing."""
        self._details: list[list[str]] = []
        # What the plan put in each row's Bib and Group, so Escape knows
        # whether anything typed would be lost.
        self._proposed: list[tuple[str, str]] = []
        entries = self.store.entries(self.event_id) if self.event_id is not None else []
        self._entries = {e.rider_id: e for e in entries}
        self._holders: dict[int, list[int]] = {}
        for e in entries:
            if e.bib is not None:
                self._holders.setdefault(e.bib, []).append(e.rider_id)

    def _show_roster_columns(self) -> None:
        for col in (P_BIB, P_GROUP):
            self.table.setColumnHidden(col, self.event_id is None)

    def set_event(self, event_id: int | None) -> bool:
        """Plan the file again against another event's roster, or none."""
        if event_id == self.event_id:
            return False
        if self.typed_anything() and not icons.ask(
            self, "Import from BikeReg", "Discard the bibs you typed?", verb="Discard"
        ):
            self.event.setCurrentIndex(self.event.findData(self.event_id))
            return False
        self.event_id = event_id
        self.event.setCurrentIndex(self.event.findData(event_id))
        self.plans = plan_import(self.store, event_id, [p.row for p in self.plans])
        self.picks = {}
        self._reset_for_event()
        self._show_roster_columns()
        # Filled as at the start, before _check may read a row.
        self.table.blockSignals(True)
        try:
            with filling(self.table):
                self._fill()
        finally:
            self.table.blockSignals(False)
        self._count()
        self._check(measure=False)
        if self._fit_pending:
            # Showing or hiding the roster columns queues a Details fit,
            # which measures every row; measuring them here as well would be a
            # second pass over the whole file.
            self._rows_stale = True
        else:
            self.table.resizeRowsToContents()
        return True

    def _count(self) -> None:
        counts = Counter(p.status for p in self.plans)
        parts = [
            f"{counts[key]} {words[counts[key] != 1]}"
            for key, words in STATUS_COUNT.items()
            if counts[key]
        ]
        total = len(self.plans)
        self.intro.setText(f"{total} registration{'' if total == 1 else 's'}: {', '.join(parts)}.")

    def _size_to(self) -> None:
        """Wide enough that most Details fit on a line, never off the screen."""
        fit_to_screen(self, 1200, 700)

    def eventFilter(self, watched, event) -> bool:
        # Only a preview on screen fits itself; a closed one left alive
        # has no layout to keep.
        if (
            watched is self.table.viewport()
            and event.type() == QEvent.Type.Resize
            and self.isVisible()
        ):
            self._fit_details_later()
        return super().eventFilter(watched, event)

    def _column_resized(self, col: int, _old: int, _new: int) -> None:
        if col != DETAILS:
            self._fit_details_later()

    def _fit_details_later(self) -> None:
        # Widths settle over several events (show, a scroll bar coming and
        # going, each column measuring itself); one pass after they do.
        if not self._fit_pending:
            self._fit_pending = True
            # Bound to the dialog: a preview deleted before the turn would
            # otherwise be fitted after it is gone.
            QTimer.singleShot(0, self, self._fit_details)

    def _fit_details(self) -> None:
        self._fit_pending = False
        stale, self._rows_stale = self._rows_stale, False
        others = sum(self.table.columnWidth(c) for c in range(DETAILS))
        # 22 characters wrap a long note onto a second line rather than
        # pushing the table sideways at 11 pt on a 1366x768 screen at 125%.
        floor = self.table.fontMetrics().averageCharWidth() * 22
        # Measured from the table's whole inside, less the room the style
        # keeps for a scroll bar, so whether a bar shows never moves it.
        # The width sets how many lines each row wraps to, which decides
        # whether the bar shows, which would change the viewport's width and
        # refit the column: on Windows that never settles and the dialog
        # hangs. Neither the viewport nor the bar's size hint is
        # used, since at 150% scaling the bar's real width and its hint
        # differ by a pixel, enough to keep the loop going.
        extent = self.table.style().pixelMetric(
            QStyle.PixelMetric.PM_ScrollBarExtent, None, self.table
        )
        room = self.table.maximumViewportSize().width() - extent
        width = max(floor, room - others)
        if width != self.table.columnWidth(DETAILS):
            self.table.setColumnWidth(DETAILS, width)
            # A wider or narrower Details column changes every row's lines.
            self.table.resizeRowsToContents()
            # The bib open for typing (opened as the preview appears) moves
            # with its cell; left where it was, it would sit over another row's
            # Import box as an empty field.
            self.table.updateEditorGeometries()
        elif stale:
            self.table.resizeRowsToContents()

    def _fill(self) -> None:
        # The Group picker's choices, kept for the column to fit the longest.
        self.group_texts = [NO_GROUP, *self.group_choices()]
        self.table.setRowCount(len(self.plans))
        for row, plan in enumerate(self.plans):
            use = QTableWidgetItem("")
            use.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            # Unticked when applying would change nothing, or when an id
            # clashes and only the scorer can say which record is right. A
            # file imported again for its bibs changes the roster, so a row
            # whose bib or group is new stays ticked.
            unchanged = plan.action == "match" and not self._roster_changes(plan)
            unchanged = unchanged and plan.already_entered
            # A later row of a rider whose registrations disagree waits
            # for the scorer to say which one is tonight's, and a New? row
            # waits to be told whether it is the rider of that name.
            off = unchanged or bool(plan.conflict) or plan.start_unticked
            use.setCheckState(Qt.CheckState.Unchecked if off else Qt.CheckState.Checked)
            self.table.setItem(row, USE, use)
            self._details.append(self._plan_details(plan))
            r = plan.row
            cells = {
                ACTION: (STATUS_TEXT[plan.status], False),
                P_FIRST: (r.first, False),
                P_LAST: (r.last, False),
                P_LICENSE: (r.usac_license or r.license_text or "", False),
                UCI: (r.uci_id or "", False),
                P_BIB: ("" if plan.bib is None else str(plan.bib), True),
                P_GROUP: (plan.group or "", True),
                DETAILS: ("; ".join(self._details[row]), False),
            }
            for col, (text, editable) in cells.items():
                self.table.setItem(row, col, input_item(text, editable))
            self._proposed.append(self._typed_in(row))
            details = self.table.item(row, DETAILS)
            details.setToolTip(details.text())
            self._action_choice(row)

    def _roster_changes(self, plan: ImportPlan) -> list[str]:
        """What the row would change on the roster entry the rider already has."""
        if not plan.already_entered or plan.rider_id is None or self.event_id is None:
            return []
        # The roster read once per event in _reset_for_event, not once per
        # row: a re-imported file is all roster riders, and each row would
        # ask twice.
        entry = self._entries.get(plan.rider_id)
        if entry is None:
            return []
        out = []
        if plan.bib is not None and plan.bib != entry.bib:
            old = "none" if entry.bib is None else str(entry.bib)
            out.append(f"bib: {old} -> {plan.bib}")
        if plan.group and not same_group(plan.group, entry.local_group):
            out.append(f"group: {entry.local_group or 'none'} -> {plan.group}")
        return out

    def _plan_details(self, plan: ImportPlan) -> list[str]:
        """The row's news: a match by USAC License is the usual case and says nothing."""
        details = []
        if plan.conflict:
            details.append(plan.conflict)
        if plan.matched_by == "chosen":
            details.append("matched by your choice")
        elif plan.matched_by == "uci":
            details.append(f"matched by {UCI_ID}")
        elif plan.matched_by == "name":
            details.append("matched by name")
        details += plan.differences
        roster = self._roster_changes(plan)
        if plan.already_entered and plan.rider_id is not None and not (plan.changes or roster):
            # Why the row starts unticked: there is nothing to bring in.
            details.append("already on this roster")
        details += roster
        if plan.note:
            details.append(plan.note)
        # Imported all the same: the name is the rider's own.
        for what, text in (("name", plan.row.name), ("group", plan.group or "")):
            if not prints(text):
                details.append(unprintable_words(f"the {what}"))
        return details

    def _action_choice(self, row: int) -> None:
        """A row that may be a rider on file gets a choice in its Status cell.

        New stays the default: merging two records is the scorer's
        call, made where the names sit side by side.
        """
        plan = self.plans[row]
        if not plan.candidates:
            return
        combo = QComboBox()
        # As wide as a status word, not as the longest candidate: sized by
        # its items, the column would take the room Details needs and the
        # table would scroll sideways. The list opens as wide as its items, and the
        # tip carries the whole of the one showing.
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(STATUS_CHARS)
        combo.addItem(STATUS_TEXT["new"], None)
        for c in plan.candidates:
            combo.addItem(c.label, c.rider.rider_id)
        combo.setCurrentIndex(max(0, combo.findData(plan.rider_id)))
        combo.currentIndexChanged.connect(
            lambda _i, r=row, c=combo: self.choose_rider(r, c.currentData())
        )
        self.table.setCellWidget(row, ACTION, combo)
        # In the dialog first, so the rows are measured in its face.
        fit_popup(combo)
        self._label_choice(row)

    def _label_choice(self, row: int) -> None:
        """The row's status on the choice that covers its Status cell.

        The list sits over the status, so the item showing carries it:
        "Conflict", "New?" or "New" for no rider, "Review: Same as Ann Alpha" for
        the rider chosen. The other items stay plain choices.
        """
        combo, plan = self.action_choice(row), self.plans[row]
        if combo is None:
            return
        status = STATUS_TEXT[plan.status]
        combo.setItemText(0, status if plan.rider_id is None else STATUS_TEXT["new"])
        for i, c in enumerate(plan.candidates, 1):
            mine = c.rider.rider_id == plan.rider_id
            combo.setItemText(i, f"{status}: {c.label}" if mine else c.label)
        combo.setToolTip(combo.currentText())

    def action_choice(self, row: int) -> QComboBox | None:
        widget = self.table.cellWidget(row, ACTION)
        return widget if isinstance(widget, QComboBox) else None

    def choose_rider(self, row: int, rider_id: int | None) -> None:
        """The scorer's answer to "is this a rider on file?" for one row."""
        before = [bool(p.conflict) or p.start_unticked for p in self.plans]
        was = [p.changes for p in self.plans]
        typed = self._typed_in(row)
        current = [
            replan(p, bib=self._bib_or_none(r), group=self.table.item(r, P_GROUP).text() or None)
            for r, p in enumerate(self.plans)
        ]
        self.plans = choose(self.store, self.event_id, current, row, rider_id)
        for r, plan in enumerate(self.plans):
            if r == row or plan.changes != was[r]:
                # Picks made against other values answer nothing now.
                self.picks.pop(r, None)
        self.table.blockSignals(True)
        try:
            with filling(self.table):
                for r, plan in enumerate(self.plans):
                    self._details[r] = self._plan_details(plan)
                    self.table.item(r, ACTION).setText(STATUS_TEXT[plan.status])
                    held = bool(plan.conflict) or plan.start_unticked
                    if held and (r == row or not before[r]):
                        self.set_checked(r, False)
                    elif r == row:
                        self.set_checked(r, True)
                    combo = self.action_choice(r)
                    if combo is None and plan.candidates:
                        self._action_choice(r)
                    elif combo is not None and combo.count() != len(plan.candidates) + 1:
                        # A choice can bring a conflict, which offers its other rider.
                        self._action_choice(r)
                    else:
                        self._label_choice(r)
                plan = self.plans[row]
                self.table.item(row, P_BIB).setText("" if plan.bib is None else str(plan.bib))
                self.table.item(row, P_GROUP).setText(plan.group or "")
                if self._typed_in(row) != typed:
                    # The chosen rider's bib and group tonight: the program
                    # proposed them, the scorer did not type them.
                    self._proposed[row] = self._typed_in(row)
        finally:
            self.table.blockSignals(False)
        self._count()
        self._check()

    def group_choices(self) -> list[str]:
        """The Group cell's list: the event's groups and the file's, one spelling each."""
        spellings = event_spellings(self.store, self.event_id) if self.event_id is not None else []
        by_key = {group_key(g): g for g in spellings}
        for plan in self.plans:
            for group in (plan.group, plan.row.local_group):
                tidy = " ".join((group or "").split())
                if tidy:
                    by_key.setdefault(group_key(tidy), tidy)
        return sorted(by_key.values(), key=str.casefold)

    def group_typed(self, text: str) -> str:
        """What a Group cell holds for ``text``: a listed group's spelling, or the text, or none."""
        tidy = clean_line(text)
        if not tidy or group_key(tidy) == group_key(NO_GROUP):
            return ""
        return next((g for g in self.group_choices() if group_key(g) == group_key(tidy)), tidy)

    def _typed_in(self, row: int) -> tuple[str, str]:
        return (
            self.table.item(row, P_BIB).text().strip(),
            self.table.item(row, P_GROUP).text().strip(),
        )

    def _editable(self, row: int) -> bool:
        ticked = self.table.item(row, USE).checkState() == Qt.CheckState.Checked
        return ticked or self.plans[row].already_entered

    def _roster_edit(self, row: int) -> bool:
        """An unticked rider on tonight's roster whose bib or group was changed here."""
        plan = self.plans[row]
        entry = self._entries.get(plan.rider_id) if plan.already_entered else None
        if entry is None:
            return False
        bib = "" if entry.bib is None else str(entry.bib)
        return self._typed_in(row) != (bib, entry.local_group or "")

    def _bib_or_none(self, row: int) -> int | None:
        try:
            return typed_bib(self.table.item(row, P_BIB).text())
        except ValueError:
            return None

    def _bib_problems(self) -> tuple[dict[int, str], dict[int, str]]:
        """Each ticked row's bib that is not a number (blocking), and who else wears it (not)."""
        bibs: dict[int, int] = {}
        problems: dict[int, str] = {}
        notes: dict[int, str] = {}
        for row in self.chosen():
            try:
                bib = typed_bib(self.table.item(row, P_BIB).text())
            except ValueError as exc:
                problems[row] = str(exc)
                continue
            if bib is not None:
                bibs[row] = bib
        for row, bib in bibs.items():
            mine = self.plans[row].rider_id
            others = [h for h in self._holders.get(bib, []) if h != mine]
            if others:
                notes[row] = f"bib {bib} is also worn by {rider_name(self.store, others[0])}"
                continue
            # The table shows no row numbers; the name is what the scorer sees.
            twin = next((r for r, b in bibs.items() if b == bib and r != row), None)
            if twin is not None:
                notes[row] = f"bib {bib} is also typed for {self.plans[twin].row.name}"
        return problems, notes

    def _check(self, _item: QTableWidgetItem | None = None, *, measure: bool = True) -> None:
        """Tints, Details and Import's state from the cells as they stand.

        ``measure`` False leaves the rows unmeasured, for a caller that
        measures every row right after: on a fresh fill every Details
        text is new, and measuring 300 rows one at a time and then all
        together would double the cost of opening the preview.
        """
        problems, notes = self._bib_problems()
        # Every cell change makes the columns sized to their contents
        # measure every row again, through the Python delegate and style:
        # setting all 120 Bib and Group cells on each keystroke would take a
        # second, and Select all on 60 rows most of a minute. So this pass
        # works out what differs first and touches only that, all inside
        # one fill. setFlags reports a change even when the flags are the
        # same, hence the comparisons.
        edits: list[tuple[QTableWidgetItem, Qt.ItemFlag | None, QColor | None]] = []
        changed = []
        retyped: list[tuple[QTableWidgetItem, str]] = []
        for row in range(self.table.rowCount()):
            editable = self._editable(row)
            bib = self.table.item(row, P_BIB)
            # A bib reads back as the file will hold it, "7" for "07", as
            # the roster's cell does.
            if editable and row not in problems:
                value = self._bib_or_none(row)
                tidy = "" if value is None else str(value)
                if bib.text() != tidy:
                    retyped.append((bib, tidy))
            for col in (P_BIB, P_GROUP):
                item = self.table.item(row, col)
                flags = item.flags() | Qt.ItemFlag.ItemIsEditable
                if not editable:
                    flags &= ~Qt.ItemFlag.ItemIsEditable
                tint = style.INPUT_GRAY if editable else style.COMPUTED_WHITE
                # The tint marks what is still to be filled in, not a stop.
                if item is bib and editable and (row in problems or not bib.text().strip()):
                    tint = style.DANGER_TINT
                new_flags = flags if flags != item.flags() else None
                new_tint = tint if item.background().color() != QColor(tint) else None
                if new_flags is not None or new_tint is not None:
                    edits.append((item, new_flags, new_tint))
            extra = [d[row] for d in (problems, notes) if row in d]
            text = "; ".join(self._details[row] + extra)
            if self.table.item(row, DETAILS).text() != text:
                changed.append((row, text))
        if edits or changed or retyped:
            # Tinting a cell is itself an item change; this pass must not
            # set off another.
            self.table.blockSignals(True)
            try:
                with filling(self.table):
                    for item, flags, tint in edits:
                        if flags is not None:
                            item.setFlags(flags)
                        if tint is not None:
                            item.setBackground(tint)
                    for item, text in retyped:
                        item.setText(text)
                    for row, text in changed:
                        details = self.table.item(row, DETAILS)
                        details.setText(text)
                        details.setToolTip(text)
            finally:
                self.table.blockSignals(False)
        # This pass runs on every keystroke's item change; measuring a
        # wrapped row is the costly part, so only a new text is worth it.
        for row, _text in changed if measure else ():
            self.table.resizeRowToContents(row)
        if problems:
            row = min(problems)
            reason = f"{self.plans[row].row.name}: {problems[row]}."
        else:
            reason = ""
        self.apply_button.setEnabled(not reason)
        self.apply_button.setToolTip(reason)

    def _typed(self, row: int, col: int, key: int) -> None:
        """Enter moves down the column to the next editable row; Tab crosses the row."""
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.edit_cell(row + 1, col, 1)
        elif key == Qt.Key.Key_Tab:
            if col == P_BIB:
                self.edit_cell(row, P_GROUP, 1, this_row=True)
            else:
                self.edit_cell(row + 1, P_BIB, 1)
        elif col == P_GROUP:
            self.edit_cell(row, P_BIB, -1, this_row=True)
        else:
            self.edit_cell(row - 1, P_GROUP, -1)

    def edit_cell(self, row: int, col: int, step: int = 1, this_row: bool = False) -> bool:
        """Open ``col`` in ``row``, or in the first editable row from there going ``step``.

        ``this_row`` opens ``row`` itself: Tab from a row's Bib to its
        Group stays on the row being typed in.
        """
        if this_row and 0 <= row < self.table.rowCount():
            self._open(row, col)
            return True
        while 0 <= row < self.table.rowCount():
            if self._editable(row):
                self._open(row, col)
                return True
            row += step
        return False

    def _open(self, row: int, col: int) -> None:
        self.table.setCurrentCell(row, col)
        self.table.editItem(self.table.item(row, col))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._shown:
            self._shown = True
            empty = [
                r
                for r in range(self.table.rowCount())
                if self._editable(r) and not self.table.item(r, P_BIB).text().strip()
            ]
            if empty:
                # Straight into typing: the first bib wanted is open.
                QTimer.singleShot(0, self, lambda: self.edit_cell(empty[0], P_BIB))

    def _cell_clicked(self, row: int, col: int) -> None:
        if col == USE:
            self.set_checked(row, row not in self.ticked())

    def set_checked(self, row: int, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.table.item(row, USE).setCheckState(state)

    def tick_rows(self, which: str) -> None:
        """Tick every row ("all"), only the new riders ("new"), or none.

        A row whose license or UCI ID is on file for someone else stays
        off for all and new: which record is right is the scorer's call,
        one row at a time, never a bulk one. So does a later row of a
        rider registered twice with another group or bib, since ticking
        both lets the last row win, and a New? row, since a rider of that
        name is on file and a bulk tick is how a duplicate gets made.
        """
        # Each tick is an item change, and each change runs the check pass
        # over every row, so the ticks go in quietly inside one fill, then
        # one check.
        self.table.blockSignals(True)
        try:
            with filling(self.table):
                for row, plan in enumerate(self.plans):
                    if which == "none":
                        on = False
                    elif plan.conflict or plan.start_unticked:
                        continue
                    else:
                        on = which == "all" or plan.status == "new"
                    self.set_checked(row, on)
        finally:
            self.table.blockSignals(False)
        self._check()

    def ticked(self) -> list[int]:
        return [
            row
            for row in range(self.table.rowCount())
            if self.table.item(row, USE).checkState() == Qt.CheckState.Checked
        ]

    def chosen(self) -> list[int]:
        """The rows Import applies: the ticked ones, and roster riders given a new bib or group."""
        ticked = set(self.ticked())
        return [r for r in range(self.table.rowCount()) if r in ticked or self._roster_edit(r)]

    def typed_anything(self) -> bool:
        return any(self._typed_in(r) != self._proposed[r] for r in range(self.table.rowCount()))

    def reject(self) -> None:
        # Escape is one key away from the bibs typed off a sheet; losing
        # them takes an answer, and closing with nothing typed takes none.
        if (
            self.result is None
            and self.typed_anything()
            and not icons.ask(
                self, "Import from BikeReg", "Discard the bibs you typed?", verb="Discard"
            )
        ):
            return
        super().reject()

    def edited_plans(self) -> list[ImportPlan] | None:
        plans = []
        ticked = set(self.ticked())
        chosen = set(self.chosen())
        for row, plan in enumerate(self.plans):
            if row not in chosen:
                # Left out: what is in its cells is not imported, so it
                # cannot stop the rows that are.
                plans.append(plan)
                continue
            try:
                bib = typed_bib(self.table.item(row, P_BIB).text())
            except ValueError as exc:
                show_message(self.error, f"{plan.row.name}: {exc}.")
                return None
            group = clean_line(self.table.item(row, P_GROUP).text()) or None
            edited = replan(plan, bib=bib, group=group)
            if row not in ticked:
                # An unticked roster rider brings only the bib and group
                # typed here, never the rider changes the tick was off for.
                edited.action, edited.changes = "match", {}
            plans.append(edited)
        return plans

    def apply(self) -> bool:
        """Import the chosen rows, after the scorer settles each one that differs from its rider.

        Every ticked rider on file whose values differ from the file's is
        reviewed in turn before anything is written;
        a Cancel there writes nothing and comes back here.
        """
        if not self.apply_button.isEnabled():
            show_message(self.error, self.apply_button.toolTip())
            return False
        plans = self.edited_plans()
        if plans is None:
            return False
        pending = [i for i in self.chosen() if plans[i].rider_id is not None and plans[i].disputes]
        for number, row in enumerate(pending, 1):
            resolved = self.review(row, plans[row], number, len(pending))
            if resolved is None:
                return False
            plans[row].resolved = resolved
        try:
            self.result = apply_import(self.store, self.event_id, plans, self.chosen())
        except (StoreError, ValueError) as exc:
            show_message(self.error, friendly_error(self.store, exc))
            return False
        self.accept()
        return True

    def review(self, row: int, plan: ImportPlan, number: int, total: int) -> dict | None:
        """The values chosen for one row's rider, or None when the scorer cancels."""
        dialog = ReconcileDialog(self.store, plan, number, total, self, picks=self.picks.get(row))
        accepted = run_dialog(dialog) == QDialog.DialogCode.Accepted
        self.picks[row] = dialog.values.chosen()
        return dialog.resolution() if accepted else None


class ReconcileDialog(QDialog):
    """One rider on file against the import's row: what agrees is kept, what differs is chosen.

    The same table as Merge riders. A value the file only fills in is
    shown as kept, since a blank is not a disagreement; each difference
    offers the database's value and the file's, nothing chosen. The title
    counts the reviews, so the scorer knows how many are left.
    """

    def __init__(
        self,
        store: Store,
        plan: ImportPlan,
        number: int,
        total: int,
        parent: QWidget | None = None,
        *,
        picks: dict[int, int] | None = None,
    ):
        super().__init__(parent)
        self.plan = plan
        rider = store.rider(plan.rider_id)
        self.setWindowTitle(f"Update {rider.name} from the File ({number} of {total})")
        fit_to_screen(self, 640, 420)
        apply_style(self)
        lines = []
        for name, label in RIDER_VALUES:
            old = getattr(rider, name)
            if name in plan.disputes:
                new = plan.disputes[name][1]
                lines.append(
                    MergeValue(
                        "rider", name, label, (old, new), (f"{old} (on file)", f"{new} (BikeReg)")
                    )
                )
            else:
                value = plan.fills[name][1] if name in plan.fills else old
                values = () if value in (None, "") else (value,)
                lines.append(
                    MergeValue("rider", name, label, values, tuple(str(v) for v in values))
                )
        self.values = ValueLines()
        self.values.changed.connect(self._update)
        self.left = QLabel("")
        self.left.setObjectName("hint")
        last = number == total
        buttons, made = button_row("Import" if last else "Next", self.accept, self.reject)
        buttons.insertWidget(1, self.left)
        self.primary = made["primary"]
        lay = QVBoxLayout(self)
        # One name differing is a nickname or a married name; both is the
        # sign of a mistyped id or a wrong pick, where the file's side
        # would rename another person.
        self.warning = QLabel("Both names differ: this may be another rider.")
        self.warning.setWordWrap(True)
        lay.addWidget(self.warning)
        self.warning.setVisible({"first_name", "last_name"} <= set(plan.disputes))
        lay.addWidget(self.values, 1)
        lay.addLayout(buttons)
        self.values.fill(lines, picks=picks)

    def _update(self) -> None:
        left = self.values.left()
        self.left.setText(f"{left} to choose" if left else "")
        self.primary.setEnabled(not left)
        self.primary.setToolTip("Choose a value on each tinted line." if left else "")

    def accept(self) -> None:
        if self.values.left():
            return
        super().accept()

    def resolution(self) -> dict[str, object]:
        """Each difference's chosen value, by rider column."""
        chosen = self.values.chosen()
        return {
            line.key: line.values[chosen[row]]
            for row, line in enumerate(self.values.lines)
            if line.differs and row in chosen
        }
