"""Golden tests from every race a venue's workbooks hold as scored.

Bibs only, as in test_golden_night98.py: the workbooks carry rider
names and license numbers and stay in local/scorer-files/ (gitignored). Each
test rebuilds the race as the scorer would have entered it, checks
every entry with validate_for_format before appending it, and asserts
the sheet's final standing.

Sources (file, sheet):

- test_night98_group_b_scratch: "SNR 98.xlsm", "Chase Score"
  ("2 MILE SCRATCH RACE", SemiProB).
- test_night98_group_a_scratch: "SNR 98.xlsm", "Chase Score"
  ("3 MILE SCRATCH RACE", SemiProA).
- test_night98_group_b_elimination: "SNR 98.xlsm", "Elimination Score"
  ("SEMI PRO B ELIMINATION").
- test_night98_group_a_elimination: "SNR 98.xlsm", "Elimination Score"
  ("SEMI PRO A ELIMINATION").

Already pinned in test_golden_night98.py, so not repeated here: the
night 98 Group B points race ("SNR 98.xlsm", "Point Sprint Race") and
the night 98 Group A madison ("SCORE SHEET MADISON SNR 98.xlsx",
"MADISON 5"). "MASTER RACE SCORE SHEET 20226-27 NC.xlsm" and "SCORE
SHEET MADISON MASTER 2026-27.xlsx" hold rosters and templates but no
scored race.

The sheets record only a finishing place per rider, typed by hand,
with the rows relinked into finishing order. For the eliminations the
order out is read back from those places: one rider out per sprint,
last place first, the top two riding the final sprint (USAC 2E3(e),
2E3(f)). The sheets show no laps, ties, DNF or green flags in these
races, so none are entered.
"""

from collections.abc import Sequence

from madtracker.scoring import compute_for_format, validate_for_format
from madtracker.scoring.actions import Action, Eliminated, FinishOrder
from madtracker.scoring.result import Standings
from madtracker.scoring.rules import EliminationRules, PlacingsRules, _Rules


def _score(format_key: str, rules: _Rules, bibs: Sequence[int], actions: Sequence[Action]):
    """Append each action only if the engine accepts it, so the test also
    proves the reconstructed log is one the scorer could have entered."""
    log: list[Action] = []
    for action in actions:
        problems = validate_for_format(format_key, rules, bibs, log, action)
        assert problems == [], (action, problems)
        log.append(action)
    return compute_for_format(format_key, rules, bibs, log)


def _elimination_actions(sheet_order: Sequence[int], survivors: int = 2) -> list[Action]:
    """The log behind a sheet's finishing order: last place out first."""
    out = list(reversed(sheet_order[survivors:]))
    actions: list[Action] = [Eliminated(n, [bib]) for n, bib in enumerate(out, start=1)]
    actions.append(FinishOrder([[bib] for bib in sheet_order[:survivors]]))
    return actions


def _assert_order(standings: Standings, sheet_order: Sequence[int]) -> None:
    assert [row.entrant_id for row in standings.rows] == list(sheet_order)
    assert [row.rank for row in standings.rows] == list(range(1, len(sheet_order) + 1))
    assert not any(row.tied for row in standings.rows)
    assert all(row.status is None for row in standings.rows)
    assert standings.is_complete


def test_night98_group_b_scratch():
    """Night 98 Group B, "2 MILE SCRATCH RACE": six riders, places 1 to 6."""
    sheet_order = [35, 18, 12, 4, 22, 2]
    actions = [FinishOrder([[bib] for bib in sheet_order])]
    standings = _score("scratch", PlacingsRules(), sorted(sheet_order), actions)
    _assert_order(standings, sheet_order)


def test_night98_group_a_scratch():
    """Night 98 Group A, "3 MILE SCRATCH RACE": eleven riders, places 1 to 11."""
    sheet_order = [5, 10, 7, 11, 57, 13, 29, 32, 31, 33, 17]
    actions = [FinishOrder([[bib] for bib in sheet_order])]
    standings = _score("scratch", PlacingsRules(), sorted(sheet_order), actions)
    _assert_order(standings, sheet_order)


def test_night98_group_b_elimination():
    """Night 98 Group B elimination: six riders, four out, two in the final."""
    sheet_order = [35, 18, 12, 22, 4, 2]
    rules = EliminationRules(survivors=2)
    standings = _score("elimination", rules, sorted(sheet_order), _elimination_actions(sheet_order))
    _assert_order(standings, sheet_order)
    assert standings.by_entrant(2).eliminated_at == 1
    assert standings.by_entrant(12).eliminated_at == 4
    assert standings.by_entrant(35).final_sprint_place == 1
    assert standings.by_entrant(18).final_sprint_place == 2


def test_night98_group_a_elimination():
    """Night 98 Group A elimination: eleven riders, nine out, two in the final."""
    sheet_order = [7, 10, 5, 11, 31, 13, 32, 29, 17, 33, 57]
    rules = EliminationRules(survivors=2)
    standings = _score("elimination", rules, sorted(sheet_order), _elimination_actions(sheet_order))
    _assert_order(standings, sheet_order)
    assert standings.by_entrant(57).eliminated_at == 1
    assert standings.by_entrant(5).eliminated_at == 9
    assert standings.by_entrant(7).final_sprint_place == 1
    assert standings.by_entrant(10).final_sprint_place == 2
