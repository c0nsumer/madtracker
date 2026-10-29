"""The operator window must not depend on the OS theme or on Windows-only fonts."""

from PySide6.QtGui import QFontDatabase, QFontInfo, QPalette
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem

from madtracker.ui import look, style


def test_available_families_exist_on_this_machine(qapp):
    present = set(QFontDatabase.families())
    families = look.available_families()
    assert families
    # Every family we hand to Qt is installed, so no alias search happens.
    assert all(f in present for f in families)


def test_light_palette_keeps_text_dark_on_light_base(qapp):
    look.apply_look(qapp)
    table = QTableWidget(1, 1)
    table.setItem(0, 0, QTableWidgetItem("Maya Petrakis"))
    pal = table.palette()
    base = pal.color(QPalette.ColorRole.Base)
    text = pal.color(QPalette.ColorRole.Text)
    assert base.lightness() > 200
    assert text.lightness() < 80
    assert QApplication.style().objectName().lower() == "fusion"


def test_check_boxes_are_drawn_large_and_dark_everywhere(qapp):
    """Fusion's 13 px faint box is invisible to a scorer; one drawing serves every widget."""
    from PySide6.QtWidgets import QCheckBox, QStyle

    look.apply_look(qapp)
    style = QApplication.style()
    assert isinstance(style, look.CheckStyle)
    for metric in look.CheckStyle.SIZES:
        assert style.pixelMetric(metric, None, QCheckBox()) == look.INDICATOR_PX
    assert style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth) >= 20


def test_every_button_flashes_after_a_click_so_a_touch_is_seen(qtbot):
    """Principle 3: a finger on the scorer's touchscreen is up again before
    the pressed look shows, so the release that clicks darkens the button
    for a moment, on its own and in a dialog alike."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton, QToolButton

    from madtracker.ui import style

    seen = []
    for b in (QPushButton("Record Sprint"), QToolButton()):
        qtbot.addWidget(b)
        b.show()
        qtbot.waitExposed(b)
        qtbot.mouseClick(b, Qt.MouseButton.LeftButton)
        assert b.property("flash") is True
        qtbot.waitUntil(lambda b=b: b.property("flash") is False, timeout=style.FLASH_MS * 10)
        seen.append(b)
    off = QPushButton("Off")
    qtbot.addWidget(off)
    off.setEnabled(False)
    off.show()
    qtbot.waitExposed(off)
    qtbot.mouseClick(off, Qt.MouseButton.LeftButton)
    assert off.property("flash") is None


def test_a_right_click_on_a_scrollbar_opens_no_stock_menu(qtbot):
    """A card and a result row have a menu and nothing else does; Qt's own
    "Scroll here" menu on every scrollbar would be the one unstyled menu
    in the program."""
    from PySide6.QtCore import QPoint, QTimer
    from PySide6.QtGui import QContextMenuEvent
    from PySide6.QtWidgets import QScrollArea, QWidget

    area = QScrollArea()
    inner = QWidget()
    inner.setMinimumHeight(3000)
    area.setWidget(inner)
    qtbot.addWidget(area)
    area.show()
    bar = area.verticalScrollBar()
    assert bar.isVisible()
    seen: list = []

    def look_for_a_menu():
        popup = QApplication.activePopupWidget()
        seen.append(None if popup is None else popup.objectName())
        if popup is not None:
            # The stock menu runs its own loop: close it so the test ends.
            popup.close()

    QTimer.singleShot(50, look_for_a_menu)
    pos = QPoint(bar.width() // 2, bar.height() // 2)
    QApplication.sendEvent(bar, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, bar.mapToGlobal(pos)))  # fmt: skip
    qtbot.waitUntil(lambda: bool(seen), timeout=1000)
    assert seen == [None]


def test_the_window_type_is_the_same_size_in_pixels_on_every_platform(qapp):
    """A point is a third of a pixel larger on Windows and Linux than on macOS,
    so the window's 12 pt is 16 px everywhere, and the layout with it."""
    assert QFontInfo(style.ui_font(12)).pixelSize() == 16
    assert QFontInfo(qapp.font()).pixelSize() == 16


def test_a_name_that_looks_like_markup_is_drawn_as_typed(qtbot, qapp):
    """Names are stored as typed and styled by the app, so a label, a message box
    and a tooltip show a team named with tags as those characters; a label made
    rich on purpose keeps its markup."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QLabel, QToolTip

    from madtracker.ui import icons

    name = "<b>Bold</b> & Co"
    label = QLabel(name)
    qtbot.addWidget(label)
    label.show()
    assert label.textFormat() == Qt.TextFormat.PlainText and label.text() == name
    rich = QLabel()
    rich.setTextFormat(Qt.TextFormat.RichText)
    rich.setText("<b>About</b>")
    qtbot.addWidget(rich)
    rich.show()
    assert rich.textFormat() == Qt.TextFormat.RichText
    box = icons.message_box(None, "warning", "Team", f"There is already a team named {name}.")
    qtbot.addWidget(box)
    box.show()
    shown = [w for w in box.findChildren(QLabel) if w.text().endswith(f"{name}.")]
    assert shown and all(w.textFormat() == Qt.TextFormat.PlainText for w in shown)
    QToolTip.showText(QPoint(10, 10), name, label)
    tips = [w for w in qapp.topLevelWidgets() if w.inherits("QLabel") and w.text() == name]
    assert tips and all(w.textFormat() == Qt.TextFormat.PlainText for w in tips)
    QToolTip.hideText()


def test_a_placeholder_and_a_locked_value_read_at_4_5_to_1_on_a_field(qapp):
    """A placeholder can be the value a blank field takes, and a locked field's
    value is still read, so both reach 4.5:1 on a field's gray."""
    from PySide6.QtGui import QColor

    from madtracker.board.theme import contrast

    p = look.light_palette()
    field = QColor("#e2e5ea")
    for group, role in (
        (QPalette.ColorGroup.Active, QPalette.ColorRole.PlaceholderText),
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text),
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText),
    ):
        assert contrast(p.color(group, role), field) >= 4.5, role


def test_a_header_and_its_figures_share_one_edge(qapp):
    """A right-aligned header over right-aligned figures ends where they
    end, and a left-aligned header starts where its words start: the
    cell's padding gives up the delegate's text margin, so both sit SM in."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QStyle, QWidget

    margin = qapp.style().pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, None) + 1
    assert style.CELL_TEXT_MARGIN == margin
    host = QWidget()
    host.setStyleSheet(style.stylesheet())
    table = QTableWidget(1, 2, host)
    table.setFont(style.ui_font())
    table.verticalHeader().setVisible(False)
    table.setFrameShape(QTableWidget.Shape.NoFrame)
    for col, align in enumerate((Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight)):
        head = QTableWidgetItem("888")
        head.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
        table.setHorizontalHeaderItem(col, head)
        cell = QTableWidgetItem("888")
        cell.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(0, col, cell)
        table.setColumnWidth(col, 120)
    host.resize(300, 120)
    host.show()
    image = table.grab().toImage()
    header_h = table.horizontalHeader().height()
    row_top = header_h + 2
    row_h = table.rowHeight(0) - 4

    def ink(x0: int, x1: int, y0: int, y1: int) -> tuple[int, int]:
        xs = [
            x
            for x in range(x0, x1)
            for y in range(y0, y1)
            if image.pixelColor(x, y).lightness() < 150
        ]
        return min(xs), max(xs)

    left_head = ink(0, 120, 2, header_h - 2)
    left_cell = ink(0, 120, row_top, row_top + row_h)
    right_head = ink(120, 240, 2, header_h - 2)
    right_cell = ink(120, 240, row_top, row_top + row_h)
    # A digit's side bearing differs a pixel between the header's weight
    # and the cell's; the edges are otherwise the same.
    assert abs(left_head[0] - left_cell[0]) <= 1, (left_head, left_cell)
    assert abs(right_head[1] - right_cell[1]) <= 1, (right_head, right_cell)
    host.deleteLater()
