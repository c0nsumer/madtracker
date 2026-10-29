#!/usr/bin/env bash
# Builds the Linux artifact: the PyInstaller folder and a tar.gz of it.
# Run from anywhere on a Linux machine:
#   packaging/build_linux.sh [--skip-tests]
#
# Needs Python 3.12 or newer as python3. The tarball name says x86_64
# because the pinned wheels are single-architecture; the script refuses
# other machines rather than mislabel the file.
set -euo pipefail

SKIP_TESTS=0
for arg in "$@"; do
    case "$arg" in
        --skip-tests) SKIP_TESTS=1 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
    echo "This script builds the Linux x86_64 package and must run on that." >&2
    exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(sed -n 's/^__version__ *= *"\([^"]*\)".*/\1/p' madtracker/__init__.py)"
if [[ -z "$VERSION" ]]; then
    echo "Could not read __version__ from madtracker/__init__.py" >&2
    exit 1
fi
echo "Building MadTracker $VERSION"

python3 - <<'PY' || { echo "Python 3.12 or newer is required." >&2; exit 1; }
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

"$PY" -m PyInstaller packaging/madtracker.spec --noconfirm --clean

DIR="$ROOT/dist/MadTracker"
if [[ ! -x "$DIR/MadTracker" ]]; then
    echo "PyInstaller did not produce $DIR/MadTracker" >&2
    exit 1
fi

# Run the packaged binary, not the venv. The offscreen platform lets this
# work on a build machine or CI runner with no display.
QT_QPA_PLATFORM=offscreen "$DIR/MadTracker" --self-test
echo "Self-test passed"

# Launcher files for a user who wants a menu entry. A .desktop Exec line
# needs an absolute path, so the folder carries a template and a script
# that fills in the folder's real location.
cp "$ROOT/madtracker/assets/icons/madtracker-256.png" "$DIR/madtracker.png"
cat > "$DIR/madtracker.desktop.in" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=MadTracker
Comment=Scoring for track cycling events
Exec=@DIR@/MadTracker
Icon=@DIR@/madtracker.png
Terminal=false
Categories=Utility;Sports;
DESKTOP
cat > "$DIR/install-launcher.sh" <<'LAUNCHER'
#!/usr/bin/env bash
# Adds MadTracker to the application menu for the current user, pointing
# at the folder this script is in. Run it again after moving the folder.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$target"
sed "s|@DIR@|$here|g" "$here/madtracker.desktop.in" > "$target/madtracker.desktop"
echo "Installed $target/madtracker.desktop"
LAUNCHER
chmod +x "$DIR/install-launcher.sh"

TARBALL="$ROOT/dist/MadTracker-$VERSION-linux-x86_64.tar.gz"
rm -f "$TARBALL"
tar -C "$ROOT/dist" -czf "$TARBALL" MadTracker

echo ""
echo "Artifacts:"
echo "  Folder:  $DIR"
echo "  Tarball: $TARBALL"
