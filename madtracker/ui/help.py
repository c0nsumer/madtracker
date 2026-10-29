"""Built-in help: the scorer's pages, rendered from their Markdown.

One window for the scorer's pages (design section 5), with a contents
list on the left. The rule register (docs/scoring-rules.md) and the
installing page are not among them: the first is written for officials
and developers, and the second is for whoever sets up the laptop,
before the app can show it. The pages are the files in
``madtracker/help/``, kept apart from the repository's ``docs/``: those
are for developers and whoever installs, at their length, and an edit
made for them must not change what the scorer reads.
A page links only to another page, since nothing else ships. A page
whose file is missing is left out of the list rather than shown empty.
The pages link into each other's sections, so the window keeps a
history of the places visited and Back and Forward step through it, as
a browser does: Qt's own history in the text browser is empty, since
the pages are set as Markdown and not loaded from a URL.
"""

import html
import re
from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QKeySequence,
    QPalette,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFrameFormat,
    QTextImageFormat,
    QTextLength,
    QTextTable,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from madtracker import APP_NAME
from madtracker.ui import style
from madtracker.ui.icons import WARN, mdi, mdi_pixmap
from madtracker.ui.look import text_scale
from madtracker.ui.widgets import close_on_shortcut, fit_to_screen

# (key, title, file name under docs/), in the Help menu's order. Each
# title is the page's own H1 and the text of every link to it, so a page
# has one name in the app and on GitHub.
PAGES: tuple[tuple[str, str, str], ...] = (
    ("start", "Getting Started", "getting-started.md"),
    ("scoring", "Scoring", "scoring.md"),
    ("results", "Results", "results.md"),
    ("multi_race", "Multi-Race Standings", "multi-race-standings.md"),
    ("backups", "Backups", "backups.md"),
)
# What F1 opens from each of the main window's screens: (page, section).
# A section renamed in its page falls back to the page's top.
HELP_HERE: dict[str, tuple[str, str | None]] = {
    "empty": ("start", None),
    "setup": ("start", "The event"),
    "surface": ("start", "Scoring a race"),
    # The File menu's Multi-Race Standings dialog, which opens its own help.
    "standings": ("multi_race", None),
}
KEY_ROLE = Qt.ItemDataRole.UserRole
SECTION_ROLE = Qt.ItemDataRole.UserRole + 1
# Wide enough for "Rules shared by every format" under its page.
CONTENTS_W = 290
# Back and Forward: a glyph alone, as a browser's, square at the
# dialogs' control height.
NAV_ICON_PX = 20
NAV_WORDS = {"back": "Back", "forward": "Forward"}

# The page's look, laid on the document Qt builds from the Markdown, so
# the files stay plain Markdown and nothing new ships. Qt's own rendering
# puts the text against the frame in long lines with cramped headings.
BODY_PT = 12
H1_PT = 24
H2_PT = 16
LINE_HEIGHT = 140  # percent
# The page's room on every side, inside the scroll bar.
PAGE_MARGIN = 32
# The longest line, in pixels: about 80 characters at BODY_PT, which a
# maximized window would otherwise stretch to 200.
COLUMN = 760
# A paragraph that opens with one of these words is a callout, marked
# with the icon the app uses for the same kind of message.
CALLOUT = re.compile(r"^(Note|Suggestion|Caution|Tip):")
CALLOUT_ICONS = {
    "Note": ("information-outline", style.ACCENT),
    "Suggestion": ("lightbulb-outline", style.ACCENT),
    "Tip": ("lightbulb-outline", style.ACCENT),
    "Caution": ("alert-outline", WARN),
}
ICON_PX = 16
NEXT_GAP = 28
SHEET = f"""
QDialog#helpWindow {{ background: {style.BODY}; }}
QTreeWidget#helpContents {{
    background: #ffffff; border: 1px solid {style.PANE_EDGE}; border-radius: 8px;
    padding: {style.SM}px; outline: 0; show-decoration-selected: 0;
}}
QTreeWidget#helpContents::item {{
    min-height: 36px; padding: 0 {style.SM}px; border-radius: 6px; color: {style.INK};
}}
QTreeWidget#helpContents::item:hover {{ background: #f0f2f5; }}
QTreeWidget#helpContents::item:selected {{
    background: {style.ACCENT_TINT}; color: {style.ACCENT};
}}
QTreeWidget#helpContents::branch, QTreeWidget#helpContents::branch:selected {{
    background: #ffffff;
}}
QTextBrowser#helpText {{
    background: #ffffff; border: 1px solid {style.PANE_EDGE}; border-radius: 8px;
}}
QPushButton#helpNav {{ padding: 0; }}
"""


def dress(browser: QTextBrowser) -> None:
    """Headings, spacing, and callouts on the page just loaded."""
    doc = browser.document()
    doc.setDocumentMargin(PAGE_MARGIN)
    callouts = []
    block = doc.begin()
    while block.isValid():
        fmt = block.blockFormat()
        level = fmt.headingLevel()
        cursor = QTextCursor(block)
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        if level:
            chars = QTextCharFormat()
            chars.setFontWeight(QFont.Weight.Bold)
            if level == 1:
                chars.setFontPointSize(H1_PT * text_scale())
                chars.setForeground(QColor(style.INK))
                fmt.setTopMargin(0)
                fmt.setBottomMargin(style.MD)
            else:
                chars.setFontPointSize(H2_PT * text_scale())
                chars.setForeground(QColor(style.ACCENT))
                fmt.setTopMargin(28)
                fmt.setBottomMargin(style.SM)
            cursor.mergeCharFormat(chars)
        else:
            fmt.setLineHeight(
                LINE_HEIGHT, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
            )
            fmt.setBottomMargin(style.XS if block.textList() else style.SM + 2)
            match = CALLOUT.match(block.text()) if not block.textList() else None
            if match:
                callouts.append((block.position(), match.group(1)))
        QTextCursor(block).setBlockFormat(fmt)
        block = block.next()
    # Last first, so a frame inserted cannot move a callout not yet framed.
    for position, word in reversed(callouts):
        block = doc.findBlock(position)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        frame = QTextFrameFormat()
        frame.setBackground(QColor(style.ACCENT_TINT_FAINT))
        frame.setBorder(1)
        frame.setBorderBrush(QColor(style.ACCENT_TINT_STRONG))
        frame.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        frame.setPadding(style.MD)
        frame.setTopMargin(style.XS)
        frame.setBottomMargin(style.SM + 2)
        inside = cursor.blockFormat()
        inside.setBottomMargin(0)
        boxed = cursor.insertFrame(frame)
        QTextCursor(doc.findBlock(boxed.firstPosition())).setBlockFormat(inside)
        # A frame takes the paragraph out of its line, and Qt leaves an
        # empty one on each side; they are flattened rather than removed,
        # since a frame must have a block on either side.
        for at in (boxed.firstPosition() - 1, boxed.lastPosition() + 1):
            empty = doc.findBlock(at)
            if empty.isValid() and not empty.text():
                flat = QTextBlockFormat()
                flat.setLineHeight(0, QTextBlockFormat.LineHeightTypes.FixedHeight.value)
                QTextCursor(empty).setBlockFormat(flat)
        _add_icon(doc, boxed.firstPosition(), *CALLOUT_ICONS[word])
    for frame in doc.rootFrame().childFrames():
        if isinstance(frame, QTextTable):
            _dress_table(frame)
    fit_column(browser)


def _add_icon(doc: QTextDocument, position: int, name: str, color: str) -> None:
    """The callout's icon before its first word, drawn at twice the size for a sharp edge."""
    url = QUrl(f"mdi:{name}:{color}")
    doc.addResource(
        QTextDocument.ResourceType.ImageResource,
        url,
        mdi_pixmap(name, ICON_PX, color, 2.0).toImage(),
    )
    image = QTextImageFormat()
    image.setName(url.toString())
    image.setWidth(ICON_PX)
    image.setHeight(ICON_PX)
    image.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignMiddle)
    cursor = QTextCursor(doc)
    cursor.setPosition(position)
    cursor.insertImage(image)
    cursor.insertText("  ", QTextCharFormat())


def _dress_table(table: QTextTable) -> None:
    """A table as the app's tables are: thin lines, room in each cell, a shaded header."""
    fmt = table.format()
    fmt.setBorder(1)
    fmt.setBorderBrush(QColor(style.PANE_EDGE))
    fmt.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
    fmt.setBorderCollapse(True)
    fmt.setCellPadding(style.SM)
    fmt.setCellSpacing(0)
    fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
    fmt.setTopMargin(style.XS)
    fmt.setBottomMargin(style.MD)
    table.setFormat(fmt)
    for col in range(table.columns()):
        cell = table.cellAt(0, col)
        shade = cell.format()
        shade.setBackground(QColor("#f0f2f5"))
        cell.setFormat(shade)


def add_next_link(browser: QTextBrowser, title: str, file_name: str) -> None:
    """ "Next: <page> ->" at the foot of a page, to the page after it."""
    cursor = QTextCursor(browser.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    block = QTextBlockFormat()
    block.setTopMargin(NEXT_GAP)
    cursor.insertBlock(block, QTextCharFormat())
    cursor.insertHtml(
        f'<a href="{file_name}" style="text-decoration: none">'
        f"<b>Next: {html.escape(title)} \u2192</b></a>"
    )


def fit_column(browser: QTextBrowser) -> None:
    """Keep lines to COLUMN pixels: the room past it goes on the right."""
    doc = browser.document()
    root = doc.rootFrame()
    fmt = root.frameFormat()
    room = browser.viewport().width() - 2 * PAGE_MARGIN
    fmt.setRightMargin(PAGE_MARGIN + max(0, room - COLUMN))
    fmt.setWidth(QTextLength())
    root.setFrameFormat(fmt)


class _HelpText(QTextBrowser):
    def resizeEvent(self, event) -> None:
        # Document layout only, not a widget's geometry or style.
        super().resizeEvent(event)
        fit_column(self)


def help_dir() -> Path:
    """Where the pages are; importlib.resources keeps this right inside a bundle."""
    return Path(str(files("madtracker").joinpath("help")))


def available_pages(folder: Path | None = None) -> list[tuple[str, str, Path]]:
    """(key, title, path) for every page whose file exists."""
    folder = help_dir() if folder is None else folder
    out = []
    for key, title, name in PAGES:
        path = folder / name
        if path.is_file():
            out.append((key, title, path))
    return out


def headings(path: Path) -> list[str]:
    """The page's section headings (its H2s), as the contents list shows them."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [_plain(m) for m in re.findall(r"^## (.+?)\s*$", text, flags=re.MULTILINE)]


def _plain(markdown: str) -> str:
    """Heading text as Qt shows it: no emphasis marks, a link's text alone."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", markdown)
    return re.sub(r"[*_`]", "", text).strip()


def slug(heading: str) -> str:
    """The heading's anchor as GitHub makes it (lowercase, punctuation dropped,
    spaces as hyphens), so one link reaches the section on GitHub and here."""
    text = re.sub(r"[^\w\- ]", "", _plain(heading).lower())
    return text.replace(" ", "-")


class HelpWindow(QDialog):
    def __init__(self, parent: QWidget | None = None, folder: Path | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("helpWindow")
        self.setStyleSheet(SHEET)
        self.setWindowTitle(f"{APP_NAME} Help")
        self.setModal(False)
        close_on_shortcut(self)
        fit_to_screen(self, 1040, 700)
        self.setFont(style.ui_font(12))
        self.folder = help_dir() if folder is None else folder
        self.pages = available_pages(self.folder)
        # The pages, and under the open one its sections: Getting started
        # runs to seven, and the scorer looking for "The races" would go to
        # it by scrolling. Only the open page shows its sections, so the list
        # stays a list of four.
        self.contents = QTreeWidget()
        self.contents.setObjectName("helpContents")
        self.contents.setHeaderHidden(True)
        self.contents.setRootIsDecorated(False)
        self.contents.setIndentation(style.MD)
        self.contents.setFixedWidth(CONTENTS_W)
        self.contents.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.contents.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.contents.setTextElideMode(Qt.TextElideMode.ElideRight)
        for key, title, path in self.pages:
            page = QTreeWidgetItem([title])
            page.setData(0, KEY_ROLE, key)
            page.setFont(0, style.ui_font(13))
            for heading in headings(path):
                section = QTreeWidgetItem([heading])
                section.setData(0, KEY_ROLE, key)
                section.setData(0, SECTION_ROLE, heading)
                section.setFont(0, style.ui_font(12))
                section.setToolTip(0, heading)
                page.addChild(section)
            self.contents.addTopLevelItem(page)
        self.contents.currentItemChanged.connect(self._item_changed)
        self._key: str | None = None
        self._jumping = False
        self.text = _HelpText()
        self.text.setObjectName("helpText")
        links = self.text.palette()
        links.setColor(QPalette.ColorRole.Link, QColor(style.ACCENT))
        self.text.setPalette(links)
        # The documents link to each other by file name, as they do on
        # GitHub; the browser would load such a link as raw text with no
        # contents row selected, so links are routed here instead.
        self.text.setOpenLinks(False)
        self.text.setSearchPaths([str(self.folder)])
        self.text.anchorClicked.connect(self._link_clicked)
        self.text.setFont(style.ui_font(BODY_PT))
        self.text.verticalScrollBar().valueChanged.connect(self._follow_scroll)
        # The places visited, (page key, scroll position), and where in
        # them the reader is; a new place after a step back drops what
        # was ahead, as a browser's history does.
        self._history: list[tuple[str, int]] = []
        self._at = -1
        self._restoring = False
        self.back = self._nav_button("back", "chevron-left", QKeySequence.StandardKey.Back)
        self.forward = self._nav_button(
            "forward", "chevron-right", QKeySequence.StandardKey.Forward
        )
        nav = QHBoxLayout()
        nav.setSpacing(style.XS)
        nav.addWidget(self.back)
        nav.addWidget(self.forward)
        nav.addStretch(1)
        columns = QHBoxLayout()
        columns.setSpacing(style.MD)
        columns.addWidget(self.contents)
        columns.addWidget(self.text, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(style.MD, style.MD, style.MD, style.MD)
        lay.setSpacing(style.SM)
        lay.addLayout(nav)
        lay.addLayout(columns, 1)
        if self.pages:
            self.contents.setCurrentItem(self.contents.topLevelItem(0))
        else:
            self.text.setPlainText("The help documents are not installed with this copy.")

    def _nav_button(self, which: str, glyph: str, key: QKeySequence.StandardKey) -> QPushButton:
        """A square glyph button that steps the history, with the platform's
        key for it (Alt+Left and Alt+Right; Command-[ and Command-] on the Mac)."""
        button = QPushButton()
        button.setObjectName("helpNav")
        button.setToolTip(NAV_WORDS[which])
        button.setAccessibleName(NAV_WORDS[which])
        button.setIcon(mdi(glyph, NAV_ICON_PX, style.INK))
        button.setIconSize(QSize(NAV_ICON_PX, NAV_ICON_PX))
        side = style.control_height()
        button.setFixedSize(side, side)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setEnabled(False)
        step = -1 if which == "back" else 1
        button.clicked.connect(lambda: self._step(step))
        action = QAction(self)
        action.setShortcut(key)
        action.triggered.connect(lambda: self._step(step))
        self.addAction(action)
        return button

    # ----- history ---------------------------------------------------------

    def _leave(self) -> None:
        """Keep where the reader got to on the place being left, so a step
        back returns there and not to where the place was entered."""
        if self._key is not None and self._history and not self._restoring:
            self._history[self._at] = (self._key, self.text.verticalScrollBar().value())

    def _arrive(self) -> None:
        if self._restoring or self._key is None:
            return
        place = (self._key, self.text.verticalScrollBar().value())
        if self._history and self._history[self._at] == place:
            return
        del self._history[self._at + 1 :]
        self._history.append(place)
        self._at = len(self._history) - 1
        self._sync_nav()

    def _sync_nav(self) -> None:
        self.back.setEnabled(self._at > 0)
        self.forward.setEnabled(self._at < len(self._history) - 1)

    def _step(self, by: int) -> None:
        """Back or Forward: the place in the history that way, at its scroll
        position, with the contents row for it; nothing when there is none."""
        at = self._at + by
        if not 0 <= at < len(self._history):
            return
        self._leave()
        self._at = at
        key, scroll = self._history[at]
        self._restoring = True
        try:
            if key != self._key:
                self._jumping = True
                try:
                    self._load(key)
                finally:
                    self._jumping = False
            bar = self.text.verticalScrollBar()
            bar.setValue(scroll)
            self._follow_scroll(bar.value())
        finally:
            self._restoring = False
        self._sync_nav()

    # ----- pages and sections -------------------------------------------

    def _page_item(self, key: str) -> QTreeWidgetItem | None:
        for i in range(self.contents.topLevelItemCount()):
            item = self.contents.topLevelItem(i)
            if item.data(0, KEY_ROLE) == key:
                return item
        return None

    def _item_changed(self, item: QTreeWidgetItem | None, _previous=None) -> None:
        if item is None:
            return
        key = item.data(0, KEY_ROLE)
        section = item.data(0, SECTION_ROLE)
        self._leave()
        # The bar's signal is what scrolls the page, so it is not blocked;
        # the flag keeps the scroll from choosing another row than the one
        # clicked, a new page's reset to the top included.
        self._jumping = True
        try:
            if key != self._key:
                self._load(key)
            # A step of room over the heading, not flush with the frame.
            self.text.verticalScrollBar().setValue(
                max(0, self._section_top(section) - style.MD) if section else 0
            )
        finally:
            self._jumping = False
        self._arrive()

    def _load(self, key: str) -> None:
        index = next(i for i, (k, _t, _p) in enumerate(self.pages) if k == key)
        _key, _title, path = self.pages[index]
        self._key = key
        for i in range(self.contents.topLevelItemCount()):
            page = self.contents.topLevelItem(i)
            page.setExpanded(page.data(0, KEY_ROLE) == key)
        try:
            self.text.setMarkdown(path.read_text(encoding="utf-8"))
        except OSError as exc:
            self.text.setPlainText(f"{path.name} could not be read: {exc}")
            return
        dress(self.text)
        if index + 1 < len(self.pages):
            # The pages read in order, as a short manual does.
            _k, title, following = self.pages[index + 1]
            add_next_link(self.text, title, following.name)

    def _heading_blocks(self, levels: tuple[int, ...] = (2,)) -> list:
        doc = self.text.document()
        out = []
        block = doc.begin()
        while block.isValid():
            if block.blockFormat().headingLevel() in levels:
                out.append(block)
            block = block.next()
        return out

    def _section_top(self, section: str) -> int:
        layout = self.text.document().documentLayout()
        for block in self._heading_blocks():
            if block.text().strip() == section:
                return round(layout.blockBoundingRect(block).top())
        return 0

    def _follow_scroll(self, value: int) -> None:
        """Keep the section being read selected in the contents as the page scrolls."""
        page = self._page_item(self._key) if self._key else None
        if page is None or self._jumping:
            return
        layout = self.text.document().documentLayout()
        # A heading counts as reached a little before it touches the top.
        reached = value + PAGE_MARGIN
        current = page
        for block in self._heading_blocks():
            if layout.blockBoundingRect(block).top() > reached:
                break
            for i in range(page.childCount()):
                if page.child(i).data(0, SECTION_ROLE) == block.text().strip():
                    current = page.child(i)
        if page.childCount() and value and value >= self.text.verticalScrollBar().maximum():
            # Scrolled to the end: a short last section never reaches the
            # top, and it is the one being read.
            current = page.child(page.childCount() - 1)
        if self.contents.currentItem() is not current:
            self.contents.blockSignals(True)
            self.contents.setCurrentItem(current)
            self.contents.blockSignals(False)

    def _link_clicked(self, url: QUrl) -> None:
        """A listed page selects its row; another local document is shown; the web opens outside."""
        if url.scheme() not in ("", "file"):
            QDesktopServices.openUrl(url)
            return
        name = Path(url.path()).name
        if not name:
            if url.fragment() and self._key:
                self._jump(self._key, url.fragment())
            return
        for key, _title, path in self.pages:
            if path.name == name:
                if url.fragment():
                    self._jump(key, url.fragment())
                else:
                    self.contents.setCurrentItem(self._page_item(key))
                return
        path = self.folder / name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            QDesktopServices.openUrl(url)
            return
        self._leave()
        self.contents.blockSignals(True)
        self.contents.setCurrentItem(None)
        self.contents.blockSignals(False)
        self._key = None
        self.text.setMarkdown(text)
        dress(self.text)

    def _jump(self, key: str, fragment: str) -> None:
        """Open the page at the heading the fragment names, any level, and
        select the section row it falls under; an unknown fragment is the top."""
        page = self._page_item(key)
        if page is None:
            return
        self._leave()
        self._jumping = True
        try:
            if key != self._key:
                self._load(key)
            layout = self.text.document().documentLayout()
            top, section = 0, None
            current = None
            for block in self._heading_blocks((2, 3)):
                if block.blockFormat().headingLevel() == 2:
                    current = block.text().strip()
                if slug(block.text()) == fragment:
                    top, section = round(layout.blockBoundingRect(block).top()), current
                    break
            self.text.verticalScrollBar().setValue(max(0, top - style.MD) if section else 0)
            row = page
            for i in range(page.childCount()):
                if page.child(i).data(0, SECTION_ROLE) == section:
                    row = page.child(i)
            # The row is set without its signal: the page is already loaded
            # and scrolled, and the signal would put it at the section's top.
            self.contents.blockSignals(True)
            self.contents.setCurrentItem(row)
            self.contents.blockSignals(False)
        finally:
            self._jumping = False
        self._arrive()

    def show_page(self, key: str, section: str | None = None) -> bool:
        """Open the page by key, at a section when given; False when its file is not installed."""
        page = self._page_item(key)
        self.show()
        if page is None:
            return False
        target = page
        for i in range(page.childCount()):
            if page.child(i).data(0, SECTION_ROLE) == section:
                target = page.child(i)
        if self.contents.currentItem() is target:
            self._item_changed(target)
        else:
            self.contents.setCurrentItem(target)
        self.raise_()
        return True

    def current_key(self) -> str | None:
        item = self.contents.currentItem()
        return None if item is None else item.data(0, KEY_ROLE)

    def current_section(self) -> str | None:
        item = self.contents.currentItem()
        return None if item is None else item.data(0, SECTION_ROLE)
