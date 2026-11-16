"""The board's texture engine: a shape tiled in a staggered grid."""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage

from madtracker.board import texture, theme

# An invented shape: the venue's own mark never enters the repository.
CHEVRON = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    b'<path d="M0 0 L50 0 L100 50 L50 100 L0 100 L50 50 Z" fill="#f00"/></svg>'
)


def _alpha(image: QImage, x: int, y: int) -> int:
    w, h = image.width(), image.height()
    return image.pixelColor(x % w, y % h).alpha()


def _chevron() -> texture.Texture:
    svg = texture.first_shape_svg(CHEVRON)
    assert svg is not None
    return texture.Texture(svg)


def test_the_builtin_tile_is_a_stroke_at_the_boards_slant(qapp):
    tex = texture.Texture(None)
    assert tex.builtin
    cell = tex.cell(1.0, 1.0)
    h = texture.TILE_H

    def span(y: int) -> tuple[int, int]:
        xs = [x for x in range(cell.width()) if cell.pixelColor(x, y).alpha() > 128]
        return xs[0], xs[-1]

    top, foot = span(2), span(h - 3)
    lean = top[0] - foot[0]
    assert abs(lean - theme.SLANT * (h - 5)) <= 2


def test_a_venue_shape_tiles_in_a_staggered_grid(qapp):
    tex = _chevron()
    assert not tex.builtin
    cell = tex.cell(1.0, 1.0)
    h = texture.TILE_H
    w = h  # the chevron's box is square
    assert abs(cell.width() - texture.PITCH_X * w) <= 1
    assert abs(cell.height() - 2 * texture.PITCH_Y * h) <= 1
    # Ink sits inside each of the two shapes' boxes and between them is empty.
    assert _alpha(cell, 5, 5) > 0
    sx, sy = round(texture.PITCH_X * w / 2), round(texture.PITCH_Y * h)
    assert _alpha(cell, sx + 5, sy + 5) > 0
    assert _alpha(cell, sx + 5, 5) == 0
    # The image is a white mask whatever the SVG's own colors are.
    assert cell.pixelColor(5, 5).rgb() == QColor("white").rgb()


def test_any_shape_tiles_at_the_tile_height(qapp):
    shapes = {
        "wide": b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 50"><rect width="1000" height="50"/></svg>',
        "tall": b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 1000"><rect width="50" height="1000"/></svg>',
        "offset": b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-300 -200 600 400"><rect x="-300" y="-200" width="300" height="400"/></svg>',
        "grouped": b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><g transform="translate(10,20) scale(2,1)"><path d="M0 0H10V40H0Z"/></g></svg>',
    }
    for name, data in shapes.items():
        svg = texture.first_shape_svg(data)
        assert svg is not None, name
        tex = texture.Texture(svg)
        assert not tex.builtin, name
        cell = tex.cell(1.0, 1.0)
        ys = [y for y in range(cell.height()) if cell.pixelColor(2, y).alpha() > 128]
        # Column 2 crosses the shape at the origin (or its wrap-around).
        assert ys, name
        rows = [
            y
            for y in range(cell.height())
            if any(cell.pixelColor(x, y).alpha() > 128 for x in range(0, cell.width(), 2))
        ]
        height = max(rows) - min(rows) + 1
        assert height > 0
        assert cell.width() > 0
        assert abs(cell.height() - 2 * texture.PITCH_Y * texture.TILE_H) <= 1


def test_the_grouped_shape_keeps_its_parents_transform(qapp):
    svg = texture.first_shape_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        b'<g transform="scale(2,1)"><path d="M0 0H10V40H0Z"/></g></svg>'
    )
    cell = texture.Texture(svg).cell(1.0, 1.0)
    # 20 by 40 units: half as wide as tall.
    assert abs(cell.width() - texture.PITCH_X * texture.TILE_H / 2) <= 1


def test_first_shape_rejects_hostile_and_empty_svgs(qapp):
    ns = 'xmlns="http://www.w3.org/2000/svg"'
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE s [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        f'<svg {ns}><path d="M0 0H1V1Z" id="&b;"/></svg>'
    ).encode()
    external = (
        '<?xml version="1.0"?><!DOCTYPE s [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        f'<svg {ns}><path d="M0 0H1V1Z" id="&x;"/></svg>'
    ).encode()
    for data in (
        b"<svg " + b" " * texture.MAX_SVG_BYTES + b"/>",
        b"<svg><path",
        bomb,
        external,
        f'<svg {ns}><path d="M0 0H1V1Z" fill="none"/></svg>'.encode(),
        f"<svg {ns}><g/></svg>".encode(),
        b"",
    ):
        assert texture.first_shape_svg(data) is None


def test_an_unusable_svg_falls_back_to_the_builtin(qapp):
    empty = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0 0" /></svg>'
    assert texture.Texture(b"not svg").builtin
    assert texture.Texture(texture.first_shape_svg(empty)).builtin


def test_the_brush_keeps_its_pattern_fixed_to_the_origin(qapp):
    tex = texture.Texture(None)
    brush = tex.brush(1.0, 1.0, QColor(255, 0, 0, 90), QPointF(37, 11))
    t = brush.transform()
    assert (t.dx(), t.dy()) == (37, 11)
    tinted = brush.textureImage()
    ink = [
        tinted.pixelColor(x, y)
        for x in range(tinted.width())
        for y in range(tinted.height())
        if tinted.pixelColor(x, y).alpha() > 0
    ]
    assert ink
    assert all(c.alpha() <= 90 and c.red() > 0 and c.green() == 0 for c in ink)


def test_cells_and_brushes_are_cached(qapp, monkeypatch):
    tex = texture.Texture(None)
    built = []
    draw = tex._draw_shape
    monkeypatch.setattr(tex, "_draw_shape", lambda *a: (built.append(1), draw(*a)))
    a = tex.cell(1.0, 1.0)
    count = len(built)
    assert tex.cell(1.0, 1.0) is a
    assert len(built) == count
    tex.cell(2.0, 1.0)
    assert len(built) > count
