from __future__ import annotations

import json

import pytest

from pipelines.extract.census_bds_extract import (
    build_census_bds_params,
    extract_census_bds,
    validate_bds_response,
)
from pipelines.storage.raw_artifacts import S3ArtifactStore, S3RawArtifactStore
from pipelines.utils.source_config_models import (
    CENSUS_BDS_CONFIG_FILE,
    CensusBDSConfig,
    load_census_bds_config,
)
from pipelines.utils.source_resources import SourceIdentity
from tests.unit.config_test_helpers import config_path
from tests.unit.extract_test_helpers import (
    FakeGetSession as FakeSession,
    FakeS3ObjectClient,
    census_bds_fixture_response,
    read_json_file,
    read_summary_manifest,
)


CENSUS_BDS_CONFIG_PATH = config_path(CENSUS_BDS_CONFIG_FILE)

def test_load_census_bds_config_from_yaml():
    config = load_census_bds_config(CENSUS_BDS_CONFIG_PATH)

    assert config.endpoint == "https://api.census.gov/data/timeseries/bds"
    assert config.geography == "state"
    assert config.start_year == 1990
    assert "YEAR" in config.required_variables
    assert "JOB_DESTRUCTION" in config.required_variables


def test_build_census_bds_params_for_year_range():
    config = CensusBDSConfig(
        endpoint="https://api.census.gov/data/timeseries/bds",
        geography="state",
        start_year=2020,
        required_variables=("YEAR", "NAME", "state", "ESTAB"),
    )

    params = build_census_bds_params(config, start_year=2021, end_year=2023)

    assert params == {
        "get": "YEAR,NAME,ESTAB",
        "for": "state:*",
        "time": "from 2021 to 2023",
    }


def test_validate_bds_response_requires_header_and_data_rows():
    summary = validate_bds_response(
        census_bds_fixture_response(),
        required_variables=("YEAR", "NAME", "state", "ESTAB"),
    )

    assert summary.row_count == 3
    assert summary.latest_available_year == 2023
    assert summary.header[:2] == ["NAME", "YEAR"]


def test_validate_bds_response_rejects_missing_required_variables():
    with pytest.raises(ValueError, match="Missing required Census BDS variables"):
        validate_bds_response(
            [["NAME", "YEAR"], ["Alabama", "2023"]],
            required_variables=("YEAR", "NAME", "state"),
        )


def test_validate_bds_response_rejects_duplicate_state_year_grain():
    duplicate_response = (
        census_bds_fixture_response()
        + [census_bds_fixture_response()[1]]
    )

    with pytest.raises(ValueError, match="Duplicate Census BDS state-year rows"):
        validate_bds_response(
            duplicate_response,
            required_variables=("YEAR", "NAME", "state", "ESTAB"),
        )


def test_extract_census_bds_writes_raw_json_before_manifest(tmp_path, monkeypatch):
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    config = CensusBDSConfig(
        endpoint="https://api.census.gov/data/timeseries/bds",
        geography="state",
        start_year=2020,
        required_variables=(
            "YEAR",
            "NAME",
            "state",
            "ESTAB",
            "ESTABS_ENTRY",
            "ESTABS_ENTRY_RATE",
            "ESTABS_EXIT",
            "ESTABS_EXIT_RATE",
            "FIRM",
            "JOB_CREATION",
            "JOB_DESTRUCTION",
        ),
    )
    session = FakeSession(census_bds_fixture_response())

    summary = extract_census_bds(
        config=config,
        session=session,
        data_root=tmp_path,
        s3_bucket="unit-test-bucket",
        pipeline_run_id="run-123",
        extracted_at_utc="2026-05-07T12:00:00Z",
        start_year=2022,
        end_year=2023,
    )

    assert session.calls == [
        {
            "url": "https://api.census.gov/data/timeseries/bds",
            "params": {
                "get": (
                    "YEAR,NAME,ESTAB,ESTABS_ENTRY,ESTABS_ENTRY_RATE,"
                    "ESTABS_EXIT,ESTABS_EXIT_RATE,FIRM,JOB_CREATION,"
                    "JOB_DESTRUCTION"
                ),
                "for": "state:*",
                "time": "from 2022 to 2023",
            },
            "timeout": 120,
        }
    ]
    assert summary.result.local_raw_path == tmp_path / (
        "raw/census/bds/grain=state_year/ingestion_date=2026-05-07/"
        "pipeline_run_id=run-123/bds_state_year_2022_2023.json"
    )
    assert read_json_file(summary.result.local_raw_path) == census_bds_fixture_response()
    assert summary.result.manifest.row_count == 3
    assert summary.latest_available_year == 2023

    manifest = read_summary_manifest(summary)
    assert manifest["resource_name"] == "bds_state_year"
    assert manifest["row_count"] == 3
    assert manifest["latest_available_year"] == 2023
    assert manifest["s3_raw_uri"].startswith("s3://unit-test-bucket/raw/census/bds/")


def test_extract_census_bds_uses_passed_source_identity(tmp_path, monkeypatch):
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    config = CensusBDSConfig(
        endpoint="https://api.census.gov/data/timeseries/bds",
        geography="state",
        start_year=2020,
        required_variables=("YEAR", "NAME", "state", "ESTAB"),
    )
    session = FakeSession(census_bds_fixture_response())

    summary = extract_census_bds(
        config=config,
        source_identity=SourceIdentity(
            source_system="custom_census",
            dataset_name="custom_bds",
        ),
        session=session,
        data_root=tmp_path,
        s3_bucket="unit-test-bucket",
        pipeline_run_id="run-123",
        extracted_at_utc="2026-05-07T12:00:00Z",
        start_year=2022,
        end_year=2023,
    )

    assert summary.result.local_raw_path == tmp_path / (
        "raw/custom_census/custom_bds/grain=state_year/"
        "ingestion_date=2026-05-07/pipeline_run_id=run-123/"
        "bds_state_year_2022_2023.json"
    )
    manifest = read_summary_manifest(summary)
    assert manifest["source_system"] == "custom_census"
    assert manifest["dataset_name"] == "custom_bds"
    assert manifest["s3_raw_uri"].startswith(
        "s3://unit-test-bucket/raw/custom_census/custom_bds/"
    )


def test_extract_census_bds_can_write_raw_artifact_to_s3(tmp_path, monkeypatch):
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    config = CensusBDSConfig(
        endpoint="https://api.census.gov/data/timeseries/bds",
        geography="state",
        start_year=2020,
        required_variables=("YEAR", "NAME", "state", "ESTAB"),
    )
    session = FakeSession(census_bds_fixture_response())
    s3_client = FakeS3ObjectClient()

    summary = extract_census_bds(
        config=config,
        session=session,
        data_root=tmp_path,
        s3_bucket="cloud-bucket",
        pipeline_run_id="cloud-run",
        extracted_at_utc="2026-05-07T12:00:00Z",
        start_year=2022,
        end_year=2023,
        raw_artifact_store=S3RawArtifactStore(
            bucket="cloud-bucket",
            s3_client=s3_client,
        ),
        manifest_artifact_store=S3ArtifactStore(
            bucket="cloud-bucket",
            s3_client=s3_client,
        ),
    )

    assert summary.result.local_raw_path is None
    assert summary.result.manifest.storage_backend == "s3"
    manifest = read_summary_manifest(summary)
    assert manifest["storage_backend"] == "s3"
    assert manifest["raw_uri"] == manifest["s3_raw_uri"]
    key = manifest["raw_uri"].removeprefix("s3://cloud-bucket/")
    assert json.loads(s3_client.objects[("cloud-bucket", key)]) == (
        census_bds_fixture_response()
    )
    assert summary.manifest_location is not None
    assert summary.manifest_location.artifact_uri.startswith(
        "s3://cloud-bucket/manifests/census/bds/"
    )
    assert json.loads(
        s3_client.objects[
            ("cloud-bucket", summary.manifest_location.artifact_key)
        ]
    )["latest_available_year"] == 2023
