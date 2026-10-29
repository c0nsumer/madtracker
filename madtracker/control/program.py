"""The program as a list to edit: what a race's Edit, Duplicate, Move and Remove may do, and the reorder.

The setup screen's buttons for a race ask here what they may do, so a
disabled button carries its reason and a Move swaps the right two rows.
"""

from madtracker.store import Race, Store

NO_RACE = "Select a race first"
ALREADY_FIRST = "It is already first."
ALREADY_LAST = "It is already last."
RACE_ACTIONS = ("edit", "duplicate", "remove", "up", "down")


def is_scored(store: Store, race: Race) -> bool:
    """A race with an entry that stands: its format and field are fixed (design section 6).

    An entry Undo took back does not count: a race undone to its start
    list is in setup with nothing to replay, and is set up again like one
    never scored. Its dead rows stay in the log, so Remove asks
    ``ever_scored`` instead.
    """
    return race.state != "setup" or store.has_live_actions(race.race_id)


def ever_scored(store: Store, race: Race) -> bool:
    """A race with anything in its log, undone or not: it is never removed.

    Its rows and their voids are in the log for good, and the store
    refuses to delete a race or an event under them, so the screen
    offers what the store allows.
    """
    return race.state != "setup" or store.last_action(race.race_id) is not None


def race_refusals(store: Store | None, event_id: int | None, race_id: int | None) -> dict[str, str]:
    """Why Edit, Duplicate, Remove, and the up and down arrows would be refused ("" when allowed)."""
    none = dict.fromkeys(RACE_ACTIONS, NO_RACE)
    if store is None or event_id is None or race_id is None:
        return none
    races = store.races(event_id)
    index = next((i for i, r in enumerate(races) if r.race_id == race_id), None)
    if index is None:
        # Mid-refill a selected row can still hold a removed race.
        return none
    race = races[index]
    if is_scored(store, race):
        remove = f"{race.name} has been scored and cannot be removed."
    elif ever_scored(store, race):
        # Undone to its start list: nothing stands, but the log keeps
        # every entry, so the race is no longer one that was never scored.
        remove = f"{race.name} has had entries and cannot be removed."
    else:
        remove = ""
    return {
        "edit": "",
        # A scored race duplicates as well: the copy is a new race, unscored.
        "duplicate": "",
        "remove": remove,
        "up": ALREADY_FIRST if index == 0 else "",
        "down": ALREADY_LAST if index == len(races) - 1 else "",
    }


def move_race(store: Store, event_id: int, race_id: int, step: int) -> str:
    """Swap the race with its neighbor ``step`` rows away; the refusal, or "" when moved.

    Every race's sequence is renumbered so a program whose numbers have
    gaps (a removed race) comes out dense; only the rows whose number
    changed are written, all in one transaction, so a move is one commit
    and a failure leaves the order as it was.
    """
    races = store.races(event_id)
    index = next((i for i, r in enumerate(races) if r.race_id == race_id), None)
    if index is None:
        return NO_RACE
    if not 0 <= index + step < len(races):
        return ALREADY_FIRST if step < 0 else ALREADY_LAST
    order = [r.race_id for r in races]
    order[index], order[index + step] = order[index + step], order[index]
    with store.transaction():
        for seq, rid in enumerate(order, start=1):
            if store.race(rid).seq_in_event != seq:
                store.update_race(rid, seq_in_event=seq)
    return ""


def place_after(store: Store, event_id: int, race_id: int, after_id: int) -> None:
    """Put the race right after ``after_id``: a duplicate sits beside its original.

    Renumbered as a move is, in one transaction, writing only the rows
    whose number changed.
    """
    order = [r.race_id for r in store.races(event_id) if r.race_id != race_id]
    if after_id not in order:
        return
    order.insert(order.index(after_id) + 1, race_id)
    with store.transaction():
        for seq, rid in enumerate(order, start=1):
            if store.race(rid).seq_in_event != seq:
                store.update_race(rid, seq_in_event=seq)
