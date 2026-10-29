"""Child process for the kill test: append actions forever, acknowledge each on stdout.

Each printed action_id is the equivalent of the UI's acknowledgement to
the scorer: it is written only after append_action() has returned, that
is, after COMMIT. The parent kills this process without warning and
checks that every acknowledged id survived. Not a test module itself
(no test_ prefix), so pytest does not collect it.
"""

import sys

from madtracker.store import Store


def main(path: str) -> None:
    store = Store.open(path)
    event = store.add_event("kill test", "2026-01-01")
    race = store.add_race(event.event_id, "kill race", "placings")
    n = 0
    while True:
        n += 1
        action_id = store.append_action(race.race_id, "note", {"n": n}, 1)
        sys.stdout.write(f"{action_id}\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main(sys.argv[1])
