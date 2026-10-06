"""Bound local dbt build evidence while preserving compact historical receipts."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

from pipelines.utils.dates import utc_now_iso


DBT_ARTIFACT_NAMES = ("manifest.json", "run_results.json")
DBT_RECEIPT_NAME = "dbt_artifact_receipt.json"
MAX_DBT_ARTIFACT_RUNS = 3
MAX_DBT_ARTIFACT_BYTES = 20 * 1024 * 1024


def _artifact_files(directory: Path) -> list[Path]:
    """Select only the two owned files, rejecting redirected cleanup paths."""
    files = []
    for name in DBT_ARTIFACT_NAMES:
        path = directory / name
        if path.resolve() != directory.resolve() / name:
            raise ValueError(f"Redirected dbt artifact path: {path}")
        if path.is_file():
            files.append(path)
    return files


def _receipt_path(directory: Path) -> Path:
    """Keep receipt updates inside the same run directory."""
    path = directory.parent / DBT_RECEIPT_NAME
    if path.resolve() != directory.resolve().parent / DBT_RECEIPT_NAME:
        raise ValueError(f"Redirected dbt receipt path: {path}")
    return path


def write_dbt_artifact_receipt(directory: Path) -> Path:
    """Retain hashes, sizes and build outcomes without retaining modeled data."""
    files = _artifact_files(directory)
    results_path = directory / "run_results.json"
    results = (
        json.loads(results_path.read_text(encoding="utf-8"))
        if results_path.is_file()
        else {}
    )
    artifacts = {}
    for path in files:
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        artifacts[path.name] = {"size_bytes": path.stat().st_size, "sha256": checksum}
    receipt = {
        "collected_at_utc": utc_now_iso(),
        "invocation_id": results.get("metadata", {}).get("invocation_id"),
        "result_status_counts": dict(
            Counter(
                item.get("status", "unknown") for item in results.get("results", [])
            )
        ),
        "artifacts": artifacts,
        "full_artifacts_retained": len(files) == len(DBT_ARTIFACT_NAMES),
        "retention": {
            "max_runs": MAX_DBT_ARTIFACT_RUNS,
            "max_bytes": MAX_DBT_ARTIFACT_BYTES,
        },
    }
    path = _receipt_path(directory)
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def expired_dbt_artifact_dirs(
    validation_dir: Path,
    *,
    current_dir: Path | None = None,
    max_runs: int = MAX_DBT_ARTIFACT_RUNS,
    max_bytes: int = MAX_DBT_ARTIFACT_BYTES,
) -> list[Path]:
    """Preview the oldest pairs beyond the recent-run count or byte budget."""
    if max_runs < 1 or max_bytes < 1:
        raise ValueError("dbt retention limits must be positive")
    root = validation_dir.resolve()
    candidates = []
    for directory in validation_dir.glob("pipeline_run_id=*/dbt_artifacts"):
        if directory.resolve() != root / directory.parent.name / "dbt_artifacts":
            raise ValueError(f"Redirected dbt evidence directory: {directory}")
        files = _artifact_files(directory)
        if not files:
            continue
        receipt = _receipt_path(directory)
        timestamp = (
            receipt.stat().st_mtime_ns
            if receipt.is_file()
            else directory.stat().st_mtime_ns
        )
        candidates.append((timestamp, directory, sum(p.stat().st_size for p in files)))
    candidates.sort(
        key=lambda item: (
            current_dir is not None and item[1].resolve() == current_dir.resolve(),
            item[0],
            str(item[1]),
        ),
        reverse=True,
    )
    total = 0
    retained = 0
    expired = []
    budget_exhausted = False
    for _, directory, size in candidates:
        if budget_exhausted or retained >= max_runs or total + size > max_bytes:
            budget_exhausted = True
            expired.append(directory)
        else:
            retained += 1
            total += size
    return expired


def expire_dbt_artifacts(directory: Path) -> None:
    """Discard one completed pair while keeping its compact evidence receipt."""
    expected = (
        directory.parent.parent.resolve() / directory.parent.name / "dbt_artifacts"
    )
    if (
        not directory.parent.name.startswith("pipeline_run_id=")
        or directory.resolve() != expected
    ):
        raise ValueError(f"Redirected dbt evidence directory: {directory}")
    _artifact_files(directory)
    receipt_path = _receipt_path(directory)
    if not receipt_path.is_file():
        write_dbt_artifact_receipt(directory)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    try:
        for path in _artifact_files(directory):
            path.unlink()
    finally:
        receipt["full_artifacts_retained"] = all(
            (directory / name).is_file() for name in DBT_ARTIFACT_NAMES
        )
        if not any((directory / name).exists() for name in DBT_ARTIFACT_NAMES):
            receipt["pruned_at_utc"] = utc_now_iso()
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if not any(directory.iterdir()):
        directory.rmdir()


def prune_dbt_artifacts(
    validation_dir: Path, *, current_dir: Path | None = None, **limits: int
) -> list[Path]:
    """Expire owned JSON files only, preserving receipts and all run summaries."""
    expired = expired_dbt_artifact_dirs(
        validation_dir, current_dir=current_dir, **limits
    )
    for directory in expired:
        expire_dbt_artifacts(directory)
    return expired


def retain_dbt_artifacts(target_dir: Path, run_validation_dir: Path) -> dict[str, str]:
    """Copy a required build pair, write its receipt and enforce local limits."""
    missing = [name for name in DBT_ARTIFACT_NAMES if not (target_dir / name).is_file()]
    if missing:
        raise RuntimeError("dbt build did not produce artifacts: " + ", ".join(missing))
    size = sum((target_dir / name).stat().st_size for name in DBT_ARTIFACT_NAMES)
    if size > MAX_DBT_ARTIFACT_BYTES:
        raise RuntimeError(
            "dbt artifact pair exceeds the 20 MiB local retention budget"
        )
    directory = run_validation_dir / "dbt_artifacts"
    if directory.resolve() != run_validation_dir.resolve() / "dbt_artifacts":
        raise ValueError(f"Redirected dbt evidence directory: {directory}")
    _artifact_files(directory)
    _receipt_path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name in DBT_ARTIFACT_NAMES:
        shutil.copy2(target_dir / name, directory / name)
    write_dbt_artifact_receipt(directory)
    prune_dbt_artifacts(run_validation_dir.parent, current_dir=directory)
    return {name: str(directory / name) for name in DBT_ARTIFACT_NAMES}
