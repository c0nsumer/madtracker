# Scoring

This page explains how MadTracker works out the result of each format.

**Note**: MadTracker is not a USA Cycling product and is not endorsed by USA Cycling. It strives to score races as the [USA Cycling Rulebook](https://usacycling.org/resources-rules-fees-policies/rulebook) describes, but it is not an authority on those rules. It also adds some club-specific formats.

The articles named below are from the USA Cycling Rulebook Version 8•25 and are cited as the book writes them, eg: 2M2(f). (As of mid-October 2026, when this software was written, the current rulebook PDF said Version 7•2025 on the title page and some footers, but later indicates the changes in 8•25.)

## Rules shared by every format

- A tie shares a place, and the next place is skipped: 1, 2, 2, 4.
- Did Not Start and Disqualified take the rider out of the result; the sheet shows DNS or DQ. A disqualified rider's place goes to the riders behind them.
- Did Not Finish keeps any points the rider scored and ranks them after every finisher; the sheet shows DNF. (The [Elimination](#elimination-usac-2e) is the exception.)
- **Withdrawn**, on the card's ⋯ and the row's ⋯, is for a rider the officials pull from the race, or classify as though pulled. In the Four-Race Omnium's Scratch Race and Tempo Race, that's a rider two laps down, pulled or not (2O3(e); see [The four kinds](multi-race-standings.md#the-four-kinds)). In any race it's a pulled rider the Chief Referee has placed (1M6(d)). Mark it at that moment: the card stays, grayed, with "Withdrawn" on it, and the rider ranks after every rider who finishes, so the latest withdrawn ranks highest (a rider who later abandons is not placed, so that place closes up). When several are pulled together, mark them in the order the officials give, lowest first. Their points and laps stay as figures, and the sheet shows "Withdrawn" beside the name. Don't mark them Did Not Finish for it. Withdrawn is offered in the races placed at the line, the Points Race, the Madison, and the Tempo Race; an Elimination clicks a pulled rider out instead, and the Win-and-Out has no rule for it. **Undo** takes it back.
- A rider already marked Did Not Start or Did Not Finish can still be disqualified, from the result row's ⋯: the DQ replaces the earlier mark, and **Undo** puts it back.
- A race entry in the file includes a copy of the rules it was made with. Editing a ruleset later doesn't change the rules used by past races.
- While a race runs, each row of the standings has a ⋯ with the same actions as the rider's card, except the moves of a place being built, which stay on the card. The card's **+1** and **−1** are **Gained a Lap** and **Lost a Lap** on the row's ⋯. A right-click (or a long press) on a card or a row opens its ⋯ menu. A rider placed, out, or marked keeps a grayed card in the same spot with the place or the status on it. A click on it records nothing, and the line under the race's name says why. Its ⋯ holds the same items as the rider's row.

## Rulesets

A ruleset changes numbers, not methods. For example, these are the sort of things that can be changed in the rulesets:

- The sprint points for the [Points Race](#points-race-usac-2m) and the [Madison](#madison-usac-2n) and whether they give double points for the last sprint
- The [Tempo Race](#tempo-race-usac-2p) points per sprint
- The lap gained and lap lost points for the Points Race, the Madison, and the Tempo Race
- The [Elimination](#elimination-usac-2e)'s final sprint size
- The [Win-and-Out](#win-and-out-club) direction
- Whether a lapped [Scratch Race](#scratch-race-usac-2c) rider is placed by laps down

It can also give a format the venue's own name (**Shown as**), eg: "Devil" for the Elimination.

The built-in ruleset, **USAC 2025 + Club formats**, is aligned with the USAC rulebook's values and club values chosen from surveying clubs that post their rules to the internet. This built-in ruleset can't be changed, but it can be copied to a new set which can be edited and set as the new default (**Rulesets...** in [Settings](getting-started.md#settings)).

A sprint points table is typed first place first, eg: "10, 7, 5, 3, 2, 1". Spaces, semicolons, or hyphens between numbers are accepted. Whole numbers from 0 to 999 only; anything else is refused on the red line when you click **Save**. An empty field shows the rulebook's default table in gray.

## Scratch Race (USAC 2C)

Riders are placed by net laps first, then by the order across the line. A rider a lap down who stays in is placed behind every rider on the lead lap (2C4). With **Lapped riders are placed by laps down** off in the ruleset, a lapped rider is Did Not Finish instead.

If the officials call the last places before the rest, use **Place Last** on the rider's ⋯ menu. The rider takes the last open place, counted from the riders still in the race, and the next **Place Last** takes the place above it. If the officials can't separate the riders in the middle, click **Place the Rest Together**. Every unplaced rider then shares the next place, an equal placing under 1M6(a), and the result is complete. **Undo** takes back one place at a time, from either end.

In a [Four-Race Omnium](multi-race-standings.md#the-four-kinds), a rider who falls in the last kilometer and can't finish is still ranked (2O3(f)): give them **Place Last**, counting from the riders still in, rather than Did Not Finish, which would put them out of the omnium.

If a rider was clicked in the wrong order, use the ⋯ on their row in the result list. A row placed from the front offers **Move Up**, **Move Down**, and, with three or more places clicked from the front, **Move to Place**. A row placed from the back offers **Move Up** and **Move Down** within the back. **Undo** takes a move back. Where laps count, a row moves only among the riders on its lap, so a rider a lap up can't be moved below or tied with a rider on the lead lap. If the lap itself shouldn't stand, **Lap Not Counted** on the row's ⋯ is the ruling for that (see [Points Race](#points-race-usac-2m)).

## Handicap (USAC 2D)

Riders start from the marks the handicapper sets. After the start it's placed as a [Scratch Race](#scratch-race-usac-2c) (2D5).

## Elimination (USAC 2E)

The result fills from the bottom up: the first rider out is last, the next is second to last, and so on (2E3(e)). The last two ride for the win (2E3(f)). Laps don't count (2E3(g)).

A ruleset may allow more than two riders for a final sprint; they're placed in that sprint's order.

A rider who crashes or is pulled between sprints and can't rejoin is eliminated at that moment (2E4): click them out as you would at a bell, and they take the next place. Mark Did Not Finish only for a rider who quits the race. It places them the same way, with "Did not finish" beside the name on the sheet, but in a [Four-Race Omnium](multi-race-standings.md#the-four-kinds) a Did Not Finish is an abandon that puts the rider out of the omnium (2O3(d)), and a rider clicked out stays in. On the scoreboard the rider leaves the race's page and is listed at that place on the result.

If a rider went out and nobody clicked, click them out when you notice, then use the row's ⋯ (**Move Up**, **Move Down**, or **Move to Place**) to put them where they belong. Two riders out at one bell: click both out, then **Tie with the Rider Below** on the upper row or **Tie with the Rider Above** on the lower. Either records the one tie. **Undo** takes a move back.

## Sprint Final (USAC 2F) and Keirin Final (USAC 2H)

One heat, placed by the order across the line. (Tournaments and bracket scoring are not supported.)

## Points Race (USAC 2M)

Each rider's sprint points and lap points are added, and the total ranks the race. The last sprint is the finish, and every rider still in is placed in it.

The rulebook's default values are 5-3-2-1 per sprint, double points for the last sprint, and 20 points for a lap gained or lost (2M2(f)). A tie in a sprint gives both riders the place and its points, and the next place is skipped. That holds for the final sprint too: a dead heat for 1st there awards both riders first place's points, there is no 2nd, and riders level on points after it share 1st (2M2(f)(i)). No re-ride is entered.

Riders level on points are split by their places in the final sprint (2M2(g)); if neither placed there, they share the place. A lap is points only: a rider a lap down can win on sprints. A lap gained at a sprint scores both (2M3(d)).

A rider whose free laps after a mishap run into the last kilometer can't return (2M7). They're placed on the points and laps they held (2M8), and the sheet shows "Out of the finish (mishap)" beside the name. The [Madison](#madison-usac-2n) (2N6) and the [Tempo Race](#tempo-race-usac-2p) work the same way.

If the officials stop the race after 80 percent of its distance and let the results stand (2M6), use the ⋯ at the right end of the task line and pick **End Race Now, Result As-Is...**. The ⋯ is there from the start of a Points Race, Madison, or Tempo Race, and its items are grayed until a sprint is recorded (pointing at a grayed item says why). It asks before it records. The race is then complete on the sprints ridden: no sprint doubles, there is no final sprint, and riders level on points share the place. The task line and the results sheet say "Race ended after 2 sprints" (see [The PDF](results.md#the-pdf)). **Undo** reopens the race where it was.

If the Chief Referee shortens the race (1G4(b)), pick **Shorten Race...** from the same ⋯ and give the new number of sprints. It's grayed until a sprint is recorded and again once the final sprint begins. The race keeps going, and the last sprint under the new count is the final sprint, with double points and the tie-break. The task line turns to it at once, and riders already clicked in that sprint stay as the first places of the finish. The results sheet prints the sprints ridden and says "race shortened from 4 to 3 sprints". **Undo** takes the latest shortening back.

If fewer riders are placed than the sprint calls for, **Record Sprint** asks before it records. If the riders were clicked in the wrong order, use the card's ⋯ before **Record Sprint**. A card with a place offers **Move Up**, **Move Down**, and, with three or more places taken, **Move to Place**. When multiple riders are sharing a place, **Break Tie** splits the result. **Undo** takes a move back. A reopened sprint moves the same way, and **Record Sprint** records the moved order. **Cancel** leaves the sprint as it was.

The officials may take points or a lap from a rider (8D5(b): "loss of points or laps illegally gained"; 8D5(c) and 2N3(e) for a Madison relay). The card's ⋯ offers both, and so does the row's ⋯ once the result is complete. **Points Penalty...** shows the rider's penalty in points and sets it to the number the officials now say. A second ruling, a reversal, or a penalty on the wrong rider is one dialog each: type the new number, or 0 to take the penalty off.

**Lap Not Counted** takes back a lap gained as if it was never recorded, and its points with it. It is offered while a lap gained stands. The sheet shows "Lap not counted" beside the rider's name, so the ruling stays visible after the lap is gone.

A penalty shows in a Penalty column in the standings.

**Undo** takes back a penalty or a **Lap Not Counted**, one change at a time.

## Madison (USAC 2N)

A [Points Race](#points-race-usac-2m) for teams of two (2N1), scored per team: both riders share the team's place. A ruleset sets the Madison's sprint and lap points separately from the Points Race's.

A Madison stopped after 80 percent ends with **End Race Now, Result As-Is...**, as a Points Race does (2N5). A shortened Madison takes **Shorten Race...** the same way. Over two nights, the teams' totals or places add up in a Team Omnium (see [The four kinds](multi-race-standings.md#the-four-kinds)).

On the scoreboard, a Madison while it runs shows each team as a bar of its color with the team's name, laps, penalty, and total on it; the riders' names are on the start list and the results sheet. The decided result is the same table, stamped Provisional or Final.

## Tempo Race (USAC 2P)

A [Points Race](#points-race-usac-2m) where only the first rider across the line scores at each sprint, one point, with no double points for the final sprint (2P2). The final sprint's full order breaks ties on points. A lap is 20 points under the rulebook.

A stopped Tempo Race is restarted with the points it had, or rerun (2P5), so it has no **End Race Now, Result As-Is...**. A shortened Tempo Race takes **Shorten Race...** as a Points Race does, and finishes that much sooner.

## Chariot (Club)

A one-lap race from a standing start, with riders held at the line. The USA Cycling rulebook has no article for it; it's described by [Dick Lane Velodrome](https://dicklanevelodrome.com/types-of-events/), [Northbrook](https://www.northbrookcyclecommittee.org/race-format-descriptions), and [Burnaby](https://cbtl.ca/race-descriptions/). Placed by the order across the line.

## Unknown Distance (Club)

A club Scratch Race format where only the officials know the distance; the bell gives one lap to go. It's described by [Northbrook](https://www.northbrookcyclecommittee.org/race-format-descriptions), [San Diego Velodrome](https://www.sdvelodrome.com/_files/ugd/3f8e7c_f931699825aa46e89151c421f55fbc87.pdf), [Dick Lane Velodrome](https://dicklanevelodrome.com/types-of-events/), and [Burnaby](https://cbtl.ca/race-descriptions/). It's scored as a [Scratch Race](#scratch-race-usac-2c), laps included.

## Win-and-Out (Club)

At each bell, the first rider across the line on the next lap takes a place and leaves the track, for as many places as the race was set up with (**Places** in Add Race, see [The races](getting-started.md#the-races)). The riders still in then finish together. It's described by [San Diego Velodrome](https://www.sdvelodrome.com/_files/ugd/3f8e7c_f931699825aa46e89151c421f55fbc87.pdf), [Northbrook](https://www.northbrookcyclecommittee.org/race-format-descriptions), [Dick Lane Velodrome](https://dicklanevelodrome.com/types-of-events/), and [Burnaby](https://cbtl.ca/race-descriptions/).

The riders still in after the last place is called are placed behind the lap winners, in their finishing order. The ruleset sets the direction:

- Forward, the Danish race: the first bell lap wins 1st, the next 2nd, and so on.
- Reverse, the Belgian race: the first bell lap wins the last of the places, and the last bell lap decides 1st.

The officials name one rider per bell lap. A dead heat they declare shares the place and skips the next one, as in any other finish (1M6(a)): the next bell lap is for the next open place, so the race rings one bell fewer, and a dead heat for 1st is re-ridden (1M4(b)). A lap winner later marked Did Not Finish or Disqualified gives up the place, and the later places close up.

A wrong lap winner is fixed from the result's ⋯. **Move Up** and **Move Down** swap the winners of two laps, and **Disqualify** gives up the place.
