"""An export that fails midway leaves the earlier file whole and no partial file behind."""

import pytest

from madtracker.export import write_results_pdf, write_usac_csv
from madtracker.export.files import write_replacing


def test_a_failed_write_keeps_the_earlier_file_and_leaves_no_partial(tmp_path):
    out = tmp_path / "results.csv"
    out.write_text("last week")

    def half(partial):
        partial.write_text("half")
        raise OSError("No space left on device")

    with pytest.raises(OSError):
        write_replacing(out, half)
    assert out.read_text() == "last week"
    assert list(tmp_path.iterdir()) == [out]

    write_replacing(out, lambda partial: partial.write_text("this week"))
    assert out.read_text() == "this week"
    assert list(tmp_path.iterdir()) == [out]


def test_the_csv_and_the_pdf_replace_the_earlier_file_only_once_written(
    store, event, seeded, tmp_path, monkeypatch
):
    tmp_path = tmp_path / "exports"
    tmp_path.mkdir()
    csv_out = tmp_path / "usac.csv"
    pdf_out = tmp_path / "results.pdf"
    csv_out.write_bytes(b"old csv")
    pdf_out.write_bytes(b"old pdf")

    import madtracker.export.pdf as pdf_mod
    import madtracker.export.usac_csv as csv_mod

    def refuse(*args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(csv_mod.csv, "writer", refuse)
    with pytest.raises(OSError):
        write_usac_csv(store, event[0], csv_out)
    assert csv_out.read_bytes() == b"old csv"
    monkeypatch.undo()

    monkeypatch.setattr(pdf_mod._Doc, "output", refuse)
    with pytest.raises(OSError):
        write_results_pdf(store, event[0], pdf_out)
    assert pdf_out.read_bytes() == b"old pdf"
    monkeypatch.undo()

    assert sorted(p.name for p in tmp_path.iterdir()) == ["results.pdf", "usac.csv"]
    write_usac_csv(store, event[0], csv_out)
    write_results_pdf(store, event[0], pdf_out)
    assert csv_out.read_bytes().startswith(b"Race Date")
    assert pdf_out.read_bytes().startswith(b"%PDF")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["results.pdf", "usac.csv"]
