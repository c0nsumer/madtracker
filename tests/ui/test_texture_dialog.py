"""The Scoreboard Texture dialog: the adjustments, their preview, and Settings' use of them."""

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton

from madtracker.board.texture import Adjust
from madtracker.control import venue
from madtracker.store import Store
from madtracker.ui import style, widgets
from madtracker.ui.settings import SettingsDialog
from madtracker.ui.texture_dialog import TextureDialog


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "v.sqlite")
    yield s
    s.close()


def _dialog(qtbot, adjust: Adjust | None = None, pattern: str = "bolts") -> TextureDialog:
    d = TextureDialog(pattern, None, adjust or Adjust())
    qtbot.addWidget(d)
    return d


def _settings(store, tmp_path, qtbot) -> SettingsDialog:
    d = SettingsDialog(store, tmp_path)
    qtbot.addWidget(d)
    return d


def _on_screen(d) -> None:
    d.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    d.show()
    QApplication.processEvents()


def _labels(d) -> list[str]:
    form = d.form
    out = []
    for row in range(form.rowCount()):
        item = form.itemAt(row, form.ItemRole.LabelRole)
        out.append(item.widget().text())
    return out


def test_the_dialog_reads_as_approved(qtbot):
    d = _dialog(qtbot)
    _on_screen(d)
    assert d.windowTitle() == "Scoreboard Texture"
    assert _labels(d) == ["Size", "Rotation", "Spacing", "Opacity", "Tone"]
    ranges = {
        "size": (50, 200, 100),
        "rotation": (-45, 45, 0),
        "spacing": (60, 200, 100),
        "opacity": (0, 200, 100),
        "tone": (-100, 100, 0),
    }
    for key, (lo, hi, default) in ranges.items():
        s = d.sliders[key]
        assert (s.minimum(), s.maximum(), s.value()) == (lo, hi, default), key
    assert d.tone_ends[0].text() == "Darker" and d.tone_ends[1].text() == "Lighter"
    left, right = d.tone_ends
    assert left.x() < d.sliders["tone"].x() < right.x()
    texts = [b.text() for b in d.findChildren(QPushButton)]
    assert texts == ["Reset", "Cancel", "OK"]
    xs = [b.mapTo(d, b.rect().topLeft()).x() for b in d.findChildren(QPushButton)]
    assert xs == sorted(xs), "Reset, then Cancel, then OK rightmost"
    assert d.ok_button.isDefault()


def test_value_readouts_follow_the_sliders(qtbot):
    d = _dialog(qtbot)
    assert [d.readouts[k].text() for k in d.sliders] == ["100%", "0°", "100%", "100%", "0"]
    d.sliders["size"].setValue(150)
    d.sliders["rotation"].setValue(30)
    d.sliders["spacing"].setValue(80)
    d.sliders["opacity"].setValue(160)
    d.sliders["tone"].setValue(-60)
    assert d.readouts["size"].text() == "150%"
    assert d.readouts["rotation"].text() == "30°"
    assert d.readouts["spacing"].text() == "80%"
    assert d.readouts["opacity"].text() == "160%"
    assert d.readouts["tone"].text() == "−60"
    d.sliders["rotation"].setValue(-15)
    assert d.readouts["rotation"].text() == "−15°"
    d.sliders["tone"].setValue(60)
    assert d.readouts["tone"].text() == "60"
    assert d.adjust() == Adjust(size=150, rotation=-15, spacing=80, opacity=160, tone=60)


def test_readouts_are_plain_text(qtbot):
    d = _dialog(qtbot)
    for label in [*d.readouts.values(), *d.tone_ends]:
        assert isinstance(label, QLabel) and label.textFormat() == Qt.TextFormat.PlainText


def test_the_preview_redraws_as_a_slider_moves(qtbot):
    d = _dialog(qtbot)
    _on_screen(d)
    before = d.preview.grab().toImage()
    d.sliders["size"].setValue(180)
    QApplication.processEvents()
    after = d.preview.grab().toImage()
    assert before != after
    d.sliders["size"].setValue(100)
    QApplication.processEvents()
    assert d.preview.grab().toImage() == before
    # No opacity draws the rows without a texture, still drawn.
    d.sliders["opacity"].setValue(0)
    assert d.preview.texture is None
    assert d.preview.grab().toImage() != before


def test_the_preview_shows_each_pattern(qtbot):
    seen = []
    for key in ("bolts", "slant", "chevrons", "dots"):
        d = _dialog(qtbot, pattern=key)
        _on_screen(d)
        seen.append(d.preview.grab().toImage())
    assert all(seen[i] != seen[j] for i in range(4) for j in range(i))


def test_reset_returns_every_slider_to_its_default(qtbot):
    d = _dialog(qtbot, Adjust(size=150, rotation=30, spacing=80, opacity=160, tone=-60))
    assert d.adjust() != Adjust()
    d.reset_button.click()
    assert d.adjust() == Adjust()
    assert [d.readouts[k].text() for k in d.sliders] == ["100%", "0°", "100%", "100%", "0"]


def test_the_dialog_opens_on_the_adjustments_it_is_given(qtbot):
    given = Adjust(size=75, rotation=-20, spacing=150, opacity=40, tone=25)
    assert _dialog(qtbot, given).adjust() == given


def test_adjust_is_disabled_for_none(store, qtbot, tmp_path):
    d = _settings(store, tmp_path, qtbot)
    _on_screen(d)
    assert d.adjust_button.isVisibleTo(d) and d.adjust_button.isEnabled()
    d.texture_combo.setCurrentIndex(d.texture_combo.findData("none"))
    assert not d.adjust_button.isEnabled()
    d.texture_combo.setCurrentIndex(d.texture_combo.findData("dots"))
    assert d.adjust_button.isEnabled()


def _answer(monkeypatch, result, change=None):
    """TextureDialog.exec answers at once, after ``change`` has moved its sliders."""
    opened = []

    def run(self):
        opened.append((self.pattern, self.adjust()))
        if change:
            change(self)
        return int(result)

    monkeypatch.setattr(TextureDialog, "exec", run)
    return opened


def test_ok_hands_back_the_adjustments_and_settings_saves_them(store, qtbot, tmp_path, monkeypatch):
    def move(dialog):
        dialog.sliders["size"].setValue(150)
        dialog.sliders["rotation"].setValue(30)
        dialog.sliders["opacity"].setValue(160)
        dialog.sliders["tone"].setValue(-60)

    opened = _answer(monkeypatch, QDialog.DialogCode.Accepted, move)
    d = _settings(store, tmp_path, qtbot)
    d.texture_combo.setCurrentIndex(d.texture_combo.findData("dots"))
    d.adjust_button.click()
    assert opened == [("dots", Adjust())], "opened with the pending pattern and adjustments"
    chosen = Adjust(size=150, rotation=30, spacing=100, opacity=160, tone=-60)
    assert d.pending_adjust == chosen
    assert venue.texture_adjust(store) == Adjust(), "nothing reaches the store before Save"
    assert d.save()
    assert venue.texture_adjust(store) == chosen and venue.texture_pattern(store) == "dots"


def test_cancel_keeps_everything_as_it_was(store, qtbot, tmp_path, monkeypatch):
    start = Adjust(size=120, rotation=10)
    venue.save(store, name="R", backup="", texture_pattern="slant", texture_adjust=start)

    def move(dialog):
        dialog.sliders["size"].setValue(60)

    _answer(monkeypatch, QDialog.DialogCode.Rejected, move)
    d = _settings(store, tmp_path, qtbot)
    d.adjust_button.click()
    assert d.pending_adjust == start
    assert d.save()
    assert venue.texture_adjust(store) == start and venue.texture_pattern(store) == "slant"


def test_settings_cancel_after_the_adjustments_ok_saves_nothing(
    store, qtbot, tmp_path, monkeypatch
):
    _answer(monkeypatch, QDialog.DialogCode.Accepted, lambda x: x.sliders["size"].setValue(170))
    d = _settings(store, tmp_path, qtbot)
    d.adjust_button.click()
    assert d.pending_adjust.size == 170
    d.reject()
    assert venue.texture_adjust(store) == Adjust()


def test_the_dialog_fits_a_1366_by_768_screen_at_125_percent(qtbot, monkeypatch):
    room = QSize(1093 - 2 * style.MD, 576 - widgets.FRAME_ALLOWANCE - style.MD)
    monkeypatch.setattr(widgets, "screen_room", lambda _w: room)
    d = _dialog(qtbot)
    _on_screen(d)
    assert d.width() <= room.width() and d.height() <= room.height(), d.size()
    hint = d.minimumSizeHint()
    assert hint.width() <= room.width() and hint.height() <= room.height(), hint


def test_every_control_does_something(qtbot):
    """Each slider moves its readout and the preview; the buttons close or reset."""
    d = _dialog(qtbot)
    _on_screen(d)
    base = d.preview.grab().toImage()
    for key, slider in d.sliders.items():
        slider.setValue(slider.maximum())
        assert d.readouts[key].text() != "", key
    assert d.preview.grab().toImage() != base
    results = []
    d.finished.connect(results.append)
    d.cancel_button.click()
    assert results == [int(QDialog.DialogCode.Rejected)]


def _bands(monkeypatch):
    from madtracker.board import team_rows

    rows: list = []
    band = team_rows.paint_band

    def record(p, row, color, *args, **kwargs):
        rows.append((row.height(), color))
        return band(p, row, color, *args, **kwargs)

    monkeypatch.setattr(team_rows, "paint_band", record)
    return rows


def test_the_preview_rows_are_as_tall_as_the_boards_at_1080p(qtbot, monkeypatch):
    """A five-team Madison's start list and table rows, and a sixteen-rider table's rows."""
    import dataclasses

    from madtracker.board import payloads as P
    from madtracker.board import sample
    from madtracker.ui import texture_dialog as td
    from ui.board_helpers import render
    from ui.test_board_fit import madison
    from ui.test_madison_board import start_list

    rows = _bands(monkeypatch)
    render(qtbot, "pre_race", start_list(td.TEAMS))
    assert [round(h, 3) for h, _c in rows] == [round(td.TEAM_ROW_H, 3)] * td.TEAMS
    rows.clear()
    render(qtbot, "madison", madison(teams=td.TEAMS))
    assert [round(h, 3) for h, _c in rows] == [round(td.TEAM_ROW_H, 3)] * td.TEAMS
    rows.clear()
    data = sample.sprint_points()
    many = [
        dataclasses.replace(data.rows[i % len(data.rows)], rank=i + 1) for i in range(td.RIDERS)
    ]
    render(qtbot, "sprint_points", dataclasses.replace(data, rows=many))
    assert isinstance(data, P.Standings)
    assert len(rows) == td.RIDERS
    assert {round(h, 2) for h, _c in rows} == {round(td.RIDER_BAND_H, 2)}


def test_the_preview_sizes_the_start_names_with_the_boards_helper():
    from madtracker.board import team_rows
    from madtracker.ui import texture_dialog as td

    first, last = team_rows.start_name_px(td.TEAM_ROW_H, 1.0)
    assert last == min(team_rows.START_SURNAME_SHARE * td.TEAM_ROW_H, team_rows.START_SURNAME_MOST)
    assert first <= team_rows.START_FIRST_MOST


def test_the_preview_keeps_the_boards_gap_between_rows(qtbot):
    from madtracker.board import team_rows
    from madtracker.ui import texture_dialog as td

    assert td.DESIGN_H == 2 * td.TEAM_ROW_H + td.RIDER_BAND_H + 2 * team_rows.ROW_GAP
