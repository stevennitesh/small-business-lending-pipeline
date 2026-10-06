from __future__ import annotations

import json

from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    ArtifactReader,
    RawArtifactReader,
)
from pipelines.utils.hashing import hash_bytes
from pipelines.validation.raw_manifest_artifact_validation import (
    check_raw_manifest,
)
from pipelines.validation.raw_manifest_rule_checks import (
    check_cloud_manifest_storage,
    check_manifest_raw_uri_required,
)
from tests.unit.artifact_store_test_helpers import FakeS3ObjectClient
from tests.unit.raw_manifest_test_helpers import (
    manifest_for,
    s3_manifest_for,
    write_manifest,
    write_raw_file,
)
from tests.unit.validation_test_helpers import raw_check_result


def test_raw_manifest_artifact_validation_passes_for_s3_backed_file(tmp_path):
    """Validate that raw manifest artifact validation passes for S3 backed file."""
    raw_payload = b'[["YEAR","state"],["2023","01"],["2023","02"]]\n'
    manifest = s3_manifest_for(raw_payload)
    manifest_path = write_manifest(tmp_path, manifest)

    s3_client = FakeS3ObjectClient(
        {("bucket", "raw/census/bds/file.json"): raw_payload}
    )
    results = check_raw_manifest(
        manifest_path,
        artifact_reader=RawArtifactReader(s3_client=s3_client),
    )

    assert all(result.status == "passed" for result in results)
    assert s3_client.get_calls == [("bucket", "raw/census/bds/file.json")]


def test_raw_manifest_artifact_validation_reads_manifest_artifact_from_s3(tmp_path):
    """Validate that raw manifest artifact validation reads manifest artifact from S3."""
    raw_payload = b'[["YEAR","state"],["2023","01"],["2024","01"]]\n'
    manifest = s3_manifest_for(raw_payload)
    s3_client = FakeS3ObjectClient(
        {
            ("bucket", "manifests/census/bds/manifest.json"): json.dumps(
                manifest
            ).encode("utf-8"),
            ("bucket", "raw/census/bds/file.json"): raw_payload,
        }
    )

    results = check_raw_manifest(
        ArtifactLocation(
            storage_backend="s3",
            artifact_uri="s3://bucket/manifests/census/bds/manifest.json",
            artifact_key="manifests/census/bds/manifest.json",
            s3_uri="s3://bucket/manifests/census/bds/manifest.json",
        ),
        artifact_reader=RawArtifactReader(s3_client=s3_client),
        manifest_artifact_reader=ArtifactReader(s3_client=s3_client),
    )

    assert all(result.status == "passed" for result in results)


def test_cloud_manifest_storage_check_rejects_local_backed_manifest(tmp_path):
    """Validate that cloud manifest storage check rejects local backed manifest."""
    raw_file = write_raw_file(tmp_path)
    manifest = manifest_for(raw_file)
    manifest["raw_uri"] = str(raw_file)
    manifest["storage_backend"] = "local"

    result = check_cloud_manifest_storage(manifest)

    assert result.validation_check_id == "RAW_012"
    assert result.status == "failed"
    assert result.severity == "fail"


def test_raw_uri_required_check_rejects_missing_identity(tmp_path):
    """Validate that raw uri required check rejects missing identity."""
    raw_file = write_raw_file(tmp_path)
    manifest = manifest_for(raw_file)
    manifest.pop("raw_uri", None)

    result = check_manifest_raw_uri_required(manifest)

    assert result.validation_check_id == "RAW_013"
    assert result.status == "failed"
    assert result.severity == "fail"


def test_raw_manifest_artifact_validation_fails_cleanly_for_missing_s3_object(
    tmp_path,
):
    """Validate that raw manifest artifact validation fails cleanly for missing S3 object."""
    placeholder_file = write_raw_file(tmp_path, "[]\n", filename="placeholder.json")
    manifest = manifest_for(placeholder_file)
    manifest.update(
        {
            "storage_backend": "s3",
            "raw_uri": "s3://bucket/raw/census/bds/missing.json",
            "local_raw_path": None,
            "s3_raw_uri": "s3://bucket/raw/census/bds/missing.json",
            "sha256_checksum": hash_bytes(b"[]\n"),
        }
    )
    manifest_path = write_manifest(tmp_path, manifest)

    results = check_raw_manifest(
        manifest_path,
        artifact_reader=RawArtifactReader(s3_client=FakeS3ObjectClient({})),
    )
    file_exists = raw_check_result(results, "RAW_001")

    assert file_exists.status == "failed"
    assert file_exists.severity == "fail"
    assert file_exists.observed_value == "s3://bucket/raw/census/bds/missing.json"
