from __future__ import annotations

from pathlib import Path


def _clean_segment(segment: str) -> str:
    cleaned = str(segment).strip("/")
    if not cleaned:
        raise ValueError("Path segments cannot be empty")
    if ".." in Path(cleaned).parts:
        raise ValueError("Path segments cannot contain parent traversal")
    return cleaned


def build_raw_s3_key(
    *,
    source_system: str,
    dataset_name: str,
    resource_name: str,
    ingestion_date: str,
    pipeline_run_id: str,
    filename: str,
) -> str:
    parts = [
        "raw",
        source_system,
        dataset_name,
        resource_name,
        f"ingestion_date={ingestion_date}",
        f"pipeline_run_id={pipeline_run_id}",
        filename,
    ]
    return "/".join(_clean_segment(part) for part in parts)


def build_local_raw_path(
    *,
    data_root: Path | str = "data",
    source_system: str,
    dataset_name: str,
    resource_name: str,
    ingestion_date: str,
    pipeline_run_id: str,
    filename: str,
) -> Path:
    return Path(data_root) / build_raw_s3_key(
        source_system=source_system,
        dataset_name=dataset_name,
        resource_name=resource_name,
        ingestion_date=ingestion_date,
        pipeline_run_id=pipeline_run_id,
        filename=filename,
    )


def build_manifest_s3_key(
    *,
    source_system: str,
    ingestion_date: str,
    pipeline_run_id: str,
    filename: str = "manifest.json",
) -> str:
    parts = [
        "manifests",
        f"source_system={source_system}",
        f"ingestion_date={ingestion_date}",
        f"pipeline_run_id={pipeline_run_id}",
        filename,
    ]
    return "/".join(_clean_segment(part) for part in parts)


def build_partitioned_artifact_key(
    *,
    prefix: str,
    source_system: str,
    dataset_name: str,
    resource_name: str,
    ingestion_date: str,
    pipeline_run_id: str,
    filename: str,
) -> str:
    parts = [
        prefix,
        source_system,
        dataset_name,
        resource_name,
        f"ingestion_date={ingestion_date}",
        f"pipeline_run_id={pipeline_run_id}",
        filename,
    ]
    return "/".join(_clean_segment(part) for part in parts)


def build_s3_uri(bucket: str, key: str) -> str:
    cleaned_bucket = bucket.removeprefix("s3://").strip("/")
    if not cleaned_bucket:
        raise ValueError("Bucket cannot be empty")
    return f"s3://{cleaned_bucket}/{key.strip('/')}"
