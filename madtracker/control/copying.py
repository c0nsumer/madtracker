"""Copying between files and events: a new file from the open one, a program from an earlier event.

One file serves a venue for life (design section 12), so a second
file is rare: another venue, or a practice file. It may take the
open file's settings, logo, rulesets and riders, never its events. A
new event may take an earlier event's program (section 6): the races
with their formats, rulesets and sprint counts or places, with empty
fields. On request it also takes the roster with its bibs and the
races' fields and teams, so the second night of a two-day event is
set up in one click; nothing else.
"""

from dataclasses import dataclass

from madtracker.control import venue
from madtracker.store import DuplicateEntryError, DuplicateError, Store


@dataclass(frozen=True)
class CopyChoice:
    settings: bool = True
    logo: bool = True
    rulesets: bool = True
    riders: bool = True


def copy_venue(src: Store, dst: Store, choice: CopyChoice | None = None) -> dict[str, int]:
    """Copy the chosen parts of ``src`` into the empty ``dst``; returns counts per part."""
    choice = choice or CopyChoice()
    counts = {"settings": 0, "logo": 0, "rulesets": 0, "riders": 0}
    # One write: on disk together, a commit (an fsync) for the whole copy
    # rather than one per setting, ruleset, and rider, and never half a copy.
    with dst.transaction():
        if choice.settings:
            for key in venue.SETTING_KEYS:
                value = src.get_setting(key)
                if value is not None:
                    dst.set_setting(key, value)
                    counts["settings"] += 1
        if choice.logo:
            data = venue.logo_setting(src)
            if data:
                venue.set_logo(dst, data)
                counts["logo"] = 1
        if choice.rulesets:
            for row in src.rulesets():
                if dst.ruleset_by_name(row.name) is None:
                    dst.add_ruleset(row.name, row.doc)
                    counts["rulesets"] += 1
        if choice.riders:
            for r in src.riders():
                try:
                    dst.add_rider(
                        r.first_name,
                        r.last_name,
                        usac_license=r.usac_license,
                        uci_id=r.uci_id,
                        birth_year=r.birth_year,
                        notes=r.notes,
                    )
                except DuplicateError:
                    continue
                counts["riders"] += 1
    return counts


def copy_program(
    store: Store, from_event_id: int, to_event_id: int, with_roster: bool = False
) -> int:
    """Add the earlier event's races to the new one; returns how many.

    The fields are empty unless ``with_roster``, which first enters the
    earlier roster (bibs and groups as they were) and then fills each
    race's field and teams as they were. Riders already on the new
    roster keep their entry. One transaction: never half an event.
    """
    added = 0
    with store.transaction():
        if with_roster:
            for entry in store.entries(from_event_id):
                try:
                    store.add_entry(to_event_id, entry.rider_id, entry.bib, entry.local_group)
                except DuplicateEntryError:
                    continue
        for race in store.races(from_event_id):
            new = store.add_race(
                to_event_id,
                race.name,
                race.format,
                group_label=race.group_label,
                rules_preset=race.rules_preset,
                rules=race.rules,
                rules_version=race.rules_version,
                usac_discipline=race.usac_discipline,
                usac_category=race.usac_category,
                usac_gender=race.usac_gender,
                usac_class=race.usac_class,
                usac_age_group=race.usac_age_group,
            )
            added += 1
            if with_roster:
                for e in store.race_entries(race.race_id):
                    store.add_race_entry(new.race_id, e.rider_id)
                for team in store.teams(race.race_id):
                    copy = store.add_team(
                        new.race_id, team.name, color=team.color, color_hex=team.color_hex
                    )
                    for rider_id in team.members:
                        store.add_team_member(copy.team_id, rider_id)
    return added
