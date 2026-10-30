"""What each platform needs for the app's name and icon."""

import sys


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
