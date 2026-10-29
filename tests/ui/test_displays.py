"""Scoreboard screen choice: pure rules, no Qt."""

from madtracker.displays import ScreenInfo, choose_scoreboard_screen, screen_label

LAPTOP = ScreenInfo("eDP-1", 0, 0, 1600, 900, is_primary=True)
TV = ScreenInfo("HDMI-1", 1600, 0, 1920, 1080)
TV2 = ScreenInfo("HDMI-2", 3520, 0, 1920, 1080)


def test_preferred_screen_wins_when_connected():
    assert choose_scoreboard_screen([LAPTOP, TV, TV2], "HDMI-2") == TV2


def test_preferred_screen_may_be_the_primary():
    # The operator's explicit pick is respected even if it is the primary.
    assert choose_scoreboard_screen([LAPTOP, TV], "eDP-1") == LAPTOP


def test_missing_preferred_falls_back_to_first_non_primary():
    assert choose_scoreboard_screen([LAPTOP, TV, TV2], "DISPLAY9") == TV


def test_no_preference_uses_first_non_primary():
    assert choose_scoreboard_screen([TV, LAPTOP], None) == TV


def test_single_display_gives_none():
    assert choose_scoreboard_screen([LAPTOP], None) is None
    assert choose_scoreboard_screen([LAPTOP], "HDMI-1") is None


def test_no_screens_gives_none():
    assert choose_scoreboard_screen([], "HDMI-1") is None


def test_friendly_label_prefers_make_and_model():
    from madtracker.displays import friendly_label

    assert (
        friendly_label("\\\\.\\DISPLAY2", "Dell Inc.", "DELL U2415", 1920, 1200, False, 1)
        == "Dell Inc. DELL U2415, 1920x1200"
    )
    # A model that already starts with the make is not doubled.
    assert friendly_label("HDMI-1", "Samsung", "Samsung Q60", 3840, 2160, False, 1) == (
        "Samsung Q60, 3840x2160"
    )


def test_friendly_label_falls_back_to_a_numbered_display():
    from madtracker.displays import friendly_label

    assert friendly_label("\\\\.\\DISPLAY1", "", "", 1366, 768, True, 0) == (
        "Display 1, 1366x768 (Primary)"
    )
    assert friendly_label("eDP-1", "", "", 1600, 900, True, 0) == "eDP-1, 1600x900 (Primary)"
    assert friendly_label("", "", "", 1920, 1080, False, 2) == "Display 3, 1920x1080"


def test_a_displays_entry_says_whether_the_board_fills_it_or_is_a_window():
    """One list under Scoreboard: a display the scoring
    window is on gets a window, any other gets the board full screen."""
    laptop = ScreenInfo(
        "eDP-1", 0, 0, 1600, 900, is_primary=True, label="Display 1, 1600x900 (Primary)"
    )
    tv = ScreenInfo("HDMI-1", 1600, 0, 1920, 1080, label="Sony TV, 1920x1080")
    assert screen_label(laptop, "eDP-1") == "Display 1, 1600x900 (Primary) (Windowed)"
    assert screen_label(tv, "eDP-1") == "Sony TV, 1920x1080 (Full Screen)"
    assert screen_label(tv, None) == "Sony TV, 1920x1080 (Full Screen)"
