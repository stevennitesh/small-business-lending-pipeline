from __future__ import annotations

import sys
from pathlib import Path


def add_repo_root_to_path() -> None:
    """Add the repository root to sys.path for direct script execution."""
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
