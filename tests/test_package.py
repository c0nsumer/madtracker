import madtracker


def test_app_name_is_set():
    # The test pins that user-visible code reads the constant, not that
    # the constant has a particular value.
    assert isinstance(madtracker.APP_NAME, str) and madtracker.APP_NAME


def test_every_bundled_asset_is_in_the_pyinstaller_spec():
    """A file read through importlib.resources at runtime must travel with the build.

    A glyph the spec does not list reads fine from the checkout, and the
    frozen app draws nothing where the logo belongs.
    """
    import fnmatch
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = (root / "packaging" / "madtracker.spec").read_text(encoding="utf-8")
    globs = re.findall(r'ROOT / "madtracker" / "assets"((?: / "[^"]+")+)', spec)
    patterns = [
        "madtracker/assets" + "".join(f"/{part}" for part in re.findall(r'"([^"]+)"', g))
        for g in globs
    ]
    assets = root / "madtracker" / "assets"
    missing = []
    for path in assets.rglob("*"):
        # Notes for people (README.md) stay in the repo; the app never reads them.
        if path.is_dir() or "__pycache__" in path.parts or path.suffix in (".py", ".md"):
            continue
        rel = path.relative_to(root).as_posix()
        if not any(fnmatch.fnmatch(rel, pat) for pat in patterns):
            missing.append(rel)
    assert missing == [], f"not in packaging/madtracker.spec: {missing}"


def test_every_help_page_is_in_the_pyinstaller_spec():
    """The help window lists only pages whose files exist, so a page the
    spec leaves out would vanish from the frozen app's help without a word."""
    import fnmatch
    import re
    from pathlib import Path

    from madtracker.ui.help import PAGES

    root = Path(__file__).resolve().parents[1]
    spec = (root / "packaging" / "madtracker.spec").read_text(encoding="utf-8")
    globs = re.findall(r'ROOT / "madtracker" / "help"((?: / "[^"]+")+)', spec)
    patterns = [
        "madtracker/help" + "".join(f"/{part}" for part in re.findall(r'"([^"]+)"', g))
        for g in globs
    ]
    pages = [f"madtracker/help/{name}" for _key, _title, name in PAGES]
    assert all((root / page).is_file() for page in pages)
    missing = [p for p in pages if not any(fnmatch.fnmatch(p, pat) for pat in patterns)]
    assert missing == [], f"not in packaging/madtracker.spec: {missing}"


def test_the_installer_names_every_wizard_picture_the_build_draws():
    """installer.iss lists the bitmaps by size; the tool draws them by size. The two lists are one."""
    import re
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    try:
        import make_installer_images as tool
    finally:
        sys.path.remove(str(root / "tools"))
    iss = (root / "packaging" / "installer.iss").read_text(encoding="utf-8")
    listed = {
        kind: {
            tuple(map(int, size.split("x"))) for size in re.findall(rf"{kind}-(\d+x\d+)\.bmp", iss)
        }
        for kind in ("welcome", "header")
    }
    assert listed["welcome"] == set(tool.WELCOME_SIZES)
    assert listed["header"] == {(n, n) for n in tool.HEADER_SIZES}
