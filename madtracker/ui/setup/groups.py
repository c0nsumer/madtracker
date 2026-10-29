"""Edit Groups: the event's groups, with New Group and Rename Group."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTableWidget, QVBoxLayout, QWidget

from madtracker.control import groups as group_rules
from madtracker.control.groups import event_spellings, group_key
from madtracker.store import Store, StoreError
from madtracker.ui import icons, style
from madtracker.ui.setup._shared import _fit_side, _refusal_line, _refuse
from madtracker.ui.widgets import (
    ID_ROLE,
    GroupCombo,
    NameDialog,
    align_header,
    apply_style,
    close_on_shortcut,
    enter_activates,
    fit_to_screen,
    friendly_error,
    input_item,
    run_dialog,
    setup_table,
    why_label,
    with_why,
)


class NewGroupDialog(NameDialog):
    """A name for a group with nobody in it yet; ``made`` is the name as stored."""

    def __init__(self, store: Store, event_id: int, parent: QWidget | None = None):
        super().__init__("New Group", "Add", self._take, placeholder="Group A", parent=parent)
        self.store = store
        self.event_id = event_id
        self.name = self.field
        self.made: str | None = None

    def _take(self, text: str) -> str | None:
        try:
            self.made = group_rules.add_group(self.store, self.event_id, text)
        except (StoreError, ValueError) as exc:
            return friendly_error(self.store, exc)
        return None


class RenameGroupDialog(NameDialog):
    """A new name for a group; another group's name merges the two, after a question.

    ``made`` is the name the group has afterwards (the merged-into
    group's spelling for a merge).
    """

    def __init__(
        self,
        store: Store,
        event_id: int,
        use: group_rules.GroupUse,
        parent: QWidget | None = None,
        *,
        confirm: bool = True,
    ):
        combo = GroupCombo()
        others = [
            g for g in event_spellings(store, event_id) if group_key(g) != group_key(use.label)
        ]
        combo.addItems(sorted(others, key=str.casefold))
        combo.setCurrentText(use.label)
        combo.setToolTip("Type a new name, or pick a group to merge into")
        super().__init__(f"Rename {use.label}", "Rename", self._take, field=combo, parent=parent)
        self.store = store
        self.event_id = event_id
        self.use = use
        self.confirm = confirm
        self.made: str | None = None
        self.group = combo

    def _take(self, new: str) -> str | None:
        use = self.use
        into = next(
            (
                u
                for u in group_rules.group_uses(self.store, self.event_id)
                if group_key(u.label) != group_key(use.label)
                and group_key(u.label) == group_key(new)
            ),
            None,
        )
        if into is not None and self.confirm:
            one = len(use.riders) == 1
            riders = f"{len(use.riders)} rider{'' if one else 's'} {'joins' if one else 'join'}"
            question = f"Merge {use.label} into {into.label}? Its {riders} {into.label}."
            if not icons.ask(self, "Merge Groups", question, verb="Merge"):
                return ""
        try:
            self.made = group_rules.rename_group(self.store, self.event_id, use, new)
        except (StoreError, ValueError) as exc:
            return friendly_error(self.store, exc)
        return None


# The column after the group's name.
GROUP_RIDERS = 1


class GroupsDialog(QDialog):
    """The event's groups as a list: how many riders each has, which races use it.

    As text typed on each rider, a slip would make a new group nobody
    saw and a fix would mean retyping every rider. Here
    each group is one row, and New group is where one is made before
    anyone is in it; the roster's Group cell then picks it. Rename changes it on its riders and on the
    races made from it, and a name the event already has merges the two.
    The rules follow the races: a group a scored race ran under keeps
    its name ("Has raced"), and one a race was made from is not deleted
    ("Used by a race"); each says so under its button, as the Riders window does.
    """

    def __init__(self, store: Store, event_id: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.event_id = event_id
        self.uses: list[group_rules.GroupUse] = []
        self.changed = False
        self.setWindowTitle(f"Edit Groups: {store.event(event_id).name}")
        fit_to_screen(self, 640, 380)
        apply_style(self)
        close_on_shortcut(self)
        self.table = QTableWidget()
        setup_table(self.table, ["Group", "Riders", "Races"])
        align_header(self.table, GROUP_RIDERS, Qt.AlignmentFlag.AlignHCenter)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        enter_activates(self.table, self.rename_selected)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.new = QPushButton("New Group...")
        self.new.clicked.connect(lambda: self.new_group())
        self.rename = QPushButton("Rename...")
        self.rename.clicked.connect(lambda: self.rename_selected())
        self.delete = QPushButton("Delete")
        self.delete.setObjectName("danger")
        self.delete.clicked.connect(lambda: self.delete_selected())
        self.rename_why = why_label()
        self.delete_why = why_label()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        self.status = _refusal_line()
        side = QVBoxLayout()
        side.setSpacing(style.SM)
        side.addWidget(self.new)
        side.addLayout(with_why(self.rename, self.rename_why))
        side.addSpacing(style.XL - style.SM)
        side.addLayout(with_why(self.delete, self.delete_why))
        side.addStretch(1)
        side.addWidget(close)
        side.setContentsMargins(0, 0, 0, 0)
        side_box = QWidget()
        side_box.setLayout(side)
        body = QHBoxLayout()
        body.addWidget(self.table, 1)
        body.addWidget(side_box)
        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addWidget(self.status)
        buttons = [self.new, self.rename, self.delete, close]
        # Enter on a row is the row's: the table passes it up, and an
        # auto-default button would take it as New Group....
        for b in buttons:
            b.setAutoDefault(False)
        _fit_side(side_box, buttons)
        self.refresh()

    def refresh(self, select: str | None = None) -> None:
        self.uses = group_rules.group_uses(self.store, self.event_id)
        self.table.setRowCount(len(self.uses))
        for row, use in enumerate(self.uses):
            races = ", ".join(r.name for r in use.races)
            for col, text in enumerate((use.label, str(len(use.riders)), races)):
                item = input_item(text, editable=False)
                item.setData(ID_ROLE, row)
                if col == GROUP_RIDERS:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
        rows = [r for r, u in enumerate(self.uses) if select and same_label(u.label, select)]
        if rows or self.uses:
            self.table.selectRow(rows[0] if rows else 0)
        self._update_buttons()

    def selected(self) -> "group_rules.GroupUse | None":
        row = self.table.currentRow()
        return self.uses[row] if 0 <= row < len(self.uses) else None

    def select_group(self, label: str) -> None:
        for row, use in enumerate(self.uses):
            if same_label(use.label, label):
                self.table.selectRow(row)

    def _update_buttons(self) -> None:
        use = self.selected()
        rename = group_rules.rename_refusal(use) if use else ""
        delete = group_rules.delete_refusal(use) if use else ""
        self.rename.setEnabled(use is not None and not rename)
        self.rename_why.setText(rename)
        self.delete.setEnabled(use is not None and not delete)
        self.delete_why.setText(delete)
        self.rename.setToolTip("Its result is under this name" if rename else "")
        self.delete.setToolTip(
            "Used by " + ", ".join(r.name for r in use.races) if use and delete else ""
        )

    def new_group(self, dialog: "NewGroupDialog | None" = None) -> bool:
        """New Group...: the dialog makes the group itself, so a refusal keeps it open."""
        dialog = dialog or NewGroupDialog(self.store, self.event_id, self)
        if run_dialog(dialog) != QDialog.DialogCode.Accepted or dialog.made is None:
            return False
        self.changed = True
        self.refresh(select=dialog.made)
        _refuse(self.status, "")
        return True

    def rename_dialog(self, confirm: bool = True) -> "RenameGroupDialog | None":
        use = self.selected()
        if use is None or group_rules.rename_refusal(use):
            return None
        return RenameGroupDialog(self.store, self.event_id, use, self, confirm=confirm)

    def rename_selected(
        self, dialog: "RenameGroupDialog | None" = None, confirm: bool = True
    ) -> bool:
        dialog = dialog or self.rename_dialog(confirm)
        if (
            dialog is None
            or run_dialog(dialog) != QDialog.DialogCode.Accepted
            or dialog.made is None
        ):
            return False
        self.changed = True
        self.refresh(select=dialog.made)
        _refuse(self.status, "")
        return True

    def delete_selected(self, confirm: bool = True) -> bool:
        use = self.selected()
        if use is None or group_rules.delete_refusal(use):
            return False
        one = len(use.riders) == 1
        riders = f"{len(use.riders)} rider{'' if one else 's'} {'is' if one else 'are'}"
        question = f"Delete {use.label}? Its {riders} left with no group."
        # A group nobody is in goes without a question; there is nothing to lose.
        if confirm and use.riders and not icons.ask(self, "Delete Group", question, verb="Delete"):
            return False
        try:
            group_rules.delete_group(self.store, self.event_id, use)
        except (StoreError, ValueError) as exc:
            _refuse(self.status, friendly_error(self.store, exc))
            return False
        self.changed = True
        self.refresh()
        _refuse(self.status, "")
        return True


def same_label(a: str, b: str) -> bool:
    return group_key(a) == group_key(b)
