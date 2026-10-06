from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd

from pipelines.load.raw_load_inputs import flatten_manifest_groups
from pipelines.validation.validation_result import ValidationResult


RAW_SOURCE_TABLE_KEYS = (
    "raw_sba_7a_foia",
    "raw_sba_504_foia",
    "raw_census_bds_state_year",
    "raw_bls_laus_state_month",
)

RAW_ROW_METADATA_COLUMNS = (
    "pipeline_run_id",
    "source_system",
    "source_dataset",
    "source_resource_name",
    "ingestion_date",
    "storage_backend",
    "raw_uri",
    "raw_file_path",
    "s3_raw_uri",
    "sha256_checksum",
)


@dataclass(frozen=True)
class RawLoadMetadataFrames:
    """Metadata frames common to DuckDB and Snowflake raw load routes."""

    manifest: pd.DataFrame
    validation: pd.DataFrame
    summary: pd.DataFrame


def raw_ingestion_manifest_frame(
    manifest_groups: dict[str, list[dict[str, Any]]],
) -> pd.DataFrame:
    """Build the raw ingestion manifest metadata table frame."""
    return normalize_records(flatten_manifest_groups(manifest_groups))


def raw_validation_result_frame(
    validation_results: Iterable[ValidationResult],
) -> pd.DataFrame:
    """Build the raw validation-result metadata table frame."""
    return normalize_records([result.to_dict() for result in validation_results])


def raw_pipeline_run_summary_frame(
    *,
    pipeline_run_ids: tuple[str, ...],
    loaded_at_utc: str,
    validation_status: str = "passed",
    extra_values: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build the one-row summary frame for a completed raw load."""
    summary = {
        "pipeline_run_ids": ",".join(pipeline_run_ids),
        "loaded_at_utc": loaded_at_utc,
        "raw_table_count": len(RAW_SOURCE_TABLE_KEYS),
        "validation_status": validation_status,
    }
    if extra_values:
        summary.update(extra_values)
    return pd.DataFrame([summary])


def raw_load_metadata_frames(
    *,
    manifest_groups: dict[str, list[dict[str, Any]]],
    validation_results: Iterable[ValidationResult],
    pipeline_run_ids: tuple[str, ...],
    loaded_at_utc: str,
    summary_extra_values: dict[str, Any] | None = None,
) -> RawLoadMetadataFrames:
    """Build the standard raw metadata frames for a completed load."""
    return RawLoadMetadataFrames(
        manifest=raw_ingestion_manifest_frame(manifest_groups),
        validation=raw_validation_result_frame(validation_results),
        summary=raw_pipeline_run_summary_frame(
            pipeline_run_ids=pipeline_run_ids,
            loaded_at_utc=loaded_at_utc,
            extra_values=summary_extra_values,
        ),
    )


def normalize_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert metadata records into a frame with scalar cell values."""
    # Raw metadata tables are warehouse-friendly scalar tables; nested validation
    # details stay available as deterministic JSON text instead of Python objects.
    normalized_records = [
        {
            key: json.dumps(value, sort_keys=True)
            if isinstance(value, (dict, list))
            else value
            for key, value in record.items()
        }
        for record in records
    ]
    return pd.DataFrame(normalized_records)


def manifest_raw_row_metadata(
    manifest: dict[str, Any],
    *,
    uppercase: bool = False,
) -> dict[str, Any]:
    """Return lineage metadata values attached to rows loaded from a manifest."""
    local_raw_path = manifest.get("local_raw_path")
    raw_uri = manifest.get("raw_uri") or local_raw_path or manifest.get("s3_raw_uri")
    storage_backend = manifest.get("storage_backend") or (
        "s3" if not local_raw_path else "local"
    )
    metadata = {
        "pipeline_run_id": manifest["pipeline_run_id"],
        "source_system": manifest["source_system"],
        "source_dataset": manifest["dataset_name"],
        "source_resource_name": manifest["resource_name"],
        "ingestion_date": manifest["ingestion_date"],
        "storage_backend": storage_backend,
        "raw_uri": raw_uri,
        "raw_file_path": local_raw_path or raw_uri,
        "s3_raw_uri": manifest["s3_raw_uri"],
        "sha256_checksum": manifest["sha256_checksum"],
    }
    if uppercase:
        return {key.upper(): value for key, value in metadata.items()}
    return metadata
