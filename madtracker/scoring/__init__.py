"""Pure scoring engines: (race rules, scorer actions) -> standings. No Qt, no SQLite.

Entry points the rest of the app uses:

- ``actions``: the scorer action classes and ``decode_action``.
- ``rules``: per-engine rules dataclasses, presets and ``rules_from_dict``.
- ``replay.compute_for_format`` / ``replay.validate_for_format``: score a
  race or check an entry before it is committed.
- ``replay.compute_aggregate``: standings over several races.
- ``result.Standings``: what every engine returns.
"""

from .replay import (
    RULES_VERSION,
    actions_from_rows,
    compute_aggregate,
    compute_for_format,
    validate_for_format,
)
from .result import Standing, Standings

__all__ = [
    "RULES_VERSION",
    "Standing",
    "Standings",
    "compute_aggregate",
    "compute_for_format",
    "actions_from_rows",
    "validate_for_format",
]
