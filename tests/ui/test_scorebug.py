"""The score sequence model: when each total slams, holds, swaps and reorders."""

from __future__ import annotations

from madtracker.board.motion import ease_out
from madtracker.board.scorebug import (
    REORDER_MS,
    RUSH,
    STEP_MS,
    SWAP_AT_MS,
    SWAP_MS,
    Play,
    ScoreQueue,
    Step,
    duration,
)

A, B = ("A",), ("B",)
LAND = SWAP_AT_MS + SWAP_MS


def play(*steps, before=(A, B), after=(A, B)) -> Play:
    return Play(steps=tuple(steps), before=tuple(before), after=tuple(after))


def test_one_step_slams_holds_then_swaps_to_the_new_total():
    q = ScoreQueue()
    q.push(play(Step(A, 23, 28, 1, 1)), now=0)
    assert q.frame(100).totals[A] == 23 and A in q.frame(100).chips
    assert q.frame(SWAP_AT_MS + 1).totals[A] == 28
    assert q.frame(LAND + 1) is None


def test_chips_count_ms_into_their_step():
    q = ScoreQueue()
    q.push(play(Step(A, 0, 5, 0, 0), Step(B, 0, 5, 0, 0)), now=0)
    f = q.frame(STEP_MS + 50)
    assert f.chips[B] == 50 and f.chips[A] == STEP_MS + 50


def test_a_sprint_plays_one_team_at_a_time_in_order():
    q = ScoreQueue()
    q.push(play(Step(A, 0, 5, 0, 0), Step(B, 0, 3, 0, 0)), now=0)
    assert B not in q.frame(STEP_MS - 1).chips
    assert B in q.frame(STEP_MS + 1).chips
    assert q.frame(STEP_MS + 1).totals[B] == 0
    assert q.frame(STEP_MS + 1).totals[A] == 5


def test_rows_reorder_only_after_the_last_total_lands():
    p = play(
        Step(A, 0, 5, 0, 0),
        Step(B, 0, 9, 0, 0),
        before=(A, B),
        after=(B, A),
    )
    q = ScoreQueue()
    q.push(p, now=0)
    start = STEP_MS + LAND
    assert q.frame(start - 1).rows == {A: 0, B: 1}
    mid = q.frame(start + REORDER_MS / 2).rows
    assert mid[A] == 0 + ease_out(0.5) and mid[B] == 1 - ease_out(0.5)
    assert q.frame(start + REORDER_MS - 1).rows[A] > 0.99
    assert duration(p) == STEP_MS + LAND + REORDER_MS
    assert q.frame(duration(p) + 1) is None


def _plays():
    return [
        play(Step(A, 0, 5, 0, 0)),
        play(Step(A, 5, 8, 0, 0)),
        play(Step(A, 8, 9, 0, 0)),
    ]


def test_queued_plays_run_at_double_speed_and_end_on_the_newest_totals():
    p1, p2, p3 = _plays()
    q = ScoreQueue()
    q.push(p1, now=0)
    q.push(p2, now=100)
    q.push(p3, now=200)
    # p1 runs real time to 200, then RUSH while two wait; p2 and p3 then
    # run real time because at most one waits behind each.
    end = 200 + (duration(p1) - 200) / RUSH + duration(p2) + duration(p3)
    assert q.busy(end - 1)
    assert q.frame(end - 1).totals[A] == 9
    assert not q.busy(end + 1)
    assert q.frame(end + 1) is None


def test_the_queue_is_faster_than_real_time_while_two_wait():
    p1, p2, p3 = _plays()
    q = ScoreQueue()
    q.push(p1, now=0)
    q.push(p2, now=0)
    q.push(p3, now=0)
    # Real time would leave p1 500 ms in; RUSH leaves it 1000 in.
    assert q.frame(500).chips[A] == 500 * RUSH


def test_one_waiting_play_gets_no_speed_up():
    p1, p2, _ = _plays()
    q = ScoreQueue()
    q.push(p1, now=0)
    q.push(p2, now=0)
    assert q.frame(1000).chips[A] == 1000
    end = duration(p1) + duration(p2)
    assert q.busy(end - 1)
    assert not q.busy(end + 1)


def test_cancel_drops_the_playing_and_waiting_plays():
    p1, p2, _ = _plays()
    q = ScoreQueue()
    q.push(p1, now=0)
    q.push(p2, now=0)
    q.cancel()
    assert q.frame(10) is None and not q.busy(10)


def test_push_on_an_idle_queue_starts_at_now():
    q = ScoreQueue()
    q.push(play(Step(A, 0, 5, 0, 0)), now=5000)
    assert q.frame(5100).chips[A] == 100


def test_a_loss_reads_with_the_board_minus():
    assert Step(A, 6, -14, 0, -1).text == "−20"
    assert Step(A, 6, 11, 0, 0).text == "+5"
    assert Step(A, 6, 11, 0, 0).gain and not Step(A, 6, -14, 0, -1).gain
