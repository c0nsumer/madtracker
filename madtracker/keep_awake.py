"""Keep the displays awake while the program runs.

A race night has long stretches with no keyboard or mouse input, and the
scoreboard is a second display nobody touches at all. The operating
system's idle timer would blank both. Each platform has its own request
for "someone is watching, do not blank the screen":

- Windows: SetThreadExecutionState with ES_DISPLAY_REQUIRED and
  ES_SYSTEM_REQUIRED, held by the main thread.
- macOS: an IOKit power assertion of type PreventUserIdleDisplaySleep.
- Linux: the freedesktop ScreenSaver Inhibit call over the session D-Bus
  (KDE, Xfce and others). GNOME does not offer it, and its own Inhibit
  call takes unsigned integers, which PySide6's D-Bus binding cannot
  send; a GNOME machine keeps its own idle timer.

The request is made once and never withdrawn: every platform drops it
when the process ends, crash included, so there is nothing to release
and no way to leave a machine unable to sleep. A refused request changes
nothing else. The scorer can still turn the display timeout off in the
power settings, and a message box at every start on a desktop without
the service would be noise.
"""

import sys

REASON = "Scoring a race; the scoreboard is on"

# Windows SetThreadExecutionState flags (winbase.h).
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def hold(app_name: str) -> bool:
    """Ask the system to keep the displays on until the process ends; False when refused."""
    try:
        if sys.platform == "win32":
            return _hold_windows()
        if sys.platform == "darwin":
            return _hold_macos(app_name)
        return _hold_dbus(app_name)
    except Exception:  # a missing library or service must not stop the program
        return False


def _hold_windows(kernel32=None) -> bool:
    if kernel32 is None:
        import ctypes

        kernel32 = ctypes.windll.kernel32
    # A zero return is the call's only failure signal.
    return bool(
        kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED)
    )


def _hold_macos(app_name: str) -> bool:
    import ctypes
    import ctypes.util

    iokit = ctypes.cdll.LoadLibrary(ctypes.util.find_library("IOKit"))
    cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    iokit.IOPMAssertionCreateWithName.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    utf8 = 0x08000100  # kCFStringEncodingUTF8
    kind = cf.CFStringCreateWithCString(None, b"PreventUserIdleDisplaySleep", utf8)
    name = cf.CFStringCreateWithCString(None, f"{app_name}: {REASON}".encode(), utf8)
    assertion = ctypes.c_uint32(0)
    try:
        # 255 is kIOPMAssertionLevelOn; 0 is kIOReturnSuccess.
        status = iokit.IOPMAssertionCreateWithName(kind, 255, name, ctypes.byref(assertion))
    finally:
        cf.CFRelease(kind)
        cf.CFRelease(name)
    return status == 0


def _hold_dbus(app_name: str) -> bool:
    from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False
    screensaver = QDBusInterface(
        "org.freedesktop.ScreenSaver",
        "/org/freedesktop/ScreenSaver",
        "org.freedesktop.ScreenSaver",
        bus,
    )
    if not screensaver.isValid():
        return False
    # The inhibit lives as long as this bus connection, which is the
    # process's own shared session connection.
    reply = screensaver.call("Inhibit", app_name, REASON)
    return reply.type() == QDBusMessage.MessageType.ReplyMessage
