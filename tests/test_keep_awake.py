"""The display keep-awake request: the right Windows flags, and never an exception."""

import sys

from madtracker import keep_awake


class _Kernel32:
    def __init__(self, result: int) -> None:
        self.result = result
        self.calls: list[int] = []

    def SetThreadExecutionState(self, flags: int) -> int:  # the Win32 name
        self.calls.append(flags)
        return self.result


def test_windows_asks_for_the_display_until_the_process_ends():
    kernel32 = _Kernel32(result=keep_awake.ES_CONTINUOUS)
    assert keep_awake._hold_windows(kernel32) is True
    # ES_CONTINUOUS makes the request stick to the thread; without it the
    # call only resets the idle timer once.
    assert kernel32.calls == [
        keep_awake.ES_CONTINUOUS | keep_awake.ES_DISPLAY_REQUIRED | keep_awake.ES_SYSTEM_REQUIRED
    ]


def test_windows_refusal_is_false():
    assert keep_awake._hold_windows(_Kernel32(result=0)) is False


def test_a_failing_platform_call_is_false_not_an_exception(monkeypatch):
    def boom(*_args):
        raise OSError("no such service")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(keep_awake, "_hold_dbus", boom)
    assert keep_awake.hold("MadTracker") is False
