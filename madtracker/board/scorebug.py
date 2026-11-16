"""The score sequence for the Madison table: when each total changes.

A play is one sprint's score changes. Each team's points slam onto its
total, hold, and the new total rises in; a sprint plays one team at a
time in sprint order, and the rows reorder only after the last total has
landed. This module is timing only, with no painting, so the rules are
tested without a display.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from madtracker.board.motion import ease_out, phase
from madtracker.board.payloads import MINUS

SLAM_MS = 260
OLD_OUT_MS = 160
RING_AT_MS = 182
RING_MS = 320
SHEEN_MS = 420
SWAP_AT_MS = 1160
SWAP_MS = 380
# One team's whole step; the next team's step starts when it ends.
STEP_MS = 1160
REORDER_MS = 600
# Queue speed while two or more plays wait behind the one playing, so a
# burst of sprints catches up to the newest totals.
RUSH = 2.0

Key = tuple[str, ...]


@dataclass(frozen=True)
class Step:
    key: Key
    old: int
    new: int
    old_laps: int
    new_laps: int

    @property
    def gain(self) -> bool:
        return self.new > self.old

    @property
    def text(self) -> str:
        d = self.new - self.old
        return f"+{d}" if d > 0 else f"{MINUS}{-d}"


@dataclass(frozen=True)
class Play:
    steps: tuple[Step, ...]
    # Row order (keys top to bottom) before and after the play.
    before: tuple[Key, ...]
    after: tuple[Key, ...]


@dataclass(frozen=True)
class Frame:
    # What each cell shows: the old value until its step's swap starts.
    totals: dict[Key, int]
    laps: dict[Key, int]
    # Ms into the key's step, while its chip or swap shows.
    chips: dict[Key, float]
    # Fractional row index per key.
    rows: dict[Key, float]


def _reorder_at(play: Play) -> float:
    return (len(play.steps) - 1) * STEP_MS + SWAP_AT_MS + SWAP_MS


def duration(play: Play) -> float:
    return _reorder_at(play) + (REORDER_MS if play.before != play.after else 0)


def _frame_at(play: Play, t: float) -> Frame:
    totals: dict[Key, int] = {}
    laps: dict[Key, int] = {}
    chips: dict[Key, float] = {}
    for i, step in enumerate(play.steps):
        local = t - i * STEP_MS
        landed = local >= SWAP_AT_MS
        totals[step.key] = step.new if landed else step.old
        laps[step.key] = step.new_laps if landed else step.old_laps
        if 0 <= local < SWAP_AT_MS + SWAP_MS:
            chips[step.key] = local
    k = ease_out(phase(t, _reorder_at(play), REORDER_MS))
    after = {key: i for i, key in enumerate(play.after)}
    rows = {key: i + (after.get(key, i) - i) * k for i, key in enumerate(play.before)}
    return Frame(totals, laps, chips, rows)


class ScoreQueue:
    """Plays one sprint at a time and speeds up when plays pile up.

    A play that waits keeps its own steps as built: the caller builds it
    against the totals the play ahead ends on.
    """

    def __init__(self) -> None:
        self._playing: Play | None = None
        self._elapsed = 0.0  # queue time into the playing play
        self._synced = 0.0  # real time the state is current to
        self._waiting: deque[Play] = deque()

    def push(self, play: Play, now: float) -> None:
        self._advance(now)
        if self._playing is None:
            self._playing = play
            self._elapsed = 0.0
            self._synced = now
        else:
            self._waiting.append(play)

    def cancel(self) -> None:
        self._playing = None
        self._waiting.clear()

    def busy(self, now: float) -> bool:
        self._advance(now)
        return self._playing is not None

    def frame(self, now: float) -> Frame | None:
        self._advance(now)
        if self._playing is None:
            return None
        return _frame_at(self._playing, self._elapsed)

    def _advance(self, now: float) -> None:
        """Bring the state to real time ``now``, finishing plays on the way."""
        while self._playing is not None and self._synced < now:
            speed = RUSH if len(self._waiting) >= 2 else 1.0
            left = duration(self._playing) - self._elapsed
            if left <= (now - self._synced) * speed:
                self._synced += left / speed
                if self._waiting:
                    self._playing = self._waiting.popleft()
                    self._elapsed = 0.0
                else:
                    self._playing = None
            else:
                self._elapsed += (now - self._synced) * speed
                self._synced = now
        if self._playing is None:
            self._synced = max(self._synced, now)
