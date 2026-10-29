# UCI track race formats: a scoring reference

This file lists every track race format in UCI Regulations Part 3 (Track Races).
It focuses on what a scoring program must model.
It also covers some common non-UCI formats, which are marked as not from the UCI text.

## Sources and how to read this file

All sources were accessed on 2026-10-07.

- **Primary source.** UCI Cycling Regulations, Part 3 Track Races, consolidated "Version on 01.09.2026".
  - PDF: https://assets.ctfassets.net/761l7gh5x5an/7IE4WjTvQLqeRF5aniDP34/886f3c73d9f0241465b71f9e2e0833d8/PART_3_E_-_As_of_01.09.2026.pdf
  - Index page: https://www.uci.org/regulations/3MyLDDrwJCJJ0BGGOFzOat
  - The index page lists this PDF as the Part III rules in force.
- **Upcoming UCI amendments.** The UCI index page lists one future amendment for Part 3, in force on 01.01.2028.
  - PDF: https://assets.ctfassets.net/761l7gh5x5an/7sVY0lFLys4gA22Dr5DOl2/749a0e3ee33f47f9a10d0f46cdb09bdb/Part_3_Track_Regulations_amendments_01012028.pdf
  - It changes only article 3.8.003 (calendar class criteria). It does not change any scoring rule.
- **Secondary source.** USA Cycling Rulebook, Version 7, 2025, Chapter 2 Track Racing.
  - PDF: https://assets.usacycling.org/prod/documents/USACycling_RuleBook_7_2025.pdf
  - This file cites it as "USAC 2X1" (section numbers). It is used for formats that the UCI does not define, and to show where USAC differs from the UCI.
- **Secondary source, low confidence.** Canyon blog, "Understanding track cycling events" (used only for Win-and-out): https://www.canyon.com/en-de/blog-content/road-cycling-news/best-track-cycling-teams/b16052024.html

Conventions in this file:

- Article numbers such as "3.2.118" refer to UCI Part 3. Rule text is paraphrased from the 01.09.2026 consolidated PDF.
- "UNVERIFIED:" marks anything not confirmed from the UCI regulation text. This includes rules taken from USAC or other secondary sources, and interpretations where the UCI text is silent or ambiguous.
- "Derived:" marks a number computed from a rule, not printed in the regulations.
- In UCI text, "event" means a race type (Points Race, Keirin, and so on), and "competition" means the whole meet (3.1.011bis). This project's vocabulary differs. Here, an "event" is a day or night of racing and a "race" is one scored contest. This file uses the project's terms in its own prose.

## Contents

- [Rules that apply to many formats](#rules-that-apply-to-many-formats)
- [200 metres Time Trial (sprint qualifying)](#200-metres-time-trial-sprint-qualifying)
- [Sprint](#sprint)
- [Tandem sprint](#tandem-sprint)
- [Keirin](#keirin)
- [Individual Pursuit](#individual-pursuit)
- [Team Pursuit](#team-pursuit)
- [Kilometre and 500 m Time Trial](#kilometre-and-500-m-time-trial)
- [Team Sprint](#team-sprint)
- [Flying Lap](#flying-lap)
- [Points Race](#points-race)
- [Scratch Race](#scratch-race)
- [Elimination Race](#elimination-race)
- [Tempo Race](#tempo-race)
- [Madison](#madison)
- [Omnium](#omnium)
- [Motor-Pacing (stayer races)](#motor-pacing-stayer-races)
- [Six-Day Races](#six-day-races)
- [Formats not in UCI Part 3](#formats-not-in-uci-part-3)
- [Masters distances](#masters-distances)
- [Scoring rules most likely to be implemented wrong](#scoring-rules-most-likely-to-be-implemented-wrong)

---

## Rules that apply to many formats

These general rules affect every bunch race. A scoring program needs them as shared building blocks.

### Bunch events

Article 3.1.011 defines the "bunch events": Points Race, Madison, Scratch Race, Elimination Race, Omnium, and Tempo Race.
A judge-referee is required for the sprint, the keirin, and all bunch events (3.2.011).

### Track limits

The number of riders on the track at once may not exceed these limits (3.1.009):

| Track length | Riders | Madison teams |
|---|---|---|
| 166 m | 16 | 12 |
| 200 m | 20 | 15 |
| 250 m | 24 | 18 |
| 333.33 m | 36 | 20 |

If more riders enter than the limit, the race needs qualifying heats.
In every bunch race with heats, each heat must eliminate the same number of the riders who started the race, and that number is at least 2 per heat (3.2.115, 3.2.157, 3.2.175, 3.2.219, 3.2.247bis).

### Bell, head of the race, and lap counter

- A bell marks the start of each sprint lap, including the last lap (3.2.017bis).
- The bell rings when the head of the race crosses the finish line. It rings again for any rider or group who can also score in that sprint.
- Points are awarded, or the race ends, the next time the head of the race crosses the finish line.
- The president of the commissaires' panel decides who the head of the race is.
- After the start, the lap counter shows the remaining distance. This holds even when the distance actually raced differs from the distance in the regulations (3.2.017ter). The scorer should therefore follow the lap counter, not a precomputed distance.

### Gaining and losing laps

Article 3.2.017quater: a rider or team has gained a lap once it catches the rear of the largest racing bunch on the track. It has lost a lap once that bunch catches it.
The president of the commissaires' panel decides which bunch is the largest.

UNVERIFIED: USAC adds detail that the UCI text does not have (USAC 2M4, 2M5):

- A lap is gained when the gap to the rear of the main bunch is less than 5 m.
- If two groups have the same size, the leading group is the main bunch.
- A rider who gains a lap and drops back keeps the lap until the main group catches that rider.

The program should not try to detect lap gains. The scorer records each lap-gain or lap-loss event when an official calls it.

### Neutralization after a mishap

Article 3.2.020bis applies to bunch races unless a specific rule says otherwise:

- A rider with a recognized mishap gets a neutralization equal to the number of laps nearest 1250 m (5 laps on a 250 m track).
- Beyond 1250 m, the neutralized rider begins to lose laps until back in position.
- Neutralized riders cannot rejoin once the last kilometre has started.
- If the last kilometre starts during the neutralization and the rider cannot return, the neutralized rider or team is placed in the final classification according to the points and laps it had before the mishap.

Recognized mishaps are a legitimate fall, a puncture, and a broken essential part of the bicycle (3.2.021). All other incidents are unrecognized mishaps.

Derived: the 1250 m neutralization is 5 laps on 250 m, 6 laps on 200 m (1200 m), 4 laps on 285.714 m (1143 m) or 333.33 m (1333 m), and 3 laps on 400 m (1200 m). The rule says "closest to", so the program should compute it from track length.

### Restarts in standing-start races

Article 3.2.021ter applies to standing-start races (pursuits, kilometre, team sprint):

- A rider or team gets at most two starts per round.
- A second false start or second recognized mishap has these results:
  - In the qualifying round, the rider or team is eliminated (DNF).
  - In the first round, the rider or team is relegated.
  - In the finals, the rider or team loses the final.
- If a rider stops after an unrecognized mishap, the rider is DNF in qualifying, or relegated in later rounds.

### Result marks and how non-finishers are ranked

Article 3.3.012 defines four result marks:

- **DNS**, Did Not Start.
- **DNF**, Did Not Finish. The causes are a recognized mishap, being withdrawn by the commissaires, or being withdrawn by the race doctor.
- **ABD**, Abandon. The causes are an unrecognized mishap, or the rider deciding to stop.
- **DSQ**, Disqualified.

Note: DNF and ABD are different. A rider pulled by the commissaires is DNF, not ABD. This changes the rider's rank.

Article 3.3.012 A ranks the final of a bunch race in groups, in this order:

1. Finishers, ranked by the rules of the race.
2. Riders withdrawn by the commissaires or with a mishap (DNF). They share one tied rank, the next position after group 1.
3. Riders who abandoned (ABD).
   - If heats were held, they share the last available position in the race.
   - If no heats were held, they get no rank and no UCI points.
4. Riders who qualified through heats but did not start the final (DNS). They share the next rank after group 3.
5. Riders disqualified in the final (DSQ). They get no rank.
6. Riders who finished a heat but did not qualify. They share the next rank after group 4.
7. Riders who did not finish a heat. They get no rank. They are listed in the order DNF, ABD, DNS, DSQ.

Several formats override group 2 with their own rule. Examples are the Scratch Race final-kilometre rule (3.2.182) and the Omnium two-laps-down rule (3.2.251bis). Each format section below notes its overrides.

Articles 3.3.012 B to G give similar group rules for Keirin, Sprint, Kilometre, Team Pursuit, Individual Pursuit, and Team Sprint. Those rules are summarized in each format's section.

### Warnings, relegations, and disqualification

Article 3.10.003 sets limits that apply across a whole meet:

- A warning given in one race carries over to the other races in the same competition.
- A second warning to a rider in the same event disqualifies that rider from the event and from the rest of the competition.
- A rider who gets 3 warnings in a competition, or is relegated for the third time, is disqualified from the rest of the competition.
- In the Madison, a warning goes to both the rider and the team. A team with two warnings within the same event is disqualified from that event.
- A rider disqualified for dangerous or unsportsmanlike behavior is disqualified for the entire competition.

The program should therefore keep warnings and relegations per rider across all races of a meet. It should alert the scorer when a rider reaches a limit.

Also, a rider who qualifies for the next round must ride it, unless prevented by circumstances beyond their control. Otherwise the rider is disqualified from the event and from the remainder of the competition (3.2.004).

### Seeding

Article 3.2.021bis sets the seeding order for most competitions:

- Sprint, Keirin, and Kilometre use the UCI Individual Ranking (Sprint).
- Elimination, Omnium, Scratch, Points Race, and Individual Pursuit use the UCI Individual Ranking (Endurance).
- Madison, Team Pursuit, and Team Sprint use the UCI Nation Rankings for that race type.
- Unranked riders go last, in random order.
- If a bunch race has heats, the results of those heats seed the later rounds.

For local racing, the program should accept a manual seed order.

### Interrupted races

Each format has a table of what happens if a race cannot be finished before the end of the competition. The tables were added on 01.01.25. They are listed in each section. The program should support the outcomes "no result", "rerun", "resume with points kept", and "result stands as is".

---

## 200 metres Time Trial (sprint qualifying)

Articles 3.2.022 to 3.2.028.

### On the track

- Each rider rides alone against the clock with a flying start. Only the last 200 m are timed (3.2.022).
- Riders start in the order the commissaires set (3.2.023).
- The next rider enters the track when the previous rider triggers the timing (3.2.024).
- The run-up plus timed distance depends on track length (3.2.025):
  - 250 m or smaller: 3.5 laps.
  - 285.714 m: 3 laps.
  - 333.33 m: 2.5 laps.
  - 400 m or longer: 2 laps.

### Scorer inputs

- Rider order.
- Time for the 200 m, to the thousandth of a second (3.2.015).
- Optional: time for the last 100 m, used only for ties.
- DNS, DNF, DSQ.
- A restart after a recognized mishap. Only one restart per rider is allowed (3.2.028).

This app has no timing hardware. The scorer must type times from the timing system or a manual watch.

### Ranking algorithm

1. Sort by 200 m time, fastest first.
2. Tie: in a dead heat, the tied riders are ranked by their times over the last 100 m (3.2.027).
3. If the last-100 m time is missing or still tied, draw lots (3.2.027).

Riders who do not finish are grouped DNF, then DNS, then DSQ. They do not progress to the sprint (3.3.012 C).

### Edge cases

- A tie needs a lot-draw input from the scorer.
- The result seeds the sprint tournament and ranks the sprint's early-round losers. Store it with the sprint, not as a separate race.

UNVERIFIED: USAC 2F1 breaks seeding ties by drawing lots directly. It does not mention the last-100 m rule.

### Typical configuration

- Track length sets the run-up laps.
- The number of riders who qualify for the sprint is 28 at World Cups and World Championships, and 24 at the Olympic Games (3.2.033, 3.2.050). Other competitions may qualify 16 or 8 (3.2.033).

---

## Sprint

Articles 3.2.029 to 3.2.050, and 3.3.012 C.

### On the track

- A sprint heat is a race between 2 and 4 riders over 2 or 3 laps (3.2.029).
- Heats are 3 laps on tracks shorter than 333.33 m and 2 laps on tracks of 333.33 m or more (3.2.035).
- Start position is drawn by lot. Rider 1 starts on the inside (3.2.037).
- In a best-of-three match, the riders swap positions for the second heat. A fresh draw decides the third heat (3.2.037).
- The inside rider must lead at least at walking pace to the pursuit line on the opposite side (3.2.039).
- Each heat allows at most two standstills of at most 30 seconds (3.2.039bis).
- If a rider drops out of a two-up heat, the opponent rolls to the start line and is declared the winner. The opponent need not ride the distance (3.2.036).

### Tournament structure

The minimum sprint event (3.2.031) has:

- 8 riders.
- A flying-start 200 m time trial.
- Quarter-finals, "straight" (one heat each).
- Semi-finals, best of three heats.
- A final for 3rd and 4th, and a final for 1st and 2nd, each best of three heats.

The World Cup and World Championships table (3.2.050), with 28 riders:

| Round | Matches | Pairing | Winners | Losers |
|---|---|---|---|---|
| 1/16 finals | 12 | Q1 to Q4 skip this round. N5 v N28, N6 v N27, ... N16 v N17 | 5A to 16A | Ranked 17 to 28 by 200 m TT time |
| 1/8 finals | 8 | 1A v 16A, 2A v 15A, ... 8A v 9A | 1B to 8B | Ranked 9 to 16 by 200 m TT time |
| 1/4 finals | 4 | 1B v 8B, 2B v 7B, 3B v 6B, 4B v 5B. Best of three | 1C to 4C | Ranked 5 to 8 by 200 m TT time |
| 1/2 finals | 2 | 1C v 4C, 2C v 3C. Best of three | Gold final | Bronze final |
| Finals | 2 | Best of three each | 1st, 3rd | 2nd, 4th |

In the 1/16 table, the four best qualifiers become 1A to 4A without racing. The 1/16 and 1/8 rounds are single heats. Rounds marked as 2 heats, with a third if required, are best of three.

For other competitions, the same format can run with fewer riders, using the 3.2.050 table with either 16 or 8 qualifiers (3.2.033).

The Olympic Games use a different table with 24 riders and repechages (3.2.050, second table):

- 1/32 finals: 12 matches, N1 v N24 through N12 v N13. Winners go to the 1/16 finals. Losers go to repechages.
- Repechages: 4 three-rider heats. Only each heat winner advances. Others are ranked by 200 m TT time.
- 1/16 finals: 8 matches. Losers go to a second repechage of 4 two-rider heats.
- 1/8 finals: 6 matches. Losers go to a third repechage of 2 three-rider heats.
- 1/4 finals: 4 matches, best of three. Losers race for places 5 to 8.
- 1/2 finals and finals: best of three.

### Scorer inputs

- The 200 m TT result, which builds the bracket.
- For each heat: the riders, the draw (who starts inside), the winner, and in 3 or 4-up heats the full finish order.
- Relegations and their reason.
- Per heat: DNS, DNF, DSQ.
- Per match (best of three): which heats each rider won, and whether a decider is needed.

### Ranking algorithm

- A match winner advances. A best-of-three match ends when one rider has won two heats.
- A relegated rider loses the heat. In a 3 or 4-up heat, the race is rerun at once without that rider (3.2.039bis, 3.2.047).
- Losers in rounds before the semi-finals are ranked by their 200 m TT time within the band of places for that round (3.2.050). Example: the 1/8 final losers take places 9 to 16 in order of their qualifying times.
- Semi-final losers ride the bronze final. Its winner is 3rd and its loser is 4th.
- Gold final winner is 1st. Loser is 2nd.

Non-finishers (3.3.012 C):

- A rider who starts a heat but does not finish (DNF) loses that heat. The rider is ranked as if beaten normally.
- A rider who does not start a heat (DNS) loses that heat. In a best-of-three round, a DNS loses the whole round.
- A DSQ rider gets no rank. That rider's place stays empty. Other riders do not move up into it.

### Edge cases

- **Restarts.** Many stoppages lead to a rerun with the rider not at fault choosing position (3.2.048). The program needs a "rerun this heat" action that keeps the heat number and records the reason.
- **Fall not caused by a fault.** The commissaires decide whether to rerun the heat or to keep the positions at the time of the fall as final (3.2.048 item 1).
- **Dead heat in a match.** UNVERIFIED: the UCI sprint section has no dead-heat rule for a match heat. USAC 2F12 says the race is rerun, with only the tied riders taking part.
- **Interrupted tournament** (3.2.048bis):
  - Before the end of the 1/4 finals: no result, no UCI points.
  - After the 1/4 finals but before the end of the semi-finals: the semi-finalists all get 4th place. Others are ranked by the normal rules.
  - After the semi-finals: the gold finalists both get 2nd. The bronze finalists both get 4th.
- **Brackets for 16 or 8 riders.** UNVERIFIED: 3.2.033 allows using the table with 16 or 8 qualifiers, but does not print the pairings. The natural reading is to start at the 1/8 finals (1 v 16, 2 v 15, ...) or the 1/4 finals (1 v 8, 2 v 7, ...), seeded by the 200 m TT.

### Typical configuration

- Heat length: 3 laps below 333.33 m, 2 laps at 333.33 m or more.
- Number of qualifiers: 28, 24 (Olympic), 16, or 8.
- Which rounds are single heats and which are best of three. The minimum format uses single-heat quarter-finals, but the World Cup table uses best-of-three quarter-finals.
- UNVERIFIED: USAC 2F3 also allows round-robin formats. In those, each rider meets every other rider.

---

## Tandem sprint

Articles 3.2.184 to 3.2.188.

### On the track

- Tandem sprint uses the sprint rules, with these changes.
- Each tandem pair counts as one participant (3.2.185).
- The start is at the pursuit line in the finishing straight (3.2.184bis).
- Qualifying is one lap with a flying start (3.2.187).
- Races are 3 laps (3.2.188).
- On tracks of 333.33 m or less, at most three tandems ride in one heat (3.2.186).

### Scorer inputs

Same as Sprint. The participant is a pair, so the program should model it as a two-rider team.

### Ranking algorithm

Same as Sprint. The bracket comes from the 3.2.050 table, worked out backward from the final (3.2.186).

### Edge cases

Same as Sprint.

### Typical configuration

- Qualifying: 1 lap flying start.
- Race distance: 3 laps.

---

## Keirin

Articles 3.2.134 to 3.2.143bis, and 3.3.012 B.

### On the track

- Riders follow a motorized pacer (a derny) for several laps. Then they sprint (3.2.134).
- On a 250 m track, the race is 6 laps. The pacer leaves with 3 laps to go (3.2.134, table in 3.2.135).
- On other tracks, the pacer leaves at the lap count closest to 750 m from the finish. The laps without the pacer equal the laps behind the pacer.
- The pacer starts at 30 km/h and builds to 50 km/h by the time it leaves (3.2.137).
- Start positions are drawn by lot. Riders hold their drawn positions for at least the first lap (3.2.138, 3.2.139).
- A rider who passes the front of the pacer's front wheel before the pacer leaves is disqualified. The race is rerun without that rider (3.2.140).

### Scorer inputs

- Per heat: the draw, the full finish order, and DNS, DNF, DSQ, and relegations.
- Which riders go to the next round, the repechage, or a final.

### Ranking algorithm

Minimum event (3.2.135):

- At least 10 riders.
- A qualifying round of 2 heats of 5 riders.
- A final for places 7 to 10, and a final for places 1 to 6.

World Cup and World Championships (3.2.135) need at least a 1st round, a 2nd round (1/4 finals), semi-finals, a final for 7 to 12, and a final for 1 to 6.

Round structure by field size (3.2.135 tables):

| Riders | 1st round | Repechage | 1/4 finals | Repechage | 1/2 finals | Finals |
|---|---|---|---|---|---|---|
| 10 to 14 | 2 heats of 5 to 7. Top 3 to final 1-6. 4th to 6th to final 7-12 | none | none | none | none | 1-6, 7-12 |
| 15 to 21 | 3 heats of 5 to 7. 2 per heat qualify | 2 to 3 heats of 5 to 7. 2 to 3 per heat qualify | none | none | 2 heats of 6. Top 3 to final 1-6, others to final 7-12 | 1-6, 7-12 |
| 22 to 28 | 4 heats of 5 to 7. 2 per heat qualify | 4 heats of 3 to 5. 1 per heat qualifies | none | none | 2 heats of 6 | 1-6, 7-12 |
| 29 to 42 | 6 heats of 4 to 7. 1 per heat qualifies | 6 heats of 3 to 6. 1 per heat qualifies | none | none | 2 heats of 6 | 1-6, 7-12 |
| 43 to 49 | 7 heats of 6 to 7. 1 per heat | 6 heats of 6 to 7. 2 per heat | 3 heats of 6 to 7. 2 per heat | 2 heats of 6 to 7. 3 per heat | 2 heats of 6 | 1-6, 7-12 |
| 50 to 56 | 8 heats of 6 to 7. 1 per heat | 7 heats of 6 to 7. 2 per heat | 4 heats of 5 to 6. 2 per heat | 2 heats of 7. 2 per heat | 2 heats of 6 | 1-6, 7-12 |
| 57 to 63 | 9 heats of 6 to 7. 1 per heat | 8 heats of 6 to 7. 2 per heat | 4 heats of 6 to 7. 2 per heat | 4 heats of 4 to 5. 1 per heat | 2 heats of 6 | 1-6, 7-12 |
| 64 to 70 | 10 heats of 6 to 7. 1 per heat | 9 heats of 6 to 7. 2 per heat | 4 heats of 7. 2 per heat | 4 heats of 5. 1 per heat | 2 heats of 6 | 1-6, 7-12 |

UNVERIFIED: the PDF table for 15 to 21 riders is hard to read. The repechage numbers above are a best reading of it.

The 28-rider example (3.2.135):

- Seeding for 4 heats of 7 is a serpentine: heat A has R1, R8, R9, R16, R17, R24, R25. "R" is UCI Sprint ranking. Unranked riders are drawn by lot.
- The top 2 of each 1st-round heat go to the semi-finals.
- The other riders go to 4 repechage heats of 5. Each repechage winner goes to the semi-finals.
- Repechage losers are ranked as a group by their finish place in the heat. All 2nd places are ranked 13th equal. All 3rd places are 17th equal. All 4th places are 21st equal. All 5th places are 25th equal.
- Semi-finals: top 3 of each go to the final 1-6. Places 4 to 6 go to the final 7-12.

The Olympic and World Championship example uses 30 riders. It has 5 heats of 6, then repechages, then 3 quarter-finals of 6, then semi-finals. In the quarter-finals, the top 4 advance. All 5th places are 13th equal, and all 6th places are 16th equal.

Non-finishers (3.3.012 B):

- A rider who does not finish a round is ranked last in that heat. That rider may still advance, if the rules allow.
- A rider is never moved up into a position that rider was not competing for, so some positions can stay vacant.
- In each final, the order is: finishers, then DNF (tied, next position), then DNS (tied, last position in that race), then DSQ (no rank, position left vacant).
- Riders eliminated in earlier rounds rank below riders in later rounds. Within a round, they are ranked by finish order in their heats, tied across heats.
- A DNS in the first round gets no rank.

### Edge cases

- **Restart.** A recognized mishap in the first half lap restarts the race. After the first half lap, no mishap is taken into account (3.2.143).
- **Rerun without a rider.** Faults behind the pacer stop the race. It is rerun without the rider at fault (3.2.140, 3.2.142).
- **Interrupted event** (3.2.143bis):
  - Before the qualifying round, 1/4 finals, or 1/2 finals are complete: no result.
  - After those rounds but before the finals are complete: riders qualified for each final get the last position of that final.
- **Tied ranks across heats.** Repechage losers share ranks, so the program must support tied ranks with gaps after them.

### Typical configuration

- Laps: 6 on a 250 m track, pacer off with 3 to go.
- Number of riders, which chooses the round structure from the table.
- Heat sizes and how many advance from each heat.
- UNVERIFIED: the table only gives laps for 250 m. Other tracks need a lap count computed from the 750 m rule.

---

## Individual Pursuit

Articles 3.2.051 to 3.2.076, and 3.3.012 F.

### On the track

- The two riders start opposite each other on the track. The winner catches the other rider or has the faster time (3.2.051).
- Distances (3.2.052):
  - 4 km for Men Elite and Women Elite.
  - 3 km for Junior Men and Junior Women.
- The event has a qualifying round and finals (3.2.053).
- The two fastest qualifiers ride the final for 1st and 2nd. The next two ride the final for 3rd and 4th.

### Scorer inputs

- Qualifying: pairings and each rider's time to the thousandth.
- Optional: final-lap time, used for ties.
- Finals: the winner, and whether it was a catch or a time.
- DNS, DNF, DSQ.
- Restarts.

### Ranking algorithm

- In qualifying, only times count (3.2.056). A caught rider must finish the distance to get a time.
- In a final, a catch ends the race (3.2.057). A catch happens when the chainsets of the two bikes are level (3.2.058).
- Tie on time: the rider with the better time for the final lap wins (3.2.061).
- If a rider does not start a final, the opponent wins. The non-starter is 2nd (gold final) or 4th (bronze final). If the reason is not accepted, the non-starter is DSQ and the place stays vacant (3.2.060).
- Riders who are not in the finals are ranked by qualifying time, after the finalists (3.3.012 F).
- A qualifying DNF, DNS, or DSQ gets no rank.

### Edge cases

- **Mishap in qualifying** (3.2.074). In the first half lap, the race restarts at once. After that, it is not stopped. The rider may ride again at the end of qualifying.
- **Mishap in a final** (3.2.075). In the first half lap, both riders restart. After that, the rider who suffers the mishap is considered beaten in the final.
- **Interrupted event** (3.2.073bis). Before qualifying ends: no result. After qualifying ends: rank by qualifying times.

### Typical configuration

- Distance by category.
- Number of finalists: 4.
- Masters distances are in [Masters distances](#masters-distances).

---

## Team Pursuit

Articles 3.2.077 to 3.2.100, and 3.3.012 E.

### On the track

- Two teams of four riders start on opposite sides. The race is 4 km (3.2.077).
- The team's time is taken on the front wheel of its third rider (3.2.080).
- A team is caught when the other team comes within one metre while at least 3 of its riders ride together (3.2.081).
- Team members may change between rounds (3.2.079).
- An incomplete team may not start (3.2.087).

### Scorer inputs

- Team rosters per round.
- Qualifying time per team, from the third rider.
- First round and final results: winner, catch or time, and both times when recorded.
- DNS, DNF, DSQ.

### Ranking algorithm

Basic format (3.2.085): 4 teams qualify on time. Teams 1 and 2 ride the gold final. Teams 3 and 4 ride the bronze final.

At World Cups, Continental Championships, World Championships, and Olympic Games, 8 teams qualify (3.2.082, 3.2.085). The first round is:

- Heat 1: 7th v 8th.
- Heat 2: 5th v 6th.
- Heat 3: 2nd v 3rd.
- Heat 4: 1st v 4th.

Then:

- The winners of the last two first-round heats ride the final for 1st and 2nd.
- The other 6 teams are ranked by their first-round times. The two fastest of them ride the final for 3rd and 4th.
- At the Olympic Games only, the next two ride for 5th and 6th, and the last two ride for 7th and 8th.

Other rules:

- Ties on time follow the individual pursuit rule, which is the best final lap (3.2.089, 3.2.061).
- If a team does not start the first round, it is 8th. Several non-starters fill 8th and upward in order of qualifying time. If the reason is not accepted, the team is DSQ and its place stays vacant (3.2.087).
- If a team does not start a final, the opponent wins. The non-starter is placed second in that heat (3.2.088).
- An incomplete team in qualifying is DNS with no rank (3.2.087).

### Edge cases

- **Catch in the first round.** In heats 3 and 4, the catching team wins. It must stop so the other team can finish and record a time (3.2.086). The program must allow both a "won by catch" flag and a time for the caught team.
- **Catch in a final.** The race ends at once. The catching team wins (3.2.086, 3.2.098).
- **A fast loser.** The winner of heat 1 or 2 cannot reach the gold final, even if its time is faster. A loser of heat 3 or 4 can reach the bronze final on time.
- **Mishap in qualifying** (3.2.099). In the first half lap, the race restarts. After that, if one rider is involved, the team may continue with 3 riders or stop within one lap. A team that stops rides again at the end of qualifying. A second mishap means it must continue with three or be DSQ.
- **Mishap in the first round or finals** (3.2.100). After the first half lap, a team with fewer than 3 riders must stop. It is relegated in the first round, or beaten in the finals.
- **Pushing** between teammates is DSQ in qualifying, relegation in the first round, and loss of the final in the finals (3.2.096).
- **Interrupted event** (3.2.098bis):
  - Before qualifying ends: no result.
  - After qualifying, before the first round ends: rank by qualifying.
  - After the first round: gold finalists both 2nd, bronze finalists both 4th.

### Typical configuration

- Distance: 4 km, 4 riders.
- Number of qualifiers: 4 or 8.
- Whether the Olympic 5-8 finals are ridden.

---

## Kilometre and 500 m Time Trial

Articles 3.2.101 to 3.2.112bis, and 3.3.012 D.

### On the track

- The Kilometre is an individual time trial from a standing start (3.2.101).
- At World Cups and World Championships it is 1000 m for men and women (3.2.102).
- The rider starts from a starting block on the inside edge (3.2.110, 3.2.111).
- The event has a qualifying round in two-up heats to find the 8 best, and then a final. In the final each rider rides alone (3.2.106).
- Class 1 and Class 2 events may run it as a direct final (3.2.106bis).
- All riders must ride in the same session. If they cannot, the whole race is rerun in a later session, and earlier times do not count (3.2.108).

### Scorer inputs

- Start order.
- Each rider's time.
- Optional: final-lap time, used for ties.
- DNS, DNF, DSQ, and restarts.

### Ranking algorithm

- Sort by time, fastest first.
- Tie: the rider with the better time for the final lap wins (3.2.107).
- Final ranking groups (3.3.012 D): finalists who finish, then final DNF (tied), then final DNS (tied, last in the final), then final DSQ (no rank). After them come qualifiers who did not reach the final. Qualifying DNF, DNS, and DSQ get no rank.

### Edge cases

- **Mishap in qualifying.** The other rider continues. The affected rider starts again at the end of qualifying. A second mishap is DNF (3.2.112).
- **Mishap in the final.** The race restarts at once. A second mishap means the rider is beaten (3.2.112bis).
- **Interrupted event** (3.2.108). Before qualifying ends, or before a direct final ends: no result. After qualifying: rank by qualifying.

### Typical configuration

- Distance: 1000 m.
- Direct final, or qualifying plus final.
- **500 m.** UNVERIFIED: the current Part 3 text no longer defines a 500 m time trial for elite or junior riders. Article 3.5.001 still lists the flying 500 m as a world record distance. The Masters table (3.9.006 E) uses 500 m and 750 m standing-start time trials for older age groups. The same scoring applies.

---

## Team Sprint

Articles 3.2.144 to 3.2.155, and 3.3.012 G.

### On the track

- Two teams of three riders ride 3 laps. Each rider leads for one lap and then pulls off (3.2.144, 3.2.152).
- Teams start in the middle of each straight (3.2.150).
- The leading rider's front wheel must cross the pursuit line ahead of the next rider's front wheel. The leading rider must then be above the sprinters' line within 15 m (3.2.153).
- If this changeover rule is broken, the team is placed last in that stage of the event (3.2.153).

### Scorer inputs

- Team rosters per round.
- Each team's time.
- Optional: last-lap time, used for ties.
- Changeover relegations.
- DNS, DNF, DSQ.

### Ranking algorithm

At World Cups, Continental Championships, World Championships, and Olympic Games (3.2.145):

1. A qualifying round selects 8 teams on time.
2. First round: 4th v 5th, 3rd v 6th, 2nd v 7th, 1st v 8th.
3. The four first-round winners go to the finals. The two with the best first-round times ride for 1st and 2nd. The other two ride for 3rd and 4th.
4. The four teams beaten in the first round are placed 5th to 8th by their first-round times.
5. At the Olympic Games only, the losers ride finals for 5th and 6th, and for 7th and 8th (3.2.146).

With fewer than 8 teams (3.2.145):

| Teams | First round | Final |
|---|---|---|
| 7 | 4th v 5th, 3rd v 6th, 2nd v 7th, 1st alone | Winners of each first-round heat (4 teams) |
| 6 | 4th v 6th, 3rd v 5th, 2nd alone, 1st alone | Winners of each heat (4 teams) |
| 5 | 4th v 5th, 3rd alone, 2nd alone, 1st alone | Winners of each heat (4 teams) |
| 4 or fewer | No first round | 4 best teams from qualifying |

Note that the 6-team pairing is 4th v 6th and 3rd v 5th. This is not the same pattern as the 8-team pairing.

Other rules:

- Tie: the better time for the last lap decides (3.2.147).
- If a team forfeits a final, the other team wins. If the reason is not accepted, the absent team is DSQ (3.2.148).
- If a team does not start the first round, it is 8th. Several non-starters fill 8th and upward by qualifying time (3.2.148bis).
- First-round DNS or DNF teams are ranked after the first-round losers, by qualifying time (3.3.012 G).

### Edge cases

- **Mishap in qualifying.** The team restarts at the end of qualifying. A team hindered by the other team's mishap may also be given a restart (3.2.154).
- **Mishap in the first round or finals.** It restarts at once if early. After the first half lap, no mishap counts. The team is relegated to last in the first round, or beaten in the finals (3.2.155).
- **Interrupted event** (3.2.153bis). It works the same as the Team Pursuit table.

### Typical configuration

- 3 laps, 3 riders, for men and women.
- Number of teams, which picks the bracket.

---

## Flying Lap

Articles 3.2.253 to 3.2.258.

### On the track

- One rider rides one lap against the clock, with a flying start at the finish line (3.2.253).
- The run-up plus timed lap is 3.5 laps on a 250 m or shorter track, 3 laps on 285.714 m, 2.5 laps on 333.33 m, and 2 laps on 400 m or longer (3.2.256).

### Scorer inputs

- Start order.
- Each rider's lap time.
- Optional: time for the last 200 m, used for ties.
- DNS, DNF, DSQ.

### Ranking algorithm

- Sort by time, fastest first.
- Tie: riders are ranked by their best times over the last 200 m (3.2.257).

### Edge cases

- One restart is allowed after a recognized mishap (3.2.258).
- UNVERIFIED: the text has no rule for a tie that remains after the last-200 m check. The 200 m TT uses a lot draw (3.2.027). Use the same.

### Typical configuration

- Track length sets the run-up laps.

---

## Points Race

Articles 3.2.114 to 3.2.133.

### On the track

- Riders score points in sprints held every set number of laps. Riders also gain or lose points by gaining or losing laps (3.2.114).
- Half the riders line up at the rail and half in the sprinters' lane (3.2.120).
- The race starts with a flying start after one neutral lap (3.2.121).
- Sprint interval (3.2.116, changed on 01.09.26):
  - Tracks shorter than 333.33 m: every 10 laps.
  - Tracks of 333.33 m: every 8 laps.
  - Tracks longer than 333.33 m: every 5 laps.
- If the total laps do not divide evenly by the interval, the extra laps come before the first sprint (3.2.117). Example: 56 laps on a 285.7 m track gives a first sprint after 16 laps, then every 10 laps.
- The last sprint is at the end of the full distance.

### Scorer inputs

- The roster and bib numbers.
- For each intermediate sprint: places 1 to 4, with ties.
- For the final sprint: places 1 to 4 for points, plus the full finish order of every rider for tie-breaks.
- Each lap gained, with the rider and the lap. Also note whether it happened in a sprint.
- Each lap lost, with the rider and the lap.
- Neutralizations: rider, start lap, and whether the rider came back.
- Withdrawals by the commissaires, abandons, and DSQ.
- Warnings and relegations.
- Restarts, with the laps-to-go value set after the restart.

### Ranking algorithm

Points (3.2.118):

- Each intermediate sprint gives 5, 3, 2, and 1 points to places 1 to 4.
- The last sprint, after the full distance, counts double: 10, 6, 4, and 2 points.
- If riders tie in a sprint, they all take the same position and each gets the points for it. For example, two riders tying for first both score 5 points, and nobody takes second.
- A rider who gains a lap on the main bunch gets 20 points.
- A rider who loses a lap on the main bunch loses 20 points.
- If a rider gains a lap at the moment of a sprint, the rider gets 20 points plus the sprint points (3.2.125).

Ranking:

1. Sort by total points, highest first. Totals can be negative.
2. Tie on points: the placings in the final sprint decide (3.2.119).

Laps are not a separate sort key. Laps count only as plus or minus 20 points (3.2.118). A rider with fewer laps can win on points.

Non-finishers:

- A rider pulled by the commissaires is DNF. That rider ranks in a tied group after all finishers, whatever points the rider had (3.3.012 A group 2).
- A rider neutralized when the last kilometre starts, who cannot come back, is ranked by the points and laps accumulated before the mishap (3.2.020bis). This rider stays in the points ranking, unlike a withdrawn rider.

### Edge cases

- **Sprint point ties.** A tie for 2nd means both get 3 points, and nobody gets 2nd-place points. The next rider is 4th and gets 1 point. Under the "same position" wording, there is no 3rd place. UNVERIFIED: the example in 3.2.118 shows only a tie for first. The handling of later places is our reading.
- **Lap gain during the final sprint.** The rider gets 20 points plus the doubled sprint points.
- **The whole field is lapped by a breakaway.** Each rider in the break gains 20 points. The rest of the field does not lose points. A lap is lost only when the largest bunch catches the rider (3.2.017quater).
- **A breakaway that is now the largest group.** The commissaires decide which group is the main bunch. The program should let the scorer award lap gains or losses to any set of riders in one action.
- **Riders who drop back and get caught by a break.** They may not lead the break, on pain of DSQ (3.2.126).
- **Lapped riders.** The commissaires' panel may withdraw riders who are one or more laps down (3.2.127). Withdrawal is optional. A lapped rider who stays keeps scoring.
- **Bell and head of the race.** Points go to the riders who cross next after the bell rang for the head of the race (3.2.125, 3.2.017bis).
- **Stopped race** (3.2.133). If restarted in the same session, riders keep their points. Laps to go are reset to the lap after the last sprint held. Example: the last sprint was at 40 to go and the race stopped at 33 to go. It restarts at 39 to go. All riders restart together. The commissaires may let riders more than half a lap ahead start half a lap ahead.
- **Stopped and cannot restart in the same session** (3.2.133):
  - Before 40% of the race: complete rerun.
  - Between 40% and 80%: resume with points kept.
  - After 80%: the result stands.
  - If less than 80% is complete by the end of the competition, there is no result.
- **Neutralization.** See [Neutralization after a mishap](#neutralization-after-a-mishap). The rider gets about 1250 m to return.

UNVERIFIED: USAC adds these rules (2M5, 2M7, 2M8):

- A rider who lost laps may sprint for points only after rejoining the main bunch before the sprint lap starts.
- A rider must rejoin the former group before the sprint lap to score after a mishap.
- All riders finish on the leader's lap.

### Typical configuration

UCI minimum distances (3.2.117 first table). Each cell shows km / laps / sprints.

| Track | Men Elite qual. | Men Elite final | Women Elite qual. | Women Elite final | Men Junior qual. | Men Junior final | Women Junior qual. | Women Junior final |
|---|---|---|---|---|---|---|---|---|
| 166 m | 15 / 90 / 9 | 30 / 180 / 18 | 10 / 60 / 6 | 20 / 120 / 12 | 10 / 60 / 6 | 20 / 120 / 12 | 10 / 60 / 6 | 15 / 90 / 9 |
| 200 m | 14 / 70 / 7 | 30 / 150 / 15 | 10 / 50 / 5 | 20 / 100 / 10 | 10 / 50 / 5 | 20 / 100 / 10 | 8 / 40 / 4 | 16 / 80 / 8 |
| 250 m | 15 / 60 / 6 | 30 / 120 / 12 | 10 / 40 / 4 | 20 / 80 / 8 | 10 / 40 / 4 | 20 / 80 / 8 | 10 / 40 / 4 | 15 / 60 / 6 |
| 285.71 m | 16 / 56 / 5 | 30 / 105 / 10 | 12 / 42 / 4 | 20 / 70 / 7 | 12 / 42 / 4 | 20 / 70 / 7 | 10 / 35 / 3 | 16 / 56 / 5 |
| 333.33 m | 14 / 42 / 5 | 30 / 90 / 11 | 10 / 30 / 3 | 20 / 60 / 7 | 10 / 30 / 3 | 20 / 60 / 7 | 10 / 30 / 3 | 16 / 48 / 6 |
| 400 m | 14 / 35 / 7 | 30 / 75 / 15 | 10 / 25 / 5 | 20 / 50 / 10 | 10 / 25 / 5 | 20 / 50 / 10 | 8 / 20 / 4 | 16 / 40 / 8 |

UNVERIFIED: the PDF text layer for this table is damaged. The values above match the clean Madison minimum table (3.2.157), which has the same numbers. For 285.71 m, the Points Race PDF row reads 10 km for the Women Elite qualifier, but 42 laps is 12 km. This file uses 12 km, as in the Madison table.

At World Cups, Continental Championships, and World Championships (3.2.117 second table). Each cell shows km / laps / sprints.

| Track | Men Elite qual. | Men Elite final | Women Elite qual. | Women Elite final | Men Junior qual. | Men Junior final | Women Junior qual. | Women Junior final |
|---|---|---|---|---|---|---|---|---|
| 200 m | 20 / 100 / 10 | 40 / 200 / 20 | 15 / 75 / 7 | 25 / 125 / 12 | 15 / 75 / 7 | 25 / 125 / 12 | 10 / 50 / 5 | 20 / 100 / 10 |
| 250 m | 20 / 80 / 8 | 40 / 160 / 16 | 15 / 60 / 6 | 25 / 100 / 10 | 15 / 60 / 6 | 25 / 100 / 10 | 10 / 40 / 4 | 20 / 80 / 8 |
| 285.71 m | 20 / 70 / 7 | 40 / 140 / 14 | 16 / 56 / 5 | 25 / 84 / 8 | 16 / 56 / 5 | 25 / 84 / 8 | 10 / 35 / 3 | 20 / 70 / 7 |
| 333.33 m | 20 / 60 / 7 | 40 / 120 / 15 | 16 / 48 / 6 | 25 / 75 / 9 | 16 / 48 / 6 | 25 / 75 / 9 | 10 / 30 / 3 | 20 / 60 / 7 |
| 400 m | 20 / 50 / 10 | 40 / 100 / 20 | 16 / 40 / 8 | 25 / 65 / 13 | 16 / 40 / 8 | 25 / 60 / 12 | 10 / 25 / 5 | 20 / 50 / 10 |

Settings the program should expose:

- Total laps.
- Sprint interval in laps.
- Points per place for intermediate and final sprints.
- Points for a lap gained and a lap lost.

These settings matter because local and Masters races vary them. Example: the UCI Masters table gives 10 points, not 20, for gaining or losing a lap in races under 20 km (3.9.006bis A).

UNVERIFIED: USAC 2M2 (2025) still uses every 5 laps on 333.33 m tracks, and every 20 laps on 166.66 m US tracks. The UCI text for 3.2.116 was last modified on 01.09.26 and now says every 8 laps on 333.33 m.

---

## Scratch Race

Articles 3.2.173 to 3.2.183.

### On the track

- The Scratch Race is a single-rider contest over a fixed distance, and the first rider across the line wins (3.2.173).
- Distances (3.2.174): Elite men and women ride 10 km. Junior men and women ride 7.5 km.
- Qualifying heats are 7.5 km for Elite and 5 km for Junior (3.2.175).
- The start is a flying start after one neutral lap (3.2.176).

### Scorer inputs

- The finish order of every rider.
- Laps gained and lost, per rider.
- Riders pulled after being lapped, with the moment they were pulled.
- Mishaps in the final kilometre.
- DNF, ABD, DNS, DSQ.

### Ranking algorithm

- Final placings are decided in the final sprint, with laps gained taken into account (3.2.178).
- Sort by laps, most first. Then sort by finish order.
- A rider overtaken by the main bunch must leave the track at once (3.2.177).
- Non-finishers are recorded per 3.3.012. So a pulled rider is DNF and shares the next rank after the finishers.
- A rider who falls in the final kilometre, or cannot return during it, gets the next available rank (and points) after the riders who finished. That rider is then ranked by laps gained or lost and by the number of riders still on the track at that moment (3.2.182).

### Edge cases

- **Lapped riders.** In a standalone UCI scratch race, a lapped rider must leave at once (3.2.177). The Omnium has its own rule that keeps lapped riders in until they are two laps down. See [Omnium](#omnium).
- **A rider or group laps the field.** Those riders rank ahead of everyone on fewer laps. The program must sort by laps first.
- **Stopped race** (3.2.183). Riders keep their laps gained or lost. The race restarts with the same laps to go, but never fewer than 10. Example: stopped at 4 to go means it restarts at 10 to go. If it cannot restart in the same session, it is rerun from the start.
- UNVERIFIED: USAC 2C4 says lapped riders who are not in contention are normally removed. If they are not removed, they are placed by laps down and then by finish position.

### Typical configuration

- Distance: 10 km (40 laps on 250 m) for Elite. 7.5 km (30 laps on 250 m) for Junior. Derived: the lap counts.
- Heat distance: 7.5 km or 5 km.

---

## Elimination Race

Articles 3.2.218 to 3.2.226.

### On the track

- The last rider in each intermediate sprint is eliminated (3.2.218).
- The start is a flying start after one neutral lap ridden as a compact group (3.2.221).
- Sprint interval (3.2.222):
  - Every third lap on tracks shorter than 200 m.
  - Every second lap on tracks from 200 m to less than 333.33 m.
  - Every lap on tracks of 333.33 m or more.
- On tracks shorter than 333.33 m, a bell marks each lap before a sprint.
- The last rider is judged by the position of the rear wheel on the line (3.2.223).
- The last two riders ride a final sprint. It is judged on the front wheel (3.2.224).

### Scorer inputs

- The elimination order: one or more riders per sprint, with the sprint number.
- Riders who were lapped or abandoned between sprints, which affects the next elimination.
- "No elimination this sprint" (green flag).
- Neutralizations.
- The winner of the final sprint between the last two.
- DSQ.

### Ranking algorithm

- Eliminated riders are placed in reverse order of elimination: the first rider eliminated is last, the second is second last, and so on (3.2.223bis).
- The final-sprint winner is 1st. The other rider is 2nd.
- A lap gained does not count in this race (3.2.225).
- Riders who did not qualify from heats share the last place. Riders who did not finish a heat are not placed (DNF) (3.2.219).

### Edge cases

- **Lapped or abandoning riders.** Riders who are lapped or abandon between sprints are the ones eliminated in the next sprint (3.2.223). So one sprint can eliminate more than one rider.
- **Elimination of a rider other than the last.** The commissaires may eliminate a different rider, for example for riding on the blue band (3.2.223).
- **Decision deadline.** The decision must be made and announced before the riders cross the back-straight pursuit line after the sprint. If no decision is made by then, nobody is eliminated until the next sprint. A green flag on the start line shows this (3.2.223).
- **Effect of a green flag.** UNVERIFIED: the text does not say whether the next sprint then eliminates one rider or two. It also does not say how the lap counter changes. The program should let the scorer enter any number of eliminations per sprint, including zero.
- **Mishap neutralization** (3.2.226):
  - The race is neutralized for at most the laps closest to 1250 m. If all riders crash, it is neutralized for at most 3 minutes.
  - A yellow flag shows the neutralization. The bunch rides together. Riders off the front or back lose that gap.
  - Riders who cannot rejoin when the race restarts are eliminated, ranked by the time of elimination.
  - The bell rings on the lap after the restart.
  - Once four or fewer riders remain, there is no neutralization, unless all riders crash. A rider who does not finish is eliminated at that point.
- **Eliminated rider stays on track.** The rider is relegated with a warning or DSQ (3.2.223).
- **Ties for last.** UNVERIFIED: the text has no rule for a dead heat for last place in a sprint. The commissaires decide. The program needs a way to record the decision.

### Typical configuration

- Sprint interval by track length.
- Number of starters.
- Derived: with N starters and one elimination per sprint, the race needs N - 1 sprints. On a 250 m track this is 2 x (N - 1) laps after the neutral lap. Example: 24 riders need 46 laps. The lap counter does not follow this if riders are eliminated two at a time.

---

## Tempo Race

Articles 3.2.259 to 3.2.265.

### On the track

- Riders score points in sprints and by gaining laps (3.2.259).
- The Points Race rules apply, except where the tempo rules differ (3.2.260).
- Distances: Elite men and women ride 10 km. Junior men and women ride 7.5 km (3.2.260).
- Sprints start after the first 4 laps and then happen every lap. The bell rings once those 4 laps are done to mark the start of the sprint laps (3.2.261).
- The start is a flying start after one neutral lap (3.2.264).

### Scorer inputs

- The winner of each sprint lap.
- The final sprint order for tie-breaks.
- Laps gained and lost.
- Withdrawals and DNF, ABD, DNS, DSQ.

### Ranking algorithm

- The first rider in each sprint gets 1 point, and that includes the final sprint (3.2.262). The final sprint is not doubled.
- A rider who gains a lap gets 20 points.
- A rider who loses a lap loses 20 points.
- Sort by total points.
- Tie on points: places in the final sprint decide, by the Points Race rule (3.2.260, 3.2.119).

### Edge cases

- **Lap gain in a sprint.** The rider gets 20 points plus the 1 sprint point, by the Points Race rule (3.2.125).
- **Stopped race** (3.2.265). If restarted in the same session, riders keep their points. Five laps are added to the laps to go. Example: 11 to go becomes 16 to go. If 5 or fewer laps were left, it restarts at 11 to go. Then 4 laps are ridden before sprints start again. All riders restart in one group. Gaps off the front or back are lost. If the race cannot restart in the same session, it is rerun from the start.
- **In the Omnium,** a rider who loses two laps is withdrawn with a 40-point penalty. See [Omnium](#omnium).
- UNVERIFIED: USAC 2P3 allows local variations if they are in the race announcement. This does not apply in an Omnium.

### Typical configuration

- 10 km is 40 laps on 250 m. 7.5 km is 30 laps. Derived.
- Derived: 40 laps give 36 sprints, on laps 5 to 40.
- Settings: total laps, number of non-sprint laps at the start (4), points per sprint (1), and points per lap (20).

---

## Madison

Articles 3.2.156 to 3.2.172.

### On the track

- Teams of 2 riders score points in sprints and by gaining laps (3.2.156).
- Both riders of a team wear the same number in different colors (3.2.158).
- One rider of each team starts. The other waits at the opposite rail and must not move during the neutral lap (3.2.163).
- The start is a flying start after one neutral lap.
- Riders may change over at any time, by touching hand or shorts (3.2.164).
- There is an equal number of laps between all sprints, counted back from the final sprint (3.2.157):
  - Tracks shorter than 333.33 m: 10 laps.
  - Tracks of 333.33 m: 8 laps.
  - Tracks longer than 333.33 m: 5 laps.
- Extra laps come before the first sprint (3.2.157).

### Scorer inputs

- Teams, as pairs of riders with one shared number.
- For each sprint: team places 1 to 4, with ties.
- For the final sprint: places 1 to 4, plus the full team finish order for tie-breaks.
- Team lap gains and losses.
- Team withdrawals and DSQ.
- Warnings for a rider, which also count against the team.

### Ranking algorithm

- Intermediate sprints give 5, 3, 2, and 1 points to the first four teams (3.2.161).
- The last sprint after the full distance gives double points: 10, 6, 4, and 2.
- Sprint ties work as in the Points Race. Tied teams get the same position and points (3.2.161).
- When teammates exchange exactly at the sprint line, the front wheel of the teammate taking over (the second rider in the exchange) is the one that counts. The exchange is finished once the two riders no longer touch (3.2.161).
- A team that gains a lap gets 20 points, and a team that loses a lap loses 20 points (3.2.162).
- A lap gained at the moment of a sprint gets 20 points plus the sprint points (3.2.167).
- Sort by total points.
- Tie on points: the placings in the final sprint decide (3.2.162).

### Edge cases

- **One rider has a mishap.** The teammate takes over the team's position at once. There is no neutralization (3.2.169).
- **Both riders have a mishap.** UNVERIFIED: the general rule 3.2.020bis grants neutralization when both riders of a Madison team have a mishap. USAC 2N6 says the same.
- **Dropped riders.** A rider who drops behind the bunch may not help chasing riders gain a lap, on pain of team DSQ (3.2.166).
- **Lapped teams.** The commissaires' panel may remove teams that are lapped one or more times (3.2.168).
- **Two warnings.** A team with two warnings in one Madison is DSQ (3.10.003).
- **Stopped race** (3.2.172). It works like the Points Race. Teams keep their points. Laps to go reset to the lap after the last sprint. Teams off the front or back lose their gap, and all restart as one group. The same 40% and 80% table applies if the race cannot restart in the same session.
- UNVERIFIED: USAC 2N3(e) says a relay made without a touch may cost the team a lap.

### Typical configuration

The UCI minimum distances (3.2.157 first table) are the same as the Points Race minimum table above.

At World Cups, Continental Championships, World Championships, and Olympic Games (3.2.157 second table). Each cell shows km / laps / sprints.

| Track | Men Elite qual. | Men Elite final | Women Elite qual. | Women Elite final | Men Junior qual. | Men Junior final | Women Junior qual. | Women Junior final |
|---|---|---|---|---|---|---|---|---|
| 200 m | 25 / 125 / 12 | 50 / 250 / 25 | 15 / 75 / 7 | 30 / 150 / 15 | 15 / 75 / 7 | 30 / 150 / 15 | 10 / 50 / 5 | 20 / 100 / 10 |
| 250 m | 25 / 100 / 10 | 50 / 200 / 20 | 15 / 60 / 6 | 30 / 120 / 12 | 15 / 60 / 6 | 30 / 120 / 12 | 10 / 40 / 4 | 20 / 80 / 8 |
| 285.714 m | 25.1 / 88 / 8 | 50 / 175 / 17 | 15.1 / 53 / 5 | 30 / 105 / 10 | 15.1 / 53 / 5 | 30 / 105 / 10 | 10 / 35 / 3 | 20 / 70 / 7 |
| 333.33 m | 25 / 75 / 9 | 50 / 150 / 18 | 14 / 42 / 5 | 30 / 90 / 11 | 14 / 42 / 5 | 30 / 90 / 11 | 10 / 30 / 3 | 20 / 60 / 7 |
| 400 m | 26 / 65 / 12 | 50 / 125 / 25 | 14 / 35 / 7 | 30 / 75 / 15 | 14 / 35 / 7 | 30 / 75 / 15 | 10 / 25 / 5 | 20 / 50 / 10 |

UNVERIFIED: one row does not match the stated sprint interval. The 400 m Men Elite qualifier lists 65 laps and 12 sprints, but every 5 laps gives 13. The distance (26 km) also looks unusual. The program should let the scorer set laps and interval freely.

---

## Omnium

Articles 3.2.247 to 3.2.252bis.

### On the track

The Omnium is four races held on one day, in this order (3.2.247):

1. Scratch Race: 10 km for Elite, 7.5 km for Junior.
2. Tempo Race: 10 km for Elite, 7.5 km for Junior.
3. Elimination Race.
4. Points Race: 25 km for Men Elite, 20 km for Women Elite and Men Junior, and 15 km for Women Junior.

Other rules:

- There should be at least 30 minutes between races (3.2.248).
- For the Scratch Race, the start order follows the UCI Endurance Ranking. For the later three races, it follows the current Omnium standings (3.2.249bis).
- If too many riders enter, they first ride Points Race qualifying heats. These use the first table of 3.2.117 (3.2.247bis).

### Scorer inputs

- The full result of each of the first three races, using that race's own inputs.
- The Omnium-specific withdrawals: a rider two laps down in the Scratch or Tempo Race.
- The Points Race inputs: sprints, lap gains, lap losses, and the full final-sprint order.
- DNS or abandon in any race.

### Ranking algorithm

1. Each of the first three races produces a full result. The winner gets 40 points, 2nd gets 38, 3rd gets 36, and so on down by 2. Riders in 21st place and below get 1 point each (3.2.250).
   - Derived: place p scores 42 - 2p for places 1 to 20, so 20th scores 2. Places 21 and below score 1.
2. Before the Points Race, a standings table is made with these totals (3.2.251).
3. Riders start the Points Race with those points. They add sprint points and lap points, and lose 20 for each lap lost (3.2.251).
4. The rider with the highest point total wins the Omnium (3.2.251).
5. Tie on final total: finishing order in the last sprint of the closing Points Race breaks the tie (3.2.252).

Note: the Points Race in the Omnium is not scored as a separate race and then converted to 40-38-36 points. Its raw points add straight onto the carried total.

### Edge cases

- **DNS or abandon.** A rider who does not start, or who abandons, any of the events may not continue in the Omnium. That rider is recorded in the final classification under article 3.3.012 (3.2.251bis).
- **Two laps down in the Scratch or Tempo Race** (3.2.251bis):
  - A rider who loses two laps is withdrawn.
  - The rider takes a 40-point deduction in the Omnium classification.
  - The rider gets the next available rank, set by the number of riders still on the track at that moment.
  - If the rider is not withdrawn for any reason, the rider is classified as if withdrawn at the point of losing the second lap, deduction included.
  - Note: this rider stays in the Omnium, unlike an abandon. The rider gets place points for the assigned rank, minus 40.
  - Derived: the first rider pulled from a 24-rider field gets 24th place, which scores 1 point. With the 40-point deduction, this gives -39 for that race. The second rider pulled gets 23rd.
- **Fall in the final kilometre of the Scratch Race** (3.2.251ter). The rider gets the next available rank (and points) after the riders who finished the race. The rider is then ranked by laps gained or lost and the number of riders still on the track.
- **Ties inside the first three races.** UNVERIFIED: 3.2.250 says only that each race produces a full result. It does not say how two riders tied on one place share points. The Scratch and Elimination races normally produce no ties. A Tempo Race tie is broken by the final sprint. A dead heat in the Scratch Race needs a commissaire decision.
- **Points Race laps.** The rules use only points, so a lap counts as 20 points. A rider can be down a lap and still win the Omnium.
- **Interrupted Omnium** (3.2.252bis):
  - During the Points Race, the Points Race rule (3.2.133) applies.
  - If less than 80% of the Points Race is done and it cannot restart, the standings after the Elimination Race become final.
  - If the track becomes unusable after the Elimination Race but before the Points Race, the standings after the Elimination Race become final.
  - If it becomes unusable before the Elimination Race is complete, there is no result.

UNVERIFIED: USAC 2O2(c) says a rider who fails to start one race is placed last as DNF. The UCI text instead refers to 3.3.012.

### Typical configuration

On a 250 m track (derived):

- Scratch: 40 laps for Elite, 30 laps for Junior.
- Tempo: 40 laps for Elite (36 sprints), 30 laps for Junior (26 sprints).
- Elimination: sprint every 2 laps.
- Points Race: 100 laps and 10 sprints for Men Elite. 80 laps and 8 sprints for Women Elite and Men Junior. 60 laps and 6 sprints for Women Junior.

The program should support a configurable list of component races and a configurable place-points table. Local omniums often use other races or tables. UNVERIFIED: this last point is general knowledge, not from a rulebook.

---

## Motor-Pacing (stayer races)

Articles 3.2.189 to 3.2.217.

### On the track

- Each rider rides behind a pacer on a motorcycle (3.2.189).
- A race is over a set time (1 hour) or a set distance (3.2.197).
- All heats are run on the same day. Each heat has at most 8 riders. There are at least two heats (3.2.198, 3.2.199).
- The start is a pistol shot. After one lap, riders join their pacers (3.2.210).

### Scorer inputs

- Laps completed per rider.
- Finish order.
- Eliminations: riders more than 5 laps down, or eliminated after a warning.
- Mishaps and neutralizations.
- Pacer penalties. These are fines, not scoring changes.

### Ranking algorithm

- Placing is decided by finish order and the number of laps covered. Once the winner crosses the line, the other riders cross it only once more (3.2.211).
- So: sort by laps covered, then by finish order.
- Qualification from heats to the final (3.2.199):
  - Two heats: the first three of each heat, plus the 4th of the faster heat.
  - Three heats: the first two of each, plus the 3rd of the fastest heat.
  - Four or more heats: each heat winner, plus seconds from the fastest heats, so that seven riders reach the final.
- If the final is run in heats, the organizer sets the rule for the overall result. If there is no rule, the commissaires set one before the start (3.2.201).

### Edge cases

- A rider more than 5 laps behind the leader is eliminated (3.2.214).
- A rider one lap down may not respond to an attack from a rider more than one lap ahead. The penalty is elimination after one warning (3.2.213).
- **Mishap after riders join their pacers** (3.2.216). The rider gets a neutralization closest to 1500 m, except during the last 1500 m or last minutes of a time race. A rider who cannot continue is placed where the rider was, if the result was "a foregone conclusion". Otherwise the rider is placed last among riders on the same laps at the time of the mishap.
- **Track becomes unusable** (3.2.217). The race restarts from the start, unless it is in the last 2 km or last 2 minutes. In that case, riders are placed by their position when they last crossed the finish line.

### Typical configuration

- Time (60 minutes) or distance.
- Heat sizes.
- Number of finalists: 7, when there are four or more heats.

---

## Six-Day Races

Articles 3.2.227 to 3.2.246.

### On the track

- A six-day race is a team race over several days. Teams have 2 or 3 riders (3.2.229).
- The organizer sets the duration and program (3.2.228).
- The track must be at least 140 m long (3.2.230).
- Each session includes Madisons ("chases") and other individual and team races.

### Scorer inputs

- Laps gained and lost per team in each Madison or chase.
- Points per team from every race in the program.
- Neutralizations, disbanded teams, and provisional teams.
- The final sprint order of the final Madison.

### Ranking algorithm

Points per race (3.2.242):

- Team races (Madison, Madison-Elimination, Team Time Trial 500 to 1000 m): 20, 12, 10, 8, 6, 4.
- Individual races (Points race, Elimination, 1-lap Time Trial, Derny, Scratch, Keirin): 10, 6, 5, 4, 3, 2.
- Madison sprints: 5, 3, 2, 1. These double in the final Madison, with at most 6 sprints, every 10 laps.

When races are run in heats split by the overall standings (3.2.243):

- One heat for each half of the standings, 1 rider per team: 10, 8, 6, 4, 2.
- One heat for each half, team race with one change mid-race: 10, 8, 6, 4, 2.
- One heat for each half, Madison: 15, 10, 8, 6, 4, 2.
- Two heats for each half, 1 rider: 5, 4, 3, 2, 1.
- Laps won in derny races do not count for the overall standings.

Overall standings (3.2.244 to 3.2.246):

1. Rank by total laps covered, most first. The team with the most laps wins, whatever its score (3.2.246).
2. Teams with the same laps are ranked by total points.
3. Teams with the same laps and points are ranked by the final sprint order.
4. Except in the final Madison/chase of the Six-Day Race, a team gets one bonus lap for every 100 points it logs (3.2.244).
5. Laps won count toward the general classification only in races where each team has at least one rider on the track. Laps won in Elimination races never count (3.2.245).

Note: unlike the Points Race and the Madison, a six-day race ranks on laps first and points second.

### Edge cases

- **Neutralization** (3.2.234). A team gets the laps closest to 1250 m after a recognized mishap. After that, or after an unrecognized mishap, a team member must return to the exact position, or the team loses the laps.
- **Laps gained while a teammate is neutralized** count only if the remaining rider covers the full distance, without missing a relay (3.2.235).
- **Single remaining rider.** In a timed chase, a team reduced to one rider leaves the track 10 laps before the end (3.2.236).
- **Provisional teams** (3.2.237). Riders whose teammates are neutralized may form a temporary team. Its laps are the two original teams' laps added together, rounded down to an even number, and halved. When it breaks up, laps and points go back to the original teams.
- **A fully neutralized team** is placed with the nearest team in the overall standings at the start of the race. It keeps laps lost but not laps gained, and loses one more lap (3.2.238).
- **Doctor neutralization** lasts up to 36 hours. After that the rider is eliminated (3.2.239).
- **Abandon** (3.2.240, 3.2.241). The team is disbanded. The remaining rider rides the individual races. That rider is eliminated if not placed in a new team within 48 hours. A new team takes the best disbanded team's position plus a one-lap penalty. Its points are the two teams' points, added and divided by two.
- **Scoreboard.** At the start of each Madison or chase, the board shows zero for all teams, except in handicap races. After the chase, it shows the overall standings again. On the last day, it shows the live overall standings (3.2.232).
- **UCI points.** Starting 01.01.2028, Six-Day races no longer award UCI points (3.8.003 amendment). This does not change scoring.

### Typical configuration

- Number of teams and team size.
- The program for each day.
- Points tables per race type.
- Bonus lap per 100 points: on or off.

---

## Formats not in UCI Part 3

The UCI Part 3 text does not define these formats. All rules here are UNVERIFIED with respect to the UCI.

### Team Elimination

- UNVERIFIED: no Team Elimination race exists in UCI Part 3. Article 3.2.242 names a "Madison-Elimination" only in the Six-Day points table, with no rules. No reliable source was found for a standard format. If a facility runs one, define its rules locally.

### Handicap Race

From USAC 2D (UNVERIFIED for the UCI).

- **On the track.** Stronger riders get a longer distance or a later start. The handicapper sets each rider's mark. Marks must be announced before the start (2D1, 2D2). After the start, the race runs as a scratch race (2D5).
- **Scorer inputs.** Each rider's mark (distance or time allowance). Finish order. DNF.
- **Ranking algorithm.** Finish order across the line, as in a scratch race.
- **Edge cases.** UNVERIFIED: the text does not explain how laps gained or lost work when riders start at different points. Treat the official finish order as final.
- **Typical configuration.** Distance and the list of marks.

### Miss-and-Out

From USAC 2E5 (UNVERIFIED for the UCI).

- **On the track.** Riders are eliminated every lap, every other lap, or at another stated interval. The race normally follows Elimination Race rules, except that it may run down to the last rider or to a set number of survivors. With survivors, there may be a free lap and then a conventional sprint, judged on front-wheel finish order.
- **Scorer inputs.** Same as the Elimination Race, plus the number of survivors.
- **Ranking algorithm.** Inverse order of elimination. The survivors are placed by the final sprint.
- **Typical configuration.** Elimination interval, number of survivors, and whether there is a free lap.

### Win-and-Out

UNVERIFIED: from a low-confidence secondary source (Canyon blog). No rulebook text was found.

- **On the track.** At set intervals there is a sprint. The winner of each sprint leaves the race. The first sprint winner is 1st, the second is 2nd, and so on, until the podium is filled.
- **Scorer inputs.** The winner of each sprint, in order.
- **Ranking algorithm.** Places 1 to K in the order of sprint wins. Others are unplaced, or placed by the last sprint.
- **Typical configuration.** Sprint interval and number of places awarded.

### Unknown Distance

UNVERIFIED: no rulebook source was found.

- **On the track.** Common practice is that riders do not know the distance. An official rings the bell at a moment chosen in secret, and the next lap is the last.
- **Scorer inputs.** Finish order, and laps gained or lost.
- **Ranking algorithm.** Scratch race rules.

### Derny races

- UNVERIFIED: the UCI Six-Day table lists "Derny" races (3.2.242), but Part 3 gives no rules for them. The Keirin uses a motorized pacer. Motor-Pacing (stayer races) uses motorcycles. A scratch-style finish with laps is the likely model.

---

## Masters distances

UCI Masters World Championships distances (3.9.006bis). Age groups are 35-39, 40-44, and so on in five-year steps.

| Race | Men | Women |
|---|---|---|
| Points Race | 30 km (35-39), 20 km (40-49), 15 km (50-59), 10 km (60+) | 15 km (35-39), 10 km (40+) |
| Scratch | 10 km (35-49), 7.5 km (50-59), 5 km (60+) | 5 km |
| Sprint | 3 laps, per 3.2.050 | 3 laps, per 3.2.050 |
| Individual Pursuit | 3 km (35-49), 2 km (50+) | 3 km (35-49), 2 km (50+) |
| Time Trial (direct finals) | 1 km (35-39), 750 m (40-49), 500 m (50+) | 1 km (35-39), 750 m (40-49), 500 m (50+) |
| Team Pursuit | 4 km, 4 riders | 4 km, 4 riders |
| Team Sprint | 3 laps, 3 riders | 3 laps, 3 riders |

Other Masters rules:

- Points Race: gaining or losing a lap is worth 10 points in races under 20 km.
- Points Race and Scratch: if there are more than 24 riders, qualifying heats are half distance.
- An age group needs at least 12 riders in a bunch race, or 8 in other races, to race separately. Otherwise it is combined with the next group. Separate results are still produced (3.9.006).
- A team rides in the age category of its youngest rider (3.9.006).

---

## Scoring rules most likely to be implemented wrong

1. **Omnium two-laps-down rule.** In the Omnium Scratch and Tempo races, a rider two laps down is pulled, given the next available place, and loses 40 Omnium points. The rider stays in the Omnium. A plain DNF would be wrong (3.2.251bis).
2. **Points Race and Madison rank on points only.** A lap is worth exactly 20 points. Laps are not a first sort key. The Six-Day overall standings do the opposite: laps first, then points (3.2.118, 3.2.246).
3. **The final sprint needs a full finish order.** Points ties are broken by the final sprint places. Only the top 4 score, but the scorer must capture the order of every rider (3.2.119, 3.2.162, 3.2.252).
4. **Sprint point ties share a place and skip the next.** Two riders tied for 1st both get 5 points, and nobody gets 3 (3.2.118).
5. **Pulled is not the same as neutralized.** A rider withdrawn by the commissaires is DNF and ranks below every finisher. A rider whose neutralization runs into the last kilometre keeps the points and laps earned and is ranked on them (3.3.012 A, 3.2.020bis).

Other rules worth a test case each:

- An elimination sprint can remove several riders, or none (green flag) (3.2.223).
- Sprint tournament losers in early rounds are ranked by 200 m TT time, not by the round they lost in alone (3.2.050).
- Team Pursuit: only the last two first-round heats can reach the gold final (3.2.085).
- Warnings carry across races in a meet. Two in one race, three in a meet, or three relegations mean DSQ (3.10.003).
- Restart laps-to-go formulas differ by race. Points Race and Madison reset to the lap after the last sprint. Scratch keeps the same laps, with a minimum of 10. Tempo adds 5, with a minimum of 11 (3.2.133, 3.2.183, 3.2.265).
- The UCI Points Race and Madison sprint interval on 333.33 m tracks is every 8 laps (3.2.116, modified 01.09.26). USAC 2025 says every 5 laps. A facility following USAC must set this explicitly.
