# Changelog

What changed in each build, in the scorer's words. Newest first. Each
entry names the version shown in About.

## Unreleased

- Removed the ruleset option **Lapped riders are placed by laps down**. A lapped Scratch Race rider who stays in is now always placed by laps down (USAC 2C4). This behavior is the same as the previous default of the box being checked. This is a breaking change. It will change the result of any past race where 1) this option had been set to off (from its default) and 2) a rider was automatically marked DNF in a Scratch Race after going a lap down.
- A withdrawn rider or team is taken off the scoreboard while the race runs (so it only shows who is still racing). The rider or team is shown again, placed, once the race is completed.
- The result list in the scoring window more clearly says why a placed rider is not a plain finish (eg: "Withdrawn", "Did not finish", etc.). Previously this detail was hidden in a tooltip.
- Fixed the results PDF leaving off "Withdrawn" and "Out of the finish (mishap)" for a Madison team, and for a rider with a long name.
- The Scoring help says what to mark when the officials remove a lapped rider, and the help pages cite USAC articles only.
- The macOS build requires macOS 14 (Sonoma) or newer. The version of Qt the program is built with does not run on older systems.
- The Linux build requires glibc 2.39 or newer (eg: Ubuntu 24.04, Debian 13, Fedora 40).
- Fixed a results PDF exported while a race is still running listing the riders still racing as "DNP". They are now listed with no place until the race has a result.
- Renamed **End Race Now, Result As-Is...** to **End Race Early, Result As-Is...**. Its question now says how many sprints are recorded out of the race's count, and that the results are calculated from only those.
- The questions for **Did Not Finish**, **Withdrawn**, and **Disqualify** now say what each does to the rider's place.
- A withdrawn rider or team can be disqualified while the race is still running, from the ⋯ on the card or the row.
- The rider's ⋯ menu has separators: the ways out of the race are grouped together, and **Disqualify** is set apart.
- A Sprint Final and a Keirin Final no longer offer a tie. A dead heat there is rerun (USAC 2F12, 2H2), and the scorer enters the order after the rerun.
- In the ruleset editor, **Scratch Race and Others** is now the last tab.
- The Scoring help for the Win-and-Out no longer describes a dead heat on a bell lap or a lap winner marked Did Not Finish, which the scoring window does not offer.

## 1.1.5 (2026-Oct-30)

- Changed how the cards work when clicked in races such as the Elimination. Instead of being removed and rearranged to show the remaining riders, they now stay in the same position, grayed out, and show the placing (or the status, such as DNF) of a rider who is out. This is to ensure the scorer doesn't have to re-find the location of a bib or rider name with each position entry.
- Also added more "Out Earlier" results to the Elimination scoreboard.
- Fixed a tie in Multi-Race Standings for a Four-Race Omnium over two events when the second event's Points Race is left out (USAC 2O4). Riders with equal points totals were split by the last Elimination's final (wrong) instead of the Points Race's final sprint (2O3(g)) (correct). The first event's Points Race now decides the tie.
- Fixed the Four-Race Omnium's standings leaving off a rider who was on a field but never started any of its races. USAC 2O2(c) places such a rider last as DNF, so the standings now list them after every finisher, as they already did for a rider who started one race and missed another.
- A BikeReg file with a stray byte in a name now imports that letter as "?", as the import preview says, rather than as a replacement-character glyph.
- Cleanup with no change for the scorer: unused code, parameters, an icon file, and a style rule removed; comments brought up to date; the About box no longer credits PyObjC, which the installed program never used.

## 1.0.0 (2026-Oct-28)

The first public release. MadTracker scores track cycling races, shows the results on a scoreboard for the crowd, and exports PDF results and the USA Cycling results CSV.

- Formats: every mass-start format in the Track Racing chapter of the USA Cycling Rulebook, version 8•25: Scratch Race, Handicap, Elimination, Sprint Final, Keirin Final, Points Race, Madison, and Tempo Race. Also three club formats: Unknown Distance, Chariot, and Win-and-Out.
- Scoring: the scorer clicks riders as the officials call each placing, sprint, elimination, and lap. Ties, Did Not Start, Did Not Finish, Disqualify, Withdrawn, Out of the Finish (Mishap), Points Penalty, Lap Not Counted, End Race Now, and Shorten Race are each a menu item, a recorded sprint is corrected by reopening it, and anything can be undone.
- Scoreboard: a full-screen board on a second display, switched between the logo and the race from the preview in the scoring window. Its rows and type grow to fill the screen for optimal readability.
- Multi-Race Standings: Team Omnium by points or by place, Omnium by Place, and the Four-Race Omnium, across races and events.
- Riders: imported from BikeReg or a similarly formatted spreadsheet, kept in one data file per venue with automatic backups.
- Exports: the event's program and results as PDF/A sheets that print as they look, and the CSV acceptable for submission to USA Cycling's results website.
- Runs offline on Windows, macOS (Apple silicon), and Linux.
