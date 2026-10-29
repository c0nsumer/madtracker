"""Render the placeholder wordmark PNG: the bike glyph and the app name.

The bundled default logo must not be a venue's trademark, since the
app is published for any venue. The scoreboard draws the wordmark
itself, as vectors (madtracker/board/wordmark.py); this PNG is the same
drawing for the places that need an image: the PDF results band and the
Settings preview. White on transparent, 1200 by 215 pixels (a bit under
6 to 1), the ink centered vertically with the glyph's left edge 10
pixels in. A venue replaces it through Settings.

Run from the repo root with the venv active:

    python tools/make_logo.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "madtracker" / "assets" / "logos" / "placeholder-wordmark.png"
WIDTH, HEIGHT = 1200, 215


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter

    QGuiApplication(sys.argv)
    from madtracker.board import wordmark

    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    ink = HEIGHT * wordmark.CANVAS_INK
    wordmark.paint(painter, QRectF(10, (HEIGHT - ink) / 2, WIDTH - 20, ink))
    painter.end()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(OUT))
    print(f"wrote {OUT.relative_to(ROOT)} ({WIDTH}x{HEIGHT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
