"""What a scorer types or pastes, made safe to store: one line of text, and whole numbers.

Names arrive typed, pasted from a spreadsheet or an email, and imported
from BikeReg. A pasted line separator (U+2028) would wrap a rider's card
onto two clipped lines, a right-to-left override (U+202E) would reverse
the rest of the log line it was in, and a name of zero-width spaces
would save as a rider nobody could see. So a name is cleaned to one line:
control characters, line and paragraph separators and tabs become a
space, the invisible format characters that only steer or hide text are
dropped, runs of spaces become one, and the ends are trimmed. The
joiners (U+200C, U+200D) stay, because emoji sequences and some scripts
need them to draw correctly.

``str.isdigit`` is true for "²" and "¹⁹⁹⁰", which ``int`` then refuses,
so every typed number is read here, from ASCII digits only.
"""

import unicodedata

# Format characters that steer or hide text rather than spell it: the
# bidirectional embeddings, overrides and isolates, the marks, the
# zero-width space and no-break space, the word joiner and the byte
# order mark. U+200C and U+200D are kept (see the module docstring).
_DROPPED = frozenset(
    chr(c) for c in (0x061C, 0x200B, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2060, 0x2065))
) | frozenset(chr(c) for c in (*range(0x2066, 0x206A), 0xFEFF))
# The joiners and the variation selectors draw nothing on their own.
_INVISIBLE = frozenset(chr(c) for c in (0x200C, 0x200D, 0x034F, *range(0xFE00, 0xFE10)))

# The highest bib a plate carries. The roster cell, the import and the
# store all hold to it: a held-down key or a spreadsheet's 1e30 must be
# refused where it is typed, never stored or overflow SQLite's integer.
BIB_MAX = 9999

# The longest a name or a label is kept: a stray paste of a whole page
# into a name field is cut here rather than stored and drawn.
MAX_TEXT = 200


def clean_line(text: object, limit: int = MAX_TEXT) -> str:
    """``text`` as one trimmed line, with nothing in it that steers or hides the text."""
    if text is None:
        return ""
    out = []
    for ch in str(text):
        if ch in _DROPPED:
            continue
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Zl", "Zp", "Zs") or ch.isspace():
            out.append(" ")
        elif cat == "Cs":
            # A lone surrogate (a broken paste) cannot be written as UTF-8.
            continue
        elif cat == "Co" or cat == "Cn":
            # Private-use and unassigned code points draw as a box at best.
            continue
        else:
            out.append(ch)
    line = " ".join("".join(out).split())
    return line[:limit].rstrip()


def is_blank(text: object) -> bool:
    """True when ``text`` would show nothing: empty, spaces, or only invisible marks."""
    line = clean_line(text)
    return not any(
        ch not in _INVISIBLE and unicodedata.category(ch) not in ("Mn", "Me", "Cf") for ch in line
    )


def read_int(text: object, low: int, high: int) -> int | None:
    """The whole number ``text`` spells in ASCII digits within low..high, else None."""
    value = str(text if text is not None else "").strip()
    if not value or len(value) > 9 or not (value.isascii() and value.isdigit()):
        return None
    number = int(value)
    return number if low <= number <= high else None


def is_ascii_digits(text: str) -> bool:
    return bool(text) and text.isascii() and text.isdigit()


# The scorer's sentence for a USAC License that is not a number.
LICENSE_RULE = "A USAC License is a number; leave it blank if the rider has none."


def usac_license(text: object) -> str | None:
    """The USAC License ``text`` spells, as USAC prints it, or None when it spells none.

    USAC's own results print a license without leading zeros, and a
    spreadsheet (or a hand copying from one) pads it to "0710004", so the
    zeros go here: the one spelling is what an import matches against the
    riders on file. Spaces inside are a typist's grouping. A number of
    only zeros is no license. Text that is not a number ("INTL-CAN",
    "pending") is refused with ``LICENSE_RULE``, because the USAC CSV
    carries this column and only a number uploads.
    """
    value = clean_line(text).replace(" ", "")
    if not value:
        return None
    if not is_ascii_digits(value):
        raise ValueError(LICENSE_RULE)
    return value.lstrip("0") or None


def filter_words(text: object) -> list[str]:
    """The words a filter box holds, ready for ``matches_filter``."""
    return str(text if text is not None else "").casefold().split()


def matches_filter(words: list[str], text: str, bib: int | None = None) -> bool:
    """True when every typed word is somewhere in ``text``, case-insensitively.

    One rule for every filter box, so a habit learned in one works in
    the rest: "Maya P" and "akis" both find Maya Petrakis. A word
    written "#7" is bib 7 alone, never #17 or #70, and finds nobody in a
    list that has no bibs.
    """
    text = text.casefold()
    for word in words:
        if word.startswith("#") and is_ascii_digits(word[1:]):
            if bib != int(word[1:]):
                return False
        elif word not in text:
            return False
    return True
