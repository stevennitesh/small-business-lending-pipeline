from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipelines.utils.paths import build_partitioned_artifact_key, build_raw_s3_key
from pipelines.storage.s3_objects import parse_s3_uri


@dataclass(frozen=True)
class S3UploadItem:
    """Local file plus destination key for an S3 artifact upload."""

    local_path: Path
    s3_key: str


def build_raw_upload_item(manifest: dict[str, Any]) -> S3UploadItem | None:
    """Build the raw artifact upload item for a local-backed manifest."""
    if _is_s3_backed(manifest):
        # Cloud extraction already wrote this raw artifact to S3; re-uploading it
        # from the local runner would duplicate data and may not have a local file.
        return None
    local_path = Path(str(manifest["local_raw_path"]))
    declared_uri = manifest.get("s3_raw_uri")
    declared_key = parse_s3_uri(str(declared_uri)).key if declared_uri else None
    return S3UploadItem(
        local_path=local_path,
        s3_key=declared_key
        or build_raw_s3_key(
            source_system=str(manifest["source_system"]),
            dataset_name=str(manifest["dataset_name"]),
            resource_name=str(manifest["resource_name"]),
            ingestion_date=str(manifest["ingestion_date"]),
            pipeline_run_id=str(manifest["pipeline_run_id"]),
            filename=local_path.name,
        ),
    )


def build_manifest_upload_item(
    manifest_path: Path | str,
    manifest: dict[str, Any],
) -> S3UploadItem:
    """Build the partitioned upload item for one manifest file."""
    return S3UploadItem(
        local_path=Path(manifest_path),
        s3_key=_partitioned_artifact_key(
            prefix="manifests",
            manifest=manifest,
            filename=Path(manifest_path).name,
        ),
    )


def build_validation_upload_item(
    validation_path: Path | str,
    manifest: dict[str, Any],
) -> S3UploadItem:
    """Build the partitioned upload item for validation results."""
    return S3UploadItem(
        local_path=Path(validation_path),
        s3_key=_partitioned_artifact_key(
            prefix="validation",
            manifest=manifest,
            filename=Path(validation_path).name,
        ),
    )


def build_dbt_artifact_upload_item(
    artifact_path: Path | str,
    *,
    ingestion_date: str,
    pipeline_run_id: str,
) -> S3UploadItem:
    """Build the upload item for a dbt artifact under a run partition."""
    path = Path(artifact_path)
    return S3UploadItem(
        local_path=path,
        s3_key="/".join(
            [
                "validation",
                "dbt",
                "artifacts",
                f"ingestion_date={ingestion_date}",
                f"pipeline_run_id={pipeline_run_id}",
                path.name,
            ]
        ),
    )


def build_run_upload_items(
    *,
    manifest_paths: list[Path | str],
    validation_result_path: Path | str,
    dbt_artifact_paths: list[Path | str] | None = None,
) -> list[S3UploadItem]:
    """Build all upload items needed to promote a run's local artifacts."""
    items: list[S3UploadItem] = []
    manifests: list[dict[str, Any]] = []
    for manifest_path in manifest_paths:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        manifests.append(manifest)
        raw_upload_item = build_raw_upload_item(manifest)
        if raw_upload_item is not None:
            items.append(raw_upload_item)
        items.append(build_manifest_upload_item(manifest_path, manifest))
        items.append(build_validation_upload_item(validation_result_path, manifest))

    if dbt_artifact_paths:
        ingestion_date, pipeline_run_id = _single_run_partition(manifests)
        items.extend(
            build_dbt_artifact_upload_item(
                artifact_path,
                ingestion_date=ingestion_date,
                pipeline_run_id=pipeline_run_id,
            )
            for artifact_path in dbt_artifact_paths
        )
    return items


def _is_s3_backed(manifest: dict[str, Any]) -> bool:
    """Return whether the manifest already references S3-backed raw data."""
    return str(manifest.get("storage_backend", "local")).casefold() == "s3"


def _partitioned_artifact_key(
    *,
    prefix: str,
    manifest: dict[str, Any],
    filename: str,
) -> str:
    """Build a manifest-partitioned artifact key for a local file."""
    return build_partitioned_artifact_key(
        prefix=prefix,
        source_system=str(manifest["source_system"]),
        dataset_name=str(manifest["dataset_name"]),
        resource_name=str(manifest["resource_name"]),
        ingestion_date=str(manifest["ingestion_date"]),
        pipeline_run_id=str(manifest["pipeline_run_id"]),
        filename=filename,
    )


def _single_run_partition(manifests: list[dict[str, Any]]) -> tuple[str, str]:
    """Return the shared run partition required for dbt artifact uploads."""
    partitions = {
        (str(manifest["ingestion_date"]), str(manifest["pipeline_run_id"]))
        for manifest in manifests
    }
    if len(partitions) != 1:
        raise ValueError(
            "dbt artifact uploads require one ingestion_date and pipeline_run_id."
        )
    return next(iter(partitions))
