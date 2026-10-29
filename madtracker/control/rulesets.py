"""Named rulesets: the built-in rulebook plus the venue's own, stored as JSON.

A ruleset is one flat page of values, the only ones the engines need
(``.claude/plans/rules-model.md``)::

    {
      "name": "House Rules",
      "points_table": [5, 3, 2, 1],      # points race sprint points, by place
      "points_last_double": true,        # double points for the last sprint
      "points_lap_gained": 20,           # each sprint format prices its own laps
      "points_lap_lost": 20,
      "madison_table": [5, 3, 2, 1],
      "madison_last_double": true,
      "madison_lap_gained": 20,
      "madison_lap_lost": 20,
      "tempo_points": 1,                 # per sprint, the final not doubled
      "tempo_lap_gained": 20,
      "tempo_lap_lost": 20,
      "survivors": 2,                    # elimination riders in the final
      "places": 3,                       # win-and-out places awarded
      "direction": "forward",            # "forward" or "reverse"
      "lapped_riders_placed": true,      # a lapped rider who stays in is placed (USAC 2C4)
      "format_names": {"elimination": "Devil"},          # the venue's word, optional
      "format_descriptions": {"elimination": "Last rider over the line every 2 laps is out"}
    }

The two word maps are optional and may hold any offered format key; a
blank or missing entry means the rulebook's label and no description.
A race copies the words it was made with into its ``rules_json``
(``format_name``, ``format_description``) beside the rules, so a
renamed format never changes a past sheet.

``formats_for`` turns the page into one rules dict per family, and
``FAMILIES`` maps each family to the ``replay.FORMAT_ENGINE`` keys it
covers, so every format that shares an engine and the same house values
shares one set of fields. Sprint counts and win-and-out places are set
per race by the race editor on top of the page.

The built-in "rulebook" is not a row: USAC and UCI score every format
the same way, so one read-only page stands for both. A race copies the full rules it
was created with into its own ``rules_json`` (``ui.race_editor``), so
editing, renaming or deleting a ruleset later never changes a race that
already exists.
"""

import json
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from madtracker.control.formats import FORMATS, Format, format_label
from madtracker.inputs import MAX_TEXT, clean_line
from madtracker.scoring import rules as R
from madtracker.scoring.replay import FORMAT_ENGINE
from madtracker.store import Race, Ruleset, Store

DEFAULT_SETTING = "rules/default_ruleset"

# A points table in a field is a comma-separated list, "10, 7, 5, 3, 2, 1",
# the one form a list of values takes in a text field (a print dialog's
# pages, a spreadsheet's cells), so the Rulesets and Multi-Race Standings
# fields read the same. Printed inside a sentence on a sheet the table is
# the hyphen run of a race announcement, "10-7-5-3-2-1".
TABLE_SAMPLE = "10, 7, 5, 3, 2, 1"
# The most a place awards; a held key past it is refused where it is typed.
TABLE_MAX = 999
# Between values a comma, a semicolon, or white space; a hyphen only
# between two digits, so a table copied from a sheet parses and "-1"
# stays a negative that the check refuses.
_TABLE_BREAK = re.compile(r"[,;\s]+|(?<=[0-9])-(?=[0-9])")


def table_text(values: Iterable[int]) -> str:
    """A points table as a field shows it, "10, 7, 5, 3, 2, 1"."""
    return ", ".join(str(v) for v in values)


def split_table(text: str) -> list[str]:
    """The values typed into a table field, as strings, before any check."""
    return [p for p in _TABLE_BREAK.split(text.strip()) if p]


# The key is what a race's rules_preset column and the default setting
# hold, so it stays fixed; the label is what the scorer sees and names
# whose values they are and which edition, so the app never reads as the
# authority.
BUILTIN = "rulebook"
# The rulebook's name, for the values that come from it; the built-in
# ruleset's name says it also carries the club formats' defaults (the
# win-and-out's places and direction are a club's, not USAC's), so the
# label never claims USAC wrote them.
RULEBOOK_LABEL = f"USAC {R.RULEBOOK_YEAR}"
BUILTIN_LABEL = f"{RULEBOOK_LABEL} + Club formats"
# Where a family's built-in values come from: the rulebook, or a club's
# documented program. A tab fills from the rulebook only when it is the source.
CLUB_LABEL = "Club"
FAMILY_SOURCE = {
    family: (CLUB_LABEL if family == "win_and_out" else RULEBOOK_LABEL)
    for family in ("placings", "points", "madison", "tempo", "elimination", "win_and_out")
}

FAMILIES: dict[str, tuple[str, ...]] = {
    "placings": (
        "scratch",
        "chase",
        "unknown_distance",
        "chariot",
        "handicap",
        "keirin",
        "match_sprint",
        "placings",
    ),
    "points": ("points", "sprint_points"),
    "madison": ("madison",),
    "tempo": ("tempo",),
    "elimination": ("elimination",),
    "win_and_out": ("win_and_out",),
}
FAMILY_LABELS = {
    "placings": "Scratch Race and Others",
    "points": "Points Race",
    "madison": "Madison",
    "tempo": "Tempo Race",
    "elimination": "Elimination",
    "win_and_out": "Win-and-Out (Club)",
}
_FAMILY_OF = {key: family for family, keys in FAMILIES.items() for key in keys}
assert set(_FAMILY_OF) == set(FORMAT_ENGINE), "every format key needs a ruleset family"

# The page's keys and the scorer's words for them, in the editor's order.
PAGE_LABELS: dict[str, str] = {
    "points_table": "Points Race sprint points",
    "points_last_double": "Points Race double points for the last sprint",
    "points_lap_gained": "Points Race lap gained",
    "points_lap_lost": "Points Race lap lost",
    "madison_table": "Madison sprint points",
    "madison_last_double": "Madison double points for the last sprint",
    "madison_lap_gained": "Madison lap gained",
    "madison_lap_lost": "Madison lap lost",
    "tempo_points": "Tempo Race points per sprint",
    "tempo_lap_gained": "Tempo Race lap gained",
    "tempo_lap_lost": "Tempo Race lap lost",
    "survivors": "Elimination riders in the final sprint",
    "places": "Win-and-Out places",
    "direction": "Win-and-Out direction",
    "lapped_riders_placed": "Lapped riders are placed by laps down",
}
PAGE_KEYS = tuple(PAGE_LABELS)
# The editor's tabs: the keys each family's tab holds. A lap is priced per
# sprint format, so each tab says what its own laps are worth; a shared
# pair above the tabs would not say which race it was for.
FAMILY_KEYS: dict[str, tuple[str, ...]] = {
    "placings": ("lapped_riders_placed",),
    "points": ("points_table", "points_last_double", "points_lap_gained", "points_lap_lost"),
    "madison": ("madison_table", "madison_last_double", "madison_lap_gained", "madison_lap_lost"),
    "tempo": ("tempo_points", "tempo_lap_gained", "tempo_lap_lost"),
    "elimination": ("survivors",),
    "win_and_out": ("places", "direction"),
}
assert {k for keys in FAMILY_KEYS.values() for k in keys} == set(PAGE_KEYS)
LAP_KEYS = tuple(k for k in PAGE_KEYS if "_lap_" in k)
# The venue's words for the formats: optional maps, format key to text.
WORD_KEYS = ("format_names", "format_descriptions")
WORD_LABELS = {"format_names": "Shown as", "format_descriptions": "Description"}
# The same words as the editor table's column headers, in title style.
WORD_HEADERS = {"format_names": "Shown As", "format_descriptions": "Description"}
# A description is a sentence or two on a tooltip; the venue's name for a
# format is drawn on the cards, the board, and the sheets, so it is cut
# where a format's own name would be.
WORD_LIMITS = {"format_names": 60, "format_descriptions": 600}

# The most sprints (or win-and-out places) a race or a ruleset may ask
# for. The longest points races run about 24 sprints (60 km on a 250 m
# track, one every 10 laps), and a madison on a short track a few more;
# 50 leaves room for any of those, while a typo of 100 or 200 for 10
# would make every click of that race take seconds.
MAX_COUNT = 50
# What each number on the page may be: the editor's spin boxes take these
# ranges, and an import is held to them, so every stored page opens in the
# editor as it is and saves back unchanged.
VALUE_RANGES: dict[str, tuple[int, int]] = {
    "tempo_points": (0, 100),
    **{key: (0, 100) for key in LAP_KEYS},
    "survivors": (1, 20),
    "places": (1, MAX_COUNT),
}
# A points table awards at most as many places as a race may ask for, and
# the table field holds that many values at TABLE_MAX written out, so a
# stored table is never cut when the editor shows it.
TABLE_TEXT_MAX = max(MAX_TEXT, len(table_text([TABLE_MAX] * MAX_COUNT)))


class RulesetError(ValueError):
    """A ruleset document or name the app cannot use."""


class UnknownRulesetError(RulesetError):
    """No built-in or stored ruleset has this name."""


class RulesetExistsError(RulesetError):
    """An import or copy would overwrite a stored ruleset of the same name."""


class DefaultRulesetError(RulesetError):
    """The venue's default ruleset cannot be deleted; pick another default first."""


def family_for(format_key: str) -> str:
    try:
        return _FAMILY_OF[format_key]
    except KeyError:
        raise ValueError(f"Unknown race format {format_key!r}") from None


def family_formats(family: str) -> list[Format]:
    """The offered formats a family's tab names, in the picker's order."""
    return [f for f in FORMATS if _FAMILY_OF.get(f.key) == family]


# ----- the venue's words ----------------------------------------------------


def _word(doc: dict[str, Any], key: str, format_key: str) -> str:
    words = doc.get(key) or {}
    return str(words.get(format_key, "") or "").strip() if isinstance(words, dict) else ""


def format_name(doc: dict[str, Any], format_key: str) -> str:
    """What this ruleset calls the format: its own word, or the rulebook's label."""
    return _word(doc, "format_names", format_key) or format_label(format_key)


def format_description(doc: dict[str, Any], format_key: str) -> str:
    """The ruleset's one line about the format, blank unless the venue wrote one."""
    return _word(doc, "format_descriptions", format_key)


def words_for(store: Store | None, ruleset_name: str, format_key: str) -> dict[str, str]:
    """The keys a new race copies beside its rules: only the words that differ from the rulebook's.

    A ruleset that is gone contributes nothing, as its rules fall back to
    the rulebook's.
    """
    try:
        doc = ruleset_for(store, ruleset_name)
    except RulesetError:
        return {}
    out = {}
    if _word(doc, "format_names", format_key):
        out["format_name"] = format_name(doc, format_key)
    if _word(doc, "format_descriptions", format_key):
        out["format_description"] = format_description(doc, format_key)
    return out


def race_format_name(race: Race) -> str:
    """The format as the race's own copy of its rules names it, else the rulebook's label."""
    return str((race.rules or {}).get("format_name") or "").strip() or format_label(race.format)


def race_short_name(race: Race) -> str:
    """The race's name for a screen that shows its group beside it.

    A race saved with a blank Name is named for its group and format,
    "Juniors Scratch Race", so the name stays distinct in the USAC CSV.
    Beside a group tag that reads the group twice, so the window, the
    board, and the sheets show the format alone.
    A name the scorer typed is theirs and shows whole.
    """
    return race_format_name(race) if has_default_name(race) else race.name


def has_default_name(race: Race) -> bool:
    """Whether the race's name is the one a blank Name saves as: group and format."""
    default = " ".join(f"{race.group_label} {race_format_name(race)}".split()).casefold()
    return " ".join(race.name.split()).casefold() == default


def race_format_description(race: Race) -> str:
    return str((race.rules or {}).get("format_description") or "").strip()


# ----- built-in -----------------------------------------------------------


def is_builtin(name: str) -> bool:
    # The label counts too: an exported built-in carries it as its name,
    # and a stored ruleset under the same label would be indistinguishable.
    key = name.strip().casefold()
    return key in R.PRESETS or key == BUILTIN_LABEL.casefold()


def builtin_ruleset() -> dict[str, Any]:
    """The rulebook's page: USAC 2M2(f) and UCI 3.2.118 sprint points and
    lap value, USAC 2E3(f) survivors, USAC 2C4 lapped riders."""
    points = R.points_race_rules()
    return {
        "name": BUILTIN_LABEL,
        "points_table": list(points.intermediate_points),
        "points_last_double": True,
        "madison_table": list(R.madison_rules().intermediate_points),
        "madison_last_double": True,
        "tempo_points": R.tempo_rules().intermediate_points[0],
        **{key: R.RULEBOOK_LAP_POINTS for key in LAP_KEYS},
        "survivors": R.elimination_rules().survivors,
        "places": R.win_and_out_rules().places,
        "direction": R.win_and_out_rules().direction,
        "lapped_riders_placed": R.placings_rules().lapped_riders_placed_by_laps,
    }


def formats_for(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """One rules dict per family, built from the page. Raises ValueError
    for a value a rules class refuses."""

    def sprint(family: str, table: Any, double: bool, unit: str = "rider") -> dict[str, Any]:
        table = tuple(int(v) for v in table)
        final = tuple(2 * p for p in table) if double else table
        return R.SprintPointsRules(
            intermediate_points=table,
            final_points=final,
            lap_gained_points=int(doc[f"{family}_lap_gained"]),
            lap_lost_points=int(doc[f"{family}_lap_lost"]),
            scored_unit=unit,
        ).to_dict()

    survivors = int(doc["survivors"])
    return {
        "placings": R.PlacingsRules(
            lapped_riders_placed_by_laps=bool(doc["lapped_riders_placed"])
        ).to_dict(),
        "points": sprint("points", doc["points_table"], bool(doc["points_last_double"])),
        "madison": sprint(
            "madison", doc["madison_table"], bool(doc["madison_last_double"]), "team"
        ),
        "tempo": sprint("tempo", (int(doc["tempo_points"]),), False),
        "elimination": R.EliminationRules(
            survivors=survivors, final_by_sprint=survivors > 1
        ).to_dict(),
        "win_and_out": R.WinAndOutRules(
            places=int(doc["places"]), direction=str(doc["direction"])
        ).to_dict(),
    }


# ----- lookup -------------------------------------------------------------


def ruleset_names(store: Store | None) -> list[str]:
    """The built-in first, then the stored names in list order."""
    names = [BUILTIN]
    if store is not None:
        names += [r.name for r in store.rulesets()]
    return names


def ruleset_label(name: str) -> str:
    return BUILTIN_LABEL if is_builtin(name) else name


DELETED = "(deleted)"


def ruleset_shown(name: str, known: Iterable[str]) -> str:
    """A race's ruleset as the screen names it: "(deleted)" when no ruleset has the name now.

    The race keeps its rules and the name it was made from; only the
    label says the ruleset is gone. ``known`` is the stored rulesets' names.
    """
    if is_builtin(name) or name in set(known):
        return ruleset_label(name)
    return f"{name} {DELETED}"


def ruleset_for(store: Store | None, name: str) -> dict[str, Any]:
    """The page behind a name: the built-in, or a stored row's document."""
    if is_builtin(name):
        return builtin_ruleset()
    row = store.ruleset_by_name(name) if store is not None else None
    if row is None:
        raise UnknownRulesetError(f"no ruleset named {name!r}")
    return row.doc


def rules_for(
    store: Store | None, ruleset_name: str, format_key: str, **overrides: Any
) -> R._Rules:
    """The rules object a race of this format gets from the named ruleset.

    ``overrides`` are the per-race fields the race editor sets on top
    (sprint_count, places, laps_count_for_ranking). A survivors
    override also decides ``final_by_sprint`` unless given, since one
    survivor means no final sprint (EliminationRules docstring).
    """
    family = family_for(format_key)
    doc = ruleset_for(store, ruleset_name)
    try:
        data = formats_for(doc)[family]
    except (KeyError, TypeError, ValueError) as exc:
        raise RulesetError(f"ruleset {ruleset_name!r} cannot be used: {exc}") from None
    data.update(overrides)
    if "survivors" in overrides and "final_by_sprint" not in overrides:
        data["final_by_sprint"] = int(overrides["survivors"]) > 1
    return R.rules_from_dict(data)


# ----- the venue's default --------------------------------------------------


def default_ruleset_name(store: Store) -> str:
    """The setting, or the rulebook when it is unset or names a ruleset that is gone."""
    name = store.get_setting(DEFAULT_SETTING)
    if isinstance(name, str) and name.strip():
        if is_builtin(name):
            return BUILTIN
        row = store.ruleset_by_name(name)
        if row is not None:
            return row.name
    return BUILTIN


def set_default_ruleset(store: Store, name: str) -> None:
    ruleset_for(store, name)  # must exist
    store.set_setting(DEFAULT_SETTING, BUILTIN if is_builtin(name) else name)


# ----- validation -----------------------------------------------------------


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_ruleset(doc: Any) -> list[str]:
    """Everything wrong with a page, in the scorer's words. Empty means usable."""
    if not isinstance(doc, dict):
        return ["The file does not hold a ruleset"]
    problems: list[str] = []
    name = doc.get("name")
    if not isinstance(name, str) or not name.strip():
        problems.append("The ruleset needs a name")
    missing = [PAGE_LABELS[k] for k in PAGE_KEYS if k not in doc]
    if missing:
        return [*problems, "Missing: " + ", ".join(missing)]
    for key in ("points_table", "madison_table"):
        table = doc[key]
        if not isinstance(table, list | tuple) or not table:
            problems.append(f"{PAGE_LABELS[key]}: needs at least one value")
        elif not all(_is_count(v) and v <= TABLE_MAX for v in table):
            problems.append(f"{PAGE_LABELS[key]}: must be whole numbers from 0 to {TABLE_MAX}")
        elif len(table) > MAX_COUNT:
            problems.append(f"{PAGE_LABELS[key]}: must be {MAX_COUNT} values or fewer")
    for key in ("points_last_double", "madison_last_double", "lapped_riders_placed"):
        if not isinstance(doc[key], bool):
            problems.append(f"{PAGE_LABELS[key]}: must be yes or no")
    for key, (lo, hi) in VALUE_RANGES.items():
        if not _is_count(doc[key]) or not lo <= doc[key] <= hi:
            problems.append(f"{PAGE_LABELS[key]}: must be a whole number from {lo} to {hi}")
    if doc["direction"] not in ("forward", "reverse"):
        problems.append(f"{PAGE_LABELS['direction']}: must be forward or reverse")
    for key in WORD_KEYS:
        words = doc.get(key)
        if words is None:
            continue
        if not isinstance(words, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in words.items()
        ):
            problems.append(f"{WORD_LABELS[key]}: must be text per format")
        elif unknown := sorted(set(words) - set(_FAMILY_OF)):
            problems.append(f"{WORD_LABELS[key]}: not a format: {', '.join(unknown)}")
    if not problems:
        try:
            formats_for(doc)
        except (TypeError, ValueError) as exc:
            problems.append(str(exc))
    return problems


# ----- building and saving --------------------------------------------------


def apply_values(
    doc: dict[str, Any],
    *,
    lap_points: int | None = None,
    lap_gained: int | None = None,
    lap_lost: int | None = None,
    **values: Any,
) -> dict:
    """A copy of the page with the given values set; None leaves a value alone.

    ``lap_points`` prices a lap gained and a lap lost in every sprint
    format at once, the usual case; ``lap_gained`` and ``lap_lost`` do
    one side across the formats. The other keyword names are the page's
    own keys, so a single format's lap is ``points_lap_gained`` and so on.
    """
    unknown = set(values) - set(PAGE_KEYS) - set(WORD_KEYS)
    if unknown:
        raise ValueError(f"not ruleset values: {', '.join(sorted(unknown))}")
    out = json.loads(json.dumps(doc))
    for side, value in (("gained", lap_points), ("lost", lap_points), ("gained", lap_gained), ("lost", lap_lost)):  # fmt: skip
        if value is not None:
            for key in LAP_KEYS:
                if key.endswith(side):
                    out[key] = value
    for key, value in values.items():
        if value is not None:
            out[key] = list(value) if key.endswith("_table") else value
    return _page_only(out) if any(k in WORD_KEYS for k in values) else out


def _check_storable_name(name: str) -> str:
    name = clean_line(name)
    if not name:
        raise RulesetError("The ruleset needs a name")
    if is_builtin(name):
        raise RulesetError(f"{ruleset_label(name)} is built in; choose another name")
    return name


def _page_only(doc: dict[str, Any]) -> dict[str, Any]:
    """The name, the page keys and the words that are set, nothing a file may have carried along.

    A word map is kept only with its blank entries dropped, and not at
    all when nothing is left, so a ruleset with no words of its own is
    the same document as one saved without the word fields.
    """
    out = {"name": doc["name"], **{k: doc[k] for k in PAGE_KEYS}}
    for key in WORD_KEYS:
        # One line each, as every other name is: a pasted line break or a
        # direction override would garble the surface, the board and the sheet.
        words = {
            k: clean_line(v, WORD_LIMITS[key])
            for k, v in (doc.get(key) or {}).items()
            if isinstance(v, str) and clean_line(v, WORD_LIMITS[key])
        }
        if words:
            out[key] = words
    return out


def save_ruleset(store: Store, doc: dict[str, Any], ruleset_id: int | None = None) -> Ruleset:
    """Validate, then insert (ruleset_id None) or replace the stored page."""
    problems = validate_ruleset(doc)
    if problems:
        raise RulesetError("; ".join(problems))
    doc = _page_only(doc)
    name = _check_storable_name(doc["name"])
    if ruleset_id is None:
        return store.add_ruleset(name, doc)
    # The editor's Name field is how a ruleset is renamed; the default
    # setting names it, so it follows. Decided before the write, as
    # afterwards the setting names a row that is gone.
    was_default = default_ruleset_name(store) == store.ruleset(ruleset_id).name
    row = store.update_ruleset(ruleset_id, name=name, doc=doc)
    if was_default:
        set_default_ruleset(store, row.name)
    return row


def copy_ruleset(store: Store, source_name: str, new_name: str) -> Ruleset:
    """ "Duplicate": a stored copy of the built-in or a stored ruleset under a new name."""
    new_name = _check_storable_name(new_name)
    existing = store.ruleset_by_name(new_name)
    if existing is not None:
        raise RulesetExistsError(f"A ruleset named {existing.name} already exists")
    doc = dict(ruleset_for(store, source_name))
    doc["name"] = new_name
    return save_ruleset(store, doc)


def delete_ruleset(store: Store, ruleset_id: int) -> None:
    """Delete a stored ruleset, unless it is the venue's default."""
    current = store.ruleset(ruleset_id)
    if default_ruleset_name(store) == current.name:
        raise DefaultRulesetError(
            f"{current.name} is the default ruleset; set another default first"
        )
    store.delete_ruleset(ruleset_id)


# ----- files ----------------------------------------------------------------


def export_ruleset(doc: dict[str, Any], path: str | os.PathLike[str]) -> Path:
    """Write one ruleset to a JSON file, readable by eye and by import_ruleset."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def _unreadable(path: Path, exc: Exception) -> str:
    """Why a ruleset file cannot be read, as one sentence for the red line.

    The file's name is never first, so capitalizing the sentence never
    respells it, and the OS's or the parser's own text never reaches the
    scorer.
    """
    name = path.name or str(path)
    # Windows refuses a folder as PermissionError, so the path is asked
    # rather than the exception.
    if path.is_dir():
        return f"Could not read {name}: it is a folder"
    if isinstance(exc, FileNotFoundError):
        return f"Could not find {name}"
    if isinstance(exc, PermissionError):
        return f"Could not read {name}: permission denied"
    if isinstance(exc, OSError):
        return f"Could not read {name}"
    return f"Could not read {name}: it is not a ruleset file"


def read_ruleset_file(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Parse and validate a ruleset file without storing it."""
    path = Path(path)
    try:
        # utf-8-sig: a file saved by a Windows editor may open with a BOM.
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    # A deeply nested file exhausts the parser's recursion; it is as
    # unreadable as any other file that is not a ruleset.
    except (OSError, ValueError, RecursionError) as exc:
        raise RulesetError(_unreadable(path, exc)) from None
    if not isinstance(doc, dict):
        raise RulesetError(_unreadable(path, ValueError()))
    problems = validate_ruleset(doc)
    if problems:
        raise RulesetError(f"Could not import {path.name}. " + "; ".join(problems))
    return _page_only(doc)


def import_ruleset(store: Store, path: str | os.PathLike[str], *, replace: bool = False) -> Ruleset:
    """Store the ruleset in a file under its own name.

    A stored ruleset of that name is kept unless ``replace`` is set, in
    which case its document is replaced in place (same row, same default
    setting). The built-in name is always refused.
    """
    doc = read_ruleset_file(path)
    name = _check_storable_name(doc["name"])
    existing = store.ruleset_by_name(name)
    if existing is None:
        return save_ruleset(store, doc)
    if not replace:
        raise RulesetExistsError(f"A ruleset named {existing.name} already exists")
    return save_ruleset(store, doc, existing.ruleset_id)


def family_source_line(family: str) -> str:
    """One dim line at the top of a one-format tab: whose values these are.

    "USAC 2025, article 2M" or "Club format". The many-format tab says it
    per row instead, in its Format column.
    """
    formats = family_formats(family)
    if len(formats) != 1:
        return ""
    (f,) = formats
    return f"{RULEBOOK_LABEL}, article {f.article}" if f.article else "Club format"
