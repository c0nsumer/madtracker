"""Render the app icon from madtracker/assets/icons/bike.svg.

Writes PNGs at the sizes Windows, macOS and Qt ask for, a multi-size
Windows .ico for the PyInstaller build, and a .icns for the macOS
bundle. Run from the repo root with the venv active:

    python tools/make_icons.py

Outputs:

    madtracker/assets/icons/madtracker-{16..1024}.png  (app_icon(), About, splash)
    packaging/madtracker.iconset/icon_*.png  (the macOS build's iconutil input)
    packaging/madtracker.icon/  (Icon Composer bundle: icon.json and two layers)
    packaging/madtracker.ico   (Windows exe: 16, 24, 32, 48, 64, 256)
    packaging/madtracker.icns  (macOS .app bundle, from the 1024 render)

The icon is the white bike on a rounded square (corner radius 22% of the
side, the modern app-icon shape) filled with a diagonal rainbow, red at
the top left through violet at the bottom right. The hues are muted a
little so the tile reads warm rather than toy-like next to the other
apps in a taskbar, and a faint dark edge plus a soft shadow under the
glyph keep the white bike legible over the light yellow band at 16 px.
The ICO is packed by hand because Qt's ICO writer stores one image per
file; Windows accepts PNG-compressed entries in an ICO since Vista.

The .icns is the tile on a larger transparent canvas (render_macos):
macOS draws every app icon on a 1024 canvas whose tile is 824 wide, so a
tile that fills its canvas sits in the Dock a sixth larger than its
neighbors. Windows and the
app's own uses keep the edge-to-edge tile. The macOS build prefers an
.icns made on the Mac by iconutil from the .iconset written here (every
size Apple lists, 16 to 512 with @2x), since macOS 27 draws Qt's
single-image .icns edge to edge all the same.

The .icon bundle is Apple's newer format (Icon Composer, macOS 26 and
up): full-bleed square layers that the system masks, sizes, and gives its
glass, so the Dock draws it as it draws its neighbors. It is written here
on any platform; only compiling it (actool, Xcode 26) needs a Mac, and
packaging/compile_macos_icon.sh does that for the build and for the
check a person runs (tools/check_macos_icon.sh).
"""

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "madtracker" / "assets" / "icons"
SVG = ICONS / "bike.svg"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
ICO_SIZES = (16, 24, 32, 48, 64, 256)

# The checkout's own package, not whatever an editable install points at.
sys.path.insert(0, str(ROOT))
from madtracker.assets import RAINBOW  # noqa: E402


def render(size: int):
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
    from PySide6.QtSvg import QSvgRenderer

    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    radius = size * 0.22
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    # The sweep starts and ends inside the tile: run corner to corner, the
    # red and the violet would only fill the rounded-off corners.
    sweep = QLinearGradient(QPointF(size * 0.15, size * 0.15), QPointF(size * 0.85, size * 0.85))
    for i, hue in enumerate(RAINBOW):
        sweep.setColorAt(i / (len(RAINBOW) - 1), QColor(hue))
    painter.fillPath(path, sweep)
    # A shade that deepens toward the bottom gives the tile some depth and
    # wins back contrast under the glyph's wheels.
    shade = QLinearGradient(QPointF(0, 0), QPointF(0, size))
    shade.setColorAt(0.0, QColor(0, 0, 0, 0))
    shade.setColorAt(1.0, QColor(0, 0, 0, 46))
    painter.fillPath(path, shade)
    # The faint edge separates the tile from a white or light-gray
    # taskbar, where the yellow band would otherwise blur into it.
    edge = max(1.0, size / 64)
    painter.setPen(QPen(QColor(0, 0, 0, 44), edge))
    half = edge / 2
    painter.drawRoundedRect(
        QRectF(half, half, size - edge, size - edge), radius - half, radius - half
    )
    # Small renders get a smaller margin: at 16 px every pixel of glyph
    # counts for more than the breathing room around it.
    inset = size * (0.10 if size <= 24 else 0.14)
    box = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    # The MDI glyph carries no fill, which renders black; the fill is
    # injected here rather than editing the upstream file. The black pass,
    # offset down a little, is the soft shadow that lifts the white bike.
    text = SVG.read_text(encoding="utf-8")
    shadow = QSvgRenderer(text.replace("<path ", '<path fill="#000000" ', 1).encode("utf-8"))
    painter.setOpacity(0.24)
    shadow.render(painter, box.translated(0, max(1.0, size / 48)))
    painter.setOpacity(1.0)
    glyph = QSvgRenderer(text.replace("<path ", '<path fill="#ffffff" ', 1).encode("utf-8"))
    glyph.render(painter, box)
    painter.end()
    return image


# Apple's app-icon grid: the tile is 824 of the 1024 canvas, centered,
# with a soft shadow under it that the Dock shows over its glass.
MACOS_TILE = 824 / 1024
MACOS_SHADOW_ALPHA = 48


def render_macos(size: int):
    """The tile centered on a transparent canvas with the Dock's margins and shadow."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

    tile = round(size * MACOS_TILE)
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    origin = (size - tile) / 2
    radius = tile * 0.22
    # The shadow: a few rounded rects, each a little larger and fainter,
    # offset down, in place of a blur Qt's painter cannot do on its own.
    for step in range(1, 5):
        grow = step * size * 0.004
        drop = size * 0.012
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(origin - grow, origin - grow + drop, tile + 2 * grow, tile + 2 * grow),
            radius + grow,
            radius + grow,
        )
        painter.fillPath(path, QColor(0, 0, 0, MACOS_SHADOW_ALPHA // step))
    painter.drawImage(QRectF(origin, origin, tile, tile), render(tile))
    painter.end()
    return image


# The Icon Composer canvas, in pixels: every layer is drawn on it full size.
ICON_CANVAS = 1024


def render_background(size: int):
    """The tile's rainbow and shade, square and full bleed: the system adds the shape."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    rect = QRectF(0, 0, size, size)
    sweep = QLinearGradient(QPointF(size * 0.15, size * 0.15), QPointF(size * 0.85, size * 0.85))
    for i, hue in enumerate(RAINBOW):
        sweep.setColorAt(i / (len(RAINBOW) - 1), QColor(hue))
    painter.fillRect(rect, sweep)
    shade = QLinearGradient(QPointF(0, 0), QPointF(0, size))
    shade.setColorAt(0.0, QColor(0, 0, 0, 0))
    shade.setColorAt(1.0, QColor(0, 0, 0, 46))
    painter.fillRect(rect, shade)
    painter.end()
    return image


def render_glyph(size: int):
    """The white bike alone on a transparent canvas, placed as on the tile.

    No drop shadow: the system draws the glass and its own shadow.
    """
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    inset = size * 0.14
    text = SVG.read_text(encoding="utf-8")
    glyph = QSvgRenderer(text.replace("<path ", '<path fill="#ffffff" ', 1).encode("utf-8"))
    glyph.render(painter, QRectF(inset, inset, size - 2 * inset, size - 2 * inset))
    painter.end()
    return image


# icon.json as Icon Composer saves it: groups front first, each with its
# layers; the system's shadow on both groups. The bike is a flat, opaque
# glyph: with translucency and the specular highlight on, macOS 26 lights
# the white rings from above, and in the app switcher the wheels look
# thicker at the top and bottom than at the sides.
# The schema is Apple's and undocumented: the Mac-side compile is the
# check.
ICON_JSON = {
    "groups": [
        {
            "layers": [{"image-name": "bike.png", "name": "bike"}],
            "shadow": {"kind": "neutral", "opacity": 0.5},
            "specular": False,
            "translucency": {"enabled": False, "value": 0.5},
        },
        {
            "layers": [{"image-name": "background.png", "name": "background"}],
            "shadow": {"kind": "neutral", "opacity": 0.5},
            "translucency": {"enabled": False, "value": 0.5},
        },
    ],
    "supported-platforms": {"circles": ["watchOS"], "squares": "shared"},
}


def write_icon_composer(folder: Path) -> None:
    """packaging/madtracker.icon: icon.json and its two layers under Assets/."""
    import json

    assets = folder / "Assets"
    assets.mkdir(parents=True, exist_ok=True)
    render_background(ICON_CANVAS).save(str(assets / "background.png"))
    render_glyph(ICON_CANVAS).save(str(assets / "bike.png"))
    text = json.dumps(ICON_JSON, indent=2, sort_keys=True) + "\n"
    (folder / "icon.json").write_text(text, encoding="utf-8")


# The names iconutil wants: a point size and its 2x, 16 to 512.
ICONSET_POINTS = (16, 32, 128, 256, 512)


def write_iconset(folder: Path) -> None:
    """The padded renders under Apple's names, for ``iconutil -c icns`` on the Mac."""
    folder.mkdir(parents=True, exist_ok=True)
    for points in ICONSET_POINTS:
        render_macos(points).save(str(folder / f"icon_{points}x{points}.png"))
        render_macos(points * 2).save(str(folder / f"icon_{points}x{points}@2x.png"))


def write_ico(path: Path, pngs: dict[int, bytes]) -> None:
    entries = sorted(pngs.items())
    header = struct.pack("<HHH", 0, 1, len(entries))
    directory = b""
    offset = len(header) + 16 * len(entries)
    blobs = b""
    for size, data in entries:
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    path.write_bytes(header + directory + blobs)


def main() -> int:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QGuiApplication

    QGuiApplication(sys.argv)
    pngs: dict[int, bytes] = {}
    for size in SIZES:
        image = render(size)
        image.save(str(ICONS / f"madtracker-{size}.png"))
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        pngs[size] = bytes(buf.data())
    write_ico(ROOT / "packaging" / "madtracker.ico", {s: pngs[s] for s in ICO_SIZES})
    render_macos(1024).save(str(ROOT / "packaging" / "madtracker.icns"))
    write_iconset(ROOT / "packaging" / "madtracker.iconset")
    write_icon_composer(ROOT / "packaging" / "madtracker.icon")
    print(
        f"wrote {len(SIZES)} PNGs, packaging/madtracker.ico, packaging/madtracker.icns,"
        " packaging/madtracker.iconset, packaging/madtracker.icon"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
