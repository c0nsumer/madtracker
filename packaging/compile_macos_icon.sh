#!/usr/bin/env bash
# Compiles packaging/madtracker.icon (Icon Composer) with Apple's actool:
#   packaging/compile_macos_icon.sh OUTDIR
# Writes OUTDIR/Assets.car (the icon macOS 26 and up draw, by the name
# "madtracker"), OUTDIR/madtracker.icns (the same art for older macOS) when
# actool makes one, OUTDIR/partial.plist, and OUTDIR/actool.log. Exits 0 when
# Assets.car was written; 3 when actool is not available (Xcode 26 or newer
# is needed, not only the command line tools); 1 when actool ran and failed.
# build_macos.sh and tools/check_macos_icon.sh both call this, so the build
# and the check never compile the icon two ways.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:?usage: compile_macos_icon.sh OUTDIR}"
ICON="$ROOT/packaging/madtracker.icon"

# The active developer directory may be the command line tools, which have
# no actool. An Xcode in /Applications is used for this run alone, through
# DEVELOPER_DIR, so the Mac's own xcode-select setting is never changed.
if ! xcrun --find actool >/dev/null 2>&1; then
    for xcode in /Applications/Xcode*.app; do
        if [[ -x "$xcode/Contents/Developer/usr/bin/actool" ]]; then
            export DEVELOPER_DIR="$xcode/Contents/Developer"
            echo "Using $xcode for actool (DEVELOPER_DIR, this run only)."
            break
        fi
    done
fi
if ! xcrun --find actool >/dev/null 2>&1; then
    echo "actool not found: Xcode 26 or newer is needed for the .icon format." >&2
    echo "Install Xcode from the App Store; no xcode-select change is needed." >&2
    exit 3
fi

rm -rf "$OUT"
mkdir -p "$OUT"
# The app runs on macOS 12 and up; a target below 26 makes actool write an
# .icns from the same .icon for the older systems.
xcrun actool "$ICON" \
    --compile "$OUT" \
    --platform macosx \
    --target-device mac \
    --minimum-deployment-target 12.0 \
    --app-icon madtracker \
    --include-all-app-icons \
    --output-partial-info-plist "$OUT/partial.plist" \
    --output-format human-readable-text \
    --notices --warnings --errors \
    > "$OUT/actool.log" 2>&1
STATUS=$?
cat "$OUT/actool.log"
if [[ $STATUS -ne 0 || ! -f "$OUT/Assets.car" ]]; then
    echo "actool did not write Assets.car (exit $STATUS); see $OUT/actool.log" >&2
    exit 1
fi
echo "Compiled the .icon: $OUT/Assets.car"
exit 0
