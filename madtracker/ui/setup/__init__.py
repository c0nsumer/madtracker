"""Edit Event: the event, the roster, the program, top to bottom (design section 6).

Every edit is written through at once; nothing waits on a Save button
that might be forgotten before the first race. A refused edit puts the
old value back and says why on the part's message line. The dialogs
(a rider, an import preview, a race with its field and teams) write on
their own OK, and the screen reloads from the store after each.

The screen and each family of dialogs live in their own module; this
package names what the app and the tests reach for.
"""

from PySide6.QtWidgets import QLabel, QPushButton, QTableWidget, QTableWidgetItem

from madtracker.control.groups import event_spellings
from madtracker.ui import style
from madtracker.ui.setup.events import (
    CopyFileDialog,
    ExportPdfDialog,
    NewEventDialog,
    OpenEventDialog,
)
from madtracker.ui.setup.groups import GroupsDialog, NewGroupDialog, RenameGroupDialog
from madtracker.ui.setup.importing import (
    ACTION,
    DETAILS,
    P_BIB,
    P_GROUP,
    USE,
    ImportPreview,
    ReconcileDialog,
)
from madtracker.ui.setup.race import MAX_COUNT, PALETTE, RaceDialog, TeamDialog
from madtracker.ui.setup.riders import (
    KEEP_PAGE,
    M_MATCH,
    PICK,
    MergeDialog,
    RiderForm,
    RidersDialog,
)
from madtracker.ui.setup.screen import (
    AGE,
    BIB,
    FIRST,
    GROUP,
    LAST,
    PROGRAM_HEADERS,
    PROGRAM_MIN_ROWS,
    PROGRAM_SHORT_ROWS,
    ROSTER_MIN_ROWS,
    SetupScreen,
    race_number,
)
from madtracker.ui.widgets import ID_ROLE, UNPRINTABLE_NOTE, selected_id

__all__ = [
    "ACTION",
    "AGE",
    "BIB",
    "DETAILS",
    "FIRST",
    "GROUP",
    "ID_ROLE",
    "KEEP_PAGE",
    "LAST",
    "MAX_COUNT",
    "M_MATCH",
    "PALETTE",
    "PICK",
    "PROGRAM_HEADERS",
    "PROGRAM_MIN_ROWS",
    "PROGRAM_SHORT_ROWS",
    "P_BIB",
    "P_GROUP",
    "QLabel",
    "QPushButton",
    "QTableWidget",
    "QTableWidgetItem",
    "ROSTER_MIN_ROWS",
    "UNPRINTABLE_NOTE",
    "USE",
    "CopyFileDialog",
    "ExportPdfDialog",
    "GroupsDialog",
    "ImportPreview",
    "MergeDialog",
    "NewEventDialog",
    "NewGroupDialog",
    "OpenEventDialog",
    "RaceDialog",
    "ReconcileDialog",
    "RenameGroupDialog",
    "RiderForm",
    "RidersDialog",
    "SetupScreen",
    "TeamDialog",
    "event_spellings",
    "race_number",
    "selected_id",
    "style",
]
