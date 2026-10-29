# Session replay

A hand tool that plays whole race nights through the app headless and checks, after every step, what should always hold. It drives the `AppController` methods the window's signals call (a card's click, a row's menu, Record Sprint, End Race, Undo, Mark Final, the file switches, the exports), on a copy of the demo file, so it covers the controller, the store, the wiring, and the exports above the scoring engines (`tools/scoring/` covers those). It's never a suite test: pytest's `testpaths` is `tests`, and nothing here is named `test_*`.

```bash
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python tools/session_replay/run.py --nights 3 --seed 1
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python tools/session_replay/run.py --fast
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python tools/session_replay/run.py --only storm --nights 20 --seed 5
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python tools/session_replay/run.py --sabotage total --fast
```

Each round plays three nights, each on its own copy of the demo: a clean night (every race scored as called, marked final, exported), a messy night (a short sprint, a DNF, laps, a penalty set, changed, and removed, Out of the Finish, two riders withdrawn a sprint apart (and one before the line in a race placed at the line), a crash in an Elimination, End Race undone and ended again, reopened sprints with moves and ties, Reopen and a DQ, plus random controls), and a switch night (another file, a backup restored as a new file and over the open one, the demo data file, refused files, and Edit Event mid-race). `--only storm` is a fourth night that's mostly random controls with every step undone and done again.

The checks: the table matches a replay of the live log, the race read again from the file matches the screen, the stored state is the log's, the staged order in the file is the controller's, no `race_action` row changes or goes, Undo puts the screen back, the exports agree with the shared rows (no "None" anywhere), no second-window line, nothing logged as an error, and the run stays under 1.5 GB.

The last line is `breaks: N`, and the exit code is N. A break prints its step number and race, so `--night K --trace` with the same `--seed` replays that night step by step. `--sabotage` breaks the app on purpose, to show the harness still catches it. Files go to a temp folder that's deleted at the end, unless you pass `--out DIR`.
