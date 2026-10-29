"""File names, folders and wording for the results exports.

The files themselves are written by ``madtracker.export``; this module
only decides where they go by default and what the scorer is told.
"""

import os
import re
from html import escape
from pathlib import Path

from madtracker.export.usac_csv import ExportReport
from madtracker.store import Event

# docs/research/usac-results-export.md: Excel rewrites an age group like
# 9-14 as a date (it published as "14-Sep") and USAC rejects or garbles
# the row, so the CSV must go to USAC exactly as written.

# Most general to least: the event, then what the file is, then which
# part, so a folder of exports sorts by night and then by document.
DOCUMENT = {
    "program": "Program.pdf",
    "pdf": "Results - Overall.pdf",
    "csv": "Results - USAC Upload.csv",
}

# Riders named before the rest are counted, so one long line stays short.
NAMES_SHOWN = 5


def documents_dir() -> Path:
    """The user's Documents folder, or home when there is none.

    Exports are documents the scorer emails or uploads, so they belong
    where the scorer looks for files, unlike the database, which must stay
    out of synced folders (store.paths).
    """
    found = _qt_documents()
    if found and Path(found).is_dir():
        return Path(found)
    if os.name == "nt":
        profile = os.environ.get("USERPROFILE")
        base = Path(profile) if profile else Path.home()
    else:
        base = Path.home()
    docs = base / "Documents"
    return docs if docs.is_dir() else base


def _qt_documents() -> str:
    """Qt's Documents folder, or "" when it knows none.

    Qt reads the system's known-folder path, which follows Documents when
    OneDrive's folder backup moves it out of the user profile. It needs no
    application object, so the import stays here and the control layer
    loads without Qt.
    """
    from PySide6.QtCore import QStandardPaths

    return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)


# Each name in a file name stops here, so a long event and race name
# together stay well inside the platforms' 255-character name limit.
NAME_PART_MAX = 80


def _safe(text: str) -> str:
    # Characters Windows refuses in a file name.
    return re.sub(r'[<>:"/\\|?*]+', " ", text).strip()[:NAME_PART_MAX].strip()


def _event(event: Event) -> str:
    return f"{event.event_date} - {_safe(event.name)}"


def default_file_name(event: Event, kind: str) -> str:
    """'2026-10-10 - Race Night 12 - Results - Overall.pdf', or '... - USAC Upload.csv'."""
    return f"{_event(event)} - {DOCUMENT[kind]}"


def race_file_name(event: Event, race_name: str) -> str:
    """'2026-10-10 - Race Night 12 - Results - Points A.pdf': one race's PDF."""
    return f"{_event(event)} - Results - {_safe(race_name)}.pdf"


REPORT_COLUMNS = ("Race", "Discipline", "Category", "Class", "Gender")
CHECK_HEADING = "Things to check before uploading:"


def _report_parts(report: ExportReport) -> tuple[str, list[str], list[str]]:
    """The report's opening line, the races left out, and the things to check, as plain text."""
    count = len(report.race_fields)
    if not count:
        intro = "No race is finished, so the file has only its header row."
    else:
        noun, them = ("race", "it") if count == 1 else ("races", "them")
        intro = f"The file has {count} {noun}, as USAC will file {them}:"
    fixes = list(report.race_notes)
    if report.unlicensed:
        shown = ", ".join(report.unlicensed[:NAMES_SHOWN])
        more = len(report.unlicensed) - NAMES_SHOWN
        fixes.append(f"No USAC License: {shown}" + (f", and {more} more." if more > 0 else "."))
    return intro, list(report.left_out), fixes


def usac_report_text(report: ExportReport) -> str:
    """What Export USAC CSV says after writing: rich text for the message box.

    Each race as USAC files it, the races left out, then what the upload
    would trip on, with nothing else: the scorer chose the file's place.
    """
    intro, left_out, fixes = _report_parts(report)
    parts = [f"<p>{escape(intro)}</p>"]
    if report.race_fields:
        head = "".join(
            f"<th align='left' style='padding-right: 16px'>{h}</th>" for h in REPORT_COLUMNS
        )
        body = "".join(
            "<tr>"
            + "".join(f"<td style='padding-right: 16px'>{escape(cell)}</td>" for cell in row)
            + "</tr>"
            for row in report.race_fields
        )
        parts.append(f"<table cellspacing='0' cellpadding='4'><tr>{head}</tr>{body}</table>")
    if left_out:
        names = ", ".join(escape(n) for n in left_out)
        parts.append(f"<p><b>Not finished, so not in the file:</b> {names}.</p>")
    if fixes:
        items = "".join(f"<li>{escape(f)}</li>" for f in fixes)
        parts.append(f"<p><b>{CHECK_HEADING}</b></p><ul>{items}</ul>")
    return "".join(parts)


def usac_report_plain(report: ExportReport) -> str:
    """The same report as plain text, for Copy: the races tab-separated, so they paste as a table."""
    intro, left_out, fixes = _report_parts(report)
    lines = [intro]
    if report.race_fields:
        lines += ["\t".join(REPORT_COLUMNS), *("\t".join(row) for row in report.race_fields)]
    if left_out:
        lines += ["", f"Not finished, so not in the file: {', '.join(left_out)}."]
    if fixes:
        lines += ["", CHECK_HEADING, *(f"- {f}" for f in fixes)]
    return "\n".join(lines) + "\n"
