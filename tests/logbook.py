"""An event's log in the scorer's words, oldest first: what the tests read to check what was recorded.

The app keeps no logbook view or export; the log stays in the data file.
The tests read it through ``LiveRace.log_rows`` per race, and through
``event_log`` across an event, with a result becoming provisional or
final placed after the newest entry when it happened.
"""

from madtracker.control.race import LiveRace, LogRow, local_time
from madtracker.store import Race, Store

STATE_WORDS = {"provisional": "Provisional", "final": "Marked final"}


def state_text(from_state: str, to_state: str) -> str:
    """``Marked final``, ``Reopened``, ``Provisional``, ``No longer provisional``."""
    if from_state == "final":
        return "Reopened"
    if to_state in STATE_WORDS:
        return STATE_WORDS[to_state]
    # An Undo took back the entry that completed the result.
    return "No longer provisional"


def event_log(store: Store, event_id: int) -> list[LogRow]:
    """Every entry across the event's races, and each change of result state, oldest first."""
    out: list[tuple[tuple[int, int, int], LogRow]] = []
    for race in store.races(event_id):
        if store.last_action(race.race_id) is not None:
            out.extend(_race_log(store, race))
    out.sort(key=lambda pair: pair[0])
    return [line for _, line in out]


def _race_log(store: Store, race: Race) -> list[tuple[tuple[int, int, int], LogRow]]:
    try:
        live = LiveRace(store, race.race_id)
    except ValueError:
        return []
    out = []
    for row, line in zip(store.actions(race.race_id), live.log_rows(), strict=True):
        out.append(
            (
                (row.action_id, 0, 0),
                LogRow(line.time, line.text, line.voided, race.race_id, race.name),
            )
        )
    for change in store.state_changes(race.race_id):
        time = local_time(change.recorded_utc)
        text = state_text(change.from_state, change.to_state)
        out.append(
            (
                (change.after_action_id, 1, change.change_id),
                LogRow(time, text, False, race.race_id, race.name),
            )
        )
    return out
