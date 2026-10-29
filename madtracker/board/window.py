"""The audience scoreboard: a top bar and one layout at a time beneath it.

``BoardCanvas`` draws; ``ScoreboardWindow`` is the canvas as the TV's
window, and the operator window embeds a second canvas as its preview.
The window only renders what it is handed. The app decides which screen
it goes on (``madtracker.displays``) and reacts to hot-plug signals; the
scoring side decides what to show and calls ``set_layout``.
"""

import dataclasses
import sys

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap, QRegion, QScreen
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from madtracker import APP_NAME
from madtracker.board import theme as t
from madtracker.board import wordmark
from madtracker.board.pages import PAGES, EliminationPage, Page, lap_chip_height
from madtracker.board.payloads import LAYOUT_PAYLOADS, Header, coerce
from madtracker.displays import ScreenInfo, friendly_label

# The board is designed on a 1080-line canvas; every size is a multiple
# of height / 1080.
DESIGN_HEIGHT = 1080
TOP_BAR_HEIGHT = 140
# The widest a logo may run along the top bar, in design units. Venue
# wordmarks are long and short (one is 1200 by 215), so the box
# follows the image's aspect up to this width instead of squeezing it
# into a square-ish slot where it would print at a third of its height.
LOGO_MAX_W = 620

# How long a sprint's result card stays up, whatever its length: one
# time the stands and the announcer can count on, rather than three
# seconds a place, which would only ever vary for a Tempo Race. The
# next entry takes it down sooner, so a sprint every lap
# never waits on it.
SPRINT_CARD_MS = 10000


# The board as an ordinary window on the laptop, for setup and testing:
# 16:9 and small enough to sit beside the operator window.
WINDOWED_SIZE = (960, 540)


def windowed_position(area: QRect, size: QSize, avoid: QRect | None) -> QPoint:
    """Where the windowed board goes in ``area``: clear of ``avoid`` if it fits.

    Right of the operator window, then left, below, above; with no room
    anywhere (a maximized operator window), the bottom right corner,
    which covers the action log rather than the outline or the bib box.
    """
    w, h = size.width(), size.height()
    corner = QPoint(area.right() - w + 1, area.bottom() - h + 1)
    if avoid is None:
        return QPoint(max(area.left(), corner.x()), max(area.top(), corner.y()))
    top = max(area.top(), min(avoid.top(), area.bottom() - h + 1))
    left = max(area.left(), min(avoid.left(), area.right() - w + 1))
    candidates = [
        QPoint(avoid.right() + 1, top),
        QPoint(avoid.left() - w, top),
        QPoint(left, avoid.bottom() + 1),
        QPoint(left, avoid.top() - h),
    ]
    for pos in candidates:
        if area.contains(QRect(pos, size)):
            return pos
    return QPoint(max(area.left(), corner.x()), max(area.top(), corner.y()))


def screen_infos(screens: list[QScreen] | None = None) -> list[ScreenInfo]:
    """Describe Qt's screens for ``choose_scoreboard_screen``."""
    if screens is None:
        screens = QGuiApplication.screens()
    primary = QGuiApplication.primaryScreen()
    out = []
    for index, s in enumerate(screens):
        g = s.geometry()
        label = friendly_label(
            s.name(), s.manufacturer(), s.model(), g.width(), g.height(), s is primary, index
        )
        out.append(ScreenInfo(s.name(), g.x(), g.y(), g.width(), g.height(), s is primary, label))
    return out


def screen_by_name(name: str | None) -> QScreen | None:
    if not name:
        return None
    for s in QGuiApplication.screens():
        if s.name() == name:
            return s
    return None


def fit_pixmap(src: QPixmap, box: QSize, dpr: float) -> QPixmap:
    """``src`` fitted inside ``box`` (logical pixels) at the screen's real pixel density.

    Qt draws a pixmap in logical pixels, so one scaled to the logical box
    is stretched again on a 125%, 150% or 200% display. Scaling to the
    physical size and tagging the ratio uses every pixel of the source.
    """
    target = QSize(max(1, round(box.width() * dpr)), max(1, round(box.height() * dpr)))
    pix = src.scaled(
        target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    pix.setDevicePixelRatio(dpr)
    return pix


class FitCache:
    """The last fitted pixmap, kept until the source, box or ratio changes.

    The top bar repaints on every entry; a smooth rescale of a
    scoreboard-sized logo each time would be wasted work on the scorer's laptop.
    """

    def __init__(self) -> None:
        self.key: tuple | None = None
        self.pixmap: QPixmap | None = None

    def get(self, src: QPixmap, box: QSize, dpr: float) -> QPixmap:
        key = (src.cacheKey(), box.width(), box.height(), dpr)
        if self.pixmap is None or key != self.key:
            self.key, self.pixmap = key, fit_pixmap(src, box, dpr)
        return self.pixmap


def stamp_colors(status: str) -> tuple[QColor, QColor, QColor | None] | None:
    """A result's state as a stamp: (fill, ink, outline), or None for no stamp.

    Provisional is drawn hollow in the accent, Final filled in the gain
    green with dark ink. Read at paint time: the accent and the gain color
    are the venue's, set after this module loads.
    """
    if status == "Provisional":
        return t.BAR, t.ACCENT, t.ACCENT
    if status == "Final":
        return t.GAIN, t.PLATE_TEXT, None
    return None


# The widest the top bar's right column (the status) may take, in design
# px; it is only as wide as what it shows.
STATUS_MAX_W = 560


class TopBar(QWidget):
    """Venue logo, race title and group, and a status line at the right."""

    def __init__(self, venue_name: str, event_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.venue_name = venue_name
        self.event_name = event_name
        self.logo: QPixmap | None = None
        self._fit = FitCache()
        self.header = Header(title="")
        self.u = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def paintEvent(self, event) -> None:
        u = self.u
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), t.BAR)
        p.setPen(QPen(t.RULE, 2 * u))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        m = t.EDGE * u
        box_h = self.height() - 48 * u
        has_logo = self.logo is not None and not self.logo.isNull() and self.logo.height() > 0
        if has_logo:
            aspect = self.logo.width() / self.logo.height()
            box = QRectF(m, 24 * u, min(LOGO_MAX_W * u, box_h * aspect), box_h)
            pix = self._fit.get(self.logo, box.size().toSize(), self.devicePixelRatioF())
            size = pix.deviceIndependentSize()
            p.drawPixmap(QPointF(box.x(), box.center().y() - size.height() / 2), pix)
        else:
            # No venue logo: the app's wordmark, drawn rather than
            # scaled from a raster so it is sharp on any TV.
            box = QRectF(m, 24 * u, min(LOGO_MAX_W * u, box_h * wordmark.CANVAS_ASPECT), box_h)
            pad = box_h * (1 - wordmark.CANVAS_INK) / 2
            wordmark.paint(p, box.adjusted(0, pad, 0, -pad))

        h = self.header
        x = box.right() + 48 * u
        # The right column is as wide as the status, up to STATUS_MAX_W:
        # held at the maximum, a short "Start list" would leave a gap
        # beside the group tag while the title was cut short. The event's
        # name is not here: the logo page carries it between races, and
        # on a race page it would only repeat what the stands know, so
        # the status has the column to itself.
        status_w = STATUS_MAX_W * u
        stamp = stamp_colors(h.status)
        if stamp is not None:
            status_used = t.chip_width(lap_chip_height(u), h.status.upper())
        else:
            status_used = t.text_width(h.status, t.font(44 * u, t.BOLD))
        right_w = min(status_w, status_used)
        title_w = self.width() - x - right_w - (48 * u if right_w else 0.0) - m
        # The group rides on the title's line, its chip type at the board's
        # minimum: on the line below, at the height that line allows, it
        # would be 21 px, and which group is racing is news to the stands.
        chip_h = lap_chip_height(u)
        gap = 24 * u
        chip_w = t.chip_width(chip_h, h.group) + gap if h.group else 0.0
        # With no format line under it (an unnamed race, whose title is the
        # format), the title sits in the middle of the bar, not over a gap.
        title_y = 12 * u if h.detail else (self.height() - 72 * u) / 2
        title_line = QRectF(x, title_y, max(0.0, title_w - chip_w), 72 * u)
        used = t.text(p, title_line, h.title, t.font(58 * u, t.HEAVY), t.TEXT, shrink=True)
        if h.group:
            cx = x + (used + gap if h.title else 0.0)
            t.accent_chip(p, cx, title_line.center().y() - chip_h / 2, chip_h, h.group)
        if h.detail:
            # The kind of race, muted under the title: the stands know a
            # madison from a points race without reading the rules.
            t.text(
                p,
                QRectF(x, 86 * u, title_w, 40 * u),
                h.detail,
                t.font(t.MIN_PX * u, t.SEMI),
                t.MUTED,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )

        right = QRectF(self.width() - m - status_w, 0, status_w, self.height())
        align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if stamp is not None:
            # A result's state is a stamp, not a line of the same amber as
            # "Racing": Provisional hollow, Final filled green, so the two
            # cannot be mistaken for each other from the stands.
            fill, ink, outline = stamp
            # Its type at the board's floor, as the group chip's is: at
            # 56 u the stamp's type would be 31 px, under the floor.
            # Centered in the bar, as the status line is.
            stamp_h = lap_chip_height(u)
            w = t.chip_width(stamp_h, h.status.upper())
            t.chip(
                p,
                right.right() - w,
                (self.height() - stamp_h) / 2,
                stamp_h,
                h.status.upper(),
                fill,
                ink,
                outline=outline,
            )
        else:
            # Gray before the start, as on the scoring surface: the accent
            # is for a race under way, so the stands can tell the two apart.
            t.text(
                p,
                right,
                h.status,
                t.font(44 * u, t.BOLD),
                t.MUTED if h.status == "Start list" else t.ACCENT,
                align,
            )
        p.end()


# The event name under the logo, in design px: large enough to read
# across the venue between sessions.
EVENT_PX = 96


class LogoPage(QWidget):
    """The board between sessions: the logo, large, and the event name under it.

    Shown during setup and after the night so the TV never carries a
    stale or half-entered race. It reads the logo and the event
    name from the top bar, so the venue settings reach both views at once.
    """

    def __init__(self, bar: TopBar, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bar = bar
        self.u = 1.0
        self._trimmed: tuple[QPixmap, QPixmap] | None = None
        self._fit = FitCache()
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def _logo(self) -> QPixmap | None:
        """The logo without its transparent margins, so it centers on what is drawn.

        Wordmarks often ship on a wider transparent canvas (the bundled
        one does), which in the top bar is harmless but here would pull
        the mark off the middle of the TV.
        """
        logo = self.bar.logo
        if logo is None or logo.isNull():
            return None
        if self._trimmed is None or self._trimmed[0] is not logo:
            area = QRegion(logo.mask()).boundingRect() if logo.hasAlpha() else logo.rect()
            self._trimmed = (logo, logo.copy(area) if not area.isEmpty() else logo)
        return self._trimmed[1]

    def paintEvent(self, event) -> None:
        u = self.u
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), t.BG)
        w, h = self.width(), self.height()
        box = QRectF(w * 0.15, h * 0.2, w * 0.7, h * 0.45)
        logo = self._logo()
        if logo is not None:
            pix = self._fit.get(logo, box.size().toSize(), self.devicePixelRatioF())
            size = pix.deviceIndependentSize()
            top = box.center().y() - size.height() / 2
            p.drawPixmap(QPointF(box.center().x() - size.width() / 2, top), pix)
            bottom = top + size.height()
        else:
            bottom = wordmark.paint(p, box, Qt.AlignmentFlag.AlignCenter).bottom()
        if self.bar.event_name:
            # Read from the stands, so large and in full ink; a long name
            # steps down to fit the width, but
            # never under the board's floor.
            room = w * 0.9
            px = EVENT_PX
            while (
                px > t.MIN_PX and t.text_width(self.bar.event_name, t.font(px * u, t.BOLD)) > room
            ):
                px -= 4
            t.text(
                p,
                QRectF((w - room) / 2, bottom + 56 * u, room, px * 1.5 * u),
                self.bar.event_name,
                t.font(px * u, t.BOLD),
                t.TEXT,
                Qt.AlignmentFlag.AlignCenter,
            )
        p.end()


class BoardCanvas(QWidget):
    """The board's drawing surface: the live face and the logo page.

    The TV window and the operator window's preview are both one of
    these, fed the same calls, so the preview cannot drift from what the
    audience sees. Public surface: ``set_layout``, ``set_live``,
    ``set_logo``, ``set_show_bibs``, ``set_event_name``, ``set_venue_name``,
    ``layout_name`` and ``page_kind``.
    """

    # How long the loud treatments last before the board settles. These are
    # the only timers on the board; everything else redraws on new data.
    ELIMINATION_HIGHLIGHT_MS = 5000
    SPRINT_OVERLAY_MS = SPRINT_CARD_MS
    PAGE_MS = 6000

    def __init__(
        self,
        venue_name: str = "",
        event_name: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), t.BG)
        self.setPalette(pal)

        self.top_bar = TopBar(venue_name, event_name, self)
        self.stack = QStackedWidget(self)
        self.pages: dict[str, Page] = {}
        for name, cls in PAGES.items():
            page = cls(self.stack)
            self.pages[name] = page
            self.stack.addWidget(page)

        # The live board (top bar over a layout) and the logo page are two
        # faces of one window, so flipping between them never moves or
        # re-places the window on the TV. Layouts keep updating behind the
        # logo, so a flip to live shows the current race at once.
        live = QWidget(self)
        lay = QVBoxLayout(live)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.top_bar)
        lay.addWidget(self.stack, 1)
        self.logo_page = LogoPage(self.top_bar, self)
        self.faces = QStackedWidget(self)
        self.faces.addWidget(live)
        self.faces.addWidget(self.logo_page)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.faces)
        self._live = True

        self._layout_name = "between"
        # Per race, the riders out in order as the elimination page last
        # showed them, so a payload says whether a rider was just put out.
        self._out_seen: dict[int, tuple[tuple[str, ...], ...]] = {}
        self._highlight = QTimer(self, singleShot=True, interval=self.ELIMINATION_HIGHLIGHT_MS)
        self._highlight.timeout.connect(self._settle_elimination)
        self._overlay = QTimer(self, singleShot=True, interval=self.SPRINT_OVERLAY_MS)
        self._overlay.timeout.connect(self._clear_overlay)
        # A standings table longer than a page turns its pages on its own.
        self._pager = QTimer(self, interval=self.PAGE_MS)
        self._pager.timeout.connect(self._turn_page)
        self._pager.start()
        self._apply_scale()

    # Content -----------------------------------------------------------

    def layout_name(self) -> str:
        return self._layout_name

    def set_live(self, live: bool) -> None:
        """Show the live layouts, or the logo page over them."""
        self._live = bool(live)
        self.faces.setCurrentIndex(0 if self._live else 1)

    def page_kind(self) -> str:
        """What the audience sees: "logo", or the live layout's name."""
        return self._layout_name if self._live else "logo"

    def set_layout(self, name: str, data) -> None:
        """Switch to layout ``name`` and render ``data``, that layout's payload."""
        if name not in PAGES:
            raise ValueError(f"unknown scoreboard layout {name!r}; expected one of {sorted(PAGES)}")
        payload = coerce(LAYOUT_PAYLOADS[name], data)
        page = self.pages[name]
        if isinstance(page, EliminationPage):
            self._notice_eliminations(page, payload)
        elif name == "pre_race":
            # The start list: nobody is out, so the first rider out is
            # news (an Undo of the first elimination lands here too).
            self._out_seen[payload.header.race_id] = ()
            self._highlight.stop()
            self.pages["elimination"].fresh = False
        result = getattr(payload, "sprint_result", None)
        if result is not None:
            self._overlay.start(self.SPRINT_OVERLAY_MS)
        else:
            self._overlay.stop()
        if payload.header != self.top_bar.header:
            # A new race, or a new sprint, starts a long table on its first
            # page (StandingsPage.set_data), so the page clock starts over
            # with it. The TV and the preview get this call together; each
            # running its own clock from when it was made, a turn on one
            # could land on the far side of a new header from the turn on
            # the other, and the two would show different pages until the
            # next turn.
            self._pager.start()
        page.set_data(payload)
        self.top_bar.header = payload.header
        self.top_bar.update()
        self.stack.setCurrentWidget(page)
        self._layout_name = name

    def set_venue_name(self, name: str) -> None:
        """The venue's name; the board draws the logo, or the app's wordmark, in its place."""
        self.top_bar.venue_name = name
        self.top_bar.update()
        self.logo_page.update()

    def set_logo(self, path: str | None) -> None:
        pix = QPixmap(path) if path else None
        self.top_bar.logo = pix if pix is not None and not pix.isNull() else None
        self.top_bar.update()
        self.logo_page.update()

    def set_logo_bytes(self, data: bytes | None) -> None:
        """The venue's logo as the data file holds it (design section 11)."""
        pix = QPixmap()
        if data and pix.loadFromData(bytes(data)):
            self.top_bar.logo = pix
        else:
            self.top_bar.logo = None
        self.top_bar.update()
        self.logo_page.update()

    def set_show_bibs(self, show: bool) -> None:
        """Bibs and names, or names only: the two-way form of ``set_rider_label``."""
        self.set_rider_label("bibs_names" if show else "names")

    def set_rider_label(self, mode: str) -> None:
        """How every layout names a rider: names, bibs_names or bibs (design section 10)."""
        for page in self.pages.values():
            page.rider_label = mode
            page.update()

    def set_accent(self, hex_color: str | None) -> None:
        """The venue's accent color, for the whole board at once."""
        t.set_accent(hex_color)
        self.top_bar.update()
        for page in self.pages.values():
            page.update()

    def set_event_name(self, name: str) -> None:
        self.top_bar.event_name = name
        self.top_bar.update()
        self.logo_page.update()

    # Internals ---------------------------------------------------------

    def _notice_eliminations(self, page: EliminationPage, payload) -> None:
        """Flash "Eliminated" only when a rider was added to the out order.

        The order as last shown for this race is the memory, not the
        last-out rider alone: an Undo shortens the order and settles the
        page to "Last out" at once instead of flashing the rider before,
        a race this board has not shown before (a switch to it, or a
        display connected mid-race) shows its order quietly, and the
        same order pushed again (any redraw) leaves a running flash alone.
        """
        out = [*payload.eliminated]
        if payload.last_eliminated is not None:
            out.append(payload.last_eliminated)
        order = tuple(tuple(e.bibs) for e in out)
        race_id = payload.header.race_id
        seen = self._out_seen.get(race_id)
        self._out_seen[race_id] = order
        if seen is not None and order == seen:
            return
        added = seen is not None and len(order) > len(seen) and order[: len(seen)] == seen
        page.fresh = added
        if added:
            self._highlight.start()
        else:
            self._highlight.stop()

    def _settle_elimination(self) -> None:
        page = self.pages["elimination"]
        page.fresh = False
        page.update()

    def _turn_page(self) -> None:
        page = self.pages[self._layout_name]
        if page.data is not None and hasattr(page, "advance"):
            page.advance()

    def _clear_overlay(self) -> None:
        # The TV and the preview are handed one payload object. Clearing
        # the card on it in place would let whichever timer fired first
        # clear it for both, and the other would find nothing to clear and
        # never repaint, so each canvas takes a copy without the card.
        page = self.pages[self._layout_name]
        if getattr(page.data, "sprint_result", None) is not None:
            page.data = dataclasses.replace(page.data, sprint_result=None)
        page.update()

    def _apply_scale(self) -> None:
        u = self.height() / DESIGN_HEIGHT
        self.top_bar.u = u
        self.logo_page.u = u
        self.top_bar.setFixedHeight(round(TOP_BAR_HEIGHT * u))
        for page in self.pages.values():
            page.u = u

    def resizeEvent(self, event) -> None:
        self._apply_scale()
        super().resizeEvent(event)


class ScoreboardWindow(BoardCanvas):
    """The audience board as a top-level window: full screen on the TV.

    Adds placement (``show_on``) and the close and Escape handling to the
    canvas; everything it draws comes from ``BoardCanvas``.
    """

    # The board's close button, or Cmd+W on it, hides the board through
    # the operator window, so the Scoreboard menu's None stays in step.
    # No key hides it: a scorer who Alt-Tabs onto the TV and presses
    # Escape must not take the board down mid-race.
    close_requested = Signal()

    # macOS puts a full-screen window in a Space of its own, entered and
    # left with an animation that ends after the call returns.
    SPACES = sys.platform == "darwin"

    def __init__(
        self,
        venue_name: str = "",
        event_name: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(venue_name, event_name, parent)
        self.setWindowTitle(f"{APP_NAME} Scoreboard")
        self.resize(*WINDOWED_SIZE)
        # Set once the windowed board has a place of its own; after that a
        # person may have moved it, and their spot stands.
        self._windowed_placed = False

    def closeEvent(self, event) -> None:
        # Only a close the person initiated (Qt marks it spontaneous) is
        # forwarded; a programmatic close, from shutdown or the test
        # harness, simply closes.
        if event.spontaneous():
            event.ignore()
            self.close_requested.emit()
            return
        event.accept()

    def show_on(self, screen: QScreen | None, avoid: QRect | None = None) -> None:
        """Fill ``screen``, or open as an ordinary window when it is None.

        ``avoid`` is the operator window's frame: the windowed board is
        placed beside it when the primary screen has room, so setup and
        testing on one laptop do not hide the controls.
        """
        if screen is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            came_from_tv = self.isFullScreen() or self._frameless()
            if self.SPACES and came_from_tv:
                # Leaving a Space animates and ends after this call returns;
                # a window moved or shown normally meanwhile stays full
                # screen, over the scoring window. A new native window starts
                # outside any Space.
                self._new_native_window()
            elif self.isFullScreen() or self.windowState() & Qt.WindowState.WindowFullScreen:
                # Leave full screen first, while still frameless, and only
                # then take the frameless flag off. Qt on Windows saves the
                # window's style on the way into full screen and puts it back
                # on the way out: with the flag changed first, leaving full
                # screen would put the saved frameless style back, and the
                # windowed board would have no title bar to move it by.
                self.showNormal()
            self._set_frameless(False)
            if came_from_tv or not self._windowed_placed:
                self._place_windowed(avoid)
            self.showNormal()
            return
        # The audience never needs a pointer, and a stray one on the TV
        # looks broken.
        self.setCursor(Qt.CursorShape.BlankCursor)
        if self.SPACES:
            if self.isVisible() and self.isFullScreen() and self._screen_name() == screen.name():
                return
            # macOS reuses a window's drawing buffers across displays when
            # their pixel sizes match, whatever their scale: a 960x540
            # window at 2x and a 1920x1080 TV at 1x share buffers, and
            # every other frame reaches the TV drawn at double size. A full
            # screen window also cannot move between Spaces in place. Both
            # need a new native window, whose buffers are all made on the TV.
            if self.isFullScreen() or self.devicePixelRatioF() != screen.devicePixelRatio():
                self._new_native_window()
        else:
            # Frameless as well as full screen: a window manager that ignores
            # the full-screen request, or honors it late, must still never
            # put a title bar across the top of the TV. Not on macOS, where
            # full screen hides the title bar itself, and a frameless window
            # is taken into its Space only by giving it a frame and then
            # taking the frame away again, which leaves the menu bar showing.
            self._set_frameless(True)
        # Moving to the screen before going full screen matters on some
        # Windows setups, which otherwise maximize onto the primary display.
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.showFullScreen()

    def _screen_name(self) -> str | None:
        handle = self.windowHandle()
        here = handle.screen() if handle is not None else None
        return here.name() if here is not None else None

    def _new_native_window(self) -> None:
        """Drop the native window, its buffers, and its Space; the next show makes new ones."""
        self.hide()
        self.destroy()
        self.setWindowState(Qt.WindowState.WindowNoState)

    def _frameless(self) -> bool:
        return bool(self.windowFlags() & Qt.WindowType.FramelessWindowHint)

    def _set_frameless(self, on: bool) -> None:
        # Changing window flags re-creates the native window and hides it,
        # so it is done only when the flag actually changes.
        if self._frameless() != on:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, on)

    def _place_windowed(self, avoid: QRect | None) -> None:
        screen = QGuiApplication.primaryScreen()
        self.resize(*WINDOWED_SIZE)
        self._windowed_placed = True
        if screen is None:
            return
        self.setScreen(screen)
        self.move(windowed_position(screen.availableGeometry(), self.frameGeometry().size(), avoid))
