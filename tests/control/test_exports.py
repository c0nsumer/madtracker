"""Where the exports go by default."""

from madtracker.control import exports


def test_documents_dir_takes_the_folder_qt_reports(tmp_path, monkeypatch):
    docs = tmp_path / "OneDrive" / "Documents"
    docs.mkdir(parents=True)
    monkeypatch.setattr(exports, "_qt_documents", lambda: str(docs))
    assert exports.documents_dir() == docs


def test_documents_dir_falls_back_when_qt_reports_none(tmp_path, monkeypatch):
    monkeypatch.setattr(exports, "_qt_documents", lambda: "")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert exports.documents_dir() == tmp_path
    (tmp_path / "Documents").mkdir()
    assert exports.documents_dir() == tmp_path / "Documents"


def test_documents_dir_falls_back_when_qt_reports_a_missing_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(exports, "_qt_documents", lambda: str(tmp_path / "gone"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert exports.documents_dir() == tmp_path
