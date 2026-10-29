"""The bundled typeface: Inter 4.1, static TrueType, SIL OFL 1.1.

The window, the scoreboard and the results PDF all draw with this one
face, shipped with the app, rather than whatever the machine has. Two
reasons. First, identical metrics on Windows, macOS and Linux: a column
that fits a name on one laptop fits it on every laptop, and a layout
checked on Linux is the layout the scorer sees. Second, PDF/A-2B forbids
the PDF core fonts and needs an embeddable TrueType file, and a file we
ship is one whose embedding permission (fsType 0, installable) and glyph
coverage we know. A per-machine search for Arial, Liberation Sans and
DejaVu Sans would give a different sheet on every machine and none at
all on a Linux box without those packages.

Inter was chosen by comparing mockups of the window, the board and the
sheet: its tall x-height and open shapes read well at a distance and for
scorers who are often older. The scoreboard uses its Bold and Black
weights rather than a separate display family. Inter's default figures
are proportional; the board asks for tabular figures (tnum) where a
column of numbers must not shimmer.

Family names, as read from the name tables: Regular and Bold carry the
family "Inter"; Medium, SemiBold and Black carry the legacy family
"Inter <Weight>" with the typographic family "Inter". Qt reports both
names for those three files but lists all five styles under "Inter"
(Regular, Medium, SemiBold, Bold, Black), so callers ask for
QFont(FAMILY) with a weight, never for "Inter SemiBold" by name (that
name is what Windows GDI would show and it does not hold across
platforms).

This module imports no Qt at the top so the PDF exporter and the
self-test can use it without a GUI stack loaded.
"""

from importlib.resources import files
from pathlib import Path

FAMILY = "Inter"
LICENSE_FILE = "LICENSE-Inter.txt"

# weight (CSS / OS/2 usWeightClass) -> file.
_FILES = {
    400: "Inter-Regular.ttf",
    500: "Inter-Medium.ttf",
    600: "Inter-SemiBold.ttf",
    700: "Inter-Bold.ttf",
    900: "Inter-Black.ttf",
}
FILES = tuple(_FILES.values())


def fonts_dir() -> Path:
    """The folder holding the bundled font files.

    importlib.resources keeps this right inside a PyInstaller bundle,
    where __file__-relative paths are the classic packaging bug.
    """
    return Path(str(files("madtracker.assets").joinpath("fonts")))


def font_path(weight: int = 400) -> Path:
    """The TrueType file for ``weight`` (400 regular, 700 bold, and so on).

    A weight that is not bundled raises KeyError rather than quietly
    substituting another, so a typo shows up in tests and not on paper.
    """
    return fonts_dir() / _FILES[weight]


def all_paths() -> list[Path]:
    return [fonts_dir() / name for name in FILES]


def register_with_qt() -> list[str]:
    """Add every bundled file to Qt's font database; return the families.

    Call once after the QApplication exists and before any widget picks
    a font. A file Qt refuses (missing or unreadable) is skipped, so the
    returned list is what is actually available and the caller can
    decide what a short list means.
    """
    from PySide6.QtGui import QFontDatabase

    families: list[str] = []
    for path in all_paths():
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        for family in QFontDatabase.applicationFontFamilies(font_id):
            if family not in families:
                families.append(family)
    return families
