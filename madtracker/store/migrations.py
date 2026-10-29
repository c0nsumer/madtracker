"""The schema, keyed by PRAGMA user_version.

MIGRATIONS holds one entry per schema version: the baseline, which creates
the whole schema in one step, and after it one entry per later change.
open_database() runs every entry whose version is above the file's
user_version, each inside one transaction together with the version bump,
so a crash mid-step leaves the file at the previous version with nothing
half-applied. SQLite DDL is transactional, which is what makes this safe.

The baseline carries the version number of the schema it creates, so a
file at that version runs nothing, and a file numbered below it (one no
file in use is at) is refused (store.db) rather than guessed at, as a
file written by a newer app is. A later change is a new
(version, sql) pair appended after the baseline; the baseline and every
shipped entry are never edited.

Conventions in the schema:

- Optional identifiers and categories (license, UCI ID, USAC category,
  birth year, group) are NULL when unknown, because "unknown" and "empty"
  differ for a license number. Free text (notes, venue) is NOT NULL with
  an empty default, because absent and empty mean the same thing there.
- Timestamps are ISO 8601 text in UTC. They are for audit only; ordering
  never depends on them, since a laptop clock can be wrong or change.
- The rules a race was scored under are stored in full (rules_json) plus
  the ruleset name and the scoring code version. A later change to a
  preset or to the scoring code must never rewrite history; replaying an
  old race with its own rules object gives the same answer years later.
"""

BASELINE_SQL = """
CREATE TABLE rider (
    rider_id            INTEGER PRIMARY KEY,
    first_name          TEXT    NOT NULL,
    last_name           TEXT    NOT NULL,
    usac_license        TEXT,
    uci_id              TEXT,
    birth_year          INTEGER,
    notes               TEXT    NOT NULL DEFAULT '',
    created_utc         TEXT    NOT NULL,
    updated_utc         TEXT    NOT NULL
);
-- SQLite already treats NULLs as distinct under UNIQUE; the partial index
-- states the rule explicitly: one rider per license, foreign riders
-- without a USAC License are unconstrained.
CREATE UNIQUE INDEX rider_usac_license ON rider(usac_license) WHERE usac_license IS NOT NULL;
CREATE INDEX rider_by_name ON rider(last_name, first_name);

CREATE TABLE event (
    event_id    INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    event_date  TEXT NOT NULL,
    venue       TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    created_utc TEXT NOT NULL,
    -- The series an event belongs to (docs/design.md section 6), a name.
    series      TEXT NOT NULL DEFAULT ''
);

-- The bib belongs to the entry, not the rider: a venue may hand out new
-- bibs every event. It may be NULL until the venue assigns it (riders
-- are imported before bibs exist), and two riders who never share a race
-- may wear one number; the race field is where both are refused
-- (madtracker.control.roster). The group lives here and not on the
-- rider: a rider moves between groups as they age and upgrade, so the
-- group is a fact about one event (docs/design.md section 6).
CREATE TABLE roster_entry (
    event_id    INTEGER NOT NULL REFERENCES event(event_id),
    rider_id    INTEGER NOT NULL REFERENCES rider(rider_id),
    bib         INTEGER CHECK (bib IS NULL OR bib > 0),
    local_group TEXT,
    PRIMARY KEY (event_id, rider_id)
);

CREATE TABLE race (
    race_id         INTEGER PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES event(event_id),
    seq_in_event    INTEGER NOT NULL,
    name            TEXT    NOT NULL,
    format          TEXT    NOT NULL,
    group_label     TEXT    NOT NULL DEFAULT '',
    rules_preset    TEXT    NOT NULL DEFAULT '',
    rules_json      TEXT    NOT NULL DEFAULT '{}',
    rules_version   TEXT    NOT NULL DEFAULT '',
    usac_discipline TEXT,
    usac_category   TEXT,
    usac_gender     TEXT,
    usac_class      TEXT,
    usac_age_group  TEXT,
    state           TEXT    NOT NULL DEFAULT 'setup'
                    CHECK (state IN ('setup', 'running', 'provisional', 'final')),
    announced_utc   TEXT,
    notes           TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX race_by_event ON race(event_id, seq_in_event);

-- Who started. The bib resolves through roster_entry, so a race entrant
-- must be an event entrant; the triggers below keep that true even for a
-- caller that bypasses the Store class.
CREATE TABLE race_entry (
    race_id  INTEGER NOT NULL REFERENCES race(race_id),
    rider_id INTEGER NOT NULL REFERENCES rider(rider_id),
    PRIMARY KEY (race_id, rider_id)
);
CREATE TRIGGER race_entry_needs_roster_entry BEFORE INSERT ON race_entry
BEGIN
    SELECT RAISE(ABORT, 'race_entry: rider is not entered in the event')
    WHERE NOT EXISTS (
        SELECT 1 FROM roster_entry ro JOIN race r ON r.event_id = ro.event_id
        WHERE r.race_id = NEW.race_id AND ro.rider_id = NEW.rider_id
    );
END;
CREATE TRIGGER roster_entry_in_use BEFORE DELETE ON roster_entry
BEGIN
    SELECT RAISE(ABORT, 'roster_entry: rider is entered in a race of this event')
    WHERE EXISTS (
        SELECT 1 FROM race_entry re JOIN race r ON r.race_id = re.race_id
        WHERE r.event_id = OLD.event_id AND re.rider_id = OLD.rider_id
    );
END;

-- Teams are per race (madison pairs, team sprint). Names are the colors
-- the scorer types ("Yellow"), so they must be unique within a race.
CREATE TABLE team (
    team_id   INTEGER PRIMARY KEY,
    race_id   INTEGER NOT NULL REFERENCES race(race_id),
    name      TEXT    NOT NULL,
    color     TEXT    NOT NULL DEFAULT '',
    color_hex TEXT,
    seq       INTEGER NOT NULL,
    UNIQUE (race_id, name)
);
CREATE TABLE team_member (
    team_id  INTEGER NOT NULL REFERENCES team(team_id) ON DELETE CASCADE,
    rider_id INTEGER NOT NULL REFERENCES rider(rider_id),
    PRIMARY KEY (team_id, rider_id)
);
CREATE TRIGGER team_member_needs_race_entry BEFORE INSERT ON team_member
BEGIN
    SELECT RAISE(ABORT, 'team_member: rider is not entered in the race')
    WHERE NOT EXISTS (
        SELECT 1 FROM race_entry re JOIN team t ON t.race_id = re.race_id
        WHERE t.team_id = NEW.team_id AND re.rider_id = NEW.rider_id
    );
    SELECT RAISE(ABORT, 'team_member: rider is already on a team in this race')
    WHERE EXISTS (
        SELECT 1 FROM team_member tm
        JOIN team t1 ON t1.team_id = tm.team_id
        JOIN team t2 ON t2.race_id = t1.race_id
        WHERE t2.team_id = NEW.team_id AND tm.rider_id = NEW.rider_id
    );
END;

-- The scorer's actions. Append-only: standings are always derived by
-- replaying a race's actions, undo is a 'void' row pointing at the undone
-- action, and the triggers make UPDATE and DELETE fail inside the
-- database itself so no tool, not just this app, can edit history.
-- action_id orders actions; action_uuid identifies one across exports.
CREATE TABLE race_action (
    action_id       INTEGER PRIMARY KEY,
    action_uuid     TEXT    NOT NULL UNIQUE,
    race_id         INTEGER NOT NULL REFERENCES race(race_id),
    recorded_utc    TEXT    NOT NULL,
    kind            TEXT    NOT NULL,
    schema_ver      INTEGER NOT NULL CHECK (schema_ver >= 1),
    payload_json    TEXT    NOT NULL,
    voids_action_id INTEGER REFERENCES race_action(action_id),
    operator_note   TEXT,
    CHECK ((kind = 'void') = (voids_action_id IS NOT NULL))
);
CREATE INDEX race_action_by_race ON race_action(race_id, action_id);
-- A void names the row it voids, and the trigger and the store both ask
-- whether a row is voided already. Without an index that question scans
-- every action of every race ever scored in the file, so an Undo or a
-- correction slows with the venue's whole history. Partial: only void
-- rows carry a target, and the index holds nothing else.
CREATE INDEX race_action_by_void ON race_action(voids_action_id)
    WHERE voids_action_id IS NOT NULL;
CREATE TRIGGER race_action_no_update BEFORE UPDATE ON race_action
BEGIN
    SELECT RAISE(ABORT, 'race_action is append-only');
END;
CREATE TRIGGER race_action_no_delete BEFORE DELETE ON race_action
BEGIN
    SELECT RAISE(ABORT, 'race_action is append-only');
END;
-- A void targets a live, non-void action of the same race. Voiding a void
-- is not a redo here (redo re-appends the original action), which keeps
-- "live" a single lookup instead of a parity count.
CREATE TRIGGER race_action_void_target BEFORE INSERT ON race_action
WHEN NEW.kind = 'void'
BEGIN
    SELECT RAISE(ABORT, 'void target must be a live non-void action of the same race')
    WHERE NOT EXISTS (
        SELECT 1 FROM race_action t
        WHERE t.action_id = NEW.voids_action_id
          AND t.race_id = NEW.race_id
          AND t.kind <> 'void'
    )
    OR EXISTS (
        SELECT 1 FROM race_action v
        WHERE v.kind = 'void' AND v.voids_action_id = NEW.voids_action_id
    );
END;

-- When a race's result became provisional or final, and back again:
-- race.state holds only where a race is now, and
-- a disputed result needs its history. Kept apart from race_action so
-- it is never replayed and Undo never touches it; append-only for the
-- same reason that table is. after_action_id is the newest action in
-- the file when the change was made, which places it in the log
-- without trusting the clock.
CREATE TABLE race_state_change (
    change_id       INTEGER PRIMARY KEY,
    race_id         INTEGER NOT NULL REFERENCES race(race_id),
    from_state      TEXT    NOT NULL,
    to_state        TEXT    NOT NULL,
    recorded_utc    TEXT    NOT NULL,
    after_action_id INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX race_state_change_by_race ON race_state_change(race_id, change_id);
CREATE TRIGGER race_state_change_no_update BEFORE UPDATE ON race_state_change
BEGIN
    SELECT RAISE(ABORT, 'race_state_change is append-only');
END;
CREATE TRIGGER race_state_change_no_delete BEFORE DELETE ON race_state_change
BEGIN
    SELECT RAISE(ABORT, 'race_state_change is append-only');
END;

-- The venue's settings (name, logo bytes, backup folder, the live
-- race). JSON values so a setting can be a list or an object without a
-- schema change.
CREATE TABLE setting (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

-- Named rulesets the venue defines in the app. One JSON document per
-- row holding one page of values. A race copies the rules it is created
-- with into its own rules_json, so editing or deleting a ruleset never
-- touches a past race; the table is a library of starting points, not a
-- reference the race points at. Names compare without case so "House
-- Rules" and "house rules" cannot both exist and confuse the race dialog.
CREATE TABLE ruleset (
    ruleset_id  INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    json        TEXT    NOT NULL,
    created_utc TEXT    NOT NULL,
    updated_utc TEXT    NOT NULL
);

-- A multi-race standings is a stored definition, never stored numbers:
-- the result is replayed from the races it names every time, as a
-- race's result is. Events and left-out races are link tables rather
-- than a JSON list, so "which events" is a plain query, and a deleted
-- event or race leaves the definition through the cascade (foreign_keys
-- is on for every connection) instead of as a dangling id. rules_json
-- holds the kind's values; '{}' means the kind's own defaults, which the
-- control layer knows and the store does not. Names compare without
-- case, as a ruleset's do: the PDF is named from the name, and two
-- standings that read the same in the list would print to one file name.
CREATE TABLE standings (
    standings_id INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    kind         TEXT NOT NULL,
    rules_json   TEXT NOT NULL,
    created_utc  TEXT NOT NULL,
    updated_utc  TEXT NOT NULL
);
CREATE TABLE standings_event (
    standings_id INTEGER NOT NULL REFERENCES standings(standings_id) ON DELETE CASCADE,
    event_id     INTEGER NOT NULL REFERENCES event(event_id) ON DELETE CASCADE,
    PRIMARY KEY (standings_id, event_id)
);
CREATE TABLE standings_race_excluded (
    standings_id INTEGER NOT NULL REFERENCES standings(standings_id) ON DELETE CASCADE,
    race_id      INTEGER NOT NULL REFERENCES race(race_id) ON DELETE CASCADE,
    PRIMARY KEY (standings_id, race_id)
);

-- An omnium-level penalty on a rider in a standings (USAC 2O3(e): two
-- laps down in the Scratch Race or Tempo Race costs 40 omnium points). It
-- belongs to the standings, not to a race: a Points Penalty in a race
-- would change that race's own result. One number per rider, as a race's
-- penalty is; a penalty taken off is the row deleted.
CREATE TABLE standings_penalty (
    standings_id INTEGER NOT NULL REFERENCES standings(standings_id) ON DELETE CASCADE,
    rider_id     INTEGER NOT NULL REFERENCES rider(rider_id) ON DELETE CASCADE,
    points       INTEGER NOT NULL CHECK (points > 0),
    PRIMARY KEY (standings_id, rider_id)
);
"""

# The baseline creates the whole schema; a later change appends its own entry.
MIGRATIONS: list[tuple[int, str]] = [
    (4, BASELINE_SQL),
]

SCHEMA_VERSION = MIGRATIONS[-1][0]
FIRST_VERSION = MIGRATIONS[0][0]
