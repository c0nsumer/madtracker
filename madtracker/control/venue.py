"""Venue settings kept in the store: logo, name, backup folder, bibs on the board.

They live in the database's setting table, not in QSettings, because
they belong to the venue's data and should travel with the file when
it is copied to another laptop. The scoreboard display choice stays in
QSettings: it names a monitor on this machine and means nothing on
another one.

The logo is stored as the image itself (design section 11), base64 in
the setting table, so the file carries everything the scoreboard and
the exports need wherever it is opened.
"""

import base64
from pathlib import Path

from madtracker.assets import bundled_logo_path
from madtracker.control.exports import documents_dir
from madtracker.inputs import clean_line
from madtracker.store import Store
from madtracker.store.paths import BACKUP_DIR_NAME

LOGO_KEY = "venue/logo_png"
NAME_KEY = "venue/name"
BACKUP_KEY = "backup/dir"
# Where the exports are offered to be saved; Documents until the venue
# chooses.
EXPORT_KEY = "export/dir"
# How the scoreboard names a rider (design section 10): names only,
# bibs and names, or bibs only. A venue whose announcers call riders
# by name picks names.
RIDER_LABEL_KEY = "board/rider_label"
RIDER_LABELS = ("names", "bibs_names", "bibs")
RIDER_LABEL_WORDS = {
    "names": "Names Only",
    "bibs_names": "Bibs and Names",
    "bibs": "Bibs Only",
}
# The one color the scoreboard uses for emphasis (design section 11).
ACCENT_KEY = "board/accent"
# The accent colors a venue picks from, and only these: each reads at
# 6.5:1 or better on the board's near-black,
# so the board draws it exactly as Settings shows it, and none is a gray
# that "Start list" could be mistaken for. The red and the green make the
# board's own red and green give way to white (board.theme.set_accent),
# so the green sits close enough in hue to the lap-gained green to
# trigger that. Yellow is the default.
ACCENTS = (
    ("Yellow", "#ffc83d"),
    ("Orange", "#ff9a3c"),
    ("Red", "#ff6161"),
    ("Pink", "#ff7ac0"),
    ("Purple", "#b794ff"),
    ("Blue", "#5cadff"),
    ("Teal", "#38d1c4"),
    ("Green", "#5fd68a"),
)
DEFAULT_ACCENT = ACCENTS[0][1]
ACCENT_HEXES = tuple(hex_color for _name, hex_color in ACCENTS)
# The largest a stored logo needs to be. The logo page draws it in a box
# 70% of the screen wide and 45% high, which on a 4K TV is 2688 by 972
# physical pixels at any display scaling; the top bar (at most 1240 by
# 280 there) and the printed sheets (about 190 pixels high) need less.
# The cap leaves headroom for the transparent margins the logo page trims
# away, and keeps a photo from swelling the file and every backup of it.
LOGO_MAX_WIDTH = 2880
LOGO_MAX_HEIGHT = 1200


def logo_setting(store: Store) -> bytes | None:
    """The stored image bytes, or None when the venue has set none."""
    value = store.get_setting(LOGO_KEY)
    if not isinstance(value, str) or not value:
        return None
    try:
        return base64.b64decode(value)
    except ValueError:
        return None


def logo_bytes(store: Store) -> bytes | None:
    """The image the PDF and the Settings preview draw: the stored one, else the bundled PNG.

    The board takes ``logo_setting`` instead and draws the app's wordmark
    itself when it is None.
    """
    data = logo_setting(store)
    if data:
        return data
    path = bundled_logo_path()
    return path.read_bytes() if path.is_file() else None


def set_logo(store: Store, data: bytes | None) -> None:
    """Store the image bytes; None or empty means the bundled placeholder."""
    if data:
        store.set_setting(LOGO_KEY, base64.b64encode(bytes(data)).decode("ascii"))
    else:
        store.delete_setting(LOGO_KEY)


def venue_name(store: Store, event_venue: str = "") -> str:
    """The venue's name, else the event's; blank until Settings names it.

    Blank rather than a placeholder: a placeholder would print on every PDF
    of a venue that never opened Settings. The empty window's Settings
    button is what gets it noticed.
    """
    return str(store.get_setting(NAME_KEY, "") or "") or event_venue


def automatic_backup_dir(data_dir: Path) -> Path:
    return data_dir / BACKUP_DIR_NAME


def chosen_backup_dir(store: Store) -> Path | None:
    """The folder the scorer picked for an extra copy, or None."""
    chosen = str(store.get_setting(BACKUP_KEY, "") or "").strip()
    return Path(chosen) if chosen else None


def chosen_export_dir(store: Store) -> Path | None:
    """The folder the venue picked for its exports, or None."""
    chosen = str(store.get_setting(EXPORT_KEY, "") or "").strip()
    return Path(chosen) if chosen else None


def export_dir(store: Store) -> Path:
    """Where an export's save dialog opens: the chosen folder while it exists, else Documents.

    A chosen folder that is gone (a USB stick, a renamed folder) falls
    back rather than failing: the scorer can still pick a place by hand.
    """
    chosen = chosen_export_dir(store)
    return chosen if chosen is not None and chosen.is_dir() else documents_dir()


def rider_label(store: Store) -> str:
    """names, bibs_names or bibs; bibs and names until the venue chooses."""
    value = store.get_setting(RIDER_LABEL_KEY)
    return str(value) if value in RIDER_LABELS else "bibs_names"


def show_bibs(store: Store) -> bool:
    """Whether the board draws bib plates at all (the two bib modes)."""
    return rider_label(store) != "names"


def accent(store: Store) -> str:
    """The venue's accent, one of ACCENTS; anything else reads as the default."""
    value = store.get_setting(ACCENT_KEY)
    value = value.strip().casefold() if isinstance(value, str) else ""
    return value if value in ACCENT_HEXES else DEFAULT_ACCENT


def save(
    store: Store,
    *,
    name: str,
    backup: str,
    logo: bytes | None = None,
    keep_logo: bool = False,
    rider_label: str | None = None,
    accent: str | None = None,
    exports: str | None = None,
) -> None:
    """Write the venue settings.

    ``logo`` replaces the stored image (None clears it to the bundled
    placeholder) unless ``keep_logo`` is set. ``rider_label`` is one of
    RIDER_LABELS; left None it stays as it was, as do ``accent`` and
    ``exports`` (the folder the exports are offered in; blank means
    Documents) when None.
    """
    if rider_label is not None and rider_label not in RIDER_LABELS:
        raise ValueError(f"rider_label must be one of {RIDER_LABELS}, not {rider_label!r}")
    values: dict = {NAME_KEY: clean_line(name), BACKUP_KEY: backup.strip()}
    delete: list[str] = []
    if not keep_logo:
        if logo:
            values[LOGO_KEY] = base64.b64encode(bytes(logo)).decode("ascii")
        else:
            delete.append(LOGO_KEY)
    if rider_label is not None:
        values[RIDER_LABEL_KEY] = rider_label
    if exports is not None:
        values[EXPORT_KEY] = exports.strip()
    if accent is not None:
        accent = accent.strip().casefold() or DEFAULT_ACCENT
        if accent not in ACCENT_HEXES:
            raise ValueError(f"accent must be one of {ACCENT_HEXES}, not {accent!r}")
        values[ACCENT_KEY] = accent
    # One write: a failure halfway must not keep the logo without the name.
    store.write_settings(values, delete)


# Everything a new data file may take from the open one (design section 12).
SETTING_KEYS = (
    NAME_KEY,
    BACKUP_KEY,
    EXPORT_KEY,
    RIDER_LABEL_KEY,
    ACCENT_KEY,
    "rules/default_ruleset",
)
