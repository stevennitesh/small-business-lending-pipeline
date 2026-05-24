from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from pipelines.storage.raw_artifacts import ArtifactLocation, ArtifactReader
from pipelines.validation.validation_result import (
    ValidationFailedError,
    ValidationResult,
    assert_no_blocking_failures,
)


SOURCE_TABLE_KINDS = {
    "raw_sba_7a_foia": "sba_csv",
    "raw_sba_504_foia": "sba_csv",
    "raw_census_bds_state_year": "census_bds_json",
    "raw_bls_laus_state_month": "bls_laus_json",
}

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


ManifestReference = Path | str | ArtifactLocation


def load_manifests(
    paths: Iterable[ManifestReference],
    *,
    artifact_reader: ArtifactReader | None = None,
) -> list[dict[str, Any]]:
    reader = artifact_reader or ArtifactReader()
    return [
        json.loads(_read_reference_text(path, reader))
        for path in paths
    ]


def load_validation_results(
    paths: Iterable[ManifestReference],
    *,
    error_cls: type[Exception],
    missing_message: str,
    artifact_reader: ArtifactReader | None = None,
) -> list[ValidationResult]:
    validation_paths = list(paths)
    if not validation_paths:
        raise error_cls(missing_message)

    reader = artifact_reader or ArtifactReader()
    results: list[ValidationResult] = []
    for path in validation_paths:
        payload = json.loads(_read_reference_text(path, reader))
        results.extend(ValidationResult(**record) for record in payload)
    return results


def assert_validation_passed(
    validation_results: list[ValidationResult],
    *,
    error_cls: type[Exception],
) -> None:
    try:
        assert_no_blocking_failures(validation_results)
    except ValidationFailedError as exc:
        raise error_cls(str(exc)) from exc


def require_manifest_groups(
    manifest_groups: dict[str, list[dict[str, Any]]],
    *,
    error_cls: type[Exception],
) -> None:
    empty_group_names = [
        table_name
        for table_name, manifests in manifest_groups.items()
        if not manifests
    ]
    if empty_group_names:
        raise error_cls(
            "Required manifest group is empty: "
            + ", ".join(sorted(empty_group_names))
        )


def pipeline_run_ids_from_manifest_groups(
    manifest_groups: dict[str, list[dict[str, Any]]],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(manifest["pipeline_run_id"])
                for manifests in manifest_groups.values()
                for manifest in manifests
            }
        )
    )


def flatten_manifest_groups(
    manifest_groups: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [
        manifest
        for manifests in manifest_groups.values()
        for manifest in manifests
    ]


def load_local_source_frame(
    table_name: str,
    manifests: list[dict[str, Any]],
    *,
    error_cls: type[Exception],
) -> pd.DataFrame:
    """Read local raw files referenced by manifests into a source-shaped frame."""

    table_key = _table_key(table_name)
    table_kind = SOURCE_TABLE_KINDS.get(table_key)
    if table_kind is None:
        raise error_cls(f"Unsupported raw table: {table_name}")

    frames = [
        _with_metadata(_read_manifest_frame(table_kind, manifest), manifest)
        for manifest in manifests
    ]
    return pd.concat(frames, ignore_index=True)


def normalize_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    normalized_records = [
        {
            key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
            for key, value in record.items()
        }
        for record in records
    ]
    return pd.DataFrame(normalized_records)


def manifest_raw_row_metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    local_raw_path = manifest.get("local_raw_path")
    raw_uri = manifest.get("raw_uri") or local_raw_path or manifest.get("s3_raw_uri")
    storage_backend = manifest.get("storage_backend") or (
        "s3" if not local_raw_path else "local"
    )
    return {
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


def _read_reference_text(
    reference: ManifestReference,
    artifact_reader: ArtifactReader,
) -> str:
    if isinstance(reference, ArtifactLocation):
        return artifact_reader.read_text(reference)
    return Path(reference).read_text(encoding="utf-8")


def _table_key(table_name: str) -> str:
    return table_name.split(".", maxsplit=1)[-1]


def _read_manifest_frame(table_kind: str, manifest: dict[str, Any]) -> pd.DataFrame:
    raw_path = Path(manifest["local_raw_path"])
    if table_kind == "sba_csv":
        return pd.read_csv(raw_path, low_memory=False)
    if table_kind == "census_bds_json":
        return _read_census_bds_json(raw_path)
    if table_kind == "bls_laus_json":
        return _read_bls_laus_json(raw_path)
    raise ValueError(f"Unsupported source table kind: {table_kind}")


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
    for column_name, value in manifest_raw_row_metadata(manifest).items():
        enriched[column_name] = value
    return enriched
