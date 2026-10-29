"""Look of the operator window: one spacing scale, sizes from the font, a flat modern face.

Light and quiet, so the scoreboard's dark theme is never mistaken for
the operator's own screen. Gray marks where the scorer types, as in
the spreadsheet the scorer already uses ("only type in gray areas");
white is computed and read-only.

Control heights come from the font's line height, not from the
platform's defaults, so a button is the same shape on Windows, macOS
and Linux, and every margin and gap is one step of ``SPACE``. The
primary button of a dialog is the filled one; a destructive one is red.
"""

from PySide6.QtGui import QColor, QFont, QFontMetrics

from madtracker.ui.look import APP_PT, available_families, text_scale

INPUT_GRAY = QColor("#e2e5ea")
COMPUTED_WHITE = QColor("#ffffff")
NEXT_BLUE = QColor("#d9e6fb")
ACCENT = "#1f5fd1"
LIVE = "#d98a00"
OK_GREEN = "#1d7a3a"
DANGER = "#b3261e"
# A cell that needs a value before the dialog can go on: DANGER, faint.
DANGER_TINT = QColor("#f6d9d6")
INK = "#11151b"
DIM = "#5b6472"

# Faint tints of the four colors, for a fill that says the same thing
# as the color without shouting it: accent for "this is the live
# control", amber for live, green for done, red for trouble.
ACCENT_TINT = "#e8effc"
ACCENT_TINT_FAINT = "#f4f7fd"
ACCENT_TINT_STRONG = "#d6e3fa"

# The podium: places 1, 2 and 3 in the result, as on a results board.
GOLD_TINT = QColor("#f5e6b8")
SILVER_TINT = QColor("#dfe3e9")
BRONZE_TINT = QColor("#f0dccf")
MEDAL_TINTS = (GOLD_TINT, SILVER_TINT, BRONZE_TINT)

# The window behind the panes, a touch cooler than the white panes so
# they read as sheets lying on it; a pane's darker bottom edge stands in
# for a shadow, which style sheets cannot draw.
BODY = "#eef0f4"
PANE_EDGE = "#d7dbe1"
PANE_SHADE = "#c5cbd4"
CARD_EDGE = "#c3c9d2"
CARD_SHADE = "#aab2bd"
# The window's disabled gray: a disabled button's text, and the fill of a
# mark that says "nothing to do here".
DISABLED_INK = "#9aa1ad"
# A done card (a rider placed, out, or marked): the window's pale gray
# with an edge a touch darker, so it reads as set aside from the white
# cards that still take a click while it holds its slot.
DONE_GROUND = "#f1f3f5"
DONE_EDGE = "#e1e5ea"
DONE_SHADE = "#d6dbe1"

# The wash on the row the pointer or the keyboard is on, in every list
# that opens (a combo's list, a menu, the menu bar): the selected
# program row's tint, so "this one" looks alike wherever it appears.
POINTED = NEXT_BLUE.name()

# The three sections of Edit event, each with a hue from the app's
# rainbow (madtracker.assets.RAINBOW): the stripe in the hue itself, the
# title in a darker shade of it that reads at 4.5:1 or better on white.
# Red, orange and green are left out on purpose: red means trouble here,
# amber is Live, green is Final, and a section must never look like one.
STEP_HUES = {
    "stepEvent": ("#d9b43c", "#86680d"),
    "stepRoster": ("#3d7fc0", "#326fae"),
    "stepProgram": ("#7a5bb0", "#7a5bb0"),
}

# The rainbow under the menu bar: thin, a brand mark, not a border.
RAINBOW_PX = 3

# The scroll bar: thin enough to stay out of the way, wide enough that
# an older hand on a touchpad still catches the handle; the handle is
# never shorter than a fingertip.
SCROLL_PX = 14
SCROLL_HANDLE_MIN = 40

# The spacing scale: every margin, gap and padding is one of these.
SPACE = (4, 8, 12, 16, 24)
XS, SM, MD, LG, XL = SPACE
# How long a button keeps the flash after a click (look.ClickFlash): long
# enough to be seen on a touchscreen, short enough to be gone before the
# next click of a sprint's order.
FLASH_MS = 180
# The smallest target a finger hits reliably on the scorer's touchscreen:
# Apple's 44 points, between Microsoft's 40 and Google's 48. The card's
# +1 and -1 and its ⋯ strip, a result row, and a ⋯ menu's items are no
# smaller.
TOUCH = 44
# The lap buttons, pressed far more often than anything else on a card.
TOUCH_LAP = 48
# What Qt's item delegate keeps clear inside a cell beyond the style
# sheet's padding when it draws the text (PM_FocusFrameHMargin plus one,
# 3 under Fusion, the one style the app runs). A cell's padding gives it
# up, so the text sits SM from the cell's edge as a header's does, and a
# column's header and its figures share one edge: the right edge of a
# right-aligned "Total" over its totals, the left edge of "Place" over
# its places.
CELL_TEXT_MARGIN = 3
# The corner of every state tag (Racing, Provisional, Final): a rounded
# rectangle, the same shape in the program list and on the surface, so
# the two read as one kind of thing.
TAG_RADIUS = 6


def ui_font(pt: float = APP_PT, bold: bool = False) -> QFont:
    """A font at ``pt`` for Normal text size, scaled to the current one."""
    f = QFont()
    f.setFamilies(available_families())
    f.setPointSizeF(pt * text_scale())
    f.setBold(bold)
    return f


def line_height(pt: float = APP_PT) -> int:
    return QFontMetrics(ui_font(pt)).height()


def control_height(pt: float = APP_PT, factor: float = 2.2) -> int:
    """A button or field height: 2.2 line heights, the same on every platform."""
    return round(line_height(pt) * factor)


def stylesheet(pt: float = APP_PT) -> str:
    """The window's and the dialogs' face at base size ``pt``.

    The text a style sheet would otherwise take from the application
    font (tables, headers, lists, menus, fields) is set to ``pt`` here,
    so a child never comes out smaller than the face it sits in.
    """
    from madtracker.assets import RAINBOW
    from madtracker.ui.icons import svg_file

    h = control_height(pt)
    # The padding that makes a menu item TOUCH tall at the menu's own type.
    TOUCH_PAD = max(SM, round((TOUCH - line_height(pt)) / 2))
    field_h = control_height(pt, 1.9)
    fs = f"font-size: {pt * text_scale():g}pt;"
    # Forward slashes: a style sheet url() reads them on Windows too.
    chevron = svg_file("chevron-down", "#5b6472").as_posix()
    chevron_dim = svg_file("chevron-down", "#c3c9d2").as_posix()
    chevron_up = svg_file("chevron-up", "#5b6472").as_posix()
    chevron_up_dim = svg_file("chevron-up", "#c3c9d2").as_posix()
    chevron_right = svg_file("chevron-right", "#5b6472").as_posix()
    chevron_left = svg_file("chevron-left", "#5b6472").as_posix()
    check = svg_file("check", ACCENT).as_posix()
    check_dim = svg_file("check", "#9aa1ad").as_posix()
    sort_down = svg_file("chevron-down", ACCENT).as_posix()
    sort_up = svg_file("chevron-up", ACCENT).as_posix()
    rainbow = ", ".join(f"stop:{i / (len(RAINBOW) - 1):g} {hue}" for i, hue in enumerate(RAINBOW))
    steps = "\n".join(
        f"QGroupBox#{name} {{ border-top-color: {stripe}; color: {title}; }}"
        for name, (stripe, title) in STEP_HUES.items()
    )
    # The spin box's two buttons share the field's height, so each is half
    # of it: a step target the size of a key, not the style's own sliver.
    step_h = field_h // 2
    return f"""
QMainWindow, QWidget#central, QDialog {{ background: {BODY}; }}
QFrame#pane {{
    background: #ffffff; border: 1px solid {PANE_EDGE}; border-bottom: 2px solid {PANE_SHADE};
    border-radius: 6px;
}}
QFrame#pane QWidget#central {{ background: #ffffff; }}
/* The TV preview is the TV's one control: a pane that answers the mouse. */
QFrame#boardPane {{
    background: #ffffff; border: 1px solid {PANE_EDGE}; border-bottom: 2px solid {PANE_SHADE};
    border-radius: 6px;
}}
QFrame#boardPane[active="true"]:hover {{ border-color: {ACCENT}; background: {ACCENT_TINT}; }}
QFrame#boardPane[flash="true"] {{ border-color: {ACCENT}; background: {ACCENT_TINT_STRONG}; }}
QLabel#paneTitle {{ color: {ACCENT}; font-weight: 600; letter-spacing: 1px; }}
QLabel#raceTitle {{ color: #11151b; }}
QFrame#eventBand {{ background: {ACCENT_TINT}; border-radius: 6px; }}
QFrame#eventBand QLabel {{ background: transparent; }}
QLabel#eventName {{ color: {ACCENT}; }}
QLabel#raceDetail {{ color: #5b6472; }}
QLabel#raceDescription {{ color: #5b6472; }}
QLabel#hint {{ color: #5b6472; }}
QLabel#formError {{ color: {DANGER}; font-weight: 600; }}
QGroupBox {{ border: 1px solid {PANE_EDGE}; border-top: 2px solid {ACCENT}; border-radius: 6px;
    margin-top: {MD}px; padding: {MD}px {SM}px {SM}px {SM}px; font-weight: 600; color: {ACCENT};
    background: #ffffff; }}
QGroupBox::title {{ subcontrol-origin: margin; left: {MD}px; padding: 0 {XS}px; }}
QTabWidget::pane {{ border: 1px solid {PANE_EDGE}; border-radius: 6px; background: #ffffff;
    top: -1px; }}
QTabBar::tab {{
    min-height: {h}px; padding: 0 {LG}px; margin-right: {XS}px; border: 1px solid {PANE_EDGE};
    border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px;
    background: #f0f2f5; color: #5b6472;
}}
QTabBar::tab:selected {{ background: #ffffff; color: #11151b; border-top: 2px solid {ACCENT};
    font-weight: 600; }}
QTabBar::tab:hover:!selected {{ background: #f7f8fa; }}
QTabWidget > QWidget > QWidget {{ background: #ffffff; }}
QPushButton {{
    min-height: {h}px; padding: 0 {LG}px; border: 1px solid #c3c9d2; border-radius: 6px;
    background: #ffffff; color: #11151b;
}}
QPushButton:hover {{ background: #f0f2f5; }}
QPushButton:pressed {{ background: #e2e5ea; }}
QPushButton:focus {{ border: 2px solid {ACCENT}; padding: 0 {LG - 1}px; }}
QPushButton:disabled {{ color: #9aa1ad; background: #f3f4f6; border-color: #dfe3e8; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: #ffffff; font-weight: 600; }}
QPushButton#primary:hover {{ background: #1a52b5; }}
QPushButton#primary:disabled {{ background: #c3c9d2; border-color: #c3c9d2; color: #ffffff; }}
QPushButton#danger {{ color: {DANGER}; border-color: #e0b4b0; }}
QPushButton#danger:hover {{ background: #fbeeed; }}
QPushButton#danger:disabled {{ color: #9aa1ad; background: #f3f4f6; border-color: #dfe3e8; }}
QPushButton#square, QPushButton#square:focus {{ padding: 0; min-width: {h}px; max-width: {h}px; }}
QPushButton#undo:enabled {{ background: {ACCENT_TINT}; border-color: #b7cbf0; }}
QPushButton#undo:enabled:hover {{ background: {ACCENT_TINT_STRONG}; }}
QPushButton#undo:enabled:pressed {{ background: #c4d6f7; }}
/* The Edit | Score switch: a frame of two sides, the one on filled. */
/* The pane's edge: the switch stands in line with the panes, a gap apart. */
QFrame#modeSwitch {{
    background: #ffffff; border: 1px solid {PANE_EDGE}; border-bottom: 2px solid {PANE_SHADE};
    border-radius: 6px;
}}
QPushButton#mode {{
    border: none; border-radius: 4px; background: transparent; color: {DIM}; padding: 0 {SM}px;
}}
QPushButton#mode:hover {{ background: #f0f2f5; }}
QPushButton#mode:checked {{ background: {ACCENT}; color: #ffffff; }}
QPushButton#mode:checked:hover {{ background: #1a52b5; }}
QPushButton#mode:disabled {{ background: transparent; color: #9aa1ad; }}
QFrame#modeSwitch:disabled {{ border-color: #dfe3e8; background: #f3f4f6; }}
QPushButton#rider {{
    /* A card is as tall as the grid says, never the generic button height. */
    min-height: 0px;
    background: #ffffff; border: 1px solid {CARD_EDGE}; border-bottom: 2px solid {CARD_SHADE};
    border-radius: 8px; color: {INK}; padding: 0; text-align: left;
}}
QPushButton#rider:hover {{ background: {ACCENT_TINT_FAINT}; }}
QPushButton#rider:pressed {{ background: {ACCENT_TINT_STRONG}; }}
/* The card whose ⋯ menu is open stays lit until it closes, so the menu
   says whose it is; the row's ⋯ does the same. */
QPushButton#rider[lit="true"] {{ background: {ACCENT_TINT_STRONG}; }}
/* A done card answers a click only with the red line, so it neither
   tints under the pointer nor when pressed; its menu still lights it. */
QPushButton#rider[done="true"], QPushButton#rider[done="true"]:hover,
QPushButton#rider[done="true"]:pressed {{
    background: {DONE_GROUND}; border: 1px solid {DONE_EDGE}; border-bottom: 2px solid {DONE_SHADE};
}}
QPushButton#rider[done="true"][lit="true"] {{ background: {ACCENT_TINT_STRONG}; }}
/* A row's ⋯ is a strip like the card's: a divider on its left, the row's
   full height and a touch wide (review.DOTS_COL_W), the glyph as large
   as the card's, so it reads as a button and takes a finger: the glyph
   alone reads as too small to touch. */
QToolButton#dots {{ border: none; border-left: 1px solid {CARD_EDGE}; border-radius: 0;
    margin: 0; padding: 0; }}
QToolButton#dots:hover {{ background: {ACCENT_TINT}; }}
QToolButton#dots:pressed, QToolButton#dots[lit="true"] {{ background: {ACCENT_TINT_STRONG}; }}
QToolButton#cardActions {{
    border: none; border-left: 1px solid {CARD_EDGE}; padding: 0; background: transparent;
    border-top-right-radius: 7px; border-bottom-right-radius: 7px;
}}
QToolButton#cardActions:hover {{ background: {ACCENT_TINT}; }}
QToolButton#cardActions:pressed {{ background: {ACCENT_TINT_STRONG}; }}
QToolButton#taskActions {{ border: none; padding: 0; background: transparent; border-radius: 7px; }}
QToolButton#taskActions:hover {{ background: {ACCENT_TINT}; }}
QToolButton#taskActions:pressed {{ background: {ACCENT_TINT_STRONG}; }}
QToolButton#cardLap {{
    border: none; border-left: 1px solid {CARD_EDGE}; padding: 0; background: transparent;
    color: {INK};
}}
QToolButton#cardLap:hover {{ background: {ACCENT_TINT}; }}
QToolButton#cardLap:pressed {{ background: {ACCENT_TINT_STRONG}; }}
/* The flash after a click (look.ClickFlash): darker than hover and pressed,
   since a touch is up again before the pressed look is seen. One rule per
   kind of button, after that kind's own rules, so each flashes in its
   own color. */
QPushButton[flash="true"] {{ background: #c8cdd5; }}
QPushButton#primary[flash="true"] {{ background: #143f8f; }}
QPushButton#danger[flash="true"] {{ background: #f1cfcc; }}
QPushButton#undo:enabled[flash="true"] {{ background: #b5cbf3; }}
QPushButton#mode[flash="true"] {{ background: #d6dae0; }}
QPushButton#mode:checked[flash="true"] {{ background: #143f8f; }}
QPushButton#rider[flash="true"] {{ background: #c4d6f7; }}
QPushButton#rider[done="true"][flash="true"] {{ background: {DONE_GROUND}; }}
QToolButton[flash="true"] {{ background: #c4d6f7; }}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
    {fs} min-height: {field_h}px; background: #e2e5ea; border: 1px solid #c3c9d2;
    border-radius: 4px; padding: 0 {SM}px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus {{ border: 2px solid {ACCENT}; }}
QLineEdit:read-only, QPlainTextEdit[readOnly="true"] {{ background: #ffffff; }}
QComboBox QLineEdit, QComboBox QLineEdit:focus {{
    /* The typed-into combo's own line edit sits over the box's left edge,
       and its field look there hid the box's focus border on that side.
       The box draws the face; the edit is text alone. */
    border: none; background: transparent; padding: 0; margin: 0; min-height: 0;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right;
    width: {h}px; border: none; border-left: 1px solid #c3c9d2;
}}
QComboBox::down-arrow {{ image: url({chevron}); width: 20px; height: 20px; }}
QComboBox::down-arrow:disabled {{ image: url({chevron_dim}); }}
QComboBox:disabled::drop-down {{ border-left-color: #dfe3e8; }}
QDateEdit::drop-down {{
    /* The calendar's button, as wide as a combo's: Qt's own was a sliver. */
    subcontrol-origin: padding; subcontrol-position: center right;
    width: {h}px; border: none; border-left: 1px solid #c3c9d2;
}}
QDateEdit::down-arrow {{ image: url({chevron}); width: 20px; height: 20px; }}
/* The text inset and height of a line edit: a spin box's own size hint
   is a few pixels taller than the rule above, and wins without a cap.
   A spin box's inset is set on its edit (widgets.spin_box), since Qt
   ignores this padding there. */
QSpinBox, QDateEdit {{ max-height: {field_h}px; }}
QDateEdit {{ padding-left: {SM}px; }}
QSpinBox::up-button, QDateEdit::up-button, QSpinBox::down-button, QDateEdit::down-button {{
    subcontrol-origin: padding; width: {h}px; height: {step_h}px;
    border: none; border-left: 1px solid #c3c9d2; background: transparent;
}}
QSpinBox::up-button, QDateEdit::up-button {{ subcontrol-position: top right; }}
QSpinBox::down-button, QDateEdit::down-button {{
    subcontrol-position: bottom right; border-top: 1px solid #c3c9d2;
}}
QSpinBox::up-button:hover, QDateEdit::up-button:hover,
QSpinBox::down-button:hover, QDateEdit::down-button:hover {{ background: {ACCENT_TINT}; }}
QSpinBox::up-button:pressed, QDateEdit::up-button:pressed,
QSpinBox::down-button:pressed, QDateEdit::down-button:pressed {{
    background: {ACCENT_TINT_STRONG};
}}
QSpinBox::up-arrow, QDateEdit::up-arrow {{ image: url({chevron_up}); width: 18px; height: 18px; }}
QSpinBox::down-arrow, QDateEdit::down-arrow {{ image: url({chevron}); width: 18px; height: 18px; }}
QSpinBox::up-arrow:disabled, QSpinBox::up-arrow:off, QDateEdit::up-arrow:disabled {{
    image: url({chevron_up_dim});
}}
QSpinBox::down-arrow:disabled, QSpinBox::down-arrow:off, QDateEdit::down-arrow:disabled {{
    image: url({chevron_dim});
}}
QListWidget#outline {{ {fs} border: none; background: #ffffff; }}
/* No dotted focus frame on a list's current row: the selection already
   marks it, and the frame drew a second box inside it. */
QListWidget {{ {fs} background: #ffffff; border: 1px solid #d7dbe1; border-radius: 4px;
    outline: 0; }}
QListWidget::item {{ padding: {XS}px {SM}px; }}
QListWidget#checkList::item:hover {{ background: #eef2f8; }}
QTableWidget {{
    {fs} border: 1px solid #d7dbe1; gridline-color: #e6e9ee; background: #ffffff;
    selection-background-color: #cfe0ff; selection-color: #11151b;
    alternate-background-color: #f5f6f8;
}}
QTableWidget::item {{ padding: 0 {SM - CELL_TEXT_MARGIN}px; }}
QHeaderView::section {{
    {fs} background: #f3f4f6; border: none; border-bottom: 1px solid #d7dbe1;
    padding: {XS}px {SM}px; color: #5b6472; font-weight: 600; min-height: {field_h}px;
}}
/* The sort mark: the app's chevron in the accent, the same glyph as a
   combo's, where Fusion drew a small gray triangle. */
QHeaderView::down-arrow {{ image: url({sort_down}); width: 16px; height: 16px;
    subcontrol-position: center right; padding-right: {XS}px; }}
QHeaderView::up-arrow {{ image: url({sort_up}); width: 16px; height: 16px;
    subcontrol-position: center right; padding-right: {XS}px; }}
QStatusBar {{ {fs} background: #e9ebef; color: #3b4350; }}
QFrame#rainbow {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {rainbow});
    border: none; min-height: {RAINBOW_PX}px; max-height: {RAINBOW_PX}px; }}
QMenuBar {{ {fs} background: {BODY}; padding: 0 {XS}px; }}
QMenuBar::item {{ padding: {XS}px {SM}px; border-radius: 4px; background: transparent; }}
QMenuBar::item:selected {{ background: {ACCENT_TINT}; }}
QMenuBar::item:pressed {{ background: {POINTED}; }}
QMenu {{ {fs} background: #ffffff; border: 1px solid #c3c9d2; padding: {XS}px; }}
/* Qt adds the check mark's column itself, in a menu that has a tick. */
QMenu::item {{ padding: {SM}px {XL}px {SM}px {MD}px; border-radius: 4px; color: {INK}; }}
QMenu::item:selected {{ background: {POINTED}; }}
/* A ⋯ menu is tapped on the touchscreen: its items are TOUCH tall. */
QMenu#touchMenu::item {{ padding: {TOUCH_PAD}px {XL}px {TOUCH_PAD}px {MD}px; }}
QMenu::item:disabled {{ color: #9aa1ad; }}
QMenu::item:disabled:selected {{ background: transparent; }}
QMenu::separator {{ height: 1px; background: #e6e9ee; margin: {XS}px {SM}px; }}
/* A checked item's tick is the app's own check in the accent, the
   same mark as a ticked box; an exclusive choice (Logo or Live, the
   display) is a tick too, not Fusion's small radio dot. */
QMenu::indicator {{ width: 18px; height: 18px; left: {SM}px; }}
QMenu::indicator:checked {{ image: url({check}); }}
QMenu::indicator:checked:disabled {{ image: url({check_dim}); }}
QMenu::indicator:unchecked {{ image: none; }}
QMenu::right-arrow {{ image: url({chevron_right}); width: 18px; height: 18px;
    right: {SM}px; }}
/* A combo's open list: a list below the box, rows as tall as a menu's
   and the same tint, framed like the box it came from. Fusion opened a
   plain combo as a menu laid over the box and a typed-into one
   (GroupCombo) as a bare list in a smaller face; this opens both alike.
   (The menu kind cannot take these row rules: Qt sizes its rows wrong.)
   A list this kind opens only as wide as its box, so a box whose items
   run longer widens its own list (widgets.fit_popup). */
QComboBox {{ combobox-popup: 0; }}
QComboBox QAbstractItemView {{
    {fs} background: #ffffff; color: {INK}; border: 1px solid #c3c9d2; padding: {XS}px;
    outline: 0; selection-background-color: {POINTED}; selection-color: {INK};
}}
QComboBox QAbstractItemView::item {{ padding: {SM}px {SM}px; border-radius: 4px;
    min-height: {line_height(pt)}px; }}
QComboBox QAbstractItemView::item:hover {{ background: {ACCENT_TINT}; }}
QComboBox QAbstractItemView::item:selected {{ background: {POINTED}; color: {INK}; }}
/* A heading in a list (the format picker's rule books) is not a choice. */
QComboBox QAbstractItemView::item:disabled {{ color: #5b6472; background: transparent; }}
/* Scroll bars: a rounded handle on a clear track, darker under the
   pointer, with no arrow buttons; the track itself pages on a click. */
QScrollBar:vertical {{ background: transparent; width: {SCROLL_PX}px; margin: 0; border: none; }}
QScrollBar:horizontal {{ background: transparent; height: {SCROLL_PX}px; margin: 0; border: none; }}
QScrollBar::handle {{ background: #c3c9d2; border-radius: {(SCROLL_PX - 6) // 2}px; margin: 3px; }}
QScrollBar::handle:vertical {{ min-height: {SCROLL_HANDLE_MIN}px; }}
QScrollBar::handle:horizontal {{ min-width: {SCROLL_HANDLE_MIN}px; }}
QScrollBar::handle:hover {{ background: #9aa1ad; }}
QScrollBar::handle:pressed {{ background: #6b7484; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QAbstractScrollArea::corner {{ background: transparent; border: none; }}
/* The tab strip's scroll buttons when the tabs run out of room: the
   app's chevrons on a button the size of a field, not Fusion's slivers. */
QTabBar::scroller {{ width: {2 * field_h}px; }}
QTabBar QToolButton {{ background: #ffffff; border: 1px solid {PANE_EDGE}; border-radius: 4px;
    margin: {XS}px 0 {XS}px {XS}px; }}
QTabBar QToolButton:hover {{ background: {ACCENT_TINT}; }}
QTabBar QToolButton::left-arrow {{ image: url({chevron_left}); width: 18px; height: 18px; }}
QTabBar QToolButton::right-arrow {{ image: url({chevron_right}); width: 18px; height: 18px; }}
/* The pane dividers draw nothing until the pointer finds one. */
QSplitter::handle {{ background: transparent; image: none; }}
QSplitter::handle:hover {{ background: {ACCENT_TINT}; }}
QTextBrowser {{ background: #ffffff; border: 1px solid {PANE_EDGE}; border-radius: 4px;
    padding: {SM}px; }}
QCheckBox {{ {fs} spacing: {SM}px; }}
/* Dark, so a tip reads as a note over the window rather than another
   pane of it; rounded like the fields. */
QToolTip {{ {fs} background: #2b313a; color: #ffffff; border: 1px solid #2b313a;
    border-radius: 4px; padding: {XS}px {SM}px; }}
QDialogButtonBox {{ button-layout: 3; }}
{steps}
"""
