from __future__ import annotations

from pipelines.storage.raw_artifacts import (
    LocalArtifactStore,
    S3ArtifactStore,
)


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
    assert s3_client.objects[
        (
            "cloud-bucket",
            "validation/bls/laus/laus_state_month/"
            "ingestion_date=2026-05-17/pipeline_run_id=cloud-run/"
            "validation_results.json",
        )
    ] == b"[]\n"


class FakeBody:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class FakeS3ObjectClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str):
        return {"Body": FakeBody(self.objects[(Bucket, Key)])}
