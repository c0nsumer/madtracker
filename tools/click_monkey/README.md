# Click monkey

This is a hand tool, not a suite test. It plays a click-happy scorer: random presses over every visible control of the operator window, in random order and random states, headless, one seed at a time. It's for catching what a person mashing the screen would hit that the design walk's sweep doesn't reach.

## Running it

Run it from the repo root with the venv active:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python tools/click_monkey/run.py --seeds 20 --steps 500
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python tools/click_monkey/run.py --seed 7 --steps 500 --replay
```

Each seed runs in its own child process, with `HOME` and the XDG folders pointed into that seed's temp folder. So nothing reaches your own settings or data folder, and a crash or hang in one seed doesn't spoil the next. If a seed fails, it prints each failing step: the seed, the step number, the control's name, and what broke. The exit code is the number of failing seeds.

The options:

- `--steps N` sets the steps per seed. If it's left out, each seed picks between 200 and 2000.
- `--first N` sets the first seed of a `--seeds` run.
- `--tmp DIR` sets where each seed's files go. If it's left out, they go in the system temp folder.
- `--keep` keeps a failing seed's folder: its `trail.txt` (every step and what the fakes answered), `child.log`, and the data files.
- `--replay` runs one seed in this process and prints every step as it goes. The answers come from the same `random.Random(seed)`, so a seed replays the same steps for as long as the window answers the same way.

The development laptop is short on memory, so run it under the cgroup cap (one seed peaks at ~300 MB):

```bash
.claude/tools/run.sh "$PWD" 3600 /some/log tools/click_monkey/run.py --seeds 30 --steps 500
```

## What a step is

A step is one of these, picked at random with weights:

- A visible control from the design walk's `controls()`: a card, its ⋯ or laps, a surface button, a row's ⋯, a sprint header, Undo, the preview, the Edit | Score switch, a program row, or any enabled File, Scoreboard, or Help menu item except Quit.
- A press on a done card (a rider placed, out, or marked, grayed in its slot), named `card done` and its rider.
- A right-click on a card, a result row, the task line, or the bare surface.
- A double click on a card, a row, Undo, or Record Sprint. On a card, Undo, or Record Sprint it's sent as a person's double-click is (press, release, the double-click event, release), since QTest's own sends no release and a button under it never clicks.
- A key: the Undo and Close standard keys, F1, Escape, Return, Space, Tab, or letters into whatever has focus.
- A window size: 1366 x 740, 1600 x 900, or 1920 x 1080.
- A poke at the Edit Event screen, the help window, or the welcome screen.
- A fake second display (`FAKE-TV`) plugged in or pulled out.

Every blocking call is answered at random:

- A modal dialog (`QDialog.exec`) is shown and poked at up to eight times. Pokes press buttons, type or paste into fields (eg: the fuzzer's corpus, invented names, or nothing), pick from combos, and click, double-click, right-click, or edit table cells. Then the dialog is closed by its primary button, Return, Escape, the Close key, or Cancel. A poke can open another dialog, up to three deep.
- `icons.ask` answers yes or Cancel, `icons.choose` picks any offered verb or Cancel, and `warn` and `inform` are only noted.
- A file picker returns nothing, or one of these: the open file, a text file, an empty or junk `.sqlite`, a copy of the demo, a backup, a new path, or a path in a folder that doesn't exist.
- A ⋯ menu picks one enabled item, including the items in the moves submenu, and sometimes picks nothing.

## What is checked after each step

After the event loop runs, these must all hold:

- No exception escaped a slot.
- No "Unexpected error" or traceback is new in the app's log.
- No modal dialog, message box, menu, or popup is left open.
- The main window still shows. If it shows the empty screen, no race is live.
- The surface's `Screen` equals a fresh `race_screen.screen` of the live log.
- While cards show, they're the race's field in bib order.
- A press on a done card leaves the log's length and the staged setting row as they were, and the red line says the controller's refusal for that card.
- No entrant is listed twice.
- Each recorded row's total (in a points race) or place (in a placings race) matches `compute_for_format` on `live.actions()`.
- The staged setting row equals the race's staged order.
- `race_action` never shrinks while the same store is open.
- Every open SQLite connection is on the current data file. (This is checked every tenth step.)
- RSS stays under 1.5 GB.

A press of a surface control must also change what the snapshot holds, open something, or say why not, the same way the sweep checks it. A ⋯ press must open a menu with items in it.

If the harness itself raises, the failure is labeled `HARNESS`, so a bug in the harness never reads as a bug in the app.
