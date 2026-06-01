from __future__ import annotations

import json
from datetime import date

import pytest

from pipelines.extract.bls_laus_extract import (
    PUBLIC_YEAR_WINDOW_SIZE,
    REGISTERED_YEAR_WINDOW_SIZE,
    build_bls_payload,
    chunk_series,
    chunk_year_range,
    extract_bls_laus,
    fetch_bls_laus_responses,
    normalize_bls_response,
    resolve_bls_year_window_size,
)
from pipelines.extract.bls_laus_periods import parse_monthly_period
from pipelines.storage.raw_artifacts import S3ArtifactStore, S3RawArtifactStore
from pipelines.utils.source_config_models import (
    BLS_LAUS_CONFIG_FILE,
    BLSLAUSConfig,
    BLSSeriesConfig,
    load_bls_laus_config,
)
from pipelines.utils.source_resources import SourceIdentity
from tests.unit.config_test_helpers import config_path
from tests.unit.extract_test_helpers import (
    FakePostSession as FakeSession,
    FakeS3ObjectClient,
    read_json_file,
    read_summary_manifest,
)


BLS_LAUS_CONFIG_PATH = config_path(BLS_LAUS_CONFIG_FILE)


def _series_configs() -> tuple[BLSSeriesConfig, ...]:
    return (
        BLSSeriesConfig(
            state_fips="01",
            state_abbr="AL",
            state_name="Alabama",
            series_id="LASST010000000000003",
        ),
        BLSSeriesConfig(
            state_fips="02",
            state_abbr="AK",
            state_name="Alaska",
            series_id="LASST020000000000003",
        ),
    )


def _fixture_response() -> dict:
    return {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": "LASST010000000000003",
                    "data": [
                        {
                            "year": "2023",
                            "period": "M02",
                            "periodName": "February",
                            "value": "2.7",
                            "footnotes": [{}],
                        },
                        {
                            "year": "2023",
                            "period": "M01",
                            "periodName": "January",
                            "value": "2.6",
                            "footnotes": [{"code": "P", "text": "Preliminary"}],
                        },
                        {
                            "year": "2023",
                            "period": "M13",
                            "periodName": "Annual",
                            "value": "2.9",
                            "footnotes": [{}],
                        },
                        {
                            "year": "2024",
                            "period": "M01",
                            "periodName": "January",
                            "value": "-",
                            "footnotes": [{}],
                        },
                    ],
                },
                {
                    "seriesID": "LASST020000000000003",
                    "data": [
                        {
                            "year": "2023",
                            "period": "M01",
                            "periodName": "January",
                            "value": "3.8",
                            "footnotes": [{}],
                        }
                    ],
                },
            ]
        },
    }


def test_load_bls_laus_config_from_yaml():
    config = load_bls_laus_config(BLS_LAUS_CONFIG_PATH)

    assert config.endpoint == "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    assert config.measure_name == "unemployment_rate"
    assert len(config.series) == 51
    assert config.series[0].series_id == "LASST010000000000003"


def test_chunk_series_splits_large_requests():
    chunks = list(chunk_series(tuple(range(51)), chunk_size=25))

    assert [len(chunk) for chunk in chunks] == [25, 25, 1]


def test_chunk_year_range_splits_long_bls_windows():
    assert list(chunk_year_range(1990, 2026, window_size=20)) == [
        (1990, 2009),
        (2010, 2026),
    ]


def test_build_bls_payload_uses_year_range_and_optional_key():
    payload = build_bls_payload(
        ("LASST010000000000003", "LASST020000000000003"),
        start_year=2022,
        end_year=2023,
        api_key="secret-key",
    )

    assert payload == {
        "seriesid": ["LASST010000000000003", "LASST020000000000003"],
        "startyear": "2022",
        "endyear": "2023",
        "registrationkey": "secret-key",
    }


def test_resolve_bls_year_window_size_uses_override_or_api_access():
    assert resolve_bls_year_window_size(api_key=None, year_window_size=7) == 7
    assert resolve_bls_year_window_size(api_key="secret-key") == (
        REGISTERED_YEAR_WINDOW_SIZE
    )
    assert resolve_bls_year_window_size(api_key=None) == PUBLIC_YEAR_WINDOW_SIZE


def test_resolve_bls_year_window_size_rejects_non_positive_override():
    with pytest.raises(ValueError, match="year_window_size must be at least 1"):
        resolve_bls_year_window_size(api_key=None, year_window_size=0)


def test_parse_monthly_period_excludes_annual_periods():
    assert parse_monthly_period("2023", "M01") == date(2023, 1, 1)
    assert parse_monthly_period("2023", "M12") == date(2023, 12, 1)
    assert parse_monthly_period("2023", "M13") is None


def test_parse_monthly_period_returns_none_for_invalid_year():
    assert parse_monthly_period("not-a-year", "M01") is None


def test_fetch_bls_laus_responses_chunks_series_and_year_ranges():
    config = BLSLAUSConfig(
        endpoint="https://api.bls.gov/publicAPI/v2/timeseries/data/",
        measure_name="unemployment_rate",
        seasonal_adjustment="seasonally_adjusted",
        series=_series_configs(),
    )
    session = FakeSession(
        [
            {"status": "REQUEST_SUCCEEDED", "Results": {"series": []}},
            {"status": "REQUEST_SUCCEEDED", "Results": {"series": []}},
            {"status": "REQUEST_SUCCEEDED", "Results": {"series": []}},
            {"status": "REQUEST_SUCCEEDED", "Results": {"series": []}},
        ]
    )

    fetch_bls_laus_responses(
        config,
        session=session,
        start_year=1990,
        end_year=2026,
        api_key="secret-key",
        chunk_size=1,
    )

    assert [
        (
            call["json"]["seriesid"],
            call["json"]["startyear"],
            call["json"]["endyear"],
        )
        for call in session.calls
    ] == [
        (["LASST010000000000003"], "1990", "2009"),
        (["LASST020000000000003"], "1990", "2009"),
        (["LASST010000000000003"], "2010", "2026"),
        (["LASST020000000000003"], "2010", "2026"),
    ]


def test_normalize_bls_response_excludes_annual_and_parses_values():
    rows = normalize_bls_response(
        [_fixture_response()],
        series_by_id={series.series_id: series for series in _series_configs()},
    )

    assert rows == [
        {
            "series_id": "LASST010000000000003",
            "state_fips": "01",
            "state_abbr": "AL",
            "state_name": "Alabama",
            "year": 2023,
            "period": "M02",
            "observed_month": "2023-02-01",
            "value": 2.7,
            "footnotes": [],
        },
        {
            "series_id": "LASST010000000000003",
            "state_fips": "01",
            "state_abbr": "AL",
            "state_name": "Alabama",
            "year": 2023,
            "period": "M01",
            "observed_month": "2023-01-01",
            "value": 2.6,
            "footnotes": [{"code": "P", "text": "Preliminary"}],
        },
        {
            "series_id": "LASST020000000000003",
            "state_fips": "02",
            "state_abbr": "AK",
            "state_name": "Alaska",
            "year": 2023,
            "period": "M01",
            "observed_month": "2023-01-01",
            "value": 3.8,
            "footnotes": [],
        },
    ]


def test_extract_bls_laus_writes_raw_json_and_manifest(tmp_path, monkeypatch):
    monkeypatch.delenv("BLS_API_KEY", raising=False)
    config = BLSLAUSConfig(
        endpoint="https://api.bls.gov/publicAPI/v2/timeseries/data/",
        measure_name="unemployment_rate",
        seasonal_adjustment="seasonally_adjusted",
        series=_series_configs(),
    )
    session = FakeSession([_fixture_response()])

    summary = extract_bls_laus(
        config=config,
        session=session,
        data_root=tmp_path,
        s3_bucket="unit-test-bucket",
        pipeline_run_id="run-123",
        extracted_at_utc="2026-05-07T12:00:00Z",
        start_year=2023,
        end_year=2023,
        chunk_size=25,
    )

    assert session.calls == [
        {
            "url": "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            "json": {
                "seriesid": [
                    "LASST010000000000003",
                    "LASST020000000000003",
                ],
                "startyear": "2023",
                "endyear": "2023",
            },
            "timeout": 120,
        }
    ]
    assert summary.result.local_raw_path == tmp_path / (
        "raw/bls/laus/grain=state_month/ingestion_date=2026-05-07/"
        "pipeline_run_id=run-123/bls_laus_state_month_2023_2023.json"
    )
    raw_payload = read_json_file(summary.result.local_raw_path)
    assert raw_payload["normalized_rows"][0]["observed_month"] == "2023-02-01"
    assert raw_payload["responses"][0]["status"] == "REQUEST_SUCCEEDED"
    assert summary.result.manifest.row_count == 3
    assert summary.latest_observed_month == "2023-02-01"

    manifest = read_summary_manifest(summary)
    assert manifest["resource_name"] == "laus_state_month"
    assert manifest["row_count"] == 3
    assert manifest["series_count"] == 2
    assert manifest["latest_observed_month"] == "2023-02-01"
    assert manifest["s3_raw_uri"].startswith("s3://unit-test-bucket/raw/bls/laus/")


def test_extract_bls_laus_uses_passed_source_identity(tmp_path, monkeypatch):
    monkeypatch.delenv("BLS_API_KEY", raising=False)
    config = BLSLAUSConfig(
        endpoint="https://api.bls.gov/publicAPI/v2/timeseries/data/",
        measure_name="unemployment_rate",
        seasonal_adjustment="seasonally_adjusted",
        series=_series_configs(),
    )
    session = FakeSession([_fixture_response()])

    summary = extract_bls_laus(
        config=config,
        source_identity=SourceIdentity(
            source_system="custom_bls",
            dataset_name="custom_laus",
        ),
        session=session,
        data_root=tmp_path,
        s3_bucket="unit-test-bucket",
        pipeline_run_id="run-123",
        extracted_at_utc="2026-05-07T12:00:00Z",
        start_year=2023,
        end_year=2023,
    )

    assert summary.result.local_raw_path == tmp_path / (
        "raw/custom_bls/custom_laus/grain=state_month/"
        "ingestion_date=2026-05-07/pipeline_run_id=run-123/"
        "bls_laus_state_month_2023_2023.json"
    )
    manifest = read_summary_manifest(summary)
    assert manifest["source_system"] == "custom_bls"
    assert manifest["dataset_name"] == "custom_laus"
    assert manifest["s3_raw_uri"].startswith(
        "s3://unit-test-bucket/raw/custom_bls/custom_laus/"
    )


def test_extract_bls_laus_can_write_raw_artifact_to_s3(tmp_path, monkeypatch):
    monkeypatch.delenv("BLS_API_KEY", raising=False)
    config = BLSLAUSConfig(
        endpoint="https://api.bls.gov/publicAPI/v2/timeseries/data/",
        measure_name="unemployment_rate",
        seasonal_adjustment="seasonally_adjusted",
        series=_series_configs(),
    )
    session = FakeSession([_fixture_response()])
    s3_client = FakeS3ObjectClient()

    summary = extract_bls_laus(
        config=config,
        session=session,
        data_root=tmp_path,
        s3_bucket="cloud-bucket",
        pipeline_run_id="cloud-run",
        extracted_at_utc="2026-05-07T12:00:00Z",
        start_year=2023,
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
    raw_payload = json.loads(s3_client.objects[("cloud-bucket", key)])
    assert raw_payload["normalized_rows"][0]["observed_month"] == "2023-02-01"
    assert summary.manifest_location is not None
    assert summary.manifest_location.artifact_uri.startswith(
        "s3://cloud-bucket/manifests/bls/laus/"
    )
    assert json.loads(
        s3_client.objects[
            ("cloud-bucket", summary.manifest_location.artifact_key)
        ]
    )["latest_observed_month"] == "2023-02-01"
