"""Where the live database lives.

The database must sit on a local, non-synced disk, which rules out the
three places a scorer would naturally put it:

- Next to the exe. The portable zip may be unpacked anywhere, including a
  USB stick, and the installer puts the exe in a folder the installer
  later overwrites.
- Under Documents or Desktop. OneDrive's Known Folder Move redirects
  those into a sync folder, and a sync client that copies or locks a live
  SQLite file with a -wal side file produces errors or bad copies.
- On a USB stick. Flash drives are the devices most likely to lie about
  having flushed their write cache, which defeats synchronous=FULL.

So the default is the per-user local application data folder:
%LOCALAPPDATA%\\MadTracker on Windows, ~/Library/Application Support/
MadTracker on macOS (iCloud Drive syncs Desktop and Documents, not this
folder), $XDG_DATA_HOME/madtracker (or ~/.local/share/madtracker)
elsewhere. The MADTRACKER_DATA_DIR environment
variable overrides it for tests and for a deliberately portable setup.

The folder name is a literal, not APP_NAME: renaming the app must not
move the scorer's data out from under them.
"""

import os
import sys
from pathlib import Path

DATA_DIR_ENV = "MADTRACKER_DATA_DIR"
DATABASE_FILE_NAME = "madtracker.sqlite"
BACKUP_DIR_NAME = "backups"


def default_data_dir() -> Path:
    """Return the directory that holds the live database and its backups.

    The directory is not created here; opening the database creates it,
    so that merely asking for the path has no side effects.
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        base_path = Path(base) if base else Path.home() / "AppData" / "Local"
        return base_path / "MadTracker"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MadTracker"
    xdg = os.environ.get("XDG_DATA_HOME")
    base_path = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base_path / "madtracker"


def default_database_path() -> Path:
    """Return the live database file path inside the data directory."""
    return default_data_dir() / DATABASE_FILE_NAME
