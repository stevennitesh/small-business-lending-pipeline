from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import duckdb
import pandas as pd

from pipelines.utils.dates import utc_now_iso
from pipelines.validation.validation_result import (
    ValidationFailedError,
    ValidationResult,
    assert_no_blocking_failures,
)


RAW_TABLES = (
    "raw_sba_7a_foia",
    "raw_sba_504_foia",
    "raw_census_bds_state_year",
    "raw_bls_laus_state_month",
    "raw_ingestion_manifest",
    "raw_validation_result",
    "raw_pipeline_run_summary",
)

SOURCE_TABLES = {
    "raw.raw_sba_7a_foia": "sba_7a",
    "raw.raw_sba_504_foia": "sba_504",
    "raw.raw_census_bds_state_year": "census_bds",
    "raw.raw_bls_laus_state_month": "bls_laus",
}


class RawLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class RawLoadSummary:
    duckdb_path: Path
    table_row_counts: dict[str, int]
    pipeline_run_ids: tuple[str, ...]


def load_raw_extracts(
    *,
    duckdb_path: Path | str = "data/warehouse/small_business_lending.duckdb",
    sba_7a_manifest_paths: Iterable[Path | str],
    sba_504_manifest_paths: Iterable[Path | str],
    census_bds_manifest_paths: Iterable[Path | str],
    bls_laus_manifest_paths: Iterable[Path | str],
    validation_result_paths: Iterable[Path | str],
) -> RawLoadSummary:
    resolved_duckdb_path = Path(duckdb_path)
    resolved_duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    validation_results = _load_validation_results(validation_result_paths)
    try:
        assert_no_blocking_failures(validation_results)
    except ValidationFailedError as exc:
        raise RawLoadError(str(exc)) from exc

    manifest_groups = {
        "raw.raw_sba_7a_foia": _load_manifests(sba_7a_manifest_paths),
        "raw.raw_sba_504_foia": _load_manifests(sba_504_manifest_paths),
        "raw.raw_census_bds_state_year": _load_manifests(census_bds_manifest_paths),
        "raw.raw_bls_laus_state_month": _load_manifests(bls_laus_manifest_paths),
    }
    pipeline_run_ids = tuple(
        sorted(
            {
                str(manifest["pipeline_run_id"])
                for manifests in manifest_groups.values()
                for manifest in manifests
            }
        )
    )

    with duckdb.connect(str(resolved_duckdb_path)) as connection:
        connection.execute("create schema if not exists raw")
        table_row_counts: dict[str, int] = {}

        for table_name, manifests in manifest_groups.items():
            frame = _load_source_frame(table_name, manifests)
            _create_or_replace_table(connection, table_name, frame)
            row_count = _table_count(connection, table_name)
            expected_row_count = sum(int(manifest["row_count"]) for manifest in manifests)
            if row_count != expected_row_count:
                raise RawLoadError(
                    f"Row count mismatch for {table_name}: "
                    f"loaded {row_count}, expected {expected_row_count}"
                )
            table_row_counts[table_name] = row_count

        manifest_frame = _normalize_records(
            [
                manifest
                for manifests in manifest_groups.values()
                for manifest in manifests
            ]
        )
        _create_or_replace_table(connection, "raw.raw_ingestion_manifest", manifest_frame)
        table_row_counts["raw.raw_ingestion_manifest"] = _table_count(
            connection,
            "raw.raw_ingestion_manifest",
        )

        validation_frame = _normalize_records(
            [result.to_dict() for result in validation_results]
        )
        _create_or_replace_table(connection, "raw.raw_validation_result", validation_frame)
        table_row_counts["raw.raw_validation_result"] = _table_count(
            connection,
            "raw.raw_validation_result",
        )

        summary_frame = pd.DataFrame(
            [
                {
                    "pipeline_run_ids": ",".join(pipeline_run_ids),
                    "loaded_at_utc": utc_now_iso(),
                    "raw_table_count": len(SOURCE_TABLES),
                    "validation_status": "passed",
                }
            ]
        )
        _create_or_replace_table(
            connection,
            "raw.raw_pipeline_run_summary",
            summary_frame,
        )
        table_row_counts["raw.raw_pipeline_run_summary"] = _table_count(
            connection,
            "raw.raw_pipeline_run_summary",
        )

    return RawLoadSummary(
        duckdb_path=resolved_duckdb_path,
        table_row_counts=table_row_counts,
        pipeline_run_ids=pipeline_run_ids,
    )


def _load_source_frame(table_name: str, manifests: list[dict[str, Any]]) -> pd.DataFrame:
    if table_name in {"raw.raw_sba_7a_foia", "raw.raw_sba_504_foia"}:
        frames = [
            _with_metadata(pd.read_csv(manifest["local_raw_path"]), manifest)
            for manifest in manifests
        ]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if table_name == "raw.raw_census_bds_state_year":
        frames = [
            _with_metadata(_read_census_bds_json(Path(manifest["local_raw_path"])), manifest)
            for manifest in manifests
        ]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if table_name == "raw.raw_bls_laus_state_month":
        frames = [
            _with_metadata(_read_bls_laus_json(Path(manifest["local_raw_path"])), manifest)
            for manifest in manifests
        ]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    raise RawLoadError(f"Unsupported raw table: {table_name}")


def _read_census_bds_json(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if len(payload) < 1:
        return pd.DataFrame()
    return pd.DataFrame(payload[1:], columns=payload[0])


def _read_bls_laus_json(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(payload.get("normalized_rows", []))


def _with_metadata(frame: pd.DataFrame, manifest: dict[str, Any]) -> pd.DataFrame:
    enriched = frame.copy()
    enriched["pipeline_run_id"] = manifest["pipeline_run_id"]
    enriched["source_system"] = manifest["source_system"]
    enriched["source_dataset"] = manifest["dataset_name"]
    enriched["source_resource_name"] = manifest["resource_name"]
    enriched["ingestion_date"] = manifest["ingestion_date"]
    enriched["raw_file_path"] = manifest["local_raw_path"]
    enriched["sha256_checksum"] = manifest["sha256_checksum"]
    return enriched


def _load_manifests(paths: Iterable[Path | str]) -> list[dict[str, Any]]:
    return [
        json.loads(Path(path).read_text(encoding="utf-8"))
        for path in paths
    ]


def _load_validation_results(paths: Iterable[Path | str]) -> list[ValidationResult]:
    validation_paths = list(paths)
    if not validation_paths:
        raise RawLoadError("At least one validation result file is required before loading.")

    results: list[ValidationResult] = []
    for path in validation_paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        results.extend(ValidationResult(**record) for record in payload)
    return results


def _normalize_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    normalized_records = [
        {
            key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
            for key, value in record.items()
        }
        for record in records
    ]
    return pd.DataFrame(normalized_records)


def _create_or_replace_table(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    frame: pd.DataFrame,
) -> None:
    connection.register("_load_frame", frame)
    try:
        connection.execute(f"create or replace table {table_name} as select * from _load_frame")
    finally:
        connection.unregister("_load_frame")


def _table_count(connection: duckdb.DuckDBPyConnection, table_name: str) -> int:
    return int(connection.execute(f"select count(*) from {table_name}").fetchone()[0])
