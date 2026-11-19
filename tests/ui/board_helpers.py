"""Rendering a board for the board tests; ``conftest.drawn`` records what it paints."""


def render(qtbot, layout, data, size=(1920, 1080), bibs=True, label=None):
    """A board of ``size`` showing ``data`` on ``layout``, painted once.

    ``label`` is the venue's rider label; without it, ``bibs`` picks
    bibs and names or names only.
    """
    from madtracker.board.window import ScoreboardWindow

    w = ScoreboardWindow("Test Velodrome", "Test Event")
    qtbot.addWidget(w)
    if label is None:
        w.set_show_bibs(bibs)
    else:
        w.set_rider_label(label)
    w.resize(*size)
    w.set_layout(layout, data)
    w.grab()
    return w


def strings(drawn) -> list[str]:
    return [s for s, *_ in drawn]


def record_looks(monkeypatch) -> list[tuple[str, float, float]]:
    """Every string the board paints, with the painter's opacity and its shift right."""
    from madtracker.board import theme

    looks: list[tuple[str, float, float]] = []
    text = theme.text

    def record(p, rect, s, *args, **kwargs):
        looks.append((s, p.opacity(), p.transform().dx()))
        return text(p, rect, s, *args, **kwargs)

    monkeypatch.setattr(theme, "text", record)
    return looks
