"""About MadTracker: who made it, where it lives, its license, and what it is built with.

The program ships as a binary that carries other people's work, so the
About box owes each of them a credit, a version and the license text.
The versions are read from the running program rather than typed in,
so the box cannot drift from what was actually bundled; a component
that is not installed (PyObjC off macOS) is left out rather than shown
as missing. The license texts are files under
``madtracker/assets/licenses/`` (and Inter's beside the fonts), so the
same text travels in the repository, the wheel and the bundle.
"""

import importlib.util
import platform
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from madtracker import APP_NAME, __version__
from madtracker.ui import style
from madtracker.ui.look import DIALOG_BASE_PT
from madtracker.ui.widgets import (
    apply_style,
    button_row,
    center_on_parent,
    close_on_shortcut,
    fit_to_screen,
    run_dialog,
    screen_room,
    setup_table,
)

AUTHOR_URL = "https://nuxx.net"
PROJECT_URL = "https://github.com/c0nsumer/madtracker"
COPYRIGHT = "Copyright (c) 2026 Steve Vigneau."
# The app cites the USA Cycling Rulebook and writes its upload format;
# this says once that it is not theirs.
NOT_USAC = f"{APP_NAME} is not a USA Cycling product and is not endorsed by USA Cycling."

# Links inside the box that open a license text rather than a web page.
LICENSE_SCHEME = "license"
KEY_ROLE = Qt.ItemDataRole.UserRole
# The fewest component rows About keeps on a short screen before its table scrolls.
ABOUT_MIN_ROWS = 3


@dataclass(frozen=True)
class LicenseText:
    key: str
    name: str
    path: tuple[str, ...]  # under madtracker/assets

    def read(self) -> str:
        return files("madtracker.assets").joinpath(*self.path).read_text(encoding="utf-8")


# In the Licenses dialog's order: the program's own first, then the rest.
LICENSES: dict[str, LicenseText] = {
    lic.key: lic
    for lic in (
        LicenseText("madtracker", f"{APP_NAME} (MIT License)", ("licenses", "MadTracker-MIT.txt")),
        LicenseText("lgpl-3.0", "GNU LGPL v3.0", ("licenses", "LGPL-3.0.txt")),
        # The LGPL is a set of permissions added to the GPL, so it is
        # not complete without the GPL's text.
        LicenseText("gpl-3.0", "GNU GPL v3.0", ("licenses", "GPL-3.0.txt")),
        LicenseText("apache-2.0", "Apache License 2.0", ("licenses", "Apache-2.0.txt")),
        LicenseText("harfbuzz", "HarfBuzz (Old MIT)", ("licenses", "HarfBuzz.txt")),
        LicenseText("fonttools", "fontTools (MIT)", ("licenses", "fontTools-MIT.txt")),
        LicenseText("pillow", "Pillow (MIT-CMU)", ("licenses", "Pillow.txt")),
        LicenseText("defusedxml", "defusedxml (PSF-2.0)", ("licenses", "defusedxml-PSF-2.0.txt")),
        LicenseText("python", "Python (PSF License)", ("licenses", "Python.txt")),
        LicenseText(
            "pictogrammers", "Pictogrammers Free License", ("licenses", "Pictogrammers.txt")
        ),
        LicenseText("ofl-1.1", "SIL Open Font License 1.1", ("fonts", "LICENSE-Inter.txt")),
        LicenseText("pyobjc", "PyObjC (MIT)", ("licenses", "PyObjC-MIT.txt")),
    )
}


@dataclass(frozen=True)
class Component:
    name: str
    url: str
    version: str
    license: str
    license_key: str
    # The Python distributions this row credits, so a test can hold the
    # table to pyproject's dependency list.
    dists: tuple[str, ...] = ()
    # Where its source is: the LGPL (through GPL section 6) asks for this
    # beside a library shipped in compiled form.
    source: str = ""


def _dist_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _inter_version() -> str:
    """The version in Inter's name table ("Version 4.001;git-...") as "4.001"."""
    from fontTools.ttLib import TTFont

    from madtracker.assets import fonts

    with TTFont(fonts.font_path(400), lazy=True) as font:
        text = font["name"].getDebugName(5) or ""
    return text.removeprefix("Version ").split(";")[0].strip()


def components() -> list[Component]:
    """Every third-party component in the program, as installed right now."""
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion

    out = [
        Component(
            "Python", "https://www.python.org", platform.python_version(), "PSF License", "python"
        ),
        Component(
            "Qt",
            "https://www.qt.io",
            qVersion(),
            "LGPL-3.0",
            "lgpl-3.0",
            source="https://download.qt.io/archive/qt/",
        ),
        Component(
            "PySide6 and shiboken6",
            "https://doc.qt.io/qtforpython-6/",
            pyside_version,
            "LGPL-3.0",
            "lgpl-3.0",
            ("PySide6", "PySide6-Essentials", "shiboken6"),
            "https://code.qt.io/cgit/pyside/pyside-setup.git/",
        ),
    ]
    for name, url, dist, lic, key, source in (
        (
            "fpdf2",
            "https://py-pdf.github.io/fpdf2/",
            "fpdf2",
            "LGPL-3.0",
            "lgpl-3.0",
            "https://github.com/py-pdf/fpdf2",
        ),
        (
            "uharfbuzz",
            "https://github.com/harfbuzz/uharfbuzz",
            "uharfbuzz",
            "Apache License 2.0",
            "apache-2.0",
            "",
        ),
    ):
        v = _dist_version(dist)
        if v:
            out.append(Component(name, url, v, lic, key, (dist,), source))
    if importlib.util.find_spec("uharfbuzz") is not None:
        import uharfbuzz

        # uharfbuzz carries its own build of HarfBuzz, which has its own license.
        out.append(
            Component(
                "HarfBuzz",
                "https://harfbuzz.github.io/",
                uharfbuzz.version_string(),
                "Old MIT",
                "harfbuzz",
            )
        )
    for name, url, dist, lic, key in (
        ("fontTools", "https://github.com/fonttools/fonttools", "fonttools", "MIT", "fonttools"),
        ("Pillow", "https://python-pillow.github.io/", "pillow", "MIT-CMU", "pillow"),
        (
            "defusedxml",
            "https://github.com/tiran/defusedxml",
            "defusedxml",
            "PSF-2.0",
            "defusedxml",
        ),
    ):
        v = _dist_version(dist)
        if v:
            out.append(Component(name, url, v, lic, key, (dist,)))
    out.append(
        Component(
            "Material Design Icons by the Pictogrammers",
            "https://pictogrammers.com/library/mdi/",
            # The icons are single upstream SVG files with no release
            # number in them, so there is no version to read.
            "",
            "Pictogrammers Free License",
            "pictogrammers",
        )
    )
    out.append(
        Component(
            "Inter by Rasmus Andersson",
            "https://rsms.me/inter/",
            _inter_version(),
            "SIL OFL 1.1",
            "ofl-1.1",
        )
    )
    if importlib.util.find_spec("objc") is not None:
        v = _dist_version("pyobjc-core")
        if v:
            out.append(
                Component(
                    "PyObjC",
                    "https://pyobjc.readthedocs.io/",
                    v,
                    "MIT",
                    "pyobjc",
                    ("pyobjc-core", "pyobjc-framework-Cocoa"),
                )
            )
    return out


def license_keys(shown: list[Component]) -> list[str]:
    """The licenses that apply to this copy, in LICENSES order.

    The program's own and the GPL (which the LGPL is written against) are
    always there; any other only when a component shown uses it.
    """
    used = {"madtracker", "gpl-3.0"} | {c.license_key for c in shown}
    return [key for key in LICENSES if key in used]


def _link(href: str, text: str) -> str:
    return f'<a href="{href}">{text}</a>'


def _license_link(key: str, text: str) -> str:
    return _link(f"{LICENSE_SCHEME}:{key}", text)


def _rich_label(html: str) -> QLabel:
    label = QLabel(html)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setWordWrap(True)
    # Links reachable with Tab and Enter as well as the mouse.
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    label.setOpenExternalLinks(False)
    return label


def outlined(close: QPushButton) -> None:
    """Close outlined, as in every other window.

    Filled marks the action that changes something; Close changes
    nothing, so it keeps the plain face. It stays the default button, so
    Enter still closes.
    """
    close.setObjectName("")


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        apply_style(self)
        close_on_shortcut(self)
        self.components = components()

        icon = QLabel()
        icon_px = 64
        pix = QPixmap(str(files("madtracker.assets").joinpath("icons", "madtracker-128.png")))
        # The 128 pixel file drawn at 64: sharp on a 2x screen, scaled down cleanly at 1x.
        pix.setDevicePixelRatio(pix.width() / icon_px if pix.width() else 1.0)
        icon.setPixmap(pix)
        icon.setFixedSize(QSize(icon_px, icon_px))
        title = QLabel(
            f'<span style="font-size: {style.ui_font(20).pointSizeF():g}pt; font-weight: 700;">'
            f"{APP_NAME}</span>&nbsp;&nbsp;"
            f'<span style="color: #5b6472;">Version {__version__}</span>'
        )
        title.setTextFormat(Qt.TextFormat.RichText)
        tagline = QLabel("Scoring for track cycling events.")
        heading = QVBoxLayout()
        heading.setSpacing(style.XS)
        heading.addWidget(title)
        heading.addWidget(tagline)
        top = QHBoxLayout()
        top.setSpacing(style.MD)
        top.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addLayout(heading, 1)
        top.setAlignment(heading, Qt.AlignmentFlag.AlignVCenter)

        self.author = _rich_label(f"Developed by Steve Vigneau ({_link(AUTHOR_URL, 'nuxx.net')})")
        project = PROJECT_URL.removeprefix("https://")
        self.project = _rich_label(f"Project: {_link(PROJECT_URL, project)}")
        self.license = _rich_label(
            f"{APP_NAME} is free software under the "
            f"{_license_link('madtracker', 'MIT License')}. {COPYRIGHT}"
        )

        built = QLabel("Built With")
        built.setFont(style.ui_font(11, bold=True))
        self.table = self._build_table()
        for label in (self.author, self.project, self.license):
            label.linkActivated.connect(self.open_link)
        self.usac = _rich_label(NOT_USAC)

        buttons, found = button_row("Close", self.accept)
        self.close_button = found["primary"]
        outlined(self.close_button)
        self.licenses_button = QPushButton("Licenses...")
        self.licenses_button.setMinimumWidth(self.close_button.minimumWidth())
        self.licenses_button.clicked.connect(lambda: self.show_licenses())
        buttons.insertWidget(0, self.licenses_button)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(style.XL, style.XL, style.XL, style.LG)
        lay.setSpacing(style.SM)
        lay.addLayout(top)
        lay.addSpacing(style.MD)
        lay.addWidget(self.author)
        lay.addWidget(self.project)
        lay.addWidget(self.license)
        lay.addWidget(self.usac)
        lay.addSpacing(style.MD)
        lay.addWidget(built)
        lay.addWidget(self.table)
        lay.addSpacing(style.SM)
        lay.addLayout(buttons)
        fit_to_screen(self, 760, 0)
        self._fitted = False
        self.close_button.setFocus()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._fitted:
            self._fitted = True
            self._fit_table()
            # The wrapped paragraphs are as tall as this width makes them.
            want = self.layout().totalHeightForWidth(self.width())
            room = screen_room(self)
            if room is not None and want > room.height():
                # A short screen: the table gives up rows and scrolls.
                t = self.table
                t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                t.setFixedHeight(max(self._table_floor, t.height() - (want - room.height())))
                want = self.layout().totalHeightForWidth(self.width())
            fit_to_screen(self, self.width(), want)
            # Once, at its final size: in the middle of the window, not low.
            center_on_parent(self)

    def _fit_table(self) -> None:
        """Size the narrow columns to their widest cell and the table to its rows.

        ResizeToContents measures item text, and every cell here is a
        label widget, so the widths are taken from the labels once they
        carry the style sheet's font. The whole table shows without
        scrolling where the screen has the room; on a short one (1366 by
        768 at 125%) it keeps a few rows and scrolls, so Close stays on
        the screen.
        """
        t = self.table
        header = t.horizontalHeader()
        for col in (1, 2):
            widest = max(
                [header.sectionSizeHint(col)]
                + [t.cellWidget(r, col).sizeHint().width() for r in range(t.rowCount())]
            )
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(col, widest + style.XL)
        rows = [t.rowHeight(r) for r in range(t.rowCount())]
        chrome = header.height() + 2 * t.frameWidth()
        t.setFixedHeight(chrome + sum(rows))
        self._table_floor = chrome + sum(rows[:ABOUT_MIN_ROWS])

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(len(self.components), 3)
        setup_table(table, ["Component", "Version", "License"], selectable=False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        row_h = style.control_height(DIALOG_BASE_PT, 1.6)
        table.verticalHeader().setDefaultSectionSize(row_h)
        for row, c in enumerate(self.components):
            name = _rich_label(_link(c.url, c.name))
            name.setWordWrap(False)
            name.setToolTip(c.url)
            ver = QLabel(c.version)
            text = _license_link(c.license_key, c.license)
            if c.source:
                text += f" ({_link(c.source, 'source')})"
            lic = _rich_label(text)
            lic.setWordWrap(False)
            for col, label in enumerate((name, ver, lic)):
                label.setContentsMargins(style.SM, 0, style.SM, 0)
                label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                table.setCellWidget(row, col, label)
            name.linkActivated.connect(self.open_link)
            lic.linkActivated.connect(self.open_link)
        return table

    def open_link(self, href: str) -> None:
        """A license link opens its text here; any other link opens in the browser."""
        url = QUrl(href)
        if url.scheme() == LICENSE_SCHEME:
            self.show_licenses(url.path())
        else:
            QDesktopServices.openUrl(url)

    def show_licenses(self, key: str = "madtracker") -> None:
        run_dialog(LicensesDialog(self, key, license_keys(self.components)))


class LicensesDialog(QDialog):
    """Every bundled license text: the list on the left, the text on the right."""

    def __init__(
        self,
        parent: QWidget | None = None,
        key: str = "madtracker",
        keys: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Licenses")
        apply_style(self)
        close_on_shortcut(self)
        self.contents = QListWidget()
        keys = license_keys(components()) if keys is None else keys
        for lic in (LICENSES[k] for k in keys):
            item = QListWidgetItem(lic.name)
            item.setData(KEY_ROLE, lic.key)
            self.contents.addItem(item)
        width = self.contents.sizeHintForColumn(0) + 2 * style.LG
        self.contents.setFixedWidth(width)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        # A license keeps its own line breaks; wrapped again to the pane it
        # reads as ragged half-lines.
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # Read-only text still takes focus so the keyboard can scroll it.
        self.text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.contents.currentRowChanged.connect(self._row_changed)
        body = QHBoxLayout()
        body.setSpacing(style.MD)
        body.addWidget(self.contents)
        body.addWidget(self.text, 1)
        buttons, found = button_row("Close", self.accept)
        self.close_button = found["primary"]
        outlined(self.close_button)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(style.LG, style.LG, style.LG, style.LG)
        lay.setSpacing(style.MD)
        lay.addLayout(body, 1)
        lay.addLayout(buttons)
        fit_to_screen(self, 940, 640)
        self.show_key(key)
        self.contents.setFocus()

    def _row_changed(self, row: int) -> None:
        item = self.contents.item(row)
        if item is None:
            return
        lic = LICENSES[item.data(KEY_ROLE)]
        try:
            self.text.setPlainText(lic.read())
        except OSError as exc:
            self.text.setPlainText(f"The {lic.name} text could not be read: {exc}")

    def show_key(self, key: str) -> None:
        for i in range(self.contents.count()):
            if self.contents.item(i).data(KEY_ROLE) == key:
                self.contents.setCurrentRow(i)
                return
        self.contents.setCurrentRow(0)

    def current_key(self) -> str | None:
        item = self.contents.currentItem()
        return None if item is None else item.data(KEY_ROLE)
