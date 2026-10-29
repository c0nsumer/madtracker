"""The packaged app's smoke test: ``python -m madtracker --self-test``.

Runs the store self-test, then seeds the demo event, scores a race
through LiveRace, and writes the results PDF, the USAC CSV, and the
program PDF, then resamples a logo as the PDFs do, all in a
scratch folder, and checks that the bundled font, help pages, and box
icons are there. No Qt object is made, so the check runs on a build
machine with no display. Returns failures instead of raising so every
broken step is reported at once.
"""

import tempfile
from pathlib import Path


def run_full_selftest() -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="madtracker-selftest-") as tmp:
        base = Path(tmp)
        try:
            from madtracker.store.selftest import run_selftest

            failures += [f"store: {f}" for f in run_selftest(base)]
        except Exception as exc:  # report, do not crash: the exit code is the result
            failures.append(f"store: {exc!r}")
        step = "demo"
        try:
            from madtracker.control.demo import seed_demo
            from madtracker.control.race import LiveRace
            from madtracker.export import write_results_pdf, write_usac_csv
            from madtracker.store import Store

            with Store.open(base / "demo.sqlite") as store:
                event_id = seed_demo(store, "2026-10-10")
                step = "scoring"
                chase = store.races(event_id)[0]
                live = LiveRace(store, chase.race_id)
                for entrant_id in live.roster.ids:
                    outcome = live.click(entrant_id)
                    if not outcome.ok:
                        failures.append(f"scoring: {outcome.message}")
                        break
                if live.state != "provisional":
                    failures.append(f"scoring: race is {live.state}, not provisional")
                step = "pdf"
                pdf = write_results_pdf(store, event_id, base / "results.pdf")
                if not Path(pdf).is_file() or Path(pdf).stat().st_size < 1000:
                    failures.append("pdf: file missing or empty")
                step = "csv"
                report = write_usac_csv(store, event_id, base / "usac.csv")
                if report.rows_written < 1 or not (base / "usac.csv").is_file():
                    failures.append("csv: no rows written")
                step = "program"
                from madtracker.export.program import write_program_pdf

                program = write_program_pdf(store, event_id, base / "program.pdf")
                if not Path(program).is_file() or Path(program).stat().st_size < 1000:
                    failures.append("program: file missing or empty")
            step = "logo"
            failures += _logo_check()
        except Exception as exc:
            failures.append(f"{step}: {exc!r}")
    try:
        failures += _bundle_check()
    except Exception as exc:
        failures.append(f"bundle: {exc!r}")
    return failures


def _bundle_check() -> list[str]:
    """The files a frozen build reads through importlib.resources are in it.

    Without the bundled Inter the sheets still export, in Helvetica and
    not PDF/A; without a help page or a box's icon the window still
    opens and fails only when the scorer reaches it. So only this check
    notices a spec that left them out.
    """
    from madtracker.export.pdf import find_font
    from madtracker.ui.help import PAGES, available_pages
    from madtracker.ui.icons import BOX_ICONS, svg_path

    failures = []
    if find_font() is None:
        failures.append("bundle: the Inter font files are missing")
    found = {key for key, _title, _path in available_pages()}
    missing = [name for key, _title, name in PAGES if key not in found]
    if missing:
        failures.append(f"bundle: help pages missing: {', '.join(missing)}")
    gone = [name for name, _color in BOX_ICONS.values() if not svg_path(name).is_file()]
    if gone:
        failures.append(f"bundle: icons missing: {', '.join(gone)}")
    return failures


def _logo_check() -> list[str]:
    """A large logo is resampled for print, which needs Pillow's PNG reader and writer.

    A frozen build without them still writes the PDFs (an unreadable logo
    is passed on whole), so only this check notices: the sheets would
    carry a scoreboard-sized image.
    """
    from io import BytesIO

    from PIL import Image

    from madtracker.export.pdf import _print_logo

    buf = BytesIO()
    Image.new("RGBA", (2400, 2400), (200, 30, 30, 255)).save(buf, "PNG")
    small = _print_logo(buf.getvalue())
    if not isinstance(small, bytes):
        return ["logo: not resampled"]
    with Image.open(BytesIO(small)) as im:
        if im.height >= 2400:
            return ["logo: not resampled"]
    return []
