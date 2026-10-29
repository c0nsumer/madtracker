"""Private copies of the program for the mutation tools, and the swap of one mutant into one.

A mutant is written into a copy, never into the checkout: the checkout
is someone's working tree, and a run killed halfway would leave a
broken engine behind. The venv's editable install points at the main
checkout, so a copy is only tested when PYTHONPATH puts it first;
``prove_imports`` checks that before any result is counted, as a run
against the wrong code reports every mutant as a survivor.
"""

import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from mutator import mutate

# tools/scoring/mutate/ is three folders under the repo root.
REPO = Path(__file__).resolve().parents[3]
MODULES = ["_common", "placings", "elimination", "sprint_points", "win_and_out",
           "aggregate", "replay", "result"]  # fmt: skip
TIMEOUT = 120


def env(tree: Path) -> dict[str, str]:
    """The environment every run in a copy uses.

    No bytecode is written, so a stale .pyc can never stand in for a
    mutant (the cache is also cleared around each swap, below).
    """
    return dict(
        os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(tree), PYTHONDONTWRITEBYTECODE="1"
    )


def make_tree(tree: Path) -> Path:
    """A fresh copy of the package, the tests, and the pytest settings."""
    if tree.exists():
        shutil.rmtree(tree)
    tree.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for sub in ("madtracker", "tests"):
        shutil.copytree(REPO / sub, tree / sub, ignore=ignore)
    shutil.copy2(REPO / "pyproject.toml", tree / "pyproject.toml")
    return tree


def prove_imports(tree: Path) -> None:
    """Exit unless Python run in the copy imports the copy's madtracker."""
    got = subprocess.run(
        [sys.executable, "-c", "import madtracker.scoring as s; print(s.__file__)"],
        cwd=tree,
        env=env(tree),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not Path(got).resolve().is_relative_to(tree.resolve()):
        sys.exit(
            f"PYTHONPATH does not reach the copy: madtracker.scoring is {got}, not under {tree}"
        )
    print(f"imports from the copy: {got}", flush=True)


def scoring_path(tree: Path, module: str) -> Path:
    return tree / "madtracker" / "scoring" / f"{module}.py"


def clear_cache(tree: Path) -> None:
    # A mutant of the same size written in the same second as the
    # original would otherwise be shadowed by the original's .pyc.
    shutil.rmtree(tree / "madtracker" / "scoring" / "__pycache__", ignore_errors=True)


@contextmanager
def swapped(tree: Path, module: str, index: int):
    """The copy with mutant ``index`` of ``module`` in place; the original is restored after."""
    path = scoring_path(tree, module)
    original = path.read_text()
    mutant, site = mutate(original, index)
    clear_cache(tree)
    try:
        path.write_text(mutant)
        yield site
    finally:
        path.write_text(original)
        clear_cache(tree)
