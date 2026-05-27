"""Shared test fixtures.

Adds the repo root to sys.path so `helpers.transcribe` is importable without
having to install the package.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
