"""The page every sheet shares: nothing within the margin of an edge, and the band's spacing."""

import pytest

from madtracker.control.demo import DEMO_STANDINGS, seed_demo
from madtracker.export import pdf as pdf_mod
from madtracker.export import program as prog
from madtracker.export.standings_pdf import write_standings_pdf


@pytest.fixture
def marks(monkeypatch):
    """Every cell, filled rectangle, line, and image a sheet draws, as page boxes."""
    seen = []
    D = pdf_mod._Doc
    cell, rect, line, image = D.cell, D.rect, D.line, D.image

    def on(self, box, what):
        seen.append((what, self.page_no(), self.w, self.h, *box))

    def rec_cell(self, *a, **k):
        w = k.get("w", a[0] if a else 0)
        h = k.get("h", a[1] if len(a) > 1 else 0)
        text = k.get("text") or (a[2] if len(a) > 2 else "")
        if text:
            on(self, (self.get_x(), self.get_y(), w, h), "cell")
        return cell(self, *a, **k)

    def rec_rect(self, x, y, w, h, *a, **k):
        on(self, (x, y, w, h), "rect")
        return rect(self, x, y, w, h, *a, **k)

    def rec_line(self, x1, y1, x2, y2, *a, **k):
        on(self, (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)), "line")
        return line(self, x1, y1, x2, y2, *a, **k)

    def rec_image(self, src, x=None, y=None, w=0, h=0, *a, **k):
        on(self, (x, y, w, h), "image")
        return image(self, src, x, y, w, h, *a, **k)

    monkeypatch.setattr(D, "cell", rec_cell)
    monkeypatch.setattr(D, "rect", rec_rect)
    monkeypatch.setattr(D, "line", rec_line)
    monkeypatch.setattr(D, "image", rec_image)
    return seen


def test_no_sheet_draws_within_the_margin_of_an_edge(store, tmp_path, marks):
    """A printer leaves each edge unprinted, so the PDF is the page it gives back."""
    tonight = seed_demo(store, "2026-10-18")
    for event in store.events():
        pdf_mod.write_results_pdf(store, event.event_id, tmp_path / f"r{event.event_id}.pdf")
    prog.write_program_pdf(store, tonight, tmp_path / "p.pdf")
    (made,) = [s for s in store.list_standings() if s.name == DEMO_STANDINGS]
    write_standings_pdf(store, made.standings_id, tmp_path / "s.pdf")
    m = pdf_mod.MARGIN
    assert any(page > 1 for _, page, *_ in marks), "a running header is drawn"
    assert any(what == "rect" for what, *_ in marks), "a band is drawn"
    for what, page, pw, ph, x, y, w, h in marks:
        box = (what, page, x, y, w, h)
        assert x >= m - 0.01 and y >= m - 0.01, box
        assert x + w <= pw - m + 0.01 and y + h <= ph - m + 0.01, box


def test_the_running_header_s_dividers_are_evenly_spaced(store, tmp_path, drawn):
    """The event's name ends where " | date" begins, so the gap before the first
    divider is the divider's own spaces, as between the others."""
    seed_demo(store, "2026-10-18")
    for event in store.events():
        pdf_mod.write_results_pdf(store, event.event_id, tmp_path / f"r{event.event_id}.pdf")
    top = pdf_mod.MARGIN + pdf_mod.RUN_H
    band = [d for d in drawn if d["page"] == 2 and d["y"] < top and d["text"]]
    title = next(i for i, d in enumerate(band) if not d["text"].startswith(" "))
    name, rest = band[title], band[title + 1]
    assert rest["text"].startswith(pdf_mod.SEP)
    name_ends = name["x"] + name["margin"] + name["width"]
    assert rest["x"] + rest["margin"] == pytest.approx(name_ends, abs=0.01)
