"""The packaged app's --self-test covers every export the scorer has."""

from madtracker.control.selftest import run_full_selftest


def test_full_selftest_passes():
    assert run_full_selftest() == []


def test_a_broken_program_export_fails_the_selftest(monkeypatch):
    import madtracker.export.program as program

    def broken(*args, **kwargs):
        raise ImportError("no module named madtracker.export.program")

    monkeypatch.setattr(program, "write_program_pdf", broken)
    assert any(f.startswith("program:") for f in run_full_selftest())


def test_a_logo_left_whole_fails_the_selftest(monkeypatch):
    # What a frozen build without Pillow's PNG plugin does: the logo passes through.
    import madtracker.export.pdf as pdf

    monkeypatch.setattr(pdf, "_print_logo", lambda logo: logo)
    assert "logo: not resampled" in run_full_selftest()


def test_a_build_without_its_font_fails_the_bundle_step(monkeypatch):
    # What a spec that leaves out assets/fonts does: the sheets fall back to Helvetica.
    import madtracker.export.pdf as pdf

    monkeypatch.setattr(pdf, "find_font", lambda: None)
    assert "bundle: the Inter font files are missing" in run_full_selftest()


def test_a_build_without_a_help_page_or_an_icon_fails_the_bundle_step(monkeypatch, tmp_path):
    import madtracker.ui.help as help_pages
    import madtracker.ui.icons as icons

    monkeypatch.setattr(help_pages, "help_dir", lambda: tmp_path)
    monkeypatch.setattr(icons, "svg_path", lambda name: tmp_path / f"{name}.svg")
    failures = run_full_selftest()
    assert any(f.startswith("bundle: help pages missing: ") for f in failures)
    assert any(f.startswith("bundle: icons missing: ") for f in failures)
