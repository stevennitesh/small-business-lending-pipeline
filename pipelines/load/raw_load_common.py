"""Compatibility facade for raw-load input, metadata, and local-source helpers."""

from __future__ import annotations

import pandas as pd

from pipelines.load.raw_load_inputs import (
    ManifestReference,
    PreparedRawLoadInputs,
    assert_validation_passed,
    expected_manifest_row_count,
    flatten_manifest_groups,
    load_manifests,
    load_raw_manifest_groups,
    load_validation_results,
    pipeline_run_ids_from_manifest_groups,
    prepare_raw_load_inputs,
    require_manifest_groups,
)
from pipelines.load.raw_load_local_sources import (
    LOCAL_FRAME_SOURCE_TABLE_KINDS,
    load_local_source_frame,
)
from pipelines.load.raw_load_metadata import (
    RAW_ROW_METADATA_COLUMNS,
    RAW_SOURCE_TABLE_KEYS,
    RawLoadMetadataFrames,
    manifest_raw_row_metadata,
    normalize_records,
    raw_ingestion_manifest_frame,
    raw_load_metadata_frames,
    raw_pipeline_run_summary_frame,
    raw_validation_result_frame,
)


__all__ = [
    "LOCAL_FRAME_SOURCE_TABLE_KINDS",
    "ManifestReference",
    "PreparedRawLoadInputs",
    "RAW_ROW_METADATA_COLUMNS",
    "RAW_SOURCE_TABLE_KEYS",
    "RawLoadMetadataFrames",
    "assert_validation_passed",
    "expected_manifest_row_count",
    "flatten_manifest_groups",
    "load_local_source_frame",
    "load_manifests",
    "load_raw_manifest_groups",
    "load_validation_results",
    "manifest_raw_row_metadata",
    "normalize_records",
    "pd",
    "pipeline_run_ids_from_manifest_groups",
    "prepare_raw_load_inputs",
    "raw_ingestion_manifest_frame",
    "raw_load_metadata_frames",
    "raw_pipeline_run_summary_frame",
    "raw_validation_result_frame",
    "require_manifest_groups",
]
