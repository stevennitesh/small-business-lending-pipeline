from __future__ import annotations

import json
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from pipelines.load.s3_loader import (
    S3UploadRequiredError,
    S3UploadItem,
    build_dbt_artifact_upload_item,
    build_manifest_upload_item,
    build_raw_upload_item,
    build_validation_upload_item,
    upload_run_artifacts_to_s3,
    upload_items_to_s3,
)


def test_s3_upload_items_follow_partitioning_contract(tmp_path):
    raw_path = tmp_path / "raw.csv"
    raw_path.write_text("a,b\n1,2\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    validation_path = tmp_path / "validation_results.json"
    validation_path.write_text("[]", encoding="utf-8")
    dbt_manifest_path = tmp_path / "dbt_manifest.json"
    dbt_manifest_path.write_text("{}", encoding="utf-8")
    manifest = {
        "pipeline_run_id": "run-123",
        "source_system": "sba",
        "dataset_name": "7a_foia",
        "resource_name": "source_period=fy2020_present",
        "ingestion_date": "2026-05-07",
        "local_raw_path": str(raw_path),
    }

    assert build_raw_upload_item(manifest).s3_key == (
        "raw/sba/7a_foia/source_period=fy2020_present/"
        "ingestion_date=2026-05-07/pipeline_run_id=run-123/raw.csv"
    )
    assert build_manifest_upload_item(manifest_path, manifest).s3_key == (
        "manifests/sba/7a_foia/source_period=fy2020_present/"
        "ingestion_date=2026-05-07/pipeline_run_id=run-123/manifest.json"
    )
    assert build_validation_upload_item(validation_path, manifest).s3_key == (
        "validation/sba/7a_foia/source_period=fy2020_present/"
        "ingestion_date=2026-05-07/pipeline_run_id=run-123/validation_results.json"
    )
    assert build_dbt_artifact_upload_item(
        dbt_manifest_path,
        ingestion_date="2026-05-07",
        pipeline_run_id="run-123",
    ).s3_key == (
        "validation/dbt/artifacts/ingestion_date=2026-05-07/"
        "pipeline_run_id=run-123/dbt_manifest.json"
    )


def test_upload_items_to_s3_retries_transient_failure(tmp_path):
    source_path = tmp_path / "raw.csv"
    source_path.write_text("a,b\n1,2\n", encoding="utf-8")
    item = S3UploadItem(
        local_path=source_path,
        s3_key=(
            "raw/sba/7a_foia/source_period=fy2020_present/"
            "ingestion_date=2026-05-07/pipeline_run_id=run-123/raw.csv"
        ),
    )
    s3_client = FlakyS3Client(failures_before_success=2)

    summary = upload_items_to_s3(
        [item],
        bucket="unit-test-bucket",
        s3_client=s3_client,
        required=True,
        max_attempts=3,
        base_delay_seconds=0,
    )

    assert summary.uploaded_count == 1
    assert s3_client.calls == [
        ("unit-test-bucket", item.s3_key),
        ("unit-test-bucket", item.s3_key),
        ("unit-test-bucket", item.s3_key),
    ]


def test_upload_items_to_s3_required_mode_fails_but_optional_mode_warns(tmp_path):
    source_path = tmp_path / "raw.csv"
    source_path.write_text("a,b\n1,2\n", encoding="utf-8")
    item = S3UploadItem(
        local_path=source_path,
        s3_key=(
            "raw/sba/7a_foia/source_period=fy2020_present/"
            "ingestion_date=2026-05-07/pipeline_run_id=run-123/raw.csv"
        ),
    )

    with pytest.raises(S3UploadRequiredError, match="required S3 upload failed"):
        upload_items_to_s3(
            [item],
            bucket="unit-test-bucket",
            s3_client=AlwaysFailingS3Client(),
            required=True,
            max_attempts=1,
            base_delay_seconds=0,
        )

    summary = upload_items_to_s3(
        [item],
        bucket=None,
        s3_client=AlwaysFailingS3Client(),
        required=False,
        max_attempts=1,
        base_delay_seconds=0,
    )

    assert summary.uploaded_count == 0
    assert summary.skipped
    assert "S3 upload skipped" in summary.warning


def test_upload_run_artifacts_applies_local_and_cloud_mode_policy(tmp_path):
    raw_path = tmp_path / "raw.csv"
    raw_path.write_text("a,b\n1,2\n", encoding="utf-8")
    validation_path = tmp_path / "validation_results.json"
    validation_path.write_text("[]", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_run_id": "run-123",
                "source_system": "sba",
                "dataset_name": "7a_foia",
                "resource_name": "source_period=fy2020_present",
                "ingestion_date": "2026-05-07",
                "local_raw_path": str(raw_path),
            }
        ),
        encoding="utf-8",
    )

    local_summary = upload_run_artifacts_to_s3(
        manifest_paths=[manifest_path],
        validation_result_path=validation_path,
        bucket=None,
        run_mode="local",
        s3_client=AlwaysFailingS3Client(),
        max_attempts=1,
        base_delay_seconds=0,
    )

    assert local_summary.skipped

    with pytest.raises(S3UploadRequiredError, match="S3 upload skipped"):
        upload_run_artifacts_to_s3(
            manifest_paths=[manifest_path],
            validation_result_path=validation_path,
            bucket=None,
            run_mode="cloud",
            s3_client=AlwaysFailingS3Client(),
            max_attempts=1,
            base_delay_seconds=0,
        )


def test_upload_run_artifacts_keeps_final_mode_as_compatibility_alias(tmp_path):
    raw_path = tmp_path / "raw.csv"
    raw_path.write_text("a,b\n1,2\n", encoding="utf-8")
    validation_path = tmp_path / "validation_results.json"
    validation_path.write_text("[]", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_run_id": "run-123",
                "source_system": "sba",
                "dataset_name": "7a_foia",
                "resource_name": "source_period=fy2020_present",
                "ingestion_date": "2026-05-07",
                "local_raw_path": str(raw_path),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(S3UploadRequiredError, match="S3 upload skipped"):
        upload_run_artifacts_to_s3(
            manifest_paths=[manifest_path],
            validation_result_path=validation_path,
            bucket=None,
            run_mode="final",
            s3_client=AlwaysFailingS3Client(),
            max_attempts=1,
            base_delay_seconds=0,
        )


def test_upload_run_artifacts_skips_raw_upload_for_s3_backed_manifest(tmp_path):
    validation_path = tmp_path / "validation_results.json"
    validation_path.write_text("[]", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_run_id": "cloud-run",
                "source_system": "census",
                "dataset_name": "bds",
                "resource_name": "bds_state_year",
                "ingestion_date": "2026-05-07",
                "storage_backend": "s3",
                "raw_uri": (
                    "s3://unit-test-bucket/raw/census/bds/bds_state_year/"
                    "ingestion_date=2026-05-07/pipeline_run_id=cloud-run/raw.json"
                ),
                "local_raw_path": None,
                "s3_raw_uri": (
                    "s3://unit-test-bucket/raw/census/bds/bds_state_year/"
                    "ingestion_date=2026-05-07/pipeline_run_id=cloud-run/raw.json"
                ),
            }
        ),
        encoding="utf-8",
    )
    s3_client = FlakyS3Client(failures_before_success=0)

    summary = upload_run_artifacts_to_s3(
        manifest_paths=[manifest_path],
        validation_result_path=validation_path,
        bucket="unit-test-bucket",
        run_mode="cloud",
        s3_client=s3_client,
        max_attempts=1,
        base_delay_seconds=0,
    )

    assert summary.uploaded_count == 2
    assert [key for _, key in s3_client.calls] == [
        (
            "manifests/census/bds/bds_state_year/"
            "ingestion_date=2026-05-07/pipeline_run_id=cloud-run/manifest.json"
        ),
        (
            "validation/census/bds/bds_state_year/"
            "ingestion_date=2026-05-07/pipeline_run_id=cloud-run/"
            "validation_results.json"
        ),
    ]


class FlakyS3Client:
    def __init__(self, *, failures_before_success: int) -> None:
        self.failures_before_success = failures_before_success
        self.calls: list[tuple[str, str]] = []

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.calls.append((bucket, key))
        Path(filename).read_text(encoding="utf-8")
        if len(self.calls) <= self.failures_before_success:
            raise _client_error("Throttling")


class AlwaysFailingS3Client:
    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        Path(filename).read_text(encoding="utf-8")
        raise _client_error("ServiceUnavailable")


def _client_error(code: str) -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": code, "Message": "temporary failure"}},
        operation_name="PutObject",
    )
