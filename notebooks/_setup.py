"""Notebook bootstrap.

Import this first in every notebook::

    import _setup  # noqa: F401

Jupyter sets the working directory to the notebook's own folder, so this module
is always importable from a notebook in this directory. It walks up to the repo
root and puts it on ``sys.path`` so ``utils``, ``cleaning`` and ``db_config``
import the same way from any depth — no package install required.
"""

import sys
from pathlib import Path


def _find_root(marker: str = ".git") -> Path:
    """Return the nearest ancestor directory containing ``marker``."""
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if (candidate / marker).exists():
            return candidate
    raise RuntimeError(
        f"Could not locate the repo root: no {marker!r} found in {Path.cwd()} "
        f"or any parent directory."
    )


ROOT: Path = _find_root()
DATA_RAW: Path = ROOT / "data" / "raw"
DATA_PROCESSED: Path = ROOT / "data" / "processed"
FIGURES: Path = ROOT / "reports" / "figures"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
