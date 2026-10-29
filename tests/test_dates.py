"""Dates shown with the month as a word, so day and month never swap."""

from datetime import date, datetime

from madtracker.dates import show_date, show_date_time, show_time


def test_a_date_shows_its_month_as_a_word():
    assert show_date("2026-10-04") == "2026-Oct-04"
    assert show_date(date(2027, 1, 31)) == "2027-Jan-31"
    assert show_date("2026-12-09T21:45:00") == "2026-Dec-09"
    assert show_date("not a date") == "not a date"
    assert show_date_time(datetime(2026, 5, 2, 9, 7)) == "2026-May-02 9:07 AM"


def test_every_shown_time_is_the_sheets_clock():
    """One clock, the announcer's: 12-hour with AM or PM, seconds only where the logbook keeps them."""
    assert show_time(datetime(2026, 5, 2, 0, 5)) == "12:05 AM"
    assert show_time(datetime(2026, 5, 2, 12, 0)) == "12:00 PM"
    assert show_time(datetime(2026, 5, 2, 21, 45, 12)) == "9:45 PM"
    assert show_time(datetime(2026, 5, 2, 21, 45, 12), seconds=True) == "9:45:12 PM"


def test_the_pdf_long_date_is_english_whatever_the_locale():
    import locale

    from madtracker.export.pdf import _pretty_date

    try:
        locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")
    except locale.Error:
        pass  # not installed here; the words are fixed either way
    try:
        assert _pretty_date("2026-10-14") == "Wednesday, October 14, 2026"
    finally:
        locale.setlocale(locale.LC_TIME, "")
