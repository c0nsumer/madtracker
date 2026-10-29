# The data file

Sooner or later someone will want to read a MadTracker data file without MadTracker: to audit a disputed result, make a report the app doesn't, move to another program, or recover a season from a dead laptop. The file is plain SQLite, so `sqlite3` or a few lines of Python can read all of it. This page says what's in it.

This describes schema version 4 (`PRAGMA user_version = 4`) and action payload version 1 for every action kind. The durability design (WAL, sync settings, the kill test) is in [architecture.md](architecture.md#the-action-log) and isn't repeated here. Backups and restores are in [Backups](../madtracker/help/backups.md).

## Identifying the file

- File: `madtracker.sqlite` in the per-user data folder (`%LOCALAPPDATA%\MadTracker`, `~/Library/Application Support/MadTracker`, or `~/.local/share/madtracker`), unless `MADTRACKER_DATA_DIR` says otherwise. File -> Open Data File... can open any name, anywhere. The demo data file that Help -> Demo Data File... builds is `demo/demo.sqlite` under that folder, with its own `backups` folder beside it; it has the same shape as any data file.
- `PRAGMA application_id`: `0x4D414454` (1296122964, ASCII 'MADT'). The app refuses any other id, except on a brand-new empty file.
- `PRAGMA user_version`: the schema version, 4. The app refuses a file newer than itself, and one numbered below the baseline.
- `PRAGMA journal_mode`: `wal` on the live file, `delete` on a backup (one self-contained file).

While the app runs, recent commits can sit in `madtracker.sqlite-wal` (with `-shm` beside it) and not yet be in the main file. So a plain copy of the `.sqlite` alone, taken then, can miss entries or be inconsistent. A clean close checkpoints the WAL (`wal_checkpoint(TRUNCATE)`), after which the `.sqlite` holds everything. For a copy, use an app backup or a cleanly closed file.

A marker file named after the data file (`madtracker.open` for `madtracker.sqlite`) is created on open and removed on a clean close. If it's there and the app isn't running, the last session crashed (the data is fine; SQLite recovers the WAL on the next open). While a window has the file open, it also holds a lock file named after the data file (`madtracker.sqlite.lock`). A second copy of the app refuses a file whose lock another window holds. A lock left by a crash doesn't refuse anything: the app sees that its process is gone and takes the lock over.

## Reading the file safely

- Read a backup, or a cleanly closed copy, rather than the live file. Nothing can change under you that way.
- Open it read-only. In `sqlite3`: `sqlite3 "file:madtracker-2026-10-10-214512.sqlite?mode=ro"`. In Python: `sqlite3.connect("file:...?mode=ro", uri=True)`.
- `immutable=1` (in place of `mode=ro`) skips locking and is fine for a backup or a cleanly closed file. Never use it on a live file: it ignores the `-wal`, so you'd read stale data.
- Never write to the file with another tool, and never try to edit `race_action` (the triggers refuse, on purpose). Fix things in the app, which records a correction as new rows.

## Tables and the design's words

`docs/design.md` section 3 sets one word per idea. The names below are exactly what's in the file:

| Table | Design word | Holds |
|---|---|---|
| `rider` | rider | People, kept from event to event. |
| `event` | event | One date of racing. |
| `roster_entry` | roster (one entry) | A rider entered in an event, with that night's bib and group. |
| `race` | race (the rows of one event, in order, are its program) | One race, its format and the rules it's scored under. |
| `race_entry` | field (individual) | Who starts a race. |
| `team`, `team_member` | team | Teams within one race, and their riders. |
| `race_action` | (the scorer's entries) | The append-only log every result is replayed from. |
| `race_state_change` | (the logbook's result lines) | When each race's result became provisional or final, or left either. |
| `ruleset` | ruleset | The venue's own rulesets. |
| `standings`, `standings_event`, `standings_race_excluded`, `standings_penalty` | standings | Multi-race standings: a points table over races from one event or several, with the events it takes, the races left out, and the omnium penalties. |
| `setting` | (settings) | Venue values and a few per-file UI states. |

A Result isn't stored; it's replayed from `race_action` every time. A standings isn't stored as numbers either: it's a definition, and its table is replayed from the races it names. Series is a text column on `event`, not a table.

Optional identifiers (USAC License, UCI ID, birth year, group) are NULL when unknown; free text is NOT NULL with an empty default. Timestamps (`*_utc`) are ISO 8601 UTC text, eg: `2026-10-09T03:05:07.345+00:00`, for audit only (order never depends on them, since a laptop clock can be wrong).

## rider

| Column | Type | Meaning | Design word |
|---|---|---|---|
| `rider_id` | INTEGER PK | | rider |
| `first_name`, `last_name` | TEXT NOT NULL | | |
| `usac_license` | TEXT | USA Cycling license number, digits only and without leading zeros as USAC prints it ("0710004" is stored as "710004"), NULL if none. | USAC License |
| `uci_id` | TEXT | The 11-digit UCI ID, NULL if none. The app refuses one that another rider already holds, though no index enforces it. | UCI ID |
| `birth_year` | INTEGER | NULL if unknown. | birth year |
| `notes` | TEXT NOT NULL '' | | |
| `created_utc`, `updated_utc` | TEXT NOT NULL | | |

Indexes: `rider_usac_license`, a partial UNIQUE index on `usac_license WHERE usac_license IS NOT NULL` (one rider per license), and `rider_by_name` on `(last_name, first_name)`. A rider has raced when they're in a race that has a `race_action` row or a state other than `setup`. A rider who has raced is never deleted. Deleting any other rider deletes their `team_member`, `race_entry`, and `roster_entry` rows with them. A merge moves a spare rider's `roster_entry`, `race_entry`, and `team_member` rows to the kept rider and deletes the spare. Where both have a row for one event or race, the kept rider's row stays, filling an empty bib or group from the spare's. Values the scorer chose in Merge Riders (the rider's columns, a bib or group per event, a team per race) are written in the same transaction. A merge is refused while the spare has raced.

## event

| Column | Type | Meaning | Design word |
|---|---|---|---|
| `event_id` | INTEGER PK | | event |
| `name` | TEXT NOT NULL | | event name |
| `event_date` | TEXT NOT NULL | ISO date, `YYYY-MM-DD` (the app checks this). | date |
| `venue` | TEXT NOT NULL '' | The venue name when the event was created. The `venue/name` setting wins when set. | venue (name) |
| `notes` | TEXT NOT NULL '' | | |
| `created_utc` | TEXT NOT NULL | | |
| `series` | TEXT NOT NULL '' | Series name, empty for none. | series |

## roster_entry

| Column | Type | Meaning | Design word |
|---|---|---|---|
| `event_id` | INTEGER NOT NULL -> `event` | | event |
| `rider_id` | INTEGER NOT NULL -> `rider` | | rider |
| `bib` | INTEGER, CHECK `bib IS NULL OR bib > 0` | That night's bib. NULL until the venue assigns it. | bib |
| `local_group` | TEXT | The group on this entry. NULL if none. The rider record has no group, since a rider changes groups as they age and upgrade. | group |

Primary key `(event_id, rider_id)`. A bib isn't unique in the event: two riders who never share a race may wear one number. The program refuses a bib twice in one race's field, and scores a race only when every rider in its field has a bib. Trigger `roster_entry_in_use` refuses deleting an entry while the rider is in a race of that event.

## race

| Column | Type | Meaning | Design word |
|---|---|---|---|
| `race_id` | INTEGER PK | | race |
| `event_id` | INTEGER NOT NULL -> `event` | | event |
| `seq_in_event` | INTEGER NOT NULL | Position in the event's order. | program (order) |
| `name` | TEXT NOT NULL | | race name |
| `format` | TEXT NOT NULL | A format key, eg: `chase`, `points`, `madison` (see "Formats and rules_json"). | format |
| `group_label` | TEXT NOT NULL '' | The group the field was filled from. | group |
| `rules_preset` | TEXT NOT NULL '' | The ruleset's name: `rulebook` or a `ruleset.name`. | ruleset |
| `rules_json` | TEXT NOT NULL '{}' | The full rules the race is scored under. | |
| `rules_version` | TEXT NOT NULL '' | The scoring code's `RULES_VERSION` when the rules were saved, eg: `2026.10`. | |
| `usac_discipline`, `usac_category`, `usac_class`, `usac_age_group` | TEXT | Fields for the USAC CSV. NULL lets the export derive or leave the value. | |
| `usac_gender` | TEXT | Whom the race is for: `Men`, `Women`, or `Mixed`, set by **Gender** in the race editor. The USAC CSV writes it as stored. NULL is written as `Mixed`. | |
| `state` | TEXT NOT NULL 'setup', CHECK in `setup`, `running`, `provisional`, `final` | | result (provisional or final) |
| `announced_utc` | TEXT | Set the first time the race becomes provisional. | |
| `notes` | TEXT NOT NULL '' | | |

Index `race_by_event` on `(event_id, seq_in_event)`. A race row is ordinary data. The Add Race / Edit Race dialog (Edit Event) can change its name, whom it is for, and its USAC fields after scoring. Once a race has an entry, the dialog keeps its format, group, ruleset, sprints or places, field, and teams as they are.

## race_entry

| Column | Type | Meaning | Design word |
|---|---|---|---|
| `race_id` | INTEGER NOT NULL -> `race` | | race |
| `rider_id` | INTEGER NOT NULL -> `rider` | | rider |

Primary key `(race_id, rider_id)`. Trigger `race_entry_needs_roster_entry` refuses a rider who isn't on that event's roster. The bib is found through `roster_entry`.

## team and team_member

`team`:

| Column | Type | Meaning | Design word |
|---|---|---|---|
| `team_id` | INTEGER PK | | team |
| `race_id` | INTEGER NOT NULL -> `race` | Teams belong to one race. | race |
| `name` | TEXT NOT NULL | What the scorer types, usually a color ("Yellow"). | team name |
| `color` | TEXT NOT NULL '' | Color name. | color |
| `color_hex` | TEXT | Display color, eg: `#2f6bff`, NULL if none. | |
| `seq` | INTEGER NOT NULL | Display order within the race. | |

UNIQUE `(race_id, name)`.

`team_member`: `team_id` (INTEGER NOT NULL -> `team`, ON DELETE CASCADE) and `rider_id` (INTEGER NOT NULL -> `rider`), primary key `(team_id, rider_id)`. Trigger `team_member_needs_race_entry` refuses a rider who isn't in the race's `race_entry`, or who is already on another team in the same race.

## race_action

This is the part that matters. Every scorer entry is one row, and rows are never changed or removed.

| Column | Type | Meaning |
|---|---|---|
| `action_id` | INTEGER PK | Order of entry. Replay in `action_id` order. |
| `action_uuid` | TEXT NOT NULL UNIQUE | Identifies the row across files and exports. |
| `race_id` | INTEGER NOT NULL -> `race` | |
| `recorded_utc` | TEXT NOT NULL | Audit only. |
| `kind` | TEXT NOT NULL | The action kind (table below), or `void`. |
| `schema_ver` | INTEGER NOT NULL, CHECK `>= 1` | Payload version. |
| `payload_json` | TEXT NOT NULL | JSON object, keys sorted. |
| `voids_action_id` | INTEGER -> `race_action` | Set only on a `void` row. |
| `operator_note` | TEXT | Bookkeeping tags (below), NULL on a plain entry. |

Table CHECK: `(kind = 'void') = (voids_action_id IS NOT NULL)`. Indexes: `race_action_by_race` on `(race_id, action_id)`, and `race_action_by_void`, a partial index on `voids_action_id WHERE voids_action_id IS NOT NULL`. The second makes "is this row already voided" a lookup instead of a scan of every action in the file, so Undo and corrections stay quick as the venue's history grows.

Triggers:

- `race_action_no_update` and `race_action_no_delete`: any UPDATE or DELETE aborts with "race_action is append-only".
- `race_action_void_target`: a `void` must point at an existing non-void row of the same race that no other void already targets.

Undo is a `void` row (payload `{}`, `schema_ver` 1) pointing at the undone row. A void is never voided; redo appends the original entry again. So a row is live when it isn't a void and no void points at it.

`operator_note` carries tags from `madtracker/control/race.py` that never change a replay, which always reads the live rows in `action_id` order: `[action N]` (the rows and voids scorer action N wrote, undone together), `[undo of N]` (the rows and voids the Undo of action N wrote), `corrected` (the void a correction writes), `restored by undo` (a row Undo appended again), and `kept in order by undo` (a row Undo appended again only so the restored rows keep their place). A row Undo appends also carries `[from N]`, where N is the row it copies, or that row's own `[from]`. That number is the row's place in the order: a later Undo uses it to put the row back where it stood, and a correction reads a DNF's moment from it. A correction's first row may also carry its own words after `said:` ("[action 12] said: Moved #7 Maya Petrakis to 2nd"); the logbook shows them above the new entry, since the two orders alone do not say who moved.

One action's rows share a transaction. Its voids are written before its new rows, so a correction reads in `action_id` order as the scorer made it: the void of the old row, then its replacement.

## race_state_change

`race.state` holds only where a race is now. This table keeps how it got there: a row each time a race's result becomes provisional or final, or leaves either (an Undo that takes back the completing entry, or Reopen). Nothing replays it, and Undo never touches it, so it can't change a result. It's append-only like `race_action`.

| Column | Type | Meaning |
|---|---|---|
| `change_id` | INTEGER PK | Order of change. |
| `race_id` | INTEGER NOT NULL -> `race` | |
| `from_state`, `to_state` | TEXT NOT NULL | The race states before and after, eg: `provisional` -> `final`. |
| `recorded_utc` | TEXT NOT NULL | When, for the logbook and audit. |
| `after_action_id` | INTEGER NOT NULL | The newest `race_action` row in the file at the time; it places the line in the logbook without trusting the clock. |

Index `race_state_change_by_race` on `(race_id, change_id)`. Triggers `race_state_change_no_update` and `race_state_change_no_delete` abort any UPDATE or DELETE.

## Getting the live rows

This query gives the rows that `Store.live_actions(race_id)` returns, and it's what scoring replays. (The app's own statement is written as `NOT IN` over the race's void rows, which reads the same rows in one pass over the race's index.)

```sql
SELECT e.action_id, e.kind, e.schema_ver, e.payload_json
FROM race_action e
WHERE e.race_id = 3
  AND e.kind <> 'void'
  AND NOT EXISTS (
    SELECT 1 FROM race_action v
    WHERE v.kind = 'void' AND v.voids_action_id = e.action_id
  )
ORDER BY e.action_id;
```

The whole history, voids included, is the same query without the last two conditions.

## Action kinds

Payload keys are the field names of the classes in `madtracker/scoring/actions.py`. Every kind is at `schema_ver` 1 as of this writing.

An entrant id is a `rider_id` in an individual race and a `team_id` in a team race (a Madison, or any race whose rules say `"scored_unit": "team"`). Bibs and colors never appear in payloads, so fixing a bib typo on the roster can't change a recorded entry.

Places are a list of lists, best first: `[[35], [12, 18], [], [4]]` is 35 first, 12 and 18 tied second, third not seen by the judges, 4 fourth. An empty inner list is a place the judges couldn't call. The current UI never writes one.

| `kind` | Payload | Meaning |
|---|---|---|
| `sprint_result` | `sprint_no` (int), `places` (places) | Places in one sprint. In a Win-and-Out, `sprint_no` is the place lap. |
| `finish_order` | `places` (places) | The full order across the line at the end. Entrants left out share the next rank. |
| `lap_gained` | `entrant_ids` (list of int), `sprint_no` (int or null) | One lap gained by each listed entrant. `sprint_no` notes the sprint it was taken at. |
| `lap_lost` | `entrant_ids` (list of int) | One lap lost by each. |
| `eliminated` | `sprint_no` (int), `entrant_ids` (list of int) | Out at that sprint, sharing one place. An empty list is no elimination at that sprint. |
| `status` | `entrant_id` (int), `status` (`DNS`, `DNF`, `DQ`, or `DNP`), `reason` (text) | A non-finisher mark. A later `status` row for the same entrant replaces the earlier one (a DQ after a DNF, for a protest), so the engine keeps the newest; the app refuses the same mark twice. |
| `out_of_finish` | `entrant_id` (int) | A rider or team kept out of the final sprint by a mishap (USAC 2M7(b), 2M8(a)). Not a status: the entrant is placed on the points and laps held. Points Race, Madison, and Tempo Race only. |
| `withdrawn` | `entrant_id` (int) | A rider or team withdrawn at this moment, or classified as though they had been (USAC 2O3(e), 1M6(d)). Not a status: the entrant is placed after every finisher, the latest withdrawn highest, with the points and laps held as figures, and no later scoring row names them. Races placed at the line, Points Race, Madison, and Tempo Race only. |
| `race_ended` | `after_sprint` (int) | The officials ended the race with its results standing, after the sprint named (USAC 2M6, 2N5). The race is complete on the sprints ridden: no sprint doubles and there is no final-sprint place. Points Race and Madison only. |
| `race_shortened` | `sprint_count` (int) | The officials shortened the race to this many sprints (USAC 1G4(b)). The race rides on, and the last sprint under the new count is the final sprint (doubled in a Points Race or Madison, USAC 2M2(f)). The latest row is the count in force; the race keeps the count it was set with. Points Race, Madison, and Tempo Race only. |
| `points_adjusted` | `entrant_id` (int), `points` (int) | A points penalty, as a ruling. Each row is the difference from the penalty standing before it: negative as the penalty grows, positive as it is lowered or taken off. The sum is the penalty shown, and validation keeps it at or below zero. Points Race, Madison, and Tempo Race only. |
| `lap_not_counted` | `entrant_ids` (list of int) | One lap gained by each listed entrant that the officials ruled did not count (USAC 8D5(b)). It cancels the newest uncancelled `lap_gained` of that entrant, with the lap's points. |
| `void` | `{}` | Undo of `voids_action_id`. |

The app writes every kind above.

The schema_ver rule: when a payload's shape changes, that kind's `SCHEMA_VER` goes up and old rows keep their number. `decode_action` refuses a `schema_ver` newer than it knows, or an unknown `kind`, rather than guessing. A parser should do the same, since a silent misread changes a result.

## setting

`key TEXT PRIMARY KEY`, `value_json TEXT NOT NULL`. Each value is JSON, so read it with `json.loads`. Keys in use:

| Key | Value | Meaning |
|---|---|---|
| `venue/name` | string | The venue name on the board and the PDF. |
| `venue/logo_png` | string | The venue logo as base64 PNG bytes, scaled to fit 2880 by 1200 px when chosen. Absent means the bundled placeholder. |
| `backup/dir` | string | The extra backup folder, empty for none. |
| `export/dir` | string | The folder the exports offer to save in, empty for Documents. |
| `backup` | `{"taken_at": "2026-10-10T21:45:12", "source": string, "event": string}` | Present only in a backup: when it was taken (local time), the data file it came from, and the event that was open. It makes the file a backup whatever it's called. A restore deletes it from its copy. |
| `board/rider_label` | string | How the scoreboard names a rider: `names`, `bibs_names`, or `bibs`. Absent means `bibs_names`. |
| `board/accent` | string | The scoreboard's accent color, eg: `#ffc83d` (the default when absent). |
| `rules/default_ruleset` | string | `rulebook` or a `ruleset.name`. |
| `ui/live_race_id` | integer | The race that was live, selected on the next open. |
| `event/{event_id}/groups` | list of strings | Groups made in Edit Groups > New Group that may have no rider or race yet. A group with riders is only the label on their roster entries. Deleting the event deletes the row. |
| `race/{race_id}/staged` | `{"groups": [[int, ...], ...], "sprint": int or null}` | Clicks not yet recorded as an entry (eg: places of a sprint before Record Sprint). Not an entry, never in the log. |

Per-machine choices (the scoreboard display, the last event shown, the last data file, the scoring window's place and size) are in Qt's QSettings, not in this file.

## ruleset

| Column | Type | Meaning |
|---|---|---|
| `ruleset_id` | INTEGER PK | |
| `name` | TEXT NOT NULL UNIQUE COLLATE NOCASE | "House Rules" and "house rules" can't both exist. |
| `json` | TEXT NOT NULL | The ruleset page, below. |
| `created_utc`, `updated_utc` | TEXT NOT NULL | |

The built-in ruleset isn't a row. Races and the default setting name it by the key `rulebook`; the app shows it as USAC 2025 + Club formats. The `json` column is one flat page of values, and its `name` key always matches the column:

```json
{
  "direction": "forward",
  "lapped_riders_placed": true,
  "madison_lap_gained": 20,
  "madison_lap_lost": 20,
  "madison_last_double": true,
  "madison_table": [5, 3, 2, 1],
  "name": "House Rules",
  "places": 3,
  "points_lap_gained": 20,
  "points_lap_lost": 20,
  "points_last_double": true,
  "points_table": [5, 3, 2, 1],
  "survivors": 2,
  "tempo_lap_gained": 20,
  "tempo_lap_lost": 20,
  "tempo_points": 1
}
```

Those are the built-in USAC 2025 values. `*_table` is points by place, `*_last_double` doubles the last sprint, `*_lap_gained` and `*_lap_lost` price a lap in that format, `survivors` ride an Elimination's final sprint, and `places` and `direction` are for the Win-and-Out. Two optional keys hold the venue's words for its formats, each a map from a format key to text: `format_names` (what the format is called, blank or missing means the rulebook's label) and `format_descriptions` (one line shown under the scorer's header). For example `"format_names": {"elimination": "Devil"}`. A ruleset is a starting point, not a reference: a saved race copies its rules in full into `race.rules_json`, so editing or deleting a ruleset never changes a past race.

## standings

A multi-race standings is a points table over races from one event or several, such as the venue's 2 Day Omnium over a Friday and a Saturday. The file holds only its definition. Every view and the PDF replay the races it names, as they do for a race's own result.

The screens, the help, and the code call these Multi-Race Standings; the tables keep the name `standings`, since renaming them would be a schema migration nobody sees.

| Column | Type | Meaning |
|---|---|---|
| `standings_id` | INTEGER PK | |
| `name` | TEXT NOT NULL UNIQUE COLLATE NOCASE | Eg: "Oktoberfest 2 Day Omnium". "Weekend" and "weekend" can't both exist, since the PDF is named from it. |
| `kind` | TEXT NOT NULL | How it scores: `team_omnium` (the Madison totals summed), `team_omnium_places` (points for each team's place in each Madison, summed), `omnium_places` (points for each rider's place in each race but the Madison, summed), or `four_race_omnium` (USAC 2O3: the Scratch Race, Tempo Race, Elimination, and Points Race per event). |
| `rules_json` | TEXT NOT NULL | The kind's values, as the `to_dict()` of `AggregateRules` in `madtracker/scoring/rules.py` (without `engine`). `{}` means the kind's defaults. Keys present override the defaults. |
| `created_utc`, `updated_utc` | TEXT NOT NULL | |

`standings_event` is `(standings_id, event_id)`, one row per ticked event. `standings_race_excluded` is `(standings_id, race_id)`, one row per race the scorer left out. `standings_penalty` is `(standings_id, rider_id, points)`, one row per rider with an omnium penalty, `points` above zero (a penalty taken off is the row deleted). All three have the id pair as their primary key and cascade: deleting a standings deletes its rows, and deleting an event, a race, or a rider deletes the rows that name it.

A Team Omnium by Points (`team_omnium`) counts every `madison` race in the ticked events, except the left-out ones. It makes one table per race group (`race.group_label`, compared without case or spaces). In each table, a team is its two riders (`team_member`), whatever it's called in each race. It's shown under the name and color it raced under last. Each team's total is the sum of its Madison totals, with `absent_points` (0) for a Madison it didn't ride. Ties go to the most race wins, then the better place in the latest race (USAC 2B19(e)). A Team Omnium by Place (`team_omnium_places`) counts the same races and teams, but each Madison scores the team's place through `points_by_place` (default `[7, 5, 3, 2, 1]`), with `points_beyond_table` (0) past its end, and the same tie-break.

An Omnium by Place (`omnium_places`) counts every race in the ticked events whose format is not `madison`, except the left-out ones, with the same tables per group. A row is a rider (`race_entry.rider_id`, the same rider across events), shown under the bib they raced under last. Every rider who rode any counting race is in the table; a race not ridden adds nothing (`absent_points`, 0). The race scores the rider's place through `points_by_place` as above, with the same tie-break. A Four-Race Omnium (`four_race_omnium`) counts the `chase`, `tempo`, `elimination`, and `points` races of the ticked events, which must be exactly one of each per event and group or the standings is refused with no table. Its values are `uci_omnium_rules()` in `madtracker/scoring/rules.py`: 40 down to 2 by place for the first three, 1 past 20th, the Points Race's total summed raw (`sum_total_races` is set per table to the Points Race columns), `must_finish_all` so a rider out of any race is listed DNF after the ranked rows, and ties by the Points Race's final sprint. The stored `rules_json` is `{}` for it; the scorer sets nothing. A `standings_penalty` row (USAC 2O3(e), 40 points for two laps down) is taken off that rider's total before ranking, for this kind only.

A race still in `setup` with no live `race_action` rows is "not yet raced": it adds nothing and isn't a column. The standings is final only when every counting race is final and none is still to race. The code is `madtracker/control/multi_race.py`.

## Formats and rules_json

`race.format` names how the race is shown and exported. The engine that ranks it comes from `FORMAT_ENGINE` in `madtracker/scoring/replay.py`:

| Engine | Format keys |
|---|---|
| `placings` | `scratch`, `chase`, `unknown_distance`, `chariot`, `handicap`, `keirin`, `match_sprint`, `placings` |
| `sprint_points` | `points`, `madison`, `tempo`, `sprint_points` |
| `elimination` | `elimination` |
| `win_and_out` | `win_and_out` |

The race dialog offers the keys listed in `madtracker/control/formats.py`, which also holds each one's label and USAC article. `scratch`, `placings`, and `sprint_points` are engine-level keys the dialog doesn't offer. A miss-and-out is an `elimination` (USAC 2E5), and a Belgian win-and-out is a `win_and_out` with `direction` set to `reverse`.

`rules_json` is the `to_dict()` of the matching class in `madtracker/scoring/rules.py`, plus an `engine` key:

- `placings`: `laps_count_for_ranking`, `lapped_riders_placed_by_laps`.
- `sprint_points`: `sprint_count` (required: until it's set, every entry is refused), `intermediate_points`, `final_points` (the sprint numbered `sprint_count` awards these), `points_by_sprint` (null, or a table per sprint), `lap_gained_points`, `lap_lost_points`, `tie_break` (`final_sprint` or `none`), `scored_unit` (`rider` or `team`).
- `elimination`: `survivors`, `final_by_sprint`.
- `win_and_out`: `places`, `direction` (`forward` or `reverse`).

Beside the engine's values, `rules_json` may carry `format_name` and `format_description`, the ruleset's words for the format when the race was made; the engines ignore them. A fifth engine, `aggregate`, works across races and is never stored on one; a standings uses it. If `rules_json` has no `engine` key (the `'{}'` default, or a partial dict), the app fills it from the `rules_preset` ruleset (`rules_for_race` in `madtracker/control/race.py`); the Add Race / Edit Race dialog (Edit Event) always saves the full dict.

## Reproducing a result

Every screen, the scoreboard, the PDF, and the CSV replay the live rows through the engine each time. To do the same outside the app, run this from the repo root with the venv active (`python replay.py FILE RACE_ID`):

```python
import json, sqlite3, sys
from madtracker.scoring import compute_for_format, actions_from_rows
from madtracker.scoring.rules import rules_from_dict

db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
race_id = int(sys.argv[2])
fmt, rules_json = db.execute("SELECT format, rules_json FROM race WHERE race_id = ?", (race_id,)).fetchone()
entrants = [r[0] for r in db.execute(
    "SELECT re.rider_id FROM race_entry re JOIN race r USING (race_id) "
    "JOIN roster_entry me ON me.event_id = r.event_id AND me.rider_id = re.rider_id "
    "WHERE re.race_id = ? ORDER BY me.bib", (race_id,))]
rows = db.execute(
    "SELECT kind, schema_ver, payload_json FROM race_action e WHERE race_id = ? AND kind <> 'void' "
    "AND NOT EXISTS (SELECT 1 FROM race_action v WHERE v.kind = 'void' AND v.voids_action_id = e.action_id) "
    "ORDER BY action_id", (race_id,))
actions = actions_from_rows((k, v, json.loads(p)) for k, v, p in rows)
for row in compute_for_format(fmt, rules_from_dict(json.loads(rules_json)), entrants, actions).rows:
    print(row.rank, row.entrant_id, row.status, row.total_points)
```

That's an individual race with full `rules_json`. For a team race the entrants are `SELECT team_id FROM team WHERE race_id = ? ORDER BY seq, team_id`. Each `Standing` also carries `sprint_points`, `laps_gained`, `laps_lost`, `lap_points`, `final_sprint_place`, and `eliminated_at`: the work behind the total. `RULES_VERSION` is bumped whenever an engine's answer for an existing log could change, so to check an old race exactly, use the code whose `RULES_VERSION` matches `race.rules_version`.

## Schema versions

The schema lives in `madtracker/store/migrations.py` as a list keyed by `user_version`. Its first entry is the baseline: one step that creates every table, index, and trigger above, numbered 4. A new file is made by that one step. A later change to the schema is a new entry after it, and a file at an earlier version runs each later entry in one transaction with its version bump, so a file is at one version or the next, never between.

Every file in use is at version 4. A file numbered below 4 is refused rather than guessed at, and so is a file numbered above the app's own version.

That's it. One table really matters: if you can read `race_action` and replay it, you can rebuild every result the app ever showed.
