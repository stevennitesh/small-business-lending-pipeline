#!/usr/bin/env python3
"""Preview or remove generated local data that is safe to rebuild."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


try:
    from scripts.repo_bootstrap import add_repo_root_to_path
except ModuleNotFoundError:
    from repo_bootstrap import add_repo_root_to_path

add_repo_root_to_path()

from pipelines.powerbi.export_schema import BI_EXPORT_TABLES
from pipelines.storage.dbt_artifacts import (
    DBT_ARTIFACT_NAMES,
    expire_dbt_artifacts,
    expired_dbt_artifact_dirs,
    prune_dbt_artifacts,
)
from pipelines.utils.dates import utc_now_iso


DEFAULT_KEEP_PIPELINE_RUN_ID = "live-dashboard-1990-current-context"


@dataclass(frozen=True)
class CleanupCandidate:
    """Generated local-data path that can be previewed or deleted."""

    path: Path
    reason: str
    size_bytes: int


def repo_root() -> Path:
    """Return the repository root inferred from this script location."""
    return Path(__file__).resolve().parents[1]


def path_size(path: Path) -> int:
    """Return a file or directory size in bytes."""
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def is_within(path: Path, parent: Path) -> bool:
    """Return whether path resolves inside parent."""
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def require_repo_local(path: Path, root: Path) -> None:
    """Reject cleanup targets outside known generated local-data directories."""
    if path.resolve() != path.absolute():
        raise ValueError(f"Refusing redirected cleanup target: {path}")
    allowed_roots = [
        root / "data" / "raw" / "sba",
        root / "data" / "warehouse",
        root / "dbt" / "logs",
        root / "dbt" / "target",
    ]
    # Cleanup is intentionally allow-listed so --apply cannot remove source,
    # manifests, validation outputs, Power BI assets, or unrelated user files.
    verification_file = (
        is_within(path, root / ".tmp")
        and path.resolve() == path.absolute()
        and (
            (
                path.name == "dbt_artifacts"
                and path.parent.name.startswith("pipeline_run_id=")
                and path.parent.parent.name == "validation"
            )
            or path.name.endswith((".duckdb", ".duckdb.wal", ".duckdb.tmp"))
            or (path.suffix == ".csv" and path.stem in BI_EXPORT_TABLES)
        )
    )
    if not verification_file and not any(
        is_within(path, allowed_root) for allowed_root in allowed_roots
    ):
        raise ValueError(f"Refusing cleanup outside generated local-data paths: {path}")


def find_candidates(
    root: Path, keep_pipeline_run_id: str | None = None
) -> list[CleanupCandidate]:
    """Find generated local-data paths that are safe cleanup candidates."""
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
    if keep_pipeline_run_id is not None and sba_root.exists():
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
            candidates.append(
                CleanupCandidate(path=path, reason=reason, size_bytes=path_size(path))
            )

    for candidate in candidates:
        require_repo_local(candidate.path, root)

    return candidates


def find_verification_candidates(
    root: Path, directories: list[str]
) -> list[CleanupCandidate]:
    """Select large derived outputs in explicitly named scratch folders."""
    root = root.resolve()
    scratch = root / ".tmp"
    candidates = {}
    for value in directories:
        directory = root / value
        if (
            directory.resolve() == scratch
            or not is_within(directory, scratch)
            or directory.resolve() != directory.absolute()
        ):
            raise ValueError(
                f"Verification directory must be a direct folder inside .tmp: {value}"
            )
        for path in sorted(directory.rglob("*")):
            if path.is_file() and (
                path.name.endswith((".duckdb", ".duckdb.wal", ".duckdb.tmp"))
                or (path.suffix == ".csv" and path.stem in BI_EXPORT_TABLES)
            ):
                require_repo_local(path, root)
                candidates[path] = CleanupCandidate(
                    path,
                    "Completed verification warehouse or BI export",
                    path.stat().st_size,
                )
        for artifact_dir in sorted(directory.rglob("dbt_artifacts")):
            if (
                artifact_dir.is_dir()
                and artifact_dir.parent.name.startswith("pipeline_run_id=")
                and artifact_dir.parent.parent.name == "validation"
            ):
                require_repo_local(artifact_dir, root)
                files = [
                    artifact_dir / name
                    for name in DBT_ARTIFACT_NAMES
                    if (artifact_dir / name).is_file()
                ]
                if files:
                    candidates[artifact_dir] = CleanupCandidate(
                        artifact_dir,
                        "Completed verification dbt pair; compact receipt retained",
                        sum(p.stat().st_size for p in files),
                    )
    return list(candidates.values())


def write_cleanup_receipt(candidates: list[CleanupCandidate], root: Path) -> Path:
    """Record file hashes/sizes before removing completed verification outputs."""
    entries = []
    for candidate in candidates:
        require_repo_local(candidate.path, root)
        files = (
            [candidate.path]
            if candidate.path.is_file()
            else [
                candidate.path / name
                for name in DBT_ARTIFACT_NAMES
                if (candidate.path / name).is_file()
            ]
        )
        for path in files:
            if path.resolve() != path.absolute():
                raise ValueError(f"Refusing redirected cleanup target: {path}")
            with path.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            entries.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": checksum,
                }
            )
    directory = root / "data" / "validation"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = utc_now_iso().replace(":", "").replace("-", "").replace(".", "")
    path = directory / f"verification_cleanup_{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "checked_at_utc": utc_now_iso(),
                "candidate_files": entries,
                "status": "planned",
                "candidate_bytes": sum(c.size_bytes for c in candidates),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def format_bytes(size_bytes: int) -> str:
    """Format a byte count using binary units."""
    value = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def print_candidates(candidates: list[CleanupCandidate], root: Path) -> None:
    """Print a dry-run style cleanup candidate report."""
    if not candidates:
        print("No generated local-data cleanup candidates found.")
        return

    total = sum(candidate.size_bytes for candidate in candidates)
    print(f"Found {len(candidates)} cleanup candidates totaling {format_bytes(total)}:")
    for candidate in candidates:
        display_path = candidate.path.relative_to(root)
        print(
            f"- {format_bytes(candidate.size_bytes):>10}  {display_path}  # {candidate.reason}"
        )


def apply_cleanup(candidates: list[CleanupCandidate], *, root: Path) -> None:
    """Delete cleanup candidate paths."""
    for candidate in candidates:
        require_repo_local(candidate.path, root)
    for candidate in candidates:
        if candidate.path.name == "dbt_artifacts":
            expire_dbt_artifacts(candidate.path)
        elif candidate.path.is_dir():
            shutil.rmtree(candidate.path)
        elif candidate.path.exists():
            candidate.path.unlink()


def parse_args() -> argparse.Namespace:
    """Parse local data cleanup CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="List cleanup candidates without deleting them.",
    )
    mode.add_argument(
        "--apply", action="store_true", help="Delete the listed cleanup candidates."
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--verification-dir",
        action="append",
        help="Only remove copied warehouses, BI CSVs and full dbt pairs in this explicit .tmp folder; repeat for several folders.",
    )
    scope.add_argument(
        "--run-evidence-only",
        action="store_true",
        help="Only enforce the three-run / 20 MiB dbt history policy under data/validation.",
    )
    parser.add_argument(
        "--keep-pipeline-run-id",
        default=None,
        help="Explicitly prune SBA raw runs except this ID. Omit to preserve all raw runs.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the local generated-data cleanup CLI."""
    args = parse_args()
    root = repo_root()
    if args.run_evidence_only:
        validation_dir = root / "data" / "validation"
        expired = expired_dbt_artifact_dirs(validation_dir)
        print_candidates(
            [
                CleanupCandidate(
                    p, "Expired dbt build pair; compact receipt preserved", path_size(p)
                )
                for p in expired
            ],
            root,
        )
        if args.apply:
            prune_dbt_artifacts(validation_dir)
            print("Applied bounded dbt evidence retention.")
        else:
            print("Dry run only. Re-run with --apply to expire these pairs.")
        return 0
    candidates = (
        find_verification_candidates(root, args.verification_dir)
        if args.verification_dir
        else find_candidates(root=root, keep_pipeline_run_id=args.keep_pipeline_run_id)
    )
    print_candidates(candidates, root)
    if args.apply:
        receipt = None
        if args.verification_dir and candidates:
            receipt = write_cleanup_receipt(candidates, root)
            print(f"Preserved cleanup receipt: {receipt.relative_to(root)}")
        apply_cleanup(candidates, root=root)
        if receipt is not None:
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            payload["status"] = "completed"
            payload["completed_at_utc"] = utc_now_iso()
            receipt.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        print("Deleted generated local-data cleanup candidates.")
    else:
        print("Dry run only. Re-run with --apply to delete these paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
