"""Material Design Icons for the operator window, and message boxes that use them.

Qt's stock icons (the QMessageBox question mark, the QStyle standard
pixmaps) look different on every platform and dated on all of them. The
app icon is already a Material Design Icons glyph, so the interface uses
the same family: the few SVGs it needs are bundled under
``madtracker/assets/icons/mdi/`` and rendered here at the size and color
each use asks for.

The upstream files carry no fill, which renders black; the fill is
injected into the SVG text before rendering (as tools/make_icons.py does
for the app icon), so one file serves every tint without editing it.
"""

import os
import stat
import tempfile
from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from madtracker.ui import style
from madtracker.ui.widgets import run_dialog

INK = "#2a313b"
WARN = "#b25e00"
# Which glyph and color each kind of message box shows.
BOX_ICONS = {
    "question": ("help-circle-outline", style.ACCENT),
    "warning": ("alert-outline", WARN),
    "information": ("information-outline", style.ACCENT),
}
BOX_ICON_SIZE = 48

_svg_text: dict[str, str] = {}
_pixmaps: dict[tuple[str, int, str, float], QPixmap] = {}
_icon_dir: Path | None = None


def svg_path(name: str):
    """The bundled SVG for ``name``; importlib.resources keeps this right in a bundle."""
    return files("madtracker.assets").joinpath("icons", "mdi", f"{name}.svg")


def _svg(name: str, color: str) -> bytes:
    if name not in _svg_text:
        _svg_text[name] = svg_path(name).read_text(encoding="utf-8")
    return _svg_text[name].replace("<path ", f'<path fill="{color}" ').encode("utf-8")


def svg_file(name: str, color: str | None = None) -> Path:
    """A tinted copy of the glyph on disk, for a style sheet's ``url()``.

    A style sheet draws a combo box's arrow only from an image file, and
    the bundled glyphs carry no fill, so the tinted copy is written once
    per color to this user's icon folder and its path handed to the sheet.
    """
    color = color or INK
    path = icon_dir() / f"{name}-{color.lstrip('#')}.svg"
    if not path.is_file():
        path.write_bytes(_svg(name, color))
    return path


def icon_dir() -> Path:
    """The folder of tinted glyphs, this user's own.

    The temp folder is shared between users on Linux, so the folder
    carries the user id where the platform has one, and a folder of that
    name that another user made (or that is not a folder) is passed over
    for a fresh private one. Windows and macOS give each user their own
    temp folder.
    """
    global _icon_dir
    if _icon_dir is None:
        getuid = getattr(os, "getuid", None)
        uid = getuid() if getuid else None
        folder = Path(tempfile.gettempdir()) / (
            "madtracker-icons" if uid is None else f"madtracker-icons-{uid}"
        )
        try:
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = folder.lstat()
            if not stat.S_ISDIR(info.st_mode) or (uid is not None and info.st_uid != uid):
                raise PermissionError(f"{folder} is not this user's folder")
        except OSError:
            folder = Path(tempfile.mkdtemp(prefix="madtracker-icons-"))
        _icon_dir = folder
    return _icon_dir


def mdi_pixmap(name: str, size: int, color: str | None = None, dpr: float = 1.0) -> QPixmap:
    """``name`` rendered ``size`` pixels square in ``color``, cached.

    ``dpr`` renders extra pixels for a high-density screen, so a glyph
    stays sharp on a 150% Windows laptop panel.
    """
    from PySide6.QtSvg import QSvgRenderer

    color = color or INK
    key = (name, size, color, dpr)
    pix = _pixmaps.get(key)
    if pix is None:
        renderer = QSvgRenderer(QByteArray(_svg(name, color)))
        if not renderer.isValid():
            raise FileNotFoundError(f"no usable icon {name!r} at {svg_path(name)}")
        side = max(1, round(size * dpr))
        pix = QPixmap(side, side)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, side, side))
        painter.end()
        pix.setDevicePixelRatio(dpr)
        _pixmaps[key] = pix
    return pix


def mdi(name: str, size: int = 24, color: str | None = None) -> QIcon:
    """An icon for a button or a menu action.

    The normal and the high-density renders are both added, and Qt picks
    the one the screen needs. A disabled state is rendered dim by hand,
    since Fusion's own dimming of a colored glyph reads as a smudge.
    """
    icon = QIcon()
    for dpr in (1.0, 2.0):
        icon.addPixmap(mdi_pixmap(name, size, color, dpr), QIcon.Mode.Normal)
        icon.addPixmap(mdi_pixmap(name, size, "#9aa1ad", dpr), QIcon.Mode.Disabled)
    return icon


# A button's icon beside its text. Qt draws them 4 px apart, and with the
# glyph's own margin the icon would all but touch the word; the icon carries
# one step of the spacing scale as clear space on its right, so every
# icon button has the same gap of about SM.
BUTTON_ICON_PX = 16
BUTTON_ICON_GAP = style.XS


def set_button_icon(
    button: QAbstractButton,
    name: str,
    color: str | None = None,
    size: int = BUTTON_ICON_PX,
    lift: int = 0,
) -> None:
    """Put ``name`` on a text button, ``BUTTON_ICON_GAP`` clear of its text.

    ``lift`` raises a glyph whose ink sits low in its square (the undo
    arrow) onto the middle of the text beside it.
    """
    icon = QIcon()
    for dpr in (1.0, 2.0):
        for mode, tint in ((QIcon.Mode.Normal, color), (QIcon.Mode.Disabled, "#9aa1ad")):
            glyph = mdi_pixmap(name, size, tint, dpr)
            pix = QPixmap(round((size + BUTTON_ICON_GAP) * dpr), round(size * dpr))
            # Set before painting, so the painter works in the same
            # logical pixels as the glyph's own ratio.
            pix.setDevicePixelRatio(dpr)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            painter.drawPixmap(0, -lift, glyph)
            painter.end()
            icon.addPixmap(pix, mode)
    button.setIcon(icon)
    button.setIconSize(QSize(size + BUTTON_ICON_GAP, size))


def message_box(
    parent: QWidget | None,
    kind: str,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    default: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
) -> QMessageBox:
    """A message box with an MDI glyph in place of Qt's stock icon.

    ``kind`` is question, warning or information. Use this, never the
    QMessageBox static helpers, which always show the stock icon; a test
    scans the UI for them.
    """
    name, color = BOX_ICONS[kind]
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(buttons)
    if default != QMessageBox.StandardButton.NoButton:
        box.setDefaultButton(default)
    dpr = parent.devicePixelRatioF() if parent is not None else 1.0
    box.setIconPixmap(mdi_pixmap(name, BOX_ICON_SIZE, color, dpr))
    # The dialogs' margins and the gap above the buttons, from the one
    # spacing scale; Qt's own left the text and the buttons tight against
    # the frame. The gap beside the glyph stays Qt's: the box's width is
    # Qt's, and a wider gap would only wrap the question onto more lines.
    # Set after the pixmap, since setting one lays the box out afresh.
    lay = box.layout()
    if isinstance(lay, QGridLayout):
        lay.setContentsMargins(style.LG, style.LG, style.LG, style.LG)
        lay.setVerticalSpacing(style.MD)
    _fit_paths(box, text)
    return box


def _fit_paths(box: QMessageBox, text: str) -> None:
    """Widen the text to a path on a line of its own, so it is not broken.

    A path has no spaces to wrap at, and in a box at Qt's own width it
    breaks after "C:". A line with no space is taken for a path. The box
    grows to it, up to the width Qt lets a message box have on this
    screen; a path wider still may break after a folder separator,
    never inside a name.
    """
    lines = text.splitlines()
    paths = [line for line in lines if line and " " not in line]
    label = box.findChild(QLabel, "qt_msgbox_label")
    if not paths or label is None:
        return
    screen = box.screen() or QGuiApplication.primaryScreen()
    width = screen.availableGeometry().width() if screen is not None else 1024
    # QMessageBox's own ceiling (qmessagebox.cpp, updateSize), less the
    # glyph and the margins beside the text.
    cap = (width if width <= 1024 else min(width - 480, 1000)) - BOX_ICON_SIZE - 64
    # The style sheet's text can be a size above the label's own font.
    widest = round(max(label.fontMetrics().horizontalAdvance(p) for p in paths) * 1.1)
    label.setMinimumWidth(min(widest, cap))
    if widest > cap:
        breakable = [
            line.replace("\\", "\\\u200b").replace("/", "/\u200b") if line in paths else line
            for line in lines
        ]
        box.setText("\n".join(breakable))


def ask(parent: QWidget | None, title: str, text: str, verb: str = "OK") -> bool:
    """A question answered by its verb or Cancel; True for the verb.

    The buttons are [Cancel] [verb], the verb rightmost and filled, the
    same order as every dialog's (widgets.button_row), so the answer is
    the word on the button rather than a Yes that means whatever the
    question said. Enter and Escape both cancel.
    """
    box = message_box(parent, "question", title, text, QMessageBox.StandardButton.NoButton)
    # GnomeLayout: reject left of accept on every platform.
    box.setStyleSheet("QDialogButtonBox { button-layout: 3; }")
    cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    yes = box.addButton(verb, QMessageBox.ButtonRole.AcceptRole)
    yes.setObjectName("primary")
    # The button box polished the button when it was added; the style
    # sheet's #primary rule reaches it only on a fresh polish.
    yes.style().unpolish(yes)
    yes.style().polish(yes)
    # Cancel is the default: a question exists to catch a stray click, and
    # a stray Enter must not answer it. The verb stays the filled button,
    # one Tab or a click away. Escape cancels too.
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    cancel.setFocus()
    run_dialog(box)
    return box.clickedButton() is yes


def choose(
    parent: QWidget | None,
    title: str,
    text: str,
    verbs: list[str],
    primary: str,
    disabled: tuple[str, ...] = (),
) -> str | None:
    """A question with more than one answer: the verb chosen, or None for Cancel.

    Laid out as ask() is, [Cancel] then the verbs in order with
    ``primary`` filled and rightmost; a verb in ``disabled`` is grayed,
    still there to show what the question can offer. Cancel is the
    default, so Enter and Escape both cancel.
    """
    box = message_box(parent, "question", title, text, QMessageBox.StandardButton.NoButton)
    box.setStyleSheet("QDialogButtonBox { button-layout: 3; }")
    cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    buttons = {}
    # GnomeLayout sets Reject, then Accept in reverse order of adding,
    # then Yes: the other verbs are added last first, and the primary
    # alone is Yes, so the row reads Cancel, the verbs in order, primary.
    for verb in reversed([v for v in verbs if v != primary]):
        buttons[verb] = box.addButton(verb, QMessageBox.ButtonRole.AcceptRole)
    buttons[primary] = box.addButton(primary, QMessageBox.ButtonRole.YesRole)
    for verb, button in buttons.items():
        button.setEnabled(verb not in disabled)
    buttons[primary].setObjectName("primary")
    buttons[primary].style().unpolish(buttons[primary])
    buttons[primary].style().polish(buttons[primary])
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    cancel.setFocus()
    run_dialog(box)
    clicked = box.clickedButton()
    return next((verb for verb, b in buttons.items() if b is clicked), None)


def warn(parent: QWidget | None, title: str, text: str, name: str = "") -> None:
    """A warning box; ``name`` is its object name, for a caller that must find it again."""
    box = message_box(parent, "warning", title, text)
    if name:
        box.setObjectName(name)
    run_dialog(box)


def inform(
    parent: QWidget | None,
    title: str,
    text: str,
    chars: int = 0,
    copy: str | None = None,
    rich: bool = False,
) -> None:
    """``chars`` widens the text to that many average characters: Qt keeps a
    message box narrow, which wraps a table's cells one word per line.

    ``rich`` draws ``text`` as HTML, for a report built as one with every
    name escaped; every other box shows its text as typed.

    ``copy`` adds a Copy Details to Clipboard button left of OK that puts
    that text on the clipboard, for a report the scorer keeps or passes
    on. A message box closes on any button of its own row, so this one
    sits in a strip beside that row: the box stays up and the button
    says Copied to Clipboard in place.
    """
    box = message_box(parent, "information", title, text)
    if rich:
        box.setTextFormat(Qt.TextFormat.RichText)
    if chars:
        label = box.findChild(QLabel, "qt_msgbox_label")
        if label is not None:
            label.setMinimumWidth(label.fontMetrics().averageCharWidth() * chars)
    if copy is not None:
        _copy_strip(box, copy)
    run_dialog(box)


COPY_DETAILS = "Copy Details to Clipboard"
COPIED = "Copied to Clipboard"


def _copy_strip(box: QMessageBox, text: str) -> QPushButton:
    """The copy button beside the box's own buttons, left, outside their row."""
    grid = box.layout()
    row_box = box.findChild(QDialogButtonBox)
    at = grid.getItemPosition(grid.indexOf(row_box))
    grid.removeWidget(row_box)
    strip = QWidget(box)
    lay = QHBoxLayout(strip)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(style.SM)
    button = QPushButton(COPY_DETAILS, strip)
    button.setObjectName("copyDetails")
    lay.addWidget(button)
    lay.addStretch(1)
    lay.addWidget(row_box)
    grid.addWidget(strip, *at)

    def copy_it() -> None:
        QGuiApplication.clipboard().setText(text)
        button.setText(COPIED)

    button.clicked.connect(copy_it)
    box.setDefaultButton(QMessageBox.StandardButton.Ok)
    return button
