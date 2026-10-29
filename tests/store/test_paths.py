"""Data directory resolution: the override, the Windows folder, the macOS folder, the XDG fallback."""

from pathlib import Path

from madtracker.store import paths


def test_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(tmp_path / "portable"))
    assert paths.default_data_dir() == tmp_path / "portable"
    assert paths.default_database_path() == tmp_path / "portable" / "madtracker.sqlite"


def test_windows_uses_localappdata(monkeypatch):
    monkeypatch.delenv(paths.DATA_DIR_ENV, raising=False)
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\scorer\AppData\Local")
    assert paths.default_data_dir() == Path(r"C:\Users\scorer\AppData\Local") / "MadTracker"


def test_macos_uses_application_support(monkeypatch, tmp_path):
    monkeypatch.delenv(paths.DATA_DIR_ENV, raising=False)
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    expected = tmp_path / "home" / "Library" / "Application Support" / "MadTracker"
    assert paths.default_data_dir() == expected


def test_posix_uses_xdg_or_home(monkeypatch, tmp_path):
    monkeypatch.delenv(paths.DATA_DIR_ENV, raising=False)
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert paths.default_data_dir() == tmp_path / "xdg" / "madtracker"
    monkeypatch.delenv("XDG_DATA_HOME")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    assert paths.default_data_dir() == tmp_path / "home" / ".local" / "share" / "madtracker"


def test_default_data_dir_has_no_side_effects(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(tmp_path / "nothing"))
    paths.default_data_dir()
    assert not (tmp_path / "nothing").exists()
