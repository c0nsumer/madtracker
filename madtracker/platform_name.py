"""Make the process present itself as the app, not as "Python".

On Windows the fix is an explicit AppUserModelID for the taskbar (see
_claim_windows_app_id).

On macOS a script run from a venv executes inside the Python framework's
own application bundle, so the menu bar and the dock say "Python" with
the Python icon. The dock icon follows the Qt window icon, but the menu
bar name comes from the bundle's CFBundleName, which only Cocoa can
change, and only before the application menu is built. PyObjC is an
optional extra (``pip install -e ".[macos]"``); without it the name stays
"Python" and nothing else changes. A packaged .app carries its own name
and does not need any of this. Other platforms take the name from the
Qt application name and the window titles.
"""

import sys


def claim_process_name(name: str) -> bool:
    """Return True when the macOS bundle name was changed."""
    if sys.platform == "win32":
        return _claim_windows_app_id(name)
    if sys.platform != "darwin":
        return False
    try:
        from Foundation import NSBundle
    except ImportError:
        return False
    try:
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info is None:
            return False
        info["CFBundleName"] = name
        info["CFBundleDisplayName"] = name
        return True
    except Exception:
        # Cosmetic: a failure here must never stop the app from starting.
        return False


def _claim_windows_app_id(name: str) -> bool:
    """Give the process its own taskbar identity on Windows, when run from a venv.

    Run from a venv, the process is python.exe, so the taskbar groups it
    under Python and shows the Python icon even after setWindowIcon. An
    explicit AppUserModelID set before any window exists makes the
    taskbar use the window's own icon and group the app by itself.

    The packaged exe must not set one. Windows resolves a taskbar group's
    icon through the AppUserModelID: an explicit one needs a Start Menu
    shortcut carrying the same ID, and without it Windows 11 draws the
    combined button as a blank window over the two MadTracker windows.
    Left alone, Windows derives the ID
    from the exe path, as it does for every ordinary installed program,
    and the group takes the exe's own icon.
    """
    if getattr(sys, "frozen", False):
        return False
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"MadTracker.{name}")
        return True
    except (AttributeError, OSError):
        return False


def sets_window_icon(platform: str | None = None, frozen: bool | None = None) -> bool:
    """Whether the app should set Qt's window icon at startup.

    Not in the packaged macOS app: there Qt hands the window icon to the
    Dock as the running app's icon, which would replace the bundle's own
    (Icon Composer, drawn by the system the size of its neighbors) with
    the edge-to-edge PNGs, and the Dock would draw MadTracker larger than
    every other app. Mac windows have no title-bar icon, so
    nothing else uses it there. Run from a venv on a Mac it is still set,
    or the Dock shows Python's icon; Windows and Linux need it for their
    title bars and taskbars.
    """
    platform = sys.platform if platform is None else platform
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    return not (platform == "darwin" and frozen)
