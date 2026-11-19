"""Fixtures shared by the window and board tests."""

import pytest


@pytest.fixture
def drawn(monkeypatch):
    """Every string the board paints, with its rect, pixel size and color."""
    from madtracker.board import theme

    seen: list[tuple[str, object, int, str]] = []
    text = theme.text

    def record(p, rect, s, f, color, *args, **kwargs):
        seen.append((s, rect, f.pixelSize(), color.name()))
        return text(p, rect, s, f, color, *args, **kwargs)

    monkeypatch.setattr(theme, "text", record)
    return seen
