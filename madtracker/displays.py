"""Which screen the audience scoreboard goes on.

Pure logic with no Qt import, so the rules are unit-tested on any machine
without a display. The board module turns ``QGuiApplication.screens()``
into ``ScreenInfo`` values and maps the answer back to a ``QScreen``.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenInfo:
    """One display as Qt reports it, in logical pixels."""

    name: str
    x: int
    y: int
    w: int
    h: int
    is_primary: bool = False
    # What the menus show. The name stays the stored key because it is
    # stable across runs; Windows names a monitor "\\.\\DISPLAY1", which
    # tells a scorer nothing, so the label comes from the monitor's own
    # make and model when the driver reports them.
    label: str = ""

    @property
    def shown(self) -> str:
        return self.label or self.name


# The Scoreboard menu is one list of where the board goes: Automatic,
# each display with what the board would be there, then None, which is
# the board off: one list, no Display submenu and no Show Scoreboard
# switch. "Automatic (Second Display)" on a laptop with no second
# display would read as a promise of one.
AUTOMATIC = "Automatic"
NONE_LABEL = "None"
# The key the menu sends for None, beside a display's name or None for
# Automatic.
NO_DISPLAY = "none"
# What the board is on a display: full screen on any other, a window
# beside the controls on the scoring window's own.
FULL_SCREEN = "Full Screen"
WINDOWED = "Windowed"


def friendly_label(
    name: str, manufacturer: str, model: str, w: int, h: int, is_primary: bool, index: int
) -> str:
    """A label a scorer can match to the monitor in front of them."""
    make = manufacturer.strip()
    kind = model.strip()
    if kind and make and kind.lower().startswith(make.lower()):
        make = ""
    base = " ".join(part for part in (make, kind) if part)
    if not base:
        stripped = name.replace("\\\\.\\", "").replace("\\", "")
        if stripped.upper().startswith("DISPLAY") and stripped[7:].isdigit():
            base = f"Display {int(stripped[7:])}"
        else:
            base = stripped or f"Display {index + 1}"
    tag = " (Primary)" if is_primary else ""
    return f"{base}, {w}x{h}{tag}"


def choose_scoreboard_screen(
    screens: list[ScreenInfo], preferred_name: str | None
) -> ScreenInfo | None:
    """Return the screen the scoreboard should fill, or None.

    The operator's stored pick wins when that display is connected, even if
    it is the primary one, because only the operator knows how the venue is
    cabled. Otherwise the first non-primary screen is the TV: on the venue
    laptop the built-in panel is primary and HDMI is the extension. None
    means a single display, where the scoreboard must not cover the
    operator window, so the caller opens it as an ordinary movable window.
    """
    if preferred_name:
        for screen in screens:
            if screen.name == preferred_name:
                return screen
    for screen in screens:
        if not screen.is_primary:
            return screen
    return None


def screen_label(screen: ScreenInfo, here: str | None = None) -> str:
    """A display's menu entry: its name and what the board would be there.

    ``here`` is the scoring window's display, where the board can only
    be a window.
    """
    mode = WINDOWED if here is not None and screen.name == here else FULL_SCREEN
    return f"{screen.shown} ({mode})"
