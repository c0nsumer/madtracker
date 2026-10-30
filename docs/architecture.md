# Architecture

The job looks small. One volunteer sits at a laptop with a mouse and a headset radio, and officials call placings to them by name or bib. The laptop drives a TV picture for the stands over HDMI. At the end of the night the results go to the awards ceremony, the archive, and USA Cycling. The catch is everything around it: the volunteer isn't a programmer, the laptop can lose power at any moment (a dead battery, a kicked cord, a forced Windows update), there's no network, and the results have to be right the first time.

So the design comes down to a few rules. Every entry is on disk before the screen says so. A result is always recomputed from what was entered, never stored as a number that could drift. The arithmetic lives in one place, pinned by tests that cite the rulebook. And the TV shows what the scorer's screen shows.

It stays at the level of layers and responsibilities rather than UI file names. `docs/design.md` is the authority for what the scorer sees; `docs/scoring-rules.md` covers the scoring rules themselves, and `docs/data-file.md` documents the SQLite file table by table for anyone reading it without the app.

## Layers

The code is Python 3.12 or newer, with PySide6 (Qt) for the windows, the standard library's `sqlite3` for storage, and fpdf2 (with uharfbuzz for text shaping) for the PDF. It's split into packages under `madtracker/`, each with one job and a short list of things it may import:

| Package | Responsibility | May depend on |
|---|---|---|
| `scoring` | Pure scoring engines: rules plus entries give standings. | Nothing else in the project; standard library only. |
| `store` | The SQLite file: schema, migrations, the append-only action log, backups. | Standard library only. It stores action payloads as JSON and doesn't know what they mean. |
| `control` | Ties store and scoring together: the race controller, rulesets, roster, backups policy, scoreboard feed, and multi-race standings (`multi_race.py`, which replays each counting race and sums them with the `aggregate` engine). | `scoring`, `store`, `board` payloads (plain data), `export`. No Qt. |
| `export` | The USAC CSV and the PDF results, from one shared row builder; the program and standings sheets share the results sheet's header. | `control`, `scoring`, `store`, fpdf2. |
| `importers` | BikeReg entry exports: parse, plan the import, then apply it. | `control`, `store`. |
| `board` | The audience scoreboard: a Qt canvas that draws payloads. | Its own payload types, Qt, and the shared font lookup. Never the store or scoring. |
| `ui` | The operator window, the setup screens, and the File menu's dialogs, among them the Multi-Race Standings dialog (`standings.py`). | Everything below it. |
| `help` | The scorer's help pages, plain Markdown shipped with the program and rendered by `ui`. | Nothing. |
| `assets` | Icons (Material Design Icons), the bundled Inter typeface, the license texts, the app's own wordmark. | Nothing. |

`madtracker/app.py` wires the windows, the displays, and the store together, and is meant to stay thin. Beside it sit a few small modules with one job each: `applog.py` (the program's log file), `dates.py` (dates as people read them, 2026-Oct-14), `displays.py` (which screen the board goes on, pure logic), `inputs.py` (typed text and numbers made safe to store), `keep_awake.py` (the displays never blank during a race), and `platform_name.py` (whether the packaged Mac app sets Qt's window icon). Qt appears only in `board`, `ui`, and `app.py`, which is why everything under them can be tested as plain Python.

The rule that matters most: `scoring` imports nothing from the project and `store` imports nothing from `scoring`, so each can be tested without the other.

## The action log

A race isn't stored as a result. It's stored as what the scorer entered (sprint results, finish orders, eliminations, laps, status marks), one row each in the `race_action` table with a `kind`, a `schema_ver`, and a JSON payload.

- **Append-only.** Triggers in the database refuse any `UPDATE` or `DELETE` on `race_action`, so no tool (not only this program) can edit history.
- **Undo is a void.** Undo takes back the newest action in one transaction: it appends a `void` row for each row that action wrote, and appends again any row it voided. A trigger checks that the target is a live, non-void row of the same race. A void can't itself be voided, and an undo is never itself undone, which keeps the log a straight line.
- **Corrections are new rows.** Moving a row in a result, or reopening a sprint, appends the corrected entry and voids the old one in the same transaction, so a power cut leaves both changes or neither. One scorer action's rows (the new rows, the voids of what they replace, and the staged order) always share one transaction.
- **Rulings are rows too.** A points penalty is stored as the difference from the penalty standing before it, so the Penalty figure is the sum of a rider's `points_adjusted` rows, and one Undo puts the earlier number back without touching the sprints recorded since. A lap the officials ruled did not count cancels the newest lap gained. A later status replaces an earlier one, so a DNF rider can be disqualified after a protest without undoing anything.
- **Replay.** `Store.live_actions(race_id)` returns the rows with voids and voided rows removed, in order, and the scoring engine replays them to get the standings. Every screen, the scoreboard, and both exports read standings that came from a replay. A partial index on `voids_action_id` keeps "is this row voided" a lookup as the file grows.
- **Validate first.** The race controller validates new entries against the log as it would stand, including every later entry after a correction, before the first write. A refused entry writes nothing and says why in one line. A correction is refused only for a contradiction it adds, never for one the log already held.

Why build it this way? Officials change calls minutes later, and an append-only log makes that a non-event: the correction is one more row, the old call stays in the record, and the result recomputes. A result can also be re-derived years later, because each race stores the full rules it was scored under plus the scoring code's `RULES_VERSION`, and an action payload newer than the code is refused rather than guessed at.

The SQLite settings are these:

- `journal_mode = WAL` with `synchronous = FULL` (SQLite documents this pair as ACID across power loss, with one sync per commit).
- `foreign_keys = ON` (off by default in SQLite).
- `busy_timeout = 5000` (a brief lock becomes a short wait, not an error).
- `application_id` set to 'MADT' (the file identifies itself, so opening some other program's database is refused).
- `user_version` holds the schema version, 4. The schema is one baseline entry that creates it in a single step, plus one entry per later change. Each entry runs in one transaction with its version bump, so a crash mid-step leaves the file at the old version. A file from a newer app is refused, and so is one numbered below the baseline (an automatic backup from before 2026-Oct-20). When a later entry exists, a file from an older build is upgraded when it opens, and one that sits on read-only media or that another program has open says it needs updating and how, instead of being called damaged.

Connections run in autocommit mode, and the store issues `BEGIN IMMEDIATE` and `COMMIT` itself, so every write is one short transaction. `append_action` returns only after the commit. On a clean close the store checkpoints the WAL into the main file, so the `.sqlite` file alone then holds everything.

The kill test (`tests/store/test_kill.py`) is the proof of the commit-before-acknowledge ordering. A helper process appends actions and prints each id only after the commit returns. The test reads a random number of ids, kills the helper outright (SIGKILL on Linux and macOS, TerminateProcess on Windows), reopens the file, and checks that every acknowledged event is there, the ids are contiguous, the integrity check passes and the file still takes writes.

What it doesn't prove: power loss. A killed process leaves the operating system's page cache intact, so the test exercises SQLite's crash recovery and the program's ordering, not whether the drive honored the sync. That part depends on the hardware: Windows' write-cache buffer flushing left on (its default), and the live file on the laptop's internal disk, never on a USB stick, as `docs/installing.md` says.

Beside this, a marker file created on open and removed on a clean close makes the next start after a crash say "The last session did not close cleanly." An integrity check runs on every open. A lock file beside the data file (`madtracker.sqlite.lock`) refuses a second copy of the app on the same file, since two copies would each score into it and the first to quit would remove the other's marker. A lock left by a crashed copy names a process that is gone, and the app checks that with the operating system before it takes the lock over, because Qt's own staleness rule differs by platform.

## Backups

A backup is a complete, self-contained copy of the database, made with SQLite's online backup API (never a file copy, because the `-wal` side file is part of the state). It's written to a `.partial` name beside the target, switched to a single file with no WAL, marked as a backup in its `setting` table, integrity-checked, and only then renamed into place. A copy cut short by a crash leaves its `.partial` behind, and the next backup to the automatic folder clears any it finds. The mark, not the name or the folder, is how the program knows a backup: opening one offers to restore a copy, and rotation deletes only marked files. Backups are taken when a race becomes provisional, when it's marked final, on a clean close, and on request. They go to a `backups` folder beside the data file (the newest 20 kept, plus the last of each of the last 10 dates) and, if the venue sets one, to a second folder such as a USB stick, where nothing is ever deleted. Restoring a backup over an existing data file first copies that file into its own `backups` folder as `madtracker-before-restore-<time>.sqlite`, and rotation never deletes those copies. The help's Backups page (`madtracker/help/backups.md`) has the restore steps.

## The scoring engines

The engines in `madtracker/scoring/` are pure functions. `compute_for_format(format_key, rules, entrants, actions)` returns a `Standings` value, and `validate_for_format(...)` returns the list of problems with a new entry. There's no Qt, no SQLite, and no I/O, and nothing is mutated: events and rules are frozen dataclasses.

There are five engines: `placings` (the Scratch Race and everything ranked at the line), `elimination`, `sprint_points` (Points Race, Madison, Tempo Race), `win_and_out`, and `aggregate` (a standings table over several races). Rules are one dataclass per engine, filled from the built-in USAC 2025 ruleset or a venue's stored copy of it.

Each rule in the engines cites its article in a comment or docstring (USAC 2M2(f)(i), UCI 3.2.118 and so on) and has a test named for what it pins, such as `test_sprint_tie_shares_place_and_skips_next` or `test_dnf_rider_counts_as_eliminated_at_the_next_sprint`. The golden tests in `tests/scoring/test_golden_night98.py` reproduce real results sheets from a venue's workbook, by bib and team color only, with the venue's house values spelled out in the test. The project rule is that a scoring rule changes only together with its test. When an engine's answer for an existing log could change, `RULES_VERSION` is bumped.

Standings rows carry the work behind each total (per-sprint points, laps, final-sprint place), so a second person can check the program against the officials' sheet.

## The scoreboard

The scoreboard is a canvas, `BoardCanvas` in `madtracker/board/`, and it only draws what it's handed. The control layer turns standings into payloads: plain dataclasses for each layout (logo, start list, elimination, standings, result, next race). The board never reads the store or runs scoring, so it can be driven from sample data in tests and in mockups.

- The canvas is designed on a 1080-line grid, and every size scales with the window's height, so it reads the same on any TV.
- The same canvas class runs twice: full screen on the TV's display, and as the preview in the operator window. That's how "the scoreboard shows what the scorer sees" (design principle 6) is enforced, rather than hoped for.
- The app picks the board's display and follows hot-plugs.
- A rider with a status (DNF, DNS, DQ, DNP) is left off every audience layout without comment, with one exception: an Elimination DNF keeps a place (USAC 2E4), so the result page lists them there, with nothing beside the name. The elimination page leaves them off. A DNF may be an injury and a DQ a protest still being argued, and neither is the TV's to announce. The operator's copy keeps the row and its code.

## Exports

The PDF and the USAC CSV are built from one shared row builder, `madtracker/export/summary.py`. Both read place, names, license, and status from the same rows, so the printed sheet and the uploaded file can't disagree. Every export (the results PDF, the program PDF, the multi-race standings PDF, and the CSV) goes through `madtracker/export/files.py`: it is written to a `.partial` name beside the earlier file and swapped in with one rename once complete, so a write that fails partway (a full or pulled USB stick) leaves last week's file whole and no half-written file behind. A status wins over a rank in both, so a DNF prints as DNF, with one exception: a rider an Elimination placed after leaving the race (out at that moment, USAC 2E4) prints the place with "Did not finish" beside the name on the sheet. The USAC CSV carries the place alone. The board's result page lists the place with nothing beside it, and the elimination page leaves the rider off.

- **USAC CSV.** The one layout is USAC's 2024 ten-column template, with its exact headers and no bib column (`docs/research/usac-results-export.md`). USAC publishes no schema, so the template is the requirement. The header row, column order, line endings, and place words were compared with the template character for character. Race discipline is the format's code on USAC's results site: SR, ER, and MAD went through a real upload (a venue's two-day file), and PR, TMPR, SPR, and KEIR are unverified, so a race's stored discipline override wins. The file is UTF-8 with no byte order mark and CRLF line endings, one row per rider per race, and a Madison writes one row per rider carrying the team's place. It must never be re-saved from Excel, which turns values such as "9-14" or a license with leading zeros into dates and numbers.
- **PDF/A-2B.** The archival results sheet is PDF/A-2B, which forbids the PDF core fonts, so a TrueType font has to be embedded. The sheet embeds the bundled Inter Regular, Bold, and Black (`madtracker/assets/fonts/`, SIL Open Font License), the same face the window and the scoreboard draw with, so the sheet is identical on every machine. uharfbuzz shapes the PDF text with Inter's tabular figures, so the digits in the place and points columns line up. If the bundled files are missing (a packaging bug, not a machine difference) the PDF is still written with core Helvetica, which isn't PDF/A. A sheet that prints beats no sheet.

## Platforms

Windows, macOS, and Linux run the same code, and CI runs the full test suite on all three with Python 3.12. Linux is where the program is developed and tested headless; Windows laptops are the most likely target at a venue.

- **Look.** The operator window uses Qt's Fusion style with an explicit light palette, so the operating system's theme (dark mode, for one) can't change what the scorer sees. The scoreboard is always dark.
- **Fonts.** One typeface is bundled, Inter, and registered with Qt at startup, so the window, the scoreboard and the PDF have identical metrics on every platform and a layout checked on Linux is the layout the scorer sees. The scoreboard and the PDF both ask for Inter's tabular figures (Qt directly, the PDF through uharfbuzz), so numbers line up in columns. Nothing is looked up on the machine.
- **Data location.** The data file lives in the per-user data folder (`%LOCALAPPDATA%\MadTracker`, `~/Library/Application Support/MadTracker`, or `~/.local/share/madtracker`), never next to the program or in Documents, where a sync client might grab a live database. The demo data file (Help > Demo Data File...) is built fresh as `demo/demo.sqlite` under that folder, opened for the session only, and never remembered, so the next start returns to the venue's file.
- **Window placement.** The scoring window opens maximized the first time and afterwards where it was last quit; the place is kept in QSettings on the machine, never in the data file, and a place on a display no longer connected falls back to maximized.
- **Packaging.** PyInstaller builds a one-folder bundle on each platform from one spec (one folder starts faster than one file, and keeps the Qt libraries replaceable for the LGPL). Windows gets an Inno Setup per-user installer plus a portable zip, macOS a `.app` in a DMG and a zip (arm64, unsigned unless signing secrets are set), and Linux an x86_64 tarball. A `v*` tag builds all three in GitHub Actions and attaches them to a release. As of this writing (2026-Oct-19), the Linux package has been built and self-tested. The Windows installer and portable zip have been built and tested on real hardware. The macOS app has been built on a Mac and passed its self-test, but the DMG hasn't been opened yet. Two platform quirks are worth knowing: the Windows exe sets no AppUserModelID, because an explicit one without a matching shortcut drew a blank taskbar icon on Windows 11; and the packaged Mac app does not set Qt's window icon, which replaced the bundle's own icon in the Dock. The Mac icon comes in Apple's Icon Composer format when Xcode 26 is on the build Mac, else as an `.icns` packed by `iconutil` (`docs/building.md`).

## The test suite

Tests are pytest, run headless (`QT_QPA_PLATFORM=offscreen`), offline, on all three platforms. They need no display, no network, and no fixture files with real rider data; every name in the tests is invented.

As of this writing there are about 1350 tests, and the whole suite runs in about two minutes on this Linux box. The non-UI tests (scoring, store, control, export, importers, and the package checks) are about 760 of them; the Qt tests are about 590. The input fuzzer's deep tier (`pytest -m fuzz`, minutes) is left out of the everyday run and is run before a version is tagged. Run the suite with its output to a file, not through a pipe: a dialog raised during teardown would otherwise hang the run silently.

The acceptance test is `tests/ui/test_design_walk.py`, the walk through every screen that `docs/design.md` section 13 asks for:

- **The table per format.** `WALK` is the design written as data: for each format (Scratch Race, Elimination, Points Race, Madison, Win-and-Out, and the Handicap and the Unknown Distance, which walk the Scratch Race's steps), the steps a night takes and what the window must show after each. That's the state word, the task line, the buttons, the cards, the menus on a card and on a result row, the board page, and the Undo label. The walk runs a demo event through every step and asserts exactly that.
- **The sweep.** In every state of every format, a second test clicks every visible control and opens every menu. Each click must change what the scorer sees, open a menu or a dialog, or say in one line why it didn't (design principle 3, "nothing is silent"). A silent control fails the test.
- **The other screens.** Edit Event, Settings, Rulesets, Multi-Race Standings, and New Event are checked for their labels and their button order, with the primary action rightmost.
- **The differential run.** A second, naive scorer (`tests/scoring/test_differential.py`), written from the rulebook articles and not from the engine code, adds up thousands of seeded random races per format the way a person does on paper, and every rank, status, total, and lap count must match the engine's.

Lint is ruff (`ruff check` and `ruff format --check`). Both the tests and lint must pass before a commit.

## Adding a format

Does a venue's own format (the Win-and-Out is one) fit this shape? It does, and the Win-and-Out shows both halves of the answer: its engine (`madtracker/scoring/win_and_out.py`) took one pure function and its tests, and its surface in `madtracker/control/race.py` (what a click means at each bell, the task line, how a wrong lap winner is corrected) and its rows in the design walk were the larger part of the work, which is where the cost of any new format sits. The touch points, in order:

- **Scoring.** A variant of an existing shape (another points table, laps counted differently, a snowball) is a rules change only. A new shape is one engine in `madtracker/scoring/`: a pure `compute` and `validate`, a rules dataclass, a format key in `FORMAT_ENGINE`, rows in the register in `docs/scoring-rules.md` with the article or the club source, and the named tests that pin them (the register test fails until they exist).
- **The action log.** The entry kinds (sprint places, finish order, laps, eliminations, statuses) cover every bunch race. A format that needs a new kind of entry (times, for a pursuit) adds one action kind with its own schema version; old rows never change.
- **The surface.** What a click means for that format, the task line, the rider menu, and when the race is complete, in `madtracker/control/race.py` and the design walk. This is the part that takes the time.
- **The scoreboard.** A page, or the standings and result pages as they are.
- **Exports.** The shared row builder already carries rank, points, laps, and status, so most formats need nothing there.

The limit: a format whose result isn't a ranking of entrants with points and laps (a sprint tournament with brackets, say) doesn't fit the row shape and needs more than this list. Everything the venue runs tonight fits.

## Known limits and deferred work

These are known and left for later on purpose:

- **Timed events.** Time trials, pursuits, team sprint, and team pursuit are scored by entered times in a later version. The data model already allows them (a team can have more than two riders), but no engine scores them.
- **Tournaments.** Keirin Finals and Sprint Finals are scored as single heats. Brackets and qualifying rounds are not.
- **The four-race omnium** isn't a race format. Multi-Race Standings offers it as the Four-Race Omnium kind over an event's four races. Its two-laps-down deduction (USAC 2O3(e)) is an Omnium Penalty on the standings, never a Points Penalty on the Points Race (see `docs/scoring-rules.md` R-OMNI-5).
- **Multi-race standings on the board.** A multi-race standings (the Team Omnium or a rider omnium) over several events prints as a PDF (`madtracker/control/multi_race.py`, `madtracker/export/standings_pdf.py`); there is no scoreboard page for it and no CSV, since USAC takes race results, not standings.
- **The stream feed.** The video team can capture the scoreboard window, but there's no data feed for a streaming PC. That waits on what their software can take; a chroma-keyed overlay window has been researched and not built.
- **Two laptops on one file.** A lock file refuses a second copy of the app on the same file on one machine. Two machines on one shared file are not refused and not supported; the design discourages it.
- **Rule enforcement** (warnings, gear limits, eligibility) is out of scope by design, not deferred.

That's the shape of it: an append-only log on a durable SQLite file, pure engines that replay it, and two windows and two exports that all read the same replay. Much of the code was written with AI assistance (Claude Code), to the maintainer's design and review. For now, at least, it holds together well.
