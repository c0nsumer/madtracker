"""The race dialog with its field, and the team dialog it opens."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from madtracker.control import groups as group_rules
from madtracker.control import rulesets
from madtracker.control.describe import who as bib_and_name
from madtracker.control.formats import (
    DEFAULT_FORMAT,
    NO_LAP_FORMATS,
    TEAM_COLORS,
    TEAM_FORMATS,
    TEAM_SIZE,
    format_label,
    picker_groups,
)
from madtracker.control.groups import canonical_group, event_spellings, group_key
from madtracker.control.program import is_scored
from madtracker.control.roster import (
    TEAM_NAME_MAX,
    clash_text,
    field_clash,
    field_clashes,
    team_name_problem,
)
from madtracker.export import usac_csv
from madtracker.inputs import clean_line, filter_words, is_blank, matches_filter
from madtracker.scoring import rules as R
from madtracker.scoring.replay import FORMAT_ENGINE, RULES_VERSION
from madtracker.store import Race, Store, StoreError
from madtracker.ui import style
from madtracker.ui.setup._shared import _typed
from madtracker.ui.widgets import (
    ID_ROLE,
    CheckList,
    FilterBox,
    Form,
    GroupCombo,
    apply_style,
    button_row,
    error_label,
    fit_to_screen,
    friendly_error,
    input_item,
    note_unprintable,
    rider_name,
    run_dialog,
    selected_id,
    setup_table,
    show_message,
    spin_box,
    swatch_icon,
)

# The jersey colors, from the one table the export reads too.
PALETTE = TEAM_COLORS
MAX_COUNT = rulesets.MAX_COUNT


def format_picker() -> QComboBox:
    """The race dialog's format combo: the USAC formats, then the club ones.

    Each group sits under a header row that is drawn but never
    selectable, so the current item is always a real format and the
    keyboard and wheel step over the headers.
    """
    combo = QComboBox()
    model = combo.model()
    for header, formats in picker_groups():
        combo.addItem(header)
        item = model.item(combo.count() - 1)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        for f in formats:
            combo.addItem(f.source_text, f.key)

    def off_header(index: int) -> None:
        # A header picked in code (setCurrentIndex) moves on to the format under it.
        if index >= 0 and combo.itemData(index) is None and index + 1 < combo.count():
            combo.setCurrentIndex(index + 1)

    combo.currentIndexChanged.connect(off_header)
    combo.setCurrentIndex(combo.findData(DEFAULT_FORMAT))
    # Every format at once, so no one scrolls a list of thirteen.
    combo.setMaxVisibleItems(combo.count())
    return combo


LOCKED_NOTE = "Scored races keep their rules."
# Where groups come from, on the one line that counts them.
# Whom a race is for, as the USAC CSV words it (design section 6).
RACE_GENDERS = ("Men", "Women", "Mixed")
DEFAULT_RACE_GENDER = "Mixed"
# Small counts as words, for a refusal that reads as a sentence.
COUNT_WORDS = {0: "no", 1: "one", 2: "two", 3: "three", 4: "four"}


def race_rules(store: Store, format_key: str, ruleset_name: str, number: int | None) -> R._Rules:
    """The ruleset's rules for this format with the race's own number on top."""
    engine = FORMAT_ENGINE[format_key]
    overrides: dict = {}
    if engine == "placings" and format_key in NO_LAP_FORMATS:
        overrides["laps_count_for_ranking"] = False
    elif engine == "win_and_out" and number:
        overrides["places"] = number
    elif engine == "sprint_points":
        overrides["sprint_count"] = number
    return rulesets.rules_for(store, ruleset_name, format_key, **overrides)


def _with_number(stored: dict, engine: str, number: int | None) -> dict:
    """A race's stored rules with the sprints or places as set in the dialog."""
    out = dict(stored)
    if engine == "sprint_points":
        out["sprint_count"] = number
    elif engine == "win_and_out" and number:
        out["places"] = number
    return out


class UsacBox(GroupCombo):
    """A USAC field: USAC's own words, then the file's, and anything typed.

    It answers as a line edit does (``text``, ``setText``,
    ``isModified``), so a value picked from the list counts as the
    scorer's own, as a typed one does, and a suggestion never replaces it.
    """

    def __init__(self, standard: tuple[str, ...], used: list[str]) -> None:
        super().__init__()
        self.addItems(standard)
        known = {v.casefold() for v in standard}
        more = [v for v in used if v.casefold() not in known]
        if standard and more:
            self.insertSeparator(self.count())
        self.addItems(more)
        self.setCurrentIndex(-1)
        self.setCurrentText("")
        self._modified = False
        self.lineEdit().textEdited.connect(self._touched)
        self.activated.connect(self._touched)

    def _touched(self, *_args) -> None:
        self._modified = True

    def text(self) -> str:
        return self.currentText()

    def setText(self, text: str) -> None:
        self.setCurrentText(text)

    def isModified(self) -> bool:
        return self._modified

    def setModified(self, modified: bool) -> None:
        self._modified = modified

    def placeholderText(self) -> str:
        return self.lineEdit().placeholderText()

    def setPlaceholderText(self, text: str) -> None:
        self.lineEdit().setPlaceholderText(text)


def last_race_of_group(store: Store, event_id: int, group: str) -> Race | None:
    """The event's most recently made race for this group, or None."""
    key = group_key(group)
    if not key:
        return None
    same = [r for r in store.races(event_id) if group_key(r.group_label) == key]
    return max(same, key=lambda r: r.race_id, default=None)


def _squash(text: str | None) -> str:
    return " ".join((text or "").split())


NO_TEAM_SELECTED = "Select a team first"


def team_refusal(
    name: str,
    color: str,
    members: list[int],
    size: int | None,
    used_names: set[str],
    used_colors: set[str],
) -> str:
    """Why this team cannot join the race's teams, or an empty string.

    One rule for the team dialog and for the race dialog's own path, so
    a team given in a test and a team clicked together are refused
    alike. The name is how the board and the sheets name the team, so
    it follows roster.team_name_problem and no two teams may share one.
    Two teams in one color would look like one team on the board, so
    that is refused as well.
    """
    problem = team_name_problem(name)
    if problem:
        return problem + "."
    # The color first: a team named by its color is refused as a color.
    if color.casefold() in used_colors:
        return f"There is already a {color} team."
    if name.casefold() in used_names:
        return f"There is already a team named {name}."
    if size is not None and len(members) != size:
        return f"A team here has {size} riders; {len(members)} ticked."
    if len(members) < 2:
        return "A team needs at least two riders."
    return ""


class TeamDialog(QDialog):
    """One team: its name, its color and its riders from the field.

    Most clubs call a team by its jersey color, so the name is optional:
    the placeholder shows the color that is picked, and a blank name
    saves as that color. The same dialog edits a team; its own riders
    are then listed along with those on no team, already ticked.
    """

    def __init__(
        self,
        riders: list[tuple[int, str]],
        used_colors: set[str],
        size: int | None,
        parent: QWidget | None = None,
        *,
        used_names: set[str] = frozenset(),
        team: tuple[str, str, list[int]] | None = None,
    ):
        super().__init__(parent)
        editing = team is not None
        self.setWindowTitle("Edit Team" if editing else "Add Team")
        apply_style(self)
        self.team_size = size
        self.used_colors = {c.casefold() for c in used_colors}
        self.used_names = {n.casefold() for n in used_names}
        self.name = QLineEdit()
        self.name.setMaxLength(TEAM_NAME_MAX)
        self.color = QComboBox()
        for color, hex_color in PALETTE.items():
            self.color.addItem(swatch_icon(hex_color), color, hex_color)
        free = next((i for i, c in enumerate(PALETTE) if c.casefold() not in self.used_colors), 0)
        self.color.setCurrentIndex(free)
        self.list = CheckList()
        for rider_id, name in riders:
            self.list.add(rider_id, name)
        self.error = error_label()
        note_unprintable(self.name, self.error)
        buttons, _ = button_row(
            "Save Team" if editing else "Add Team", self.accept_team, self.reject
        )
        form = Form()
        form.addRow("Name", self.name)
        form.addRow("Color", self.color)
        form.addRow(f"Riders ({size})" if size else "Riders", self.list)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.error)
        lay.addLayout(buttons)
        # The placeholder is the name the team gets when none is typed.
        self.color.currentTextChanged.connect(self.name.setPlaceholderText)
        self.name.setPlaceholderText(self.color.currentText())
        if team is not None:
            name, color, members = team
            index = self.color.findText(color)
            if index >= 0:
                self.color.setCurrentIndex(index)
            # A team named by its color comes back with a blank name, as entered;
            # "RED" was typed, so it stays.
            self.name.setText("" if name == color else name)
            for rider_id in members:
                self.check(rider_id)

    def check(self, rider_id: int, on: bool = True) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(ID_ROLE) == rider_id:
                item.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def members(self) -> list[int]:
        return [
            self.list.item(i).data(ID_ROLE)
            for i in range(self.list.count())
            if self.list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def team_name(self) -> str:
        """The typed name, or the color when none is typed."""
        return _typed(self.name) or self.color.currentText()

    def accept_team(self) -> bool:
        refused = team_refusal(
            self.team_name(),
            self.color.currentText(),
            self.members(),
            self.team_size,
            self.used_names,
            self.used_colors,
        )
        if refused:
            show_message(self.error, refused)
            return False
        self.accept()
        return True


class RaceDialog(QDialog):
    """Add or edit a race: name, format, group, ruleset, the one number, the field, the teams.

    A race with an entry that stands keeps its rules (design section 6):
    format, group, ruleset, the sprints or places, the field and the
    teams are disabled, and one line under them says why. The name and
    whom the race is for stay editable. A race undone to its start list
    has no such entry and opens like one never scored.

    A bib is unique within a race's field: ticking a rider whose number
    is already ticked is refused. A group pick fills the field anyway
    and lists the clashes, since the group is usually right and one bib
    on the roster is wrong; the race then waits for the fix before it
    can be scored.
    """

    def __init__(
        self,
        store: Store,
        event_id: int,
        race_id: int | None = None,
        parent: QWidget | None = None,
        copy_of: int | None = None,
    ):
        """``copy_of``: a new race filled from that one (Duplicate), saved as a new race."""
        super().__init__(parent)
        self.store = store
        self.event_id = event_id
        self.race_id = race_id
        self.copy_of = None if race_id else copy_of
        self.setWindowTitle(
            "Edit Race" if race_id else "Duplicate Race" if self.copy_of else "Add Race"
        )
        fit_to_screen(self, 1000, 640)
        apply_style(self)
        self._loading = True
        self._filling = False
        self._keep_number = False
        # (ruleset name, format, rules) for a race whose ruleset is gone.
        self._kept_rules: tuple[str, str, dict] | None = None
        self.teams: list[tuple[str, str, str, list[int]]] = []  # (name, color, hex, members)

        form = self._build_race_form()
        self.scored = False
        self._build_usac_box()
        self._build_field_box()
        self._build_teams_box()
        self._lay_out(form)
        self._connect_fields()

        # Read as the field is filled; an existing race's field is filled
        # once, by _load, rather than empty first and again with its riders.
        self._bibs: dict[int, int | None] = {}
        if race_id is not None:
            self._load()
        elif self.copy_of is not None:
            self._load(self.copy_of)
        else:
            self._fill_field([])
            self._reset_number()
        self._loading = False
        # A loaded race keeps its sprints or places: the format is shown,
        # not changed, so the ruleset's count must not replace the stored one.
        self._keep_number = race_id is not None or self.copy_of is not None
        self._format_changed()
        self._keep_number = False
        self._show_default_name()
        self._show_look_alike()

    def _build_race_form(self) -> Form:
        """The race's fields (the USAC details' too) and the Race box's form."""
        self.name = QLineEdit()
        self.format = format_picker()
        self.group = GroupCombo()
        self.group.addItems(sorted(event_spellings(self.store, self.event_id), key=str.casefold))
        self.group.lineEdit().setPlaceholderText("No group")
        self.group.setCurrentText("")
        self.gender = QComboBox()
        self.gender.addItems(RACE_GENDERS)
        self.gender.setCurrentText(DEFAULT_RACE_GENDER)
        # USAC's template fields for the field. They go only into the USAC
        # file, so a scored race may still change them, as it may For.
        # Each offers USAC's own words and every value this file has used,
        # so a value typed once is picked, spelled the same, every week.
        used_categories, used_classes, used_ages = self.store.usac_values()
        self.category = UsacBox(usac_csv.CATEGORIES, used_categories)
        self.category.setToolTip("Race Category in the USAC CSV, eg: Cat 3/4 or Open")
        self.usac_class = UsacBox(usac_csv.CLASSES, used_classes)
        self.usac_class.setToolTip("Race Class in the USAC CSV, eg: Senior, Junior, or Master")
        self.age_group = UsacBox((), used_ages)
        self.age_group.setToolTip("Race Age Group in the USAC CSV, eg: 9-14 or 35+")
        self.ruleset = QComboBox()
        for name in rulesets.ruleset_names(self.store):
            self.ruleset.addItem(rulesets.ruleset_label(name), name)
        self.ruleset.setCurrentIndex(
            self.ruleset.findData(rulesets.default_ruleset_name(self.store))
        )
        # Blank until typed: a default of one sprint saved unnoticed turns
        # a points race into its final sprint on the first click, and the
        # count is fixed once anything is entered.
        self.number = spin_box(0, MAX_COUNT)
        self.number.setSpecialValueText(" ")
        self.number_label = QLabel("Sprints")
        form = Form()
        form.addRow("Name", self.name)
        form.addRow("Format", self.format)
        form.addRow(self.number_label, self.number)
        form.addRow("Group", self.group)
        form.addRow("Ruleset", self.ruleset)
        self.locked_note = QLabel(LOCKED_NOTE)
        self.locked_note.setObjectName("hint")
        self.locked_note.setVisible(False)
        form.addRow("", self.locked_note)
        self.form = form
        return form

    def _build_usac_box(self) -> None:
        # Whom the race is for and the three template fields go only into
        # the USAC CSV, so they sit apart from what scores the race, under
        # it. Two pairs to a row, labels beside: four rows of fields, or
        # labels over them, would make a Points Race taller than a 1366 by 768
        # screen at 125%. The dialog is wide enough that Category shows
        # its value whole.
        self.usac_box = QGroupBox("USAC CSV Details")
        usac_grid = QGridLayout(self.usac_box)
        usac_grid.setColumnStretch(1, 1)
        usac_grid.setColumnStretch(4, 1)
        # Column 2 is the gap that keeps the pairs apart.
        usac_grid.setColumnMinimumWidth(2, style.SM)
        pairs = (
            ("Gender", self.gender),
            ("Category", self.category),
            ("Class", self.usac_class),
            ("Age group", self.age_group),
        )
        for i, (text, widget) in enumerate(pairs):
            label = QLabel(text)
            label.setBuddy(widget)
            row, col = divmod(i, 2)
            usac_grid.addWidget(label, row, col * 3)
            usac_grid.addWidget(widget, row, col * 3 + 1)
        # Another race of this event USAC would see as this one.
        self.look_alike = QLabel("")
        self.look_alike.setObjectName("hint")
        self.look_alike.setWordWrap(True)
        self.look_alike.setVisible(False)
        usac_grid.addWidget(self.look_alike, 2, 0, 1, 5)

    def _build_field_box(self) -> None:
        self.field_box = QGroupBox("Field")
        self.field_filter = FilterBox("Filter by name, group, or bib")
        self.field_filter.textChanged.connect(self._filter_field)
        self.field_filter.returnPressed.connect(self.check_top_match)
        self.field = CheckList()
        self.field_count = QLabel("")
        self.field_count.setObjectName("hint")
        field_lay = QVBoxLayout(self.field_box)
        field_lay.addWidget(self.field_filter)
        field_lay.addWidget(self.field, 1)
        field_lay.addWidget(self.field_count)

    def _build_teams_box(self) -> None:
        self.teams_box = QGroupBox("Teams")
        self.teams_table = QTableWidget()
        setup_table(self.teams_table, ["Team", "Riders"])
        self.teams_table.cellDoubleClicked.connect(lambda row, _col: self.edit_team(row))
        self.teams_table.itemSelectionChanged.connect(self._update_team_buttons)
        add_team = QPushButton("Add Team...")
        add_team.clicked.connect(lambda: self.add_team())
        self.edit_team_button = QPushButton("Edit Team...")
        self.edit_team_button.clicked.connect(lambda: self.edit_team())
        self.remove_team_button = QPushButton("Remove Team")
        self.remove_team_button.clicked.connect(self.remove_team)
        team_buttons = QHBoxLayout()
        team_buttons.addWidget(add_team)
        team_buttons.addWidget(self.edit_team_button)
        team_buttons.addWidget(self.remove_team_button)
        team_buttons.addStretch(1)
        self._update_team_buttons()
        teams_lay = QVBoxLayout(self.teams_box)
        teams_lay.addLayout(team_buttons)
        teams_lay.addWidget(self.teams_table, 1)

    def _lay_out(self, form: Form) -> None:
        """The red line, the buttons, the Race box, and the three columns."""
        self.error = error_label()
        note_unprintable(self.name, self.error)
        note_unprintable(self.group.lineEdit(), self.error)
        buttons, _ = button_row("Save Race", self.save, self.reject)
        # What scores the race in its own box, as the field and the USAC
        # details are in theirs, so the dialog reads as three parts.
        self.race_box = QGroupBox("Race")
        QVBoxLayout(self.race_box).addLayout(form)
        left = QVBoxLayout()
        left.addWidget(self.race_box)
        left.addWidget(self.usac_box)
        left.addStretch(1)
        # A team race's field is its teams, so the teams take the field's
        # place rather than a second list that must agree with it; either
        # takes the column's whole height, for more riders in view.
        body = QHBoxLayout()
        body.addLayout(left, 1)
        body.addWidget(self.field_box, 1)
        body.addWidget(self.teams_box, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addWidget(self.error)
        lay.addLayout(buttons)

    def _connect_fields(self) -> None:
        self.format.currentIndexChanged.connect(self._format_changed)
        self.ruleset.currentIndexChanged.connect(self._reset_number)
        # The placeholder is the name a blank box saves as, so the scorer
        # sees "Group A Madison" take shape as the group and format are
        # picked, rather than a rule about it.
        self.format.currentIndexChanged.connect(self._show_default_name)
        self.group.currentTextChanged.connect(self._show_default_name)
        self.ruleset.currentIndexChanged.connect(self._show_default_name)
        self.group.currentTextChanged.connect(self._suggest_usac)
        self.format.currentIndexChanged.connect(self._show_look_alike)
        self.group.currentTextChanged.connect(self._show_look_alike)
        self.gender.currentIndexChanged.connect(self._show_look_alike)
        for box in (self.category, self.usac_class, self.age_group):
            box.currentTextChanged.connect(self._show_look_alike)
        # Who is out of the race's group follows the group as it changes.
        self.group.currentTextChanged.connect(lambda _t: self._count_field())
        # Only a pick from the list refills the field; typing a group
        # name leaves the riders ticked by hand alone.
        self.group.activated.connect(lambda i: self.choose_group(self.group.itemText(i)))
        self.field.itemChanged.connect(self._field_changed)

    # ----- data ---------------------------------------------------------

    def format_key(self) -> str:
        return self.format.currentData()

    def format_name(self) -> str:
        """The format as the chosen ruleset names it ("Devil" for a venue's elimination)."""
        try:
            doc = rulesets.ruleset_for(self.store, self.ruleset.currentData() or rulesets.BUILTIN)
        except rulesets.RulesetError:
            return format_label(self.format_key())
        return rulesets.format_name(doc, self.format_key())

    def default_name(self) -> str:
        """The name a blank Name box saves as: the group and the format."""
        group = " ".join(self.group.currentText().split())
        return f"{group} {self.format_name()}".strip()

    def _show_default_name(self, *_args) -> None:
        # A scored race keeps its name when Name is left blank, so that
        # name is the placeholder; the ruleset's word may have changed.
        scored = self.scored and self.race_id is not None
        self.name.setPlaceholderText(
            self.store.race(self.race_id).name if scored else self.default_name()
        )
        # A blank Category saves as the group, so the group shows there
        # the way the default name shows in Name.
        self.category.setPlaceholderText(_squash(self.group.currentText()))

    def _suggest_usac(self, *_args) -> None:
        """A new race takes Class and Age group from the group's last race.

        A group runs the same class and ages all night, so the scorer
        types them once; a value typed here is never overwritten.
        """
        if self._loading or self.race_id is not None:
            return
        last = last_race_of_group(self.store, self.event_id, self.group.currentText())
        for box, value in (
            (self.usac_class, last.usac_class if last else None),
            (self.age_group, last.usac_age_group if last else None),
        ):
            if not box.isModified():
                box.setText(value or "")

    def _show_look_alike(self, *_args) -> None:
        """Name the other races of the event USAC would see as this one.

        A note, not a refusal: whether USAC files such races as one is
        unverified, and the template has no field for a race's name, so a
        refusal would push the scorer into inventing a Class.
        """
        if self._loading:
            return
        group = self.group.currentText()
        discipline = self.store.race(self.race_id).usac_discipline if self.race_id else None
        mine = usac_csv.details_key(
            _squash(discipline) or usac_csv.DISCIPLINE_BY_FORMAT.get(self.format_key(), ""),
            self.usac_fields(group)["usac_category"],
            self.gender.currentText(),
            self.usac_fields(group)["usac_class"],
            self.usac_fields(group)["usac_age_group"],
        )
        same = [
            r.name
            for r in self.store.races(self.event_id)
            if r.race_id != self.race_id and usac_csv.usac_key(r) == mine
        ]
        self.look_alike.setText(f"Same USAC details as {', '.join(same)}." if same else "")
        self.look_alike.setVisible(bool(same))

    def usac_fields(self, group: str) -> dict[str, str | None]:
        """The three USAC fields as saved; a blank Category is the group."""
        return {
            "usac_category": _squash(self.category.text()) or _squash(group) or None,
            "usac_class": _squash(self.usac_class.text()) or None,
            "usac_age_group": _squash(self.age_group.text()) or None,
        }

    def engine(self) -> str:
        return FORMAT_ENGINE[self.format_key()]

    def _load(self, copy_of: int | None = None) -> None:
        """The race's values into the boxes; ``copy_of`` fills a new race from another."""
        race = self.store.race(self.race_id if copy_of is None else copy_of)
        index = self.format.findData(race.format)
        if index < 0:
            self.format.addItem(format_label(race.format), race.format)
            index = self.format.count() - 1
        self.format.setCurrentIndex(index)
        # A default name stays blank, the default in gray, as when the race
        # was made; a blank Name saves it again, for a new group if changed.
        self.name.setText("" if rulesets.has_default_name(race) else race.name)
        if copy_of is not None:
            # A typed name is copied selected, since a duplicate is usually
            # renamed ("4 Mile Madison" from "8 Mile Madison"); typing replaces it.
            self.name.selectAll()
        self.group.setCurrentText(race.group_label)
        if race.usac_gender in RACE_GENDERS:
            self.gender.setCurrentText(race.usac_gender)
        # A Category that is only the group, the default for a blank one,
        # stays blank with the group in gray, so it follows a new group.
        same = _squash(race.usac_category).casefold() == _squash(race.group_label).casefold()
        self.category.setText("" if same else race.usac_category or "")
        self.usac_class.setText(race.usac_class or "")
        self.age_group.setText(race.usac_age_group or "")
        if copy_of is not None:
            # Copied values are kept as typed ones are: a group picked in
            # the duplicate must not replace them with its last race's.
            self.usac_class.setModified(True)
            self.age_group.setModified(True)
        index = self.ruleset.findData(race.rules_preset)
        if index < 0 and race.rules_preset and race.format == self.format_key():
            # Its ruleset was deleted: the race keeps the rules it holds,
            # shown under the name it was made from, rather than the
            # default's put in their place on Save.
            self.ruleset.addItem(f"{race.rules_preset} {rulesets.DELETED}", race.rules_preset)
            index = self.ruleset.count() - 1
            self._kept_rules = (race.rules_preset, race.format, dict(race.rules or {}))
        if index >= 0:
            self.ruleset.setCurrentIndex(index)
        self._reset_number()
        rules = race.rules or {}
        if rules.get("sprint_count"):
            self.number.setValue(int(rules["sprint_count"]))
        elif rules.get("places"):
            self.number.setValue(int(rules["places"]))
        self._fill_field([e.rider_id for e in self.store.race_entries(race.race_id)])
        self.teams = [
            (
                t.name,
                t.color or t.name,
                t.color_hex or PALETTE.get(t.color, "#9aa0a6"),
                list(t.members),
            )
            for t in self.store.teams(race.race_id)
        ]
        self._show_teams()
        if copy_of is None and is_scored(self.store, race):
            # The log's entries are this format's, name this field and
            # were scored by these rules; changing any of them would
            # rewrite a result already called. A race undone to its start
            # list has no entry that stands, and opens unlocked.
            self.scored = True
            for w in self.locked_widgets():
                w.setEnabled(False)
            self.locked_note.setVisible(True)
            self._update_team_buttons()

    def locked_widgets(self) -> list[QWidget]:
        return [self.format, self.group, self.ruleset, self.number, self.field, self.teams_box]

    def _fill_field(self, chosen: list[int]) -> None:
        """The roster as a tick list: the field, then the race's group, then everyone else.

        Each part is in bib order, as the roster and the cards are: a row
        starts with the bib, and sorted by last name the numbers would run
        42, 17, 3, 31 and read as no order at all. Riders without a bib
        come last in their part, by name.
        """
        chosen_set = set(chosen)
        self._filling = True
        try:
            self.field.clear()
            pairs = self.store.entries_with_riders(self.event_id)
            self._bibs = {e.rider_id: e.bib for e, _r in pairs}
            race_group = group_key(self.group.currentText())
            riders = sorted(
                pairs,
                key=lambda pair: (
                    pair[0].rider_id not in chosen_set,
                    not race_group or group_key(pair[0].local_group) != race_group,
                    pair[0].bib is None,
                    pair[0].bib or 0,
                    pair[1].last_name.casefold(),
                    pair[1].first_name.casefold(),
                ),
            )
            for e, r in riders:
                item = self.field.add(
                    e.rider_id,
                    f"{bib_and_name(e.bib, r.name)}  ({e.local_group or 'no group'})",
                    e.rider_id in chosen_set,
                )
                item.setData(ID_ROLE + 1, e.local_group or "")
        finally:
            self._filling = False
        self._filter_field()
        self._count_field()

    def _filter_field(self, *_args) -> None:
        """Show the riders whose bib, name, or group has the typed text; a hidden rider keeps its tick."""
        words = filter_words(self.field_filter.text())
        for i in range(self.field.count()):
            item = self.field.item(i)
            bib = self._bibs.get(item.data(ID_ROLE))
            item.setHidden(not matches_filter(words, item.text(), bib))

    def team_format(self) -> bool:
        return self.format_key() in TEAM_FORMATS

    def field_ids(self) -> list[int]:
        """The riders in the race: the ticked ones, or for a team race its teams' riders."""
        if self.team_format():
            return [m for _n, _c, _h, members in self.teams for m in members]
        return [
            self.field.item(i).data(ID_ROLE)
            for i in range(self.field.count())
            if self.field.item(i).checkState() == Qt.CheckState.Checked
        ]

    def set_in_field(self, rider_id: int, on: bool) -> None:
        for i in range(self.field.count()):
            item = self.field.item(i)
            if item.data(ID_ROLE) == rider_id:
                item.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def _count_field(self) -> None:
        ids = self.field_ids()
        text = f"{len(ids)} riders in the field"
        missing = sum(1 for rid in ids if self._bibs.get(rid) is None)
        if missing:
            text += f", {missing} without a bib"
        if not self.team_format():
            groups = {
                self.field.item(i).data(ID_ROLE): self.field.item(i).data(ID_ROLE + 1)
                for i in range(self.field.count())
            }
            text += group_rules.out_of_group(
                self.group.currentText(), [groups.get(rid) for rid in ids]
            )
        self.field_count.setText(text)

    def _field_changed(self, item) -> None:
        if self._filling:
            # _fill_field counts once at the end; a count per row filled
            # would be most of the dialog's opening time on a 150-rider roster.
            return
        if item.checkState() == Qt.CheckState.Checked:
            rider_id = item.data(ID_ROLE)
            others = [rid for rid in self.field_ids() if rid != rider_id]
            clash = field_clash(
                self.store, self.event_id, rider_id, self._bibs.get(rider_id), others
            )
            if clash:
                self.field.blockSignals(True)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.field.blockSignals(False)
                show_message(self.error, clash)
        self._count_field()

    def check_top_match(self) -> bool:
        """Enter in the filter checks the top match and empties the box, as Choose Riders does."""
        if not self.field.isEnabled():
            return False
        shown = (self.field.item(i) for i in range(self.field.count()))
        top = next((item for item in shown if not item.isHidden()), None)
        if top is None:
            show_message(self.error, "No rider matches.")
            return False
        show_message(self.error, "")
        top.setCheckState(Qt.CheckState.Checked)
        self.field_filter.clear()
        self.field_filter.setFocus()
        return top.checkState() == Qt.CheckState.Checked

    def field_clash_text(self) -> str:
        """The clashes in the ticked field, for the refusal line."""
        rows = [(rid, self._bibs.get(rid), rider_name(self.store, rid)) for rid in self.field_ids()]
        return clash_text(field_clashes(rows))

    def choose_group(self, text: str) -> None:
        """A group picked from the list fills the field; it can then be adjusted rider by rider.

        A team race's field is its teams, so there the group only puts its
        riders first in the team dialog.
        """
        if self._loading or self.scored:
            return
        self.group.setCurrentText(text)
        key = group_key(text)
        if not key or self.team_format():
            return
        self._fill_field(
            [
                e.rider_id
                for e in self.store.entries(self.event_id)
                if group_key(e.local_group) == key
            ]
        )
        show_message(self.error, self.field_clash_text())

    def _format_changed(self) -> None:
        engine = self.engine()
        self.form.setRowVisible(self.number, engine in ("sprint_points", "win_and_out"))
        self.number_label.setText("Places" if engine == "win_and_out" else "Sprints")
        self.teams_box.setVisible(self.team_format())
        self.field_box.setVisible(not self.team_format())
        if not self._loading:
            self._reset_number()

    def _reset_number(self) -> None:
        if self._keep_number or (self._loading and self.race_id is not None):
            return
        engine = self.engine()
        if engine == "win_and_out":
            try:
                rules = race_rules(self.store, self.format_key(), self.ruleset.currentData(), None)
                # A stored ruleset is not checked again as it is read, and
                # setValue overflows past a C int, so its places are held
                # to the box's range.
                self.number.setValue(min(rules.places, self.number.maximum()))
            except rulesets.RulesetError:
                pass
        elif engine == "sprint_points" and self.number.value() < 1:
            # The event's last race of this format has the count the
            # venue runs it at; with none, the box stays blank.
            counts = [
                int((r.rules or {}).get("sprint_count") or 0)
                for r in self.store.races(self.event_id)
                if r.format == self.format_key()
            ]
            self.number.setValue(next((c for c in reversed(counts) if c), 0))

    # ----- teams --------------------------------------------------------

    def _show_teams(self, select: int | None = None) -> None:
        self.teams_table.setRowCount(len(self.teams))
        for row, (name, _, hex_color, members) in enumerate(self.teams):
            # The swatch shows the color, so the name stands alone.
            item = input_item(name, editable=False)
            item.setIcon(swatch_icon(hex_color))
            item.setData(ID_ROLE, row)
            self.teams_table.setItem(row, 0, item)
            names = ", ".join(rider_name(self.store, m) for m in members)
            self.teams_table.setItem(row, 1, input_item(names, editable=False))
        if select is not None and 0 <= select < len(self.teams):
            self.teams_table.selectRow(select)
        self._update_team_buttons()

    def _update_team_buttons(self) -> None:
        chosen = selected_id(self.teams_table) is not None
        # A scored race's teams are locked whatever is selected, and the
        # tip says that rather than asking for a selection.
        why = LOCKED_NOTE if self.scored else "" if chosen else NO_TEAM_SELECTED
        for button in (self.edit_team_button, self.remove_team_button):
            button.setEnabled(chosen)
            button.setToolTip(why)

    def _free_riders(self, team: int | None) -> list[tuple[int, str]]:
        """The roster's riders on no team, plus this team's own when editing one.

        The race's group comes first, since a madison is usually one
        group's riders paired up.
        """
        taken = {m for i, (_, _, _, ms) in enumerate(self.teams) if i != team for m in ms}
        if self.race_id is not None and is_scored(self.store, self.store.race(self.race_id)):
            riders = [
                (e.rider_id, bib_and_name(e.bib, e.name))
                for e in self.store.race_entries(self.race_id)
            ]
        else:
            key = group_key(self.group.currentText())
            entries = sorted(
                self.store.entries(self.event_id),
                key=lambda e: not key or group_key(e.local_group) != key,
            )
            riders = [
                (e.rider_id, bib_and_name(e.bib, rider_name(self.store, e.rider_id)))
                for e in entries
            ]
        return [(rid, name) for rid, name in riders if rid not in taken]

    def _other_teams(self, team: int | None) -> tuple[set[str], set[str]]:
        """The names and the colors of every team but this one, casefolded."""
        others = [t for i, t in enumerate(self.teams) if i != team]
        return {n.casefold() for n, _, _, _ in others}, {c.casefold() for _, c, _, _ in others}

    def add_team(
        self, color: str | None = None, members: list[int] | None = None, name: str = ""
    ) -> bool:
        """Add a team; without arguments the dialog asks. A blank name is the color."""
        riders = self._free_riders(None)
        if not riders:
            show_message(self.error, "Every rider on the roster is on a team already.")
            return False
        size = TEAM_SIZE.get(self.format_key())
        used_names, used_colors = self._other_teams(None)
        if color is None or members is None:
            dialog = TeamDialog(riders, used_colors, size, self, used_names=used_names)
            if run_dialog(dialog) != QDialog.DialogCode.Accepted:
                return False
            name, color, members = dialog.team_name(), dialog.color.currentText(), dialog.members()
        name = ("" if is_blank(name) else clean_line(name)) or color
        refused = team_refusal(name, color, members, size, used_names, used_colors)
        if refused:
            show_message(self.error, refused)
            return False
        self.teams.append((name, color, PALETTE.get(color, "#9aa0a6"), list(members)))
        self._show_teams()
        show_message(self.error, "")
        return True

    def edit_team(
        self,
        index: int | None = None,
        *,
        name: str | None = None,
        color: str | None = None,
        members: list[int] | None = None,
    ) -> bool:
        """Change the selected team (or row ``index``); without the fields the dialog asks.

        The dialog opens on the team as it is, with its own riders ticked
        and listed along with those on no team, so a swap between two
        teams is one edit of each. A blank name is the color.
        """
        if index is None:
            index = selected_id(self.teams_table)
        if index is None:
            show_message(self.error, "Select a team first.")
            return False
        old_name, old_color, _hex, old_members = self.teams[index]
        size = TEAM_SIZE.get(self.format_key())
        used_names, used_colors = self._other_teams(index)
        if name is None and color is None and members is None:
            dialog = TeamDialog(
                self._free_riders(index),
                used_colors,
                size,
                self,
                used_names=used_names,
                team=(old_name, old_color, old_members),
            )
            if run_dialog(dialog) != QDialog.DialogCode.Accepted:
                return False
            name, color, members = dialog.team_name(), dialog.color.currentText(), dialog.members()
        color = color if color is not None else old_color
        members = list(members) if members is not None else list(old_members)
        # A team named by its color follows the color when only the color changes.
        if name is None:
            name = color if old_name.casefold() == old_color.casefold() else old_name
        name = ("" if is_blank(name) else clean_line(name)) or color
        refused = team_refusal(name, color, members, size, used_names, used_colors)
        if refused:
            show_message(self.error, refused)
            return False
        self.teams[index] = (name, color, PALETTE.get(color, "#9aa0a6"), members)
        self._show_teams(select=index)
        show_message(self.error, "")
        return True

    def remove_team(self) -> bool:
        index = selected_id(self.teams_table)
        if index is None:
            show_message(self.error, "Select a team first.")
            return False
        del self.teams[index]
        self._show_teams()
        return True

    # ----- save ---------------------------------------------------------

    def save(self) -> bool:
        if self.scored:
            return self._save_name()
        group = canonical_group(self.store, self.event_id, self.group.currentText())
        name = _typed(self.name) or f"{group} {self.format_name()}".strip()
        # (``default_name`` with the group as the event spells it.)
        number = self.number.value() if self.engine() in ("sprint_points", "win_and_out") else None
        if self.engine() in ("sprint_points", "win_and_out") and not number:
            # Without a count the engine cannot tell the last sprint from the
            # others; without places a win-and-out has no laps to decide.
            what = "places" if self.engine() == "win_and_out" else "sprints"
            show_message(self.error, f"Set the number of {what}.")
            return False
        field = self.field_ids()
        # A race with a group may wait for its riders: until it is scored
        # its field follows the group, so the program can be built first.
        # A team race fills only through its teams.
        if not field and not group:
            text = "Add the teams." if self.team_format() else "Pick a group or tick the riders."
            show_message(self.error, text)
            return False
        if self.team_format():
            problem = self.team_problem()
            if problem:
                show_message(self.error, problem)
                return False
        kept = self._kept_rules
        if kept and (kept[0], kept[1]) != (self.ruleset.currentData(), self.format_key()):
            kept = None
        try:
            if kept:
                rules = R.rules_from_dict(_with_number(kept[2], self.engine(), number))
            else:
                rules = race_rules(
                    self.store, self.format_key(), self.ruleset.currentData(), number
                )
        except (ValueError, rulesets.RulesetError) as exc:
            text = str(exc) or "These rules cannot be used"
            show_message(self.error, text[:1].upper() + text[1:] + ".")
            return False
        fields = {
            "name": name,
            "format": self.format_key(),
            "group_label": group,
            "rules_preset": self.ruleset.currentData(),
            # The ruleset's words travel with the rules: the race keeps
            # calling itself what it was called when it was made.
            "rules": {
                # A gone ruleset's race keeps the words it was made with.
                **(kept[2] if kept else {}),
                **rules.to_dict(),
                **rulesets.words_for(self.store, self.ruleset.currentData(), self.format_key()),
            },
            "rules_version": RULES_VERSION,
            "usac_gender": self.gender.currentText(),
            **self.usac_fields(group),
        }
        try:
            # One write for the race, its field and its teams: one commit
            # rather than one per rider, and never half a race on a refusal.
            self.race_id = self.store.save_race(
                self.event_id,
                self.race_id,
                fields,
                field,
                self.teams if self.team_format() else None,
            ).race_id
        except (StoreError, ValueError) as exc:
            show_message(self.error, friendly_error(self.store, exc))
            return False
        self.accept()
        return True

    def _save_name(self) -> bool:
        """A scored race: only the name, whom it is for and the USAC fields change.

        None touches the result; the gender and the USAC fields go only
        into the USAC CSV.
        """
        race = self.store.race(self.race_id)
        changes = {}
        name = _typed(self.name) or race.name
        if name != race.name:
            changes["name"] = name
        if self.gender.currentText() != race.usac_gender:
            changes["usac_gender"] = self.gender.currentText()
        for key, value in self.usac_fields(race.group_label).items():
            if value != getattr(race, key):
                changes[key] = value
        try:
            if changes:
                self.store.update_race(self.race_id, **changes)
        except (StoreError, ValueError) as exc:
            show_message(self.error, friendly_error(self.store, exc))
            return False
        self.accept()
        return True

    def team_problem(self) -> str:
        """Why the teams cannot be saved, or an empty string.

        Checked before anything is written: every team has the format's
        number of riders; no rider is on two teams; no two teams share a
        name or a color. The field is the teams' riders, so it always
        agrees with them.
        """
        size = TEAM_SIZE.get(self.format_key())
        seen_names: set[str] = set()
        seen_colors: set[str] = set()
        placed: dict[int, str] = {}
        for name, color, _hex, members in self.teams:
            if color.casefold() in seen_colors:
                return f"There are two {color} teams."
            seen_colors.add(color.casefold())
            if name.casefold() in seen_names:
                return f"There are two teams named {name}."
            seen_names.add(name.casefold())
            if size is not None and len(members) != size:
                count = COUNT_WORDS.get(len(members), str(len(members)))
                noun = "rider" if len(members) == 1 else "riders"
                return f"Team {name} has {count} {noun}."
            for m in members:
                if m in placed:
                    return f"{rider_name(self.store, m)} is on team {placed[m]} and team {name}."
                placed[m] = name
        return ""
