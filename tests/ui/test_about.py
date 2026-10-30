"""Help > About: the credits, the versions and the bundled license texts."""

import re
import tomllib
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog

from madtracker.ui import about

ROOT = Path(__file__).resolve().parents[2]


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _dependency_names() -> list[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return [
        re.split(r"[\s<>=!~;\[]", dep, maxsplit=1)[0] for dep in data["project"]["dependencies"]
    ]


def test_every_dependency_is_credited(qapp):
    # A new dependency fails here until it has a row (and a license text).
    credited = {_norm(d) for c in about.components() for d in c.dists}
    missing = [d for d in _dependency_names() if _norm(d) not in credited]
    assert not missing, f"credit these in madtracker/ui/about.py and the README: {missing}"


def test_every_license_text_is_bundled_and_every_row_has_one(qapp):
    for lic in about.LICENSES.values():
        assert lic.read().strip(), lic.key
    for c in about.components():
        assert c.license_key in about.LICENSES, c.name
    assert "Steve Vigneau" in about.LICENSES["madtracker"].read()
    assert about.LICENSES["madtracker"].read() == (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_license_texts_travel_with_the_package_and_the_bundle():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    spec = (ROOT / "packaging" / "madtracker.spec").read_text(encoding="utf-8")
    assert '"licenses/*.txt"' in pyproject
    assert '"licenses" / "*.txt"' in spec


def test_versions_are_read_from_what_is_installed(qapp, monkeypatch):
    from importlib.metadata import version

    from PySide6.QtCore import qVersion

    rows = {c.name: c for c in about.components()}
    assert rows["Qt"].version == qVersion()
    assert rows["fpdf2"].version == version("fpdf2")
    assert rows["Inter by Rasmus Andersson"].version
    # A component that is not installed is left out, not shown as missing.
    real = about._dist_version
    monkeypatch.setattr(about, "_dist_version", lambda n: None if n == "fpdf2" else real(n))
    assert "fpdf2" not in {c.name for c in about.components()}


@pytest.fixture
def opened(monkeypatch):
    """Dialogs record themselves instead of blocking."""
    seen: list[QDialog] = []
    monkeypatch.setattr(about.AboutDialog, "exec", lambda self: seen.append(self) or 0)
    monkeypatch.setattr(about.LicensesDialog, "exec", lambda self: seen.append(self) or 0)
    return seen


def test_about_opens_from_the_help_menu(qtbot, opened):
    from madtracker.ui.window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.about_action.trigger()
    (box,) = opened
    assert box.windowTitle() == "About MadTracker"
    assert "Developed by Steve Vigneau" in box.author.text()
    assert 'href="https://nuxx.net"' in box.author.text()
    assert "github.com/c0nsumer/madtracker" in box.project.text()
    assert "MIT License" in box.license.text() and "Copyright (c) 2026" in box.license.text()
    assert box.usac.text() == (
        "MadTracker is not a USA Cycling product and is not endorsed by USA Cycling."
    )
    # LGPL 4(a) and GPL 6: each LGPL library is named as such, with its source.
    for c in about.components():
        if c.license_key == "lgpl-3.0":
            assert c.source.startswith("https://"), c.name
    assert box.table.rowCount() == len(about.components())


def test_licenses_button_shows_the_mit_text(qtbot, opened):
    box = about.AboutDialog()
    qtbot.addWidget(box)
    box.licenses_button.click()
    licenses = opened[-1]
    assert isinstance(licenses, about.LicensesDialog)
    assert licenses.current_key() == "madtracker"
    assert licenses.text.isReadOnly()
    assert licenses.text.lineWrapMode() == licenses.text.LineWrapMode.NoWrap, "the text's own lines"
    assert "MIT License" in licenses.text.toPlainText()
    # Only the licenses of what this copy ships.
    keys = [
        licenses.contents.item(i).data(about.KEY_ROLE) for i in range(licenses.contents.count())
    ]
    assert keys == about.license_keys(box.components)


def test_links_open_a_license_here_and_the_web_outside(qtbot, opened, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    browsed = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: browsed.append(url)))
    box = about.AboutDialog()
    qtbot.addWidget(box)
    box.open_link("license:gpl-3.0")
    assert opened[-1].current_key() == "gpl-3.0"
    assert "GNU GENERAL PUBLIC LICENSE" in opened[-1].text.toPlainText()
    box.open_link("https://nuxx.net")
    assert [u.toString() for u in browsed] == ["https://nuxx.net"]


def test_licenses_list_moves_with_the_keyboard(qtbot):
    from PySide6.QtCore import Qt

    dialog = about.LicensesDialog(None, "madtracker")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.keyClick(dialog.contents, Qt.Key.Key_Down)
    assert dialog.current_key() == "lgpl-3.0"
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in dialog.text.toPlainText()


def test_the_credits_table_fits_without_scrolling(qtbot):
    box = about.AboutDialog()
    qtbot.addWidget(box)
    box.show()
    qtbot.waitExposed(box)
    t = box.table
    assert not t.horizontalScrollBar().isVisible()
    assert not t.verticalScrollBar().isVisible()
    for r in range(t.rowCount()):
        for c in range(t.columnCount()):
            cell = t.cellWidget(r, c)
            assert cell.width() >= cell.sizeHint().width(), (r, c, cell.text())
