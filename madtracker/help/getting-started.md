# Getting Started

Scoring an event with MadTracker follows this overall flow:

1. Create the data file and initial settings (only on first setup, or as desired)
2. Create the event
3. Add or update the riders
4. Define the races and the rider roster
5. Mark down the results
6. Generate the reports

Press F1 at any time (or Command-? on a Mac) to open the help for the screen in view. The pages link to each other's sections; **Back** and **Forward** at the top of the help window (Alt+Left and Alt+Right, or Command-[ and Command-] on a Mac) retrace the links you followed.

## Terminology

| Term | What it is | Part of |
|---|---|---|
| Venue | The place, and the one data file that holds it: its name, logo, riders, rulesets, and every event. | |
| Ruleset | The point values a venue scores with. | Venue |
| Rider | A person. Riders are kept from event to event, so a rider is in the venue, and on a roster only for the events they enter. | Venue |
| Event | One date of racing at the venue. It has a roster and a program. | Venue |
| Series | An optional series name label on the results, program, and standings PDFs. Display only. | Event |
| Roster | The riders entered in the event, each with a bib number for that event. | Event |
| Group | A label on a roster entry, eg: "A" or "Juniors", used to fill a race's field. | Roster |
| Program | The event's races, in order. | Event |
| Race | One contest, with one format and one field. | Program |
| Field | The riders or teams in a race, usually a group from the roster. | Race |
| Team | Riders scored together in a race, eg: the pair in a Madison. | Race |
| Result | The race's placings, and points where the format has them. | Race |
| Multi-Race Standings | A points table over races from several events, eg: a weekend's Team Omnium. | Venue |

## The data file

The data file is a database which holds everything: the venue info and its logo, the overall rider list, the event list, the riders participating in each event, the [rulesets](scoring.md#rulesets) used, the races, and other settings.

This is created when first launching the program, or on demand.

This file, and the backups, are an [SQLite](https://www.sqlite.org/) database and can be opened or analyzed in other software. There are a few methods for backing it up, automatically or on demand. See [Backups](backups.md).

**Suggestion**: For practice scoring use either the [demo](#demo-data-file) or make a second file with **File** → **New Data File...** and check what to copy from the open one. **File** → **Open Data File...** switches between files.

### Demo data file

To see how the program works before setting up your own, use **Help** → **Demo Data File...**.

**Create New** builds a sample data file with invented riders and two events: one already scored, and one with a race of every format ready to score. The scored night shows an entry of each kind a race can need beside the placings: a lap, **Lap Not Counted**, **Did Not Start**, **Did Not Finish**, **Disqualify** after the finish, **Points Penalty...**, **Out of the Finish (Mishap)**, **Withdrawn**, **Shorten Race...**, and **End Race Now, Result As-Is...**. It has three multi-race standings over both nights, one of each kind but Team Omnium by Place, so the Multi-Race Standings dialog has something to show.

**Open Previous** opens the demo you last used instead. This demo data is separate from your own data file, which is not changed.

The demo is stored as `demo.sqlite` in a `demo` folder under your data folder, with its own backups and log in that folder. While the demo is open, **Help** → **Open Data Folder** opens that folder. The demo is open for this session only: the next time the program starts it returns to your own file. To load your data file without relaunching, use **File** → **Open Data File...** and open your data file. You can also use this same process to reopen the demo file.

## Settings

A new file with no event shows three buttons in the middle of the window: **Settings...**, **Edit Riders...**, and **New Event...**. They are the same items as on the **File** menu, and a check mark shows on a step once it's done.

Click **Settings...** (**File** → **Settings...**; on macOS it's **MadTracker** → **Preferences...**, and the window is called Preferences) and fill in the venue's values. They are stored in the data file and rarely change.

- **Venue name**: shown on the results PDF.
- **Scoreboard logo**, **Riders on the scoreboard** (Names Only, Bibs and Names, or Bibs Only), and **Accent color**. These set how the scoreboard looks.
  The logo must be a PNG file. It shows on the dark scoreboard and in the dark band at the top of the PDF sheets, so light-colored artwork on a transparent background works best. A wide logo, about three times as wide as it is tall, fills the most space. For a 1080p TV, make it at least 1400 pixels wide; for a 4K TV, 2880 pixels wide. A larger image is scaled down to fit 2880 by 1200 pixels when it's picked, so there's no reason to go bigger.
- **Backup folder**: an extra copy of the data file written when MadTracker is closed. For example, to a USB stick. See [When and where](backups.md#when-and-where).
- **Exports folder**: where the PDF and CSV exports go by default (see [Results](results.md)). Leave it blank for Documents.
- **Rulesets...**: the point values the venue scores with (see [Rulesets](scoring.md#rulesets)). The built-in ruleset holds scoring based on the USA Cycling rulebook and club rules. For the venue's own values, select it, click **Duplicate...**, then **Edit...**, change the numbers, **Save**. And if desired, set the house rules as default with **Set as Default**. **Export to File...** and **Import from File...** move a ruleset between data files as a `.json` file.

## Riders

Click **Edit Riders...** (**File** → **Edit Riders...**). This is the venue's list of riders and it is kept from night to night. This is the one place where a rider is added, imported, edited, or merged with another entry.

- **New Rider...** adds one by hand: first name, last name, USAC License, UCI ID, and birth year.
- **Import from BikeReg...** reads the entries CSV and shows a preview before anything is saved. **Put on the roster of** names the event the riders go on, with their bibs and groups. If there is no event yet, pick **No Event**.
- **Merge With...** joins two records.

In the import preview, each row's **Status** says what Import does with it:

| Status | What Import does |
|---|---|
| "New" | No rider on file matches. Import adds the rider. |
| "New?" | A rider with the same name is on file. **Details** names them. |
| "On file" | The rider is on file, and the file adds nothing. |
| "Update" | The file fills in a value the rider is missing, such as a USAC License. |
| "Review" | The file and the rider on file disagree on a value. A first name with the same first letter on a matching USAC License or UCI ID is only noted, as "registered as ...". |
| "Conflict" | The row's USAC License or UCI ID belongs to another rider, the file gives one id to two people, or a likely match is already on this roster. **Details** says which. |

Import brings in the checked rows only. "New?" and "Conflict" rows start unchecked, and **Select All** leaves them off. When a row may be a rider on file, its **Status** cell is a list and **Details** names who. Pick "Same as ..." to make the row that rider. To add the row as another person, check it. Nothing is merged on its own.

At **Import**, a window opens for each checked "Review" row. Pick the value to keep on each tinted line.

If an import makes a second record of one person, select one of them and click **Merge With...**.

**Note**: Bib assignments do not happen in the rider list as this is a list of all riders at a venue. Bibs are assigned per event.

## The event

Click **New Event...** (**File** → **New Event...**). Type the name and pick the date. During a subsequent event, **Start from** can be used to copy an earlier event's program with empty fields. To copy a previous event's details, such as for the second night of a two-day event, check **Copy roster, bibs, fields, and teams**.

**File** → **Open Event...** lists the venue's events, newest first, and opens the selected one. **Delete** there removes an event made by mistake. An event with a race that has ever had an entry can't be deleted.

The Edit Event screen opens, with three parts: Event, Roster, and Program. Work down it from the top. Under **Event**, **Series** is an optional label shared by related events, eg: a season. It appears under the event's name on the program and the results sheet. The **Edit** | **Score** switch under the program shows which screen is open. Click **Edit** to reopen it at any time.

Under **Roster**, click **Choose Riders...** and check everyone racing in this event. Type part of a name in the filter box to find a rider: each word is matched anywhere in the first or last name, so "Maya P" and "akis" both find Maya Petrakis. Press Enter to check the top match. Close the window, and the checked riders fill the roster table.

Type each rider's bib in the gray **Bib** cell and press Enter to jump to the next rider without a bib. An empty cell is tinted red, and the count above the table says how many bibs are missing. A race can't be scored until every rider in it has a bib.

Pick each rider's group in the gray **Group** cell. A group is a label for this event, such as Group A, and it's the primary way to set who is participating in a race. **Edit Groups...** makes, renames, and merges groups.

During a BikeReg import that contains bibs and categories, setting **Put on the roster of** to this event adds these riders to the event, with their bibs, and puts each in a group derived from their BikeReg category.

## The races

Under **Program**, click **Add...** once per race, in order.

- **Name**: if left blank, it uses the group and the format, eg: "Group A Scratch Race".
- **Format**: the USA Cycling Rulebook and club formats.
- **Group**: pick this to fill the field with that group's riders. Check or uncheck riders to adjust it, and type in the filter box above them to find a rider by name, group, or bib, the same way as in **Choose Riders...**; "#7" finds bib 7 alone. Enter checks the top match. Riders from outside the group can be added.
- **Ruleset**: the venue's default, or select another.
- **Sprints**: number of sprints; used for a [Points Race](scoring.md#points-race-usac-2m), [Madison](scoring.md#madison-usac-2n), or [Tempo Race](scoring.md#tempo-race-usac-2p).
- **Places**: number of places for a [Win-and-Out](scoring.md#win-and-out-club).
- **USAC CSV Details** box: These values, **Gender**, **Category**, **Class**, and **Age group**, are only used by the USAC CSV export. Each list offers values from USAC's template and values previously used in MadTracker. Anything else can be typed in directly. If another race has the same details, a gray note names it (see [The USAC CSV](results.md#the-usac-csv)).

A Madison's field is its teams (see [Madison](scoring.md#madison-usac-2n)). Click **Add Team...** for each team, pick a color and two riders, and type a name if the team has one.

**Duplicate...** opens a copy of the selected race, its riders or teams included, to change and save as a new race right after it. **Edit...**, **Remove**, and the up and down arrows change the program. Once a race has an entry, **Edit...** changes only its name and its USAC CSV details; the format, group, ruleset, sprints or places, field, and teams are fixed. If every entry is undone, back to the start list, the race can be edited in full again. **Remove** is refused for a race that has ever had an entry. Click **Score** to return to the race you were on, or to the first race.

Once the races and fields are set, **File** → **Export Program PDF...** writes the program, to post for the riders and for the announcer to call each race's riders onto the track. It lists the races in order, each with its group, how it scores, and every rider in it by bib and name. A Madison lists its teams. It has no start times. Export it again if a field changes; the footer says when it was generated.

## The scoreboard

The picture under the Program shows a copy of the scoreboard. Click it to switch the scoreboard between its two screens: the logo screen, which shows the venue's logo from Settings with the event name under it, and the live screen, which shows the selected race. **Scoreboard** → **Logo** and **Scoreboard** → **Live** do the same.

The **Scoreboard** menu lists where the scoreboard goes: **Automatic**, each display with "Full Screen" or "Windowed" after its name, and **None**, which turns the scoreboard off. While it is off, the picture is grayed out and says "Off", and a click on it does nothing; picking a display or **Automatic** brings the scoreboard back as the picture showed it, the race or the logo. Opening another event puts the scoreboard on the logo, so the TV never shows a race you didn't choose.

While MadTracker is running, it keeps the displays awake, so the laptop's screen and the scoreboard TV don't go to sleep during a night with no typing. It may not stop a screen saver, so turn the screen saver off on a laptop used for scoring. On Linux this works on KDE, Xfce, and other desktops that support it; on GNOME, turn off screen blanking in the power settings.

## Scoring a race

To score a race, select it in the Program on the left. A race being scored is tagged Racing, and selecting another race asks before switching away.

The line under the race's name gives a hint as to how to enter the results, eg: "Click riders in the order they finish." Click the rider cards as the officials call them.

A rider you've placed, clicked out, or marked keeps their card where it was, grayed, with the place in blue or the status ("DNF", "DNS", "DQ", "Withdrawn", or "Mishap") on it, so the other cards never move. A click on a grayed card does nothing. Its **⋯** holds the same items as the rider's row in the result.

Each card has **−1** and **+1** for a lap lost or gained, where laps count, and a **⋯** menu with **Did Not Start**, **Did Not Finish**, **Disqualify**, and, where the officials pull a rider, **Withdrawn** (see [Rules shared by every format](scoring.md#rules-shared-by-every-format)). In a race placed by its finish order the menu starts with **Place Last** to allow marking results from the tail of the race.

In a Points Race, Madison, or Tempo Race it also has **Points Penalty...**, and wherever laps count it has **Lap Not Counted** once a lap is gained (see [Points Race](scoring.md#points-race-usac-2m)).

While a sprint is being scored, a card with a place offers **Move Up**, **Move Down**, and **Move to Place** to fix a wrong order. The card of a rider placed after another offers **Tie with the Rider Above**, or **Tie with the Rider Below** (**Tie with the Team Above** and **Tie with the Team Below** in a Madison). On a card that shares its place, **Move Up** reads **Break Tie**.

What a click on a rider or team means depends on the format:

- **[Scratch Race](scoring.md#scratch-race-usac-2c), [Handicap](scoring.md#handicap-usac-2d), [Chariot](scoring.md#chariot-club), [Unknown Distance](scoring.md#unknown-distance-club), [Sprint Final](scoring.md#sprint-final-usac-2f-and-keirin-final-usac-2h), and [Keirin Final](scoring.md#sprint-final-usac-2f-and-keirin-final-usac-2h):** click riders in the order they cross the line. If the officials call the last places first, **Place Last** on the card's ⋯ takes them from the tail, and **Place the Rest Together** gives every rider still unplaced one shared place.
- **[Elimination](scoring.md#elimination-usac-2e):** click the rider the officials call out at each sprint. Two out at one bell are two clicks, in the order the officials name them. With two left, the line reads "Click the winner."
- **[Points Race](scoring.md#points-race-usac-2m) and [Madison](scoring.md#madison-usac-2n):** at each sprint, click the riders who score, in order, then **Record Sprint**. The line under the race's name says how many: four under the rulebook (5-3-2-1), or as the ruleset sets. A rider clicked past those scores nothing, and their place shows in gray; one more click is how a tie for the last place that scores is entered, then **Tie with the Rider Above** on that rider's **⋯**. For the final sprint, click every rider in the order they finish, not only those who score. It's recorded automatically on the last click, with no **Record Sprint** button shown. A rider kept out of the finish by a mishap gets **Out of the Finish (Mishap)** from their **⋯** during the final sprint. The **⋯** at the right end of the line under the race's name holds the officials' calls on the race itself: **Shorten Race...** and **End Race Now, Result As-Is...**.
- **[Tempo Race](scoring.md#tempo-race-usac-2p):** click the sprint's winner, then **Record Sprint**. In the final sprint, click every rider in the order they finish. All are needed to break a tie based on points. It's recorded on the last click, with no **Record Sprint**.
- **[Win-and-Out](scoring.md#win-and-out-club):** click one rider per bell lap ("Lap 1: click the winner."). After the last place, click the rest in the order they finish.

**Did Not Start** is offered until anything is recorded for the rider; after that, only **Did Not Finish** and **Disqualify**. A rider already marked Did Not Start or Did Not Finish can still be disqualified from their row in the result: the DQ replaces the earlier mark.

**Undo**, in the bar under the race, says what it takes back, eg: "Undo: #7 Maya Petrakis placed 1st". Once the race is marked final it reads "Reopen First to Undo". Ctrl+Z (Command-Z on a Mac) does the same as the button.

When every rider is placed, the cards go away and the result shows as a list marked "Provisional". Results are adjusted via the row's **⋯** menu, and then **Mark Final** marks the race "Final" once scoring for it is complete. **Reopen** unlocks a final race. The tags mean the same on the sheet (see [The PDF](results.md#the-pdf)).

In a race placed by its finish order or an Elimination the menu has **Move Up**, **Move Down**, **Move to Place**, **Tie with the Rider Above**, **Tie with the Rider Below**, and **Disqualify**. On a tied row **Move Up** reads **Break Tie**.

In a Win-and-Out the rows of lap winners offer only **Move Up**, **Move Down**, and **Disqualify**; a move swaps the winners of two laps.

In a Points Race, Madison, or Tempo Race the total ranks the rows, so the menu has the officials' rulings instead: **Points Penalty...**, **Lap Not Counted** while a lap gained stands, and **Disqualify**. **Lap Not Counted** is only on a row with a lap gained. A sprint is reopened by clicking its column header.

How each format comes out, and more details, can be found on the [Scoring](scoring.md) page.

## Generating results

**File** → **Export Results PDF...** writes the results sheet, for the whole event or for one race picked from a list (see [The PDF](results.md#the-pdf)). **File** → **Export USAC CSV...** writes the night's results for USA Cycling's upload (see [The USAC CSV](results.md#the-usac-csv)).

Standings over several events, eg: a two-night omnium or a season, are **File** → **Multi-Race Standings...**, with a PDF export of their own. See [Multi-Race Standings](multi-race-standings.md).

A backup of the data file is taken on its own as races conclude and when the program closes. See [Backups](backups.md). To move the file to another laptop, see [Restoring](backups.md#restoring).

**File** → **Quit** (on macOS, **MadTracker** → **Quit MadTracker**) takes the final backup before the program closes. **Help** → **About MadTracker** (on macOS, **MadTracker** → **About MadTracker**) shows the version to give in a bug report.
