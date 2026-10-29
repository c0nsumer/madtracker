# Results

Beyond the scoreboard and on-screen display, MadTracker writes two primary results files: a results PDF and the USA Cycling-compatible CSV. Each is written on demand, from the **File** menu.

A multi-race standings over several nights has a [PDF Export](multi-race-standings.md#pdf-export) of its own, on the Multi-Race Standings page. The program sheet, for posting before the racing, is on [The races](getting-started.md#the-races).

## The PDF

**File** → **Export Results PDF...** writes a results sheet, either for the **Whole event** or **Race** and a race chosen from the list. The list holds every race that has started and defaults to the currently selected one. It then asks where to save, in Documents or the **Exports folder** from [Settings](getting-started.md#settings), under a name made from the date and the event, eg: "2026-10-10 - Race Night 12 - Results - Overall.pdf".

The sheet has the event's name and date, the venue's name or logo from Settings, and then each scored race:

- The race's number in the program, its name, and its group, with a tag at the right: FINAL once the race is marked final, PROVISIONAL when complete but not finalized, and IN PROGRESS if the export is run while it's still being scored.
- A gray line of text with the format, the [ruleset](scoring.md#rulesets), the values the race was scored with, and the time the result first became PROVISIONAL. A race the officials ended early or shortened says so there too, eg: "Race ended after 2 sprints" or "race shortened from 4 to 3 sprints" (see [Points Race](scoring.md#points-race-usac-2m)).
- The placings in order, with the first three larger: place, bib, name, then for a Points Race, Madison, or Tempo Race each sprint's points under S1, S2, and so on, net laps where there are any, and the total. A Penalty column appears between Laps and Total only when a points penalty was recorded in that race; it shows the points taken, eg: "−5", and the total already has them off. A lap the officials ruled not to count shows "Lap not counted" beside the rider's name, a rider the officials pulled and placed shows "Withdrawn", and a rider a mishap kept out of a points race's finish shows "Out of the finish (mishap)" (see [Rules shared by every format](scoring.md#rules-shared-by-every-format)).
- Riders with a status after the placings, with DNS, DNF, or DQ.

A sprint in which a rider scored nothing is blank. The last sprint's figures include the doubling where the race doubles them, so the sprint columns, the laps at the lap value on the gray line, and any penalty add up to the total. A race with more sprints than fit across the page has one Sprints column with the sum instead.

On the results sheet, a finish-order race with eight or more placed riders prints in two columns, so read down the left column and then the right.

The results and standings sheets are landscape; the program sheet is portrait.

## The USAC CSV

**File** → **Export USAC CSV...** writes the night's results in the comma-separated value (CSV) format USA Cycling's results upload website accepts. Do this once, at the end of the night, after every race is final.

The file has the ten columns of the USAC results template:

- Race Date
- Race Discipline
- Race Category
- Race Gender
- Race Class
- Race Age Group
- Rider License
- Rider First Name
- Rider Last Name
- Rider Place

The discipline comes from the race's format. Category, Gender, Class, and Age Group come from the race's **Category**, **Gender**, **Class**, and **Age group** in Add Race (see [The races](getting-started.md#the-races)). A rider with a status gets DNS, DNF, or DQ as the place; a withdrawn rider has a place, and gets it. Both riders of a Madison team get the team's place.

After writing the CSV file the program shows details about the export, including each race written, and names any race that isn't finished (because those are left out). **Copy Details to Clipboard** copies that message to the clipboard as text, and the window stays open; the button then reads **Copied to Clipboard**. The list of races can be pasted into a spreadsheet as a table.

**Note**: USAC's template has no column for a race's name. Two races with the same discipline, Category, Gender, Class, and Age group may look like one race to USAC, so the message names them under "Things to check before uploading". To keep them apart, edit one of the races, change its Category, Class, or Age group, and export again.

**Caution**: Upload the CSV as it is. Be careful if you open and save it in Excel first: Excel turns age groups that look like dates into dates, eg: the junior age group 10-12 becomes "12-Oct" and 9-14 becomes "14-Sep", and USAC then gets the wrong age group.
