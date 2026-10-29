# Changelog

What changed in each build, in the scorer's words. Newest first. Each
entry names the version shown in About.

## 1.1.0 (not yet released)

- The cards stay put. A rider placed, clicked out, or marked keeps their card in the same spot, grayed, with the place in blue or the status (DNF, DNS, DQ, Withdrawn, Mishap) on it, until the result is complete. The other cards no longer shift when one is done, so a rider is where the scorer last saw them. A click on a grayed card records nothing and says why, and its ⋯ menu is the rider's row's.

## 1.0.0 (2026-Oct-28)

The first public release. MadTracker scores track cycling races, shows the results on a scoreboard for the crowd, and exports PDF results and the USA Cycling results CSV.

- Formats: every mass-start format in the Track Racing chapter of the USA Cycling Rulebook, version 8•25: Scratch Race, Handicap, Elimination, Sprint Final, Keirin Final, Points Race, Madison, and Tempo Race. Also three club formats: Unknown Distance, Chariot, and Win-and-Out.
- Scoring: the scorer clicks riders as the officials call each placing, sprint, elimination, and lap. Ties, Did Not Start, Did Not Finish, Disqualify, Withdrawn, Out of the Finish (Mishap), Points Penalty, Lap Not Counted, End Race Now, and Shorten Race are each a menu item, a recorded sprint is corrected by reopening it, and anything can be undone.
- Scoreboard: a full-screen board on a second display, switched between the logo and the race from the preview in the scoring window. Its rows and type grow to fill the screen for optimal readability.
- Multi-Race Standings: Team Omnium by points or by place, Omnium by Place, and the Four-Race Omnium, across races and events.
- Riders: imported from BikeReg or a similarly formatted spreadsheet, kept in one data file per venue with automatic backups.
- Exports: the event's program and results as PDF/A sheets that print as they look, and the CSV acceptable for submission to USA Cycling's results website.
- Runs offline on Windows, macOS (Apple silicon), and Linux.
