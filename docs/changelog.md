# Changelog

What changed in each build, in the scorer's words. Newest first. Each
entry names the version shown in About.

## 1.1.4 (2026-Oct-30)

- Fixed the ⋯ menu on a placed rider's card in races where laps matter, such as a Scratch Race or Handicap. Since 1.1.0 card-hiding changes it was missing Gained a Lap and Lost a Lap, so a lap for a rider already placed could only be entered from the result row. The card's menu now has the same items as the row's menu.
- Fixed a tie in Multi-Race Standings for a Four-Race Omnium over two events when the second event's Points Race is left out (USAC 2O4). Riders with equal points totals were split by the last Elimination's final (wrong) instead of the Points Race's final sprint (2O3(g)) (correct). The first event's Points Race now decides the tie.
- Fixed the Four-Race Omnium's standings leaving off a rider who was on a field but never started any of its races. USAC 2O2(c) places such a rider last as DNF, so the standings now list them after every finisher, as they already did for a rider who started one race and missed another.

## 1.1.0 (2026-Oct-29)

- Changed how the cards work when clicked in races such as the Elimination. Instead of being removed and rearranged to show the remaining riders, they now stay in the same position, grayed out, and show the placing (or the status, such as DNF) of a rider who is out. This is to ensure the scorer doesn't have to re-find the location of a bib or rider name with each position entry.
- Also added more "Out Earlier" results to the Elimination scoreboard.

## 1.0.0 (2026-Oct-28)

The first public release. MadTracker scores track cycling races, shows the results on a scoreboard for the crowd, and exports PDF results and the USA Cycling results CSV.

- Formats: every mass-start format in the Track Racing chapter of the USA Cycling Rulebook, version 8•25: Scratch Race, Handicap, Elimination, Sprint Final, Keirin Final, Points Race, Madison, and Tempo Race. Also three club formats: Unknown Distance, Chariot, and Win-and-Out.
- Scoring: the scorer clicks riders as the officials call each placing, sprint, elimination, and lap. Ties, Did Not Start, Did Not Finish, Disqualify, Withdrawn, Out of the Finish (Mishap), Points Penalty, Lap Not Counted, End Race Now, and Shorten Race are each a menu item, a recorded sprint is corrected by reopening it, and anything can be undone.
- Scoreboard: a full-screen board on a second display, switched between the logo and the race from the preview in the scoring window. Its rows and type grow to fill the screen for optimal readability.
- Multi-Race Standings: Team Omnium by points or by place, Omnium by Place, and the Four-Race Omnium, across races and events.
- Riders: imported from BikeReg or a similarly formatted spreadsheet, kept in one data file per venue with automatic backups.
- Exports: the event's program and results as PDF/A sheets that print as they look, and the CSV acceptable for submission to USA Cycling's results website.
- Runs offline on Windows, macOS (Apple silicon), and Linux.
