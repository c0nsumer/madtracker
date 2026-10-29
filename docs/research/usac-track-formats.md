# USAC track race formats: a scoring reference

This file documents the USA Cycling (USAC) track racing rules and the race formats that US velodromes run.
It focuses on what a scoring program must model.
The software does not do timing.
A human scorer enters placings, sprint results, eliminations, and lap gains as each race runs.

Companion files in this folder:

- `uci-track-formats.md` covers the UCI Part 3 text article by article.
- `usac-results-export.md` covers the USAC results CSV, including the `DNP` code.

## Sources and how to read this file

All sources were accessed on 2026-10-07.

### Primary sources

- **[USAC25]** USA Cycling Rulebook, 2025 edition. Chapter 1 is General Regulations. Chapter 2 is Track Racing. Chapter 7 is National Championships. Appendix A holds the track tables.
  - PDF: https://assets.usacycling.org/prod/documents/USACycling_RuleBook_8_2025.pdf
  - The cover reads "Version 7•2025" and the page footers read "07•25".
  - The rulebook index page lists this PDF as the current rulebook, dated August 2025: https://usacycling.org/resources-rules-fees-policies/rulebook
  - UNVERIFIED: a file named `USACycling_RuleBook_7_2025.pdf` also exists on the same server. This file assumes the two are the same text.
- **[UCI]** UCI Cycling Regulations, Part 3 Track Races, "Version on 01.09.2026".
  - PDF: https://assets.ctfassets.net/761l7gh5x5an/7IE4WjTvQLqeRF5aniDP34/886f3c73d9f0241465b71f9e2e0833d8/PART_3_E_-_As_of_01.09.2026.pdf
  - Index page: https://www.uci.org/regulations/3MyLDDrwJCJJ0BGGOFzOat

### Older USAC rulebooks (used to trace removed or renamed rules)

- **[USAC24]** 2024: https://assets.usacycling.org/prod/documents/USACycling_RuleBook_7_2024.pdf
- **[USAC23]** 2023: https://assets.usacycling.org/prod/documents/USACycling_RuleBook_3_2023.pdf
- **[USAC20]** 2020: https://assets.usacycling.org/prod/documents/2020-USAC-Rulebook.pdf
- **[USAC16]** 2016: https://assets.usacycling.org/prod/documents/2016-USAC-Rulebook.pdf
- **[USAC12]** 2012: https://assets.usacycling.org/prod/documents/2012-USAC-Rulebook.pdf
- **[USAC09]** 2009: https://www.usada.org/wp-content/uploads/2009-RdTrkCx_rulebook.pdf

### Velodrome and club sources (secondary)

- **[SD1]** San Diego Velodrome Association, "2021 FNR Race Book" (333.3 m track): https://www.sdvelodrome.com/_files/ugd/3f8e7c_f931699825aa46e89151c421f55fbc87.pdf
- **[SD2]** San Diego Velodrome, "Race Types" page: https://www.sdvelodrome.com/race-types
- **[NB]** Northbrook Cycle Committee (Ed Rudolph Velodrome, Northbrook, IL), "Race Format Descriptions": https://www.northbrookcyclecommittee.org/race-format-descriptions
- **[DL1]** Dick Lane Velodrome (East Point, GA), "Types of Events": https://www.dicklanevelodrome.com/?p=20
- **[DL2]** Dick Lane Velodrome, 2019 "Velodrome Cup" program: https://www.dicklanevelodrome.com/wp/wp-content/uploads/2019/08/19VeloCupPRSProgram_4pgs.pdf
- **[MM1]** Marymoor Velodrome (Redmond, WA), "JBMV Grand Prix 2023 Race Book": https://velodrome.org/wp-content/uploads/2023/06/JBMV_Grand_Prix_2023_Race_Book.pdf
- **[MM2]** Marymoor Velodrome, "What is Track Cycling?": https://velodrome.org/about-track-racing/
- **[IC]** Indy Cycloplex (Major Taylor Velodrome, Indianapolis), "Major Taylor Race League": https://indycycloplex.com/major-taylor-race-league
- **[CB]** Burnaby Velodrome Club track league (Canada, not US), "Race Descriptions": https://cbtl.ca/race-descriptions/

### Conventions

- "USAC 2M2(f)" means USAC rulebook section 2M2, item (f), in [USAC25] unless another edition is named.
- "UCI 3.2.118" means UCI Part 3 article 3.2.118 in [UCI].
- "UNVERIFIED:" marks anything not confirmed from a cited source. It also marks interpretations where the rule text is silent.
- "Derived:" marks a number computed from a rule, such as a lap count for a 166 m track. The rulebooks do not print these numbers.
- The task brief expected the track chapter to be "Chapter 3" with rules numbered 3A, 3B, and so on. In every USAC edition checked (2009 through 2025), track is Chapter 2 and its rules are numbered 2A, 2B, and so on. Road racing is Chapter 3.
- Project vocabulary from `CLAUDE.md` applies. An "event" is a day or night of racing. A "race" is one scored contest. USAC's own text uses "competition" for the meet and "event" for a race type (USAC 2B19).

### Velodrome lengths used in this file

- "A 166 m facility" below is one club track of that length. Its programs come from its published results.
- USAC tables use "166.66" m for this class of track and say "166.66m U.S. tracks" (USAC 2M2(b)).
- San Diego is 333.3 m [SD1].
- Marymoor is 400 m [MM2].
- Derived: on a 166.66 m track, 1 km is 6 laps and 1250 m is 7.5 laps.
- Derived: on a 250 m track, 1 km is 4 laps and 1250 m is 5 laps.

## Contents

1. [General track rules every format inherits](#general-track-rules-every-format-inherits)
2. Bunch races defined by USAC and UCI:
   [Scratch](#scratch-race), [Points](#points-race), [Tempo](#tempo-race), [Elimination](#elimination-race), [Madison](#madison), [Omnium](#omnium-international-style)
3. USAC-only or older USAC formats:
   [Miss-and-out](#miss-and-out-and-devil-take-the-hindmost), [Handicap and wheel race](#handicap-race-and-wheel-race), [Italian pursuit](#italian-pursuit)
4. Sprint and timed formats:
   [Match sprint](#match-sprint), [Keirin](#keirin), [Team sprint](#team-sprint), [Individual pursuit](#individual-pursuit), [Team pursuit](#team-pursuit), [Flying 200 m and flying lap](#flying-200-m-and-flying-lap), [Kilo and 500 m](#kilo-and-500-m-time-trial), [Tandem](#tandem-sprint)
5. Club formats not in either rulebook:
   [Unknown distance](#unknown-distance), [Win-and-out family](#win-and-out-family), [Snowball family](#snowball-family), [Point-a-lap](#point-a-lap), [Chariot](#chariot), [Longest lap and track-stand races](#longest-lap-and-track-stand-races), [Scratch variants](#scratch-variants-split-scratch-devils-scratch-win-and-in), [Elimination combos](#elimination-combos-antioquena-black-jack), [Australian pursuit](#australian-pursuit), [Novelty races](#novelty-races-cops-and-robbers), [Formats named in the brief but not found](#formats-named-in-the-brief-but-not-found)
6. [Categories and results conventions](#categories-and-results-conventions)
7. [Omnium and overall-for-the-day scoring](#omnium-and-overall-for-the-day-scoring)
8. [Local and club variants and where they came from](#local-and-club-variants-and-where-they-came-from)
9. [USAC versus UCI: differences the software must care about](#usac-versus-uci-differences-the-software-must-care-about)

## General track rules every format inherits

These rules apply to every massed-start race unless a format overrides them.

### Starts, bells, and finish judging

- A start or restart is signaled by a single gunshot, whistle, or waved flag (USAC 1L3).
- A double gunshot or double whistle stops or neutralizes the race (USAC 1L3).
- The bell and a lap card showing "1" announce the last lap (USAC 1M2).
- The finish is judged when the front tire first reaches the finish line plane (USAC 1M1).
- Bunch races start with a flying start after one neutralized lap (USAC 2B8, 2C3, 2M3).
- If the bell is rung on the wrong lap, the judges record the order at the end of that lap. The Chief Referee then decides whether those results stand or whether part of the race is rerun (USAC 1M3).

### Track limits

USAC 2B7 caps the number of riders on the track at once:

- 166.66 m: 16 riders, or 12 Madison teams.
- 200 m: 20 riders, or 15 teams.
- 250 m: 24 riders, or 18 teams.
- 333.33 m: 36 riders, or 20 teams.
- 400 m: 40 riders, or 20 teams.

If entries exceed the limit, the scratch, points, elimination, Madison, and omnium rules call for qualifying heats (USAC 2C2(b), 2E2(a), 2M2(a), 2N2(a), 2O2(a)).

### Neutralization and mishaps

- A recognized mishap is a legitimate fall, a puncture, or a broken essential part of the bike. Any other incident is an unrecognized mishap (USAC 1O; glossary "MISHAP").
- A crash that does not endanger other riders does not neutralize the race, except in the elimination race (USAC 2B5).
- If a crash is a hazard, the starter may neutralize the race. Riders ride slowly at the top of the track and keep their relative positions (USAC 2B5).
- A rider who has a mishap resumes at the point where the rider left the track (USAC 2B6).
- Scratch and points races allow free laps up to the distance nearest 1250 m (USAC 2C5(a), 2M7(a)).
- Riders may not return within the last kilometer (USAC 2C5(b), 2M7(b)).
- Derived: on a 166.66 m track, 7 laps (1166.7 m) and 8 laps (1333.3 m) are equally close to 1250 m. UNVERIFIED: which the commissaires pick. The software should let the scorer set the free-lap count per race.

### Dead heats

- If riders dead-heat for first place, they re-ride the final sprint over 1000 m or a shorter distance set by the Chief Referee (USAC 1M4(b)).
- A dead heat for any place other than first leaves the riders tied for that place (USAC 1M4(b)).
- In track races, riders who dead-heat for a prize place may re-ride, unless a format rule says otherwise (USAC 2B11).
- Software implication: every format needs (a) a tied placing and (b) a way to enter the result of a re-ride that breaks the tie.

### Warnings, relegation, and disqualification

- A warning applies to one race and also carries to the other races of the same competition (USAC 2B12(a), (c)).
- A second warning in the same race disqualifies the rider from that race and the rest of the competition (USAC 2B12(c)).
- Three warnings in a competition, or a third relegation, disqualify the rider for the rest of the competition (USAC 2B12(c)).
- A disqualification for dangerous or unsportsmanlike riding applies to the entire competition (USAC 2B12(d)).
- Relegation is a penalty that costs the rider position, points, or time, depending on the race type (glossary "RELEGATION").
- A rider who is disqualified after collecting prizes must return them (USAC 1K2(c)).
- Software implication: store warnings and relegations per rider per event (day), not per race. The software should flag a rider who reaches the automatic disqualification thresholds. The officials still make the call.

### Results tabulation

USAC 1M6 sets the default result codes:

- The Chief Judge places as many finishers as possible. If a group cannot be separated, it gets an equal placing (USAC 1M6(a)).
- A rider who does not take the start line is DNS (USAC 1M6(b)).
- A rider who withdraws by choice is DNF (USAC 1M6(c)).
- A rider who stops for a mishap, or is withdrawn by officials as out of contention, is generally DNF (USAC 1M6(d)).
- The Chief Referee may instead tell the Chief Judge to place withdrawn riders by their relative positions when they were withdrawn (USAC 1M6(d)).
- "DQ" and "DSQ" both mean disqualified (glossary).
- USAC rules do not define "DNP". The USAC results CSV accepts `DNP`. See `usac-results-export.md`.

### Protests and provisional results

- A protest about foul riding must reach the Chief Referee within 15 minutes after the protester finishes (USAC 1P1(a)).
- A protest about the results must reach the Chief Judge within 15 minutes after the results are announced (USAC 1P1(b)).
- Prizes wait until podium protests are settled and 15 minutes have passed since the announcement (USAC 1M7).
- Field-of-play decisions, such as relegation or disqualification, are not subject to a hearing (USAC 1P2(a)).
- Software implication: a race result needs a "provisional" state with the announcement time, and a "final" state.

### Restarts in standing-start events

- Each team or rider gets at most two starts per round. A restart is given only for a false start or a recognized mishap (USAC 2B20).
- A further false start or mishap means DNF in qualifying, relegation in the first round, and loss of the ride in a final (USAC 2B20(a) to (c)).

### Entering the wrong race, withdrawal, and non-competitors

- The rider is responsible for entering the proper class and category. A registrar's acceptance is no excuse (USAC 1H4(b)).
- A rider may not withdraw from one race and ride another until the first race is done, unless the Race Director agrees in writing (USAC 1H9).
- A rider may not be on the track during a race the rider did not enter, or after being told to withdraw (USAC 1N13).
- Software implication: the scorer must be able to move a participant from one race to another, remove a participant from a race, and mark a rider DQ, all with an audit entry.

## Scratch race

USAC 2C. UCI §11 (3.2.173 to 3.2.183). Some clubs call this a "Chase" race.

### On the track

- All riders start together and race a set distance (USAC 2C1).
- Half the riders line up on the rail and half in the sprinters lane. A flying start follows one neutralized lap (USAC 2C3).
- There are no intermediate sprints (glossary "SCRATCH RACE").
- The order across the line at the end of the final lap decides the result, taking laps gained and lost into account (USAC 2C5 "Finish").

### Scorer inputs

- Start list (bibs on the line).
- Each lap gain or lap loss, by bib, when the officials call it.
- Each rider pulled by the officials, by bib, with the lap on which the rider was pulled.
- Each DNF (mishap not returning, or withdrawal) and DQ, by bib.
- A mishap flag with free laps, so the scoreboard shows the rider as neutralized and not lapped.
- The finish order. The judges may place every rider or only some. The rest share an equal placing (USAC 1M6(a)).
- Relegations, applied after the finish order is entered.

### Ranking algorithm

1. Split riders into finishers and non-finishers.
2. Sort finishers by net laps (laps gained minus laps lost), highest first (USAC 2C4, 2C5).
3. Within the same net laps, sort by finish line order (USAC 2C5).
4. Apply relegations. A relegated rider moves to the position the officials name. UNVERIFIED: USAC does not define a default position for a scratch relegation. Usually it is "behind the rider fouled" or "last on the lap".
5. Riders pulled by the officials are DNF by default (USAC 1M6(d)). If the Chief Referee says to place them, rank them after the finishers, by their positions when withdrawn (USAC 1M6(d)). Derived: a rider pulled later ranks ahead of a rider pulled earlier.
6. DNF riders are "not placed" (USAC 2C4, 2C5(c)).
7. Tie-break: a dead heat for first is re-ridden. Any other dead heat stays tied (USAC 1M4(b)).

### Edge cases

- Lapped riders who are out of contention are normally taken off the track (USAC 2C4).
- If lapped riders stay on the track, they finish on the lap the leaders finish on. They are placed by laps down first, then by finish position (USAC 2C4).
- UCI differs: a rider overtaken by the main bunch must leave the track at once (UCI 3.2.177).
- A rider who cannot return before the last kilometer starts is left out of the final placings (USAC 2C5(b)).
- UCI differs: such a rider gets the next available ranking after the finishers (UCI 3.2.182).
- A rider who has a mishap and does not return is not placed (USAC 2C5(c)).
- Stoppage and restart in the same session: riders keep their laps gained or lost. The laps remaining stay as they were, with a minimum of 10 (USAC 2C6(a), (b)).
- If the race cannot restart in the same session, it is rerun from the start (USAC 2C6(d)).
- In a qualifying heat, an equal number of riders is eliminated from each heat, at least 2 per heat (USAC 2C2(b)).

### Typical configuration

- Elite men and women: 10 km. Junior men and women: 7.5 km (USAC 2C2(a)).
- Championship distances (USAC 7D4):
  - Men: 7.5 km at 17-18, 10 km for Elite and for 35-49, 7.5 km at 50-59, and 5 km at 60 and over.
  - Women: 7.5 km at 17-18, 10 km for Elite, and 5 km at 35 and over.
- Derived: 10 km is 60 laps on a 166.66 m track and 40 laps on a 250 m track.
- Club examples: San Diego (333 m) runs 4 km for its D group and 5 to 6 km for its C group [SD1]. Dick Lane runs 5-lap and 10-lap scratch races to seed a wheel race [DL2]. A 166 m facility runs Chase races of 10 to 50 laps (its published results).

## Points race

USAC 2M. UCI §7 (3.2.114 to 3.2.133).

### On the track

- Riders race a set distance with intermediate sprints at a fixed lap interval (USAC 2M1, 2M2).
- Riders also score by gaining a lap on the main bunch (USAC 2M2(f)(ii)).
- The bell before a sprint lap fixes who is the head of the race for that sprint (USAC 2M3(d)).

### Scorer inputs

- Race distance in laps and the sprint interval. The software computes the sprint laps.
- For each intermediate sprint: the top four, in order, with ties allowed.
- For the final sprint: the full order of every rider still in the race. This order is the tie-break (USAC 2M2(g), 2M8(b)).
- Each lap gain (+1) and lap loss (-1), by bib, with the lap number.
- If a lap gain happens at the moment of a sprint, the scorer enters both the lap gain and the sprint placing (USAC 2M3(d)).
- Withdrawals by the officials (USAC 2M3(g)), DNF, DQ, and mishaps with free laps.
- Points penalties or relegations, if the officials impose them.

### Ranking algorithm

1. Intermediate sprint points: 5, 3, 2, 1 for places 1 to 4 (USAC 2M2(f)).
2. Final sprint points (after the full distance): 10, 6, 4, 2 (USAC 2M2(f)).
3. Tied riders in a sprint get the same position and the same points. The next position is skipped. Example: two riders tie for first, both score 5, and nobody scores second (USAC 2M2(f)(i)).
4. Lap gained: +20. Lap lost: -20 (USAC 2M2(f)(ii), (iii)).
5. Total = sprint points + 20 x laps gained - 20 x laps lost. Totals may be negative.
6. Rank by total, highest first.
7. Tie-break: the better place in the final sprint wins (USAC 2M2(g), 2M8(b)).
8. Riders whose mishap kept them out under 2M7(b) keep their points and are ranked (USAC 2M8(a)).
9. Other riders who do not finish are not placed (USAC 2M8(a)).
10. UNVERIFIED: if tied riders have no final sprint place (for example, both kept points after a last-kilometer mishap), the rules give no further tie-break. Suggest a shared place.

USAC and UCI use the same points values, the same 20-point lap rule, and the same tie-break (UCI 3.2.118, 3.2.119).

### Edge cases

- Gaining a lap: a rider has lapped the bunch on reaching shelter behind it, within 5 m of its last rider (USAC 2M4(a)).
- The main bunch is the largest group. If groups are the same size, the leading group is the main bunch (USAC 2M4(b)).
- If no main bunch exists, the chief commissaire decides when a lap is gained (USAC 2M4(c)).
- A rider who has lost laps may score in a sprint only if the main bunch has caught that rider before the sprint lap starts (USAC 2M5(a)).
- Riders may win points no matter how many laps they have lost (USAC 2M5(a)).
- A rider who gains a lap and then drops off keeps it until the main group catches that rider (USAC 2M5(b)).
- Software implication: the scorer does not compute bunch membership. The scorer records the lap gains and losses the officials call.
- Riders one or more laps down may be withdrawn by the commissaires (USAC 2M3(g)).
- A rider must rejoin the group the rider was part of before the sprint lap starts, to score in that sprint after a mishap (USAC 2M7(c)).
- If the total laps do not divide by the sprint interval, the extra laps are ridden before the first sprint (USAC 2M2(e)).
- Restart in the same session: riders keep their points. The laps-to-go counter is reset to the lap right after the previous sprint. Example: previous sprint at 40 to go, stopped at 33 to go, restart at 39 to go (USAC 2M6(b)).
- If the race cannot restart in the same session (USAC 2M6(d)):

| Distance completed when stopped | Decision |
|---|---|
| Less than 40% | Complete rerun |
| 40% to 80% | Resume with points accumulated and lost |
| More than 80% | Results stand |

- If less than 80% of the race is done when the competition ends, there is no final classification (USAC 2M6(d)).
- Software implication: store the race as an ordered list of scorer actions. A restart is then one more action that resets the lap counter.

### Typical configuration

Sprint interval (USAC 2M2(b), (c)):

| Track | USAC | UCI 3.2.116 |
|---|---|---|
| 166.66 m | every 20 laps | every 10 laps |
| Under 333.33 m (200 m, 250 m) | every 10 laps | every 10 laps |
| 333.33 m | every 5 laps | every 8 laps |
| Over 333.33 m | every 5 laps | every 5 laps |

Finals from the USAC Standard Points Race Table (USAC Appendix A3), for 166.66 m and 250 m tracks:

| Group | 166.66 m | 250 m |
|---|---|---|
| Men Elite | 30 km, 180 laps, 9 sprints | 30 km, 120 laps, 12 sprints |
| Women Elite | 20 km, 120 laps, 6 sprints | 20 km, 80 laps, 8 sprints |
| Men Junior | 20 km, 120 laps, 6 sprints | 20 km, 80 laps, 8 sprints |
| Women Junior | 16 km, 100 laps, 5 sprints | 15 km, 60 laps, 6 sprints |
| Masters Men 35+ | 40 km, 240 laps, 12 sprints | 30 km, 120 laps, 12 sprints |
| Masters Men 45+ | 40 km, 240 laps, 12 sprints | 20 km, 80 laps, 8 sprints |
| Masters Men 60+ and Masters Women 45+ | 20 km, 120 laps, 6 sprints | 10 km, 40 laps, 4 sprints |
| Masters Women 35+ | 20 km, 120 laps, 6 sprints | 15 km, 60 laps, 6 sprints |

- The table is copied as printed. Some 166.66 m entries look inconsistent. For example, Masters Men 35+ and 45+ are longer than Men Elite. UNVERIFIED: whether these are errors.
- The rulebook is also internally inconsistent. USAC 7D11 lists championship points race distances (for example Men Elite 40 km, Women Elite 25 km). Appendix A3 lists Men Elite 30 km and Women Elite 20 km.
- The UCI table for a 166 m track lists Men Elite final as 30 km, 180 laps, 18 sprints (UCI 3.2.117).
- Club examples: San Diego (333 m) runs 4 to 5 km points races with 5-lap sprints for its D group, and 6 to 8 km with sprints every 2 km for its C group [SD1]. Dick Lane runs a 60-lap Cat A points race [DL2]. Dick Lane says sprints are every 5 or 10 laps [DL1].

## Tempo race

USAC 2P. UCI §18 (3.2.259 to 3.2.265). Older USAC editions called it the "International Tempo Race" (USAC20 2P).

### On the track

- A points race in which, after the first 4 laps, every lap is a sprint (USAC 2P2(b)).
- The bell rings after 4 laps to start the sprint laps (USAC 2P2(b)).

### Scorer inputs

- The first rider across the line on each sprint lap.
- Lap gains and losses, by bib.
- The full finish order on the final lap, for the tie-break.
- DNF, DQ, withdrawals.

### Ranking algorithm

1. Each sprint: 1 point to the first rider, including the final sprint (USAC 2P2(c)).
2. Lap gained: +20. Lap lost: -20 (USAC 2P2(d), (e)).
3. Rank by total points, highest first.
4. Tie-break: the points race rules apply (USAC 2P2(a)). So the final sprint place breaks ties (USAC 2M2(g)).

### Edge cases

- Variations are allowed if the race announcement states them (USAC 2P3).
- A tempo race inside an omnium must follow USAC 2P1 and 2P2 exactly (USAC 2P3).
- UCI has no clause allowing local variations.
- Restart in the same session: riders keep their points. Add 5 laps to the laps remaining. If 5 or fewer laps remained, restart with 11 to go (USAC 2P5(b)).
- After a restart, the first 4 laps again have no sprints (USAC 2P5(c)).
- If the race cannot restart in the same session, it is rerun (USAC 2P5(e)).

### Typical configuration

- UCI categories: Elite 10 km, Junior 7.5 km (USAC 2P1(a)).
- Non-UCI categories: the organizer chooses (USAC 2P1(b)).
- Derived: 10 km is 60 laps on a 166.66 m track, which is 56 sprints. On a 250 m track it is 40 laps and 36 sprints.
- UNVERIFIED: whether 166 m tracks sprint every lap or every second lap in practice.
- Club variants (not USAC):
  - San Diego "Tempo": every lap, 2 points to first and 1 to second. A lap gain is 4 points. Lapped riders are pulled and lose all points. Ties go to finishing order [SD1].
  - San Diego "International Tempo": 1 point per sprint after a neutral lap and 3 laps at speed. A lap gain is 4 points [SD1]. This lap-gain value differs from USAC 2P2(d) (20 points).
  - Northbrook "Tempo": every lap, the first two riders get 2 and 1 points. Riders with no points are placed by finishing order [NB].
  - Dick Lane "American / Super Tempo": 2 and 1 points each lap, then 3, 2, 1 on the final lap. Ties go to final-lap placing [DL1].
- Software implication: the tempo engine needs configurable per-lap points depth, final-lap points, lap-gain value, and a "lapped riders lose all points" switch.

## Elimination race

USAC 2E. UCI §14 (3.2.218 to 3.2.226).

### On the track

- After a neutralized lap, the last rider in each intermediate sprint is eliminated (USAC 2E1, 2E3(b)).
- The last two riders sprint for the win (USAC 2E3(f)).

### Scorer inputs

- Each elimination: bib, in order. More than one bib may go out at one sprint.
- "No elimination this sprint" (green flag), when the officials cannot decide in time (USAC 2E3(d)(iii)).
- Riders who abandon or are lapped between sprints. They are the riders eliminated at the next sprint (USAC 2E3(d)(i)).
- Mishap neutralizations, and riders who fail to rejoin.
- The final two-rider sprint result.

### Ranking algorithm

1. The last rider in each sprint goes out, judged on the back edge of the rear tire (USAC 2E3(d)).
2. Eliminated riders are placed in reverse order of elimination. The first out is last (USAC 2E3(e)).
3. The final two are placed by front wheel at the line (USAC 2E3(f)).
4. Lap gains do not count (USAC 2E3(g)).
5. Riders who did not qualify through heats share last place. Riders who did not finish a heat are DNF (USAC 2E2(b)).

### Edge cases

- The commissaires may eliminate a rider other than the last one, for example for riding on the blue band (USAC 2E3(d)(ii)).
- The decision must be made before the riders pass the back-straight pursuit line. If not, nobody is eliminated until the next sprint (USAC 2E3(d)(iii)).
- UNVERIFIED: whether the next sprint then removes one rider or two. The text does not say. Let the scorer enter any number.
- If two or more riders go out at the same sprint (for example a lapped rider plus the last rider), the rules give no order between them. UNVERIFIED: suggest a shared place unless the officials give an order. Older USAC text placed riders out together for a mishap "equally" (USAC20 2E5).
- An eliminated rider who stays on the track may be relegated with a warning or disqualified (USAC 2E3(d)(iv)).
- Mishap: the race is neutralized for the laps nearest 1250 m. If every rider is involved, it is neutralized for up to 3 minutes (USAC 2E4(a)).
- Riders who cannot rejoin when the race restarts are eliminated at that moment (USAC 2E4(a)(ii)).
- Once four or fewer riders remain, there is no neutralization. Riders who do not finish are eliminated at that moment (USAC 2E4(d)).
- The bell rings on the lap after a restart, to start a sprint lap (USAC 2E4(a)(ii)).

### Typical configuration

- Sprint every third lap on tracks under 200 m, every second lap on 200 m to 333.33 m tracks, and every lap on tracks of 333.33 m or more (USAC 2E3(c); UCI 3.2.222 is the same).
- On tracks under 333.33 m, a bell marks each lap before a sprint (USAC 2E3(c)(i)).
- Derived: on a 166.66 m track, a 16-rider field needs 14 elimination sprints plus the final sprint. At one sprint every 3 laps, that is about 42 laps plus the neutral lap and the final sprint distance.
- A 166 m facility runs eliminations with the bell every other lap, after 5 laps to settle, and gives the final two 2 laps to sprint (its published results). This differs from the USAC "every third lap" cadence.
- The USAC glossary entry "MISS-AND-OUT" still sets an interval of every two laps on shorter tracks for championships. This is older text and conflicts with USAC 2E3(c).

## Miss-and-out and devil take the hindmost

USAC 2E5 (2025). Older text in USAC20 2E1 to 2E6 and USAC12 2E. Not in UCI.

### On the track

- A non-championship elimination race (USAC 2E5).
- Riders may go out every lap, every other lap, or at another interval that the race announcement gives (USAC 2E5).
- It may be ridden to the last rider, or to a set number of survivors (USAC 2E5).
- With survivors, there may be a free lap and then a normal sprint judged on front wheels (USAC 2E5).
- "Devil take the hindmost" is an older name for the same race (USAC12 2E1; glossary index "devil take the hindmost").

### Scorer inputs

- Elimination interval (laps), and the number of survivors (1, 3, or another number).
- Free (no-pull) laps before the final sprint.
- Each elimination by bib, as for the elimination race.
- The final sprint order of the survivors.

### Ranking algorithm

1. Survivors are placed by the final sprint (front wheel) (USAC 2E5).
2. Eliminated riders are placed in reverse order of elimination, after the survivors (USAC 2E3(e) applies, since the race normally follows Elimination Race rules).
3. Lap gains do not matter (glossary "MISS-AND-OUT").

### Edge cases

- The officials must explain the format to all riders before the start (USAC 2E5). Store the format in the race setup and print it on the result.
- Older USAC rule (USAC20 2E5): riders with mishaps were eliminated and placed ahead of riders already eliminated. If several riders were involved, they were placed equally. The next sprint was postponed one or two laps. UNVERIFIED: whether officials still apply this at club level.
- Older USAC rule (USAC20 2E4): if an eliminated rider does not leave, the Chief Referee may call free laps until the rider leaves.

### Typical configuration

- Older USAC default (USAC20 2E1(a)): end with three riders, a neutral lap, then the bell and a three-up sprint.
- Northbrook: down to three riders, then a set number of no-pull laps, then the sprint [NB].
- San Diego: down to 3 to 5 riders, a no-pull lap, then the sprint [SD1].
- Dick Lane: last rider each lap, down to three riders, then a sprint [DL2].
- "Miss-and-out with a sprint every X laps" is simply this race with an interval of X. The interval is a race setting.

## Madison

USAC 2N. UCI §10.

### On the track

- Teams of two riders score points in sprints and by gaining laps (USAC 2N1).
- One rider races while the partner rides slowly above. They change by a hand touch or a hand sling (USAC 2N3(d)).
- The glossary still says "teams of two or three riders" (glossary "MADISON"). USAC 2N1 says teams of 2.

### Scorer inputs

- Team definitions for this race: team number and the two riders. Both riders wear the same number in different colors (USAC 2N2(f)).
- Sprint placings by team number. On a relay at the line, the front wheel of the teammate taking over counts (USAC 2N2(g)(ii)).
- Lap gains and losses by team.
- The full final sprint order by team.
- Team DNF, DQ, withdrawals, and mishaps.

### Ranking algorithm

Same as the points race, applied to teams:

1. Intermediate sprints: 5, 3, 2, 1. Final sprint: 10, 6, 4, 2 (USAC 2N2(g)).
2. Ties in a sprint share the position and points. The next position is skipped (USAC 2N2(g)(i)).
3. Lap gained: +20. Lap lost: -20 (USAC 2N2(g)(iv), (v)).
4. A lap gain at the moment of a sprint scores 20 plus the sprint points (USAC 2N3(h)).
5. Rank by total. Ties go to the final sprint place (USAC 2N2(h), 2N7(b)).

### Edge cases

- Lap gains and losses use the points race rules (USAC 2N4).
- If one rider has a mishap, the partner continues alone. No free laps are given (USAC 2N6(a)).
- If both riders have a mishap, the team gets free laps nearest 1250 m (USAC 2N6(b)).
- No return in the final kilometer. Such a team is placed by the laps and points it held at the mishap (USAC 2N6(c)).
- A relay without a touch may cost the team a lap (USAC 2N3(e)).
- A team that drops behind may not help a chasing team gain a lap, on pain of team disqualification (USAC 2N3(g)).
- Stoppage rules match the points race. The restart is a normal Madison start. Teams off the front or back are not given their gap back (USAC 2N5).
- USAC 2N2(a) and (b) refer to an "Appendix A5" for the Madison table. The 2025 appendix has no A5. The Madison table is A4 (USAC 2N2(d)).
- Older UCI rules ranked teams by laps first and points second. UNVERIFIED: the date of the change. The current UCI text gives 20 points per lap (UCI 3.2.162, text modified 14.10.16).

### Typical configuration

Sprint interval: every 10 laps on tracks under 333.33 m, every 20 laps on 166.66 m US tracks, and every 5 laps on tracks of 333.33 m or more (USAC 2N2(c)). UCI uses 10 laps under 333.33 m and 8 laps at 333.33 m.

Finals from the USAC Standard Madison Table (USAC Appendix A4), as printed:

| Group | 166.66 m | 250 m |
|---|---|---|
| Men Elite | 30 km, 180 laps, 9 sprints | 30 km, 120 laps, 12 sprints |
| Women Elite | 20 km, 120 laps, 6 sprints | 20 km, 80 laps, 8 sprints |
| Men Junior | 20 km, 120 laps, 6 sprints | 20 km, 80 laps, 8 sprints |
| Women Junior | 16 km, 100 laps, 5 sprints | 15 km, 60 laps, 6 sprints |
| Men Junior 13-14 | 13 km, 80 laps, 4 sprints | 20 km, 80 laps, 8 sprints |
| Women Junior 13-14 | 10 km, 60 laps, 3 sprints | 15 km, 60 laps, 8 sprints |
| Masters Men 35-44 | 20 km, 120 laps, 6 sprints | 30 km, 120 laps, 12 sprints |
| Masters Men 45-54 | 20 km, 120 laps, 6 sprints | 25 km, 100 laps, 10 sprints |
| Masters Women 35+ | 16 km, 100 laps, 5 sprints | 15 km, 60 laps, 6 sprints |

- Some entries do not fit the stated interval. For example, Women Junior 13-14 on 250 m lists 60 laps and 8 sprints. UNVERIFIED: whether this is a misprint.
- A Madison needs at least 5 eligible teams (6 for Elite) at a championship (USAC 7D12(a)).
- A 166 m facility runs 80-, 100-, and 120-lap Madisons with sprints every 20 laps (its published results).
- San Diego says Madison sprints are "typically every 6, 10, or 12 laps" [SD1].

## Omnium (international style)

USAC 2O. UCI §16 (3.2.247 to 3.2.252bis).
For club omniums and overall-for-the-day scoring, see [Omnium and overall-for-the-day scoring](#omnium-and-overall-for-the-day-scoring).

### On the track

Four races on one day, in this order (USAC 2O1):

1. Scratch race: Elite 10 km, Junior 7.5 km.
2. Tempo race: Elite 10 km, Junior 7.5 km.
3. Elimination race.
4. Points race: Men Elite 25 km, Women Elite and Men Junior 20 km, Women Junior 15 km.

### Scorer inputs

- The results of each of the four races, as for the stand-alone formats.
- Start order: the scratch race order is set by ranking or by the Chief Commissaire. Later races use the current omnium standings (USAC 2O2(d)).

### Ranking algorithm

1. For the first three races, award 40 points for 1st, 38 for 2nd, 36 for 3rd, and so on, down by 2 per place (USAC 2O3(a)).
2. Riders ranked 21st and below get 1 point each (USAC 2O3(a)(i)).
3. Riders carry these totals into the points race. Sprint points and lap gains and losses add to or subtract from the total (USAC 2O3(b)).
4. Highest total wins (USAC 2O3(b)(ii)).
5. Tie-break: the final sprint of the points race (USAC 2O3(g)).

### Edge cases

- A rider who fails to start one race may not ride later races. The rider is placed last as DNF (USAC 2O2(c)).
- A rider who abandons any race is placed after the last-placed rider as DNF (USAC 2O3(d)).
- In the scratch and tempo races, a rider who loses two laps is withdrawn, loses 40 omnium points, and gets the next available rank based on the riders still on the track (USAC 2O3(e)).
- If such a rider is not withdrawn, the rider is still classified as if withdrawn when losing the second lap (USAC 2O3(e)).
- In the scratch race, a rider who falls in the last kilometer, or cannot return in it, gets the next available ranking and points based on laps and riders remaining (USAC 2O3(f)). This is the opposite of the stand-alone scratch rule (USAC 2C5(b)).
- Stoppage (USAC 2O4): in the points race, USAC 2M6 applies. If less than 80% of the points race is done and it cannot restart, the standings after the elimination race are final. If the track becomes unusable before the elimination race is complete, there is no omnium classification.
- Derived: on a 166.66 m track, the field limit is 16, so the "21st and below" rule never applies.

### Typical configuration

- Omnium championships exist for Men and Women 17-18 and Elite (USAC 7D13).
- Derived: the four races total about 25 km plus the elimination for Men Elite. That is about 150 laps of scratch and tempo plus 150 laps of points race on a 166.66 m track.
- Northbrook's local version differs [NB]. A DNF costs at least 40 points, but the rider may start later races. A DNS also costs at least 40 points and the rider may continue. A rider pulled for being lapped loses 20 points per lap down. Northbrook says its rules "differ from UCI and national events".

## Handicap race and wheel race

USAC 2D. Not in UCI.

### On the track

- Stronger riders get a longer distance or a later start, to equalize the race (USAC 2D1).
- The handicapper sets each rider's mark, and the marks are announced before the start (USAC 2D2).
- After the start, it is run as a scratch race (USAC 2D5).
- "Wheel race" is the common name at Dick Lane and Marymoor. Dick Lane runs it over 3 or 4 laps from a standing start with holders [DL1], [DL2]. Marymoor runs it at its Grand Prix [MM1].
- T-Town runs the "Golden Wheel" as a handicap race. Source: Valley Preferred Cycling Center 2026 schedule announcement, https://thevelodrome.com/blogs/news/valley-preferred-cycling-center-announces-2026-racing-schedule-celebrating-50-years-of-track-cycling-excellence

### Scorer inputs

- Each rider's mark: a distance in meters, or a time delay in seconds. The scratch rider has mark 0.
- Finish order.
- DNF, DQ, relegations.

### Ranking algorithm

1. Rank by finish order, front wheel at the line (USAC 2D5).
2. The marks do not change the ranking. They only change the start.

### Edge cases

- Riders on the same mark start one behind the other or side by side (USAC 2D4).
- Holders may run with their riders a short way if this is stated before the start (USAC 2D4).
- On a steep track, riders start on the blue band (USAC 2D3).
- Qualifying: Dick Lane's 2019 program put the top 4 from each group's scratch race into the wheel race [DL2]. The software needs a way to build a race's start list from another race's result.

### Typical configuration

- 3 or 4 laps from a standing start [DL1].
- UNVERIFIED: typical marks on a 166 m track.

## Italian pursuit

USAC 2K1(a); glossary "ITALIAN PURSUIT". Not in UCI.

### On the track

- Teams of any size start at equal intervals around the track (USAC 2K1(a)).
- The first rider of each team leads for one or two laps, as announced, then pulls off and stops (USAC 2K1(a)).
- Each rider in turn does the same until one rider per team rides the last one or two laps (USAC 2K1(a)).
- The team whose last rider is farthest ahead, compared with the team's starting position, wins (USAC 2K1(a)).

### Scorer inputs

- Teams and their riders.
- The laps each rider leads (1 or 2).
- The finishing order as called by the officials, or each team's finish time if a timing system supplies it.

### Ranking algorithm

1. With two teams on opposite sides, the team that finishes first in time wins. UNVERIFIED: USAC gives no tie-break.
2. With more teams, rank by how far each last rider is ahead of the team's start point. Without timing, the officials call the order and the scorer enters it.

### Edge cases

- A rider who pulls off early or late. UNVERIFIED: no USAC penalty is defined.
- Reading Velodrome (UK) runs a variant that drops a rider every half lap and ranks by time. Source: https://www.readingvelodromeracing.co.uk/news/2015/program-for-13-july/ UNVERIFIED: US use of this variant.

### Typical configuration

- UNVERIFIED: no US velodrome source gave team sizes or distances.

## Match sprint

USAC 2F. UCI §3.

### On the track

- A series of races of 2 to 4 riders each (USAC 2F1).
- Rounds may be seeded by a flying-start 200 m time trial (USAC 2F1).
- Formats are championship (seeding tables in Appendix A1), round robin, and exhibition (USAC 2F1(a) to (c)).
- Elite and Junior national championships and qualifying events use the UCI sprint rules (USAC 2F1(d)).

### Scorer inputs

- Seeding: each rider's 200 m time, entered by hand if a timing system supplies it.
- The bracket or round robin pairing.
- For each heat and each ride: the winner (and order for 3-up or 4-up heats).
- Relegations, disqualifications, no-shows, restarts.
- Which rider led out each ride, since each rider leads one ride in a best-of-three (USAC 2F5(c)).

### Ranking algorithm

- Championship format: the bracket decides the order. Riders who lose in the same round are placed by the seeding tables (USAC 2F1(a), Appendix A1).
- Best of three: each rider leads one heat. A further draw decides who leads the third ride (USAC 2F5(c)).
- Round robin (USAC 2F3):
  1. The winner of each pairing gets 1 point.
  2. Rank by points.
  3. If a rider does not finish the whole series, all points won by or against that rider are cancelled.
  4. Tie-break: most points in matches among the tied riders. Then an extra sprint among the riders still tied.
- With five or fewer riders, the round robin may be ridden as repeated rounds to decide each pairing (USAC 2F3).
- Seeding time ties: by lot (USAC 2F1). This conflicts with USAC 2I6(c), which breaks 200 m ties on the last 100 m first. UNVERIFIED: which applies at club level.

### Edge cases

- A no-show loses the sprint. The other rider must appear on the line but need not ride (USAC 2F10).
- A dead heat is rerun with only the tied riders (USAC 2F12).
- Falls, mishaps, and fouls lead to restarts, relegation, or disqualification (USAC 2F6, 2F9, 2F11).
- In a 3-up or 4-up heat, a relegated rider is removed and the race is rerun with the rest (USAC 2F5(b), 2F11).
- If the tournament cannot finish (USAC 2F6(e)):
  - Stopped before the quarterfinals finish: no classification.
  - Stopped after the quarterfinals: riders in the semifinals share 4th.
  - Stopped after the semifinals: gold-final riders share 2nd, bronze-final riders share 4th.

### Typical configuration

- Distance: 3 laps on tracks under 333.33 m, 2 laps on tracks of 333.33 m or more (USAC 2F4).
- Derived: 3 laps on a 166.66 m track is 500 m. On a 250 m track it is 750 m.
- Rock Hill's 2017 spring series used a 200 m qualifying time to seed sprint events for the whole series. Source: https://visitrockhillsc.com/?p=2497 (search summary only). UNVERIFIED.

## Keirin

USAC 2H. UCI §8.

### On the track

- Riders draw start positions and ride behind a pacer, usually a derny (USAC 2H1, 2H2(a)).
- The pacer leaves the track, and the riders sprint for the finish (USAC 2H1).
- There may be qualifying rounds and repechages (USAC 2H1).

### Scorer inputs

- Heat composition and draw positions.
- Finish order for each heat.
- Relegations, disqualifications, restarts, and reruns without a rider at fault.
- Which riders advance (top N per heat), by round.

### Ranking algorithm

1. Each heat is ranked by finish order.
2. Riders advance by the round table. UCI-rule competitions use Appendix A2 (USAC 2H1).
3. The final order of the last round gives the top places. Earlier-round finishers are placed by the round they reached and their place in it. UNVERIFIED: USAC gives no default for placing non-finalists at club level.
4. UCI rule for non-finishers: a rider who does not finish a round (other than DNS or DSQ) is placed last in that heat (UCI 3.3.012 B).

### Edge cases

- A rider who passes the pacer's front wheel before the pacer leaves is disqualified, and the race is rerun (USAC 2H2(e)).
- Illegal riding behind the pacer: the race is stopped and rerun without the riders at fault (USAC 2H2(f)).
- A mishap in the first half lap restarts the race (USAC 2H2(c)).
- Software implication: a rerun replaces the heat result. Keep the voided heat in the audit trail.

### Typical configuration

- Distance closest to 1.5 km: 6 laps on 250 m, 5 on 333 m, 4 on 400 m (USAC 2H1).
- The pacer starts at 30 km/h and builds to 50 km/h by the time it leaves (USAC 2H2(d)).
- On 250 m tracks the pacer leaves after the pursuit line with 3 laps to go. On other tracks it leaves closest to 750 m from the finish (USAC 2H2(d)).
- Usually 6 or 7 riders per heat, never more than 9 (USAC 2H1).
- Derived: on a 166.66 m track, 1.5 km is 9 laps, and the pacer leaves about 4.5 laps from the finish.
- A 166 m facility runs a local version with an e-bike pacer and 6 riders over about 10 laps. The pacer leaves on lap 6 and riders sprint the last 4 laps (its published results).
- Dick Lane: heats of 5 to 8 riders. The pacer leaves with 1.5 laps to go [DL1].
- San Diego (333 m): 5 laps, 6 to 9 riders, pacer to about 31 mph, pacer leaves with 2.5 laps to go [SD1].

## Team sprint

USAC 2L. UCI §9.

### On the track

- Two teams of three start on opposite straights. Each rider leads one lap and pulls off. The third rider rides the last lap alone (USAC 2L1, 2L4).

### Scorer inputs

- Teams (up to 4 registered, 3 ride) for each round (USAC 2L2).
- Each team's time, entered by hand from the timing system.
- Changeover faults reported by the officials (USAC 2L4(g), (i)).
- Restarts, mishaps, DNS.

### Ranking algorithm

1. Qualifying: rank by time. The best four go to the finals (USAC 2L3(a)).
2. Finals: 1st and 2nd ride off, and 3rd and 4th ride off (USAC 2L3(b)).
3. The team whose rider crosses the line first wins (USAC 2L7, printed as "276").
4. Ties: best final-lap time, timed on the lead rider (USAC 2L8).
5. A faulty changeover relegates the team to last in that round (USAC 2L4(i)).

### Edge cases

- A team that fails to start a final is placed 2nd (gold final) or 4th (bronze final). If the reason is not accepted, the team is disqualified and the place stays empty (USAC 2L6(b)(i)).
- Stoppage table as for the team pursuit (USAC 2L5).

### Typical configuration

- 3 laps, 3 riders (USAC 2L1, 7D10).
- Derived: 3 laps on a 166.66 m track is 500 m.
- Collegiate co-ed team sprint: 6 laps, 2 to 6 riders with at least one woman, who leads at least 2 laps, one team on the track at a time (USAC 7I7(f)).

## Individual pursuit

USAC 2J. UCI §4.

### On the track

- Two riders start on opposite sides of the track. A rider wins by catching the other or by the faster time (USAC 2J1).

### Scorer inputs

- Pairings and start side.
- Times (entered by hand), or a "caught" flag and the lap of the catch.
- DNS, restarts, mishaps.

### Ranking algorithm

1. Qualifying: rank by time. The best 4 advance (USAC 2J2(a)).
2. A caught rider must finish the distance to get a time (USAC 2J2(a)(i)).
3. Finals: the two fastest ride for 1st and 2nd, the next two for 3rd and 4th (USAC 2J2(b)).
4. A catch ends a final (USAC 2J2(b)). A rider is caught when the other rider's chainset draws even (USAC 2J2(d)).
5. Ties: best final-lap time (USAC 2J7).

### Edge cases

- A rider who fails to start the gold final is placed 2nd. In the bronze final, 4th. If the reason is not accepted, the rider is disqualified and the place stays empty (USAC 2J6(c)).
- If the event cannot finish: no classification before qualifying ends, or the qualifying order after it (USAC 2J4).

### Typical configuration

- Championship distances (USAC 7D8):
  - Men: 3 km at 15-16, 17-18, and 35-49. 4 km for Elite. 2 km at 50 and over.
  - Women: 3 km at 15-16 and 17-18. 4 km for Elite. 2 km at 35 and over.
- Derived: 3 km is 18 laps on a 166.66 m track.

## Team pursuit

USAC 2K. UCI §5.

### On the track

- Two teams of 4 start on opposite sides of the track. A team wins by catching the other or by the faster time (USAC 2K1).
- The team's time is taken on the front wheel of its third rider (USAC 2K3(c)).

### Scorer inputs

- Teams (up to 6 registered, at least 4 to start) (USAC 2K2).
- Times entered by hand, or a catch.
- Mishaps, DNS, disqualifications.

### Ranking algorithm

1. Qualifying by time. The best four advance (USAC 2K3(a)).
2. Finals as for the individual pursuit (USAC 2K3(b)).
3. A team is caught when the other team, riding with 3 together, comes within 1 m (USAC 2K3(d)).
4. Ties: the faster lap times nearest the finish (USAC 2K8).

### Edge cases

- DNS in a final: 2nd or 4th place, or disqualification (USAC 2K7(c)).
- Pushing between teammates: disqualification in qualifying, loss in a final (USAC 2K4(f)).

### Typical configuration

- 4 km, except 3 km for Men Masters 55+ and Women Masters 35+ (USAC 2K1, 7D9).
- Collegiate teams may be 3 or 4 riders (USAC 7I7(e)).

## Flying 200 m and flying lap

USAC 2I (time trials), 2F1 (sprint seeding), 2Q (flying lap). UCI §2, §17.

### On the track

- Flying 200 m: the rider winds up over several laps and is timed over the last 200 m (USAC 2F1, 2F1(e)).
- Flying lap: a flying start from the finish line, timed over one lap (USAC 2Q1).

### Scorer inputs

- Start order.
- Each rider's time, entered by hand.
- Restarts for a recognized mishap.

### Ranking algorithm

1. Rank by time, fastest first.
2. Flying 200 m ties: best last 100 m. If still tied, or not measurable, draw lots (USAC 2I6(c)). Sprint seeding ties: lots (USAC 2F1).
3. Flying lap ties: best last 200 m (USAC 2Q2(d)).

### Edge cases

- Derived: on a 166.66 m track, a "lap" is shorter than 200 m. So the flying lap tie-break (last 200 m) is longer than the timed distance. UNVERIFIED: how officials apply it on short tracks.
- A rider gets one new start for a recognized mishap (UCI 3.2.258).

### Typical configuration

- Flying lap total distance including wind-up: 3.5 laps on tracks of 250 m or shorter, 3 on 285 m, 2.5 on 333.33 m, 2 on 400 m (USAC 2Q2(c)).

## Kilo and 500 m time trial

USAC 2I. UCI §6.

### On the track

- A standing-start ride against the clock over a fixed distance (USAC 2I1).

### Scorer inputs

- Start order and pairs, if two riders start at once (USAC 2I3(b)).
- Times entered by hand.
- Restarts: one charged restart at most (USAC 2I4(c)).

### Ranking algorithm

1. Rank by time.
2. Ties: best final-lap time (USAC 2I6(a), (b)).

### Edge cases

- If a session is interrupted, all riders must ride in a later session, and earlier times are discarded (USAC 2I1, 2I7).
- A second mishap in qualifying is DNF. In a final, the rider is considered beaten (USAC 2I4(b)).

### Typical configuration

- Championship distances (USAC 7D7): Men 15-16, 17-18, Elite, and 35-49 ride 1000 m. Men 50+ ride 500 m. Women 15-16, 17-18, and Elite ride 1000 m. Women 35+ ride 500 m.
- San Diego runs a 1 km time trial with an 88-inch gear limit for its D group and no gear limit for its C group [SD1].

## Tandem sprint

USAC 2G. UCI §12.

### On the track

- A match sprint for tandems (USAC 2G1).
- The start is from the pursuit line in the finishing straight (USAC 2G1(a)).

### Scorer inputs

- Tandem teams (two riders, one result).
- As for the match sprint.

### Ranking algorithm

- As for the match sprint (USAC 2G1).

### Edge cases

- At most four tandems per heat. On tracks of 333 m or less, at most three (USAC 2G1(b)).
- "Mixed" tandem events require one male and one female rider (glossary "MIXED").

### Typical configuration

- Qualifying: one lap, flying start (USAC 2G1(c)).
- Race: 3 laps (USAC 2G1(d)).

## Unknown distance

Club format. Not in USAC 2025 or UCI. A 166 m facility runs it most nights (its published results).

### On the track

- A scratch race in which the riders do not know the distance [NB], [SD1].
- The bell rings with one lap to go [NB], [SD1].
- Dick Lane: "Only the official knows which lap is the last" [DL1].

### Scorer inputs

- The secret distance, set before the start, or the lap on which the official rings the bell.
- Then the same inputs as the scratch race.

### Ranking algorithm

- As for the scratch race.

### Edge cases

- Software implication: the audience scoreboard must not show laps to go, or total laps, for this race. It may show laps completed.
- The operator screen may show the secret distance to the scorer.
- The officials may change the distance during the race. Record the actual lap of the bell.

### Typical configuration

- UNVERIFIED: no US source gave typical distances. The SD race book schedules it without a distance [SD1].

## Win-and-out family

Club formats. Not in USAC 2025 or UCI.

### On the track

- **Win-and-out.** After a set number of laps, the bell rings. The first rider across the line on the next lap takes 1st and leaves the track. The first rider on the following lap takes 2nd, and so on [SD1], [DL2].
  - Dick Lane: the official rings the bell every lap during this phase [DL2].
  - Burnaby (Canada): a five-lap race, lap 1 winner takes 1st, lap 2 winner takes 2nd [CB].
- **Danish win-and-out** (Northbrook name). After a set number of no-pull laps, each lap winner takes the next place, starting with 1st. This runs for a set number of places, usually 5. If places remain unfilled, the rest are placed in order [NB].
- **Belgian win-and-out** (also "reverse win-and-out"). The places are filled in reverse. The first lap winner takes the lowest prize place, and the last lap winner takes 1st.
  - Northbrook: starts at 5th. Remaining riders are placed 6th and down by finish order [NB].
  - San Diego: starts at 3rd [SD1].
  - Burnaby: five laps, 5th place first, behind a pacer on the apron [CB].

### Scorer inputs

- The number of places to fill (N) and the direction (forward or reverse).
- The lap on which the first place is decided (first bell).
- For each place lap: the bib of the lap winner.
- The finish order of the remaining riders on the final lap.
- DNF, DQ.

### Ranking algorithm

1. Forward: the k-th lap winner takes place k.
2. Reverse (Belgian): the k-th lap winner takes place N + 1 - k.
3. Riders without a place are ranked N + 1 and down by their order on the final lap [NB].
4. UNVERIFIED: how to place riders still on the track if the race ends early. Suggest the order on the last lap ridden.

### Edge cases

- A winner who does not leave the track. UNVERIFIED: no published penalty. The scorer should be able to void the winner's later crossings.
- The commissaire may shorten the race, for example to fill the last places on the final lap. A UK league describes this: https://www.scrl.co.uk/raceformat (UNVERIFIED for US use).
- A tie at the line for a lap win. UNVERIFIED: suggest the officials' call or a shared place.

### Typical configuration

- Dick Lane: 7-lap win-and-out for its women, masters, and B/C groups [DL2].
- San Diego (333 m): 3 to 4 km win-and-out, and 4 to 5 km Belgian win-and-out, with the first bell at the race distance [SD1].
- Northbrook: usually 5 places [NB].

## Snowball family

Club formats. Not in USAC 2025 or UCI.

### On the track

- A mass-start race over a set distance with a sprint on every lap (or on set laps). The points grow (or shrink) as the race goes on.
- **Snowball, leader only** (San Diego, Dick Lane). Only the first rider on each lap scores. Lap 1 is worth 1 point, lap 2 is worth 2, and so on [SD1], [DL1].
- **Snowball, variation 1** (Northbrook). Lap 1: 1 point to the winner. Lap 2: 2 and 1. Each lap adds one more place and one more point. From lap 5 on, the top five score 5, 4, 3, 2, 1 [NB].
- **Snowball, variation 2** (Northbrook). A point-a-lap where only the first rider's points grow on later laps [NB].
- **Reverse snowball** (Dick Lane). Only the first rider scores. The first sprint gives the most points, and each sprint gives one less, down to 1 point on the last lap [DL2].
- **Avalanche** (San Diego). A points race where sprint values grow each sprint: 5-3-2-1, then 10-6-4-2, then 15-9-6-3, and so on [SD1].
- **Avalanche** (Burnaby, Canada). The first sprint pays 1 point to the winner and the last pays 5, four places deep [CB].

### Scorer inputs

- The points schedule (see the configuration section below).
- For each sprint: the scoring places in order.
- The final-lap finish order, for tie-breaks and for riders with no points.
- Lap gains and losses only if the variant counts them. UNVERIFIED: no snowball source mentions lap gains.

### Ranking algorithm

1. Sum each rider's points.
2. Rank by total, highest first.
3. Ties: order of finish [SD1], or final sprint placing [DL1].
4. Riders with no points: placed by finishing order, after the riders with points [NB].

### Edge cases

- A tie at the line on a points lap. UNVERIFIED: suggest the points race rule (shared position, shared points, next position skipped, USAC 2M2(f)(i)).
- Dick Lane notes that the final lap of a snowball does not pay three places deep [DL1].

### Typical configuration

- San Diego (333 m): 3 to 4 km snowball [SD1].
- Dick Lane: 10-lap reverse snowball [DL2]. Derived: 10 laps paying 10, 9, 8, ... 1.
- Software implication: model the snowball family as a "per-lap points schedule": a table of (lap number, points by place). The variants above are presets.

## Point-a-lap

Club format. Not in USAC 2025 or UCI.

### On the track

- A race over a set distance with a sprint for 1 point on every lap [NB], [CB].
- Dick Lane: only the lap leader scores 1 point per lap, except the final lap, which pays 3, 2, 1 [DL1].

### Scorer inputs

- The first rider on each lap.
- The final-lap order (top 3 at Dick Lane, and the full order for tie-breaks).

### Ranking algorithm

1. Sum points. Rank highest first.
2. Riders with no points are placed by finishing order behind riders who scored [NB].
3. UNVERIFIED: tie-break among riders with equal points. Suggest final-lap order, as for the tempo race.

### Edge cases

- Same as tempo. This is essentially a tempo race with configurable points.

### Typical configuration

- UNVERIFIED: no US source gave distances.

## Chariot

Club format. Not in USAC 2025 or UCI. USAC20 listed a "1 Lap Chariot" in the 11-12 and 13-14 junior national omniums (USAC20, Chapter 7). The 2025 junior omnium table no longer includes it (USAC 7C3(a)).

### On the track

- A one-lap race from a standing start, with riders held at the line by holders. First across the line wins [DL1], [DL2], [NB].
- Dick Lane: up to seven riders per heat [DL1].
- A 166 m facility runs it for its Young Junior group (its published results).

### Scorer inputs

- Heat lists. Finish order per heat.
- Which riders advance to the final (Dick Lane 2019: top 2 per heat) [DL2].

### Ranking algorithm

- Finish order. With heats, the final gives the top places.
- UNVERIFIED: placing of riders eliminated in heats. Suggest tied places by the position they reached in the heat.

### Edge cases

- False starts and restarts follow standing-start practice (USAC 2B20). UNVERIFIED: that clubs apply 2B20 to chariots.

### Typical configuration

- One lap. Derived: 166 m on a 166 m track, 250 m on a 250 m track.

## Longest lap and track-stand races

Club formats. Not in USAC 2025 or UCI.

### On the track

- **San Diego Slog (longest lap)**: riders stage on the back straight and roll off at the start. Nobody may cross the start line until an unannounced timed bell rings. The bell starts a one-lap sprint [SD1].
  - Before the bell, riders may not roll backward, touch another rider, touch the rail, leave the track surface, or put a foot down [SD1].
- **Marymoor Crawl**: a track stand followed by a one-lap sprint [MM2] (search summary of Marymoor pages). UNVERIFIED: exact rules.

### Scorer inputs

- Riders who break a track-stand rule, in order.
- The sprint finish order.

### Ranking algorithm

1. Riders who finish the sprint are ranked by finish order.
2. UNVERIFIED: riders who break the rules before the bell are eliminated. Suggest reverse order of elimination, as for an elimination race.

### Edge cases

- The bell time is secret. The scoreboard must not show it.

### Typical configuration

- San Diego runs it as an "ALL" categories race [SD1].

## Scratch variants: split scratch, devil's scratch, win-and-in

Club formats. Not in USAC 2025 or UCI. The brief calls these "scratch with a twist".

### On the track

- **Split scratch** (Dick Lane). A scratch race with one mid-race sprint for 5, 3, 2, 1 and a final sprint for 9, 7, 5, 3, 2, 1. Highest total wins. Ties go to the final sprint [DL1], [DL2].
- **Devil's scratch** (Northbrook). Half the field is eliminated as in an elimination race. The survivors then race a scratch race, usually over 3 to 5 laps [NB].
- **Win-and-in** (Dick Lane). A 15-lap race with a sprint every 3 laps. Each sprint winner qualifies for a 3-lap final. If a rider wins more than one sprint, the sprint at the end of the 15 laps decides the remaining places [DL1].
- **Winners** (Burnaby, Canada). A sprint every three laps. A sprint winner stays in the pack but does not contest later sprints. After the sprint with three laps to go, riders who have not won a sprint leave. The four winners contest the final sprint [CB].
- **Triple sprint** (San Diego) appears on the schedule without a description [SD1]. UNVERIFIED: its rules.

### Scorer inputs

- Split scratch: two sprint results (top 4, then top 6).
- Devil's scratch: eliminations, then the scratch finish order.
- Win-and-in or Winners: each qualifying sprint winner, then the final finish order.

### Ranking algorithm

- Split scratch: sum points, highest first. Ties go to the final sprint. UNVERIFIED: riders with no points placed by final sprint order.
- Devil's scratch: survivors by scratch finish order, then eliminated riders in reverse order of elimination.
- Win-and-in: finalists by final order. UNVERIFIED: non-finalists. Suggest the order of the last qualifying sprint.

### Edge cases

- Devil's scratch: "half the field" with an odd field. UNVERIFIED: round up or down. Make it a setting.

### Typical configuration

- Dick Lane: 10-lap split scratch for masters, B/C, and women [DL2].

## Elimination combos: Antioquena, Black Jack

Club formats. Not in USAC 2025 or UCI. The brief calls these "elimination then points" combos.

### On the track

- **Antioquena** (San Diego, from Burnaby Velodrome): a point-a-lap elimination. The first rider each lap gets 1 point and the last rider is eliminated. With five riders left, they race a 2 km scratch with 5, 3, and 2 points at the finish. Most points wins [SD1].
- **Black Jack points race** (San Diego): after a neutral lap, points are given every other lap. A drawn playing card sets the value (ace 1, 2 to 10 face value, jack to king 10). A rider who passes 21 points is eliminated. Once a rider reaches exactly 21, the remaining places go by current totals. If the maximum laps are reached, the highest total wins. Ties go to order of finish [SD1].

### Scorer inputs

- Antioquena: per lap, the first rider (1 point) and the eliminated rider. Then the 2 km scratch finish.
- Black Jack: per sprint, the card value drawn and the sprint placings. UNVERIFIED: how many places score per sprint.

### Ranking algorithm

- Antioquena: sum points, highest first. UNVERIFIED: whether eliminated riders keep their points and are ranked by points or by elimination order. Suggest points first, then elimination order as the tie-break.
- Black Jack: the first rider to reach exactly 21 wins. Others rank by total, with "bust" riders after them in reverse order of busting. UNVERIFIED: the exact placing of bust riders.

### Typical configuration

- Antioquena final: 2 km scratch. Derived: 12 laps on a 166.66 m track.

## Australian pursuit

Not in USAC 2025 or UCI. No US velodrome source was found. The sources below are from Canada and the UK.

### On the track

- Riders start at equal intervals around the track. A caught rider is eliminated. The race may end early when two riders are left, opposite each other [CB].
- A UK league describes the same individual version: the last rider uncaught wins. Source: https://www.scrl.co.uk/blog-4/week-9-the-pursuit
- Reading Velodrome (UK) uses the name for a team race between two teams from opposite pursuit lines. Source: https://www.readingvelodromeracing.co.uk/news/2015/program-for-13-july/

### Scorer inputs

- Start positions.
- Each catch: the caught rider's bib, in order.

### Ranking algorithm

1. The last rider uncaught wins.
2. Caught riders rank in reverse order of being caught.
3. UNVERIFIED: if the race ends with two or more riders uncaught, rank them by the officials' call or by distance gained.

### Typical configuration

- UNVERIFIED.

## Novelty races: Cops and Robbers

Club format (San Diego). Not in USAC 2025 or UCI.

- A 5-lap race. One rider, the "robber", starts with a flying start. The pack, the "cops", start when the robber reaches the pursuit line or the home straight start line [SD1].
- The robber keeps a cash prize if not caught. Each cop who passes the robber's front wheel wins a smaller cash prize and is out of the race [SD1].
- Software implication: this is a prize event, not a placing event. Record "caught by" bibs in order. UNVERIFIED: whether any placing is produced.

## Formats named in the brief but not found

These names were in the research brief. No USAC text and no US velodrome source was found for them. Each is UNVERIFIED.

- **Course des primes.** One search result used it as another name for the tempo race ("one point for the first rider over the lap"). UNVERIFIED: any US use. Model it as a tempo or point-a-lap preset.
- **Team points race.** UNVERIFIED: no rule found. The USAC rulebook uses "Team Points" only for collegiate penalties (USAC 8G4) and collegiate team scoring. Suggest modeling as a points race with a team-total classification.
- **Madison TT.** UNVERIFIED: no rule found. Suggest modeling as a timed team event (team of 2, one time).
- **"Unknown distance + points".** UNVERIFIED: no rule found. Suggest modeling as a points race whose scoreboard hides laps to go, with the final sprint set when the official rings the bell.
- **"Win-and-out with points".** UNVERIFIED: no rule found.
- **"Devil" as a separate format.** Sources use "devil" as another name for the miss-and-out or elimination race (USAC12 2E1; [CB]). Dick Lane describes riders who "play the devil" by sitting at the back [DL1].

## Categories and results conventions

### Class and category are different things in USAC

- **Class** is a designation based on age, eg: junior, U23, Elite, or master (glossary "CLASS").
- **Category** is a designation based on rider ability (glossary "CATEGORY").
- A race may combine classes and categories. The categories in one race must be the same for all age groups in it (USAC 1H10(j)).

### Age classes

Racing age is the event year less the rider's birth year (USAC 1C1). Put another way, it is the rider's age on December 31 of the current year (glossary "RACING AGE"). Cyclo-cross differs, but track does not.

| Racing age | Class | Source |
|---|---|---|
| 8 and under | Youth | USAC 1C1(a). Youth races are for ages 6 to 8 (USAC 1H10(f)). |
| 9 to 18 | Junior | USAC 1C1(b) |
| 19 to 22 | U23 | USAC 1C1(c) |
| 23 to 29 | Elite | USAC 1C1(d) |
| 30 and over | Master | USAC 1C1(e) |

- A master may choose Elite status (USAC 1C1(e)).
- Riders on UCI teams are always Elite, even over 30 (USAC 1C1(e)).
- Riders 30 and over are also Elite in a discipline if they rode certain UCI championships or World Cups that year (glossary "ELITE RIDER").
- The glossary also defines an "AMATEUR CLASS" (riders 19 to 29 and older who are not on UCI teams).
- UNVERIFIED: the USAC results CSV uses "Senior" as a Race Class value. The rulebook does not define "Senior". See `usac-results-export.md`.

### Junior and masters age groups used in track racing

- Junior track gear limits use these groups: 9-12, 13-14, 15-16, 17-18 (USAC 1I4(a)).
- Junior national omniums use 11-12, 13-14, and 15-16 (USAC 7C3(a)).
- Masters national championships use five-year brackets starting at 30 or 35, depending on the discipline. Some events combine age groups and split the awards afterward (USAC 7C2).
- Track championship distances use wider bands, for example Men 35-49, 50-59, 60+ (USAC 7D4).
- In a bracketed masters race (for example 35-39), riders must ride their own bracket. In an open-ended race (for example 35+), riders may enter any one they are old enough for (USAC 7B6(a)).
- Masters may race their own age group or younger, but not U23-only or Junior-only races (USAC 1H10(c)).
- Juniors and U23 riders may race their own age group or an older one, but not masters races (USAC 1H10(d)).

### Ability categories

- Beginners are "Novice" (USAC 1D1(a)).
- Experienced road, track, and cyclo-cross riders are Category 4, 3, 2, or 1, for men and women. Lower numbers mean higher ability (USAC 1D1(b)(i)).
- "Professional" is a road, track, or cyclo-cross rider on a UCI team in that discipline (USAC 1D2(a)).
- The Novice name replaced the old entry category in the 2020 rulebook (USAC20 1D1 explanatory note). UNVERIFIED: that every older "Cat 5" maps to Novice on current licenses. Many club schedules still say "Cat 4/5".
- Categories are relative to riders of the same gender, regardless of age (USAC 1D3(b)).
- Women may enter men's races for which they are eligible by age and category. They may also enter men's races up to one category lower than their own. Category 1 women may enter men's races up to two categories lower (USAC 1H10(h)).
- Master women of category 1 or 2 may enter men's masters races for riders up to 10 years older. Category 3 or 4 master women may enter men's masters races for riders up to 20 years older (USAC 1H10(i)).
- One-day licenses are only for the lowest category, Novice (USAC 1A3(c)(i)).

### Category restrictions at track nationals

For bunch and sprint events (USAC 7D3(a), (b)):

- Men: Cat 1/2 for Elite, Cat 1/2/3 at 17-18 and at 35-54, and no restriction at 11-16 or 55 and over.
- Women: Cat 1/2/3 for Elite and at 35-54, and no restriction at all other ages.

Time trial events have no category restriction (USAC 7D3(c)).

### Junior gear limits

Junior track gear limits by age (USAC 1I4(a)), measured by roll-out, the distance covered in one pedal revolution (USAC 1I4(c)):

| Age | Maximum roll-out |
|---|---|
| 17-18 | Unrestricted |
| 15-16 | 6.93 m |
| 13-14 | 6.45 m |
| 9-12 | 6.05 m |

- A junior racing in an older age group may use that race's gear limit, if any (USAC 1I4(b)).
- Riders 14 and under ride massed-start bicycles with wheels that have no covers and at least 16 spokes (USAC 1I5).
- How this affects scoring: a junior in an open race is still a junior by class. The gear limit belongs to the race, not to the rider's result. The software does not need to model gearing, but the race setup could note a gear limit.
- Clubs set their own gear limits. San Diego suggests 48x15 for its D group and 50x15 for its C group [SD1].

### What "Class" probably means on a rider list

- In USAC terms, Class is the age class: Youth, Junior, U23, Elite, Master (glossary "CLASS").
- In the USAC results CSV, "Race Class" is a property of the race, not of the rider. See `usac-results-export.md`.
- At a club, "Class" often means the local ability group. A 166 m facility uses groups such as "SemiPro A" and "Junior B" that are not USAC categories (its published results).
- UNVERIFIED: which meaning a facility's rider list uses. It varies by club, so a facility has to say.
- Software implication: store USAC category, USAC age class (derived from birth year), and the local race group as three separate fields. Derive racing age from the birth year and the event date.

### How placings are recorded for non-finishers

| Situation | USAC rule | Code |
|---|---|---|
| Did not take the start line | USAC 1M6(b) | DNS |
| Withdrew by choice | USAC 1M6(c) | DNF |
| Mishap, or pulled by officials | USAC 1M6(d) | DNF, unless the Chief Referee says to place the rider |
| Pulled and placed by officials | USAC 1M6(d) | A place, by position when pulled |
| Disqualified | USAC 1K2, 2B12; glossary | DQ or DSQ |
| Relegated | glossary "RELEGATION" | A place (moved down) |
| Group that cannot be separated | USAC 1M6(a) | Equal placing |
| Not placed for another reason | Not in the rulebook | DNP (CSV only; see `usac-results-export.md`) |

- UCI differs. It separates DNF (recognized mishap, or withdrawn by commissaires or doctor) from ABD (unrecognized mishap or by choice) (UCI 3.3.012).
- UCI also ranks some non-finishers in bunch events. Riders in the final who are withdrawn or have a mishap get a shared next-available rank after the finishers (UCI 3.3.012 A).
- USAC has no ABD code. Software implication: store the reason internally (mishap, withdrawn, by choice, pulled) and map it to the USAC code on export.

## Omnium and overall-for-the-day scoring

### What USAC says

- USAC defines "Omnium Scoring" as the cumulative result of a set of races, with points for each place counting toward an overall standing (USAC 2B19(e)).
- The 2025 rulebook does not give a points-per-place table for this.
- The glossary says the official race announcement must give the scoring scheme (glossary "OMNIUM"). Riders do not have to ride every race unless the announcement says so.
- The glossary still says rule 2O1 gives the default omnium scheme for track events. In 2025, 2O1 is the international omnium. This is older text.
- Older editions (USAC24 2P1, USAC20 2O1) say the same: points per race, scheme in the announcement.

### Tie-break for omnium scoring (USAC 2B19(e))

1. Most first places. If still tied, most second places, and so on.
2. If still tied, the highest place in the last race. If neither tied rider placed in the last race, use the race nearest the last race in which at least one tied rider placed.

This tie-break dates back at least to 2009 (USAC09 2O2).

### Historical USAC points table

- Older rulebooks set 7-5-3-2-1 for places 1 to 5 in national championship omniums, except international-style omniums (USAC09 2O1, USAC12 2O1, USAC16 2O1).
- The 2020 rulebook dropped this table (USAC20 2O1).

### Junior national omnium (low-points)

USAC 7C3 sets a low-points omnium for juniors under 17:

- Events (USAC 7C3(a)):
  - Ages 11-12: a 3 km scratch, then a 6 km points race, then a 500 m time trial, then a 1 km scratch.
  - Ages 13-14: a 4 km scratch, then a 10 km points race, then a 500 m time trial, then a 2 km scratch.
  - Ages 15-16: a 5 km scratch, then an elimination, then a 2 km scratch, then a 15 km points race.

- Points per race: 1st gets 1 point, 2nd gets 2, and so on. Lowest total wins (USAC 7C3(d), (f)).
- A rider who chooses not to start a race gets last place points plus one. "Last place" is based on the number of confirmed omnium entrants or 24, whichever is smaller (USAC 7C3(d)).
- Riders who do not advance from heats share the next place after the qualifiers (USAC 7C3(c)).
- The standings include every rider who entered at least one race (USAC 7C3(f)).
- Ties: most firsts, then most seconds, and so on. Then the best place in Race IV (USAC 7C3(g)).

### Club and race-night tables found

| Facility | Table | Notes | Source |
|---|---|---|---|
| San Diego | 5-3-2-1 | Riders must finish all scheduled races that night to be eligible for omnium podium and points. | [SD2] |
| Marymoor Grand Prix | 15-12-10-8-6-5-4-3-2-1 (individual); 8-6-5-4-3-3-2-2-1-1 (2-person team) | DNS or DNF scores zero. Ties go to most firsts, then most seconds, and so on. Separate sprint and endurance omniums. | [MM1] |
| Marymoor rider of the year | 10, 9, 8, 7, 6, and so on | Grand Prix races count toward the season standings. | [MM1] |
| Marymoor Friday nights | Season omnium points | Table not published online. Season points were doubled for winners on the final night in 2013. | [MM2]; https://velodrome.org/?p=269 (search summary) |
| Major Taylor Race League | Points for places 1 to 36 | Every non-disqualified starter also gets bonus points equal to the field size. Riders not in a heat's main final score nothing. The lowest 6 races are dropped. International omnium night counts 2.5 times. | [IC] |
| Dick Lane | Omnium-style nights | Points accumulate across the night's races. Point table not published. | [DL1] |
| Northbrook | International omnium, local rules | 40-38-36 for the first three races, then the points race. See the omnium section. | [NB] |

- UNVERIFIED: a 10-8-6-4-2 table. No US source was found.
- UNVERIFIED: a 5-4-3-2-1 table. A search summary attributed it to San Diego, but San Diego's own page shows 5-3-2-1 [SD2].
- Software implication: the overall-for-the-day needs (a) a configurable points-per-place table per race, (b) per-race multipliers, (c) rules for DNS, DNF, and DQ (zero, last plus one, or excluded), (d) a "must finish all races" switch, (e) a high-points or low-points direction, (f) dropped-race counts for series, and (g) the USAC 2B19(e) tie-break.

## Local and club variants and where they came from

### Where the formats come from

- **UCI championship formats.** Scratch, points, tempo, elimination, Madison, omnium, sprint, keirin, team sprint, pursuits, time trials, and flying lap. USAC has aligned its text with the UCI over recent editions. The 2025 change log says several sections were "reorganized" and distances updated "to match the UCI regulations" (USAC25 change summary, sections 2C to 2Q).
- **Older USAC rules.** Miss-and-out and handicap racing stay in USAC as non-championship formats (USAC 2E5, 2D). Italian pursuit stays as a definition (USAC 2K1(a)). The 7-5-3-2-1 omnium table and the "International-style omnium" names are older USAC text.
- **Junior development.** The chariot appeared in junior national omniums (USAC20 Chapter 7). Clubs still run it for their youngest riders [DL1].
- **Australian racing.** The wheel race (handicap) is described as "extremely popular in Australia" [DL2].
- **Canadian club racing.** San Diego credits the Antioquena to Burnaby Velodrome in Vancouver [SD1].
- **US club inventions.** The Black Jack points race, Cops and Robbers, and the San Diego Slog appear only at San Diego [SD1]. The split scratch and win-and-in appear only at Dick Lane [DL1]. The Marymoor Crawl appears only at Marymoor [MM2].

### Variants that change scoring

| Format | Variant | Change | Source |
|---|---|---|---|
| Tempo | San Diego | 2-1 points per lap; lap gain 4 points; lapped riders pulled with all points lost | [SD1] |
| Tempo | Northbrook | 2-1 points per lap; non-scorers placed by finish | [NB] |
| Tempo | Dick Lane "American / Super Tempo" | 2-1 per lap; 3-2-1 on the final lap | [DL1] |
| Elimination | A 166 m facility | Every other lap on a 166 m track; USAC says every third lap | Published results; USAC 2E3(c) |
| Miss-and-out | Northbrook, Dick Lane | Down to 3 riders, then a sprint | [NB], [DL2] |
| Miss-and-out | San Diego | Down to 3 to 5 riders | [SD1] |
| Omnium | Northbrook | DNF and DNS cost 40 points but riders may continue; lapped riders lose 20 points per lap | [NB] |
| Points race | San Diego, Dick Lane | Sprint every 5 laps or every 2 km, not the USAC interval | [SD1], [DL1] |
| Madison | A 166 m facility | 80 to 120 laps, sprint every 20 laps on 166 m (matches USAC 2N2(c)) | Published results |
| Keirin | A 166 m facility, San Diego, Dick Lane | E-bike or motorcycle pacer, different laps and pull-off points | Published results; [SD1]; [DL1] |
| Omnium | Marymoor Grand Prix | 15-12-10 table, DNS or DNF zero | [MM1] |

### Local categories

- San Diego uses local C and D groups with its own eligibility rules. A USAC category "does not bypass these eligibility requirements" [SD1].
- Dick Lane uses A, B/C, Masters, and Women groups [DL2].
- Marymoor's Friday nights use Cat 1/2 Men, Cat 3 Men, Cat 1/2/3/4 Women, and Juniors [MM2].
- A 166 m facility uses Pro, SemiPro A/B/C, and junior groups (its published results).
- Software implication: the race group is a free-text label per race. It is not the rider's USAC category.

### Track lengths and why they matter

- USAC adjusts sprint intervals for 166.66 m tracks (every 20 laps for points and Madison) but not for elimination or tempo (USAC 2M2(b), 2N2(c), 2E3(c), 2P2(b)).
- On short tracks, lap gains happen often. The scorer needs a fast lap gain and lap loss entry.
- On short tracks, "laps nearest 1250 m" and "laps nearest 1.5 km" need rounding rules. Make free laps and keirin laps race settings.

## USAC versus UCI: differences the software must care about

| Topic | USAC | UCI | Software impact |
|---|---|---|---|
| Points and Madison sprint interval on 166 m | Every 20 laps (USAC 2M2(b), 2N2(c)) | Every 10 laps (UCI 3.2.116) | Sprint interval is a per-race setting with a USAC default by track length. |
| Points and Madison sprint interval on 333.33 m | Every 5 laps (USAC 2M2(c)) | Every 8 laps (UCI 3.2.116, as of 01.09.26) | Same. |
| Points race distance tables | Appendix A3 (for example 166.66 m Men Elite 180 laps, 9 sprints) | 3.2.117 (166 m Men Elite 180 laps, 18 sprints) | Presets per rulebook. |
| Scratch: lapped riders | "Normally removed", but if not removed they are placed by laps down (USAC 2C4) | Must leave the track at once (UCI 3.2.177) | Support lapped riders who stay in and finish. |
| Scratch: no return in last km | Not placed (USAC 2C5(b)) | Next available rank after finishers (UCI 3.2.182) | Rule switch by rulebook. |
| Result codes | DNS, DNF, DQ; DNP in CSV only (USAC 1M6) | DNS, DNF, ABD, DSQ with ranked groups (UCI 3.3.012) | Store the reason, map on export. |
| Omnium: DNS in one race | Placed last as DNF (USAC 2O2(c)) | Recorded per 3.3.012 (UCI 3.2.251bis) | Same outcome, different code wording. |
| Tempo variations | Allowed if announced, except in an omnium (USAC 2P3) | No such clause | Tempo points must be configurable. |
| Which rules apply | USAC rules for USAC races; UCI rules for 17-18, U23, and Elite nationals and some qualifiers (USAC 1K1(b)), and for Elite and Junior sprint nationals (USAC 2F1(d)) | UCI | A per-race "rule set" choice is enough. Club racing is USAC. |
| Formats only in USAC | Handicap (2D), miss-and-out (2E5), Italian pursuit (2K1(a)), round-robin sprints (2F3), omnium scoring for a set of races (2B19(e)), junior low-points omnium (7C3), collegiate co-ed team sprint (7I7(f)) | Not defined | These need their own engines or presets. |
| Same in both | Points values 5-3-2-1 and 10-6-4-2, 20 points per lap, final sprint tie-break, elimination cadence, omnium 40-38-36 scoring, tempo 1 point per lap, flying lap distances | | One engine serves both. |

### Formats the UCI book does not cover

- From USAC: handicap race, miss-and-out, Italian pursuit, round-robin sprint, and multi-race omnium scoring (points per place with the most-wins tie-break).
- From US clubs only: unknown distance, win-and-out (forward, Danish, Belgian, reverse), win-and-in, snowball (leader-only, expanding, reverse), avalanche, point-a-lap, chariot, longest lap or track-stand races (Slog, Crawl), split scratch, devil's scratch, Antioquena, Black Jack, American or Super tempo, Cops and Robbers, and wheel race (a handicap race by another name).
- Not found anywhere in US sources: course des primes, team points race, Madison TT, "unknown distance + points", and "win-and-out with points". All are UNVERIFIED.
