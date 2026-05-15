from __future__ import annotations

from pipelines.storage.raw_artifacts import LocalRawArtifactStore, S3RawArtifactStore


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


class FakeBody:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class FakeS3ObjectClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str):
        return {"Body": FakeBody(self.objects[(Bucket, Key)])}
