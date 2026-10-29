"""The startup splash: the right size, sharp at 2x, and not an empty frame."""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from madtracker.ui import splash


def test_splash_pixmap_is_logical_size_at_twice_the_pixels(qapp):
    pix = splash.splash_pixmap()
    assert pix.devicePixelRatio() == 2.0
    assert (pix.width(), pix.height()) == (splash.WIDTH * 2, splash.HEIGHT * 2)
    assert pix.deviceIndependentSize().toSize().width() == splash.WIDTH


def test_splash_pixmap_draws_the_icon_and_the_band(qapp):
    image = splash.splash_pixmap().toImage()
    background = QColor(splash.BACKGROUND).rgb()
    # The icon's center and a point on the rainbow band both differ from
    # the plain background; a missing icon file would leave the first blank.
    icon_center = image.pixel(splash.WIDTH, (54 + splash.ICON_PX // 2) * 2)
    band = image.pixel(splash.WIDTH, (splash.HEIGHT - 1 - splash.BAND_PX // 2) * 2)
    assert icon_center != background
    assert band != background
    # The name is drawn: some pixel in its row is dark ink.
    name_row = (54 + splash.ICON_PX + 18 + 20) * 2
    assert any(QColor(image.pixel(x, name_row)).lightness() < 80 for x in range(image.width()))


def test_splash_shows_and_finishes_offscreen(qapp):
    shown = splash.show_splash(qapp)
    window = QWidget()
    window.show()
    shown.finish(window)
    assert not shown.isVisible()
    window.close()
