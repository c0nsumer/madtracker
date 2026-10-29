"""What a scorer types or pastes: one clean line of text, and whole numbers from ASCII digits."""

import pytest

from madtracker.inputs import BIB_MAX, clean_line, is_blank, read_int

LS, PS, RLO, ZWSP, ZWJ, BOM = "\u2028", "\u2029", "\u202e", "\u200b", "\u200d", "\ufeff"


@pytest.mark.parametrize(
    ("typed", "kept"),
    [
        ("  Ann  ", "Ann"),
        (f"Ann{LS}Lee", "Ann Lee"),
        (f"Ann{PS}Lee", "Ann Lee"),
        (f"{RLO}Ann", "Ann"),
        ("Ann\tLee\r\nMore", "Ann Lee More"),
        (f"A{ZWSP}nn{BOM}", "Ann"),
        ("Ann\x00Lee\x07", "Ann Lee"),
        ("Ann   Lee", "Ann Lee"),
    ],
)
def test_a_name_is_one_trimmed_line_with_nothing_that_steers_or_hides_it(typed, kept):
    assert clean_line(typed) == kept


def test_joiners_stay_so_an_emoji_sequence_still_draws():
    family = f"\U0001f468{ZWJ}\U0001f469{ZWJ}\U0001f467"
    assert clean_line(family) == family


def test_a_paste_of_a_whole_page_is_cut():
    assert len(clean_line("x" * 10_000)) == 200


@pytest.mark.parametrize("typed", ["", "   ", ZWSP * 3, f"{ZWJ}{ZWJ}", "\u0301", "\t\n"])
def test_a_name_that_shows_nothing_is_blank(typed):
    assert is_blank(typed)


@pytest.mark.parametrize(
    ("typed", "number"),
    [
        ("12", 12),
        (" 7 ", 7),
        ("\u00b2", None),
        ("\u00b9\u2079\u2079\u2070", None),
        ("\u0663", None),
        ("\uff11\uff12", None),
        ("1e9", None),
        ("inf", None),
        ("-0", None),
        ("0", None),
        (str(BIB_MAX + 1), None),
        ("9" * 30, None),
    ],
)
def test_a_typed_number_is_ascii_digits_in_range(typed, number):
    assert read_int(typed, 1, BIB_MAX) == number
