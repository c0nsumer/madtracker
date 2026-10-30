"""Files bundled with the app: the default scoreboard wordmark and the icons.

The scoreboard logo is a per-venue setting (an image chosen in Settings
and kept in the data file); this package only supplies a neutral
default, the app's own wordmark drawn by tools/make_logo.py, so the
published app carries no venue's trademark. The venue's
own wordmark is kept outside the repo (local/,
gitignored) and chosen through Settings.
"""

import sys
from importlib.resources import files
from pathlib import Path

DEFAULT_LOGO = "placeholder-wordmark.png"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
# The icon's rainbow, red to violet, shared by tools/make_icons.py and the
# splash screen so the two never drift. Each hue is pulled toward gray a
# little: full-saturation primaries look like a toy, and a pure yellow
# washes the white glyph out.
RAINBOW = ("#d9504a", "#e3893b", "#d9b43c", "#4ea66b", "#3d7fc0", "#7a5bb0")


def bundled_logo_path(name: str = DEFAULT_LOGO) -> Path:
    """Filesystem path of a bundled logo.

    importlib.resources keeps this correct inside a PyInstaller bundle,
    where __file__-relative paths are the classic packaging bug.
    """
    return Path(str(files("madtracker.assets").joinpath("logos", name)))


def app_icon():
    """The app icon as a QIcon with every rendered size.

    Qt picks the right size for the title bar, the taskbar, the dock and
    the alt-tab switcher, which is why the PNGs are shipped at all sizes
    rather than one large one scaled down.
    """
    from PySide6.QtGui import QIcon

    icon = QIcon()
    icons_dir = files("madtracker.assets").joinpath("icons")
    for size in ICON_SIZES:
        icon.addFile(str(icons_dir.joinpath(f"madtracker-{size}.png")))
    return icon


def sets_window_icon(platform: str | None = None, frozen: bool | None = None) -> bool:
    """Whether the app should set Qt's window icon at startup.

    Not in the packaged macOS app: there Qt hands the window icon to the
    Dock as the running app's icon, which would replace the bundle's own
    (Icon Composer, drawn by the system the size of its neighbors) with
    the edge-to-edge PNGs, and the Dock would draw MadTracker larger than
    every other app. Mac windows have no title-bar icon, so nothing else
    uses it there. Windows and Linux need it for their title bars and
    taskbars.
    """
    platform = sys.platform if platform is None else platform
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    return not (platform == "darwin" and frozen)
