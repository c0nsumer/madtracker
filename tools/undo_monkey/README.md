# Undo monkey

This is a hand tool for the scorer who undoes a lot. It plays random walks of entries, corrections, and Undo against `LiveRace` and checks after every step that nothing is lost or doubled. It's slow and random, so it's never a suite test. pytest never collects it, as the suite's `testpaths` is `tests` and nothing here is named `test_*.py`.

Its target is the controller's undo stack, the staged order in the `setting` table, the sprint corrections, and the race state. The scoring engines are covered by `tools/scoring/`.

## Running it

From the repo root with the venv active:

```bash
python tools/undo_monkey/run.py --seeds 40 --ops 300                  # every format, ~10 minutes
python tools/undo_monkey/run.py --seeds 40 --format points            # one format
python tools/undo_monkey/run.py --seed 7 --format elimination --replay  # one walk, every step printed
python tools/undo_monkey/run.py --seeds 200 --clone-every 4           # faster: the copy check on 1 in 4
```

Each walk takes 100 to `--ops` operations. The formats are `chase`, `handicap`, `elimination`, `miss_and_out` (the demo's Elimination rules), `points`, `madison`, `tempo`, and `win_and_out`, each with random rules (sprint counts, survivors, places, direction) and 4 to 12 riders or 3 to 6 teams. Walks run in a fresh folder under the system temp directory, removed afterwards.

A clean run ends with `0 breaking seeds` and exits 0. Otherwise the exit code is the number of breaking seeds (capped at 125). Each break prints its check letter, the seed, the format, the operation number, the facts before and after, the last operations, and the command that replays it. The `note:` lines count things that are by design, such as a Cancel that keeps the log entries made during the correction.

## What a walk does

Each step picks one operation the controller offers right then: a card click, Record Sprint (a short sprint answered yes), any key on a card's menu or a row's menu (a Points Penalty gets a random number), a sprint reopened for correction, Cancel, Place Last, Place the Rest Together, End Race, Mark Final, Reopen, or Undo. Undo is about a third of the steps, and now and then a run of Undo goes back to the empty log. At the empty log with nothing staged, the race may be set up again as Edit Race then allows: a rider out and a spare from the roster in, two teams' riders traded, a team dropped or a pair added, the sprint count or the places up or down (what `Store.save_race` writes for the dialog's Save), and the window reads the race again. Every walk ends with a run of Undo to the empty log, one such edit, twenty more steps on the new setup, and a run of Undo back to the empty log once more. A refusal is fine. An exception is a break.

## The checks

- **a**: the stored race state is the one the live log settles to.
- **b**: a window opened now (a crash and reopen) reads the same staged order, undo stack, and screen.
- **c**: the screen's result rows match `compute_for_format` on the live log.
- **d**: the log only grows, and a voided row never comes back to life.
- **e**: every operation that succeeds pushes one undo entry, and its label starts with "Undo: ". Undo then puts back the log (its rows and their order), the staged order, the state, and the screen as they were before it. This is tried on a copy of the file right after the operation, and again for real whenever the walk's own Undo reaches that entry. A refusal changes nothing.
- **f**: Undo is never off while the log or the staged order holds something. A run of Undo ends at the empty log.
- **g**: a final race refuses every entry, Undo is off, its label is "Reopen First to Undo", and nothing in the file changes.
- **h**: a reopened sprint saves the order in progress. Cancel (or the Undo that cancels) and recording the correction both bring that order back. Cancel keeps the Undo of every log entry made during the correction.
- **j**: a race set up again at the empty log has no entry and is in setup, and its roster is the field (or the teams' riders) the file holds. The dead rows of the earlier run stay in the log, and every other check holds over the new run.
