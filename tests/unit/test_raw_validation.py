from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from pipelines.utils.hashing import calculate_sha256, hash_schema
from pipelines.validation.raw_checks import (
    check_raw_manifest,
    check_validation_output_created,
)
from pipelines.validation.freshness_checks import check_latest_observation_not_future
from pipelines.validation.row_count_checks import check_row_count_captured
from pipelines.validation.schema_checks import (
    check_bls_laus_payload,
    check_census_bds_payload,
    check_sba_required_resources,
)
from pipelines.validation.validation_result import (
    ValidationFailedError,
    ValidationResult,
    assert_no_blocking_failures,
    write_validation_results,
)


def _manifest_for(raw_file: Path) -> dict:
    return {
        "pipeline_run_id": "run-123",
        "source_system": "census",
        "dataset_name": "bds",
        "resource_name": "bds_state_year",
        "source_url": "https://example.test/source",
        "extracted_at_utc": "2026-05-07T12:00:00Z",
        "ingestion_date": "2026-05-07",
        "local_raw_path": str(raw_file),
        "s3_raw_uri": "s3://bucket/raw/census/bds/file.json",
        "file_format": "json",
        "row_count": 2,
        "sha256_checksum": calculate_sha256(raw_file),
        "schema_hash": hash_schema(["YEAR", "state"]),
        "validation_status": "passed",
        "column_count": 2,
        "file_size_bytes": raw_file.stat().st_size,
    }


def test_validation_result_serializes_and_writes_json(tmp_path):
    result = ValidationResult(
        pipeline_run_id="run-123",
        validation_check_id="RAW_001",
        validation_scope="raw",
        source_system="census",
        source_dataset="bds",
        source_resource_name="bds_state_year",
        check_name="Raw file exists",
        check_type="completeness",
        severity="fail",
        status="passed",
        expected_value="file exists",
        observed_value="file exists",
        message="Raw file exists.",
        checked_at_utc="2026-05-07T12:00:00Z",
    )

    output_path = write_validation_results([result], tmp_path / "validation.json")
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload == [result.to_dict()]


def test_blocking_failures_raise_before_load():
    failed_result = ValidationResult(
        pipeline_run_id="run-123",
        validation_check_id="RAW_001",
        validation_scope="raw",
        source_system="sba",
        source_dataset="7a_504_foia",
        source_resource_name="sba_7a_fy2020_present",
        check_name="Raw file exists",
        check_type="completeness",
        severity="fail",
        status="failed",
        expected_value="file exists",
        observed_value="missing",
        message="Raw file is missing.",
        checked_at_utc="2026-05-07T12:00:00Z",
    )

    with pytest.raises(ValidationFailedError, match="RAW_001"):
        assert_no_blocking_failures([failed_result])


def test_raw_manifest_checks_pass_for_complete_manifest(tmp_path):
    raw_file = tmp_path / "bds_state_year.json"
    raw_file.write_text('[["YEAR","state"],["2023","01"],["2023","02"]]\n')
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest_for(raw_file)), encoding="utf-8")

    results = check_raw_manifest(manifest_path)

    assert {result.validation_check_id for result in results} == {
        "RAW_001",
        "RAW_002",
        "RAW_003",
        "RAW_004",
        "RAW_005",
        "RAW_006",
        "RAW_007",
        "RAW_008",
    }
    assert all(result.status == "passed" for result in results)


def test_raw_manifest_checks_fail_for_missing_file(tmp_path):
    missing_file = tmp_path / "missing.json"
    placeholder_file = tmp_path / "placeholder.json"
    placeholder_file.write_text("[]\n", encoding="utf-8")
    manifest = _manifest_for(placeholder_file)
    manifest["local_raw_path"] = str(missing_file)
    manifest["sha256_checksum"] = "0" * 64
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    results = check_raw_manifest(manifest_path)
    file_exists = next(result for result in results if result.validation_check_id == "RAW_001")

    assert file_exists.status == "failed"
    assert file_exists.severity == "fail"


def test_raw_manifest_checks_return_failure_for_missing_metadata(tmp_path):
    raw_file = tmp_path / "bds_state_year.json"
    raw_file.write_text('[["YEAR","state"],["2023","01"]]\n', encoding="utf-8")
    manifest = _manifest_for(raw_file)
    manifest.pop("schema_hash")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    results = check_raw_manifest(manifest_path)
    metadata = next(result for result in results if result.validation_check_id == "RAW_005")
    schema_hash = next(result for result in results if result.validation_check_id == "RAW_007")

    assert metadata.status == "failed"
    assert schema_hash.status == "warning"


def test_validation_output_created_check(tmp_path):
    output_path = tmp_path / "validation_results.json"

    missing_result = check_validation_output_created(
        output_path,
        pipeline_run_id="run-123",
        source_system="census",
        source_dataset="bds",
        source_resource_name="bds_state_year",
    )
    output_path.write_text("[]\n", encoding="utf-8")
    existing_result = check_validation_output_created(
        output_path,
        pipeline_run_id="run-123",
        source_system="census",
        source_dataset="bds",
        source_resource_name="bds_state_year",
    )

    assert missing_result.status == "failed"
    assert existing_result.status == "passed"


def test_row_count_and_freshness_helpers_support_warnings():
    row_count_result = check_row_count_captured(
        row_count=10,
        pipeline_run_id="run-123",
        source_system="bls",
        source_dataset="laus",
        source_resource_name="laus_state_month",
    )
    future_result = check_latest_observation_not_future(
        latest_observation_date=date(2026, 6, 1),
        as_of_date=date(2026, 5, 7),
        pipeline_run_id="run-123",
        source_system="bls",
        source_dataset="laus",
        source_resource_name="laus_state_month",
    )

    assert row_count_result.status == "passed"
    assert future_result.severity == "warning"
    assert future_result.status == "warning"


def test_sba_required_resources_check_reports_missing_resource(tmp_path):
    raw_file = tmp_path / "sba.csv"
    raw_file.write_text("a,b\n1,2\n", encoding="utf-8")
    manifest = _manifest_for(raw_file)
    manifest.update(
        {
            "source_system": "sba",
            "dataset_name": "7a_504_foia",
            "resource_name": "sba_7a_fy2020_present",
        }
    )

    results = check_sba_required_resources(
        [manifest],
        required_resource_names=[
            "sba_7a_fy2020_present",
            "sba_504_fy2010_present",
        ],
    )

    assert [result.validation_check_id for result in results] == [
        "SBA_RAW_001",
        "SBA_RAW_002",
    ]
    assert results[0].status == "failed"
    assert "sba_504_fy2010_present" in str(results[0].observed_value)


def test_census_payload_check_requires_variables_and_state_coverage():
    payload = [
        ["YEAR", "NAME", "state", "ESTAB"],
        ["2023", "Alabama", "01", "98246"],
        ["2023", "Alaska", "02", "18870"],
    ]

    results = check_census_bds_payload(
        payload,
        required_variables=("YEAR", "NAME", "state", "ESTAB"),
        expected_state_count=2,
        pipeline_run_id="run-123",
    )

    assert all(result.status == "passed" for result in results)


def test_bls_payload_check_requires_expected_series_and_valid_months():
    payload = {
        "normalized_rows": [
            {
                "series_id": "LASST010000000000003",
                "observed_month": "2023-01-01",
                "period": "M01",
                "value": 2.6,
            },
            {
                "series_id": "LASST020000000000003",
                "observed_month": "2023-02-01",
                "period": "M02",
                "value": 3.8,
            },
        ]
    }

    results = check_bls_laus_payload(
        payload,
        expected_series_ids=(
            "LASST010000000000003",
            "LASST020000000000003",
        ),
        pipeline_run_id="run-123",
    )

    assert all(result.status == "passed" for result in results)


def test_bls_payload_check_honors_configured_period_and_value_bounds():
    payload = {
        "normalized_rows": [
            {
                "series_id": "LASST010000000000003",
                "observed_month": "2023-01-01",
                "period": "M13",
                "value": 101.0,
            },
        ]
    }

    results = check_bls_laus_payload(
        payload,
        expected_series_ids=("LASST010000000000003",),
        pipeline_run_id="run-123",
        required_period_pattern=r"^M(0[1-9]|1[0-2])$",
        unemployment_rate_min=0,
        unemployment_rate_max=100,
    )

    failed_ids = {
        result.validation_check_id
        for result in results
        if result.status == "failed"
    }
    assert {"BLS_RAW_002", "BLS_RAW_004"} <= failed_ids
