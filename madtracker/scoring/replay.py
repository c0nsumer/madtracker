"""Replay: standings from a race's format, rules and live action log.

The store hands over the ordered live actions (voids removed) and this
module picks the engine. A race records RULES_VERSION next to its rules
JSON so a replay with later code can say which rule text it was scored
under; bump it whenever an engine's answer for an existing log could
change.
"""

from collections.abc import Iterable, Mapping, Sequence
from types import ModuleType
from typing import Any

from . import aggregate, elimination, placings, sprint_points, win_and_out
from ._common import RESULTS_STAND_REFUSAL, SHORTEN_REFUSAL
from .actions import Action, RaceEnded, RaceShortened, decode_action
from .result import Standings
from .rules import AggregateRules, _Rules

RULES_VERSION = "2026.10.1"

ENGINES: dict[str, ModuleType] = {
    "placings": placings,
    "elimination": elimination,
    "sprint_points": sprint_points,
    "win_and_out": win_and_out,
}

# Format keys the UI shows, mapped to the engine that scores them. The
# format is what the sheet prints; the engine is how it is ranked.
FORMAT_ENGINE: dict[str, str] = {
    "scratch": "placings",
    "chase": "placings",
    "unknown_distance": "placings",
    "chariot": "placings",
    "handicap": "placings",
    "keirin": "placings",
    "match_sprint": "placings",
    "placings": "placings",
    "points": "sprint_points",
    "madison": "sprint_points",
    "tempo": "sprint_points",
    "sprint_points": "sprint_points",
    "elimination": "elimination",
    "win_and_out": "win_and_out",
}


# The formats whose stoppage table has "Race stopped after 80%: Let results
# stand" (USAC 2M6, 2N5). The Tempo Race shares the engine but not the
# table: USAC 2P5 restarts a stopped Tempo Race with its points, or reruns
# it, so the entry is refused there by format.
RESULTS_STAND_FORMATS = frozenset({"points", "madison", "sprint_points"})

# The formats with a sprint count to shorten (USAC 1G4(b)): every format
# the sprint-points engine scores, the Tempo Race included, since a
# shortened race rides on to its new finish rather than stopping.
SHORTEN_FORMATS = frozenset(k for k, engine in FORMAT_ENGINE.items() if engine == "sprint_points")


def engine_for(format_key: str) -> ModuleType:
    try:
        return ENGINES[FORMAT_ENGINE[format_key]]
    except KeyError:
        raise ValueError(f"Unknown race format {format_key!r}") from None


def _check_rules(engine: ModuleType, rules: _Rules) -> None:
    name = next(k for k, v in ENGINES.items() if v is engine)
    if rules.engine != name:
        raise TypeError(f"{type(rules).__name__} cannot score a {name} race")


def compute_for_format(
    format_key: str, rules: _Rules, entrants: Sequence[int], actions: Sequence[Action]
) -> Standings:
    engine = engine_for(format_key)
    _check_rules(engine, rules)
    return engine.compute(rules, entrants, actions)


def validate_for_format(
    format_key: str,
    rules: _Rules,
    entrants: Sequence[int],
    actions: Sequence[Action],
    new_action: Action,
) -> list[str]:
    engine = engine_for(format_key)
    _check_rules(engine, rules)
    if isinstance(new_action, RaceEnded) and format_key not in RESULTS_STAND_FORMATS:
        return [RESULTS_STAND_REFUSAL]
    if isinstance(new_action, RaceShortened) and format_key not in SHORTEN_FORMATS:
        return [SHORTEN_REFUSAL]
    return engine.validate(rules, entrants, actions, new_action)


def compute_aggregate(
    rules: AggregateRules,
    entrants: Sequence[int],
    races: Sequence[Standings],
    penalties: Mapping[int, int] | None = None,
) -> Standings:
    return aggregate.compute(rules, entrants, races, penalties)


def actions_from_rows(rows: Iterable[tuple[str, int, Mapping[str, Any]]]) -> list[Action]:
    """Decode the store's (kind, schema_ver, payload) rows in order."""
    return [decode_action(kind, schema_ver, payload) for kind, schema_ver, payload in rows]
