"""File > Settings: the venue's name, logo, bibs on the board, backup and exports folders, rulesets.

Only values that belong to the data file live here (design section 11).
The logo is stored in the file as the image itself: choosing a file
reads it, scales it to what the scoreboard needs and keeps the bytes,
so the file carries the logo wherever it is opened. The scoreboard
display names a monitor on this machine and changes during a night, so
it is on the Scoreboard menu and nowhere else.

The logo preview is drawn on the scoreboard's own dark background,
because venue wordmarks ship white on transparent and would vanish
on the window's light gray.
"""

from pathlib import Path

from PySide6.QtCore import QBuffer, QDir, QEvent, QIODevice, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from madtracker.board import theme
from madtracker.control import venue
from madtracker.control.exports import documents_dir
from madtracker.store import Store, StoreError
from madtracker.ui.icons import mdi
from madtracker.ui.widgets import (
    Form,
    apply_style,
    button_row,
    close_on_shortcut,
    error_label,
    fit_to_screen,
    friendly_error,
    note_unprintable,
    run_dialog,
    settings_word,
    show_message,
)

PREVIEW_W, PREVIEW_H = 520, 64
# The most pixels a logo file may declare. Qt decodes the whole image
# before it scales, so this bounds the memory one pick can take on a
# venue laptop; it still admits a 50-megapixel phone photo or an
# 8000-pixel print wordmark, far past anything the board draws.
LOGO_MAX_PIXELS = 64 * 1024 * 1024
# The decode allocation limit that matches: 8 bytes a pixel, as a 16-bit
# PNG decodes to 64-bit color. Qt's own default (256) would refuse a
# 16-bit print wordmark well inside the pixel cap.
LOGO_DECODE_LIMIT_MB = LOGO_MAX_PIXELS * 8 // (1024 * 1024)
LOGO_TIP = "A PNG with a transparent background and light artwork; it is scaled to the scoreboard."
# An invented venue, as every other field shows an example value.
NAME_PLACEHOLDER = "Lakeside Track Cycling"


class LogoTooLarge(ValueError):
    """The file declares more pixels than a logo is ever read at."""


class LogoNotPng(ValueError):
    """The file is an image but not a PNG, the one format a logo is taken in."""


def _encoded(image: QImage, fmt: str) -> bytes | None:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, fmt):
        return None
    return bytes(buffer.data())


def logo_file_bytes(path: str | Path) -> bytes | None:
    """The image file as stored logo bytes within the logo cap, or None when it cannot be read.

    Raises LogoNotPng for an image in another format, and LogoTooLarge,
    before decoding anything, for a file that declares more than
    ``LOGO_MAX_PIXELS``. A logo is a PNG only: it keeps the transparency
    the board's dark background needs, and it stays lossless as it is
    scaled to the cap.
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid():
        return None
    if bytes(reader.format().data()) != b"png":
        raise LogoNotPng(str(path))
    if size.width() * size.height() > LOGO_MAX_PIXELS:
        raise LogoTooLarge(str(path))
    box = QSize(venue.LOGO_MAX_WIDTH, venue.LOGO_MAX_HEIGHT)
    if size.width() > box.width() or size.height() > box.height():
        reader.setScaledSize(size.scaled(box, Qt.AspectRatioMode.KeepAspectRatio))
    limit = QImageReader.allocationLimit()
    QImageReader.setAllocationLimit(LOGO_DECODE_LIMIT_MB)
    try:
        image = reader.read()
    finally:
        QImageReader.setAllocationLimit(limit)
    if image.isNull():
        return None
    # An EXIF rotation turns the scaled image after the cap was applied.
    if image.width() > box.width() or image.height() > box.height():
        image = image.scaled(
            box, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
    return _encoded(image, "PNG")


SWATCH_PX = 36


def _swatch(name: str, hex_color: str) -> QPushButton:
    """One color of the venue palette: a square in the color, named in its tooltip."""
    b = QPushButton()
    b.setObjectName("swatch")
    b.setCheckable(True)
    b.setIconSize(QSize(20, 20))
    b.setToolTip(name)
    b.setAccessibleName(name)
    # The color is the button's own: set once here, never from a handler.
    b.setStyleSheet(
        # The size is the sheet's too: a widget's own min-height outranks
        # setFixedSize, and the form row would squeeze the square flat.
        f"QPushButton#swatch {{ background: {hex_color}; padding: 0;"
        f" min-width: {SWATCH_PX}px; max-width: {SWATCH_PX}px;"
        f" min-height: {SWATCH_PX}px; max-height: {SWATCH_PX}px;"
        " border: 1px solid rgba(0, 0, 0, 0.25); border-radius: 6px; }"
        " QPushButton#swatch:hover { border: 2px solid #5b6472; }"
        " QPushButton#swatch:checked { border: 2px solid #11151b; }"
    )
    return b


class SettingsDialog(QDialog):
    def __init__(self, store: Store, data_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(settings_word())
        fit_to_screen(self, 720, 500)
        apply_style(self)
        close_on_shortcut(self)
        # The bytes to save: the stored image, or None for the bundled placeholder.
        self.logo_data: bytes | None = venue.logo_setting(store)

        self.venue_name = QLineEdit(str(store.get_setting(venue.NAME_KEY, "") or ""))
        self.venue_name.setPlaceholderText(NAME_PLACEHOLDER)

        self.logo_name = QLabel("")
        self.logo_name.setToolTip(LOGO_TIP)
        browse = QPushButton("Choose...")
        browse.setToolTip(LOGO_TIP)
        browse.clicked.connect(self._pick_logo)
        default = QPushButton("Use Default")
        default.clicked.connect(lambda: self.set_logo(None))
        logo_row = QHBoxLayout()
        logo_row.addWidget(self.logo_name, 1)
        logo_row.addWidget(browse)
        logo_row.addWidget(default)

        self.preview = QLabel()
        self.preview.setFixedSize(PREVIEW_W + 24, PREVIEW_H + 24)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # With no logo it shows the venue's name, which may be long.
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet(
            f"background: {theme.BAR.name()}; color: {theme.TEXT.name()}; border-radius: 6px;"
        )
        # The dialog's one red line, also for a logo that cannot be read:
        # a note row of its own under the preview, empty nearly always,
        # would push the dialog past a 1366 by 768 screen at 125%.
        self.error = error_label()
        note_unprintable(self.venue_name, self.error)

        # How the board names riders: names, bibs and names, or bibs only.
        self.rider_label = QComboBox()
        for key in venue.RIDER_LABELS:
            self.rider_label.addItem(venue.RIDER_LABEL_WORDS[key], key)
        self.rider_label.setCurrentIndex(self.rider_label.findData(venue.rider_label(store)))

        # The one color the board uses for emphasis, picked from the venue
        # palette: a swatch per color and the chosen one's name, never a
        # hex code or a free color picker.
        self.accent = venue.accent(store)
        self.accent_group = QButtonGroup(self)
        self.accent_swatches: dict[str, QPushButton] = {}
        accent_row = QHBoxLayout()
        accent_row.setSpacing(6)
        for name, hex_color in venue.ACCENTS:
            b = _swatch(name, hex_color)
            b.clicked.connect(lambda _c=False, h=hex_color: self.set_accent(h))
            self.accent_group.addButton(b)
            self.accent_swatches[hex_color] = b
            accent_row.addWidget(b)
        self.accent_name = QLabel()
        accent_row.addSpacing(8)
        accent_row.addWidget(self.accent_name)
        accent_row.addStretch(1)
        self._show_accent()

        self.backup = QLineEdit(str(store.get_setting(venue.BACKUP_KEY, "") or ""))
        self.backup.setPlaceholderText(str(data_dir / "backups"))
        self.backup.setToolTip(
            f"Backups always go to {data_dir / 'backups'}; a folder chosen here, such as a"
            " USB stick, gets a copy when the program closes and on Backup Now..."
        )
        pick_backup = QPushButton("Choose...")
        pick_backup.clicked.connect(self._pick_backup)
        backup_row = QHBoxLayout()
        backup_row.addWidget(self.backup, 1)
        backup_row.addWidget(pick_backup)

        # Where the exports are offered: Documents until the venue picks
        # a folder, such as one a shared drive syncs.
        self.exports = QLineEdit(str(store.get_setting(venue.EXPORT_KEY, "") or ""))
        self.exports.setPlaceholderText(str(documents_dir()))
        self.exports.setToolTip(
            "Where Export Results PDF, Export Program PDF, and Export USAC CSV offer to save"
        )
        pick_exports = QPushButton("Choose...")
        pick_exports.clicked.connect(self._pick_exports)
        exports_row = QHBoxLayout()
        exports_row.addWidget(self.exports, 1)
        exports_row.addWidget(pick_exports)

        self.rulesets_button = QPushButton("Rulesets...")
        self.rulesets_button.setToolTip("The point values the venue scores with")
        self.rulesets_button.clicked.connect(self.open_rulesets)

        form = Form()
        form.addRow("Venue name", self.venue_name)
        form.addRow("Scoreboard logo", logo_row)
        form.addRow("", self.preview)
        form.addRow("Riders on the scoreboard", self.rider_label)
        form.addRow("Accent color", accent_row)
        form.addRow("Backup folder", backup_row)
        form.addRow("Exports folder", exports_row)
        rulesets_row = QHBoxLayout()
        rulesets_row.addWidget(self.rulesets_button)
        rulesets_row.addStretch(1)
        form.addRow("Rulesets", rulesets_row)
        buttons, _ = button_row("Save", self.save, self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addStretch(1)
        lay.addWidget(self.error)
        lay.addLayout(buttons)
        self._preview()

    def _pick_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Scoreboard Logo", "", "PNG Images (*.png)")
        if path:
            self.choose_logo(path)

    def choose_logo(self, path: str | Path) -> bool:
        """Read the file into the logo; False, with a note, when it is not a PNG, is too large, or cannot be read as an image."""
        try:
            data = logo_file_bytes(path)
        except LogoTooLarge:
            show_message(self.error, f"{Path(path).name} is too large to use as the logo.")
            return False
        except LogoNotPng:
            show_message(self.error, f"{Path(path).name} is not a PNG file.")
            return False
        if data is None:
            show_message(self.error, f"{Path(path).name} cannot be read as an image.")
            return False
        self.set_logo(data, Path(path).name)
        return True

    def set_logo(self, data: bytes | None, name: str = "") -> None:
        self.logo_data = data
        show_message(self.error, "")
        self.logo_name.setText(name if data else "Default logo")
        self._preview()

    def _show_accent(self) -> None:
        for hex_color, b in self.accent_swatches.items():
            chosen = hex_color == self.accent
            b.setChecked(chosen)
            b.setIcon(mdi("check", 20, "#0b0d11") if chosen else QIcon())
        self.accent_name.setText(
            next(name for name, hex_color in venue.ACCENTS if hex_color == self.accent)
        )

    def set_accent(self, hex_color: str) -> None:
        """Choose one of the venue palette's colors; any other value is ignored."""
        hex_color = hex_color.strip().casefold()
        if hex_color in self.accent_swatches:
            self.accent = hex_color
            self._show_accent()

    def _pick_backup(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Backup Folder", self.backup.text())
        if path:
            # The folder as the platform writes it (backslashes on
            # Windows), since the scorer reads it and may type over it.
            self.backup.setText(QDir.toNativeSeparators(path))

    def _pick_exports(self) -> None:
        start = self.exports.text() or str(documents_dir())
        path = QFileDialog.getExistingDirectory(self, "Exports Folder", start)
        if path:
            self.exports.setText(QDir.toNativeSeparators(path))

    def event(self, event: QEvent) -> bool:
        # The preview is scaled for one screen's pixels: drawn again once
        # the dialog is on its screen, and on a move to one of another scale.
        if event.type() in (QEvent.Type.Show, QEvent.Type.DevicePixelRatioChange):
            self._preview()
        return super().event(event)

    def _preview(self) -> None:
        pix = QPixmap()
        data = self.logo_data
        shown = data if data else venue.logo_bytes(self.store)
        if shown:
            pix.loadFromData(bytes(shown))
        if pix.isNull():
            self.preview.setPixmap(QPixmap())
            self.preview.setText(self.venue_name.text() or NAME_PLACEHOLDER)
            return
        # Scaled to the screen's pixels, not the layout's: a logical-size
        # copy is stretched again on a Retina or 150% screen and goes soft.
        dpr = self.preview.devicePixelRatioF()
        shown_pix = pix.scaled(
            round(PREVIEW_W * dpr),
            round(PREVIEW_H * dpr),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        shown_pix.setDevicePixelRatio(dpr)
        self.preview.setPixmap(shown_pix)
        if not data:
            self.logo_name.setText("Default logo")

    def open_rulesets(self) -> None:
        from madtracker.ui.rulesets import open_rulesets

        open_rulesets(self.store, self)

    def save(self) -> bool:
        # A folder is typed as well as chosen, and a typo would only be
        # found at the first backup or export; Choose... can only pick a
        # folder that exists, so a typed one is held to the same.
        for text, what in ((self.backup.text(), "backup"), (self.exports.text(), "exports")):
            folder = text.strip()
            if folder and not Path(folder).is_dir():
                show_message(self.error, f"The {what} folder does not exist.")
                return False
        try:
            venue.save(
                self.store,
                logo=self.logo_data,
                name=self.venue_name.text(),
                backup=self.backup.text(),
                rider_label=self.rider_label.currentData(),
                accent=self.accent,
                exports=self.exports.text(),
            )
        except StoreError as exc:
            # A read-only, busy or full file: said here, and the dialog
            # stays open with what was typed.
            show_message(self.error, friendly_error(self.store, exc))
            return False
        self.accept()
        return True


def open_settings(store: Store, data_dir: Path, parent: QWidget | None = None) -> bool:
    """Run the dialog. Returns True when the scorer saved."""
    dialog = SettingsDialog(store, data_dir, parent)
    return run_dialog(dialog) == QDialog.DialogCode.Accepted
