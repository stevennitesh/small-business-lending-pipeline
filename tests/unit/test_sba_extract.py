from __future__ import annotations

import hashlib
import json

import pytest
import requests

from pipelines.extract.sba_extract import (
    DEFAULT_SBA_PACKAGE_URL,
    extract_sba_foia,
    resolve_sba_resources,
)
from pipelines.storage.raw_artifacts import S3ArtifactStore, S3RawArtifactStore
from pipelines.utils.source_config_models import (
    SBA_RESOURCES_CONFIG_FILE,
    SBADiscoveryConfig,
    SBAResourcesConfig,
    load_sba_resources_config,
)
from pipelines.utils.source_resources import SourceIdentity
from tests.unit.config_test_helpers import config_path
from tests.unit.extract_test_helpers import (
    FakeDownloadSession as FakeSession,
    FakeS3ObjectClient,
    read_json_file,
    read_sba_manifest,
    sample_sba_package_metadata,
    sba_7a_fy2020_present_spec,
    sba_foia_data_dictionary_spec,
)


SBA_RESOURCES_CONFIG_PATH = config_path(SBA_RESOURCES_CONFIG_FILE)

def test_load_sba_resources_config_includes_discovery_settings():
    config = load_sba_resources_config(SBA_RESOURCES_CONFIG_PATH)

    assert config.dataset_name == "7a_504_foia"
    assert config.discovery.package_url == DEFAULT_SBA_PACKAGE_URL
    assert config.discovery.strategy == "sba_open_data_metadata"
    assert config.discovery.allow_dynamic_url_resolution is True
    assert config.discovery.cache_subdir == ".tmp/sba_resources"
    assert len(config.resources) == 7


def test_load_sba_resources_config_provides_resource_specs():
    specs = list(load_sba_resources_config(SBA_RESOURCES_CONFIG_PATH).resources)

    assert len(specs) == 7
    assert {spec.logical_name for spec in specs} == {
        "sba_foia_data_dictionary",
        "sba_7a_fy1991_fy1999",
        "sba_7a_fy2000_fy2009",
        "sba_7a_fy2010_fy2019",
        "sba_7a_fy2020_present",
        "sba_504_fy1991_fy2009",
        "sba_504_fy2010_present",
    }


def test_extract_sba_foia_uses_configured_package_url_and_cache_path(tmp_path):
    config = SBAResourcesConfig(
        dataset_name="7a_504_foia",
        discovery=SBADiscoveryConfig(
            strategy="sba_open_data_metadata",
            package_url="https://example.test/custom-package",
            allow_dynamic_url_resolution=True,
            cache_subdir=str(tmp_path / "metadata-cache"),
        ),
        resources=(sba_7a_fy2020_present_spec(),),
    )
    session = FakeSession(
        {
            "https://example.test/custom-package": {
                "result": sample_sba_package_metadata()
            },
            "https://example.test/7a_2020_present.csv": b"col\n1\n",
        }
    )

    summary = extract_sba_foia(
        config=config,
        session=session,
        data_root=tmp_path / "data",
        s3_bucket="unit-test-bucket",
        pipeline_run_id="run-123",
        extracted_at_utc="2026-05-06T12:00:00Z",
    )

    assert session.requested_urls[:2] == [
        "https://example.test/custom-package",
        "https://example.test/7a_2020_present.csv",
    ]
    cached_metadata = tmp_path / "metadata-cache" / "sba_package_metadata.json"
    assert cached_metadata.is_file()
    assert read_json_file(cached_metadata) == sample_sba_package_metadata()
    assert list(summary.results) == ["sba_7a_fy2020_present"]


def test_extract_sba_foia_requires_metadata_when_dynamic_resolution_disabled(tmp_path):
    config = SBAResourcesConfig(
        dataset_name="7a_504_foia",
        discovery=SBADiscoveryConfig(
            strategy="sba_open_data_metadata",
            package_url="https://example.test/custom-package",
            allow_dynamic_url_resolution=False,
            cache_subdir=str(tmp_path / "metadata-cache"),
        ),
        resources=(sba_7a_fy2020_present_spec(),),
    )

    with pytest.raises(ValueError, match="Dynamic SBA resource resolution is disabled"):
        extract_sba_foia(
            config=config,
            session=FakeSession({}),
            data_root=tmp_path,
            pipeline_run_id="run-123",
        )


def test_resolve_sba_resources_matches_expected_metadata():
    specs = list(load_sba_resources_config(SBA_RESOURCES_CONFIG_PATH).resources)
    resolved = resolve_sba_resources(specs, sample_sba_package_metadata())

    assert len(resolved) == 7
    assert resolved["sba_7a_fy2020_present"].url.endswith("7a_2020_present.csv")
    assert resolved["sba_504_fy2010_present"].file_format == "csv"
    assert resolved["sba_foia_data_dictionary"].file_format == "xlsx"


def test_extract_sba_foia_writes_partitioned_raw_files_and_manifests(tmp_path):
    specs = list(load_sba_resources_config(SBA_RESOURCES_CONFIG_PATH).resources)
    metadata = sample_sba_package_metadata()
    downloads = {
        resource["url"]: b"col_a,col_b\n1,2\n3,4\n"
        if resource["format"] == "csv"
        else b"fake-xlsx-content"
        for resource in metadata["resources"]
    }
    session = FakeSession(downloads)

    summary = extract_sba_foia(
        specs=specs,
        package_metadata=metadata,
        session=session,
        data_root=tmp_path,
        s3_bucket="unit-test-bucket",
        pipeline_run_id="run-123",
        extracted_at_utc="2026-05-06T12:00:00Z",
    )

    assert summary.warnings == []
    assert len(summary.results) == 7
    assert all(result.local_raw_path.is_file() for result in summary.results.values())
    assert all(path.is_file() for path in summary.manifest_paths.values())
    assert len(session.requested_urls) == 7

    csv_result = summary.results["sba_7a_fy2020_present"]
    assert csv_result.local_raw_path == tmp_path / (
        "raw/sba/7a_foia/source_period=fy2020_present/"
        "ingestion_date=2026-05-06/pipeline_run_id=run-123/"
        "7a_2020_present.csv"
    )
    assert csv_result.local_raw_path.read_bytes() == downloads[
        "https://example.test/7a_2020_present.csv"
    ]
    assert csv_result.manifest.row_count == 2
    assert len(csv_result.manifest.sha256_checksum) == 64

    manifest = read_sba_manifest(summary, "sba_7a_fy2020_present")
    assert manifest["resource_name"] == "sba_7a_fy2020_present"
    assert manifest["s3_raw_uri"].startswith("s3://unit-test-bucket/raw/sba/")
    assert manifest["validation_status"] == "passed"


def test_extract_sba_foia_profiles_chunked_csv_without_full_payload_hash(tmp_path):
    spec = sba_7a_fy2020_present_spec()
    metadata = sample_sba_package_metadata()
    chunks = [b"col_a,", b"col_b\n", b"1,2\n", b"3,4\n"]
    expected_payload = b"".join(chunks)
    session = FakeSession({"https://example.test/7a_2020_present.csv": chunks})

    summary = extract_sba_foia(
        specs=[spec],
        package_metadata=metadata,
        session=session,
        data_root=tmp_path,
        s3_bucket="unit-test-bucket",
        pipeline_run_id="run-123",
        extracted_at_utc="2026-05-06T12:00:00Z",
    )

    result = summary.results["sba_7a_fy2020_present"]
    assert result.local_raw_path.read_bytes() == expected_payload
    assert result.manifest.row_count == 2
    assert result.manifest.column_count == 2
    assert result.manifest.file_size_bytes == len(expected_payload)
    assert result.manifest.sha256_checksum == hashlib.sha256(
        expected_payload
    ).hexdigest()


def test_extract_sba_foia_uses_source_identity_for_manifests(tmp_path):
    spec = sba_7a_fy2020_present_spec()
    metadata = sample_sba_package_metadata()
    session = FakeSession(
        {"https://example.test/7a_2020_present.csv": b"col_a,col_b\n1,2\n"}
    )

    summary = extract_sba_foia(
        specs=[spec],
        source_identity=SourceIdentity(
            source_system="custom_sba",
            dataset_name="custom_7a_504",
        ),
        package_metadata=metadata,
        session=session,
        data_root=tmp_path,
        s3_bucket="unit-test-bucket",
        pipeline_run_id="run-123",
        extracted_at_utc="2026-05-06T12:00:00Z",
    )

    result = summary.results["sba_7a_fy2020_present"]
    assert result.local_raw_path == tmp_path / (
        "raw/custom_sba/7a_foia/source_period=fy2020_present/"
        "ingestion_date=2026-05-06/pipeline_run_id=run-123/"
        "7a_2020_present.csv"
    )
    manifest = read_sba_manifest(summary, "sba_7a_fy2020_present")
    assert manifest["source_system"] == "custom_sba"
    assert manifest["dataset_name"] == "custom_7a_504"
    assert manifest["s3_raw_uri"].startswith(
        "s3://unit-test-bucket/raw/custom_sba/7a_foia/"
    )


def test_extract_sba_foia_can_write_raw_artifacts_to_s3(tmp_path):
    spec = sba_7a_fy2020_present_spec()
    metadata = sample_sba_package_metadata()
    payload = b"col_a,col_b\n1,2\n"
    session = FakeSession({"https://example.test/7a_2020_present.csv": payload})
    s3_client = FakeS3ObjectClient()

    summary = extract_sba_foia(
        specs=[spec],
        package_metadata=metadata,
        session=session,
        data_root=tmp_path,
        s3_bucket="cloud-bucket",
        pipeline_run_id="cloud-run",
        extracted_at_utc="2026-05-06T12:00:00Z",
        raw_artifact_store=S3RawArtifactStore(
            bucket="cloud-bucket",
            s3_client=s3_client,
        ),
        manifest_artifact_store=S3ArtifactStore(
            bucket="cloud-bucket",
            s3_client=s3_client,
        ),
    )

    result = summary.results["sba_7a_fy2020_present"]
    assert result.local_raw_path is None
    assert result.manifest.storage_backend == "s3"
    assert result.manifest.raw_uri == result.manifest.s3_raw_uri
    manifest = read_sba_manifest(summary, "sba_7a_fy2020_present")
    assert manifest["storage_backend"] == "s3"
    assert manifest["raw_uri"].startswith("s3://cloud-bucket/raw/sba/7a_foia/")
    key = manifest["raw_uri"].removeprefix("s3://cloud-bucket/")
    assert s3_client.objects[("cloud-bucket", key)] == payload
    assert s3_client.body_types[("cloud-bucket", key)] != "bytes"
    manifest_location = summary.manifest_locations["sba_7a_fy2020_present"]
    assert manifest_location.artifact_uri.startswith(
        "s3://cloud-bucket/manifests/sba/7a_504_foia/"
    )
    assert json.loads(
        s3_client.objects[("cloud-bucket", manifest_location.artifact_key)]
    )["resource_name"] == "sba_7a_fy2020_present"


def test_data_dictionary_download_warns_without_blocking_csv_extract(tmp_path):
    csv_spec = sba_7a_fy2020_present_spec()
    dictionary_spec = sba_foia_data_dictionary_spec()
    metadata = {
        "resources": [
            {
                "name": "7a_504_FOIA Data Dictionary as of 260331.xlsx",
                "format": "xlsx",
                "url": "https://example.test/dictionary.xlsx",
            },
            {
                "name": "FOIA - 7(a) (FY2020-Present) asof 260331.csv",
                "format": "csv",
                "url": "https://example.test/7a_2020_present.csv",
            },
        ]
    }
    session = FakeSession(
        {
            "https://example.test/dictionary.xlsx": requests.ConnectionError(
                "unavailable"
            ),
            "https://example.test/7a_2020_present.csv": b"col\n1\n",
        }
    )

    summary = extract_sba_foia(
        specs=[csv_spec, dictionary_spec],
        package_metadata=metadata,
        session=session,
        data_root=tmp_path,
        s3_bucket="unit-test-bucket",
        pipeline_run_id="run-123",
        extracted_at_utc="2026-05-06T12:00:00Z",
    )

    assert list(summary.results) == ["sba_7a_fy2020_present"]
    assert summary.results["sba_7a_fy2020_present"].manifest.row_count == 1
    assert len(summary.warnings) == 1
    assert "data dictionary" in summary.warnings[0].lower()


def test_required_csv_download_failure_raises(tmp_path):
    specs = [sba_7a_fy2020_present_spec()]
    metadata = {
        "resources": [
            {
                "name": "FOIA - 7(a) (FY2020-Present) asof 260331.csv",
                "format": "csv",
                "url": "https://example.test/7a_2020_present.csv",
            }
        ]
    }
    session = FakeSession(
        {"https://example.test/7a_2020_present.csv": requests.Timeout("timeout")}
    )

    with pytest.raises(requests.RequestException):
        extract_sba_foia(
            specs=specs,
            package_metadata=metadata,
            session=session,
            data_root=tmp_path,
            s3_bucket="unit-test-bucket",
            package_url=DEFAULT_SBA_PACKAGE_URL,
            pipeline_run_id="run-123",
            extracted_at_utc="2026-05-06T12:00:00Z",
        )
