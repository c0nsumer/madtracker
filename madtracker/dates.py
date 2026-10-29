"""Dates as people read them: 2026-Oct-14, never 2026-10-14.

A date shown with a number for the month can be read with the day and
month swapped (an American reads 2026-10-04 as April or October with
equal ease); a month's word cannot. The words are
fixed English, not the machine's locale, so every laptop shows the same.
What is stored, sorted or handed to another program stays ISO: the data
file, file names (which sort by name), and the USAC CSV (USAC's format).
"""

import re
from datetime import date, datetime

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def show_date(value: str | date) -> str:
    """An ISO date (or a date) as 2026-Oct-14; text that is not a date comes back as it was."""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value.strip()[:10])
        except ValueError:
            return value
    return f"{value.year}-{MONTHS[value.month - 1]}-{value.day:02d}"


def short_date(value: str | date) -> str:
    """2026-Oct-17's short form, Oct-17, for a column whose year the page already says.

    Text that is not a date comes back as ``show_date`` gives it.
    """
    shown = show_date(value)
    return shown[5:] if re.fullmatch(r"\d{4}-\w{3}-\d{2}", shown) else shown


def show_time(moment: datetime, seconds: bool = False) -> str:
    """A time of day as 9:07 PM, or 9:07:58 PM with ``seconds``, in the moment's own clock.

    The officials read the sheets, and the sheets print the time an
    announcer says it, with AM or PM; every other place a time is shown
    uses the same clock so nobody compares 21:45 with 9:45 PM.
    """
    hour = moment.hour % 12 or 12
    rest = f"{moment:%M:%S}" if seconds else f"{moment:%M}"
    return f"{hour}:{rest} {'AM' if moment.hour < 12 else 'PM'}"


def show_date_time(moment: datetime) -> str:
    """A moment as 2026-Oct-14 9:45 PM, in the moment's own clock."""
    return f"{show_date(moment.date())} {show_time(moment)}"
