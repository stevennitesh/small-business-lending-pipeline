from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd

from pipelines.load.raw_load_common import (
    assert_validation_passed,
    flatten_manifest_groups,
    load_local_source_frame,
    load_manifests,
    load_validation_results,
    normalize_records,
    pipeline_run_ids_from_manifest_groups,
    require_manifest_groups,
)
from pipelines.utils.dates import utc_now_iso


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

    validation_results = load_validation_results(
        validation_result_paths,
        error_cls=RawLoadError,
        missing_message="At least one validation result file is required before loading.",
    )
    assert_validation_passed(validation_results, error_cls=RawLoadError)

    manifest_groups = {
        "raw.raw_sba_7a_foia": load_manifests(sba_7a_manifest_paths),
        "raw.raw_sba_504_foia": load_manifests(sba_504_manifest_paths),
        "raw.raw_census_bds_state_year": load_manifests(census_bds_manifest_paths),
        "raw.raw_bls_laus_state_month": load_manifests(bls_laus_manifest_paths),
    }
    require_manifest_groups(manifest_groups, error_cls=RawLoadError)
    pipeline_run_ids = pipeline_run_ids_from_manifest_groups(manifest_groups)

    with duckdb.connect(str(resolved_duckdb_path)) as connection:
        connection.execute("create schema if not exists raw")
        table_row_counts: dict[str, int] = {}

        for table_name, manifests in manifest_groups.items():
            frame = load_local_source_frame(
                table_name,
                manifests,
                error_cls=RawLoadError,
            )
            _create_or_replace_table(connection, table_name, frame)
            row_count = _table_count(connection, table_name)
            expected_row_count = sum(int(manifest["row_count"]) for manifest in manifests)
            if row_count != expected_row_count:
                raise RawLoadError(
                    f"Row count mismatch for {table_name}: "
                    f"loaded {row_count}, expected {expected_row_count}"
                )
            table_row_counts[table_name] = row_count

        manifest_frame = normalize_records(
            [
                manifest
                for manifest in flatten_manifest_groups(manifest_groups)
            ]
        )
        _create_or_replace_table(connection, "raw.raw_ingestion_manifest", manifest_frame)
        table_row_counts["raw.raw_ingestion_manifest"] = _table_count(
            connection,
            "raw.raw_ingestion_manifest",
        )

        validation_frame = normalize_records(
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
