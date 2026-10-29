"""Settings > Rulesets: the venue's named rulesets, next to the built-in one.

The list shows the built-in USAC ruleset (read-only) and every stored
ruleset. Duplicate... copies one under a new name; Edit opens the page of
values, a tab per scoring family with the venue's own names for the
formats; Set as default picks what the race editor starts from. Import
and Export move one ruleset through a JSON file, which is how a venue's
set reaches a new laptop.

Each prompt (a name, a file, a confirmation) is a method argument with a
dialog behind it when the argument is left out, so the tests drive the
same code the buttons do without a modal box.
"""

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from madtracker.control import rulesets
from madtracker.control.backups import open_file_refusal
from madtracker.inputs import clean_line
from madtracker.scoring import rules as R
from madtracker.store import Store, StoreError
from madtracker.ui import style
from madtracker.ui.about import NOT_USAC
from madtracker.ui.icons import ask
from madtracker.ui.look import DIALOG_BASE_PT
from madtracker.ui.widgets import (
    PLACEHOLDER_ROLE,
    Form,
    NameDialog,
    PlaceholderDelegate,
    apply_style,
    button_row,
    close_on_shortcut,
    error_label,
    fit_to_screen,
    input_item,
    run_dialog,
    setup_table,
    show_message,
    spin_box,
    why_label,
    with_why,
)

TABLE_TIP = f"Points per place, first place first, like {rulesets.TABLE_SAMPLE}"
# The one sentence shape for a refused table, as the Multi-Race Standings
# field words its own.
BAD_TABLE = (
    f"Sprint points are whole numbers from 0 to {rulesets.TABLE_MAX},"
    f" such as {rulesets.TABLE_SAMPLE}."
)
LONG_TABLE = f"Sprint points can be set for up to {rulesets.MAX_COUNT} places."


def _sentence(exc: Exception) -> str:
    text = str(exc)
    text = text[0].upper() + text[1:] if text else "That did not work"
    return text if text.endswith(".") else text + "."


class _WordsDelegate(PlaceholderDelegate):
    """The words table's cells take as much as the one-format tabs' fields do."""

    LIMITS = {
        1: rulesets.WORD_LIMITS["format_names"],
        2: rulesets.WORD_LIMITS["format_descriptions"],
    }

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        limit = self.LIMITS.get(index.column())
        if limit and hasattr(editor, "setMaxLength"):
            editor.setMaxLength(limit)
        return editor


def parse_table(text: str) -> tuple[int, ...]:
    parts = rulesets.split_table(text)
    # ASCII digits only: "²" passes isdigit and fails int().
    digits = all(p.isascii() and p.isdigit() for p in parts)
    if not parts or not digits or any(int(p) > rulesets.TABLE_MAX for p in parts):
        raise ValueError(BAD_TABLE)
    if len(parts) > rulesets.MAX_COUNT:
        raise ValueError(LONG_TABLE)
    return tuple(int(p) for p in parts)


NAME_ROLE = Qt.ItemDataRole.UserRole
# On the controls that change or remove a ruleset, as a tooltip: the
# scorer asking "will this change last week?" hovers the button.
BUILT_IN = "Built-in"
COPY_NOTE = (
    "A race keeps its own copy of the rules it was created with. Editing or deleting"
    " a ruleset here never changes a race that already exists."
)
BUILTIN_TIP = (
    f"Point values from the {R.RULEBOOK_CITATION}, and the"
    f" documented club values for the formats the rulebook has no article for. {NOT_USAC}"
)
# The disabled Edit, Rename and Delete buttons say why once.
BUILTIN_LOCKED_TIP = f"{rulesets.BUILTIN_LABEL} is built in. Duplicate it to change its values."


def _spin(lo: int, hi: int) -> QSpinBox:
    return spin_box(lo, hi)


# The field labels inside a family's tab, where the tab already says
# which format; PAGE_LABELS keeps the full names for refusals and files.
FIELD_LABELS = {
    "points_table": "Sprint points",
    "points_last_double": "Double points for the last sprint",
    "points_lap_gained": "Lap gained",
    "points_lap_lost": "Lap lost",
    "madison_table": "Sprint points",
    "madison_last_double": "Double points for the last sprint",
    "madison_lap_gained": "Lap gained",
    "madison_lap_lost": "Lap lost",
    "tempo_points": "Points per sprint",
    "tempo_lap_gained": "Lap gained",
    "tempo_lap_lost": "Lap lost",
    "survivors": "Riders in the final sprint",
    "places": "Places",
    "direction": "Direction",
    "lapped_riders_placed": "Lapped riders are placed by laps down",
}
WORDS_TIP = (
    "Blank means the rulebook's name. The name goes on the program, the scorer's header,"
    " the scoreboard, and the results sheet; the description shows under the scorer's header."
)
RESET_TIP = "Fills this tab's values from the rulebook. The names and descriptions stay."


def _rulebook_text(key: str) -> str:
    """The built-in value as the scorer would type it, for a field's tooltip."""
    value = rulesets.builtin_ruleset()[key]
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return rulesets.table_text(value)
    return str(value)


class RulesetEditor(QDialog):
    """One page of values, saved as a whole document.

    A tab per scoring family holds that family's values, laps included
    (a lap is priced per sprint format), and, under them, what the
    venue calls each of its formats and the one line it says about
    them: two fields when the family is one format, a table when it is
    several (a one-row table reads as a chart).
    """

    def __init__(
        self,
        store: Store,
        doc: dict,
        ruleset_id: int | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.store = store
        self.doc = dict(doc)
        self.ruleset_id = ruleset_id
        self.setWindowTitle("Edit Ruleset" if ruleset_id else "New Ruleset")
        apply_style(self)

        self.name = QLineEdit(str(self.doc.get("name", "")))
        self.fields: dict[str, QWidget] = {
            "points_table": QLineEdit(),
            "points_last_double": QCheckBox(),
            "madison_table": QLineEdit(),
            "madison_last_double": QCheckBox(),
            **{key: _spin(*span) for key, span in rulesets.VALUE_RANGES.items()},
            "direction": QComboBox(),
            "lapped_riders_placed": QCheckBox(),
        }
        # An empty table field shows the rulebook's table in gray, in the
        # form the field takes.
        for key in ("points_table", "madison_table"):
            self.fields[key].setPlaceholderText(_rulebook_text(key))
            self.fields[key].setMaxLength(rulesets.TABLE_TEXT_MAX)
        direction = self.fields["direction"]
        direction.addItem("Forward (First Lap Winner Takes 1st)", "forward")
        direction.addItem("Reverse (Last Lap Winner Takes 1st)", "reverse")
        for family, keys in rulesets.FAMILY_KEYS.items():
            for key in keys:
                widget = self.fields[key]
                tip = f"{rulesets.FAMILY_SOURCE[family]}: {_rulebook_text(key)}"
                widget.setToolTip(f"{TABLE_TIP}. {tip}" if key.endswith("_table") else tip)
        # The word fields by (format key, word key), filled with the page: a
        # line edit on a one-format tab, a table cell on the many-format tab.
        self.words: dict[tuple[str, str], QLineEdit | QTableWidgetItem] = {}
        self.word_tables: list[QTableWidget] = []
        self.tabs = QTabWidget()
        for family, label in rulesets.FAMILY_LABELS.items():
            self.tabs.addTab(self._tab(family), label)
        self._fill()

        self.error = error_label()
        buttons, made = button_row("Save", self.save, self.reject)
        made["primary"].setToolTip(COPY_NOTE)

        top = Form()
        top.addRow("Name", self.name)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(self.error)
        lay.addLayout(buttons)
        # Wide enough for every tab's label, measured in the dialog's own
        # font size: at 11 pt the six do not fit 860 and the last would scroll
        # out of sight. fit_to_screen still keeps it on a small screen.
        margins = lay.contentsMargins()
        tabs_w = self.tabs.tabBar().sizeHint().width() + margins.left() + margins.right()
        fit_to_screen(self, max(860, tabs_w + style.MD), 540)

    def _tab(self, family: str) -> QWidget:
        page = QWidget()
        form = Form()
        for key in rulesets.FAMILY_KEYS[family]:
            form.addRow(FIELD_LABELS[key], self.fields[key])
        formats = rulesets.family_formats(family)
        lay = QVBoxLayout(page)
        source = rulesets.family_source_line(family)
        if source:
            # Whose values this tab holds, so a club format never reads as USAC's.
            line = QLabel(source)
            line.setObjectName("hint")
            lay.addWidget(line)
        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        if rulesets.FAMILY_SOURCE[family] == rulesets.RULEBOOK_LABEL:
            # A club format's defaults are a club's, so there is no rulebook
            # to fill its tab from; the tooltips say whose the values are.
            reset = QPushButton(f"Fill {rulesets.RULEBOOK_LABEL} Values")
            reset.setObjectName(f"reset_{family}")
            reset.setToolTip(RESET_TIP)
            reset.clicked.connect(lambda _=False, fam=family: self.reset_tab(fam))
            reset_row.addWidget(reset)
        lay.addLayout(form)
        if len(formats) == 1:
            (f,) = formats
            for key in rulesets.WORD_KEYS:
                field = QLineEdit()
                field.setMaxLength(rulesets.WORD_LIMITS[key])
                field.setToolTip(WORDS_TIP)
                if key == "format_names":
                    field.setPlaceholderText(f.label)
                self.words[(f.key, key)] = field
                form.addRow(rulesets.WORD_LABELS[key], field)
            lay.addLayout(reset_row)
            lay.addStretch(1)
            return page
        table = QTableWidget(len(formats), 3)
        table.setObjectName(f"words_{family}")
        setup_table(table, ["Format", rulesets.WORD_HEADERS["format_names"], "Description"])
        table.setToolTip(WORDS_TIP)
        # An empty Shown as cell shows the rulebook's name in gray, as the
        # one-format tabs' field does; a description has no default to show.
        table.setItemDelegate(_WordsDelegate(table))
        for row, f in enumerate(formats):
            table.setItem(row, 0, input_item(f.source_text, editable=False))
            for col, key in ((1, "format_names"), (2, "format_descriptions")):
                item = input_item("")
                if key == "format_names":
                    item.setData(PLACEHOLDER_ROLE, f.label)
                table.setItem(row, col, item)
                self.words[(f.key, key)] = item
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(1, 180)
        table.verticalHeader().setDefaultSectionSize(style.control_height(DIALOG_BASE_PT, 1.7))
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.word_tables.append(table)
        lay.addWidget(table)
        lay.addLayout(reset_row)
        lay.addStretch(1)
        return page

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Every row shows: each words table is as tall as its rows, the way
        # the About box sizes its credits. Measured here, once the style
        # has given the header and the rows their real heights.
        for t in self.word_tables:
            rows = sum(t.rowHeight(r) for r in range(t.rowCount()))
            t.setFixedHeight(t.horizontalHeader().height() + rows + 2 * t.frameWidth())

    def _set(self, key: str, value) -> None:
        widget = self.fields[key]
        if isinstance(widget, QSpinBox):
            # A stored page is not checked again as it opens, and setValue
            # overflows past a C int, so a number outside the box's range
            # opens at the nearest one the box takes.
            number = int(value) if value is not None else widget.minimum()
            widget.setValue(min(max(number, widget.minimum()), widget.maximum()))
        elif isinstance(widget, QLineEdit):
            widget.setText(rulesets.table_text(value or ()))
        elif isinstance(widget, QComboBox):
            widget.setCurrentIndex(max(0, widget.findData(value)))
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))

    def _fill(self) -> None:
        for key in self.fields:
            self._set(key, self.doc.get(key))
        for (format_key, word_key), item in self.words.items():
            item.setText(str((self.doc.get(word_key) or {}).get(format_key, "") or ""))

    def reset_tab(self, family: str) -> None:
        """The rulebook's values on one tab; the words are the venue's and stay."""
        rulebook = rulesets.builtin_ruleset()
        for key in rulesets.FAMILY_KEYS[family]:
            self._set(key, rulebook[key])

    def build_doc(self) -> dict:
        """The page as the form has it, blank words left out. Raises ValueError for a bad table."""
        doc: dict = {"name": clean_line(self.name.text())}
        for key, widget in self.fields.items():
            if isinstance(widget, QSpinBox):
                doc[key] = widget.value()
            elif isinstance(widget, QLineEdit):
                doc[key] = list(parse_table(widget.text()))
            elif isinstance(widget, QComboBox):
                doc[key] = widget.currentData()
            elif isinstance(widget, QCheckBox):
                doc[key] = widget.isChecked()
        for word_key in rulesets.WORD_KEYS:
            words = {
                format_key: item.text().strip()
                for (format_key, key), item in self.words.items()
                if key == word_key and item.text().strip()
            }
            if words:
                doc[word_key] = words
        return doc

    def save(self) -> bool:
        try:
            doc = self.build_doc()
            problems = rulesets.validate_ruleset(doc)
            if problems:
                show_message(self.error, "\n".join(problems))
                return False
            row = rulesets.save_ruleset(self.store, doc, self.ruleset_id)
        except (ValueError, StoreError) as exc:
            text = str(exc)
            show_message(self.error, text[0].upper() + text[1:] if text else "Cannot save.")
            return False
        self.ruleset_id = row.ruleset_id
        self.doc = row.doc
        self.accept()
        return True


class RulesetsDialog(QDialog):
    def __init__(self, store: Store, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Rulesets")
        fit_to_screen(self, 640, 420)
        apply_style(self)
        close_on_shortcut(self)

        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())
        self.list.itemDoubleClicked.connect(lambda *_: self.edit())

        self.new_button = QPushButton("Duplicate...")
        self.new_button.clicked.connect(lambda: self.new_from())
        self.edit_button = QPushButton("Edit...")
        self.edit_button.clicked.connect(self.edit)
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(lambda: self.delete())
        self.export_button = QPushButton("Export to File...")
        self.export_button.clicked.connect(lambda: self.export_to())
        self.import_button = QPushButton("Import from File...")
        self.import_button.clicked.connect(lambda: self.import_from())
        self.default_button = QPushButton("Set as Default")
        self.default_button.clicked.connect(self.set_default)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)

        self.edit_button.setToolTip(COPY_NOTE)
        self.delete_button.setToolTip(COPY_NOTE)
        self.status = error_label()

        # Why Edit and Delete are off for the built-in set, under them, as
        # the Riders and Groups windows say "Has raced" and "Used by a race".
        self.locked_why = why_label()
        side = QVBoxLayout()
        side.addWidget(self.new_button)
        side.addWidget(self.edit_button)
        side.addLayout(with_why(self.delete_button, self.locked_why))
        for button in (self.export_button, self.import_button, self.default_button):
            side.addWidget(button)
        side.addStretch(1)
        body = QHBoxLayout()
        body.addWidget(self.list, 1)
        body.addLayout(side)
        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)
        bottom.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addLayout(bottom)
        # No default button: as the default, Duplicate... would open its name
        # box on Enter in the list. Enter in the list does nothing.
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)
        self.refresh()

    # ----- list -----------------------------------------------------------

    def refresh(self, select: str | None = None) -> None:
        current = select or self.selected_name()
        default = rulesets.default_ruleset_name(self.store)
        self.list.clear()
        for name in rulesets.ruleset_names(self.store):
            tags = []
            if rulesets.is_builtin(name):
                tags.append("Built-In")
            if name == default:
                tags.append("Default")
            label = rulesets.ruleset_label(name)
            item = QListWidgetItem(f"{label}  ({', '.join(tags)})" if tags else label)
            item.setData(NAME_ROLE, name)
            if rulesets.is_builtin(name):
                item.setToolTip(BUILTIN_TIP)
            self.list.addItem(item)
            if name == current:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self._update_buttons()

    def names(self) -> list[str]:
        return [self.list.item(i).data(NAME_ROLE) for i in range(self.list.count())]

    def selected_name(self) -> str | None:
        item = self.list.currentItem()
        return None if item is None else item.data(NAME_ROLE)

    def _selected_row(self):
        name = self.selected_name()
        if name is None or rulesets.is_builtin(name):
            return None
        return self.store.ruleset_by_name(name)

    def _update_buttons(self) -> None:
        name = self.selected_name()
        stored = name is not None and not rulesets.is_builtin(name)
        builtin = name is not None and not stored
        for button, tip in (
            (self.edit_button, COPY_NOTE),
            (self.delete_button, COPY_NOTE),
        ):
            button.setEnabled(stored)
            button.setToolTip(BUILTIN_LOCKED_TIP if builtin else tip)
        self.locked_why.setText(BUILT_IN if builtin else "")
        self.export_button.setEnabled(name is not None)
        self.default_button.setEnabled(
            name is not None and name != rulesets.default_ruleset_name(self.store)
        )

    def _say(self, text: str) -> None:
        show_message(self.status, text if text.endswith(".") else text + ".")

    def _done(self) -> None:
        # Success says nothing: the list shows the change (the new or
        # renamed row selected, the default tag moved). Only a stale
        # failure line is cleared.
        self.status.clear()

    def _fail(self, exc: Exception) -> None:
        self._say(_sentence(exc))

    # ----- actions ----------------------------------------------------------

    def new_from(self, name: str | None = None) -> str | None:
        """Copy the selected ruleset under a new name; returns the name when made.

        Without a name the dialog asks for one and refuses a bad one in
        place; a name handed in is refused on the status line instead.
        """
        source = self.selected_name()
        if source is None:
            return None

        def take(typed: str) -> str | None:
            try:
                made.append(rulesets.copy_ruleset(self.store, source, typed))
            except (rulesets.RulesetError, StoreError) as exc:
                return _sentence(exc)
            return None

        made: list[rulesets.Ruleset] = []
        if name is None:
            dialog = NameDialog(
                "Duplicate Ruleset",
                "Duplicate",
                take,
                text=f"{rulesets.ruleset_label(source)} copy",
                parent=self,
            )
            if run_dialog(dialog) != QDialog.DialogCode.Accepted or not made:
                return None
        else:
            refusal = take(name)
            if refusal:
                self._say(refusal)
                return None
        self.refresh(made[-1].name)
        self._done()
        return made[-1].name

    def editor_for_selected(self) -> RulesetEditor | None:
        row = self._selected_row()
        if row is None:
            name = self.selected_name()
            if name is not None:
                self._say(
                    f"{rulesets.ruleset_label(name)} is built in. Use Duplicate... to make an editable copy"
                )
            return None
        return RulesetEditor(self.store, row.doc, row.ruleset_id, self)

    def edit(self) -> None:
        editor = self.editor_for_selected()
        if editor is not None and run_dialog(editor) == QDialog.DialogCode.Accepted:
            self.refresh(editor.doc["name"])
            self._done()

    def delete(self, confirm: bool = True) -> bool:
        row = self._selected_row()
        if row is None:
            return False
        if confirm:
            if not ask(
                self,
                "Delete Ruleset",
                f"Delete {row.name}? Races made from it keep their own copy of the rules.",
                verb="Delete",
            ):
                return False
        try:
            rulesets.delete_ruleset(self.store, row.ruleset_id)
        except (rulesets.RulesetError, StoreError) as exc:
            self._fail(exc)
            return False
        self.refresh()
        self._done()
        return True

    def export_to(self, path: str | Path | None = None) -> Path | None:
        name = self.selected_name()
        if name is None:
            return None
        if path is None:
            # "usac-2025-club-defaults.json": a file name from a label with a "+" in it.
            suggested = re.sub(r"[^a-z0-9]+", "-", rulesets.ruleset_label(name).lower()).strip("-") + ".json"  # fmt: skip
            path, _ = QFileDialog.getSaveFileName(
                self, "Export Ruleset", suggested, "Ruleset Files (*.json)"
            )
            if not path:
                return None
        refusal = open_file_refusal(Path(path), self.store.path)
        if refusal:
            self._say(refusal)
            return None
        try:
            out = rulesets.export_ruleset(rulesets.ruleset_for(self.store, name), path)
        except OSError:
            # The OS's own text is not the scorer's; the name alone says
            # which file, and its place mid-sentence keeps its spelling.
            self._say(f"Could not write {Path(path).name or path}")
            return None
        except rulesets.RulesetError as exc:
            self._fail(exc)
            return None
        self._done()
        return out

    def import_from(
        self, path: str | Path | None = None, replace: bool | None = None
    ) -> str | None:
        """Import one ruleset file. ``replace`` None asks when the name is taken."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Import Ruleset", "", "Ruleset Files (*.json)"
            )
            if not path:
                return None
        try:
            doc = rulesets.read_ruleset_file(path)
            # Looked up as the name is stored, so a doubled space in the
            # file still finds the ruleset it would replace.
            existing = self.store.ruleset_by_name(clean_line(str(doc.get("name", ""))))
            if existing is not None and replace is None:
                replace = ask(
                    self,
                    "Replace Ruleset",
                    f"A ruleset named {existing.name} already exists. Replace its values"
                    " with the file's? Races already made from it are not changed.",
                    verb="Replace",
                )
                if not replace:
                    return None
            row = rulesets.import_ruleset(self.store, path, replace=bool(replace))
        except (rulesets.RulesetError, StoreError) as exc:
            self._fail(exc)
            return None
        self.refresh(row.name)
        self._done()
        return row.name

    def set_default(self) -> bool:
        name = self.selected_name()
        if name is None:
            return False
        try:
            rulesets.set_default_ruleset(self.store, name)
        except (rulesets.RulesetError, StoreError) as exc:
            self._fail(exc)
            return False
        self.refresh(name)
        self._done()
        return True


def open_rulesets(store: Store, parent: QWidget | None = None) -> None:
    """Settings > Rulesets. Returns when the dialog closes."""
    dialog = RulesetsDialog(store, parent)
    run_dialog(dialog)
