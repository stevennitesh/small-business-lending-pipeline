from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import requests

from pipelines.extract.bls_laus_extract import (
    BLSLAUSConfig,
    BLSSeriesConfig,
    build_bls_payload,
    chunk_series,
    extract_bls_laus,
    load_bls_laus_config,
    normalize_bls_response,
    parse_monthly_period,
)


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


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, payloads: list[dict]):
        self.payloads = payloads
        self.calls: list[dict] = []

    def post(self, url: str, json: dict[str, object], timeout: int):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(self.payloads.pop(0))


def test_load_bls_laus_config_from_yaml():
    config = load_bls_laus_config(Path("config/bls_laus_state_series.yml"))

    assert config.endpoint == "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    assert config.measure_name == "unemployment_rate"
    assert len(config.series) == 51
    assert config.series[0].series_id == "LASST010000000000003"


def test_chunk_series_splits_large_requests():
    chunks = list(chunk_series(tuple(range(51)), chunk_size=25))

    assert [len(chunk) for chunk in chunks] == [25, 25, 1]


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


def test_parse_monthly_period_excludes_annual_periods():
    assert parse_monthly_period("2023", "M01") == date(2023, 1, 1)
    assert parse_monthly_period("2023", "M12") == date(2023, 12, 1)
    assert parse_monthly_period("2023", "M13") is None


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


def test_extract_bls_laus_writes_raw_json_and_manifest(tmp_path):
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
    raw_payload = json.loads(summary.result.local_raw_path.read_text(encoding="utf-8"))
    assert raw_payload["normalized_rows"][0]["observed_month"] == "2023-02-01"
    assert raw_payload["responses"][0]["status"] == "REQUEST_SUCCEEDED"
    assert summary.result.manifest.row_count == 3
    assert summary.latest_observed_month == "2023-02-01"

    manifest = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
    assert manifest["resource_name"] == "laus_state_month"
    assert manifest["row_count"] == 3
    assert manifest["series_count"] == 2
    assert manifest["latest_observed_month"] == "2023-02-01"
    assert manifest["s3_raw_uri"].startswith("s3://unit-test-bucket/raw/bls/laus/")
