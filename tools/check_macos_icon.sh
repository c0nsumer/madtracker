#!/usr/bin/env bash
# Checks the Icon Composer app icon on a Mac and writes a report to send
# back. Run from anywhere in the checkout:
#   tools/check_macos_icon.sh
# It changes nothing outside build/icon-check/. Paste the report it prints
# (build/icon-check/report.txt), and attach build/icon-check/preview.png
# when there is one.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/build/icon-check"
REPORT="$OUT/report.txt"

"$ROOT/packaging/compile_macos_icon.sh" "$OUT/compiled"
STATUS=$?
mkdir -p "$OUT"
{
    echo "MadTracker icon check, $(date '+%Y-%m-%d %H:%M')"
    echo "commit: $(git -C "$ROOT" log --oneline -1 2>/dev/null)"
    echo "macOS: $(sw_vers -productVersion 2>/dev/null) ($(uname -m))"
    echo "Xcode: $(xcodebuild -version 2>/dev/null | tr '\n' ' ')"
    echo "xcode-select: $(xcode-select -p 2>/dev/null)"
    echo "Xcode apps: $(ls -d /Applications/Xcode*.app 2>/dev/null | tr '\n' ' ')"
    echo "actool: $(xcrun --find actool 2>/dev/null)"
    echo "compile exit: $STATUS"
    echo
    echo "--- actool.log"
    cat "$OUT/compiled/actool.log" 2>/dev/null || echo "(none)"
    echo
    echo "--- files"
    ls -la "$OUT/compiled" 2>/dev/null || echo "(none)"
    echo
    echo "--- partial.plist"
    plutil -p "$OUT/compiled/partial.plist" 2>/dev/null || echo "(none)"
} > "$REPORT"
# A picture of what older macOS would draw, from the .icns actool made.
if [[ -f "$OUT/compiled/madtracker.icns" ]]; then
    sips -s format png "$OUT/compiled/madtracker.icns" --out "$OUT/preview.png" >/dev/null 2>&1 \
        && echo "preview: $OUT/preview.png" >> "$REPORT"
fi
cat "$REPORT"
echo
echo "Report written to $REPORT"
exit $STATUS
