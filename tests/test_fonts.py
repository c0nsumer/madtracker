"""The bundled Inter files: present, real TrueType, licensed, loadable by Qt."""

import pytest

from madtracker.assets import fonts

TRUETYPE_MAGIC = (b"\x00\x01\x00\x00", b"true")


@pytest.mark.parametrize("path", fonts.all_paths(), ids=lambda p: p.name)
def test_every_bundled_file_is_truetype(path):
    assert path.is_file()
    with path.open("rb") as fh:
        assert fh.read(4) in TRUETYPE_MAGIC


def test_name_tables_carry_the_family_and_allow_embedding():
    ttlib = pytest.importorskip("fontTools.ttLib")
    for path in fonts.all_paths():
        font = ttlib.TTFont(path)
        name = font["name"]
        # Typographic family (16) when present, else the legacy family (1).
        assert (name.getDebugName(16) or name.getDebugName(1)) == fonts.FAMILY, path.name
        # fsType 0 is installable embedding, which the PDF/A sheet needs.
        assert font["OS/2"].fsType == 0, path.name


def test_font_path_by_weight():
    assert fonts.font_path(400).name == "Inter-Regular.ttf"
    assert fonts.font_path(700).name == "Inter-Bold.ttf"
    assert fonts.font_path(900).name == "Inter-Black.ttf"
    with pytest.raises(KeyError):
        fonts.font_path(300)


def test_license_is_the_ofl():
    text = (fonts.fonts_dir() / fonts.LICENSE_FILE).read_text(encoding="utf-8")
    assert "SIL Open Font License, Version 1.1" in text
    assert "Copyright (c) 2016 The Inter Project Authors" in text


def test_qt_registers_every_weight(qapp):
    from PySide6.QtGui import QFontDatabase

    assert fonts.FAMILY in fonts.register_with_qt()
    styles = set(QFontDatabase.styles(fonts.FAMILY))
    assert {"Regular", "Medium", "SemiBold", "Bold", "Black"} <= styles
