# PyInstaller spec for the Windows and macOS builds. Run from the repo root:
#   pyinstaller packaging/madtracker.spec --noconfirm --clean
#
# One-folder mode, not one-file: one-file unpacks to a temp folder on every
# launch, which is slow at a venue where the scorer restarts between races.
# One-folder also keeps the Qt libraries replaceable, which is how the
# project meets the LGPL terms for PySide6.
#
# The typeface is bundled (madtracker/assets/fonts, listed below), so the
# window, the board and the PDF/A sheet draw the same Inter on every
# platform and nothing is read from the system's font folders.
#
# macOS: after the one-folder COLLECT, a BUNDLE step wraps it as
# MadTracker.app. The bundle is built for the architecture of the Mac that
# runs the build (arm64 or x86_64), because the pinned wheels are
# single-architecture.
#
# Icon: packaging/madtracker.ico (16 to 256 px) and packaging/madtracker.icns
# are generated with the app icon PNGs by tools/make_icons.py. The spec
# uses them when present and builds without one when absent.
import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

# SPECPATH is the folder that holds this spec, set by PyInstaller.
PACKAGING_DIR = Path(SPECPATH)
ROOT = PACKAGING_DIR.parent

# Read the version by regex, not import, so the spec does not depend on
# the package being importable at spec-evaluation time.
_init_text = (ROOT / "madtracker" / "__init__.py").read_text(encoding="utf-8")
VERSION = re.search(r'^__version__\s*=\s*"([^"]+)"', _init_text, re.M).group(1)
APP_NAME = re.search(r'^APP_NAME\s*=\s*"([^"]+)"', _init_text, re.M).group(1)

_parts = [int(p) for p in re.findall(r"\d+", VERSION)[:4]]
VERSION_TUPLE = tuple(_parts + [0] * (4 - len(_parts)))

# Windows version resource: what Explorer shows under Properties > Details.
# The versioninfo module needs pefile, which only PyInstaller's Windows
# install pulls in, so import it only there.
version_info = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", "Steve Vigneau (nuxx.net)"),
                            StringStruct("FileDescription", APP_NAME),
                            StringStruct("FileVersion", VERSION),
                            StringStruct("InternalName", "MadTracker"),
                            StringStruct("OriginalFilename", "MadTracker.exe"),
                            StringStruct("ProductName", APP_NAME),
                            StringStruct("ProductVersion", VERSION),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )

icon_path = PACKAGING_DIR / "madtracker.ico"

# Only QtCore, QtGui, QtWidgets and QtSvg are imported, plus QtDBus on
# Linux. Excluding the heavy modules keeps PyInstaller's PySide6 hooks
# from pulling them in. QtSvg stays in: madtracker.ui.icons renders the
# bundled Material Design Icons SVGs at runtime, tinted per use, and it
# is a small module. QtDBus carries madtracker.keep_awake's screensaver
# request on Linux; it is small too.
EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D",
    "PySide6.QtQml",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtBluetooth",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtPositioning",
    "PySide6.QtRemoteObjects",
    "tkinter",
    "pytest",
    "pytestqt",
    "ruff",
]

datas = [(str(ROOT / "madtracker" / "assets" / "logos" / "*.png"), "madtracker/assets/logos")]
# The app icon PNGs and the interface glyphs, loaded through
# importlib.resources at runtime like the logos.
datas += [(str(ROOT / "madtracker" / "assets" / "icons" / "*.png"), "madtracker/assets/icons")]
# The bike glyph the board's wordmark draws from at paint time.
datas += [(str(ROOT / "madtracker" / "assets" / "icons" / "*.svg"), "madtracker/assets/icons")]
datas += [(str(ROOT / "madtracker" / "assets" / "icons" / "mdi" / "*.svg"), "madtracker/assets/icons/mdi")]
# The bundled Inter font and its OFL license: the window, the board and
# the PDF all draw with it, and the license must travel with the files.
datas += [(str(ROOT / "madtracker" / "assets" / "fonts" / "*.ttf"), "madtracker/assets/fonts")]
datas += [(str(ROOT / "madtracker" / "assets" / "fonts" / "*.txt"), "madtracker/assets/fonts")]
# The third-party license texts shown in Help > About; a binary that
# ships these components owes its users their licenses.
datas += [(str(ROOT / "madtracker" / "assets" / "licenses" / "*.txt"), "madtracker/assets/licenses")]
# The scorer's help pages (design section 5), read through
# importlib.resources like the assets.
datas += [(str(ROOT / "madtracker" / "help" / "*.md"), "madtracker/help")]
datas += collect_data_files("fpdf")

a = Analysis(
    [str(PACKAGING_DIR / "launcher.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=[],
    excludes=EXCLUDES,
    noarchive=False,
    # fpdf2 is LGPL-3.0, so the user must be able to replace its files.
    # Inside the PYZ archive they could not be, so fpdf2 ships as plain
    # .py files in the install folder, as Qt and PySide6 already ship as
    # separate libraries.
    module_collection_mode={"fpdf": "py"},
)

# Trim what the hooks still copy: Qt translations (the UI is English
# only) and the software OpenGL fallback, which is about 20 MB. Qt6Svg is
# not dropped: the interface icons are rendered from SVG at runtime.
_DROP_BINARIES = ("opengl32sw.dll", "qt6pdf", "qt6quick", "qt6qml", "qt6network")


def _keep_data(entry):
    dest = entry[0].replace("\\", "/").lower()
    if "/translations/" in dest or dest.startswith("pyside6/translations"):
        return Path(dest).name.startswith("qt_en")
    return True


def _keep_binary(entry):
    name = Path(entry[0].replace("\\", "/")).name.lower()
    return not name.startswith(_DROP_BINARIES)


a.datas = [d for d in a.datas if _keep_data(d)]
a.binaries = [b for b in a.binaries if _keep_binary(b)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MadTracker",
    console=False,
    icon=str(icon_path) if icon_path.exists() else None,
    version=version_info,
    # UPX is off: it slows startup and raises antivirus false positives.
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="MadTracker",
    upx=False,
)

# The .app wraps the COLLECT output. Windows and Linux builds are unchanged.
if sys.platform == "darwin":
    # The build script sets MADTRACKER_ICNS to the .icns iconutil made from
    # packaging/madtracker.iconset on the Mac; Qt's single-image .icns is
    # the fallback.
    icns_path = Path(os.environ.get("MADTRACKER_ICNS") or PACKAGING_DIR / "madtracker.icns")
    app = BUNDLE(
        coll,
        name="MadTracker.app",
        icon=str(icns_path) if icns_path.exists() else None,
        bundle_identifier="net.nuxx.madtracker",
        version=VERSION,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            # Without this, Retina displays render the scoreboard blurry.
            "NSHighResolutionCapable": True,
            # PySide6 6.11 needs macOS 12 or newer.
            "LSMinimumSystemVersion": "12.0",
            "NSPrincipalClass": "NSApplication",
        },
    )
