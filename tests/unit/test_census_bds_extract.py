from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from pipelines.extract.census_bds_extract import (
    CensusBDSConfig,
    build_census_bds_params,
    extract_census_bds,
    load_census_bds_config,
    validate_bds_response,
)


def _fixture_response() -> list[list[str]]:
    return [
        [
            "NAME",
            "YEAR",
            "ESTAB",
            "ESTABS_ENTRY",
            "ESTABS_ENTRY_RATE",
            "ESTABS_EXIT",
            "ESTABS_EXIT_RATE",
            "FIRM",
            "JOB_CREATION",
            "JOB_DESTRUCTION",
            "time",
            "state",
        ],
        [
            "Alabama",
            "2022",
            "97218",
            "8966",
            "9.260",
            "8190",
            "8.459",
            "70912",
            "226550",
            "177056",
            "2022",
            "01",
        ],
        [
            "Alabama",
            "2023",
            "98246",
            "9094",
            "9.306",
            "8044",
            "8.232",
            "71429",
            "223092",
            "179480",
            "2023",
            "01",
        ],
        [
            "Alaska",
            "2022",
            "18583",
            "1896",
            "10.250",
            "1633",
            "8.827",
            "14667",
            "36076",
            "27925",
            "2022",
            "02",
        ],
    ]


class FakeResponse:
    def __init__(self, payload: list[list[str]], status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> list[list[str]]:
        return self.payload


class FakeSession:
    def __init__(self, payload: list[list[str]]):
        self.payload = payload
        self.calls: list[dict] = []

    def get(self, url: str, params: dict[str, str], timeout: int):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(self.payload)


def test_load_census_bds_config_from_yaml():
    config = load_census_bds_config(Path("config/census_bds_variables.yml"))

    assert config.endpoint == "https://api.census.gov/data/timeseries/bds"
    assert config.geography == "state"
    assert config.start_year == 2010
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
        _fixture_response(),
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
    duplicate_response = _fixture_response() + [_fixture_response()[1]]

    with pytest.raises(ValueError, match="Duplicate Census BDS state-year rows"):
        validate_bds_response(
            duplicate_response,
            required_variables=("YEAR", "NAME", "state", "ESTAB"),
        )


def test_extract_census_bds_writes_raw_json_before_manifest(tmp_path):
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
    session = FakeSession(_fixture_response())

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
    assert json.loads(summary.result.local_raw_path.read_text(encoding="utf-8")) == (
        _fixture_response()
    )
    assert summary.result.manifest.row_count == 3
    assert summary.latest_available_year == 2023

    manifest = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
    assert manifest["resource_name"] == "bds_state_year"
    assert manifest["row_count"] == 3
    assert manifest["latest_available_year"] == 2023
    assert manifest["s3_raw_uri"].startswith("s3://unit-test-bucket/raw/census/bds/")
