"""Refresh the README's screenshots from the demo event, and say which version they show.

Run from the repo root with the venv active:

    python tools/doc_screenshots.py

The pictures come from a scorer's clicks through the demo event, so
they show the app as it is at this checkout, in a night's realistic
shape: the first race final, the second provisional, the third racing
(a night never has three races running at once, which ``--mockup``'s
walk leaves on purpose to photograph each state). They are rendered
headless: the same widgets and bundled font as on screen, without the
system's window frame. The README's screenshot
section, between its two marker comments, is rewritten with each
picture, its caption, and a footnote naming the version, so a picture
never outlives the version it claims to show.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "docs" / "images"
README = ROOT / "README.md"
START, END = "<!-- screenshots:start -->", "<!-- screenshots:end -->"

# (picture rendered here, file in docs/images, alt text, caption, shown width)
PRIMARY = (
    (
        "window_madison.png",
        "scoring-window.png",
        "The scoring window during a Madison",
        "The scoring window at 1920 by 1080, partway through a Madison in the demo event:"
        " two sprints recorded, a lap gained by the leading team, the third sprint's first"
        " two teams clicked, and the standings so far. Two teams have names of their own;"
        " the rest go by their color.",
        720,
    ),
    (
        "board_madison.png",
        "scoreboard.png",
        "The scoreboard showing a Madison's standings",
        "The scoreboard on the second display at 1920 by 1080, after the second sprint of"
        " the same Madison.",
        720,
    ),
)
SMALL = (
    (
        "board_elimination.png",
        "scoreboard-elimination.png",
        "The scoreboard as a rider is eliminated",
        "The scoreboard during an Elimination, as the fourth rider is eliminated.",
        400,
    ),
    (
        "board_sprint_result.png",
        "scoreboard-sprint-result.png",
        "The scoreboard's sprint result card",
        "The sprint result card the scoreboard shows briefly after a sprint is recorded.",
        400,
    ),
    (
        "board_madison_two.png",
        "scoreboard-madison-two-teams.png",
        "The scoreboard showing a two-team Madison's standings",
        "A Madison with two teams, one with a name of its own and one going by its color. The scoreboard's rows scale automatically.",
        400,
    ),
    (
        "board_points_five.png",
        "scoreboard-points-five-riders.png",
        "The scoreboard showing a five-rider Points Race's standings",
        "A Points Race with five riders. Nine riders fill the page at the base size, and a larger field gets smaller rows.",
        400,
    ),
    (
        "riders.png",
        "edit-riders.png",
        "The Edit Riders window",
        "File > Edit Riders..., where the venue's riders are added, imported, and edited.",
        400,
    ),
    (
        "standings_1366.png",
        "multi-race-standings.png",
        "The Multi-Race Standings window showing a two-night Team Omnium",
        "File > Multi-Race Standings..., with the demo's two-night Team Omnium partway through.",
        400,
    ),
    (
        "results_pdf.png",
        "results-pdf.png",
        "The first page of a night's results PDF",
        "The first page of the results PDF for the demo's opening night, every race final.",
        400,
    ),
    (
        "program_pdf.png",
        "program-pdf.png",
        "The first page of a night's program PDF",
        "The first page of the program PDF for the demo's race night, as it's posted for the riders.",
        400,
    ),
)
SHOTS = PRIMARY + SMALL


def _figure(name: str, alt: str, width: int) -> str:
    # Shown smaller than rendered: the README is read at a column's width,
    # and a click on the picture opens it at full size.
    return f'<a href="docs/images/{name}"><img src="docs/images/{name}" alt="{alt}" width="{width}"></a>'


def section(version: str) -> str:
    lines = [START, ""]
    for _source, name, alt, caption, width in PRIMARY:
        lines += [_figure(name, alt, width), "", caption, ""]
    # The smaller pictures go two to a row, each over its caption.
    lines.append("<table>")
    for i in range(0, len(SMALL), 2):
        lines.append("<tr>")
        for _source, name, alt, caption, width in SMALL[i : i + 2]:
            lines.append(f'<td valign="top">{_figure(name, alt, width)}<br>{caption}</td>')
        lines.append("</tr>")
    lines += [
        "</table>",
        "",
        f"Every screenshot is rendered from MadTracker {version}'s demo event by"
        " `tools/doc_screenshots.py`, without the operating system's window frame.",
        "",
        END,
    ]
    return "\n".join(lines)


def render_shots(app, out: Path) -> None:
    """A night partway through: three races final, the Madison on, and the shots on the way."""
    from PySide6.QtCore import QSettings

    from madtracker.app import AppController
    from madtracker.control import demo
    from madtracker.control.formats import TEAM_COLORS
    from madtracker.ui import mockup
    from madtracker.ui.setup import RidersDialog
    from madtracker.ui.standings import StandingsDialog

    with (
        tempfile.TemporaryDirectory(prefix="madtracker-shots-data-") as tmp,
        mockup._answering_yes(),
    ):
        settings = QSettings(str(Path(tmp) / "settings.ini"), QSettings.Format.IniFormat)
        c = AppController(app, demo=True, settings=settings, data_dir=Path(tmp) / "data")
        c.main.set_screens(
            [
                ("\\\\.\\DISPLAY1", "Display 1, 1366x768 (Primary) (Windowed)"),
                ("\\\\.\\DISPLAY2", "Sony TV, 1920x1080 (Full Screen)"),
            ],
            None,
        )
        races = c.races

        def refused() -> RuntimeError:
            return RuntimeError(c.main.surface.problem.text())

        def click(*tokens: str) -> None:
            for token in tokens:
                eid = c.live.roster.resolve(token)
                if eid is None or not c.click(eid):
                    raise RuntimeError(f"click {token!r} refused: {c.main.surface.problem.text()}")

        def finish(*out: str) -> None:
            # Riders clicked in roster order until the race is decided, then final.
            gone = {c.live.roster.resolve(token) for token in out}
            for eid in list(c.live.roster.ids):
                if c.live.standings().is_complete:
                    break
                if eid in gone:
                    continue
                if not c.click(eid):
                    raise refused()
            if not c.mark_final():
                raise refused()

        c.set_board_live(True)
        c.select_race(races[mockup.CHASE].race_id)
        finish()
        # The elimination: photographed as the fourth rider goes out.
        c.select_race(races[mockup.ELIMINATION].race_id)
        click("42", "17", "31", "8")
        mockup._grab(c.board, mockup.BOARD_SIZE, out / "board_elimination.png")
        finish("42", "17", "31", "8")
        # The points race: the card the board shows as the second sprint is recorded.
        c.select_race(races[mockup.POINTS].race_id)
        click("12", "7", "33", "4", "22", "9")
        c.record_sprint()
        c.rider_action(c.live.roster.resolve("19"), "lap_gained")
        click("7", "12", "4", "19", "9", "38")
        c.record_sprint()
        mockup._grab(c.board, mockup.BOARD_SIZE, out / "board_sprint_result.png")
        finish()

        def rename_teams(race_id: int, names: dict[str, str]) -> None:
            # As Edit Race renames them: the same riders keep their team.
            teams = [
                (names.get(t.name, t.name), t.color, t.color_hex, t.members)
                for t in c.store.teams(race_id)
            ]
            riders = [e.rider_id for e in c.store.race_entries(race_id)]
            c.store.save_race(c.event.event_id, race_id, {}, riders, teams)

        # The Madison: two sprints in, a lap gained by the leaders, the third's first two teams
        # clicked. Two teams carry names of their own, as a venue's often do.
        rename_teams(
            races[mockup.MADISON].race_id, {"Orange": "Lakeport Lightning", "Black": "Night Shift"}
        )
        c._after_setup_change(show=True)
        c.select_race(races[mockup.MADISON].race_id)
        click("Blue", "Red", "Yellow", "Night Shift")
        c.record_sprint()
        click("Red", "Lakeport Lightning", "Blue", "Night Shift")
        c.record_sprint()
        c.rider_action(c.live.roster.resolve("Red"), "lap_gained")
        click("Lakeport Lightning", "Blue")
        mockup._grab(c.main, mockup.WINDOW_SIZE, out / "window_madison.png")
        c.refresh()
        mockup._grab(c.board, mockup.BOARD_SIZE, out / "board_madison.png")

        # The dialogs before the small fields below, which are not the demo's own and
        # would join its Team Omnium.
        riders = RidersDialog(c.store, None, c.main)
        mockup._grab(riders, (1000, 640), out / "riders.png")
        riders.close()
        riders.deleteLater()
        dialog = StandingsDialog(c.store, c.main, export=lambda _id: None)
        dialog.select(demo.DEMO_STANDINGS)
        mockup._grab(dialog, mockup.WINDOW_SMALL, out / "standings_1366.png")
        dialog.close()
        dialog.deleteLater()
        pdf_pages(c, out)

        # Two small fields the demo does not have, to show the board's rows
        # growing into the page: added to this throwaway copy of the demo
        # with the rules of the demo's own races of those formats.
        def small_race(source, name: str, bibs: list[str]):
            src = c.store.race(races[source].race_id)
            race = c.store.add_race(
                c.event.event_id,
                name,
                src.format,
                group_label=src.group_label,
                usac_category=src.group_label,
                rules_preset=src.rules_preset,
                rules=dict(src.rules),
                rules_version=src.rules_version,
            )
            by_bib = {str(e.bib): e.rider_id for e in c.store.entries(c.event.event_id)}
            for bib in bibs:
                c.store.add_race_entry(race.race_id, by_bib[bib])
            return race, by_bib

        two, by_bib = small_race(mockup.MADISON, "2 Mile Madison", ["5", "36", "3", "24"])
        for name, color, x, y in (
            ("Rust Belt Rollers", "Red", "5", "36"),
            ("Blue", "Blue", "3", "24"),
        ):
            team = c.store.add_team(two.race_id, name, color=color, color_hex=TEAM_COLORS[color])
            c.store.add_team_member(team.team_id, by_bib[x])
            c.store.add_team_member(team.team_id, by_bib[y])
        five, _ = small_race(mockup.POINTS, "3 Mile Points", ["4", "7", "9", "12", "19"])
        c._after_setup_change(show=True)
        c.select_race(two.race_id)
        click("Rust Belt Rollers", "Blue")
        c.record_sprint()
        c.rider_action(c.live.roster.resolve("Rust Belt Rollers"), "lap_gained")
        c.refresh()
        mockup._grab(c.board, mockup.BOARD_SIZE, out / "board_madison_two.png")
        c.select_race(five.race_id)
        click("7", "12", "4", "19")
        c.record_sprint()
        c.rider_action(c.live.roster.resolve("12"), "lap_gained")
        c.refresh()
        mockup._grab(c.board, mockup.BOARD_SIZE, out / "board_points_five.png")
        c.board.close()
        c.main.close()
        c.close()


def pdf_pages(c, out: Path) -> None:
    """The first page of the opening night's results and of tonight's program, as the
    app exports them, rendered by poppler's pdftoppm (needed on PATH)."""
    from madtracker.export.pdf import write_results_pdf
    from madtracker.export.program import write_program_pdf

    opening = next(e for e in c.store.events() if e.event_id != c.event.event_id)
    sheets = (
        (write_results_pdf, opening.event_id, "results_pdf"),
        (write_program_pdf, c.event.event_id, "program_pdf"),
    )
    for write, event_id, stem in sheets:
        pdf = out / f"{stem}.pdf"
        write(c.store, event_id, pdf)
        # 150 dpi: sharp at full size, and a page of results is still only a few
        # hundred kilobytes.
        subprocess.run(
            [
                "pdftoppm",
                "-r",
                "150",
                "-f",
                "1",
                "-l",
                "1",
                "-singlefile",
                "-png",
                str(pdf),
                str(out / stem),
            ],
            check=True,
        )


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT))
    from PIL import Image
    from PySide6.QtWidgets import QApplication

    from madtracker import __version__
    from madtracker.ui.look import apply_look

    text = README.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        print(f"README.md has no {START} ... {END} section", file=sys.stderr)
        return 1

    app = QApplication(sys.argv)
    apply_look(app)
    IMAGES.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="madtracker-shots-") as tmp:
        render_shots(app, Path(tmp))
        for source, name, _alt, _caption, _width in SHOTS:
            shutil.copyfile(Path(tmp) / source, IMAGES / name)
            # Lossless: a README picture is mostly flat color and text.
            with Image.open(IMAGES / name) as im:
                im.load()
            im.save(IMAGES / name, optimize=True)
            print(IMAGES / name)

    README.write_text(pattern.sub(lambda _m: section(__version__), text), encoding="utf-8")
    print(f"README.md: screenshots of {__version__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
