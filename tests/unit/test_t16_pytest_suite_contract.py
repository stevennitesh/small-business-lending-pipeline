from __future__ import annotations

import csv
import json
import tomllib
from pathlib import Path

from pipelines.extract.census_bds_extract import validate_bds_response
from pipelines.validation.schema_checks import (
    check_bls_laus_payload,
    check_census_bds_payload,
    check_sba_required_resources,
)


FIXTURE_DIR = Path("tests/fixtures")
SBA_SAMPLE = FIXTURE_DIR / "sba_foia_sample.csv"
CENSUS_SAMPLE = FIXTURE_DIR / "census_bds_sample.json"
BLS_SAMPLE = FIXTURE_DIR / "bls_laus_sample.json"


def test_source_fixtures_are_committed_and_small():
    for fixture_path in (SBA_SAMPLE, CENSUS_SAMPLE, BLS_SAMPLE):
        assert fixture_path.is_file()
        assert fixture_path.stat().st_size < 5_000


def test_optional_live_and_cloud_markers_are_declared():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    markers = pyproject["tool"]["pytest"]["ini_options"]["markers"]

    assert any(marker.startswith("live_api:") for marker in markers)
    assert any(marker.startswith("cloud:") for marker in markers)


def test_source_validation_helpers_accept_committed_fixtures():
    with SBA_SAMPLE.open("r", encoding="utf-8", newline="") as file:
        sba_rows = list(csv.DictReader(file))

    sba_results = check_sba_required_resources(
        [
            {
                "pipeline_run_id": "run-fixture",
                "local_raw_path": str(SBA_SAMPLE),
                "resource_name": "sba_7a_fy2020_present",
            }
        ],
        required_resource_names=["sba_7a_fy2020_present"],
    )
    assert len(sba_rows) == 2
    assert all(result.status == "passed" for result in sba_results)

    census_payload = json.loads(CENSUS_SAMPLE.read_text(encoding="utf-8"))
    census_summary = validate_bds_response(
        census_payload,
        required_variables=("YEAR", "NAME", "state", "ESTAB"),
    )
    census_results = check_census_bds_payload(
        census_payload,
        required_variables=("YEAR", "NAME", "state", "ESTAB"),
        expected_state_count=2,
        pipeline_run_id="run-fixture",
    )
    assert census_summary.row_count == 2
    assert all(result.status == "passed" for result in census_results)

    bls_payload = json.loads(BLS_SAMPLE.read_text(encoding="utf-8"))
    bls_results = check_bls_laus_payload(
        bls_payload,
        expected_series_ids=(
            "LASST010000000000003",
            "LASST020000000000003",
        ),
        pipeline_run_id="run-fixture",
    )
    assert len(bls_payload["normalized_rows"]) == 2
    assert all(result.status == "passed" for result in bls_results)
