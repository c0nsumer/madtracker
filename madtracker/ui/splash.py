"""The splash shown while the data file opens and the windows are built.

Opening the venue file, running the backup and building both windows
takes a moment on a slow laptop, and an older scorer who sees nothing
after a double-click tends to click again. The splash answers at once
with the icon, the name and the version on the window's own light
background, with a thin band of the icon's rainbow along the bottom.
"""

from importlib.resources import files

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from madtracker import APP_NAME, __version__
from madtracker.assets import RAINBOW
from madtracker.ui.look import available_families

WIDTH, HEIGHT = 480, 300
ICON_PX = 96
BAND_PX = 6
BACKGROUND = "#f3f4f6"
BORDER = "#c3c9d2"
INK = "#11151b"
MUTED = "#5b6472"
# Painted at twice the logical size so it stays sharp at 150% and 200%
# scaling; Qt scales it down on a 100% display, which costs nothing.
PIXEL_RATIO = 2.0


def _font(px: int, bold: bool) -> QFont:
    font = QFont()
    font.setFamilies(available_families())
    font.setPixelSize(px)
    font.setBold(bold)
    return font


def splash_pixmap(ratio: float = PIXEL_RATIO) -> QPixmap:
    """The splash art, WIDTH x HEIGHT logical pixels at ``ratio``."""
    pix = QPixmap(round(WIDTH * ratio), round(HEIGHT * ratio))
    pix.setDevicePixelRatio(ratio)
    pix.fill(QColor(BACKGROUND))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # A splash has no window frame, so the border is what keeps it from
    # melting into a white desktop or a maximized white window behind it.
    p.setPen(QPen(QColor(BORDER), 1))
    p.drawRect(QRectF(0.5, 0.5, WIDTH - 1, HEIGHT - 1))
    band = QLinearGradient(QPointF(0, 0), QPointF(WIDTH, 0))
    for i, hue in enumerate(RAINBOW):
        band.setColorAt(i / (len(RAINBOW) - 1), QColor(hue))
    p.fillRect(QRectF(1, HEIGHT - 1 - BAND_PX, WIDTH - 2, BAND_PX), band)

    # The largest shipped render, drawn down to ICON_PX, so the art is
    # the icon itself and not a second drawing that could drift from it.
    icon = QPixmap(str(files("madtracker.assets").joinpath("icons", "madtracker-512.png")))
    top = 54
    p.drawPixmap(QRectF((WIDTH - ICON_PX) / 2, top, ICON_PX, ICON_PX), icon, QRectF(icon.rect()))

    p.setPen(QColor(INK))
    p.setFont(_font(30, bold=True))
    name_top = top + ICON_PX + 18
    p.drawText(
        QRectF(0, name_top, WIDTH, 40),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
        APP_NAME,
    )
    p.setPen(QColor(MUTED))
    p.setFont(_font(14, bold=False))
    p.drawText(
        QRectF(0, name_top + 42, WIDTH, 22),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
        f"Version {__version__}",
    )
    p.end()
    return pix


def show_splash(app: QApplication) -> QSplashScreen:
    """Show the splash and paint it now, before the slow work starts."""
    from madtracker.ui.widgets import center_on_screen

    splash = QSplashScreen(splash_pixmap())
    center_on_screen(splash)
    splash.show()
    # Without this the event loop has not run yet, and the splash would
    # stay an empty frame until the main window replaces it.
    app.processEvents()
    return splash
