"""Venue settings, the Settings dialog, the logo on the board, and page pacing."""

import pytest

from madtracker.assets import bundled_logo_path
from madtracker.board import sample
from madtracker.control import venue
from madtracker.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "v.sqlite")
    yield s
    s.close()


@pytest.fixture
def board(qtbot):
    from madtracker.board.window import ScoreboardWindow

    w = ScoreboardWindow(sample.VENUE_NAME, sample.EVENT_NAME)
    qtbot.addWidget(w)
    w.resize(1920, 1080)
    return w


def test_the_tv_and_the_preview_turn_a_new_races_pages_together(board, qtbot):
    """The page clocks start over with a new race, so a turn never falls on
    either side of it and the two canvases show the same page."""
    import dataclasses

    from PySide6.QtCore import Qt

    from madtracker.board.window import BoardCanvas

    # Precise clocks: Qt on Linux lines coarse timers up on its own, which
    # hid the drift; Windows keeps the gap between the two canvases' births.
    board._pager.setTimerType(Qt.TimerType.PreciseTimer)
    board._pager.start()
    qtbot.wait(400)
    preview = BoardCanvas()
    qtbot.addWidget(preview)
    preview._pager.setTimerType(Qt.TimerType.PreciseTimer)
    preview._pager.start()
    data = sample.sprint_points()
    rows = [dataclasses.replace(data.rows[i % len(data.rows)], rank=i + 1) for i in range(24)]
    data = dataclasses.replace(data, rows=rows)
    for canvas in (board, preview):
        canvas.set_layout("sprint_points", data)
    assert board.pages["sprint_points"].page_count() == 2
    assert abs(board._pager.remainingTime() - preview._pager.remainingTime()) < 100
    # A turn on the TV alone, then the next sprint's header: both start on page 1.
    board._turn_page()
    after = dataclasses.replace(data, header=dataclasses.replace(data.header, status="Next"))
    for canvas in (board, preview):
        canvas.set_layout("sprint_points", after)
    assert board.pages["sprint_points"].page == preview.pages["sprint_points"].page == 0
    assert abs(board._pager.remainingTime() - preview._pager.remainingTime()) < 100


def test_wide_logo_gets_a_wide_box_and_missing_logo_falls_back(board):
    from madtracker.board.window import LOGO_MAX_W

    board.set_logo(str(bundled_logo_path()))
    logo = board.top_bar.logo
    assert logo is not None and logo.width() / logo.height() > 5
    assert not board.grab().isNull()
    assert LOGO_MAX_W > 300
    board.set_logo("/nowhere/logo.png")
    assert board.top_bar.logo is None
    board.set_venue_name("Riverside Velodrome")
    assert board.top_bar.venue_name == "Riverside Velodrome"


def test_venue_settings_defaults_and_fallbacks(store, tmp_path):
    assert venue.logo_setting(store) is None
    assert venue.logo_bytes(store) == bundled_logo_path().read_bytes()
    assert venue.venue_name(store) == ""
    assert venue.venue_name(store, "Event Venue") == "Event Venue"
    assert venue.chosen_backup_dir(store) is None
    assert venue.automatic_backup_dir(tmp_path) == tmp_path / "backups"
    # The logo is the image itself, in the file (design section 11).
    venue.save(store, logo=b"\x89PNGfake", name=" Riverside ", backup=str(tmp_path / "b"))
    assert venue.logo_setting(store) == b"\x89PNGfake" and venue.logo_bytes(store) == b"\x89PNGfake"
    assert venue.venue_name(store, "Event Venue") == "Riverside"
    assert venue.chosen_backup_dir(store) == tmp_path / "b"
    venue.save(store, name="Riverside", backup="", keep_logo=True)
    assert venue.logo_setting(store) == b"\x89PNGfake"
    venue.save(store, logo=None, name="Riverside", backup="")
    assert venue.logo_setting(store) is None


def test_exports_open_in_the_chosen_folder_while_it_exists(store, tmp_path):
    """The exports' folder is the venue's to choose;
    Documents until then, and again when the chosen folder is gone."""
    from madtracker.control.exports import documents_dir

    assert venue.export_dir(store) == documents_dir()
    venue.save(store, name="Riverside", backup="", exports=f" {tmp_path / 'out'} ")
    assert venue.export_dir(store) == documents_dir(), "not until the folder exists"
    (tmp_path / "out").mkdir()
    assert venue.export_dir(store) == tmp_path / "out"
    venue.save(store, name="Riverside", backup="")
    assert venue.export_dir(store) == tmp_path / "out", "left alone when not given"
    venue.save(store, name="Riverside", backup="", exports="")
    assert venue.export_dir(store) == documents_dir()


def test_board_draws_the_logo_from_bytes(board):
    board.set_logo_bytes(bundled_logo_path().read_bytes())
    assert board.top_bar.logo is not None and board.top_bar.logo.width() > 0
    board.set_logo_bytes(b"not an image")
    assert board.top_bar.logo is None


def test_default_wordmark_is_drawn_without_any_image(board, monkeypatch):
    """With no venue logo the board draws the app's wordmark as vectors, no PNG involved."""
    import madtracker.assets
    from madtracker.board import wordmark

    def no_png(*a, **k):
        raise AssertionError("the board must not load the placeholder PNG")

    monkeypatch.setattr(madtracker.assets, "bundled_logo_path", no_png)
    monkeypatch.setattr(venue, "bundled_logo_path", no_png)
    board.set_logo_bytes(None)
    assert board.top_bar.logo is None
    assert 5 < wordmark.aspect() < 8
    board.set_live(False)
    page = board.logo_page.grab().toImage()
    bar = board.top_bar.grab().toImage()

    # White ink where the mark goes: the glyph's left wheel on the logo
    # page's left third, and the top bar's logo box.
    def white(img, xs, ys):
        return any(img.pixelColor(x, y).lightness() > 240 for x in xs for y in ys)

    assert white(page, range(280, 700, 4), range(380, 620, 4))
    assert white(bar, range(64, 520, 4), range(30, 110, 4))
    assert not white(bar, range(530, 600, 2), range(30, 110, 2))


def test_logo_pixmap_is_scaled_to_physical_pixels(board, monkeypatch):
    """A 150% or 200% display gets the source's full resolution, not a stretched logical copy."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage, QPixmap

    from madtracker.board.window import fit_pixmap

    src = QPixmap.fromImage(QImage(2400, 430, QImage.Format.Format_ARGB32))
    pix = fit_pixmap(src, QSize(600, 300), 2.0)
    assert (pix.width(), pix.height()) == (1200, 215)
    assert pix.devicePixelRatio() == 2.0 and round(pix.deviceIndependentSize().width()) == 600

    board.set_logo_bytes(_png(2400, 430))
    bar = board.top_bar
    monkeypatch.setattr(bar, "devicePixelRatioF", lambda: 2.0)
    bar.grab()
    drawn = bar._fit.pixmap
    box_h = bar.height() - 48 * bar.u
    assert drawn.devicePixelRatio() == 2.0
    assert abs(drawn.height() - 2 * box_h) <= 2
    # The bar repaints often; the same box and ratio reuse the scaled copy.
    bar.grab()
    assert bar._fit.pixmap is drawn


def _png(w: int, h: int) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QImage

    image = QImage(w, h, QImage.Format.Format_ARGB32)
    image.fill(0xFFFFFFFF)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def test_the_logo_preview_is_drawn_again_for_a_screen_of_another_scale(store, qtbot, tmp_path):
    """Moved to a Retina or 150% screen, the preview is scaled for that screen's pixels."""
    from PySide6.QtCore import QCoreApplication, QEvent

    from madtracker.ui.settings import SettingsDialog

    d = SettingsDialog(store, tmp_path)
    qtbot.addWidget(d)
    # The label hands back its pixmap at its own scale, so what it is given is kept.
    given = []
    set_pixmap = d.preview.setPixmap
    d.preview.setPixmap = lambda pix: (given.append(pix.devicePixelRatio()), set_pixmap(pix))
    d.preview.devicePixelRatioF = lambda: 2.0
    QCoreApplication.sendEvent(d, QEvent(QEvent.Type.DevicePixelRatioChange))
    assert given == [2.0]


def test_settings_dialog_previews_and_saves(store, qtbot, tmp_path):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QComboBox

    from madtracker.control.exports import documents_dir
    from madtracker.ui.settings import SettingsDialog

    d = SettingsDialog(store, tmp_path)
    qtbot.addWidget(d)
    assert d.preview.pixmap() is not None and not d.preview.pixmap().isNull()
    # The scoreboard display is chosen on the Scoreboard menu only.
    # Its label says what it is; a tooltip repeating it would say nothing.
    assert [c.toolTip() for c in d.findChildren(QComboBox) if c is not d.texture_combo] == [""]
    # The accent is one of the palette's swatches, named, never a hex code.
    assert [b.toolTip() for b in d.accent_swatches.values()] == [n for n, _h in venue.ACCENTS]
    assert d.accent == venue.DEFAULT_ACCENT and d.accent_name.text() == "Yellow"
    d.accent_swatches["#5cadff"].click()
    assert d.accent == "#5cadff" and d.accent_name.text() == "Blue"
    assert [h for h, b in d.accent_swatches.items() if b.isChecked()] == ["#5cadff"]
    d.set_accent("#112233")
    assert d.accent == "#5cadff", "a color outside the palette is not taken"
    assert d.logo_name.text() == "Default logo"
    assert not d.choose_logo(tmp_path / "missing.png")
    assert "cannot be read" in d.error.text()
    # A wide image is scaled to what the board needs before it is stored.
    wide = QImage(3000, 500, QImage.Format.Format_ARGB32)
    wide.fill(0xFFFFFFFF)
    wide.save(str(tmp_path / "wide.png"))
    assert d.choose_logo(tmp_path / "wide.png")
    assert d.logo_name.text() == "wide.png"
    d.venue_name.setText("Riverside Velodrome")
    assert d.exports.text() == "" and d.exports.placeholderText() == str(documents_dir())
    d.exports.setText(str(tmp_path))
    d.save()
    assert store.get_setting(venue.NAME_KEY) == "Riverside Velodrome"
    assert venue.accent(store) == "#5cadff"
    assert venue.export_dir(store) == tmp_path
    stored = QImage.fromData(venue.logo_setting(store))
    assert stored.width() == venue.LOGO_MAX_WIDTH == 2880 and stored.height() == 480
    again = SettingsDialog(store, tmp_path)
    qtbot.addWidget(again)
    again.set_logo(None)
    again.save()
    assert venue.logo_setting(store) is None


def test_settings_save_refuses_a_folder_that_does_not_exist(store, qtbot, tmp_path):
    """Choose... can only pick a folder that exists; a typed one is held to the same."""
    from madtracker.ui.settings import SettingsDialog

    d = SettingsDialog(store, tmp_path)
    qtbot.addWidget(d)
    d.backup.setText(str(tmp_path / "gone"))
    assert not d.save() and d.error.text() == "The backup folder does not exist."
    assert store.get_setting(venue.BACKUP_KEY, "") == ""
    d.backup.setText(str(tmp_path))
    d.exports.setText(str(tmp_path / "missing"))
    assert not d.save() and d.error.text() == "The exports folder does not exist."
    d.exports.setText(f"  {tmp_path}  ")
    assert d.save()
    assert store.get_setting(venue.BACKUP_KEY) == str(tmp_path)
    assert venue.export_dir(store) == tmp_path


def test_a_logo_past_qt_allocation_limit_loads_scaled(tmp_path):
    """Qt refuses to decode an image past its allocation limit (256 MB by
    default, a phone photo or print artwork); the limit is shrunk here so
    a small file stands in for a huge one."""
    from PySide6.QtGui import QImage, QImageReader

    from madtracker.ui.settings import logo_file_bytes

    wide = QImage(3000, 500, QImage.Format.Format_ARGB32)
    wide.fill(0xFFFFFFFF)
    wide.save(str(tmp_path / "huge.png"))
    (tmp_path / "junk.png").write_bytes(b"not an image at all")
    limit = QImageReader.allocationLimit()
    QImageReader.setAllocationLimit(1)
    try:
        assert QImage(str(tmp_path / "huge.png")).isNull()
        data = logo_file_bytes(tmp_path / "huge.png")
        assert QImageReader.allocationLimit() == 1
        assert logo_file_bytes(tmp_path / "junk.png") is None
    finally:
        QImageReader.setAllocationLimit(limit)
    image = QImage.fromData(data)
    assert (image.width(), image.height()) == (venue.LOGO_MAX_WIDTH, 480)


def test_a_tall_logo_is_stored_within_the_height_cap_too(tmp_path):
    """The logo page draws the logo in a box 45% of the screen high, so a
    tall image is scaled by its height as well as its width."""
    from PySide6.QtGui import QImage

    from madtracker.ui.settings import logo_file_bytes

    (tmp_path / "tall.png").write_bytes(_png(2400, 6000))
    image = QImage.fromData(logo_file_bytes(tmp_path / "tall.png"))
    assert (image.width(), image.height()) == (480, venue.LOGO_MAX_HEIGHT)


def test_a_logo_that_is_not_a_png_is_refused(store, qtbot, tmp_path):
    """A logo is a PNG only, so a photo saved as a JPEG says so on the error line."""
    from PIL import Image

    from madtracker.ui.settings import LogoNotPng, SettingsDialog, logo_file_bytes

    Image.new("RGB", (400, 300), "#808080").save(tmp_path / "phone.jpg", quality=90)
    with pytest.raises(LogoNotPng):
        logo_file_bytes(tmp_path / "phone.jpg")
    dialog = SettingsDialog(store, tmp_path)
    qtbot.addWidget(dialog)
    assert dialog.choose_logo(tmp_path / "phone.jpg") is False
    assert dialog.error.text() == "phone.jpg is not a PNG file."


def test_an_ordinary_logo_is_stored_as_it_was_drawn(tmp_path):
    """A wordmark within the cap keeps its pixels and its transparency, as a
    lossless PNG, opaque or not."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QPainter

    from madtracker.ui.settings import logo_file_bytes

    for name, background in (("clear.png", Qt.GlobalColor.transparent), ("flat.png", "#11151b")):
        art = QImage(1200, 215, QImage.Format.Format_ARGB32)
        art.fill(QColor(background))
        p = QPainter(art)
        p.fillRect(100, 40, 1000, 135, QColor("#ffffff"))
        p.end()
        art.save(str(tmp_path / name))
        data = logo_file_bytes(tmp_path / name)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        stored = QImage.fromData(data).convertToFormat(QImage.Format.Format_ARGB32)
        assert stored == art


def _declared_png(w: int, h: int) -> bytes:
    """A PNG declaring ``w`` by ``h`` with one row's worth of pixel data behind it."""
    import struct
    import zlib

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(1 + w * 4)))
        + chunk(b"IEND", b"")
    )


def test_a_logo_declaring_a_huge_size_is_refused_before_decoding(
    qtbot, store, tmp_path, monkeypatch
):
    """A small file can declare 16000 by 16000 pixels, which Qt would decode
    whole: 2 GB on a venue laptop. It is refused from its header."""
    from PySide6.QtGui import QImageReader

    from madtracker.ui import settings
    from madtracker.ui.settings import SettingsDialog

    class NoDecode(QImageReader):
        def read(self):
            raise AssertionError("decoded a file refused by its header")

    (tmp_path / "bomb.png").write_bytes(_declared_png(16000, 16000))
    monkeypatch.setattr(settings, "QImageReader", NoDecode)
    with pytest.raises(settings.LogoTooLarge):
        settings.logo_file_bytes(tmp_path / "bomb.png")
    d = SettingsDialog(store, tmp_path)
    qtbot.addWidget(d)
    assert not d.choose_logo(tmp_path / "bomb.png")
    assert d.error.text() == "bomb.png is too large to use as the logo."
    assert d.logo_data is None
    assert settings.LOGO_DECODE_LIMIT_MB < 2048


def _elimination(out: list[str], race_id: int = 7):
    from dataclasses import replace

    from madtracker.board.payloads import Entry

    riders = [Entry(bibs=[b], names=[f"Rider {b}"]) for b in out]
    base = sample.elimination()
    return replace(
        base,
        header=replace(base.header, race_id=race_id),
        last_eliminated=riders[-1] if riders else None,
        eliminated=riders[:-1],
    )


def test_eliminated_flashes_only_when_a_rider_was_just_put_out(board):
    """An Undo while "Eliminated" shows never flashes it over the rider
    before, and a rider put out again after that Undo flashes as news."""
    page = board.pages["elimination"]
    board.set_layout("pre_race", _start_list(7))
    board.set_layout("elimination", _elimination(["3"]))
    assert page.fresh and board._highlight.isActive()
    board.set_layout("elimination", _elimination(["3", "5"]))
    assert page.fresh
    # Undo: the order is shorter, so the rider before settles to Last out now.
    board.set_layout("elimination", _elimination(["3"]))
    assert not page.fresh and not board._highlight.isActive()
    # The same order pushed again by a redraw changes nothing.
    board.set_layout("elimination", _elimination(["3", "5"]))
    assert page.fresh
    board.set_layout("elimination", _elimination(["3", "5"]))
    assert page.fresh and board._highlight.isActive()


def test_the_first_rider_out_again_after_an_undo_is_news(board):
    page = board.pages["elimination"]
    board.set_layout("pre_race", _start_list(7))
    board.set_layout("elimination", _elimination(["3"]))
    board.set_layout("pre_race", _start_list(7))
    assert not board._highlight.isActive()
    board.set_layout("elimination", _elimination(["3"]))
    assert page.fresh and board._highlight.isActive()


def test_a_race_first_seen_with_riders_out_shows_its_order_quietly(board):
    """A switch to another elimination, or a display connected mid-race,
    is not a rider just put out."""
    page = board.pages["elimination"]
    board.set_layout("elimination", _elimination(["3", "5"], race_id=7))
    assert not page.fresh and not board._highlight.isActive()
    board.set_layout("elimination", _elimination(["12", "9"], race_id=8))
    assert not page.fresh
    # Back to the first race, unchanged: still nothing new.
    board.set_layout("elimination", _elimination(["3", "5"], race_id=7))
    assert not page.fresh
    board.set_layout("elimination", _elimination(["3", "5", "8"], race_id=7))
    assert page.fresh


def _start_list(race_id: int):
    from madtracker.board.payloads import Entry, Header, PreRace

    return PreRace(
        header=Header(title="Elimination", race_id=race_id), roster=[Entry(["3"], ["A"])]
    )


def test_an_accent_that_would_vanish_on_the_board_is_kept_readable():
    """A navy accent never hides the board's emphasis, a near-white one never
    makes the group chip a bib plate, and a red or green one never matches
    the eliminated card or the FINAL stamp."""
    from PySide6.QtGui import QColor

    from madtracker.board import theme as t
    from madtracker.board.window import stamp_colors

    try:
        t.set_accent("#0d2b5e")
        assert t.contrast(t.ACCENT, t.BG) >= t.ACCENT_CONTRAST
        assert abs(t.ACCENT.hslHueF() - QColor("#0d2b5e").hslHueF()) < 0.02, "the hue stays"
        assert stamp_colors("Provisional")[1] == t.ACCENT, "read at paint time"
        t.set_accent("#f2f2f2")
        assert t.ACCENT_HOLLOW
        t.set_accent("#c8102e")
        assert t.OUT == t.TEXT and t.GAIN.name() == "#6fd590"
        t.set_accent("#0a7b3e")
        assert t.GAIN == t.TEXT and t.OUT.name() == "#ff5a5f"
        t.set_accent(None)
        assert t.ACCENT.name() == t.DEFAULT_ACCENT and not t.ACCENT_HOLLOW
        assert t.OUT.name() == "#ff5a5f" and t.GAIN.name() == "#6fd590"
    finally:
        t.set_accent(None)


def test_every_palette_accent_reads_on_the_board_as_settings_shows_it():
    """The board never has to adjust a palette color, and none can pass for Start list's gray."""
    from madtracker.board import theme as t

    try:
        for _name, hex_color in venue.ACCENTS:
            t.set_accent(hex_color)
            assert t.ACCENT.name() == hex_color
            assert t.contrast(t.ACCENT, t.BAR) >= t.ACCENT_CONTRAST
            assert t.ACCENT.hslSaturationF() > 0.5, "a gray would look like Start list"
    finally:
        t.set_accent(None)


def test_an_accent_outside_the_palette_is_refused_and_reads_as_the_default(store):
    with pytest.raises(ValueError):
        venue.save(store, name="X", backup="", keep_logo=True, accent="#112233")
    store.set_setting(venue.ACCENT_KEY, "#112233")
    assert venue.accent(store) == venue.DEFAULT_ACCENT


def _native(w):
    """The board's native window, which owns its drawing buffers."""
    return int(w.winId())


def test_on_macos_the_board_gets_new_buffers_for_a_tv_of_another_scale(board, monkeypatch):
    """A 960x540 window at 2x and a 1920x1080 TV at 1x must not share buffers."""
    from PySide6.QtGui import QGuiApplication

    screen = QGuiApplication.primaryScreen()
    monkeypatch.setattr(board, "SPACES", True)
    board.show_on(None)
    windowed = _native(board)
    monkeypatch.setattr(board, "devicePixelRatioF", lambda: screen.devicePixelRatio() * 2)
    board.show_on(screen)
    assert board.isVisible() and board.isFullScreen()
    assert _native(board) != windowed
    # Full screen on macOS keeps its frame: the Space hides it, and a
    # frameless window leaves the menu bar showing.
    assert not board._frameless()


def test_on_macos_the_board_already_on_its_tv_is_left_alone(board, monkeypatch):
    from PySide6.QtGui import QGuiApplication

    screen = QGuiApplication.primaryScreen()
    monkeypatch.setattr(board, "SPACES", True)
    board.show_on(screen)
    on_tv = _native(board)
    board.show_on(screen)
    assert board.isFullScreen() and _native(board) == on_tv


def test_on_macos_the_board_leaves_full_screen_in_a_new_window(board, monkeypatch):
    """Leaving a Space ends after the call; a new native window is outside it at once."""
    from PySide6.QtGui import QGuiApplication

    screen = QGuiApplication.primaryScreen()
    monkeypatch.setattr(board, "SPACES", True)
    board.show_on(screen)
    on_tv = _native(board)
    board.show_on(None)
    assert board.isVisible() and not board.isFullScreen() and not board._frameless()
    assert _native(board) != on_tv


def test_elsewhere_the_board_is_frameless_on_the_tv_in_the_same_window(board, monkeypatch):
    from PySide6.QtGui import QGuiApplication

    screen = QGuiApplication.primaryScreen()
    monkeypatch.setattr(board, "SPACES", False)
    board.show_on(screen)
    assert board.isFullScreen() and board._frameless()
    on_tv = _native(board)
    board.show_on(screen)
    assert _native(board) == on_tv


def test_settings_save_refuses_a_folder_too_long_to_look_up(store, qtbot, tmp_path):
    """A pasted path past the system's name limit is no folder: refused on the red
    line, never an error from the check itself."""
    from madtracker.ui.settings import SettingsDialog

    d = SettingsDialog(store, tmp_path)
    qtbot.addWidget(d)
    d.backup.setText("x" * 5000)
    assert not d.save() and d.error.text() == "The backup folder does not exist."
    d.backup.setText(str(tmp_path))
    d.exports.setText(str(tmp_path / ("y" * 5000)))
    assert not d.save() and d.error.text() == "The exports folder does not exist."


# An invented shape: the venue's own mark never enters the repository.
CHEVRON = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    b'<path d="M0 0 L50 0 L100 50 L50 100 L0 100 L50 50 Z" fill="#f00"/></svg>'
)


def _settings(store, tmp_path, qtbot):
    from madtracker.ui.settings import SettingsDialog

    d = SettingsDialog(store, tmp_path)
    qtbot.addWidget(d)
    return d


REFUSAL = "That file has no shape to tile. Choose an SVG file with a filled shape."


def _items(d):
    c = d.texture_combo
    return [c.itemText(i) for i in range(c.count())]


def _empty_svg(tmp_path):
    bad = tmp_path / "empty.svg"
    bad.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    return bad


def test_the_dropdown_lists_the_patterns_then_add_from_file(store, qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    d = _settings(store, tmp_path, qtbot)
    assert d.texture_label.text() == "Scoreboard texture"
    tip = "The pattern tiled faintly across the scoreboard's rows."
    assert d.texture_label.toolTip() == tip and d.texture_combo.toolTip() == tip
    assert _items(d) == [
        "Lightning Bolts",
        "Slant Strokes",
        "Chevrons",
        "Dots",
        "None",
        "",
        "Add from File...",
    ]
    assert d.adjust_button.text() == "Adjust..." and d.adjust_button.isEnabled()
    seen = {}

    def fake(parent, title, start, flt):
        seen["args"] = (title, flt)
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake)
    d.texture_combo.setCurrentIndex(d.texture_combo.count() - 1)
    assert seen["args"] == ("Choose Scoreboard Texture", "SVG Images (*.svg)")
    # Cancelling the file dialog returns to the previous item, with no red line.
    assert d.texture_combo.currentData() == "bolts" and d.error.text() == ""


def test_bolts_is_the_default_for_a_new_file(store, qtbot, tmp_path):
    from madtracker.board.texture import Adjust

    assert venue.texture_pattern(store) == "bolts" and venue.texture_adjust(store) == Adjust()
    d = _settings(store, tmp_path, qtbot)
    assert d.pending_pattern == "bolts" and d.texture_combo.currentText() == "Lightning Bolts"
    assert d.pending_adjust == Adjust() and d.texture_data is None


def test_add_from_file_adds_and_selects_the_venue_shape(store, qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    path = tmp_path / "bolt.svg"
    path.write_bytes(CHEVRON)
    d = _settings(store, tmp_path, qtbot)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(path), ""))
    d.texture_combo.setCurrentIndex(d.texture_combo.count() - 1)
    assert _items(d) == [
        "Lightning Bolts",
        "Slant Strokes",
        "Chevrons",
        "Dots",
        "None",
        "bolt.svg",
        "",
        "Add from File...",
    ]
    assert d.texture_combo.currentText() == "bolt.svg" and d.pending_pattern == "venue"
    assert d.texture_file == "bolt.svg" and d.error.text() == ""
    # Nothing is stored until Save.
    assert store.get_setting(venue.TEXTURE_PATTERN_KEY) is None
    assert d.save()
    kept = venue.texture_setting(store)
    assert kept is not None and b"<path" in kept
    assert venue.texture_name(store) == "bolt.svg" and venue.texture_pattern(store) == "venue"
    again = _settings(store, tmp_path, qtbot)
    assert again.texture_combo.currentText() == "bolt.svg"


def test_a_refused_file_returns_to_the_previous_pattern(store, qtbot, tmp_path):
    d = _settings(store, tmp_path, qtbot)
    d.texture_combo.setCurrentIndex(d.texture_combo.findData("dots"))
    junk = tmp_path / "junk.svg"
    junk.write_bytes(b"not xml")
    for bad in (_empty_svg(tmp_path), junk, tmp_path / "missing.svg"):
        assert not d.choose_texture(bad)
        assert d.error.text() == REFUSAL
        assert d.texture_combo.currentData() == "dots" and d.pending_pattern == "dots"
    assert d.texture_data is None
    assert d.save()
    assert venue.texture_setting(store) is None and venue.texture_pattern(store) == "dots"


def test_a_refused_file_keeps_the_venue_shape_already_chosen(store, qtbot, tmp_path):
    good = tmp_path / "bolt.svg"
    good.write_bytes(CHEVRON)
    d = _settings(store, tmp_path, qtbot)
    assert d.choose_texture(good)
    kept = d.texture_data
    assert not d.choose_texture(_empty_svg(tmp_path))
    assert d.texture_combo.currentText() == "bolt.svg" and d.texture_data == kept
    assert d.save()
    assert venue.texture_name(store) == "bolt.svg" and venue.texture_setting(store) == kept


def test_none_draws_nothing_and_keeps_the_adjustments(store, qtbot, tmp_path, board):
    from madtracker.board.texture import Adjust

    chosen = Adjust(size=150, rotation=20, spacing=80, opacity=60, tone=-30)
    venue.save(store, name="R", backup="", texture_pattern="slant", texture_adjust=chosen)
    d = _settings(store, tmp_path, qtbot)
    assert d.pending_adjust == chosen and d.adjust_button.isEnabled()
    d.texture_combo.setCurrentIndex(d.texture_combo.findData("none"))
    assert d.pending_pattern == "none" and not d.adjust_button.isEnabled()
    assert d.pending_adjust == chosen
    d.texture_combo.setCurrentIndex(d.texture_combo.findData("dots"))
    assert d.adjust_button.isEnabled() and d.pending_adjust == chosen
    d.texture_combo.setCurrentIndex(d.texture_combo.findData("none"))
    assert d.save()
    assert venue.texture_pattern(store) == "none" and venue.texture_adjust(store) == chosen
    board.set_texture("none", None, chosen)
    assert all(p.texture is None for p in board.pages.values())
    board.set_texture("slant", None, chosen)
    assert all(p.texture is not None and p.texture.adjust == chosen for p in board.pages.values())


def test_choosing_a_pattern_changes_nothing_until_save(store, qtbot, tmp_path):
    d = _settings(store, tmp_path, qtbot)
    d.texture_combo.setCurrentIndex(d.texture_combo.findData("chevrons"))
    d.reject()
    assert store.get_setting(venue.TEXTURE_PATTERN_KEY) is None
    assert venue.texture_pattern(store) == "bolts"


def test_the_adjust_button_waits_for_its_dialog(store, qtbot, tmp_path):
    d = _settings(store, tmp_path, qtbot)
    d.show()
    assert d.adjust_button.isHidden()


def test_the_pattern_and_adjustments_travel_into_a_new_file(store, tmp_path):
    from madtracker.board.texture import Adjust
    from madtracker.control.copying import CopyChoice, copy_venue

    keys = (
        venue.TEXTURE_PATTERN_KEY,
        venue.TEXTURE_SIZE_KEY,
        venue.TEXTURE_ROTATION_KEY,
        venue.TEXTURE_SPACING_KEY,
        venue.TEXTURE_OPACITY_KEY,
        venue.TEXTURE_TONE_KEY,
    )
    assert keys[0] == "board/texture_pattern" and keys[-1] == "board/texture_tone"
    assert all(k in venue.SETTING_KEYS for k in keys)
    chosen = Adjust(size=120, rotation=-10, spacing=90, opacity=150, tone=40)
    venue.save(store, name="R", backup="", texture_pattern="chevrons", texture_adjust=chosen)
    with Store.open(tmp_path / "new.sqlite") as new:
        copy_venue(store, new, CopyChoice())
        assert venue.texture_pattern(new) == "chevrons"
        assert venue.texture_adjust(new) == chosen


def test_saving_other_settings_keeps_the_pattern_and_adjustments(store):
    from madtracker.board.texture import Adjust

    chosen = Adjust(size=80)
    venue.save(store, name="R", backup="", texture_pattern="dots", texture_adjust=chosen)
    venue.save(store, name="Riverside", backup="")
    assert venue.texture_pattern(store) == "dots" and venue.texture_adjust(store) == chosen


def test_bad_stored_adjustments_clamp_or_default(store):
    from madtracker.board.texture import Adjust

    store.set_setting(venue.TEXTURE_SIZE_KEY, 5000)
    store.set_setting(venue.TEXTURE_ROTATION_KEY, -999)
    store.set_setting(venue.TEXTURE_SPACING_KEY, "wide")
    store.set_setting(venue.TEXTURE_OPACITY_KEY, True)
    store.set_setting(venue.TEXTURE_TONE_KEY, 12.6)
    assert venue.texture_adjust(store) == Adjust(size=200, rotation=-45, tone=13)
    store.set_setting(venue.TEXTURE_PATTERN_KEY, "swirls")
    assert venue.texture_pattern(store) == "bolts"
    # A venue choice with no stored shape is the bolts.
    store.set_setting(venue.TEXTURE_PATTERN_KEY, "venue")
    assert venue.texture_pattern(store) == "bolts"
    with pytest.raises(ValueError):
        venue.save(store, name="R", backup="", texture_pattern="swirls")


def test_an_older_file_with_a_venue_shape_opens_on_bolts_and_lists_it(store, qtbot, tmp_path):
    venue.save(
        store, name="R", backup="", texture=CHEVRON, texture_name="old.svg", keep_texture=False
    )
    assert store.get_setting(venue.TEXTURE_PATTERN_KEY) is None
    assert venue.texture_pattern(store) == "bolts"
    d = _settings(store, tmp_path, qtbot)
    assert d.texture_combo.currentText() == "Lightning Bolts"
    assert "old.svg" in _items(d)
    d.texture_combo.setCurrentIndex(d.texture_combo.findData("venue"))
    assert d.save() and venue.texture_pattern(store) == "venue"


def test_the_texture_travels_with_the_file_and_into_a_new_file(store, tmp_path):
    from madtracker.control.copying import CopyChoice, copy_venue

    assert venue.TEXTURE_KEY == "board/texture_svg"
    assert venue.TEXTURE_KEY in venue.SETTING_KEYS and venue.TEXTURE_NAME_KEY in venue.SETTING_KEYS
    venue.save(
        store, name="R", backup="", texture=CHEVRON, texture_name="bolt.svg", keep_texture=False
    )
    with Store.open(tmp_path / "new.sqlite") as new:
        copy_venue(store, new, CopyChoice())
        assert venue.texture_setting(new) == CHEVRON
        assert venue.texture_name(new) == "bolt.svg"


def test_saving_other_settings_keeps_the_texture(store):
    venue.save(
        store, name="R", backup="", texture=CHEVRON, texture_name="bolt.svg", keep_texture=False
    )
    venue.save(store, name="Riverside", backup="")
    assert venue.texture_setting(store) == CHEVRON
    assert venue.texture_name(store) == "bolt.svg"


def test_the_board_gives_every_page_the_texture(board):
    from madtracker.board.texture import Adjust, Texture

    assert all(p.texture.builtin for p in board.pages.values())
    board.set_texture("venue", CHEVRON, Adjust())
    shared = {id(p.texture) for p in board.pages.values()}
    assert len(shared) == 1 and not next(iter(board.pages.values())).texture.builtin
    board.set_texture("bolts", None, Adjust())
    assert all(isinstance(p.texture, Texture) and p.texture.builtin for p in board.pages.values())


def test_choosing_a_texture_then_cancelling_saves_nothing(store, qtbot, tmp_path):
    path = tmp_path / "bolt.svg"
    path.write_bytes(CHEVRON)
    d = _settings(store, tmp_path, qtbot)
    assert d.choose_texture(path)
    d.reject()
    assert store.get_setting(venue.TEXTURE_KEY) is None
    assert store.get_setting(venue.TEXTURE_NAME_KEY) is None
    # A texture already kept stays as it was through a cancelled change.
    venue.save(
        store, name="R", backup="", texture=CHEVRON, texture_name="old.svg", keep_texture=False
    )
    d = _settings(store, tmp_path, qtbot)
    d.texture_combo.setCurrentIndex(d.texture_combo.findData("none"))
    d.reject()
    assert venue.texture_setting(store) == CHEVRON and venue.texture_name(store) == "old.svg"
    assert venue.texture_pattern(store) == "bolts"
