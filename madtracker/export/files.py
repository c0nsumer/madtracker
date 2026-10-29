"""Writing an export so a failure leaves the earlier file whole."""

import os
from collections.abc import Callable
from pathlib import Path


def write_replacing(path: str | Path, write: Callable[[Path], None]) -> Path:
    """Call ``write`` on a .partial name beside ``path``, then put it in place.

    An export is often written over last week's file, on a USB stick
    that may be full or pulled mid-write. Written in place, the earlier
    file would be truncated before the write failed, so the scorer would
    lose the good copy with the new one. The partial file is removed on
    any failure; the switch is one rename.
    """
    out = Path(path)
    partial = out.with_name(out.name + ".partial")
    try:
        write(partial)
        os.replace(partial, out)
    finally:
        partial.unlink(missing_ok=True)
    return out
