#!/usr/bin/env bash
# Builds the macOS artifacts: MadTracker.app, a dmg and a zip of the app.
# Run from anywhere on a Mac:
#   packaging/build_macos.sh [--skip-tests]
#
# Needs Python 3.12 or newer as python3. With Homebrew:
#   brew install python@3.12
# and put its bin folder first on PATH if python3 is older.
#
# Signing and notarization are optional and off by default:
#   MADTRACKER_SIGN_IDENTITY  name of a "Developer ID Application"
#                             certificate in the login keychain, for example
#                             "Developer ID Application: Name (TEAMID)".
#                             Needs a paid Apple Developer account.
#   MADTRACKER_NOTARY_PROFILE a keychain profile saved once with
#                             `xcrun notarytool store-credentials`. Used only
#                             when the sign identity is also set, because
#                             Apple rejects unsigned submissions.
set -euo pipefail

SKIP_TESTS=0
for arg in "$@"; do
    case "$arg" in
        --skip-tests) SKIP_TESTS=1 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This script builds the macOS app and must run on a Mac." >&2
    exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Read the version by regex, as the spec does, so no import is needed yet.
VERSION="$(sed -n 's/^__version__ *= *"\([^"]*\)".*/\1/p' madtracker/__init__.py)"
if [[ -z "$VERSION" ]]; then
    echo "Could not read __version__ from madtracker/__init__.py" >&2
    exit 1
fi
echo "Building MadTracker $VERSION"

python3 - <<'PY' || { echo "Python 3.12 or newer is required. Try: brew install python@3.12" >&2; exit 1; }
import sys
sys.exit(0 if sys.version_info >= (3, 12) else 1)
PY

VENV="$ROOT/.venv-build"
if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
fi
PY="$VENV/bin/python"
"$PY" -m pip install --upgrade pip
# Pinned packages first (requirements.txt includes PyInstaller), then the app.
"$PY" -m pip install -r requirements.txt
"$PY" -m pip install -e .

if [[ "$SKIP_TESTS" -eq 0 ]]; then
    QT_QPA_PLATFORM=offscreen "$PY" -m pytest -q -p no:cacheprovider -o faulthandler_timeout=90
fi

# The app icon. First choice: the Icon Composer .icon compiled by actool
# (Xcode 26 or newer), which macOS 26 and up draw with the system's shape,
# margins, and glass; padded art in an .icns was still drawn edge to edge
# on macOS 27. Without it: every size from the .iconset
# packed by iconutil. Without that: the committed .icns, through the spec.
ICON_CAR=""
if packaging/compile_macos_icon.sh "$ROOT/build/icon" >/dev/null; then
    ICON_CAR="$ROOT/build/icon/Assets.car"
    if [[ -f "$ROOT/build/icon/madtracker.icns" ]]; then
        export MADTRACKER_ICNS="$ROOT/build/icon/madtracker.icns"
    fi
    echo "Icon compiled by actool: $ICON_CAR"
elif [[ "${MADTRACKER_REQUIRE_ICON:-0}" == 1 ]]; then
    # Set by the release workflow, so a green run means the app carries
    # the Icon Composer icon rather than the fallback.
    echo "MADTRACKER_REQUIRE_ICON is set and actool wrote no Assets.car." >&2
    cat "$ROOT/build/icon/actool.log" >&2 2>/dev/null || true
    exit 1
else
    echo "No .icon compile (needs Xcode 26; see tools/check_macos_icon.sh): using iconutil."
fi
if [[ -z "${MADTRACKER_ICNS:-}" ]] && command -v iconutil >/dev/null 2>&1; then
    mkdir -p "$ROOT/build"
    iconutil -c icns packaging/madtracker.iconset -o "$ROOT/build/madtracker.icns"
    export MADTRACKER_ICNS="$ROOT/build/madtracker.icns"
    echo "Icon packed by iconutil: $MADTRACKER_ICNS"
fi

"$PY" -m PyInstaller packaging/madtracker.spec --noconfirm --clean

APP="$ROOT/dist/MadTracker.app"
if [[ ! -d "$APP" ]]; then
    echo "PyInstaller did not produce $APP" >&2
    exit 1
fi

# The compiled .icon goes in the bundle with the key that names it; the
# .icns stays as CFBundleIconFile for macOS before 26. Before signing, which
# seals the bundle's contents.
if [[ -n "$ICON_CAR" ]]; then
    cp "$ICON_CAR" "$APP/Contents/Resources/Assets.car"
    /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$APP/Contents/Info.plist" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Add :CFBundleIconName string madtracker" "$APP/Contents/Info.plist"
fi

# Sign before packaging: the dmg and the zip must carry the signed bundle. --deep covers the nested Qt
# libraries; the hardened runtime is required for notarization.
SIGNED=0
if [[ -n "${MADTRACKER_SIGN_IDENTITY:-}" ]]; then
    codesign --force --deep --options runtime --timestamp \
        --sign "$MADTRACKER_SIGN_IDENTITY" "$APP"
    codesign --verify --deep --strict --verbose=2 "$APP"
    SIGNED=1
else
    # The icon steps above break PyInstaller's ad-hoc seal, and a quarantined
    # bundle with a broken seal is "damaged" to Gatekeeper, with no Open
    # Anyway. A fresh ad-hoc seal leaves it merely unidentified.
    echo "MADTRACKER_SIGN_IDENTITY not set: signing ad hoc."
    codesign --force --deep --sign - "$APP"
    codesign --verify --deep --strict --verbose=2 "$APP"
fi

# Run the packaged binary, not the venv: this proves the bundle holds
# everything the store and exports need. The binary is run directly, so its
# exit code is the result.
"$APP/Contents/MacOS/MadTracker" --self-test
echo "Self-test passed"

if [[ "$SIGNED" -eq 1 && -n "${MADTRACKER_NOTARY_PROFILE:-}" ]]; then
    NOTARY_ZIP="$ROOT/dist/notarize-upload.zip"
    rm -f "$NOTARY_ZIP"
    # ditto, not zip: it keeps the bundle's symlinks and resource forks.
    ditto -c -k --keepParent "$APP" "$NOTARY_ZIP"
    xcrun notarytool submit "$NOTARY_ZIP" \
        --keychain-profile "$MADTRACKER_NOTARY_PROFILE" --wait
    rm -f "$NOTARY_ZIP"
    # Stapling stores the ticket in the app so it opens offline.
    xcrun stapler staple "$APP"
elif [[ "$SIGNED" -eq 1 ]]; then
    echo "MADTRACKER_NOTARY_PROFILE not set: skipping notarization."
fi

ZIP="$ROOT/dist/MadTracker-$VERSION-macos.zip"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"

# The dmg holds the app and an Applications symlink for drag-to-install.
DMG="$ROOT/dist/MadTracker-$VERSION.dmg"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
# diskutil image is the newer tool and hdiutil create warns that it is
# deprecated there; a Mac older than that has only hdiutil. UDZO either
# way: compressed, and readable by every macOS the app runs on (12+).
if diskutil image create from --help >/dev/null 2>&1; then
    diskutil image create from --format UDZO --volumeName "MadTracker" "$STAGE" "$DMG"
else
    hdiutil create -volname "MadTracker" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
fi
if [[ "$SIGNED" -eq 1 ]]; then
    codesign --force --timestamp --sign "$MADTRACKER_SIGN_IDENTITY" "$DMG"
fi

echo ""
echo "Artifacts:"
echo "  App: $APP"
echo "  Dmg: $DMG"
echo "  Zip: $ZIP"
