from __future__ import annotations

from pathlib import Path


def build_raw_s3_key(
    *,
    source_system: str,
    dataset_name: str,
    resource_name: str,
    ingestion_date: str,
    pipeline_run_id: str,
    filename: str,
) -> str:
    """Build the partitioned raw artifact key used locally and in S3."""
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
    """Build the local filesystem path mirroring the raw S3 key layout."""
    return Path(data_root) / build_raw_s3_key(
        source_system=source_system,
        dataset_name=dataset_name,
        resource_name=resource_name,
        ingestion_date=ingestion_date,
        pipeline_run_id=pipeline_run_id,
        filename=filename,
    )


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
    """Build a source/run-partitioned key for non-raw artifacts."""
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
    """Build an s3:// URI from a bucket and object key."""
    cleaned_bucket = bucket.removeprefix("s3://").strip("/")
    if not cleaned_bucket:
        raise ValueError("Bucket cannot be empty")
    return f"s3://{cleaned_bucket}/{key.strip('/')}"


def _clean_segment(segment: str) -> str:
    """Normalize and validate one path/key segment."""
    cleaned = str(segment).strip("/")
    if not cleaned:
        raise ValueError("Path segments cannot be empty")
    if ".." in Path(cleaned).parts:
        raise ValueError("Path segments cannot contain parent traversal")
    return cleaned
