from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
ILI2PY_SRC_DIR = PROJECT_ROOT.parent / "src"

for candidate in (SRC_DIR, ILI2PY_SRC_DIR):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
