"""The Scoreboard Texture dialog: size, rotation, spacing, opacity, and tone, shown on three rows.

The preview draws the board's own rows with the board's own painter calls
and fonts, on the board's background, so the pattern is judged where it
will be seen: on a Madison's start list row, a team's color row, and a
rider row. Every slider redraws it at once. Nothing is stored here; the
caller reads ``adjust()`` after OK and keeps it pending until Settings
saves.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from madtracker.board import team_rows, texture, theme
from madtracker.board.pages import LIST_NAME_SHARE
from madtracker.ui import style
from madtracker.ui.look import DIALOG_BASE_PT
from madtracker.ui.widgets import Form, apply_style, button_row, fit_to_screen

# The preview's rows in board units: a Madison's start list row, a team's
# color row, and a rider row, at the heights the board gives them.
DESIGN_W = 1000
MADISON_H, COLOR_H, RIDER_H = 150, 120, 112
DESIGN_H = MADISON_H + COLOR_H + RIDER_H + 2 * team_rows.ROW_GAP
PREVIEW_W = 520
PREVIEW_H = round(PREVIEW_W * DESIGN_H / DESIGN_W)
# Invented riders and team colors, as every example value is.
MADISON_COLOR, COLOR_VIEW_COLOR = "#2f6fdb", "#e0a72a"
MADISON_NAMES, MADISON_BIBS = ["Rafa Quint", "Noor Lindqvist"], ["12", "13"]
COLOR_NAME = "Yellow"
RIDER_NAME, RIDER_BIB = "Adaeze Okafor", "27"

MINUS = "−"
DEGREE = "°"


def _signed(value: int) -> str:
    return f"{MINUS}{-value}" if value < 0 else str(value)


# One slider per adjustment: its label, range, steps, and readout.
_SLIDERS = (
    ("size", "Size", texture.SIZE, 5, 25, lambda v: f"{v}%"),
    ("rotation", "Rotation", texture.ROTATION, 5, 15, lambda v: f"{_signed(v)}{DEGREE}"),
    ("spacing", "Spacing", texture.SPACING, 5, 25, lambda v: f"{v}%"),
    ("opacity", "Opacity", texture.OPACITY, 5, 25, lambda v: f"{v}%"),
    ("tone", "Tone", texture.TONE, 5, 25, _signed),
)


class TexturePreview(QWidget):
    """Three board rows on the board's background, tiled with ``texture``."""

    def __init__(self, tex: texture.Texture | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.texture = tex
        self.setFixedSize(PREVIEW_W, PREVIEW_H)

    def set_texture(self, tex: texture.Texture | None) -> None:
        self.texture = tex
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.fillRect(self.rect(), theme.BG)
        u = min(self.width() / DESIGN_W, self.height() / DESIGN_H)
        gap = team_rows.ROW_GAP * u
        width = DESIGN_W * u
        x = (self.width() - width) / 2
        y = (self.height() - DESIGN_H * u) / 2
        dpr = self.devicePixelRatioF()
        # A row's text is sized from its height as the board's rows are.
        madison = QRectF(x, y, width, MADISON_H * u)
        color = QRectF(x, madison.bottom() + gap, width, COLOR_H * u)
        rider = QRectF(x, color.bottom() + gap, width, RIDER_H * u)
        paint = {"slant": theme.SLANT, "texture": self.texture, "dpr": dpr}

        team_rows.paint_band(p, madison, MADISON_COLOR, u, **paint)
        last_px = min(
            team_rows.START_SURNAME_SHARE * madison.height(), team_rows.START_SURNAME_MOST * u
        )
        first_px = min(
            max(team_rows.START_FIRST_SHARE * madison.height(), theme.MIN_PX * u),
            team_rows.START_FIRST_MOST * u,
        )
        team_rows.paint_start_riders(
            p, madison, MADISON_BIBS, MADISON_NAMES, first_px, last_px, u, "names"
        )

        team_rows.paint_band(p, color, COLOR_VIEW_COLOR, u, sweep=1, **paint)
        pad = team_rows.ROW_PAD * u
        inner = color.adjusted(pad, 0, -pad - team_rows.run(color, theme.SLANT) / 2, 0)
        theme.text(
            p,
            inner,
            COLOR_NAME,
            theme.font(color.height() * 0.5, theme.HEAVY),
            theme.team_ink(QColor(COLOR_VIEW_COLOR)),
            Qt.AlignmentFlag.AlignCenter,
        )

        team_rows.paint_band(p, rider, team_rows.RIDER_BAR, u, **paint)
        ph = min(rider.height() * team_rows.PLATE_SHARE, team_rows.PLATE_MOST * u)
        pw = theme.plate_width(ph)
        left = rider.left() + (team_rows.SWATCH_W + team_rows.ROW_PAD) * u
        theme.plate(p, QRectF(left, rider.center().y() - ph / 2, pw, ph), RIDER_BIB)
        name_x = left + pw + team_rows.PLATE_GAP * u
        theme.text(
            p,
            QRectF(name_x, rider.top(), rider.right() - pad - name_x, rider.height()),
            RIDER_NAME,
            theme.font(rider.height() * LIST_NAME_SHARE, theme.HEAVY),
            theme.TEXT,
        )
        p.end()


class TextureDialog(QDialog):
    """Adjust the chosen pattern; OK keeps the values, Cancel keeps none."""

    def __init__(
        self,
        pattern: str,
        venue_svg: bytes | None,
        adjust: texture.Adjust,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Scoreboard Texture")
        apply_style(self)
        self.pattern = pattern
        self.venue_svg = venue_svg
        start = adjust.clamped()

        self.preview = TexturePreview(None)
        self.sliders: dict[str, QSlider] = {}
        self.readouts: dict[str, QLabel] = {}
        self.form = Form()
        self.form.setVerticalSpacing(style.XS)
        # A slider is a mouse's, and five rows plus the preview must fit a
        # 1366 by 768 screen at 125%, so it is shorter than a button.
        height = style.control_height(DIALOG_BASE_PT, 1.6)
        fm = self.fontMetrics()
        # Tone's end labels stand beside its slider; every row keeps their
        # room so the sliders line up and have one length.
        end_w = max(fm.horizontalAdvance("Darker"), fm.horizontalAdvance("Lighter"))
        readout_w = max(
            fm.horizontalAdvance(f(v)) for _k, _l, (lo, hi), _s, _p, f in _SLIDERS for v in (lo, hi)
        )
        self.tone_ends = (QLabel("Darker"), QLabel("Lighter"))
        for key, label, (lo, hi), step, page, _shown in _SLIDERS:
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(lo, hi)
            slider.setSingleStep(step)
            slider.setPageStep(page)
            slider.setFixedHeight(height)
            slider.setValue(getattr(start, key))
            readout = QLabel()
            readout.setFixedWidth(readout_w)
            readout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.sliders[key], self.readouts[key] = slider, readout
            slider.valueChanged.connect(lambda _v, k=key: self._moved(k))
            row = QHBoxLayout()
            row.setSpacing(style.SM)
            if key == "tone":
                self.tone_ends[0].setFixedWidth(end_w)
                self.tone_ends[1].setFixedWidth(end_w)
                self.tone_ends[0].setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                row.addWidget(self.tone_ends[0])
                row.addWidget(slider, 1)
                row.addWidget(self.tone_ends[1])
            else:
                row.addWidget(self._gap(end_w))
                row.addWidget(slider, 1)
                row.addWidget(self._gap(end_w))
            row.addWidget(readout)
            self.form.addRow(label, row)
        for label in (*self.readouts.values(), *self.tone_ends):
            label.setTextFormat(Qt.TextFormat.PlainText)

        buttons, made = button_row("OK", self.accept, self.reject)
        self.ok_button, self.cancel_button = made["primary"], made["cancel"]
        # Reset is no way out, so it stands apart from the pair that is.
        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self.reset)
        buttons.insertWidget(0, self.reset_button)

        lay = QVBoxLayout(self)
        lay.setSpacing(style.MD)
        lay.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addLayout(self.form)
        lay.addLayout(buttons)
        for key in self.sliders:
            self._show(key)
        self._redraw()
        fit_to_screen(self, self.sizeHint().width(), self.sizeHint().height())

    @staticmethod
    def _gap(width: int) -> QWidget:
        # A widget, not addSpacing: a spacer item takes no layout spacing, so
        # the slider would start a gap earlier than Tone's does.
        gap = QWidget()
        gap.setFixedWidth(width)
        return gap

    def adjust(self) -> texture.Adjust:
        return texture.Adjust(**{k: s.value() for k, s in self.sliders.items()})

    def reset(self) -> None:
        defaults = texture.Adjust()
        for key, slider in self.sliders.items():
            slider.setValue(getattr(defaults, key))

    def _show(self, key: str) -> None:
        shown = next(f for k, _l, _r, _s, _p, f in _SLIDERS if k == key)
        self.readouts[key].setText(shown(self.sliders[key].value()))

    def _moved(self, key: str) -> None:
        self._show(key)
        self._redraw()

    def _redraw(self) -> None:
        self.preview.set_texture(texture.make_texture(self.pattern, self.venue_svg, self.adjust()))
