"""A click-happy scorer: random presses over the operator window, checked after each.

One ``Monkey`` is one seed. It builds the demo app headless, answers
every dialog, question, file picker and menu at random, and then takes
a random number of steps. A step is one thing a person could do: a
visible control pressed, a right-click, a double click, a key, a window
size, a dialog opened and poked at, a display plugged or pulled. After
each step the event loop runs, and the checks in ``check`` say whether
anything broke.

Everything random comes from one ``random.Random(seed)``, so a seed
replays the same steps while the window answers the same way.
"""

from __future__ import annotations

import gc
import os
import random
import shutil
import sqlite3
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# The repo's own code first, then the suite's helpers (apps, the walk's
# controls and snapshot, the fuzzer's corpus), as tools/scoring does.
for sub in ("tests/ui", "tests", ""):
    p = str(REPO / sub) if sub else str(REPO)
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QContextMenuEvent,
    QDesktopServices,
    QImage,
    QKeySequence,
    QMouseEvent,
)
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollBar,
    QSpinBox,
    QTabBar,
    QTextEdit,
    QWidget,
)

RSS_CAP = 1.5 * 1024**3
SIZES = [(1366, 740), (1600, 900), (1920, 1080)]
FAKE_TV = "FAKE-TV"
# Short words a person might type, beside the fuzzer's garbage. Invented names.
WORDS = [
    "Zed Testrider",
    "Quinn Paceline",
    "Group C",
    "Night 3",
    "x",
    "12",
    "0",
    "-3",
    "999",
    "a b",
    "Bell Lap Crew",
]


def pump() -> None:
    """What the app's event loop would do between two clicks."""
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def tail(text: str) -> str:
    """A traceback's first frames and its end, which together say where and what."""
    return text if len(text) < 3500 else text[:700] + "\n  ...\n" + text[-2800:]


def ascii_text(text: str) -> bool:
    """QTest types only printable ASCII; anything else goes in as a paste."""
    return all(32 <= ord(ch) < 127 for ch in text)


def rss() -> int:
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except OSError:
        return 0


def double_click(w: QWidget, at: QPoint | None = None) -> None:
    """A person's double-click: press, release, the second press as the double-click event, release.

    QTest.mouseDClick sends a press and the double-click event with no
    release, so a button under it never clicks at all; a person's
    double-click clicks a one-click button (a card, Undo, Record Sprint)
    once.
    """
    if at is None:
        at = w.rect().center()
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    for kind in (
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.MouseButtonRelease,
    ):
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


class FakeScreen:
    """A second display the offscreen platform does not have, for unplugging."""

    def name(self):
        return FAKE_TV

    def manufacturer(self):
        return "Fake"

    def model(self):
        return "TV"

    def geometry(self):
        from PySide6.QtCore import QRect

        return QRect(1920, 0, 1920, 1080)


@dataclass
class Failure:
    seed: int
    step: int
    name: str
    kind: str
    what: str


@dataclass
class Result:
    seed: int
    steps: int
    failures: list[Failure] = field(default_factory=list)
    trail: list[str] = field(default_factory=list)
    peak_rss: int = 0


class Monkey:
    def __init__(self, seed: int, steps: int | None, tmp: Path, say=None) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.steps = steps if steps is not None else self.rng.randint(200, 2000)
        self.tmp = Path(tmp)
        self.say = say
        self.escaped: list[str] = []
        self.harness_errors: list[str] = []
        # What the fakes did during the current step: dialogs, questions, menus.
        self.opened: list[str] = []
        self.depth = 0
        self.fake_tv = False
        self.result = Result(seed, self.steps)
        self._seen_kinds: dict[str, int] = {}
        self._log_at = 0
        self._log_file: Path | None = None
        self._count_store = None
        self._count = 0
        self._idle = 0
        self.trail_file: Path | None = None
        # A done card's press: the entrant, the controller's refusal, the
        # log's length, the staged row, and the red line before it; None
        # between presses.
        self._done = None

    # ----- the fakes -------------------------------------------------------

    def _hook(self, exc_type, exc, tb) -> None:
        self.escaped.append(tail("".join(traceback.format_exception(exc_type, exc, tb))))

    def note(self, text: str) -> None:
        self.opened.append(text)

    def _text(self) -> str:
        from fuzz_inputs import CORPUS

        r = self.rng.random()
        if r < 0.45:
            return self.rng.choice(WORDS)
        if r < 0.55:
            return "".join(
                self.rng.choice("abcdefghijklmnopqrstuvwxyz0123456789 ")
                for _ in range(self.rng.randint(1, 12))
            )  # noqa: E501
        return self.rng.choice(CORPUS)

    def _paths(self, kind: str) -> list[str]:
        files = self.tmp / "files"
        out = [""]
        if kind == "folder":
            out += [str(files), str(self.tmp / "nowhere" / "deeper"), str(self.tmp / "backups-x")]
            return out
        out += [str(p) for p in sorted(files.iterdir()) if p.is_file()]
        out.append(str(self.c.data_path))
        out += [str(p) for p in sorted(self.tmp.rglob("*.sqlite"))[:20]]
        n = self.rng.randint(0, 99)
        out += [
            str(files / f"new-{n}.sqlite"),
            str(files / f"export-{n}.pdf"),
            str(files / f"export-{n}.csv"),
            str(self.tmp / "nowhere" / "x.sqlite"),
        ]
        return out

    def _pick_path(self, kind: str):
        def pick(*a, **k):
            path = self.rng.choice(self._paths(kind))
            self.note(f"{kind}-picker:{path}")
            return path if kind == "folder" else (path, "")

        return staticmethod(pick)

    def _ask(self, parent, title, text, verb="OK"):
        yes = self.rng.random() < 0.6
        self.note(f"ask:{title}:{'yes' if yes else 'cancel'}")
        return yes

    def _choose(self, parent, title, text, verbs, primary, disabled=()):
        offered = [v for v in verbs if v not in disabled] + [None]
        got = self.rng.choice(offered)
        self.note(f"choose:{title}:{got}")
        return got

    def _inform(self, parent, title, text, *a, **k):
        self.note(f"inform:{title}")

    def _warn(self, parent, title, text, name=""):
        self.note(f"warn:{title}:{str(text)[:200]}")

    def _menu(self, menu: QMenu, where) -> None:
        # Every item is noted, a grayed one marked, since a menu whose
        # items are all grayed (the task line's ⋯ before the first sprint)
        # is a menu that opened; only an open item is ever picked.
        leaves = []

        def walk(m: QMenu) -> None:
            for a in m.actions():
                if a.isSeparator() or not a.isVisible():
                    continue
                if a.menu() is not None:
                    walk(a.menu())
                else:
                    leaves.append(a)

        walk(menu)
        self.note(
            "menu:" + ",".join(a.text() if a.isEnabled() else f"({a.text()})" for a in leaves)
        )
        leaves = [a for a in leaves if a.isEnabled()]
        if not leaves or self.rng.random() < 0.12:
            return
        a = self.rng.choice(leaves)
        self.note(f"menu-pick:{a.text()}")
        a.trigger()

    def _exec(self, dialog: QDialog) -> int:
        title = dialog.windowTitle()
        self.note(f"dialog:{title}")
        self.depth += 1
        try:
            dialog.show()
            pump()
            if self.depth <= 3:
                for _ in range(self.rng.randint(0, 8)):
                    if not dialog.isVisible():
                        break
                    self._safe(self.fiddle, dialog)
            if dialog.isVisible():
                self._safe(self.finish, dialog)
            pump()
            self.close_popups()
            if dialog.isVisible():
                dialog.reject()
            return QDialog.result(dialog)
        finally:
            self.depth -= 1

    def _safe(self, fn, *args):
        """The harness's own poke inside a fake exec: a bug here is the harness's, said apart."""
        try:
            return fn(*args)
        except Exception:
            self.harness_errors.append(tail(traceback.format_exc()))
            return None

    def finish(self, dialog: QDialog) -> None:
        r = self.rng.random()
        if r < 0.5:
            primary = [
                b
                for b in dialog.findChildren(QPushButton)
                if (b.objectName() == "primary" or b.isDefault())
                and b.isVisibleTo(dialog)
                and b.isEnabled()
            ]
            if primary:
                self.note(f"dialog-ok:{primary[0].text()}")
                primary[0].click()
                return
        if r < 0.6:
            self.note("dialog-key:Return")
            QTest.keyClick(QApplication.focusWidget() or dialog, Qt.Key.Key_Return)
        elif r < 0.7:
            self.note("dialog-key:Escape")
            QTest.keyClick(QApplication.focusWidget() or dialog, Qt.Key.Key_Escape)
        elif r < 0.75:
            self.note("dialog-key:Close")
            QTest.keySequence(dialog, QKeySequence(QKeySequence.StandardKey.Close))
        else:
            self.note("dialog-cancel")
            dialog.reject()

    def close_popups(self) -> None:
        """A combo's list a fiddle opened: a person clicks outside it."""
        for _ in range(5):
            popup = QApplication.activePopupWidget()
            if popup is None:
                return
            popup.close()
            pump()

    def patch(self) -> None:
        import madtracker.board.window as board_window
        import madtracker.ui.rulesets as rs
        import madtracker.ui.window as win
        from madtracker.ui import icons, widgets

        widgets.run_menu = self._menu
        QDialog.exec = lambda dialog: self._exec(dialog)
        QFileDialog.getOpenFileName = self._pick_path("file")
        QFileDialog.getSaveFileName = self._pick_path("file")
        QFileDialog.getExistingDirectory = self._pick_path("folder")
        icons.ask = self._ask
        icons.choose = self._choose
        icons.inform = self._inform
        icons.warn = self._warn
        win.ask = self._ask
        rs.ask = self._ask
        QDesktopServices.openUrl = staticmethod(
            lambda url: self.note("browse:" + url.toString()) or True
        )  # noqa: E501
        real_infos = board_window.screen_infos

        def infos(screens=None):
            out = real_infos(screens)
            if screens is None and self.fake_tv:
                from madtracker.displays import ScreenInfo

                out.append(ScreenInfo(FAKE_TV, 1920, 0, 1920, 1080, False, "Fake TV 1920 x 1080"))
            return out

        board_window.screen_infos = infos

    # ----- building --------------------------------------------------------

    def spare_files(self, template: Path) -> None:
        files = self.tmp / "files"
        files.mkdir(exist_ok=True)
        (files / "notes.txt").write_text("not a database\n")
        (files / "empty.sqlite").write_bytes(b"")
        (files / "junk.sqlite").write_bytes(bytes(self.rng.randrange(256) for _ in range(4096)))
        (files / "riders.csv").write_text("First Name,Last Name,License\nZed,Testrider,123\n,,\n")
        (files / "notpng.png").write_text("text, not a picture")
        img = QImage(64, 32, QImage.Format.Format_RGB32)
        img.fill(0x3366CC)
        img.save(str(files / "logo.png"))
        shutil.copy(template, files / "copy.sqlite")

    def build(self) -> None:
        from apps import demo_data_dir

        from madtracker import app as app_module
        from madtracker.app import AppController
        from madtracker.store.paths import DATABASE_FILE_NAME
        from madtracker.ui.look import apply_look

        self.qapp = QApplication.instance() or QApplication([])
        apply_look(self.qapp)
        self.patch()
        data = demo_data_dir(self.tmp, 0)
        self.spare_files(self.tmp / "demo-template" / DATABASE_FILE_NAME)
        self.settings = QSettings(str(self.tmp / "s.ini"), QSettings.Format.IniFormat)
        app_module.install_excepthook(None)
        app_hook = sys.excepthook

        def hook(exc_type, exc, tb):
            self._hook(exc_type, exc, tb)
            app_hook(exc_type, exc, tb)

        self.c = AppController(self.qapp, settings=self.settings, data_dir=data)
        app_module.set_excepthook_controller(self.c)
        sys.excepthook = hook
        self.c.start()
        self.c.main.showNormal()
        self.c.main.resize(1600, 900)
        pump()

    # ----- poking at a widget tree ------------------------------------------

    def _pokeable(self, root: QWidget) -> list[tuple[str, QWidget]]:
        out = []
        for w in root.findChildren(QWidget):
            if not w.isVisibleTo(root) or not w.isEnabled() or not w.isVisible():
                continue
            if isinstance(w, QScrollBar) or isinstance(w.parentWidget(), QScrollBar):
                continue
            if isinstance(w, QAbstractButton):
                if isinstance(w.parentWidget(), (QTabBar, QAbstractSpinBox)):
                    continue
                if w.text().replace("&", "") == "Quit":
                    continue
                out.append(("button", w))
            elif isinstance(w, QAbstractSpinBox):
                if not w.isReadOnly():
                    out.append(("spin", w))
            elif isinstance(w, QComboBox):
                out.append(("combo", w))
            elif isinstance(w, QLineEdit):
                p = w.parentWidget()
                if w.isReadOnly() or isinstance(p, (QComboBox, QAbstractSpinBox)):
                    continue
                out.append(("line", w))
            elif isinstance(w, (QTextEdit, QPlainTextEdit)):
                if not w.isReadOnly():
                    out.append(("text", w))
            elif isinstance(w, QAbstractItemView):
                from PySide6.QtCore import QModelIndex

                if w.model() is not None and w.model().rowCount(QModelIndex()) > 0:
                    out.append(("view", w))
            elif isinstance(w, QTabBar):
                out.append(("tabs", w))
        return out

    def fiddle(self, root: QWidget) -> str:
        """One random poke at a visible, enabled widget under ``root``; its description."""
        found = self._pokeable(root)
        if not found:
            return "nothing to poke"
        kind, w = self.rng.choice(found)
        what = f"{kind} {type(w).__name__} {self._label(w)!r}"
        self.note(f"poke:{what}")
        if kind == "button":
            w.click()
        elif kind == "line":
            self._type(w)
        elif kind == "text":
            w.setFocus()
            w.insertPlainText(self._text()[:500])
        elif kind == "spin":
            self._spin(w)
        elif kind == "combo":
            self._combo(w)
        elif kind == "view":
            self._view(w)
        elif kind == "tabs":
            w.setCurrentIndex(self.rng.randrange(max(1, w.count())))
        pump()
        self.close_popups()
        return what

    @staticmethod
    def _label(w: QWidget) -> str:
        for attr in ("text", "windowTitle", "placeholderText", "objectName"):
            try:
                t = getattr(w, attr)()
            except (AttributeError, TypeError):
                continue
            if t:
                return str(t)[:40]
        return ""

    def _type(self, w: QLineEdit) -> None:
        text = self._text()
        w.setFocus()
        r = self.rng.random()
        if r < 0.4 and len(text) < 40 and ascii_text(text):
            if self.rng.random() < 0.5:
                w.selectAll()
            QTest.keyClicks(w, text)
        elif r < 0.8:
            QApplication.clipboard().setText(text)
            w.selectAll()
            w.paste()
        else:
            w.clear()
        if self.rng.random() < 0.5:
            QTest.keyClick(w, Qt.Key.Key_Return)
        else:
            w.editingFinished.emit()

    def _spin(self, w: QAbstractSpinBox) -> None:
        r = self.rng.random()
        if isinstance(w, QSpinBox) and r < 0.6:
            w.setValue(self.rng.randint(w.minimum(), min(w.maximum(), w.minimum() + 60)))
        elif isinstance(w, QDateEdit) and r < 0.6:
            w.setDate(w.date().addDays(self.rng.randint(-400, 400)))
        else:
            edit = w.findChild(QLineEdit)
            if edit is not None:
                QApplication.clipboard().setText(self._text()[:60])
                edit.setFocus()
                edit.selectAll()
                edit.paste()
                QTest.keyClick(edit, Qt.Key.Key_Return)
        w.editingFinished.emit()

    def _combo(self, w: QComboBox) -> None:
        r = self.rng.random()
        if w.isEditable() and r < 0.3:
            edit = w.lineEdit()
            edit.setFocus()
            edit.selectAll()
            text = self._text()[:30]
            if ascii_text(text):
                QTest.keyClicks(edit, text)
            else:
                QApplication.clipboard().setText(text)
                edit.paste()
            if self.rng.random() < 0.5:
                QTest.keyClick(edit, Qt.Key.Key_Return)
            edit.editingFinished.emit()
            return
        if w.count() == 0:
            return
        i = self.rng.randrange(w.count())
        w.setCurrentIndex(i)
        w.activated.emit(i)
        w.textActivated.emit(w.itemText(i))

    def _view(self, w: QAbstractItemView) -> None:
        model = w.model()
        from PySide6.QtCore import QModelIndex

        rows = model.rowCount(QModelIndex())
        if rows <= 0:
            return
        r_ = self.rng.randrange(rows)
        try:
            cols = max(1, model.columnCount(QModelIndex()))
        except TypeError:
            cols = 1
        idx = model.index(r_, self.rng.randrange(cols))
        w.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
        pump()
        rect = w.visualRect(idx)
        port = w.viewport()
        if not rect.isValid() or not port.rect().contains(rect.center()):
            w.setCurrentIndex(idx)
            return
        at = rect.center()
        r = self.rng.random()
        if r < 0.5:
            QTest.mouseClick(port, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at)
        elif r < 0.65:
            QTest.mouseDClick(port, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at)
        elif r < 0.75:
            QApplication.postEvent(
                port, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, at, port.mapToGlobal(at))
            )
        elif r < 0.9 and (w.editTriggers() != QAbstractItemView.EditTrigger.NoEditTriggers):
            w.setCurrentIndex(idx)
            w.edit(idx)
            pump()
            editors = [e for e in port.findChildren(QLineEdit) if e.isVisible()]
            if editors:
                self._type(editors[-1])
        else:
            w.setCurrentIndex(idx)
            key = self.rng.choice(
                [
                    Qt.Key.Key_Delete,
                    Qt.Key.Key_Return,
                    Qt.Key.Key_Space,
                    Qt.Key.Key_Down,
                    Qt.Key.Key_A,
                    Qt.Key.Key_7,
                ]  # noqa: E501
            )
            QTest.keyClick(w, key)

    # ----- the main window's moves ------------------------------------------

    def moves(self) -> list[tuple[float, str, object]]:
        """What a person could do now, each as (weight, name, do)."""
        from test_design_walk import controls

        c = self.c
        win = c.main
        s = win.surface
        showing = win.showing()
        out: list[tuple[float, str, object]] = []
        surface_names = ("card", "button", "row dots", "header", "task dots")
        listed = controls(c)
        for name, press in listed:
            on_surface = name.startswith(surface_names)
            if on_surface and showing != "surface":
                continue
            if name.startswith("menu "):
                action = next(
                    (
                        a
                        for m in (win.file_menu, win.board_menu, win.help_menu)
                        for a in m.actions()
                        if f"menu {a.text()}" == name
                    ),  # noqa: E501
                    None,
                )
                if action is None or not action.isEnabled():
                    continue
                out.append((self._weight(name), name, press))
            elif name.startswith("display "):
                out.append((self._weight(name), name, press))
            elif name == "undo" and showing == "setup":
                continue
            elif name.startswith("switch ") and not win.program.mode.isEnabled():
                continue  # no event: the switch is off, and a person cannot press it
            else:
                out.append((self._weight(name), name, ("silence", press)))
        if showing == "surface" and c.live is not None:
            for card in s.cards.cards:
                if card.card.done:
                    # Silent by design, so not a silence press: the check
                    # below asks that it changed nothing at all.
                    name = f"card done {card.card.entry.names[0]}"
                    out.append((self._weight(name), name, self._done_press(card)))
        # Each kind of control shares one weight, so sixteen cards do not
        # crowd out the one Record Sprint.
        kinds: dict[str, int] = {}
        for _, name, _ in out:
            kinds[self._kind(name)] = kinds.get(self._kind(name), 0) + 1
        out = [(w / kinds[self._kind(name)], name, do) for w, name, do in out]
        if c.races:
            for race in self.rng.sample(c.races, min(2, len(c.races))):
                out.append(
                    (
                        0.4,
                        f"program select {race.name}",
                        lambda rid=race.race_id: win.program.select(rid),
                    )
                )  # noqa: E501
            out.append((0.3, "program list poke", lambda: self._view(win.program.list)))
        if showing == "surface" and c.live is not None:
            cards = s.cards.cards
            if cards:
                card = self.rng.choice(cards)
                label = card.card.entry.names[0]
                out.append(
                    (
                        1.2,
                        f"right-click card {label}",
                        lambda w=card: self._context(w, w.rect().center()),
                    )
                )  # noqa: E501
                out.append(
                    (
                        0.6,
                        f"double-click card {label}",
                        lambda w=card: double_click(w),
                    )
                )  # noqa: E501
                out.append(
                    (
                        0.8,
                        f"mouse-click card {label}",
                        lambda w=card: QTest.mouseClick(w, Qt.MouseButton.LeftButton),
                    )
                )  # noqa: E501
            t = s.table
            if t.rowCount():
                i = self.rng.randrange(t.rowCount())
                out.append((1.2, f"right-click row {i}", lambda i=i: self._context_row(i)))
                out.append((0.5, f"double-click row {i}", lambda i=i: self._dclick_row(i)))
            out.append(
                (
                    0.6,
                    "right-click task line",
                    lambda: self._context(s.task, s.task.rect().center()),
                )
            )  # noqa: E501
            out.append(
                (0.4, "right-click surface", lambda: self._context(s, QPoint(4, s.height() - 4)))
            )  # noqa: E501
            out.append(
                (
                    0.4,
                    "double-click undo",
                    lambda: double_click(win.undo),
                )
            )  # noqa: E501
            out.append(
                (
                    0.4,
                    "double-click record",
                    lambda: double_click(s.record_button) if s.record_button.isVisible() else None,
                )
            )  # noqa: E501
        if showing == "setup":
            out.append((6.0, "setup poke", lambda: self.fiddle(win.setup)))
        if showing == "empty":
            for b in (win.welcome_settings, win.welcome_riders, win.welcome_event):
                if b.isVisible() and b.isEnabled():
                    out.append((1.0, f"welcome {b.text()}", b.click))
        help_w = win.help_window
        if help_w is not None and help_w.isVisible():
            out.append((0.8, "help poke", lambda: self.fiddle(help_w)))
        keys = [
            (
                "Undo key",
                lambda t: QTest.keySequence(t, QKeySequence(QKeySequence.StandardKey.Undo)),
            ),  # noqa: E501
            (
                "Close key",
                lambda t: QTest.keySequence(t, QKeySequence(QKeySequence.StandardKey.Close)),
            ),  # noqa: E501
            ("F1", lambda t: QTest.keyClick(t, Qt.Key.Key_F1)),
            ("Escape", lambda t: QTest.keyClick(t, Qt.Key.Key_Escape)),
            ("Return", lambda t: QTest.keyClick(t, Qt.Key.Key_Return)),
            ("Space", lambda t: QTest.keyClick(t, Qt.Key.Key_Space)),
            ("Tab", lambda t: QTest.keyClick(t, Qt.Key.Key_Tab)),
            ("letters", lambda t: QTest.keyClicks(t, self.rng.choice(["a", "zq", "7", "Ab 3"]))),
        ]
        name, press = self.rng.choice(keys)
        out.append(
            (1.5, f"key {name}", lambda press=press: press(QApplication.focusWidget() or win))
        )  # noqa: E501
        w, h = self.rng.choice(SIZES)
        out.append((0.3, f"resize {w}x{h}", lambda: win.resize(w, h)))
        if self.fake_tv:
            out.append((0.15, "unplug fake TV", self._unplug))
        else:
            out.append((0.15, "plug fake TV", self._plug))
        if c.live is None:
            self._idle += 1
            if self._idle > 12:
                out.append((5.0, "open the demo copy", self._recover))
        else:
            self._idle = 0
        return out

    def _done_press(self, card):
        """A press on a done card, with what it must leave as it was."""

        def press():
            live = self.c.live
            eid = card.card.entrant_id
            # The refusal records nothing, so asking the controller first is safe.
            said = live.click(eid)
            self._done = (
                eid,
                said,
                len(live.store.actions(live.race_id)),
                self.c.store.get_setting(live._key),
                self.c.main.surface.problem.text(),
            )
            card.click()

        return press

    KIND_WEIGHTS = {
        "card done": 2.0,
        "card": 5.0,
        "card dots": 3.0,
        "card lap": 2.0,
        "button": 4.0,
        "row dots": 3.5,
        "header": 1.5,
        "task dots": 1.5,
        "undo": 1.5,
        "preview": 0.8,
        "switch": 1.5,
        "program row": 0.5,
        "menu": 6.0,
        "display": 0.8,
    }

    @staticmethod
    def _kind(name: str) -> str:
        for kind in (
            "card done",
            "card dots",
            "card lap",
            "card",
            "button",
            "row dots",
            "header",
            "task dots",
            "undo",
            "preview",
            "switch",
            "program row",
            "menu",
            "display",
        ):  # noqa: E501
            if name.startswith(kind):
                return kind
        return name

    def _weight(self, name: str) -> float:
        return self.KIND_WEIGHTS.get(self._kind(name), 1.0)

    def _context(self, w: QWidget, at: QPoint) -> None:
        QApplication.postEvent(
            w, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, at, w.mapToGlobal(at))
        )  # noqa: E501

    def _row_point(self, i: int):
        t = self.c.main.surface.table
        if i >= t.rowCount():
            return None
        idx = t.model().index(i, 1 if t.columnCount() > 1 else 0)
        t.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
        rect = t.visualRect(idx)
        return rect.center() if rect.isValid() else None

    def _context_row(self, i: int) -> None:
        at = self._row_point(i)
        if at is not None:
            self._context(self.c.main.surface.table.viewport(), at)

    def _dclick_row(self, i: int) -> None:
        at = self._row_point(i)
        if at is not None:
            port = self.c.main.surface.table.viewport()
            QTest.mouseDClick(port, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at)

    def _plug(self) -> None:
        self.fake_tv = True
        self.c._screen_added(QApplication.primaryScreen())

    def _unplug(self) -> None:
        self.fake_tv = False
        self.c._screen_removed(FakeScreen())

    def _recover(self) -> None:
        files = self.tmp / "files"
        target = files / f"recovered-{self.rng.randint(0, 9)}.sqlite"
        if not target.exists():
            shutil.copy(files / "copy.sqlite", target)
        self.c.open_data_file(path=target)

    # ----- the checks ------------------------------------------------------

    def fail(self, step: int, name: str, kind: str, what: str) -> None:
        n = self._seen_kinds.get(kind, 0)
        self._seen_kinds[kind] = n + 1
        if n >= 3:
            return  # the first few of a kind say it; the rest would be the same
        self.result.failures.append(Failure(self.seed, step, name, kind, what))
        if self.say:
            self.say(f"  FAIL seed {self.seed} step {step} [{name}] {kind}: {what}")

    def _new_log(self) -> str:
        from madtracker import applog

        applog.flush()
        path = applog.log_path()
        if path is None:
            return ""
        path = Path(path)
        if path != self._log_file:
            self._log_file, self._log_at = path, 0
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                f.seek(self._log_at)
                text = f.read()
                self._log_at = f.tell()
        except OSError:
            return ""
        return text

    def _open_stores(self) -> list[str]:
        from madtracker.store import Store

        out = []
        seen: set[int] = set()
        for obj in gc.get_objects():
            if isinstance(obj, Store):
                conn = obj._conn
            elif type(obj) is sqlite3.Connection:
                conn = obj
            else:
                continue
            if id(conn) in seen:
                continue
            seen.add(id(conn))
            try:
                rows = conn.execute("PRAGMA database_list").fetchall()
            except sqlite3.ProgrammingError:
                continue  # closed
            except sqlite3.Error as exc:
                out.append(f"unreadable connection {exc}")
                continue
            main = next((r[2] for r in rows if r[1] == "main"), "")
            out.append(main)
        return out

    def check(self, step: int, name: str, silence_press: bool, before) -> None:
        from test_design_walk import snapshot

        c = self.c
        win = c.main
        pump()
        for text in self.escaped:
            self.fail(step, name, "exception escaped", text)
        self.escaped.clear()
        for text in self.harness_errors:
            self.fail(step, name, "HARNESS error", text)
        self.harness_errors.clear()
        log = self._new_log()
        if "Unexpected error" in log or "Traceback" in log:
            at = log.find("Unexpected error")
            at = at if at >= 0 else log.find("Traceback")
            self.fail(step, name, "unexpected error logged", log[at : at + 2500])
        modal = QApplication.activeModalWidget()
        if modal is not None:
            self.fail(
                step, name, "modal left open", f"{type(modal).__name__} {modal.windowTitle()!r}"
            )  # noqa: E501
            modal.close()
        from madtracker.ui.help import HelpWindow

        for w in QApplication.topLevelWidgets():
            if not w.isVisible():
                continue
            if isinstance(w, (QDialog, QMessageBox)) and not isinstance(w, HelpWindow):
                self.fail(step, name, "dialog left open", f"{type(w).__name__} {w.windowTitle()!r}")
                w.close()
            elif isinstance(w, QMenu):
                self.fail(
                    step,
                    name,
                    "menu left open",
                    w.title() or ",".join(a.text() for a in w.actions()),
                )  # noqa: E501
                w.close()
        popup = QApplication.activePopupWidget()
        if popup is not None:
            self.fail(step, name, "popup left open", type(popup).__name__)
            self.close_popups()
        if not win.isVisible():
            self.fail(step, name, "window hidden", "the main window is not showing")
        showing = win.showing()
        if showing == "empty" and c.live is not None:
            self.fail(
                step, name, "empty with a live race", f"race {c.live.race_id} live, screen empty"
            )  # noqa: E501
        self._check_done_press(step, name)
        if c.store is not None and c.live is not None:
            if c.live.store is not c.store:
                self.fail(step, name, "live race on another store", repr(c.live.store))
            self._check_race(step, name, showing)
        self._check_count(step, name)
        if step % 10 == 0 or step == self.steps - 1:
            here = str(Path(c.data_path).resolve()) if c.store is not None else None
            stores = self._open_stores()
            others = [p for p in stores if not here or Path(p or "/").resolve() != Path(here)]
            if others or (here and len(stores) > 1):
                self.fail(step, name, "connection left open", f"open: {stores}, current {here}")
            if c.store is not None:
                # A file written over while open reads as damaged long before
                # a click trips on it; this names the step that did it.
                try:
                    said = [r[0] for r in c.store.connection.execute("PRAGMA quick_check")]
                except sqlite3.Error as exc:
                    said = [str(exc)]
                if said != ["ok"]:
                    self.fail(step, name, "open file damaged", f"{c.data_path}: {said[:3]}")
        size = rss()
        self.result.peak_rss = max(self.result.peak_rss, size)
        if size > RSS_CAP:
            self.fail(step, name, "memory", f"RSS {size / 1024**2:.0f} MB")
        if silence_press:
            after = snapshot(c)
            s = win.surface
            problem = s.problem.text() or s.flashing()
            # A preview with no race, or with the TV off, does nothing by design and says why in its tooltip.
            off_board = name == "preview" and not win.tv.property("active")
            if after == before and not self.opened and not problem and not off_board:
                self.fail(step, name, "silent", "the press changed nothing and said nothing")
            if "dots" in name and not any(
                o.startswith("menu:") and o != "menu:" for o in self.opened
            ):  # noqa: E501
                self.fail(step, name, "dots opened no menu", str(self.opened[:3]))

    def _check_done_press(self, step: int, name: str) -> None:
        """A done card's press did nothing: no log row, the staged row and the red line as they were."""
        probe, self._done = self._done, None
        if probe is None:
            return
        eid, said, rows, staged, line = probe
        c = self.c
        live = c.live
        if said.ok:
            self.fail(step, name, "done card took a click", f"#{eid}: {said!r}")
            return
        if live is None or c.store is None:
            return
        if len(live.store.actions(live.race_id)) != rows:
            self.fail(step, name, "done card press wrote to the log", f"#{eid}")
        if c.store.get_setting(live._key) != staged:
            self.fail(step, name, "done card press changed the staged row", f"#{eid}")
        shown = c.main.surface.problem.text()
        if shown != line:
            self.fail(step, name, "done card press changed the red line", f"{line!r} to {shown!r}")

    def _check_race(self, step: int, name: str, showing: str) -> None:
        from madtracker.scoring import compute_for_format

        c = self.c
        live = c.live
        try:
            fresh = live.screen()
        except Exception:  # the check reports, the app's own path decides
            self.fail(step, name, "screen raised", traceback.format_exc()[-1500:])
            return
        if fresh.cards:
            # The fixed grid: every entrant's card, in bib order, until review.
            ids = [k.entrant_id for k in fresh.cards]
            want = sorted(live.roster.ids, key=live._sort_key)
            if ids != want:
                self.fail(step, name, "cards are not the field in bib order", f"{ids} vs {want}")
        shown = c.main.surface.screen
        if showing == "surface" and shown is not None and shown != fresh:
            diff = [f for f in fresh.__dataclass_fields__ if getattr(fresh, f) != getattr(shown, f)]
            self.fail(step, name, "surface disagrees with the log", f"race {live.race_id}: {diff}")
        ids = [r.entrant_id for r in fresh.rows if r.entrant_id is not None]
        if len(ids) != len(set(ids)):
            self.fail(step, name, "entrant listed twice", f"race {live.race_id}: {ids}")
        try:
            st = compute_for_format(live.format_key, live.rules, live.roster.ids, live.actions())
        except Exception as exc:
            self.fail(step, name, "replay raised", f"{type(exc).__name__}: {exc}")
            return
        for row in fresh.rows:
            if row.entrant_id is None or row.staged:
                continue
            want = st.by_entrant(row.entrant_id)
            if want is None:
                self.fail(
                    step, name, "row for no entrant", f"race {live.race_id}: {row.entrant_id}"
                )
                continue
            if fresh.points and row.total is not None and row.total != int(want.total_points):
                self.fail(
                    step,
                    name,
                    "total disagrees",
                    f"race {live.race_id} #{row.entrant_id}: shown {row.total}, replay {want.total_points}",
                )  # noqa: E501
            if (
                not fresh.points
                and not row.status
                and want.rank is not None
                and row.place_text != str(want.rank)
            ):  # noqa: E501
                self.fail(
                    step,
                    name,
                    "place disagrees",
                    f"race {live.race_id} #{row.entrant_id}: shown {row.place_text}, replay {want.rank}",
                )  # noqa: E501
        stored = c.store.get_setting(live._key)
        if stored is None:
            if live._staged.groups or live._staged.tail:
                self.fail(
                    step, name, "staged not stored", f"race {live.race_id}: {live._staged.groups}"
                )  # noqa: E501
        elif isinstance(stored, dict) and stored.get("format", live.format_key) == live.format_key:
            mine = live._staged.to_json()
            for key in ("groups", "tail"):
                if key in mine and stored.get(key) != mine[key]:
                    self.fail(
                        step,
                        name,
                        "staged row differs",
                        f"race {live.race_id} {key}: stored {stored.get(key)}, live {mine[key]}",
                    )  # noqa: E501

    def _check_count(self, step: int, name: str) -> None:
        c = self.c
        if c.store is None:
            self._count_store = None
            return
        try:
            n = c.store.connection.execute("SELECT COUNT(*) FROM race_action").fetchone()[0]
        except sqlite3.Error as exc:
            self.fail(step, name, "count unreadable", str(exc))
            return
        if c.store is self._count_store and n < self._count:
            self.fail(step, name, "race_action shrank", f"{self._count} -> {n}")
        self._count_store, self._count = c.store, n

    # ----- the run ---------------------------------------------------------

    def pick(self, moves):
        total = sum(w for w, _, _ in moves)
        r = self.rng.random() * total
        for w, name, do in moves:
            r -= w
            if r <= 0:
                return name, do
        return moves[-1][1], moves[-1][2]

    def run(self) -> Result:
        from test_design_walk import snapshot

        self.build()
        self._new_log()
        if self.escaped:
            for text in self.escaped:
                self.fail(-1, "build", "exception escaped", text)
            self.escaped.clear()
        for step in range(self.steps):
            moves = self.moves()
            name, do = self.pick(moves)
            silence = isinstance(do, tuple)
            press = do[1] if silence else do
            self.opened = []
            before = snapshot(self.c) if silence else None
            if self.trail_file is not None:
                with open(self.trail_file, "a", encoding="utf-8") as f:
                    f.write(f"{step:4d} > {name}\n")
            try:
                press()
            except Exception:
                self.fail(step, name, "HARNESS press raised", tail(traceback.format_exc()))
            self.check(step, name, silence, before)
            line = f"{step:4d} {name}" + (
                f"  <- {'; '.join(self.opened)[:3000]}" if self.opened else ""
            )  # noqa: E501
            self.result.trail.append(line)
            if self.trail_file is not None:
                with open(self.trail_file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            if self.say and os.environ.get("MONKEY_VERBOSE"):
                self.say(line)
        return self.result

    def dispose(self) -> None:
        from apps import dispose_app

        try:
            dispose_app(self.c)
        except Exception:
            self.fail(self.steps, "dispose", "dispose raised", traceback.format_exc()[-1500:])
        pump()
