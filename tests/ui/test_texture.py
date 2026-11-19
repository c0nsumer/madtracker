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
    tex = texture.make_texture("slant", None)
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
    tex = texture.make_texture("slant", None)
    brush = tex.brush(1.0, 1.0, QColor(255, 0, 0, 90), QPointF(37, 11))
    t = brush.transform()
    assert (t.dx(), t.dy()) == (37, 11)
    assert t.isTranslating() and not t.isRotating()
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

    tex = texture.make_texture("slant", None)
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
    tex = texture.make_texture("slant", None)
    built = []
    draw = tex._draw_shape
    monkeypatch.setattr(tex, "_draw_shape", lambda *a: (built.append(1), draw(*a)))
    a = tex.cell(1.0, 1.0)
    count = len(built)
    assert tex.cell(1.0, 1.0) is a
    assert len(built) == count
    tex.cell(2.0, 1.0)
    assert len(built) > count


def test_the_caches_keep_only_the_latest_scales(qapp):
    """A preview resized step by step makes a scale per step; only the latest few are kept."""
    tex = texture.make_texture("slant", None)
    for k in range(3 * texture.CACHE_KEPT):
        u = 0.5 + k / 100
        tex.cell(u, 1.0)
        tex.brush(u, 1.0, QColor("white"), QPointF(0, 0))
    assert len(tex._cells) == len(tex._brushes) == texture.CACHE_KEPT
    newest = 0.5 + (3 * texture.CACHE_KEPT - 1) / 100
    assert (newest, 1.0) in tex._cells


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


def test_a_shape_keeps_no_filter(qapp):
    """A filter is a render of its own on every cell, and the mask is the
    shape's outline alone."""
    blurred = (
        f'<svg {NS} viewBox="0 0 10 10"><defs><filter id="f">'
        '<feGaussianBlur stdDeviation="2"/></filter></defs>'
        '<g style="filter:url(#f);opacity:1"><rect width="9" height="9" filter="url(#f)"/></g></svg>'
    ).encode()
    out = texture.first_shape_svg(blurred)
    assert out is not None and b"filter" not in out and b"feGaussianBlur" not in out
    assert b"opacity:1" in out
    assert not texture.Texture(out).builtin


def test_a_stored_shape_past_the_size_settings_accepts_draws_the_default_pattern(qapp):
    svg = texture.first_shape_svg(CHEVRON)
    padded = svg + b" " * (texture.MAX_SVG_BYTES + 1 - len(svg))
    default = texture.make_texture(texture.DEFAULT_PATTERN, None).cell(1.0, 1.0)
    tex = texture.make_texture("venue", padded)
    assert tex.builtin and tex.cell(1.0, 1.0) == default


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
    cell = texture.make_texture("slant", None).cell(200.0, 1.0)
    assert max(cell.width(), cell.height()) <= texture.MAX_CELL_PX


def _tex(pattern: str = "slant") -> texture.Texture:
    made = texture.make_texture(pattern, None)
    assert made is not None
    return made


def test_patterns_list_reads_as_approved():
    assert texture.PATTERNS == (
        ("slant", "Slant Strokes"),
        ("chevrons", "Chevrons"),
        ("dots", "Dots"),
        ("none", "None"),
    )
    assert texture.DEFAULT_PATTERN == "slant"
    assert texture.pattern_svg("none") is None and texture.pattern_svg("venue") is None
    assert texture.pattern_svg("swirls") is None


def test_every_bundled_pattern_tiles(qapp):
    for key in ("slant", "chevrons", "dots"):
        svg = texture.pattern_svg(key)
        assert svg is not None, key
        tex = texture.make_texture(key, None)
        assert tex is not None and tex.builtin, key
        cell = tex.cell(1.0, 1.0)
        assert any(
            cell.pixelColor(x, y).alpha() > 0
            for x in range(0, cell.width(), 2)
            for y in range(0, cell.height(), 2)
        ), key


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


def test_none_draws_no_texture(qapp):
    assert texture.make_texture("none", None) is None
    assert texture.make_texture("none", CHEVRON) is None
    base = QColor("#c03030")
    assert _paint(None, base) != _paint(_tex("dots"), base)


def test_venue_unknown_and_missing_patterns(qapp):
    svg = texture.first_shape_svg(CHEVRON)
    venue = texture.make_texture("venue", svg)
    assert venue is not None and not venue.builtin
    default = texture.make_texture(texture.DEFAULT_PATTERN, None).cell(1.0, 1.0)
    for key in ("nonsense", "swirls"):
        tex = texture.make_texture(key, None)
        assert tex.builtin and tex.cell(1.0, 1.0) == default, key
    assert texture.make_texture("venue", None).cell(1.0, 1.0) == default


def test_every_pattern_tiles_within_the_cell_cap_at_any_scale(qapp):
    for key in ("slant", "chevrons", "dots"):
        tex = _tex(key)
        for u, dpr in ((1.0, 1.0), (3.0, 2.0), (200.0, 1.0)):
            cell = tex.cell(u, dpr)
            assert 0 < cell.width() <= texture.MAX_CELL_PX
            assert 0 < cell.height() <= texture.MAX_CELL_PX
        tex.brush(1.0, 1.0, QColor("white"), QPointF(5, 5))


def test_dots_are_a_fine_grain_beside_the_slant_strokes(qapp):
    stroke, dot = _tex("slant").cell(1.0, 1.0), _tex("dots").cell(1.0, 1.0)
    assert dot.height() < stroke.height() / 3
    venue = texture.make_texture("venue", texture.first_shape_svg(CHEVRON))
    assert abs(venue.cell(1.0, 1.0).height() - 2 * texture.PITCH_Y * texture.TILE_H) <= 1
