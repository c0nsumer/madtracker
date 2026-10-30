# Building

This page is for whoever builds MadTracker from source, either to work on it or to make an installable package. It covers the development setup, the build on each system, and what a release build does.

Each system builds its own package with one script. Every script creates a build environment, runs the tests, runs PyInstaller, and runs the built program's self-test. If any step fails, the script stops with an error. Results go to `dist`.

## Development setup

You need Python 3.12 or newer and Git. Clone the repository, open a terminal in it, and run:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # macOS: pip install -e ".[dev,macos]"
python -m madtracker               # start the app
pytest -q                          # tests, headless, about two minutes
ruff check madtracker/ tests/ tools/  # lint
```

The tests run offline and need no display. When you run the whole suite, send its output to a file rather than through a pipe: a dialog raised during a test's teardown would otherwise hang the run without a word. A few other commands are handy while working:

```bash
python -m madtracker --demo                # a seeded demo event in a temp dir
python -m madtracker --data-dir /some/dir  # another data dir
python -m madtracker --mockup DIR          # render both windows to PNGs, headless, and exit
python -m madtracker --self-test           # store + exports smoke test, exit code is the result
QT_QPA_PLATFORM=offscreen pytest -q -m fuzz  # the input fuzzer's deep tier (minutes); FUZZ_SEEDS=10 widens it
ruff format --check madtracker/ tests/ tools/
```

Run the fuzz tier before tagging a version. GitHub Actions runs the everyday suite on Windows, macOS, and Linux on every push.

## Build on Windows

Windows needs Windows 10 or 11, Python 3.12 or newer, and Git. Inno Setup (6 or 7) is optional; without it, the build skips the installer and makes only the folder and the zip. Clone the repository, open PowerShell in it, and run `powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1`. Add `-SkipTests` to skip the test suite. The script writes:

- `dist\MadTracker`, the program folder.
- `dist\MadTracker-<version>-portable.zip`, the portable zip.
- `dist\MadTracker-<version>-setup.exe`, the installer.

The program icon is `packaging\madtracker.ico`, which `tools\make_icons.py` renders from the app's bike glyph along with the macOS icon files. The build uses it for the program and the installer. The pictures on the installer's pages are drawn by the build from the app icon (`tools\make_installer_images.py`), so there is nothing to add for them. The built program sets no AppUserModelID of its own: an explicit one without a matching shortcut drew a blank taskbar icon on Windows 11.

## Build on a Mac

macOS needs a Mac, Python 3.12 or newer, and Git. To get Python with Homebrew, run `brew install python@3.12`. The Xcode command line tools are also needed for `hdiutil` and `codesign`. Clone the repository, open Terminal in it, and run `packaging/build_macos.sh`. Add `--skip-tests` to skip the test suite. The build is for the processor type of the Mac that runs it; the released build is for Apple silicon only. The script writes:

- `dist/MadTracker.app`, the app.
- `dist/MadTracker-<version>.dmg`, the disk image.
- `dist/MadTracker-<version>-macos.zip`, a zip of the app.

To sign and notarize, you need a paid Apple Developer account. Set `MADTRACKER_SIGN_IDENTITY` to the name of your Developer ID Application certificate. Set `MADTRACKER_NOTARY_PROFILE` to a profile saved with `xcrun notarytool store-credentials`. Without these variables, the script skips both steps.

The app icon comes in Apple's newer Icon Composer format, `packaging/madtracker.icon`, which `tools/make_icons.py` writes. macOS 26 and up draw it with the system's own shape, margins, and glass. Compiling it needs Xcode 26 or newer, not only the command line tools. The build finds an Xcode in `/Applications` by itself, so `xcode-select` doesn't need changing. Without Xcode the build packs the older `packaging/madtracker.iconset` with `iconutil` instead, and the Dock may draw that icon a little larger than its neighbors.

To check the icon on a Mac without building the app, run `tools/check_macos_icon.sh`. It compiles the `.icon`, writes `build/icon-check/report.txt`, and changes nothing else.

## Build on Linux

Linux needs 64-bit Linux, Python 3.12 or newer, and Git. Clone the repository, open a terminal in it, and run `packaging/build_linux.sh`. Add `--skip-tests` to skip the test suite. The script writes `dist/MadTracker` and `dist/MadTracker-<version>-linux-x86_64.tar.gz`.

## Release builds

Pushing a tag that starts with `v` runs the same builds on GitHub and attaches the files to a release. The checks that come before a tag are in [Releasing](releasing.md).

## README screenshots

The README's two screenshots are rendered from the demo event, so they can be redone for any version without a race night or a second display. Run `python tools/doc_screenshots.py` from the repository root with the venv active. It scores the demo event headless (the same walk as `--mockup`), writes `docs/images/scoring-window.png` and `docs/images/scoreboard.png`, and rewrites the README's screenshot section with a footnote naming the version it ran from. The pictures have no window frame, since they are drawn without the system's window manager.
