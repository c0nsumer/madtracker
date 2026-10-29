"""Group labels ("Group A") compared the way the scorer means them.

The scorer's workbook spells one group several ways ("Group A",
"GroupA", "group a"), and a race whose group is typed one way must
still find the riders entered another way. So every comparison ignores
case and spaces, and a newly typed label takes the spelling the event
already uses: the first entry group (in bib order) that matches, then
the first race group. An event then shows one spelling per group.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from madtracker.control import rulesets
from madtracker.control.formats import TEAM_FORMATS
from madtracker.control.program import is_scored
from madtracker.inputs import clean_line
from madtracker.store import Race, Store


def group_key(text: str | None) -> str:
    """The comparison key: no spaces, case folded."""
    return re.sub(r"\s+", "", text or "").casefold()


def same_group(a: str | None, b: str | None) -> bool:
    return bool(group_key(a)) and group_key(a) == group_key(b)


def out_of_group(race_group: str | None, groups: list[str | None]) -> str:
    """``, 1 from Juniors`` for riders in a race's field who are not in its group.

    Shown beside the field's size in the race dialog and the program, so a
    rider racing out of their group is seen where the program is set up
    Nothing for a race without a group. It never
    reaches the scoreboard or the USAC CSV, which keeps USAC's template.
    """
    if not group_key(race_group):
        return ""
    counts: dict[str, int] = {}
    for group in groups:
        if same_group(group, race_group):
            continue
        label = (group or "").strip()
        counts[label] = counts.get(label, 0) + 1
    parts = [
        f"{n} from {label}" if label else f"{n} with no group"
        for label, n in sorted(counts.items(), key=lambda kv: (not kv[0], kv[0].casefold()))
    ]
    return "".join(f", {part}" for part in parts)


def _declared_key(event_id: int) -> str:
    # Under event/<id>/, so deleting the event takes it (Store.delete_event).
    return f"event/{event_id}/groups"


def declared(store: Store, event_id: int) -> list[str]:
    """Groups made in Edit Groups > New Group, which may have no rider or race yet.

    Kept in the file's setting table, not a table of their own: a group
    with riders is still just the label on their entries, and this list
    only holds the names nothing carries yet.
    """
    return list(store.get_setting(_declared_key(event_id), []))


def _save_declared(store: Store, event_id: int, names: list[str]) -> None:
    if names:
        store.set_setting(_declared_key(event_id), names)
    else:
        store.delete_setting(_declared_key(event_id))


def event_spellings(store: Store, event_id: int, exclude_rider_id: int | None = None) -> list[str]:
    """Each group in the event once, in its canonical spelling, entries first.

    ``exclude_rider_id`` leaves one entry out, so a rider whose group is
    being retyped does not hold on to their own old spelling.
    """
    seen: dict[str, str] = {}
    labels = [e.local_group for e in store.entries(event_id) if e.rider_id != exclude_rider_id]
    labels += [r.group_label for r in store.races(event_id)]
    labels += declared(store, event_id)
    for label in labels:
        label = " ".join((label or "").split())
        if label and group_key(label) not in seen:
            seen[group_key(label)] = label
    return list(seen.values())


def canonical_group(
    store: Store, event_id: int, text: str | None, exclude_rider_id: int | None = None
) -> str:
    """``text`` in the spelling the event already uses, or tidied when it is new."""
    tidy = clean_line(text)
    key = group_key(tidy)
    if not key:
        return ""
    for label in event_spellings(store, event_id, exclude_rider_id):
        if group_key(label) == key:
            return label
    return tidy


@dataclass(frozen=True)
class GroupUse:
    """One group of an event: who has it and which races were made from it."""

    label: str
    riders: tuple[int, ...]
    races: tuple[Race, ...]
    # A scored race was run under this name, so the name is history.
    raced: bool


def group_uses(store: Store, event_id: int) -> list[GroupUse]:
    """Every group of the event, by name, with its riders and races."""
    entries = store.entries(event_id)
    races = store.races(event_id)
    uses = []
    for label in sorted(event_spellings(store, event_id), key=str.casefold):
        mine = tuple(e.rider_id for e in entries if same_group(e.local_group, label))
        used = tuple(r for r in races if same_group(r.group_label, label))
        raced = any(is_scored(store, r) for r in used)
        uses.append(GroupUse(label, mine, used, raced))
    return uses


def _spellings_of(store: Store, event_id: int, label: str) -> list[str]:
    """Every stored spelling of the group, so a relabel misses none."""
    found = {e.local_group for e in store.entries(event_id) if same_group(e.local_group, label)}
    return sorted(f for f in found if f)


def add_group(store: Store, event_id: int, name: str) -> str:
    """Make a group with nobody in it yet; its name as stored. ValueError when blank or taken."""
    tidy = clean_line(name)
    if not tidy:
        raise ValueError("the group needs a name")
    taken = next((g for g in event_spellings(store, event_id) if same_group(tidy, g)), None)
    if taken is not None:
        raise ValueError(f"a group named {taken} already exists")
    _save_declared(store, event_id, [*declared(store, event_id), tidy])
    return tidy


def _redeclare(store: Store, event_id: int, old: str, new: str | None) -> None:
    """A declared ``old`` becomes ``new`` (or goes), so a renamed empty group stays listed."""
    before = declared(store, event_id)
    names = [n for n in before if not same_group(n, old)]
    was_declared = len(names) != len(before)
    if was_declared and new and not any(same_group(n, new) for n in names):
        names.append(new)
    _save_declared(store, event_id, names)


def rename_refusal(use: GroupUse) -> str:
    """A group a scored race ran under keeps its name: the result says it."""
    return "Has raced" if use.raced else ""


def delete_refusal(use: GroupUse) -> str:
    """A race was made from the group, so taking it away would leave the race's label orphaned."""
    return "Used by a race" if use.races else ""


def rename_group(store: Store, event_id: int, use: GroupUse, new: str) -> str:
    """Rename the group on its riders and its races; the new name as the event spells it.

    A name the event already uses is that group's, so renaming into it
    merges the two. Refused (ValueError) for a group that has raced or a
    blank name.
    """
    if rename_refusal(use):
        raise ValueError(f"{use.label} has raced, so it keeps its name")
    # Respelling the group itself ("Group b" to "Group B") takes the new
    # spelling; any other name the event knows is that group's.
    tidy = clean_line(new)
    target = tidy if same_group(tidy, use.label) else canonical_group(store, event_id, tidy)
    if not target:
        raise ValueError("the group needs a name")
    # Into a name another group of the event already has: a merge.
    taken = any(same_group(e.local_group, target) for e in store.entries(event_id)) or any(
        same_group(r.group_label, target) for r in store.races(event_id)
    )
    merging = taken and not same_group(target, use.label)
    entries = store.entries(event_id)
    moving = [e.rider_id for e in entries if same_group(e.local_group, use.label)]
    staying = [e.rider_id for e in entries if same_group(e.local_group, target)]
    own = {r.race_id for r in use.races}
    # One write: a failure part way never leaves the riders relabeled and
    # a merge's races not yet following them.
    with store.transaction():
        store.relabel_group(
            event_id,
            _spellings_of(store, event_id, use.label),
            target,
            [r.race_id for r in use.races],
            _defaults_renamed(use.races, target),
        )
        _redeclare(store, event_id, use.label, target)
        if merging:
            # A merge puts two groups' riders in one: each unscored race
            # takes the other group's riders and keeps its own as they
            # were, so a rider trimmed by hand stays out. A plain rename
            # changes a label only.
            others = [r.race_id for r in store.races(event_id) if r.race_id not in own]
            follow_group(store, event_id, moving, race_ids=others)
            follow_group(store, event_id, staying, race_ids=own)
    return target


def _defaults_renamed(races: Iterable[Race], target: str) -> dict[int, dict[str, str]]:
    """The races whose name or USAC Category was the group's default, with the new one.

    A blank Name saves as group and format, and a blank Category as the
    group; a rename that left them would show "Group A Scratch Race"
    beside a Juniors tag, and send the old group to USAC.
    """
    out: dict[int, dict[str, str]] = {}
    for race in races:
        fields = {}
        if rulesets.has_default_name(race):
            fields["name"] = f"{target} {rulesets.race_format_name(race)}"
        if race.usac_category and same_group(race.usac_category, race.group_label):
            fields["usac_category"] = target
        if fields:
            out[race.race_id] = fields
    return out


def delete_group(store: Store, event_id: int, use: GroupUse) -> None:
    """Take the group off its riders. Refused (ValueError) while a race was made from it."""
    if delete_refusal(use):
        raise ValueError(f"{use.label} is the group of a race")
    with store.transaction():
        store.relabel_group(event_id, _spellings_of(store, event_id, use.label), None, [])
        _redeclare(store, event_id, use.label, None)


def follow_group(
    store: Store,
    event_id: int,
    rider_ids: Iterable[int],
    old_group: str | None = None,
    race_ids: Iterable[int] | None = None,
) -> None:
    """Riders whose group just became what their entry says now: their races follow.

    A race made from a group is for that group (design section 6), so
    until the race is scored its field follows the group: a rider who
    joins the group joins the race, whether they came on the roster
    before or after the program was built (a program copied from an
    earlier event meets an empty roster). ``old_group`` is the group the
    riders just left; they come out of that group's unscored races.
    Races of any other group are left alone, so a rider added to one by
    hand stays. A field with a bib clash takes the rider anyway; the
    race's task line names the clash, as for a field filled from a group.
    ``race_ids`` limits the races that follow.
    """
    rider_ids = list(rider_ids)
    only = None if race_ids is None else set(race_ids)
    entries = {e.rider_id: e for e in store.entries(event_id)}
    # A team race's field is its teams, made by hand in Edit Race; a
    # rider joining its group is not yet on a team, so it is left alone.
    races = [
        r
        for r in store.races(event_id)
        if r.group_label
        and r.format not in TEAM_FORMATS
        and (only is None or r.race_id in only)
        and not is_scored(store, r)
    ]
    moves: list[tuple[int, int, bool]] = []
    for race in races:
        field = {e.rider_id for e in store.race_entries(race.race_id)}
        for rider_id in rider_ids:
            entry = entries.get(rider_id)
            joins = entry is not None and same_group(entry.local_group, race.group_label)
            leaves = same_group(old_group, race.group_label) and not joins
            if joins and rider_id not in field:
                moves.append((race.race_id, rider_id, True))
            elif leaves and rider_id in field:
                moves.append((race.race_id, rider_id, False))
    if not moves:
        return
    # One write for every race the riders join or leave, rather than a
    # commit (an fsync) per rider per race.
    with store.transaction():
        for race_id, rider_id, joins in moves:
            if joins:
                store.add_race_entry(race_id, rider_id)
            else:
                store.remove_race_entry(race_id, rider_id)
