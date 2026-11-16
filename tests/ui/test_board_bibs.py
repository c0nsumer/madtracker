"""The venue setting "Show bib numbers on the scoreboard", in every layout."""

import pytest
from apps import dispose_app

from madtracker.board import payloads as P
from madtracker.control import venue
from madtracker.store import Store

# Invented riders with bibs no sprint value, rank or total can collide with.
ROSTER = [
    P.Entry(bibs=["701"], names=["Ada Quillfeather"]),
    P.Entry(bibs=["702"], names=["Bram Oduya"]),
    P.Entry(bibs=["703"], names=["Cleo Varga"]),
    P.Entry(bibs=["704"], names=["Dov Ristanen"]),
]
BIBS = {"701", "702", "703", "704"}
# The same riders as two Madison teams, for the team start list.
TEAMS = [
    P.Entry(
        bibs=["701", "702"], names=ROSTER[0].names + ROSTER[1].names, team="Blue", color="#2f6bff"
    ),
    P.Entry(
        bibs=["703", "704"], names=ROSTER[2].names + ROSTER[3].names, team="Red", color="#e5323b"
    ),
]
HEADER = P.Header(title="Test Race", group="Cat 3", status="Racing")


def _layouts() -> list[tuple[str, object]]:
    rows = [
        P.StandingRow(rank=i + 1, entry=e, sprints=[3 - i if i < 3 else 0], total=3 - i)
        for i, e in enumerate(ROSTER)
    ]
    placings = [P.Placing(i + 1, e) for i, e in enumerate(ROSTER)]
    return [
        ("pre_race", P.PreRace(header=HEADER, roster=ROSTER)),
        ("pre_race", P.PreRace(header=HEADER, roster=TEAMS)),
        (
            "elimination",
            P.Elimination(
                header=HEADER,
                remaining=ROSTER[:2],
                last_eliminated=ROSTER[2],
                eliminated=[ROSTER[3]],
            ),
        ),
        (
            "sprint_points",
            P.Standings(
                header=HEADER,
                sprint_count=1,
                rows=rows,
                current_sprint=1,
            ),
        ),
        ("finish", P.Finish(header=HEADER, placings=placings)),
        (
            "between",
            P.Between(
                header=HEADER,
                next_title="Next Race",
                next_roster=ROSTER,
                last_title="Last Race",
                last_placings=placings,
            ),
        ),
    ]


@pytest.fixture
def drawn(monkeypatch):
    """Every string the board paints, through the theme's text and plate helpers."""
    from madtracker.board import theme

    seen: list[str] = []
    text, plate = theme.text, theme.plate

    def record_text(p, rect, s, *args, **kwargs):
        seen.append(s)
        return text(p, rect, s, *args, **kwargs)

    def record_plate(p, rect, bib, out=False):
        seen.append(bib)
        return plate(p, rect, bib, out)

    monkeypatch.setattr(theme, "text", record_text)
    monkeypatch.setattr(theme, "plate", record_plate)
    return seen


@pytest.fixture
def board(qtbot):
    from madtracker.board.window import ScoreboardWindow

    w = ScoreboardWindow("Test Velodrome", "Test Event")
    qtbot.addWidget(w)
    w.resize(1920, 1080)
    return w


@pytest.mark.parametrize("name,data", _layouts(), ids=lambda v: v if isinstance(v, str) else "")
def test_layout_without_bibs_draws_names_only(board, drawn, name, data):
    board.set_show_bibs(False)
    board.set_layout(name, data)
    board.grab()
    assert not BIBS & set(drawn), name
    # Names still there: at least one rider's whole name, or both halves of it.
    words = {w for s in drawn for w in s.split()}
    assert {"Quillfeather", "Bram", "Oduya"} & words, name


@pytest.mark.parametrize("name,data", _layouts(), ids=lambda v: v if isinstance(v, str) else "")
def test_layout_with_bibs_draws_them(board, drawn, name, data):
    board.set_layout(name, data)
    board.grab()
    assert BIBS & set(drawn), name


def test_rider_label_defaults_to_bibs_and_names_and_round_trips_through_settings(qtbot, tmp_path):
    from madtracker.ui.settings import SettingsDialog

    store = Store.open(tmp_path / "v.sqlite")
    try:
        assert venue.rider_label(store) == "bibs_names" and venue.show_bibs(store) is True
        d = SettingsDialog(store, tmp_path)
        qtbot.addWidget(d)
        assert d.rider_label.currentData() == "bibs_names"
        assert [d.rider_label.itemText(i) for i in range(3)] == [
            "Names Only",
            "Bibs and Names",
            "Bibs Only",
        ]
        d.rider_label.setCurrentIndex(d.rider_label.findData("names"))
        d.save()
        assert store.get_setting(venue.RIDER_LABEL_KEY) == "names"
        assert venue.show_bibs(store) is False
        again = SettingsDialog(store, tmp_path)
        qtbot.addWidget(again)
        assert again.rider_label.currentData() == "names"
        # Saving without the choice leaves it as it was.
        venue.save(store, logo="", name="", backup="")
        assert venue.rider_label(store) == "names"
        venue.save(store, name="", backup="", keep_logo=True, rider_label="bibs")
        assert venue.rider_label(store) == "bibs"
    finally:
        store.close()


@pytest.mark.parametrize("name,data", _layouts(), ids=lambda v: v if isinstance(v, str) else "")
def test_layout_with_bibs_only_draws_no_names(board, drawn, name, data):
    board.set_rider_label("bibs")
    board.set_layout(name, data)
    board.grab()
    assert BIBS & set(drawn), name
    words = {w for s in drawn for w in s.split()}
    assert not {"Quillfeather", "Oduya", "Varga", "Ristanen"} & words, name


def test_app_applies_the_setting_to_the_board(qapp, tmp_path):
    from PySide6.QtCore import QSettings

    from madtracker.app import AppController

    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    c = AppController(qapp, demo=True, settings=settings, data_dir=tmp_path / "data")
    try:
        assert all(page.show_bibs for page in c.board.pages.values())
        c.store.set_setting(venue.RIDER_LABEL_KEY, "names")
        c.store.set_setting(venue.ACCENT_KEY, "#38d1c4")
        c.apply_venue()
        assert not any(page.show_bibs for page in c.board.pages.values())
        from madtracker.board import theme

        assert theme.ACCENT.name() == "#38d1c4"
        theme.set_accent(None)
    finally:
        dispose_app(c)


@pytest.mark.parametrize("label", ["bibs_names", "bibs", "names"])
@pytest.mark.parametrize("name", ["pre_race", "between"])
def test_a_rider_without_a_bib_is_named_with_no_plate(board, drawn, monkeypatch, name, label):
    """The start list of a race still waiting for a bib names that rider in every mode."""
    from madtracker.board import theme

    plates: list[str] = []
    plate = theme.plate
    monkeypatch.setattr(theme, "plate", lambda p, r, bib: plates.append(bib) or plate(p, r, bib))
    roster = [ROSTER[0], P.Entry(bibs=[], names=["Bo Nobib"])]
    data = (
        P.PreRace(header=HEADER, roster=roster)
        if name == "pre_race"
        else P.Between(header=HEADER, next_title="Next Race", next_roster=roster)
    )
    board.set_rider_label(label)
    board.set_layout(name, data)
    board.grab()
    assert "Bo Nobib" in drawn
    assert plates == ([] if label == "names" else ["701"]), "no empty plate"


@pytest.mark.parametrize("label", ["bibs_names", "bibs", "names"])
def test_a_team_rider_without_a_bib_is_named_with_no_plate(board, drawn, monkeypatch, label):
    """A Madison start list still waiting for a bib names that rider in every mode."""
    from madtracker.board import theme

    plates: list[str] = []
    plate = theme.plate
    monkeypatch.setattr(theme, "plate", lambda p, r, bib: plates.append(bib) or plate(p, r, bib))
    team = P.Entry(
        bibs=["701"], names=["Ada Quillfeather", "Bo Nobib"], team="Blue", color="#2f6bff"
    )
    board.set_rider_label(label)
    board.set_layout("pre_race", P.PreRace(header=HEADER, roster=[team]))
    board.grab()
    assert "Nobib" in drawn
    assert plates == ([] if label == "names" else ["701"]), "no empty plate"
