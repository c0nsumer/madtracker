"""USAC results CSV, written to USAC's own 2024 template.

USAC publishes no schema for the results upload. What it publishes is the
sample file "2024 Results template.csv" attached to its help article
(docs/research/usac-results-export.md, "The column list"), so that template
is the requirement: its ten columns, in its order, with its header text
character for character. Nothing else goes in the file, not even a bib,
because the template has no bib column and the header USAC would match for
one is unverified.

One row per rider per race. A team race writes one row per member, each
carrying the team's place.

Race discipline is the code USAC's results site lists for the format,
uppercase as the template's own codes are. The upload accepts SR, ER,
and MAD (a venue's two-day file went through with them); PR, TMPR, SPR,
and KEIR are unverified, so a race's ``usac_discipline``, when set, wins
over the format's code.

Rider Place is the integer rank (tied riders repeat the number, so 1, 1, 3)
or one of DNF, DNS, DQ, DNP. A row with no rank and no status, a rider the
scorer never placed, is written as DNP so no row leaves the file with an
empty place.

The file is UTF-8 without a BOM with CRLF line endings, as the template is.
Every value is a plain trimmed string and nothing is quoted unless a comma,
quote or newline forces it. Values such as the age group "9-14" or a license
with leading zeros are safe in the file but Excel silently turns them into
dates or numbers. The race director must not open the file in Excel and
save it; upload the file this function wrote.
"""

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from madtracker.export.files import write_replacing
from madtracker.export.summary import FINISHED_STATES, build_summary
from madtracker.store import Race, Store

HEADERS = (
    "Race Date",
    "Race discipline",
    "Race Category",
    "Race Gender",
    "Race Class",
    "Race Age Group",
    "Rider License",
    "Rider First Name",
    "Rider Last Name",
    "Rider Place",
)

# The discipline codes on USAC's public results site, uppercase. The match
# sprint and the keirin are scored as their finals. Every format run as a
# scratch race files as one: USAC 2D5 makes a handicap a scratch race after
# the start, and the club formats are scratch races with a twist.
DISCIPLINE_BY_FORMAT = {
    "chase": "SR",
    "handicap": "SR",
    "elimination": "ER",
    "match_sprint": "SPR",
    "keirin": "KEIR",
    "points": "PR",
    "madison": "MAD",
    "tempo": "TMPR",
    "unknown_distance": "SR",
    "chariot": "SR",
    "win_and_out": "SR",
}
DEFAULT_DISCIPLINE = "SR"
DEFAULT_GENDER = "Mixed"

# The values the race editor offers before any typed ones. Category is the
# rulebook's track categories (1D1, 1D2) plus the template's Open; Class
# is its age-based classes (1C1) plus the template's Senior and
# Collegiate. Races combine them ("Cat 1/2"), so each stays free text.
# Age group has no set list in either, so it offers only what was typed.
CATEGORIES = ("Pro", "Cat 1", "Cat 2", "Cat 3", "Cat 4", "Novice", "Open")
CLASSES = ("Youth", "Junior", "U23", "Elite", "Senior", "Master", "Collegiate")

# USAC awards no ranking points for a race with fewer finishers than this.
MIN_FINISHERS = 3


@dataclass(frozen=True)
class ExportReport:
    rows_written: int = 0
    # Each race written as USAC files it (name, discipline, category,
    # class, gender), so the scorer sees what USAC gets before uploading.
    race_fields: tuple[tuple[str, str, str, str, str], ...] = ()
    # The races left out unfinished, by name, in program order.
    left_out: tuple[str, ...] = ()
    # The warnings about a race written: a blank category, a short field.
    race_notes: tuple[str, ...] = ()
    # Each rider written without a license number, once.
    unlicensed: tuple[str, ...] = ()


def usac_date(event_date: str) -> str:
    """ISO date to M/D/YYYY without leading zeros."""
    year, month, day = event_date.strip()[:10].split("-")
    return f"{int(month)}/{int(day)}/{int(year)}"


def discipline_for(race: Race) -> str:
    return _clean(race.usac_discipline) or DISCIPLINE_BY_FORMAT.get(race.format, DEFAULT_DISCIPLINE)


def _clean(value: str | None) -> str:
    return " ".join((value or "").split())


def usac_gender(value: str | None) -> str:
    """The race editor stores the template word itself; a race never set is Mixed."""
    return _clean(value) or DEFAULT_GENDER


def details_key(
    discipline: str | None,
    category: str | None,
    gender: str | None,
    usac_class: str | None,
    age_group: str | None,
) -> tuple[str, ...]:
    """What USAC appears to tell one race from another by, on one date.

    The template has no race name, so two races alike in all of these
    may be filed as one (docs/research/usac-results-export.md, unverified
    until a real upload). Compared without case, to warn rather than miss.
    """
    values = (discipline, category, usac_gender(gender), usac_class, age_group)
    return tuple(_clean(v).casefold() for v in values)


def usac_key(race: Race) -> tuple[str, ...]:
    return details_key(
        discipline_for(race),
        race.usac_category,
        race.usac_gender,
        race.usac_class,
        race.usac_age_group,
    )


def look_alike(races: Iterable[Race]) -> list[list[Race]]:
    """The races that share a ``usac_key``, two or more to a list, in program order."""
    by_key: dict[tuple[str, ...], list[Race]] = {}
    for race in races:
        by_key.setdefault(usac_key(race), []).append(race)
    return [same for same in by_key.values() if len(same) > 1]


def look_alike_note(names: list[str]) -> str:
    joined = ", ".join(names[:-1]) + (", and " if len(names) > 2 else " and ") + names[-1]
    return (
        f"{joined} have the same USAC details, so USAC may file them as one race."
        " To keep them apart, edit one, change its Category, Class, or Age group, and export again."
    )


def race_fields(race: Race) -> tuple[str, str, str, str, str]:
    """Name, discipline, category, class and gender, as the file has them."""
    return (
        race.name,
        discipline_for(race),
        _clean(race.usac_category),
        _clean(race.usac_class),
        usac_gender(race.usac_gender),
    )


def write_usac_csv(
    store: Store,
    event_id: int,
    path: str | Path,
    *,
    races: Iterable[int] | None = None,
) -> ExportReport:
    """Write the event's finished races; ``races`` (race ids) narrows the set.

    Only provisional and final races are exported. A race the caller named
    that is not finished is left out, and the report names it, rather than
    uploaded half scored.
    """
    event = store.event(event_id)
    wanted = None if races is None else set(races)
    all_races = store.races(event_id)
    if wanted is not None:
        unknown = wanted - {r.race_id for r in all_races}
        if unknown:
            raise ValueError(f"races not in event {event_id}: {sorted(unknown)}")
    date = usac_date(event.event_date)

    written: list[Race] = []
    fields: list[tuple[str, str, str, str, str]] = []
    left_out: list[str] = []
    notes: list[str] = []
    rows: list[list[str]] = []
    # rider_id -> name: one mention per rider per export, since a rider
    # without a license is missing it in every race they ride.
    unlicensed: dict[int, str] = {}
    for race in all_races:
        if wanted is not None and race.race_id not in wanted:
            continue
        if race.state not in FINISHED_STATES:
            left_out.append(race.name)
            continue
        summary = build_summary(store, race)
        written.append(race)
        fields.append(race_fields(race))
        if summary.finishers < MIN_FINISHERS:
            finishers = f"{summary.finishers} finisher" + ("" if summary.finishers == 1 else "s")
            notes.append(
                f"{race.name}: {finishers}. USAC awards no ranking points"
                f" with fewer than {MIN_FINISHERS}."
            )
        if not _clean(race.usac_category):
            notes.append(f"{race.name}: no Category. Edit the race to set one, then export again.")
        for row in summary.rows:
            for rider in row.riders:
                if not rider.license:
                    unlicensed.setdefault(rider.rider_id, rider.name)
                rows.append(
                    [
                        date,
                        discipline_for(race),
                        _clean(race.usac_category),
                        usac_gender(race.usac_gender),
                        _clean(race.usac_class),
                        _clean(race.usac_age_group),
                        _clean(rider.license),
                        _clean(rider.first),
                        _clean(rider.last),
                        row.place,
                    ]
                )

    for same in look_alike(written):
        notes.append(look_alike_note([r.name for r in same]))

    def write(partial: Path) -> None:
        with open(partial, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(HEADERS)
            writer.writerows(rows)

    write_replacing(path, write)
    return ExportReport(
        rows_written=len(rows),
        race_fields=tuple(fields),
        left_out=tuple(left_out),
        race_notes=tuple(notes),
        unlicensed=tuple(unlicensed.values()),
    )
