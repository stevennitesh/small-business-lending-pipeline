from __future__ import annotations

from pipelines.storage.raw_artifacts import (
    LocalRawArtifactStore,
    RawArtifactReader,
    S3RawArtifactStore,
    raw_artifact_reader_for_route,
    raw_artifact_store_for_route,
)
from tests.unit.artifact_store_test_helpers import FakeS3ObjectClient


def test_local_raw_artifact_store_writes_and_reads_local_payload(tmp_path):
    store = LocalRawArtifactStore(data_root=tmp_path / "data", s3_bucket="local-live")
    location = store.location(
        source_system="sba",
        dataset_name="7a_foia",
        resource_name="sba_7a_source_period=fy2020_present",
        ingestion_date="2026-05-15",
        pipeline_run_id="local-run",
        filename="raw.csv",
    )

    store.write_bytes(location, b"a,b\n1,2\n")

    assert location.storage_backend == "local"
    assert location.local_path is not None
    assert location.raw_uri == str(location.local_path)
    assert location.s3_uri == (
        "s3://local-live/raw/sba/7a_foia/"
        "sba_7a_source_period=fy2020_present/"
        "ingestion_date=2026-05-15/pipeline_run_id=local-run/raw.csv"
    )
    assert store.read_bytes(location) == b"a,b\n1,2\n"
    assert location.manifest_fields() == {
        "storage_backend": "local",
        "raw_uri": str(location.local_path),
        "local_raw_path": str(location.local_path),
        "s3_raw_uri": location.s3_uri,
    }


def test_s3_raw_artifact_store_writes_to_s3_payload():
    client = FakeS3ObjectClient()
    store = S3RawArtifactStore(bucket="portfolio-raw", s3_client=client)
    location = store.location(
        source_system="census",
        dataset_name="bds",
        resource_name="bds_state_year",
        ingestion_date="2026-05-15",
        pipeline_run_id="cloud-run",
        filename="bds_state_year.json",
    )

    store.write_bytes(location, b'[{"state": "01"}]')

    assert location.storage_backend == "s3"
    assert location.local_path is None
    assert location.s3_key == (
        "raw/census/bds/bds_state_year/"
        "ingestion_date=2026-05-15/pipeline_run_id=cloud-run/bds_state_year.json"
    )
    assert location.raw_uri == (
        "s3://portfolio-raw/raw/census/bds/bds_state_year/"
        "ingestion_date=2026-05-15/pipeline_run_id=cloud-run/bds_state_year.json"
    )
    assert client.objects[(store.bucket, location.s3_key)] == b'[{"state": "01"}]'
    assert store.read_bytes(location) == b'[{"state": "01"}]'
    assert location.manifest_fields() == {
        "storage_backend": "s3",
        "raw_uri": location.raw_uri,
        "local_raw_path": None,
        "s3_raw_uri": location.raw_uri,
    }


def test_raw_artifact_store_for_route_selects_local_or_s3_store(tmp_path):
    local_store = raw_artifact_store_for_route(
        cloud_route=False,
        data_root=tmp_path / "data",
        bucket="mirror-bucket",
    )
    s3_store = raw_artifact_store_for_route(
        cloud_route=True,
        bucket="cloud-bucket",
        s3_client=FakeS3ObjectClient(),
    )

    assert isinstance(local_store, LocalRawArtifactStore)
    assert local_store.storage_backend == "local"
    assert isinstance(s3_store, S3RawArtifactStore)
    assert s3_store.storage_backend == "s3"


def test_raw_artifact_reader_for_route_uses_s3_client_only_for_cloud_route():
    client = FakeS3ObjectClient()

    local_reader = raw_artifact_reader_for_route(cloud_route=False, s3_client=client)
    cloud_reader = raw_artifact_reader_for_route(cloud_route=True, s3_client=client)

    assert isinstance(local_reader, RawArtifactReader)
    assert local_reader.s3_client is None
    assert cloud_reader.s3_client is client
