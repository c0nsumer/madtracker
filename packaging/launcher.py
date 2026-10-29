"""PyInstaller entry script.

PyInstaller needs a script, not a console-script entry point. This file
only forwards to the real entry so the bundle and `python -m madtracker`
start the same code.
"""

import sys

from madtracker.app import main

if __name__ == "__main__":
    sys.exit(main())
