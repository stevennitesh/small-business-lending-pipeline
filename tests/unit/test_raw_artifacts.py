from __future__ import annotations

from pipelines.storage.raw_artifacts import (
    ArtifactReader,
    LocalArtifactStore,
    S3ArtifactStore,
    artifact_reader_for_route,
    artifact_store_for_route,
)
from tests.unit.artifact_store_test_helpers import FakeS3ObjectClient


def test_local_artifact_store_writes_partitioned_manifest(tmp_path):
    store = LocalArtifactStore(data_root=tmp_path, s3_bucket="mirror-bucket")

    location = store.location(
        prefix="manifests",
        source_system="census",
        dataset_name="bds",
        resource_name="bds_state_year",
        ingestion_date="2026-05-17",
        pipeline_run_id="run-123",
        filename="manifest.json",
    )
    store.write_bytes(location, b'{"ok": true}\n')

    assert location.storage_backend == "local"
    assert location.artifact_key == (
        "manifests/census/bds/bds_state_year/"
        "ingestion_date=2026-05-17/pipeline_run_id=run-123/manifest.json"
    )
    assert location.artifact_uri == str(location.local_path)
    assert location.s3_uri == (
        "s3://mirror-bucket/manifests/census/bds/bds_state_year/"
        "ingestion_date=2026-05-17/pipeline_run_id=run-123/manifest.json"
    )
    assert store.read_bytes(location) == b'{"ok": true}\n'


def test_s3_artifact_store_writes_partitioned_validation_result():
    s3_client = FakeS3ObjectClient()
    store = S3ArtifactStore(bucket="cloud-bucket", s3_client=s3_client)

    location = store.location(
        prefix="validation",
        source_system="bls",
        dataset_name="laus",
        resource_name="laus_state_month",
        ingestion_date="2026-05-17",
        pipeline_run_id="cloud-run",
        filename="validation_results.json",
    )
    store.write_bytes(location, b"[]\n")

    assert location.storage_backend == "s3"
    assert location.local_path is None
    assert location.artifact_uri == (
        "s3://cloud-bucket/validation/bls/laus/laus_state_month/"
        "ingestion_date=2026-05-17/pipeline_run_id=cloud-run/"
        "validation_results.json"
    )
    assert store.read_bytes(location) == b"[]\n"
    assert (
        s3_client.objects[
            (
                "cloud-bucket",
                "validation/bls/laus/laus_state_month/"
                "ingestion_date=2026-05-17/pipeline_run_id=cloud-run/"
                "validation_results.json",
            )
        ]
        == b"[]\n"
    )


def test_artifact_store_for_route_selects_local_or_s3_store(tmp_path):
    local_store = artifact_store_for_route(
        cloud_route=False,
        data_root=tmp_path,
        bucket="mirror-bucket",
    )
    s3_store = artifact_store_for_route(
        cloud_route=True,
        bucket="cloud-bucket",
        s3_client=FakeS3ObjectClient(),
    )

    assert isinstance(local_store, LocalArtifactStore)
    assert local_store.storage_backend == "local"
    assert isinstance(s3_store, S3ArtifactStore)
    assert s3_store.storage_backend == "s3"


def test_artifact_reader_for_route_uses_s3_client_only_for_cloud_route():
    client = FakeS3ObjectClient()

    local_reader = artifact_reader_for_route(cloud_route=False, s3_client=client)
    cloud_reader = artifact_reader_for_route(cloud_route=True, s3_client=client)

    assert isinstance(local_reader, ArtifactReader)
    assert local_reader.s3_client is None
    assert cloud_reader.s3_client is client
