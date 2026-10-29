"""The plain-text log beside the data file.

A scorer's report is "around 8:40 it did something odd", and the boxes
the app shows are read once and gone. The log keeps what support needs
to answer that: the session (version, system, Qt, data file, displays),
every failure box and red-line refusal, each backup written or failed,
slow commits, an unclean-close recovery, and the traceback of anything
unexpected. The packaged program is windowed and has no console, so
without this file a bug in a click leaves no trace at all.

It sits beside the data file, where the backups are, so "send me the
data folder" collects everything at once. It is rotated at about 1 MB
with one old copy kept: a season of nights is a few hundred kilobytes,
and a runaway error cannot fill the disk the data file lives on.
Writing the log never raises: a log that cannot be written must not
take a click down with it.
"""

import logging
import logging.handlers
import platform
import sys
import traceback
from pathlib import Path

from madtracker import APP_NAME, __version__

LOG_NAME = "madtracker.log"
MAX_BYTES = 1_000_000
_LOGGER = logging.getLogger("madtracker")
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False
_state: dict = {"handler": None, "path": None}


class _QuietHandler(logging.handlers.RotatingFileHandler):
    """A rotating file that drops a record it cannot write rather than printing to stderr."""

    def handleError(self, record) -> None:
        # A full disk, a pulled stick or (on Windows) a second window
        # holding the file during rotation: the record is lost, nothing more.
        return


def use_folder(folder: Path | None) -> Path | None:
    """Write the log in ``folder`` from now on; the log's path, or None when there is none.

    Called whenever a data file is opened, so the log follows the file.
    """
    target = None if folder is None else Path(folder) / LOG_NAME
    if target is not None and target == _state["path"]:
        return target
    old = _state["handler"]
    if old is not None:
        _LOGGER.removeHandler(old)
        try:
            old.close()
        except OSError:
            pass
    _state["handler"] = None
    _state["path"] = None
    if target is None:
        return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = _QuietHandler(
            target, maxBytes=MAX_BYTES, backupCount=1, encoding="utf-8", delay=True
        )
    except OSError:
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _LOGGER.addHandler(handler)
    _state["handler"] = handler
    _state["path"] = target
    return target


def log_path() -> Path | None:
    return _state["path"]


def info(text: str) -> None:
    _LOGGER.info(text)


def warning(text: str) -> None:
    _LOGGER.warning(text)


def error(text: str) -> None:
    _LOGGER.error(text)


def flush() -> None:
    handler = _state["handler"]
    if handler is not None:
        try:
            handler.flush()
        except OSError:
            pass


def traceback_text(exc_type, exc, tb) -> str:
    return "".join(traceback.format_exception(exc_type, exc, tb)).rstrip()


def session_start(data_file: Path, displays: list[str]) -> None:
    """The first lines of a session: enough to tell builds and machines apart."""
    try:
        from PySide6 import __version__ as pyside
        from PySide6.QtCore import qVersion

        qt = f"Qt {qVersion()}, PySide6 {pyside}"
    except ImportError:
        qt = "Qt unknown"
    info(
        f"{APP_NAME} {__version__} started; {platform.platform()}; Python "
        f"{sys.version.split()[0]}; {qt}"
    )
    info(f"Data file: {data_file}")
    info("Displays: " + ("; ".join(displays) if displays else "none found"))
