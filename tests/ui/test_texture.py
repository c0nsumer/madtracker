"""The board's texture engine: a shape tiled in a staggered grid."""

import math

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
    tex = texture.make_texture("slant", None, texture.Adjust())
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
        "wide": b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 50"><rect width="300" height="50"/></svg>',
        "tall": b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 300"><rect width="50" height="300"/></svg>',
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
    tex = texture.make_texture("slant", None, texture.Adjust())
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


def test_the_brush_paints_the_cell_pixel_for_pixel_at_any_pixel_ratio(qapp):
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QPainter

    tex = texture.make_texture("slant", None, texture.Adjust())
    for dpr in (1.0, 1.5, 2.0):
        img = QImage(round(300 * dpr), round(150 * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.GlobalColor.black)
        p = QPainter(img)
        p.fillRect(QRectF(0, 0, 300, 150), tex.brush(1.0, dpr, QColor("white"), QPointF(0, 0)))
        p.end()
        cell = tex.cell(1.0, dpr)
        for y in range(0, img.height(), 2):
            for x in range(0, img.width(), 2):
                a = _alpha(cell, x, y)
                if a in (0, 255):
                    assert abs(img.pixelColor(x, y).red() - a) <= 8, (dpr, x, y)


def test_cells_and_brushes_are_cached(qapp, monkeypatch):
    tex = texture.make_texture("slant", None, texture.Adjust())
    built = []
    draw = tex._draw_shape
    monkeypatch.setattr(tex, "_draw_shape", lambda *a: (built.append(1), draw(*a)))
    a = tex.cell(1.0, 1.0)
    count = len(built)
    assert tex.cell(1.0, 1.0) is a
    assert len(built) == count
    tex.cell(2.0, 1.0)
    assert len(built) > count


NS = 'xmlns="http://www.w3.org/2000/svg"'
REAL = '<circle cx="50" cy="50" r="40" id="real"/>'


def _picked(body: str) -> bytes | None:
    return texture.first_shape_svg(f'<svg {NS} viewBox="0 0 100 100">{body}</svg>'.encode())


def test_the_first_visible_filled_shape_is_taken(qapp):
    cases = {
        "defs": f'<defs><path d="M0 0H9V9Z"/></defs>{REAL}',
        "clip": f'<defs><clipPath id="c"><rect width="9" height="9"/></clipPath></defs>{REAL}',
        "mask": f'<mask id="m"><rect width="9" height="9"/></mask>{REAL}',
        "symbol": f'<symbol id="s"><rect width="9" height="9"/></symbol>{REAL}',
        "none attr": f'<path d="M0 0H9V9Z" fill="none"/>{REAL}',
        "none style": f'<path d="M0 0H9V9Z" style="fill:none;stroke:#000"/>{REAL}',
        "inherited attr": f'<g fill="none"><rect width="9" height="9"/></g>{REAL}',
        "inherited style": f'<g style="fill: none"><rect width="9" height="9"/></g>{REAL}',
        "hidden": f'<rect width="9" height="9" display="none"/>{REAL}',
    }
    for name, body in cases.items():
        out = _picked(body)
        assert out is not None, name
        assert b'r="40" id="tile"' in out, name


def test_a_document_with_filled_shapes_only_in_definitions_is_refused(qapp):
    assert _picked('<defs><clipPath id="c"><rect width="9" height="9"/></clipPath></defs>') is None
    assert (
        _picked(
            '<defs><rect width="9" height="9"/></defs><g fill="none"><rect width="9" height="9"/></g>'
        )
        is None
    )


def test_a_filled_child_of_an_unfilled_group_is_taken(qapp):
    assert _picked('<g fill="none"><rect width="50" height="50" fill="#000"/></g>') is not None


def test_a_very_wide_shape_is_refused_quickly_and_a_wide_one_tiles(qapp):
    import time

    wide = f'<svg {NS} viewBox="0 0 200 1"><rect width="200" height="1"/></svg>'.encode()
    start = time.perf_counter()
    assert texture.first_shape_svg(wide) is None
    assert texture.Texture(wide).builtin
    assert time.perf_counter() - start < 1
    six = f'<svg {NS} viewBox="0 0 60 10"><rect width="60" height="10"/></svg>'.encode()
    svg = texture.first_shape_svg(six)
    assert svg is not None
    tex = texture.Texture(svg)
    assert not tex.builtin
    assert tex.cell(1.0, 1.0).width() > 0


def test_a_cell_side_is_capped(qapp):
    cell = texture.make_texture("slant", None, texture.Adjust()).cell(200.0, 1.0)
    assert max(cell.width(), cell.height()) <= texture.MAX_CELL_PX


def _tex(pattern: str = "slant", **adjust) -> texture.Texture:
    made = texture.make_texture(pattern, None, texture.Adjust(**adjust))
    assert made is not None
    return made


def test_patterns_list_reads_as_approved():
    assert texture.PATTERNS == (
        ("bolts", "Lightning Bolts"),
        ("slant", "Slant Strokes"),
        ("chevrons", "Chevrons"),
        ("dots", "Dots"),
        ("none", "None"),
    )
    assert texture.DEFAULT_PATTERN == "bolts"
    assert texture.pattern_svg("none") is None and texture.pattern_svg("venue") is None


def test_every_bundled_pattern_tiles(qapp):
    for key in ("bolts", "slant", "chevrons", "dots"):
        svg = texture.pattern_svg(key)
        assert svg is not None, key
        tex = texture.make_texture(key, None, texture.Adjust())
        assert tex is not None and tex.builtin, key
        cell = tex.cell(1.0, 1.0)
        assert any(
            cell.pixelColor(x, y).alpha() > 0
            for x in range(0, cell.width(), 2)
            for y in range(0, cell.height(), 2)
        ), key


def _run(cell: QImage) -> int:
    """The inked length of the cell's top row of shapes, left to right."""
    y = round(texture.TILE_H / 2)
    line = [cell.pixelColor(x, y).alpha() > 0 for x in range(cell.width())]
    first = line.index(True)
    end = first
    while end < len(line) and line[end]:
        end += 1
    return end - first


def test_size_and_spacing_scale_the_cell(qapp):
    base = _tex("dots").cell(1.0, 1.0)
    big = _tex("dots", size=150).cell(1.0, 1.0)
    assert abs(big.width() - 1.5 * base.width()) <= 2
    assert abs(big.height() - 1.5 * base.height()) <= 2
    wide = _tex("dots", spacing=140).cell(1.0, 1.0)
    assert abs(wide.width() - 1.4 * base.width()) <= 2
    assert abs(wide.height() - 1.4 * base.height()) <= 2
    # Spacing moves the shapes apart without resizing them: the first dot
    # is as wide in a spread cell as in the base one.
    assert abs(_run(wide) - _run(base)) <= 2


def test_rotation_turns_the_pattern_about_the_row(qapp):
    origin = QPointF(37, 11)
    flat = _tex("slant").brush(1.0, 1.0, QColor("white"), origin)
    turned = _tex("slant", rotation=30).brush(1.0, 1.0, QColor("white"), origin)
    assert (flat.transform().dx(), flat.transform().dy()) == (37, 11)
    t = turned.transform()
    # The row's origin stays put under the turn.
    mapped = t.map(QPointF(0, 0))
    assert (round(mapped.x()), round(mapped.y())) == (37, 11)
    assert abs(t.m12() - math.sin(math.radians(30))) < 1e-6
    assert abs(t.m11() - math.cos(math.radians(30))) < 1e-6
    assert flat.transform().m12() == 0


def _paint(tex: texture.Texture, base: QColor) -> QImage:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainter

    from madtracker.board import team_rows

    img = QImage(900, 120, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("#101820"))
    p = QPainter(img)
    team_rows.paint_band(
        p, QRectF(0, 10, 880, 100), base.name(), 1.0, sweep=1.0, slant=theme.SLANT, texture=tex
    )
    p.end()
    return img


def test_opacity_and_tone_change_the_drawn_texture_not_the_row(qapp):
    base = QColor("#c03030")
    plain = _paint(_tex("dots", opacity=100), base)
    dark = _paint(_tex("dots", tone=-100), base)
    light = _paint(_tex("dots", tone=100), base)
    strong = _paint(_tex("dots", opacity=200), base)
    ys, xs = range(12, 108, 2), range(60, 800, 2)

    def lum(img, x, y):
        return img.pixelColor(x, y).lightness()

    inked = [(x, y) for x in xs for y in ys if plain.pixelColor(x, y) != strong.pixelColor(x, y)]
    assert inked
    assert sum(lum(dark, x, y) for x, y in inked) < sum(lum(plain, x, y) for x, y in inked)
    assert sum(lum(light, x, y) for x, y in inked) > sum(lum(plain, x, y) for x, y in inked)
    # Where no shape lies, the band is the band whatever the tone.
    bare = [(x, y) for x in xs for y in ys if (x, y) not in set(inked)]
    same = sum(1 for x, y in bare if dark.pixelColor(x, y) == light.pixelColor(x, y))
    assert same / len(bare) > 0.5
    spots = [(x, y) for x, y in bare if dark.pixelColor(x, y) == light.pixelColor(x, y)]
    assert all(dark.pixelColor(x, y) == plain.pixelColor(x, y) for x, y in spots)


def test_none_and_zero_opacity_draw_no_texture(qapp):
    assert texture.make_texture("none", None, texture.Adjust()) is None
    assert texture.make_texture("bolts", None, texture.Adjust(opacity=0)) is None
    assert texture.make_texture("venue", CHEVRON, texture.Adjust(opacity=0)) is None
    base = QColor("#c03030")
    assert _paint(None, base) != _paint(_tex("dots"), base)


def test_venue_unknown_and_missing_patterns(qapp):
    svg = texture.first_shape_svg(CHEVRON)
    venue = texture.make_texture("venue", svg, texture.Adjust())
    assert venue is not None and not venue.builtin
    assert texture.make_texture("venue", None, texture.Adjust()).builtin
    assert texture.make_texture("nonsense", None, texture.Adjust()).builtin


def test_adjust_clamps_and_tone_mixes_toward_black_and_white():
    a = texture.Adjust(size=500, rotation=-90, spacing=0, opacity=999, tone=-500).clamped()
    assert (a.size, a.rotation, a.spacing, a.opacity, a.tone) == (200, -45, 60, 200, -100)
    assert texture.SIZE == (50, 200) and texture.TONE == (-100, 100)
    tex = _tex("dots", tone=-100)
    assert tex.fade_color(QColor(200, 100, 50)).rgb() == QColor(0, 0, 0).rgb()
    assert (
        _tex("dots", tone=100).fade_color(QColor(200, 100, 50)).rgb() == QColor(255, 255, 255).rgb()
    )
    mid = _tex("dots", tone=50).fade_color(QColor(200, 100, 50))
    assert (mid.red(), mid.green(), mid.blue()) == (228, 178, 152)
    assert abs(_tex("dots", opacity=150).fade_share - texture.FADE_SHARE * 1.5) < 1e-9
    assert abs(_tex("dots", opacity=150).solid_alpha - texture.SOLID_ALPHA * 1.5) < 1e-9


def test_adjust_extremes_tile_without_error_and_within_the_cell_cap(qapp):
    for key in ("bolts", "slant", "chevrons", "dots"):
        for size, spacing in ((200, 60), (50, 60), (200, 200), (50, 200)):
            for rotation in (-45, 45):
                tex = _tex(key, size=size, spacing=spacing, rotation=rotation)
                for u, dpr in ((1.0, 1.0), (3.0, 2.0), (200.0, 1.0)):
                    cell = tex.cell(u, dpr)
                    assert 0 < cell.width() <= texture.MAX_CELL_PX
                    assert 0 < cell.height() <= texture.MAX_CELL_PX
                tex.brush(1.0, 1.0, QColor("white"), QPointF(5, 5))
