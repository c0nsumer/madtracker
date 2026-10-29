# Session replay

A hand tool that plays whole race nights through the app headless and checks, after every step, what should always hold. It drives the `AppController` methods the window's signals call (a card's click, a row's menu, Record Sprint, End Race, Undo, Mark Final, the file switches, the exports), on a copy of the demo file, so it covers the controller, the store, the wiring, and the exports above the scoring engines (`tools/scoring/` covers those). It's never a suite test: pytest's `testpaths` is `tests`, and nothing here is named `test_*`.

```bash
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python tools/session_replay/run.py --nights 3 --seed 1
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python tools/session_replay/run.py --fast
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python tools/session_replay/run.py --only storm --nights 20 --seed 5
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python tools/session_replay/run.py --sabotage total --fast
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python tools/session_replay/run.py --only personas --nights 1 --seed 1
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python tools/session_replay/run.py --only fat-finger --nights 20 --seed 2 --coverage
```

Each round plays three nights, each on its own copy of the demo: a clean night (every race scored as called, marked final, exported), a messy night (a short sprint, a DNF, laps, a penalty set, changed, and removed, Out of the Finish, two riders withdrawn a sprint apart (and one before the line in a race placed at the line), a crash in an Elimination, End Race undone and ended again, reopened sprints with moves and ties, Reopen and a DQ, plus random controls), and a switch night (another file, a backup restored as a new file and over the open one, the demo data file, refused files, and Edit Event mid-race). `--only storm` is a fourth night that's mostly random controls with every step undone and done again.

The personas are the scorer under stress, one night each over every race of the demo. `--only personas` plays all eight, and `--only` with a persona's name plays one. Where a habit must mean what one entry means, it's checked against a twin: the open file copied as it stood before the habit, given that one entry through the controller alone.

- `careful`: the clean night over fields resized in Edit Race to 4, 12, 20, and 30 riders and 3, 6, and 12 teams, each race a size in turn. It's the baseline the others are measured by.
- `click-happy`: pressed through the window's own buttons, a double-click on a card, two to five taps on one card, a done card and then the right one, Record Sprint and Undo pressed twice or double-clicked, and a ⋯ opened and closed with no pick. Each must record what one press means, and the done card's tap does nothing, with no red line. (A second tap on a badged sprint card takes the badge off by design, so a burst there is a double-click.)
- `careless`: two riders clicked the wrong way round and noticed one to four clicks later, then fixed by Undo, by the rows' Move Up, or by the cards' (a done card's ⋯ included). Also a Chase placed from both ends with Place Last, and a status marked from the row of a rider already placed. The result after each fix must be the result of the right clicks made once.
- `panicked`: each race scored to its result, undone to the start, and scored again, twice. Both passes must end at the first one's result. Between them the live log and the staged row are empty, every entry is voided once, and Edit Race opens unlocked.
- `fast-finish`: fields of 14 riders and 12 teams, and twelve clicks in each race's finish with no turn of the event loop between them. The order recorded must be the order clicked.
- `fat-finger`: a click meant for a card lands, by the window's own geometry, on its ⋯ strip, a lap button, the card beside it, or a done card's badge. A miss on a done card's badge must be nothing, with no red line; any other miss must be nothing, or one Undo.
- `late-change`: the careful night's sizes, then mid-race a rider renamed in Edit Riders, a bib changed in the roster on a rider not yet placed, and a rider or team added or taken out where Edit Race still allows it (nothing scored yet). The grid must take the new field once, in bib order, and every card keeps its state. A rider taken out lets the staged clicks go with them, as the store does.
- `corrector`: each sprint race set to five sprints, a DNF before Sprint 2 and a withdrawal after it, Sprint 2 reopened after Sprint 4 with badges moved and recorded, and Sprint 3 reopened and cancelled. The done cards in a reopened sprint must be who had left by then, and the cancel must leave the race as it was.

`--coverage` lists what each persona did, so a habit a run never reached shows up as missing. The window-driven personas (click-happy, fast-finish, fat-finger) show the window at 1366 x 740.

The checks: the cards are the field in bib order until the result completes, each done card's mark is its row's, a click on a done card is refused and writes nothing, the window's card widgets are the screen's cards in the same order, the table matches a replay of the live log, the race read again from the file matches the screen, the stored state is the log's, the staged order in the file is the controller's, no `race_action` row changes or goes, Undo puts the screen back, the exports agree with the shared rows (no "None" anywhere), no second-window line, nothing logged as an error, and the run stays under 1.5 GB.

The last line is `breaks: N`, and the exit code is N. A break prints its step number and race, so `--night K --trace` with the same `--seed` replays that night step by step. `--sabotage` breaks the app on purpose, to show the harness still catches it. Files go to a temp folder that's deleted at the end, unless you pass `--out DIR`.
