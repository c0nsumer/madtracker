# USAC results export format

Status: research findings, ready for review.
Date: 2026-10-07.

This document pins down the file the app must produce so a race director can upload results to USA Cycling (USAC).
It also covers the rider data the app must collect to produce that file.
Claims that this research did not confirm against a primary source are marked "UNVERIFIED:".
All URLs were accessed on 2026-10-07.

## Confidence

What was actually seen:

- **The official USAC template file.** USAC attaches a sample file named `2024 Results template.csv` to its help article "How to upload results to an event sanction". A copy of the file is in `local/scorer-files/` (added 2026-Oct-19). The export's header row, column order, CRLF line endings, and DNF, DNS, DQ, and DNP place words were compared with it character for character: they match.
  The article was last updated 2025-10-23.
  The article says: "Please note when submitting results it's the same file format from before, .CSV files only. As far as formatting is concerned an example is attached to this article."
  This research downloaded and read that file byte for byte.
  Article: <https://usacyclinghelp.zendesk.com/hc/en-us/articles/42343840919195-How-to-upload-results-to-an-event-sanction>
  File: <https://usacyclinghelp.zendesk.com/hc/article_attachments/42516975392411>
- **The upload steps in the USAC Member Portal.** Two USAC help articles describe the click path (see "How results reach USAC").
- **Real facility uploads as USAC publishes them.** USAC's public results site (Sport80) shows one facility's track events from 2026.
  This research read the published race titles, places, license numbers, and gender filters through the site's public data endpoints.
  Event example: <https://usacycling.sport80.com/pub/results/events/30881/d/pr/2026-02-28>
- **The USAC discipline code list.** The public results page lists every discipline with a short code.
  Source: <https://usacycling.sport80.com/pub/results>
- **CrossMgr source code.** CrossMgr is an open-source race timing program with a "USAC Excel Publish" export.
  This research cloned <https://github.com/esitarski/CrossMgr> at commit `5827aeb` (2026-09-20) and read `USACExport.py` and `helptxt/Menu-Publish.md`.
- **The track upgrade points chart** in USAC Policy VIII (revised 2026-07-07).

What is inferred, not seen:

- USAC publishes no written specification of the columns.
  The template is a sample file, not a schema.
  Its rows mix example values from many disciplines, so the allowed values below are read from the sample, not from a published list.
- No document says whether track discipline codes (`PR`, `SR`, and so on) are accepted in the "Race discipline" column.
  The template only shows road and mountain bike codes.
  One facility's published results show "Points Race" and "Scratch Race", so some track value was accepted.
  The exact spelling that facility used in its CSV is not visible from the public site.
- This research could not log in to the Member Portal.
  So the upload screen's own validation messages, and any column mapping step, are unknown.

## How results reach USAC

1. The event is sanctioned (permitted) in the USAC Member Portal before race day.
   Each sanctioned event has a numeric event ID.
   For example, one 2026 race night is event 30881 on the public results site.
2. After race day, the event moves to "post event" status.
3. An event admin uploads the results file.
   USAC's steps are: "Enter your event that is in post event status. Click on Event Info. Click on Results Submission. Click on Upload results. Click on Select file and then upload in the bottom right."
   Source: <https://usacyclinghelp.zendesk.com/hc/en-us/articles/42109985145115-How-to-upload-event-results-in-USA-Cycling-Member-Portal> (updated 2026-04-21).
4. The Chief Referee files a separate post-event report in the portal.
   That report has event summary fields and SafeSport fields.
   It is not part of the results file.
   Source: <https://usacyclinghelp.zendesk.com/hc/en-us/articles/42111663331739>
5. USAC asks organizers to post results within about a week.
   Source: <https://usacyclinghelp.zendesk.com/hc/en-us/articles/16373703477531>

What ties the file to the permit:

- The file has no event ID or permit number column.
- The upload happens inside one event's page in the portal.
  So the portal, not the file, ties results to the permit.
- The file also has no race ID column.
  USAC creates its own race IDs on import (for example race 653615).
  UNVERIFIED: USAC appears to split the file into races by the combination of date, discipline, category, gender, class, and age group.
  The published race titles look like those fields joined together (see "What a facility's uploads look like").
- A multi-day event (such as a season-long weekly series permit) can hold many race dates.
  The "Race Date" column tells USAC which day each race belongs to.

## The column list (official template)

The file is CSV.
USAC says ".CSV files only".
The template has one header row and uses CRLF line endings.

Columns, in template order, with the exact header text:

| # | Header (exact) | Meaning | Values seen in the template |
|---|---|---|---|
| 1 | `Race Date` | Date of the race. | `7/4/2024` (M/D/YYYY, no leading zeros). |
| 2 | `Race discipline` | Discipline code. Note the lowercase "d". | `RR`, `CRIT`, `TT`, `XC`, `STXC`, `XCM`, `STR`, `DH`, `DS`, `CCR`, `Circuit Race`. |
| 3 | `Race Category` | Ability category of the field. | `Cat 1/2`, `Cat 4`, `Cat 1/2/3/4/5`, `Open`, `Cat 3/4`. |
| 4 | `Race Gender` | Gender of the field. | `Men`, `Women`, `Both`, `Mixed`, `Male`, `Female`, `M`, `W`, `A`, `B`. |
| 5 | `Race Class` | Class of the field (age class or special class). | `Master`, `Junior`, `Senior`, `Single Speed`, `A`, `B`, `Collegiate`. |
| 6 | `Race Age Group` | Age range of the field. | `35+`, `U18`, `35-44`. |
| 7 | `Rider License` | Rider's USAC license number. | `123456`. Blank is allowed in the sample. |
| 8 | `Rider First Name` | Rider's first name. | `John`, `Jane`. |
| 9 | `Rider Last Name` | Rider's last name. | `Doe`. |
| 10 | `Rider Place` | Finishing place or status code. | `1`, `2`, `DNP`, `DNS`, `DNF`, `DQ`. |

Notes on the template:

- Only the first data row is a complete example.
  The other rows list sample values for one column at a time.
- The template contains stray trailing spaces (`TT `, `Senior `, `Jane `).
  These look like typing slips, not rules.
  The app should trim all values.
- The "A" and "B" values in the gender column are unexplained.
  UNVERIFIED: they may be misplaced class values.
- Discipline codes on the public results site match the template codes.
  The public site lists these track codes: `pr` (Points Race), `sr` (Scratch Race), `ip` (Individual Pursuit), `ttt` (Track Time Trial), `spr` (Sprint), `keir` (Keirin), `tp` (Team Pursuit), `tspr` (Team Sprint), `er` (Elimination Race), `omn` (Omnium), `mad` (Madison), `tmpr` (Tempo Race).
  UNVERIFIED: the upload accepts these codes in uppercase (`PR`, `SR`, `ER`, `MAD`, and so on) in the "Race discipline" column.
  The template's own codes are uppercase.
- The template code `STR` does not appear in the public site's discipline list.
  Its meaning is unknown.

### Extra columns USAC appears to accept

USAC's public results pages show these columns for each race: Place, Points, Name, City/State, Time, USAC #, BIB, Team.

- **BIB.** One facility's published results show bib numbers.
  The template has no bib column.
  So that facility's uploads included an extra bib column, and USAC imported it.
  UNVERIFIED: the exact header text USAC matches for bib.
  CrossMgr uses `Rider Bib #`.
- **Team.** Shown on the site, empty in one facility's uploads.
  CrossMgr uses `Rider Team`.
  UNVERIFIED: header text.
- **Time.** Shown on the site, mostly empty for track races.
  CrossMgr uses `Rider Time`, formatted `H:MM:SS`, blank for non-finishers.
- **Points.** This is USAC's ranking points, which USAC computes.
  The app must not export it.
  A rider with a lower number is ranked higher.
- **City, State.** USAC fills this from its own member record.
  The app does not export it.

## The CrossMgr export (older generation)

CrossMgr writes an `.xls` file, not CSV.
Its header row, from `USACExport.py`:

```
Race Date, Race Gender, Race Discipline, Race Category, Rider Bib #, Rider Last Name, Rider First Name, Rider Team, Rider License #, Rider Place, Rider Time
```

It may add `Race Distance`, `Race Distance Type`, and `Rider Lap 1` through `Rider Lap N`.
Its conventions:

- Race Date is written as `MM/DD/YYYY`.
- Race Gender is the category gender, with "Open" rewritten as `All`.
- Race Discipline is renamed to `Cyclo-cross` or `Road Race` "to correct for USAC's picky naming".
- Rider Place is a number, or a status code.
- Rider Time is `H:MM:SS` for finishers and blank for everyone else.

CrossMgr's help text says: "In the rider place column, USAC only recognizes a place (number) and the statuses DNF, DNS and DNP (Did Not Place)."
It maps its own statuses like this:

| CrossMgr status | Written to USAC as |
|---|---|
| DQ (disqualified) | `DQ` |
| DNS (did not start) | `DNS` |
| DNF (did not finish) | `DNF` |
| PUL (pulled) | `DNP` |
| NP (not placed) | `DNP` |
| OTL (outside time limit) | `DNP` |

Its column names differ from the 2024 template (`Rider License #` versus `Rider License`, and the column order differs).
This suggests USAC matches columns by header name, not by position.
UNVERIFIED: USAC still accepts the CrossMgr header names.
The app should use the 2024 template's exact header names.

## DNF, DNS, DQ, and DNP conventions

- The 2024 template allows `DNF`, `DNS`, `DQ`, and `DNP` in "Rider Place".
- One facility's published 2026 results contain only numbers.
- Other 2026 track uploads on the public site show `DNF` and `DNS` as place values.
  A sample of five track events (about 3,700 result rows) had 113 `DNF` rows and 13 `DNS` rows.
- USAC gives a DNF rider the worst ranking score for that race (600 points was seen).
- Tied places are allowed.
  One facility's madison results list both team partners with the same place (two rows with place 1, two rows with place 2).
- Suggested mapping for the app:

| App outcome | Rider Place value |
|---|---|
| Finished, placed | the integer place |
| Eliminated in an elimination race | the integer place it produced |
| Pulled or lapped out, but ranked by the rules | the integer place |
| Pulled and not ranked | `DNP` |
| Did not finish | `DNF` |
| Entered but did not start | `DNS` |
| Disqualified (relegated to no place) | `DQ` |

- UNVERIFIED: whether USAC wants DNS riders in the file at all.
  Including them is harmless if the race director prefers it.

## What a facility's uploads look like

These observations come from one facility's events 30881 (2026-02-28) and 30916 (2026-03-14) on the public results site.

- Disciplines used: "Points Race" and "Scratch Race" only.
  Madisons, omniums, and points races were filed under Points Race.
  Chases, miss-and-outs, chariot races, unknown-distance races, and match sprints were filed under Scratch Race.
  Other velodromes did use "Elimination Race" and "Keirin" for those formats.
- A facility's scoring sheet lists its own discipline codes for the template layout: `SR` (scratch), `MO` (elimination, "miss and out"), `MAD` (madison), `KEIR` (keirin), `PR` (pursuit), `POI` (points), and `TS` (team sprint).
  The codes `MO`, `POI`, and `KEIR` differ from the public results site's `er`, `pr`, and `keir`.
  UNVERIFIED: which of the two sets the portal accepts in the template layout.
  So the template export defaults to the sheet's codes, and every value is editable per race.
- Race titles look like `Madison 4 Mile SP A M`, `Jr A 3 Mile Points`, `SP C Miss and Out`, `Pro Omnium M`.
  UNVERIFIED: the title is USAC's join of the Race Category, Class, and Age Group values, plus a gender letter.
  If so, that facility has been putting the race name and distance into the Race Category column.
- Gender filters on the site show `Male` (code `M`), `Female` (code `F`), and `Mixed` (code `N`).
  Races with no trailing "M" in the title were filed as Mixed.
- License numbers were mostly 6 digits, some 5 digits.
  Some rows had no license.
  One row had a 2-digit value, which is a data entry error.
- Rows without a license were still published.
  Some rows with a bad license still got ranking points.
  This fits USAC's statement that "our results and rankings program uploads results off of name association".
  Source: <https://usacyclinghelp.zendesk.com/hc/en-us/articles/15974990264219>
- Another velodrome's age group "9-14" was published as "14-Sep".
  A spreadsheet program turned the text into a date before upload.
  The app must write the CSV directly.
  The race director should not open and re-save it in Excel.

## Example rows

The values below are invented.
They follow the 2024 template headers plus a bib column.

```csv
Race Date,Race discipline,Race Category,Race Gender,Race Class,Race Age Group,Rider License,Rider First Name,Rider Last Name,Rider Place,Rider Bib #
2/28/2026,SR,Cat 1/2/3/4,Mixed,Senior,,123456,Alex,Example,1,12
2/28/2026,SR,Cat 1/2/3/4,Mixed,Senior,,234567,Sam,Sample,2,7
2/28/2026,SR,Cat 1/2/3/4,Mixed,Senior,,,Pat,Newrider,DNF,31
2/28/2026,MAD,Cat 1/2/3/4,Men,Senior,,345678,Chris,Partner,1,15
2/28/2026,MAD,Cat 1/2/3/4,Men,Senior,,456789,Jordan,Partner,1,2
2/28/2026,ER,Cat 3/4/5,Mixed,Junior,9-14,567890,Riley,Youth,1,88
```

The discipline codes `SR`, `MAD`, and `ER` are verified: a venue's two-day event file with those three codes was uploaded and accepted (2026-Oct-19).
`PR`, `TMPR`, `SPR`, and `KEIR` are still unverified.
If the portal rejects one of them, use the codes or names a facility's past uploads used (see "The file a facility actually uploaded").

## A file the upload accepted (2026-Oct-19)

A venue's file for a two-day event was uploaded through the portal and accepted. What it shows:

- Nine columns, the template's without "Race Age Group": Race Date, Race discipline, Race Category, Race Gender, Race Class, Rider License, Rider First Name, Rider Last Name, Rider Place.
  The upload accepts a file without the Age Group column.
  UNVERIFIED: whether it also accepts the column present and blank, as this app writes it.
  Decision (2026-Oct-19): the column stays in this app's file, because USAC's own template has it.
- Dates as M/D/YYYY without leading zeros, CRLF line endings, plain ASCII, nothing quoted.
- Discipline codes `SR`, `ER`, and `MAD`, uppercase.
- Category is "Open" on every row; Gender is Men, Women, or Mixed; Class carries the group, distance, and format as free text ("Pro 4 Mile Scratch", "Women Elimination", "CoEd 8 Mile Madison").
- Rider Place is always a number. The file has no DNF, DNS, DQ, or DNP rows; a rider who did not finish was given the last place.
- A blank license is accepted.
- A Madison is one row per rider, both rows carrying the team's place (1, 1, 2, 2, ...).
- The two-day omnium standings were uploaded as a race of their own: discipline `MAD`, Class "Pro Madison Omnium", one row per rider with the team's place.

## Field by field against the template (2026-Oct-19)

The export was checked column by column against USAC's own `2024 Results template.csv` (a copy in `local/scorer-files/`) and against what the race dialog's USAC Details box asks for. `tests/export/test_usac_csv.py` pins each row of this table.

| Template column | Template's example values | What this app writes | Where the scorer sets it |
|---|---|---|---|
| Race Date | `7/4/2024` (M/D/YYYY, no leading zeros; blank on the template's later example rows) | The event's date as M/D/YYYY without leading zeros, on every row (as the accepted upload had it) | The event's date |
| Race discipline | Road and MTB codes (`RR`, `CRIT`, `TT`, ...); no track code shown | `SR`, `ER`, `MAD` (verified by the accepted upload); `PR`, `TMPR`, `SPR`, `KEIR` from USAC's results site, unverified | The race's format, through `export/usac_csv.DISCIPLINE_BY_FORMAT`; not a dialog field |
| Race Category | `Cat 1/2`, `Cat 4`, `Cat 1/2/3/4/5`, `Open`, `Cat 3/4` | The dialog's Category, whitespace squashed; a blank is the race's group, and a blank group is warned about at export | USAC Details > Category: offers Pro, Cat 1 to Cat 4, Novice, Open, every value the file has used, and free text ("Cat 3/4" is typed) |
| Race Gender | `Men`, `Women`, `Both`, `Mixed`, `Male`, `Female`, `M`, `W`, `A`, `B` | `Men`, `Women`, or `Mixed`; a race never set is `Mixed` | USAC Details > For |
| Race Class | `Master`, `Junior`, `Senior`, `Single Speed`, `A`, `B`, `Collegiate` | The dialog's Class, whitespace squashed, blank allowed | USAC Details > Class: offers Youth, Junior, U23, Elite, Senior, Master, Collegiate, the file's values, and free text |
| Race Age Group | `35+`, `U18`, `35-44` | The dialog's Age group, whitespace squashed, blank allowed; the column is always present (the template has it; the accepted upload left it out and went through) | USAC Details > Age group: the file's values and free text |
| Rider License | `123456` or blank | The rider's USAC license, or blank; the export summary names every rider written without one | The rider, in All Riders |
| Rider First Name, Rider Last Name | `John`, `Jane ` (a stray trailing space in the template) | The rider's names, whitespace squashed; a comma or a quote in a name is quoted the standard CSV way (`"O'Brien, Jr."`); the accepted upload had nothing to quote, so a quoted name is UNVERIFIED at the portal | The rider |
| Rider Place | `1`, `2`, `DNP`, `DNS`, `DNF`, `DQ`, blank | The rank (tied riders repeat it: 1, 1, 3), or `DNF`, `DNS`, `DQ`; a rider the scorer never placed is `DNP`, never blank; a Madison writes one row per rider with the team's place | The result |

File shape: UTF-8 without a BOM, CRLF line endings, ten columns on every row, nothing quoted unless a value needs it, one header row. Exactly the template's.

## Data the app must collect

Per event:

- Event date (or the date of each race, if an event spans days).
- UNVERIFIED but recommended: the USAC event ID, for the PDF and for the operator's reference.
  It does not go into the CSV.

Per race:

- Race date.
- Discipline (one USAC discipline code).
- Race Category (for example `Cat 3/4`, `Open`).
- Race Gender (`Men`, `Women`, or `Mixed`).
- Race Class (for example `Junior`, `Senior`, `Master`).
- Race Age Group (for example `9-14`, `35+`), when the field is age-limited.
- The final place or status of every rider.

Per rider (the persistent rider record):

- First name, exactly as on the USAC license.
  USAC matches results to members by name, so nicknames break the match.
- Last name, exactly as on the USAC license.
- USAC license number.
  It is numeric.
  Observed lengths are 5 and 6 digits.
  Store it as text, so leading zeros and future longer numbers survive.
  Allow it to be blank for one-day riders or riders who have not given it.
- Bib number (per event, because bibs can change).
- Optional: team or club.
- Optional: birth year.
  USAC racing age is the current calendar year minus the birth year.
  Source: <https://usacyclinghelp.zendesk.com/hc/en-us/articles/16222929064219>
  The app needs it only to check that a rider fits an age-limited field.
- Optional: UCI ID (11 digits).
  It is not in the template.
  UNVERIFIED: some 11-digit values in other events' license fields may be UCI IDs.

About the "Class" field in the rider list:

- The initial project notes list "Class" as a rider attribute.
- In the USAC template, "Race Class" is a property of the race, not of the rider.
- USAC licenses carry a separate category per discipline.
  The track category runs from Cat 5 (entry) to Cat 1.
  Source: <https://usacyclinghelp.zendesk.com/hc/en-us/articles/16159268764443>
- UNVERIFIED: at a club, "Class" probably means the local ability group (for example "SP A", "SP B", "Jr A", "Pro").
  Labels like these appear in one facility's published race titles.

## Points and upgrades that affect the export

- **Ranking points are computed by USAC.** The app does not export them.
  A race needs at least 3 riders in the uploaded results to generate ranking points.
  Source: <https://usacyclinghelp.zendesk.com/hc/en-us/articles/15964273643675>
- **Track upgrade points** come from places 1, 2, and 3 (3, 2, and 1 points).
  Time trials, individual pursuit, and team pursuit earn no upgrade points.
  Source: Track Upgrades chart, <https://assets.usacycling.org/prod/assets/Track-Upgrades.png>, linked from <https://usacycling.org/about-us/governance/policy-viii> (revised 2026-07-07).
- **Overall place, not category place.** Policy VIII says: "Upgrade points are based on the overall placing in the entire field, not broken out by category within the field."
  So a combined field (for example Cat 1/2/3/4) must be exported as one race with one overall place sequence.
- **Omnium.** Other velodromes uploaded the omnium as one race with the final omnium standings.
  UNVERIFIED: whether to also upload each omnium event (scratch, tempo, elimination, points) separately.
  Uploading each event separately would award ranking points per event.
- **Madison and other team races.** Each team member gets their own row with the team's place.
- **Points races and other points-based races.** Only the final place goes in the file.
  Sprint points and lap gains are not exported.

## Open questions for the race director

1. Can you send one CSV you uploaded to USAC, as you uploaded it?
   That answers most of the questions below at once.
2. What did you put in "Race discipline" for your races?
   Did the portal reject any value?
3. Do you want madisons, omniums, and chases filed under their own disciplines (`MAD`, `OMN`, `SR`), or under Points Race and Scratch Race as before?
4. What goes in "Race Category" for your races?
   Do you include the race name and distance there (for example "Madison 4 Mile SP A")?
5. What does "Class" mean in your rider list?
   Is it the local group (SP A, SP B, Jr A) or a USAC category or age class?
6. Do you include a bib column?
   What is its exact header?
7. Do you upload DNS riders?
   Do you use `DNF`, `DNP`, and `DQ`?
8. Do you upload every race of the night, or only some?
   Do you upload each omnium event separately, or only the omnium final standings?
9. Is the whole season one USAC event (one permit), with a date per race?
   Or is each race night its own sanctioned event?
10. Who uploads: you, the Chief Referee, or another event admin?
11. Do you open the file in Excel before uploading?
    If yes, age groups like "9-14" may turn into dates.
12. How do you record one-day license riders?
    With a blank license, or with the one-day license number?

## Sources

All accessed 2026-10-07.

- USAC help, "How to upload results to an event sanction" (updated 2025-10-23): <https://usacyclinghelp.zendesk.com/hc/en-us/articles/42343840919195-How-to-upload-results-to-an-event-sanction>
- USAC template file `2024 Results template.csv`: <https://usacyclinghelp.zendesk.com/hc/article_attachments/42516975392411>
- USAC help, "How to upload event results in USA Cycling Member Portal" (updated 2026-04-21): <https://usacyclinghelp.zendesk.com/hc/en-us/articles/42109985145115-How-to-upload-event-results-in-USA-Cycling-Member-Portal>
- USAC help, post-event report for the Chief Referee: <https://usacyclinghelp.zendesk.com/hc/en-us/articles/42111663331739>
- USAC help, "Why is my license number not associated to my results": <https://usacyclinghelp.zendesk.com/hc/en-us/articles/15974990264219>
- USAC help, minimum field size for ranking points: <https://usacyclinghelp.zendesk.com/hc/en-us/articles/15964273643675>
- USAC help, racing age: <https://usacyclinghelp.zendesk.com/hc/en-us/articles/16222929064219>
- USAC help, race license categories: <https://usacyclinghelp.zendesk.com/hc/en-us/articles/16159268764443>
- USAC public results and discipline list: <https://usacycling.sport80.com/pub/results>
- USAC Policy VIII (upgrades): <https://usacycling.org/about-us/governance/policy-viii>
- Track Upgrades chart: <https://assets.usacycling.org/prod/assets/Track-Upgrades.png>
- CrossMgr source, `USACExport.py` and `helptxt/Menu-Publish.md`: <https://github.com/esitarski/CrossMgr>

## The file a facility actually uploaded (added 2026-10-08)

A facility supplied the CSV it uploaded for one race night (2026-02-28), which USAC accepted and published. It is the layout to produce, because it is proven. The file itself stays out of the repo because it holds rider data.

- Nine columns, in this order and spelling: `Race Date, Race Discipline, Race Class, Race Gender, Rider License #, Rider Last Name, Rider First Name, BIB NUMBER, Rider Place`. Note "Discipline" capitalized, last name before first name, no Race Category and no Race Age Group columns, and the bib header `BIB NUMBER`.
- CRLF line endings, no BOM, no quoting needed.
- `Race Date` as M/D/YYYY (2/28/2026).
- `Race Discipline` is a word, not a code: `Points` for the points race and both madisons, `Scratch` for every chase, miss-and-out, chariot and unknown-distance race. One row carried `Scratch ` with a trailing space and was still accepted, so USAC trims.
- `Race Class` is the race title: `SP A 3 Mile Chase`, `SP B Miss and Out`, `Jr Chariot 1`, `Madison 4 Mile SP A`, `SP B/C Unk Distance`. So the race name is what USAC publishes as the race title, and the local group is embedded in it.
- `Race Gender`: `Men` or `Mixed`.
- `Rider License #`: present on every row; lengths 2, 5, 6 and 7 digits (some are not USAC numbers; a 7-digit value is probably a typo or a foreign id).
- `BIB NUMBER`: sometimes blank; USAC accepted blanks.
- `Rider Place`: integers only in this file; madison partners share the place number.
- 144 rows across 18 races; a race per distinct (Discipline, Class, Gender).

Implication: the exporter defaults to exactly this layout, with `Race Class` = the race name and `Race Discipline` = Points or Scratch by format. The ten-column template layout stays available as an option only if a facility needs it.

## Updates

2026-Oct-13: The exporter writes USAC's 2024 template only: its ten columns, in its order, with its exact headers, and no bib column. The facility's nine-column file described in "The file a facility actually uploaded" is no longer produced, and neither are its discipline words (Points, Scratch) or its scoring sheet's codes (MO, POI). Race discipline is now the uppercase code from USAC's public results site (PR, TMPR, MAD, ER, KEIR, SPR, and SR for everything run as a scratch race). Whether the upload accepts these codes is still unverified until a real upload, so a race's stored discipline override still wins. The race editor now has Category, Class and Age group fields for the template's Race Category, Race Class and Race Age Group. The facility's group goes in Race Category when Category is left blank, since it is an ability group.

2026-Oct-15: The export names any races in the file that share discipline, Race Category, Race Gender, Race Class, and Race Age Group, compared without case, as races USAC may file as one; the race editor shows the same as a note. Both rest on the unverified splitting rule under "What ties the file to the permit". The venue's night 95 had two such pairs (two junior chariot races, and a chase beside an unknown-distance race of one group, both SR). A real upload settles whether it is a warning or a rule. The race editor's Category and Class now offer the rulebook's words (1D1 and 1D2 track categories; 1C1 age-based classes, plus the template's Senior and Collegiate) and every value the data file has used.
