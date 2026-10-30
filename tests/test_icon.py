from madtracker.assets import ICON_SIZES, app_icon, files


def test_every_icon_size_is_shipped_and_loads(qapp):
    icons = files("madtracker.assets").joinpath("icons")
    for size in ICON_SIZES:
        assert icons.joinpath(f"madtracker-{size}.png").is_file()
    icon = app_icon()
    assert not icon.isNull()
    assert icon.availableSizes()


def test_the_macos_icon_keeps_the_docks_margins_and_the_windows_icon_fills_its_edge(qapp):
    """A tile that filled its canvas would sit in the Dock a sixth larger
    than its neighbors: the .icns leaves Apple's margins, the .ico does
    not, since Windows icons run to the edge."""
    from pathlib import Path

    from PySide6.QtGui import QImage

    packaging = Path(__file__).resolve().parents[1] / "packaging"
    icns = QImage(str(packaging / "madtracker.icns"))
    assert icns.width() == icns.height() == 1024
    side = icns.width()
    # Transparent at the edge's middle and the corner, opaque at the center.
    assert icns.pixelColor(2, 2).alpha() == 0
    assert icns.pixelColor(round(side * 0.04), side // 2).alpha() == 0
    assert icns.pixelColor(side // 2, side // 2).alpha() == 255
    # The tile itself starts a tenth of the way in, as Apple's grid has it.
    assert icns.pixelColor(round(side * 0.12), side // 2).alpha() == 255
    ico = QImage(str(packaging / "madtracker.ico"))
    assert not ico.isNull()
    assert ico.pixelColor(0, ico.height() // 2).alpha() > 0


def test_the_macos_iconset_has_every_size_apple_names_with_the_docks_margins(qapp):
    """The macOS build packs this folder with iconutil: macOS 27 draws Qt's
    single-image .icns edge to edge in the Dock."""
    from pathlib import Path

    from PySide6.QtGui import QImage

    folder = Path(__file__).resolve().parents[1] / "packaging" / "madtracker.iconset"
    for points in (16, 32, 128, 256, 512):
        for scale, suffix in ((1, ""), (2, "@2x")):
            image = QImage(str(folder / f"icon_{points}x{points}{suffix}.png"))
            side = points * scale
            assert image.width() == image.height() == side, (points, suffix)
            if side >= 64:
                # Transparent at the edge's middle, opaque at the center.
                assert image.pixelColor(1, side // 2).alpha() == 0, (points, suffix)
                assert image.pixelColor(side // 2, side // 2).alpha() == 255, (points, suffix)


def test_the_icon_composer_bundle_names_its_layers_and_they_are_full_bleed(qapp):
    """packaging/madtracker.icon, compiled by actool on a Mac: macOS 26 and
    up draw it with the system's shape and margins."""
    import json
    from pathlib import Path

    from PySide6.QtGui import QImage

    bundle = Path(__file__).resolve().parents[1] / "packaging" / "madtracker.icon"
    doc = json.loads((bundle / "icon.json").read_text(encoding="utf-8"))
    names = [layer["image-name"] for group in doc["groups"] for layer in group["layers"]]
    assert names == ["bike.png", "background.png"], "front first, as Icon Composer saves"
    for name in names:
        image = QImage(str(bundle / "Assets" / name))
        assert image.width() == image.height() == 1024, name
    background = QImage(str(bundle / "Assets" / "background.png"))
    # Square and full bleed: the system cuts the shape, so the corners are paint.
    assert background.pixelColor(0, 0).alpha() == 255
    assert background.pixelColor(1023, 1023).alpha() == 255
    bike = QImage(str(bundle / "Assets" / "bike.png"))
    assert bike.pixelColor(0, 0).alpha() == 0 and bike.pixelColor(512, 0).alpha() == 0
    assert any(bike.pixelColor(x, 640).alpha() == 255 for x in range(200, 820, 4))


def test_the_packaged_mac_app_leaves_the_dock_its_bundle_icon():
    """Qt's window icon would replace the bundle's icon in the Dock while
    the app runs, so the packaged Mac app does not set one."""
    from madtracker.assets import sets_window_icon

    assert not sets_window_icon("darwin", frozen=True)
    assert sets_window_icon("darwin", frozen=False)
    assert sets_window_icon("win32", frozen=True)
    assert sets_window_icon("linux", frozen=True)
