# Scoring hand tools

These are three checks on the scoring that are too slow, too random, or too noisy to live in the test suite. They're hand tools: run them before a release and after any change under `madtracker/scoring/` (or `madtracker/control/multi_race.py`, for the multi-race oracle). They're never suite tests, and pytest never collects them. The suite's `testpaths` is `tests`, so a bare `pytest` never looks in `tools/`. The few pytest files here are named `cases_*.py` rather than `test_*.py`, so even `pytest tools/` collects nothing. They run only when named on the command line.

Every command below runs from the repo root with the venv active (`source .venv/bin/activate`). Each one writes its output under the system temp directory (`madtracker-scoring/` in it) unless you pass another folder, so a run never leaves files in the repo. Delete that folder when you're done with it.

The tools are the project's own code, under its MIT license. None of it borrows from a third-party source.

## Scoring oracle

`oracle/oracle.py` is a second scorer for every format, written from the rule register (`docs/scoring-rules.md`), the research notes in `docs/research/`, and the USAC rulebook, without reading the engine modules. `oracle/gen.py` builds seeded random races one action at a time and offers each action to the engine's own validation first, so every log is one the scorer could enter. An entry the window never offers (a mark other than DQ on a rider already marked) is not offered to either side, since the controller refuses it before the engine sees it; the report counts those under `unoffered`. `oracle/compare.py` scores each race both ways and reports every distinct disagreement, shrunk to its smallest repro.

What it proves: over many thousands of legal logs per format, the engines and an independent reading of the rules give the same ranks, statuses, totals, laps, and final places.

```bash
python tools/scoring/oracle/compare.py 10000                      # every format, ~35 s
python tools/scoring/oracle/compare.py 100000 win_and_out         # one format, deeper
python tools/scoring/oracle/compare.py --out DIR 10000            # the report in DIR
python tools/scoring/oracle/probes.py                             # hand probes; read the output
```

The families are `placings`, `points`, `madison`, `tempo`, `elimination`, `win_and_out`, and `aggregate`. A run is ~3.5 s per 1,000 seeds across all seven, so 10,000 is ~35 s and 100,000 is ~6 minutes.

A clean result prints `0 distinct` on every family line, ends with `0 distinct discrepancies`, and exits 0. Otherwise `discrepancies.md` in the output folder lists each disagreement with its seed and its smallest log. A disagreement is either an engine defect or a wrong oracle: read the rule row the oracle cites (its `AMBIGUITY:` notes mark where the register leaves a choice) and decide which. Fix whichever is wrong, and never change the engine without its test.

## Multi-race oracle

`multi_race_oracle/oracle.py` computes Multi-Race Standings independently from the store and each race's engine result. It covers which races count, who rode, the team minimum, the place tables, the Four-Race table, penalties, the countback, and the Final state, and it never imports `madtracker/control/multi_race.py`. `multi_race_oracle/season.py` builds random seasons scored through `LiveRace`, the surface's own path. `multi_race_oracle/compare.py` diffs the two over many seeds.

What it proves: for random seasons of every kind, `multi_race.compute` and an independent reading of the register give the same tables.

```bash
python tools/scoring/multi_race_oracle/compare.py --seeds 2000                 # ~3 minutes
python tools/scoring/multi_race_oracle/compare.py --seeds 500 --kind four_race_omnium --strict
python tools/scoring/multi_race_oracle/compare.py --seed 123 --dump            # one seed, both tables
python tools/scoring/multi_race_oracle/compare.py --seeds 150 --mutate dnf-out # self-check
```

A seed takes ~0.1 s. A clean result ends with `core mismatches: 0 []`, `display-only: 0 []`, and `crashes: 0 []`, and exits 0. The exit code is the number of failing seeds (capped at 125). A failing seed's folder is kept under `--basetemp` with a `diff.txt`, and `--seed N --dump` reproduces it. Display differences (names, bibs, colors, group spelling, the count line) fail only with `--strict`.

`--mutate` breaks the program on purpose, one rule at a time (`no-countback`, `beyond-table`, `no-minimum`, `dnf-out`, `twenty-first`, `penalty-after`), to show the oracle catches it. A self-check run is supposed to report mismatches. `twenty-first` and `penalty-after` are rare by nature, so they need a few hundred seeds or more.

The hand cases are tables worked out by hand and checked against both the program and the oracle (so a wrong oracle fails here too). `cases_questions.py` keeps decided readings of the design checked. They borrow the suite's fixtures and race builders from `tests/control/test_multi_race.py` through this folder's `conftest.py`:

```bash
pytest -q -p no:cacheprovider tools/scoring/multi_race_oracle/cases_hand.py tools/scoring/multi_race_oracle/cases_questions.py
```

This takes a few seconds. A clean result is every case passing.

## Mutation runner

`mutate/mutator.py` makes small wrong versions of the scoring engines from their syntax trees: a `<` for a `<=`, a `+` for a `-`, a constant off by one, a negated `if`, `max` for `min`, and so on. `mutate/run.py` runs `tests/scoring` against each mutant, one at a time. A mutant the tests fail on is killed. One they pass is a survivor: either the tests miss a behavior, or the mutant behaves the same as the original.

What it proves: how much of the engines' logic `tests/scoring` actually pins down, and exactly which lines it doesn't.

```bash
python tools/scoring/mutate/run.py --workers 3                    # 743 mutants, ~22 minutes
python tools/scoring/mutate/run.py --modules win_and_out          # one engine
python tools/scoring/mutate/probe_survivors.py                    # which survivors random input exposes
python tools/scoring/mutate/mutator.py madtracker/scoring/*.py    # count the sites per module
```

Each worker gets its own copy of `madtracker/`, `tests/`, and `pyproject.toml` under the output folder (`--out`, which defaults to `madtracker-scoring/mutate` under the temp directory). A mutant is only ever written into a copy, never into your checkout, so a run killed halfway leaves nothing broken behind. Two details keep the results honest:

- PYTHONPATH: the venv's editable install points at the main checkout, so Python imports that unless PYTHONPATH puts the copy first. The runner sets PYTHONPATH to the copy for every run, and it checks that `madtracker.scoring` really imports from the copy before it counts anything. If it doesn't, it stops. A run against the wrong code would report every mutant as a survivor.
- `__pycache__`: the runner clears `madtracker/scoring/__pycache__` in the copy before and after each mutant, and runs with `PYTHONDONTWRITEBYTECODE=1`. A mutant written in the same second as the original, at the same size, would otherwise be shadowed by the original's stale `.pyc` and survive without being tested.

The runner also runs `tests/scoring` unmutated in each copy first, and it stops if that baseline fails. Each mutant's run is killed after 120 s. Results append to `results.jsonl` in the output folder, and a site already there is skipped, so a run cut short resumes where it stopped. Logs are kept only for mutants that weren't killed.

A run ends with a table per module (mutants, killed, survived, timeout, import error) and one line per survivor. There's no fixed clean number. A clean result is no timeouts, no import errors, and no new survivors beyond the ones already judged equivalent. For each new survivor, `probe_survivors.py` says whether some random input tells it from the original (an exposed survivor is a missing test). A case written to kill an exposed survivor goes into `tests/scoring/`, where the next run proves it. The probe takes about a second per survivor at its default of 600 scenarios.
