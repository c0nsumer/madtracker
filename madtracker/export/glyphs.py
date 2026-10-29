"""Which letters the PDF sheets can draw, without loading the PDF writer.

The sheets set every name in the bundled Inter. A name field asks as the
scorer types, so this reads only the font's character table, and only
for text that is not plain printable ASCII, which Inter draws whole.
"""

import functools

from madtracker.assets import fonts

# Joiners and other marks that draw nothing on their own.
SILENT = frozenset((0x200C, 0x200D, 0x034F, 0x20E3))


def missing(ch: str, glyphs: frozenset[int]) -> bool:
    """True for a character the sheet's font lacks and that would draw something."""
    code = ord(ch)
    if code in glyphs or ch in " \t":
        return False
    return not (code in SILENT or 0xFE00 <= code <= 0xFE0F)


@functools.cache
def font_glyphs() -> frozenset[int] | None:
    """The code points the sheets' regular face draws, or None when it is not bundled."""
    path = fonts.font_path(400)
    if not path.is_file():
        return None
    from fontTools.ttLib import TTFont

    with TTFont(str(path), lazy=True) as face:
        return frozenset(face.getBestCmap())


def prints(text: str) -> bool:
    """True when the PDF sheets draw every letter of ``text``.

    The sheets' own rule, asked of a name as it is typed, so the scorer
    hears that a name will print with a "?" before the export says so.
    """
    if text.isascii() and text.isprintable():
        return True
    glyphs = font_glyphs()
    return glyphs is None or not any(missing(ch, glyphs) for ch in text)
