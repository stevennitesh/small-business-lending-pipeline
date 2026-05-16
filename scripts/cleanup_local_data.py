#!/usr/bin/env python3
"""Preview or remove generated local data that is safe to rebuild."""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path


DEFAULT_KEEP_PIPELINE_RUN_ID = "live-dashboard-1990-current-context"


@dataclass(frozen=True)
class CleanupCandidate:
    path: Path
    reason: str
    size_bytes: int


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def require_repo_local(path: Path, root: Path) -> None:
    allowed_roots = [
        root / "data" / "raw" / "sba",
        root / "data" / "warehouse",
        root / "dbt" / "logs",
        root / "dbt" / "target",
    ]
    if not any(is_within(path, allowed_root) for allowed_root in allowed_roots):
        raise ValueError(f"Refusing cleanup outside generated local-data paths: {path}")


def find_candidates(root: Path, keep_pipeline_run_id: str) -> list[CleanupCandidate]:
    candidates: list[CleanupCandidate] = []

    for path in sorted((root / "data" / "warehouse").glob("*.duckdb.tmp")):
        if path.exists():
            candidates.append(
                CleanupCandidate(
                    path=path,
                    reason="DuckDB temporary storage left by an interrupted local run",
                    size_bytes=path_size(path),
                )
            )

    sba_root = root / "data" / "raw" / "sba"
    if sba_root.exists():
        for path in sorted(sba_root.rglob("pipeline_run_id=*")):
            if not path.is_dir():
                continue
            pipeline_run_id = path.name.split("=", 1)[1]
            if pipeline_run_id == keep_pipeline_run_id:
                continue
            candidates.append(
                CleanupCandidate(
                    path=path,
                    reason=f"Old local SBA raw run ({pipeline_run_id})",
                    size_bytes=path_size(path),
                )
            )

    for path, reason in [
        (root / "dbt" / "target", "Rebuildable dbt target artifacts"),
        (root / "dbt" / "logs", "Rebuildable dbt log files"),
    ]:
        if path.exists():
            candidates.append(CleanupCandidate(path=path, reason=reason, size_bytes=path_size(path)))

    for candidate in candidates:
        require_repo_local(candidate.path, root)

    return candidates


def format_bytes(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def print_candidates(candidates: list[CleanupCandidate], root: Path) -> None:
    if not candidates:
        print("No generated local-data cleanup candidates found.")
        return

    total = sum(candidate.size_bytes for candidate in candidates)
    print(f"Found {len(candidates)} cleanup candidates totaling {format_bytes(total)}:")
    for candidate in candidates:
        display_path = candidate.path.relative_to(root)
        print(f"- {format_bytes(candidate.size_bytes):>10}  {display_path}  # {candidate.reason}")


def apply_cleanup(candidates: list[CleanupCandidate]) -> None:
    for candidate in candidates:
        if candidate.path.is_dir():
            shutil.rmtree(candidate.path)
        elif candidate.path.exists():
            candidate.path.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="List cleanup candidates without deleting them.")
    mode.add_argument("--apply", action="store_true", help="Delete the listed cleanup candidates.")
    parser.add_argument(
        "--keep-pipeline-run-id",
        default=DEFAULT_KEEP_PIPELINE_RUN_ID,
        help="SBA raw pipeline_run_id to preserve. Defaults to the current full local dashboard run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    candidates = find_candidates(root=root, keep_pipeline_run_id=args.keep_pipeline_run_id)
    print_candidates(candidates, root)

    if args.apply:
        apply_cleanup(candidates)
        print("Deleted generated local-data cleanup candidates.")
    else:
        print("Dry run only. Re-run with --apply to delete these paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
