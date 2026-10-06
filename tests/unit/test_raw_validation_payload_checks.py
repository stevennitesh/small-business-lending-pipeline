from __future__ import annotations

from pipelines.utils.source_resources import SourceIdentity
from pipelines.validation.bls_laus_payload_checks import check_bls_laus_payload
from pipelines.validation.census_bds_payload_checks import check_census_bds_payload
from pipelines.validation.raw_validation_check_catalog import (
    BDS_REQUIRED_VARIABLES,
    BDS_ROW_GRAIN,
    BDS_STATE_COVERAGE,
    BLS_EXPECTED_SERIES,
    BLS_ROW_GRAIN,
    BLS_MONTHLY_PERIODS,
    BLS_NUMERIC_VALUES,
    BLS_VALUE_RANGE,
)
from pipelines.validation.sba_payload_checks import check_sba_required_resources
from tests.unit.raw_manifest_test_helpers import (
    CountingRawArtifactReader,
    sba_manifest_for,
    write_raw_file,
)
from tests.unit.validation_test_helpers import failed_check_ids


def test_sba_required_resources_check_reports_missing_resource(tmp_path):
    """Validate that SBA required resources check reports missing resource."""
    manifest = sba_manifest_for(write_raw_file(tmp_path, "a,b\n1,2\n"))

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


def test_sba_required_resources_reuses_raw_file_exists_resource_names(tmp_path):
    """Validate that SBA required resources reuses raw file exists resource names."""
    manifest = sba_manifest_for(write_raw_file(tmp_path, "a,b\n1,2\n"))
    artifact_reader = CountingRawArtifactReader()

    results = check_sba_required_resources(
        [manifest],
        required_resource_names=["sba_7a_fy2020_present"],
        artifact_reader=artifact_reader,
        raw_file_exists_resource_names={"sba_7a_fy2020_present"},
    )

    assert artifact_reader.exists_calls == 0
    assert all(result.status == "passed" for result in results)


def test_sba_required_resources_reports_empty_local_raw_path_unreadable(tmp_path):
    """Validate that SBA required resources reports empty local raw path unreadable."""
    manifest = sba_manifest_for(write_raw_file(tmp_path, "a,b\n1,2\n"))
    manifest["local_raw_path"] = ""

    results = check_sba_required_resources(
        [manifest],
        required_resource_names=["sba_7a_fy2020_present"],
    )

    assert results[1].status == "failed"
    assert results[1].observed_value == {
        "unreadable_resources": ["sba_7a_fy2020_present"]
    }


def test_source_validation_checks_use_configured_identity(tmp_path):
    """Validate that source validation checks use configured identity."""
    source_identity = SourceIdentity(
        source_system="custom_source",
        dataset_name="custom_dataset",
    )
    sba_manifest = sba_manifest_for(
        write_raw_file(tmp_path, "a,b\n1,2\n"),
        source_system="custom_source",
        dataset_name="custom_dataset",
    )
    census_payload = [
        ["YEAR", "NAME", "state", "ESTAB"],
        ["2023", "Alabama", "01", "98246"],
    ]
    bls_payload = {
        "normalized_rows": [
            {
                "series_id": "LASST010000000000003",
                "observed_month": "2023-01-01",
                "period": "M01",
                "value": 2.6,
            },
        ]
    }

    results = [
        *check_sba_required_resources(
            [sba_manifest],
            required_resource_names=["sba_7a_fy2020_present"],
            source_identity=source_identity,
        ),
        *check_census_bds_payload(
            census_payload,
            required_variables=("YEAR", "NAME", "state", "ESTAB"),
            expected_state_count=1,
            pipeline_run_id="run-123",
            source_identity=source_identity,
        ),
        *check_bls_laus_payload(
            bls_payload,
            expected_series_ids=("LASST010000000000003",),
            pipeline_run_id="run-123",
            source_identity=source_identity,
        ),
    ]

    assert {result.source_system for result in results} == {"custom_source"}
    assert {result.source_dataset for result in results} == {"custom_dataset"}


def test_census_payload_check_requires_variables_and_state_coverage():
    """Validate that census payload check requires variables and state coverage."""
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
    assert [(result.validation_check_id, result.check_name) for result in results] == [
        (BDS_ROW_GRAIN.validation_check_id, BDS_ROW_GRAIN.check_name),
        (BDS_REQUIRED_VARIABLES.validation_check_id, BDS_REQUIRED_VARIABLES.check_name),
        (BDS_STATE_COVERAGE.validation_check_id, BDS_STATE_COVERAGE.check_name),
    ]


def test_bls_payload_check_requires_expected_series_and_valid_months():
    """Validate that BLS payload check requires expected series and valid months."""
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
    assert [(result.validation_check_id, result.check_name) for result in results] == [
        (BLS_ROW_GRAIN.validation_check_id, BLS_ROW_GRAIN.check_name),
        (BLS_EXPECTED_SERIES.validation_check_id, BLS_EXPECTED_SERIES.check_name),
        (BLS_MONTHLY_PERIODS.validation_check_id, BLS_MONTHLY_PERIODS.check_name),
        (BLS_NUMERIC_VALUES.validation_check_id, BLS_NUMERIC_VALUES.check_name),
        (BLS_VALUE_RANGE.validation_check_id, BLS_VALUE_RANGE.check_name),
    ]


def test_bls_payload_check_honors_configured_period_and_value_bounds():
    """Validate that BLS payload check honors configured period and value bounds."""
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

    failed_ids = failed_check_ids(results)
    assert {"BLS_RAW_002", "BLS_RAW_004"} <= failed_ids
