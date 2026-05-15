from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

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


def load_manifests(paths: Iterable[Path | str]) -> list[dict[str, Any]]:
    return [
        json.loads(Path(path).read_text(encoding="utf-8"))
        for path in paths
    ]


def load_validation_results(
    paths: Iterable[Path | str],
    *,
    error_cls: type[Exception],
    missing_message: str,
) -> list[ValidationResult]:
    validation_paths = list(paths)
    if not validation_paths:
        raise error_cls(missing_message)

    results: list[ValidationResult] = []
    for path in validation_paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
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


def load_source_frame(
    table_name: str,
    manifests: list[dict[str, Any]],
    *,
    error_cls: type[Exception],
) -> pd.DataFrame:
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


def _table_key(table_name: str) -> str:
    return table_name.split(".", maxsplit=1)[-1]


def _read_manifest_frame(table_kind: str, manifest: dict[str, Any]) -> pd.DataFrame:
    raw_path = Path(manifest["local_raw_path"])
    if table_kind == "sba_csv":
        return pd.read_csv(raw_path)
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
    enriched["pipeline_run_id"] = manifest["pipeline_run_id"]
    enriched["source_system"] = manifest["source_system"]
    enriched["source_dataset"] = manifest["dataset_name"]
    enriched["source_resource_name"] = manifest["resource_name"]
    enriched["ingestion_date"] = manifest["ingestion_date"]
    enriched["raw_file_path"] = manifest["local_raw_path"]
    enriched["s3_raw_uri"] = manifest["s3_raw_uri"]
    enriched["sha256_checksum"] = manifest["sha256_checksum"]
    return enriched
