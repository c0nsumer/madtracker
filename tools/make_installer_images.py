"""Render the pictures the Windows installer shows: the welcome panel and the header mark.

Inno Setup's modern wizard puts a tall picture on the Welcome and Finished
pages and a small one in the header of every other page. Both are plain
bitmaps, which the build draws here from the app icon and the bundled
typeface rather than committing: at the five sizes Inno Setup matches to
the display scale, the set runs to a megabyte and would change with every
touch of the icon. build_windows.ps1 runs this before the installer is
compiled; installer.iss picks the files up when they exist. Run by hand
from the repo root with the venv active:

    python tools/make_installer_images.py

Outputs, under packaging/wizard/ (gitignored):

    welcome-<w>x<h>.bmp   202x386, 269x515, 336x643, 403x772, 430x824,
                          498x953, 534x1022
    header-<n>x<n>.bmp    58, 77, 97, 116, 124, 143, 159 square

The sizes are Inno Setup's own list (6.6.0 and later) for WizardImageFile
and WizardSmallImageFile at 100% to 250% display scale. Inno Setup picks
the closest and stretches it to fill the area, so a picture whose shape
differs from the area comes out squashed: the header area is square, and
the welcome area keeps the 164:314 shape.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packaging" / "wizard"
WELCOME_SIZES = (
    (202, 386),
    (269, 515),
    (336, 643),
    (403, 772),
    (430, 824),
    (498, 953),
    (534, 1022),
)
HEADER_SIZES = (58, 77, 97, 116, 124, 143, 159)
TAGLINE = "Scoring for track cycling events"

# The checkout's own package and the icon tool beside this one.
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_icons import render  # noqa: E402

from madtracker import APP_NAME  # noqa: E402
from madtracker.ui import style  # noqa: E402


def _canvas(w: int, h: int):
    from PySide6.QtGui import QColor, QImage, QPainter

    # No alpha: the wizard's pages are white, and Inno Setup's bitmap loader
    # wants a plain 24-bit picture anyway.
    image = QImage(w, h, QImage.Format.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    return image, painter


def _tile(painter, size: int, x: float, y: float) -> None:
    """Draw the app icon's rounded tile at ``size``, drawn fresh at that size so its edge stays crisp."""
    from PySide6.QtCore import QPointF

    painter.drawImage(QPointF(x, y), render(size))


def _text_path(text: str, weight, px: float):
    from PySide6.QtGui import QFont, QPainterPath

    from madtracker.ui.look import available_families

    font = QFont()
    font.setFamilies(available_families())
    font.setPixelSize(round(px))
    font.setWeight(weight)
    path = QPainterPath()
    path.addText(0, 0, font, text)
    return path


def _draw_centered(painter, path, cx: float, baseline: float, color: str) -> None:
    from PySide6.QtGui import QColor

    bounds = path.boundingRect()
    painter.save()
    painter.translate(cx - bounds.center().x(), baseline)
    painter.fillPath(path, QColor(color))
    painter.restore()


def welcome(w: int, h: int):
    """The tall panel: the tile over the name and a one-line tagline, all sized from the width."""
    from PySide6.QtGui import QFont

    image, painter = _canvas(w, h)
    tile = round(w * 0.52)
    top = h * 0.17
    _tile(painter, tile, (w - tile) / 2, top)
    # The name fills most of the width; the tagline sits under it in the
    # dim ink the window uses for secondary text.
    name_px = w * 0.155
    name = _text_path(APP_NAME, QFont.Weight.Black, name_px)
    while name.boundingRect().width() > w * 0.84:
        name_px *= 0.96
        name = _text_path(APP_NAME, QFont.Weight.Black, name_px)
    name_base = top + tile + name_px * 1.35
    _draw_centered(painter, name, w / 2, name_base, style.INK)
    # The tagline keeps the name's margin, so neither line runs nearer the
    # panel's edge than the other.
    tag_px = name_px * 0.46
    tag = _text_path(TAGLINE, QFont.Weight.Normal, tag_px)
    while tag.boundingRect().width() > w * 0.84:
        tag_px *= 0.96
        tag = _text_path(TAGLINE, QFont.Weight.Normal, tag_px)
    _draw_centered(painter, tag, w / 2, name_base + name_px * 0.78, style.DIM)
    painter.end()
    return image


def header(n: int):
    """The small header mark: the tile alone, centered in the square area."""
    image, painter = _canvas(n, n)
    # The area sits hard against the wizard's top-right corner; the white
    # margin keeps the tile from touching the page edge and the title text.
    tile = round(n * 0.8)
    _tile(painter, tile, (n - tile) / 2, (n - tile) / 2)
    painter.end()
    return image


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    QGuiApplication(sys.argv)
    from madtracker.ui.look import register_fonts

    register_fonts()
    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for w, h in WELCOME_SIZES:
        welcome(w, h).save(str(OUT / f"welcome-{w}x{h}.bmp"), "BMP")
        written += 1
    for n in HEADER_SIZES:
        header(n).save(str(OUT / f"header-{n}x{n}.bmp"), "BMP")
        written += 1
    print(f"wrote {written} bitmaps under {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
