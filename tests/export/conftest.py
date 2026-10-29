"""A tmp store with one event, four invented riders and four finished races."""

import pytest

import madtracker.export.pdf as pdf_mod
from madtracker.control.race import LiveRace
from madtracker.scoring import rules as R
from madtracker.store import Store

RIDERS = (
    (1, "Ada", "Wren", "100001"),
    (2, "Zoe", "Łukasik", "100002"),
    (3, "Bo", "Tran", None),
    (4, "Cy", "Park", "100004"),
)


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "export.sqlite")
    yield s
    s.close()


@pytest.fixture
def event(store):
    m = store.add_event("Friday Night Test", "2026-03-06", venue="Test Velodrome")
    ids = {}
    for bib, first, last, lic in RIDERS:
        rider = store.add_rider(first, last, usac_license=lic)
        store.add_entry(m.event_id, rider.rider_id, bib, local_group="Cat 3")
        ids[bib] = rider.rider_id
    return m.event_id, ids


def _race(store, event, name, fmt, bibs, rules, **kw):
    event_id, ids = event
    race = store.add_race(event_id, name, fmt, rules=rules.to_dict(), **kw)
    for bib in bibs:
        store.add_race_entry(race.race_id, ids[bib])
    return race


@pytest.fixture
def seeded(store, event):
    """Returns race ids: chase (tie), points (DNF), madison (2 teams), elimination (unfinished)."""
    event_id, ids = event
    chase = _race(store, event, "Chase A", "chase", [1, 2, 3, 4], R.placings_rules())
    s = LiveRace(store, chase.race_id)
    for bib in (1, 2, 3):
        assert s.click(ids[bib]).ok
    assert s.tie_above(ids[3]).ok
    assert s.click(ids[4]).ok
    assert s.state == "provisional"

    pts_rules = R.SprintPointsRules(sprint_count=2)
    points = _race(
        store,
        event,
        "Points B",
        "points",
        [1, 2, 3, 4],
        pts_rules,
        group_label="Cat 3",
        usac_class="Senior",
        usac_age_group="9-14",
        usac_category="Cat 3",
        usac_gender="Women",
        usac_discipline="pr",
    )
    s = LiveRace(store, points.race_id)
    for bib in (1, 2, 3):
        assert s.click(ids[bib]).ok
    assert s.record_sprint().ok
    assert s.act(ids[1], "lap_gained").ok
    assert s.act(ids[4], "dnf").ok
    for bib in (1, 3, 2):
        assert s.click(ids[bib]).ok
    assert s.state == "provisional"

    mad_rules = R.SprintPointsRules(sprint_count=2, scored_unit="team")
    mad = _race(store, event, "Madison C", "madison", [1, 2, 3, 4], mad_rules)
    teams = {}
    for color, a, b in (("Red", 1, 2), ("Blue", 3, 4)):
        team = store.add_team(mad.race_id, color, color=color)
        store.add_team_member(team.team_id, ids[a])
        store.add_team_member(team.team_id, ids[b])
        teams[color] = team.team_id
    s = LiveRace(store, mad.race_id)
    assert s.click(teams["Red"]).ok and s.click(teams["Blue"]).ok
    assert s.record_sprint().ok
    assert s.click(teams["Blue"]).ok and s.click(teams["Red"]).ok
    assert s.state == "provisional"

    elim = _race(store, event, "Elimination D", "elimination", [1, 2, 3, 4], R.elimination_rules())
    return {
        "chase": chase.race_id,
        "points": points.race_id,
        "mad": mad.race_id,
        "elim": elim.race_id,
    }


@pytest.fixture
def drawn(monkeypatch):
    """Every cell the PDF draws: text, font size, box, and the drawn text width.

    Glyph streams are not greppable, so the tests read what went into each
    cell instead.
    """
    seen = []
    original = pdf_mod._Doc.cell

    def cell(self, *args, **kwargs):
        w = kwargs.get("w", args[0] if args else 0)
        h = kwargs.get("h", args[1] if len(args) > 1 else 0)
        text = kwargs.get("text") or (args[2] if len(args) > 2 else "")
        seen.append(
            {
                "text": text,
                "size": self.font_size_pt,
                "x": self.get_x(),
                "y": self.get_y(),
                "w": w,
                "h": h,
                "width": self.get_string_width(text),
                "page": self.page_no(),
                "margin": self.c_margin,
                "page_w": self.w,
                "page_h": self.h,
            }
        )
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pdf_mod._Doc, "cell", cell)
    return seen
