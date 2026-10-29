"""The input fuzzer's corpus and machinery, shared by the quick tier and the deep tier.

Whatever a scorer can type or paste goes into every editable input the
app shows: the corpus is garbage of the kinds that arrive from a
spreadsheet, an email, a phone or a held key. The inputs are not listed
by hand. Each screen and dialog is built, and every visible, enabled
line edit, editable combo box, spin or date box and editable table cell
in it is found, so a field added later is fuzzed without anyone
remembering to add it.

A string goes in as a paste (the clipboard, then the widget's own
paste, so validators and length limits apply as they do for a scorer),
then Enter, then the dialog's primary button. After that nothing may
have escaped a slot, what the file holds must be clean, and the screen,
the board, the PDF and the USAC CSV must still build.

Every string is spelled with chr() so this file stays plain ASCII.
"""

import datetime
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QWidget,
)

from madtracker.inputs import BIB_MAX, MAX_TEXT, clean_line

LS, PS = chr(0x2028), chr(0x2029)
RLO, LRI, PDI = chr(0x202E), chr(0x2066), chr(0x2069)
ZWSP, ZWJ, BOM, VS16 = chr(0x200B), chr(0x200D), chr(0xFEFF), chr(0xFE0F)
BIKE, MAN, WOMAN, GIRL = chr(0x1F6B4), chr(0x1F468), chr(0x1F469), chr(0x1F467)
FLAG, RAINBOW = chr(0x1F3F3), chr(0x1F308)
ACUTE = chr(0x0301)
SUP = {"1": chr(0x00B9), "2": chr(0x00B2), "9": chr(0x2079), "0": chr(0x2070)}
FULL_1, FULL_2 = chr(0xFF11), chr(0xFF12)
ARABIC_3 = chr(0x0663)
ARABIC_NAME = "".join(chr(c) for c in (0x0645, 0x062D, 0x0645, 0x062F))
CJK_NAME = chr(0x5C71) + chr(0x7530)
LONE_SURROGATE = "a" + chr(0xD800) + "b"

CORPUS: tuple[str, ...] = (
    "",
    "   ",
    "  Ann  ",
    "\t",
    "Ann\tLee\t12\tGroup A\t1990",
    "Ann\r\nLee",
    "Ann\nLee\nMore lines\n",
    f"Ann{LS}Lee",
    f"Ann{PS}Lee",
    f"{RLO}Ann Lee",
    f"{LRI}Ann{PDI} Lee",
    ZWSP * 3,
    f"A{ZWSP}nn",
    f"{BOM}Ann",
    "\x00",
    "Ann\x00Lee",
    "\x07\x08\x1b[31mred",
    BIKE,
    f"{MAN}{ZWJ}{WOMAN}{ZWJ}{GIRL}",
    f"{FLAG}{VS16}{ZWJ}{RAINBOW}",
    "x" * 10_000,
    SUP["2"],
    SUP["1"] + SUP["9"] + SUP["9"] + SUP["0"],
    FULL_1 + FULL_2,
    ARABIC_3,
    "1e9",
    "inf",
    "-0",
    "NaN",
    "99999999999999999999",
    "0",
    "-1",
    "12.5",
    "1990",
    "7",
    "'; DROP TABLE rider; --",
    "Robert'); DELETE FROM race_action;--",
    '=HYPERLINK("http://x")',
    "+cmd|' /C calc'!A0",
    "<b>x</b>",
    "<img src=x onerror=alert(1)>",
    "%s %d {0} {name}",
    "e" + ACUTE * 3,
    ARABIC_NAME,
    CJK_NAME,
    LONE_SURROGATE,
)

# Words that mean a raw Python or SQLite error reached the screen.
RAW_ERROR = (
    "Traceback",
    "invalid literal",
    "OverflowError",
    "ValueError",
    "TypeError",
    "KeyError",
    "AttributeError",
    "IndexError",
    "sqlite3",
    "NoneType",
)


@dataclass
class Target:
    """One editable input: a widget, or a table cell."""

    name: str
    kind: str  # line, combo, spin, cell
    widget: QWidget
    row: int = -1
    col: int = -1


def _label(widget: QWidget) -> str:
    parent = widget.parentWidget()
    while parent is not None:
        lay = parent.layout()
        if lay is not None:
            for form in [lay, *lay.findChildren(QFormLayout)]:
                if isinstance(form, QFormLayout):
                    label = form.labelForField(widget)
                    if isinstance(label, QLabel) and label.text():
                        return label.text()
        parent = parent.parentWidget()
    for text in (
        widget.objectName(),
        getattr(widget, "placeholderText", lambda: "")(),
        widget.toolTip(),
    ):
        if text:
            return text[:40]
    return type(widget).__name__


def find_inputs(root: QWidget) -> list[Target]:
    """Every visible, enabled input under ``root``, in a stable order."""
    found: list[Target] = []
    owned: set[int] = set()
    widgets = [root, *root.findChildren(QWidget)]
    for w in widgets:
        if w is not root and not w.isVisibleTo(root):
            continue
        if not w.isEnabled():
            continue
        if isinstance(w, QAbstractSpinBox):
            if not w.isReadOnly():
                found.append(Target(f"{_label(w)} (spin)", "spin", w))
            owned.add(id(w.findChild(QLineEdit)))
        elif isinstance(w, QComboBox) and w.isEditable():
            found.append(Target(f"{_label(w)} (combo)", "combo", w))
            owned.add(id(w.lineEdit()))
        elif isinstance(w, QTableWidget):
            for col in range(w.columnCount()):
                for row in range(w.rowCount()):
                    item = w.item(row, col)
                    if item is not None and item.flags() & Qt.ItemFlag.ItemIsEditable:
                        head = w.horizontalHeaderItem(col)
                        name = head.text() if head is not None else f"column {col}"
                        found.append(Target(f"{name} (cell)", "cell", w, row, col))
                        break
    for w in widgets:
        if isinstance(w, QLineEdit) and id(w) not in owned:
            if (w is root or w.isVisibleTo(root)) and w.isEnabled() and not w.isReadOnly():
                # A table's open editor is a cell, found above.
                if isinstance(w.parentWidget(), QWidget) and isinstance(
                    w.parentWidget().parentWidget(), QTableWidget
                ):
                    continue
                found.append(Target(_label(w), "line", w))
    return found


def _paste(edit: QLineEdit, text: str) -> None:
    QApplication.clipboard().setText(text)
    edit.setFocus()
    edit.selectAll()
    edit.paste()


def feed(root: QWidget, target: Target, text: str) -> None:
    """Paste ``text`` into the target and commit it the way a scorer would."""
    w = target.widget
    if target.kind == "cell":
        item = w.item(target.row, target.col)
        if item is None or not item.flags() & Qt.ItemFlag.ItemIsEditable:
            return
        w.setCurrentCell(target.row, target.col)
        w.editItem(item)
        # The open editor (a line edit, or an editable combo's): a closed
        # one lingers hidden until its deferred delete, and typing into
        # it would reach nothing after the first string.
        open_now = [e for e in w.viewport().findChildren(QLineEdit) if e.isVisibleTo(w)]
        editor = open_now[-1] if open_now else None
        if editor is None:
            item.setText(text)
        else:
            _paste(editor, text)
            QTest.keyClick(editor, Qt.Key.Key_Return)
    elif target.kind == "combo":
        _paste(w.lineEdit(), text)
        QTest.keyClick(w.lineEdit(), Qt.Key.Key_Return)
        w.lineEdit().editingFinished.emit()
    elif target.kind == "spin":
        edit = w.findChild(QLineEdit)
        _paste(edit, text)
        QTest.keyClick(edit, Qt.Key.Key_Return)
        w.editingFinished.emit()
    else:
        _paste(w, text)
        QTest.keyClick(w, Qt.Key.Key_Return)
    QApplication.processEvents()
    if isinstance(root, QDialog) and not closed(root):
        primary = root.findChild(QPushButton, "primary")
        if primary is not None and primary.isVisibleTo(root) and primary.isEnabled():
            primary.click()
            QApplication.processEvents()


def closed(root: QWidget) -> bool:
    """A dialog that saved: accept() set its result."""
    # QDialog.result itself: ImportPreview keeps its import result as .result.
    return isinstance(root, QDialog) and QDialog.result(root) == QDialog.DialogCode.Accepted


def shown_errors(root: QWidget) -> list[str]:
    """Every visible label under ``root`` that reads as a raw error."""
    out = []
    for label in root.findChildren(QLabel):
        if label.isVisibleTo(root) and any(word in label.text() for word in RAW_ERROR):
            out.append(label.text()[:200])
    return out


def stored_problems(store) -> list[str]:
    """Anything in the file that a clean input path would never have written."""
    conn = store.connection
    problems = []
    text_columns = {
        "rider": ("first_name", "last_name", "usac_license", "uci_id"),
        "event": ("name", "series", "venue"),
        "race": ("name", "group_label", "usac_category", "usac_class", "usac_age_group"),
        "roster_entry": ("local_group",),
        "team": ("name",),
        "ruleset": ("name",),
    }
    for table, columns in text_columns.items():
        for column in columns:
            for (value,) in conn.execute(f"SELECT {column} FROM {table}"):
                if isinstance(value, str) and clean_line(value, MAX_TEXT) != value:
                    problems.append(f"{table}.{column} = {value[:60]!r}")
    # What the screens name a thing by is never blank: a race, an event,
    # a team or a ruleset nobody can see in a list cannot be picked.
    for table in ("event", "race", "team", "ruleset"):
        for (value,) in conn.execute(f"SELECT name FROM {table}"):
            if not value:
                problems.append(f"{table}.name is blank")
    name = store.get_setting("venue/name")
    if isinstance(name, str) and clean_line(name) != name:
        problems.append(f"venue/name = {name[:60]!r}")
    this_year = datetime.date.today().year
    for (bib,) in conn.execute("SELECT bib FROM roster_entry WHERE bib IS NOT NULL"):
        if not (isinstance(bib, int) and 1 <= bib <= BIB_MAX):
            problems.append(f"bib {bib!r}")
    for (year,) in conn.execute("SELECT birth_year FROM rider WHERE birth_year IS NOT NULL"):
        if not (isinstance(year, int) and 1900 <= year <= this_year):
            problems.append(f"birth year {year!r}")
    for (doc,) in conn.execute("SELECT json FROM ruleset"):
        page = json.loads(doc) if doc else {}
        words = [page.get(key) for key in ("format_names", "format_descriptions")]
        for value in _strings(words):
            if clean_line(value, 10_000) != value:
                problems.append(f"ruleset words {value[:60]!r}")
    return problems


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def output_inputs(c) -> tuple:
    """Everything the screen, the board, the PDF and the CSV read for the open event.

    The outputs are rebuilt only when this changes: a string that went
    only into another event, or into a rider in no race, cannot change
    them, and the PDF is most of the quick tier's time.
    """
    conn, event_id = c.store.connection, c.event.event_id

    def rows(sql: str, *args) -> tuple:
        return tuple(tuple(r) for r in conn.execute(sql, args))

    return (
        rows("SELECT * FROM event WHERE event_id = ?", event_id),
        rows("SELECT * FROM race WHERE event_id = ?", event_id),
        rows("SELECT * FROM roster_entry WHERE event_id = ?", event_id),
        rows(
            "SELECT r.* FROM rider r JOIN roster_entry e ON e.rider_id = r.rider_id"
            " WHERE e.event_id = ?",
            event_id,
        ),
        rows(
            "SELECT t.* FROM team t JOIN race r ON r.race_id = t.race_id WHERE r.event_id = ?",
            event_id,
        ),
        rows("SELECT * FROM setting"),
        rows("SELECT * FROM ruleset"),
    )


def build_outputs(c, folder: Path) -> None:
    """The screen, every race's board payload, the PDF and the USAC CSV, from the file as it is."""
    from logbook import event_log

    from madtracker.control import board_feed
    from madtracker.control.race import LiveRace
    from madtracker.export import write_results_pdf, write_usac_csv

    store, event_id = c.store, c.event.event_id
    c._after_setup_change()
    for race in store.races(event_id):
        live = LiveRace(store, race.race_id)
        live.screen()
        layout, payload = board_feed.board_for(live.view())
        for board in c.boards:
            board.set_layout(layout, payload)
        c.board.grab()
    event_log(store, event_id)
    if c.live is not None:
        c.refresh()
    folder.mkdir(parents=True, exist_ok=True)
    write_results_pdf(store, event_id, folder / "fuzz.pdf")
    write_usac_csv(store, event_id, folder / "fuzz.csv")


class Escapes:
    """Every exception that escapes a slot, through sys.excepthook."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def __call__(self, exc_type, exc, tb) -> None:
        import traceback

        self.seen.append("".join(traceback.format_exception(exc_type, exc, tb))[-1500:])

    def take(self) -> list[str]:
        out, self.seen = self.seen, []
        return out


def quiet_qt(monkeypatch) -> list[str]:
    """Message boxes answered, modal dialogs and file pickers closed, menus not run."""
    from madtracker.ui import icons, widgets

    said: list[str] = []
    monkeypatch.setattr(widgets, "run_menu", lambda menu, where: None)
    monkeypatch.setattr(icons, "ask", lambda *a, **k: said.append(str(a[2])[:80]) or True)
    monkeypatch.setattr(icons, "choose", lambda *a, **k: said.append(str(a[2])[:80]) or a[4])
    monkeypatch.setattr(icons, "inform", lambda *a, **k: said.append(str(a[2])[:80]))
    monkeypatch.setattr(icons, "warn", lambda *a, **k: said.append(str(a[2])[:80]))
    import madtracker.ui.rulesets as rs
    import madtracker.ui.window as win

    for module in (win, rs):
        monkeypatch.setattr(module, "ask", icons.ask, raising=False)
    monkeypatch.setattr(QDialog, "exec", lambda self: int(QDialog.DialogCode.Rejected))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    return said


def make_controller(qapp, folder: Path):
    """The demo event with its first race scored and final, so names reach the PDF and CSV."""
    from madtracker.app import AppController

    settings = QSettings(str(folder / "s.ini"), QSettings.Format.IniFormat)
    c = AppController(qapp, demo=True, settings=settings, data_dir=folder / "data")
    # Durability is not what is fuzzed; one fsync per paste is minutes.
    c.store.connection.execute("PRAGMA synchronous = OFF")
    for eid in list(c.live.roster.ids):
        assert c.click(eid)
    assert c.mark_final()
    return c


def _rider_in_scored_race(c) -> int:
    race = c.races[0]
    return c.store.race_entries(race.race_id)[0].rider_id


def _unscored_race(c, fmt: str | None = None) -> int:
    for race in c.races:
        if race.state == "setup" and (fmt is None or race.format == fmt):
            return race.race_id
    raise AssertionError("the demo has no unscored race of that format")


def _import_preview(c):
    from madtracker.importers.bikereg import parse, plan_import
    from madtracker.ui.setup import ImportPreview

    text = (
        "Last Name,First Name,Bib,Age on 12/31/2026,Category\r\n"
        "Quill,Ada,,30,Group A\r\nMoss,Cy,5,40,Group B\r\n"
    )
    rows = parse(text)
    return ImportPreview(
        c.store, c.event.event_id, plan_import(c.store, c.event.event_id, rows), c.main
    )


def _standings_of_kind(c, kind):
    from madtracker.ui.standings import StandingsDialog

    for standings in c.store.list_standings():
        c.store.update_standings(standings.standings_id, kind=kind)
    return StandingsDialog(c.store, c.main, export=lambda _id: None)


def _setup_screen(c):
    c.open_setup()
    return c.main.setup


def _group_use(c, label: str):
    """The event's group named ``label``, or the first group there is.

    The deep tier builds a fresh Rename group dialog per string and a
    string that is a fair name renames the group, so the next dialog
    finds it under that name, not the one it was seeded with.
    """
    from madtracker.control import groups

    uses = groups.group_uses(c.store, c.event.event_id)
    return next((u for u in uses if u.label == label), uses[0])


def screens(c) -> dict[str, Callable[[], QWidget]]:
    """Each screen and dialog with text inputs, built fresh by its factory."""
    from madtracker.control import multi_race, rulesets
    from madtracker.ui import setup as su
    from madtracker.ui.rulesets import RulesetEditor
    from madtracker.ui.settings import SettingsDialog
    from madtracker.ui.standings import StandingsDialog

    store, event_id, main = c.store, c.event.event_id, c.main
    riders = [(r.rider_id, f"{r.first_name} {r.last_name}") for r in store.riders()[:4]]
    return {
        "Edit Event": lambda: _setup_screen(c),
        "New Event": lambda: su.NewEventDialog(store, main),
        "New Rider": lambda: su.RiderForm(store, None, main),
        "Edit Rider": lambda: su.RiderForm(store, _rider_in_scored_race(c), main),
        "Edit Riders": lambda: su.RidersDialog(store, None, main),
        "Choose Riders": lambda: su.RidersDialog(store, event_id, main),
        "Merge Riders": lambda: su.MergeDialog(store, store.riders()[-1].rider_id, main),
        "Import preview": lambda: _import_preview(c),
        "Add Race": lambda: su.RaceDialog(store, event_id, None, main),
        "Edit Race": lambda: su.RaceDialog(store, event_id, _unscored_race(c, "points"), main),
        "Edit Madison": lambda: su.RaceDialog(store, event_id, _unscored_race(c, "madison"), main),
        "Team": lambda: su.TeamDialog(riders, set(), 2, main),
        "New Group": lambda: su.NewGroupDialog(store, event_id, main),
        "Rename group": lambda: su.RenameGroupDialog(
            store, event_id, _group_use(c, "Group A"), main
        ),
        "Settings": lambda: SettingsDialog(store, c.data_dir, main),
        "New Ruleset": lambda: RulesetEditor(store, rulesets.builtin_ruleset(), None, main),
        "Multi-Race Standings": lambda: StandingsDialog(store, main, export=lambda _id: None),
        # The place kinds, whose Place points field the other kinds hide;
        # the rider kind's preview is bibs and names.
        "Multi-Race Standings by Place": lambda: _standings_of_kind(c, multi_race.PLACES),
        "Multi-Race Standings Omnium": lambda: _standings_of_kind(c, multi_race.OMNIUM),
        "Multi-Race Standings Four-Race": lambda: _standings_of_kind(c, multi_race.FOUR_RACE),
    }


# Dialogs with nothing to type in, or reached only through one above.
NO_TEXT_INPUT = {
    "HelpWindow": "read only",
    "AboutDialog": "read only",
    "LicensesDialog": "read only",
    "StartDialog": "three buttons",
    "OpenEventDialog": "a list of events",
    "GroupsDialog": "a list; its Rename is fuzzed as Rename group",
    "CopyFileDialog": "check boxes",
    "ExportPdfDialog": "radio buttons and a list of races",
    "PointsPenaltyDialog": "one spin box, 1 to 99",
    "OmniumPenaltyDialog": "a rider list and one spin box, 0 to 999",
    "ShortenRaceDialog": "one spin box, the next sprint to one below the count",
    "ReconcileDialog": "choices between two values, no typing",
    "RulesetsDialog": "a list; its Duplicate name is fuzzed through new_from",
    "NameDialog": "fuzzed as New Group and Rename group, which are built on it",
    "SettingsDialog": "fuzzed as Settings",
    "RulesetEditor": "fuzzed as New ruleset",
}
FUZZED_CLASSES = {
    "SetupScreen",
    "NewEventDialog",
    "RiderForm",
    "RidersDialog",
    "MergeDialog",
    "ImportPreview",
    "RaceDialog",
    "TeamDialog",
    "NewGroupDialog",
    "RenameGroupDialog",
    "StandingsDialog",
}


def every_dialog_class() -> set[str]:
    """Every QDialog subclass the app defines, and the setup screen."""
    import importlib
    import inspect
    import pkgutil

    import madtracker.ui

    names = {"SetupScreen"}
    for info in pkgutil.iter_modules(madtracker.ui.__path__):
        module = importlib.import_module(f"madtracker.ui.{info.name}")
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == module.__name__ and issubclass(cls, QDialog):
                names.add(name)
    return names


def run_screen(
    c, factory, strings, folder: Path, escapes: Escapes, *, fresh: bool = False
) -> list[str]:
    """Every string into every input of one screen; the failures, as lines.

    A dialog that saves closes. With ``fresh`` the next string gets a new
    one, as the scorer would; without, the same dialog is shown again,
    which is what keeps the quick tier quick (a race dialog takes 15 ms
    to build). The outputs are built once per input, and only when what
    they read changed (output_inputs), since otherwise they cannot have.
    """
    failures: list[str] = []
    # Never shown: painting a dialog per string would be most of the time, and
    # every input is found and fed the same without it.
    root = factory()
    targets = find_inputs(root)
    built_for = None
    for index in range(len(targets)):
        for text in strings:
            if closed(root):
                if fresh:
                    root.deleteLater()
                    root = factory()
                else:
                    QDialog.setResult(root, 0)
            current = find_inputs(root)
            if index >= len(current):
                break
            target = current[index]
            try:
                feed(root, target, text)
            except Exception as exc:  # the fuzzer reports, it does not stop
                failures.append(f"{target.name} <- {text[:30]!r}: raised {exc!r}")
            for escaped in escapes.take():
                failures.append(f"{target.name} <- {text[:30]!r}: escaped a slot\n{escaped}")
            for shown in shown_errors(root):
                failures.append(f"{target.name} <- {text[:30]!r}: shows {shown!r}")
            # Each string's own write, before the next one overwrites it.
            for problem in stored_problems(c.store):
                failures.append(f"{target.name} <- {text[:30]!r}: stored {problem}")
        read = output_inputs(c)
        if read != built_for:
            built_for = read
            try:
                build_outputs(c, folder)
            except Exception as exc:
                failures.append(f"after {targets[index].name}: outputs failed: {exc!r}")
        for escaped in escapes.take():
            failures.append(f"after {targets[index].name}: escaped while building\n{escaped}")
    root.deleteLater()
    if not targets:
        failures.append("no inputs found")
    return failures


def run_duplicate_ruleset(c, strings, escapes: Escapes) -> list[str]:
    """Rulesets > Duplicate...: the typed name goes through new_from, as the prompt hands it on."""
    from madtracker.ui.rulesets import RulesetsDialog

    failures = []
    dialog = RulesetsDialog(c.store, c.main)
    for text in strings:
        try:
            dialog.new_from(text)
        except Exception as exc:
            failures.append(f"Duplicate ruleset <- {text[:30]!r}: raised {exc!r}")
        for escaped in escapes.take():
            failures.append(f"Duplicate ruleset <- {text[:30]!r}: escaped\n{escaped}")
    dialog.close()
    return failures
