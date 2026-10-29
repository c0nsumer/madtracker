# Multi-Race Standings

The Multi-Race Standings report produces standings covering races from several events, such as a two-day omnium where Friday's and Saturday's Madisons add up to one total, or a season where each rider's places add up week by week.

It is kept in the data file as a definition: a name, a kind, the events it covers, and any race left out. It recalculates every time it is viewed or exported, from the selected races' results.

The standings display on screen and export as a PDF. They are not shown on the scoreboard, and there is no CSV export.

**Note**: The **Series** field on the Edit Event screen (see [The event](getting-started.md#the-event)) is a label that appears under the event's name in the PDF exports. It does not choose the events a standings covers; you select those in the dialog.

## The four kinds

**Kind** says what adds up and how; the type of multi-race tabulation. Every kind ranks each group on its own. Two kinds are for teams and count the Madisons of the selected events; two are for riders and count the races other than the Madison (the Four-Race Omnium counts only its four).

- **Team Omnium by Points**: each team's Madison totals from the selected nights, summed into one total.
- **Team Omnium by Place**: each team gets points for its place in each Madison, and those points are summed, the omnium scoring of USAC 2B19(e). The **Place points** table defaults to 7, 5, 3, 2, 1 (7 for 1st, 5 for 2nd, and so on) or you can set another list of points, eg: "5, 4, 3, 2, 1", which is saved with those standings. There may be up to 50 places, using whole numbers from 0 to 999.
- **Omnium by Place**: each rider gets points for their place in each race, from the same **Place points** table, and those points are summed. Every race of the selected events counts except the Madison, whose entrants are teams.
- **Four-Race Omnium**: the omnium of USAC 2O1 to 2O3 (UCI 3.2.247 to 3.2.252): one [Scratch Race](scoring.md#scratch-race-usac-2c), one [Tempo Race](scoring.md#tempo-race-usac-2p), one [Elimination](scoring.md#elimination-usac-2e), and one [Points Race](scoring.md#points-race-usac-2m) per event. The first three award 40, 38, 36, and so on down to 2 for places 1 to 20 and 1 from 21st, and the Points Race's own points are added. There is no **Place points** row; it uses the rulebook's points. A rider who does not start, does not finish, or is disqualified in any of the four is out of the omnium and listed after every finisher, as DNF or DQ. The selected races must be exactly those four for each event and group, and every selected event must have them; otherwise the **Standings** box says which event or group is short or has a format twice, and there are no standings until it's fixed. If the Points Race can't be run, or is stopped before 80 percent of its distance and can't be restarted, the standings after the Elimination are the omnium's final classification (USAC 2O4): deselect the Points Race under **Races**, and the three races stand, Final once each is. The other three can't be left out.

A tie on the total goes to the team or rider with the most wins, then the most 2nd places, and so on, then the better place in the latest race where either placed (USAC 2B19(e)). Teams or riders with the same record share the place. In the Four-Race Omnium a tie goes to the places in the final sprint of the Points Race (USAC 2O3(g)). Changing the kind saves at once and starts the standings from that kind's default points, with any omnium penalties taken off.

In the Four-Race Omnium, a rider who loses two laps in the Scratch Race or the Tempo Race is withdrawn, takes the next place, and loses 40 omnium points (USAC 2O3(e)). Record that with **Omnium Penalty...** under the **Standings** box: pick the rider, type the points, and press Enter. The penalty is on the standings, not on any race, so the race results stay as the officials gave them. It shows in a Penalty column beside the total, in the **Standings** box and the PDF export, and 0 takes it off. The button is there for the Four-Race Omnium only, and the list offers the riders still in the omnium. In the race itself, mark the rider **Withdrawn** from the card's ⋯ at that moment (see [Rules shared by every format](scoring.md#rules-shared-by-every-format)); do not mark them Did Not Finish, which would put them out of the omnium altogether.

A mishap is not an abandon. A rider kept out of a [Points Race](scoring.md#points-race-usac-2m) finish by one (**Out of the Finish (Mishap)**) is placed on the points they held and stays in the omnium, and a rider who crashes out of an [Elimination](scoring.md#elimination-usac-2e) is clicked out and placed, and stays in too. Only Did Not Finish, Did Not Start, or Disqualify puts a rider out, so use Did Not Finish for a rider who quits.

## Which riders, teams, and races count

- Every race the kind counts in the selected events is in the standings unless you deselect it under **Races**.
- Each group's races are ranked together. A race with no group label goes under the heading "No Group".
- A team is its pair of riders (see [Madison](scoring.md#madison-usac-2n)). Colors and team names change from night to night, so the two riders are what identify a team. A team shows under the name and color it raced under last.
- A team that rode fewer than every counting Madison of its group is left out of the standings. A team that started and did not finish keeps the points it scored there. A team marked Did Not Start is not scored.
- A rider is determined by rider record, regardless of bib, and shows under the bib they raced under last. Every rider who rode any counting race is in the standings; there is no minimum. A race they did not ride is blank and adds nothing. A rider marked Did Not Finish or Disqualified rode and scores nothing for that race, unless the race placed them: an Elimination puts a rider who leaves out at that moment with the next place, and that place scores. One marked Did Not Start did not ride.
- A race not yet scored is not yet raced: it is no column, and it adds nothing to the standings until it's scored. A race still running counts in a place kind once it has placed every rider still in it: a Points Race counts as it stands, by points held, while a Scratch Race or an Elimination waits and shows "(racing)" in the list. Team Omnium by Points sums a running Madison as it stands.

## Creating Multi-Race Standings

Choose **File** → **Multi-Race Standings...**. The file's standings are listed on the left, the selected one's page is beside the list, and the **Standings** box fills the rest. Each change is saved as you make it. Nothing in the dialog changes a race, so it has no Undo.

1. Click **Add...** and give it a name, eg: "Oktoberfest 2 Day Omnium". The standings needs a name. To change it later, type in **Name**.
2. Pick the **Kind**. For Team Omnium by Place and Omnium by Place, set **Place points**.
3. Select its nights under **Events**. The list holds every event in the file, with its date.
4. Every race the kind counts in the selected nights is listed under **Races**, under its event, selected. Deselect a race to leave it out. A race not yet scored shows "(not yet raced)" in gray after its name. With no race the kind counts in the selected events, the list says so.

**Duplicate...** copies the selected standings under a new name: its kind, place points, events, left-out races, and omnium penalties. **Delete** removes the selected standings after asking; the races and their results are not changed.

A standings can be made before the weekend starts and displayed or exported again as each race is scored.

## On-Screen Standings

The **Standings** box shows the current standings, the same as the PDF export. Across the top is how many of the counting races have been raced, over how many events, eg: "3 of 4 races raced over 2 events" ("Madisons" for the team kinds), and a Final tag once every race in them is final and none is left to race. Before that there is no tag: the count says what is still to come. Under that are each group's standings. Each row has the place, then the team with its color and both riders or the rider's bib and name, a column for each race headed by its date and name, and the total. A race's cell is the team's total in that race for Team Omnium by Points, its place points for the place kinds, and in the Four-Race Omnium the rulebook's points or, for the Points Race, the points scored.

On a narrow screen a team's riders give way first, then the race names are shortened, and past that the race columns scroll sideways while the team and the total stay in view. A rider kind keeps its names and scrolls the races instead.

## PDF Export

**Export PDF...** writes the standings as a PDF. It asks where to save, in Documents or the **Exports folder** from [Settings](getting-started.md#settings), under a name made from the latest night's date and the standings' name, eg: "2026-10-18 - Oktoberfest 2 Day Omnium - Standings.pdf". The button is grayed while no team or rider is in the standings.

The PDF export is landscape. It has the standings' name, with a FINAL tag once the standings are final, and three gray lines under it: the kind and how many of its races are raced, the events it covers, and how it scores. Then each group's standings, as in the **Standings** box.

A season with more races than fit beside the names repeats the standings for each run of races that does, "Races 1 to 20 of 40", each with the place, the name, and the total. Under the standings, each night lists what its races did for the standings: "Counted", "Still racing", "Not yet raced", and "Not counted" for the races you deselected, so a PDF exported mid-weekend says what it does not include yet.

**Suggestion**: Export the PDF at the end of each night. Each posts the running standings, and the one tagged FINAL, after the last race is marked final, is the archive.
