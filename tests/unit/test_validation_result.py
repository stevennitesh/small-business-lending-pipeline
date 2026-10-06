from __future__ import annotations

import json

import pytest

from pipelines.utils.source_resources import SourceIdentity
from pipelines.validation.raw_validation_check_catalog import (
    BDS_REQUIRED_VARIABLES,
    RAW_FILE_EXISTS,
    RAW_VALIDATION_RESULT_CREATED,
)
from pipelines.validation.raw_validation_resources import (
    CENSUS_BDS_RESOURCE_NAME,
    VALIDATION_RESULTS_DATASET_NAME,
    VALIDATION_RESULTS_SOURCE_SYSTEM,
)
from pipelines.validation.validation_failures import (
    ValidationFailedError,
    assert_no_blocking_failures,
)
from pipelines.validation.validation_result import (
    make_manifest_validation_result,
    make_pipeline_validation_result,
    make_source_identity_validation_result,
    make_validation_result,
)
from pipelines.validation.validation_result_io import (
    write_validation_results,
)
from tests.unit.validation_test_helpers import raw_file_exists_result


def test_validation_result_serializes_and_writes_json(tmp_path):
    """Validate that validation result serializes and writes JSON."""
    result = raw_file_exists_result()

    output_path = write_validation_results([result], tmp_path / "validation.json")
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload == [result.to_dict()]


def test_blocking_failures_raise_before_load():
    """Validate that blocking failures raise before load."""
    failed_result = raw_file_exists_result(
        source_system="sba",
        source_dataset="7a_504_foia",
        source_resource_name="sba_7a_fy2020_present",
        passed=False,
        observed_value="missing",
    )

    with pytest.raises(ValidationFailedError, match="RAW_001"):
        assert_no_blocking_failures([failed_result])


def test_make_validation_result_defaults_passed_message():
    """Validate that make validation result defaults passed message."""
    result = make_validation_result(
        pipeline_run_id="run-123",
        validation_check_id="RAW_001",
        validation_scope="raw",
        source_system="census",
        source_dataset="bds",
        source_resource_name=CENSUS_BDS_RESOURCE_NAME,
        check_name="Raw file exists",
        check_type="completeness",
        severity="fail",
        passed=True,
        expected_value="file exists",
        observed_value="file exists",
        failed_message="Raw file is missing.",
    )

    assert result.message == "Raw file exists check passed."


def test_manifest_validation_result_uses_manifest_identity():
    """Validate that manifest validation result uses manifest identity."""
    result = make_manifest_validation_result(
        manifest={
            "pipeline_run_id": "run-123",
            "source_system": "sba",
            "dataset_name": "7a_504_foia",
            "resource_name": "sba_7a_fy2020_present",
        },
        check_definition=RAW_FILE_EXISTS,
        passed=True,
        expected_value="file exists",
        observed_value="file exists",
        failed_message="Raw file is missing.",
    )

    assert result.pipeline_run_id == "run-123"
    assert result.source_system == "sba"
    assert result.source_dataset == "7a_504_foia"
    assert result.source_resource_name == "sba_7a_fy2020_present"


def test_source_identity_validation_result_uses_source_identity():
    """Validate that source identity validation result uses source identity."""
    result = make_source_identity_validation_result(
        pipeline_run_id="run-123",
        check_definition=BDS_REQUIRED_VARIABLES,
        source_identity=SourceIdentity(source_system="census", dataset_name="bds"),
        source_resource_name=CENSUS_BDS_RESOURCE_NAME,
        passed=False,
        expected_value=["YEAR"],
        observed_value={"missing_variables": ["YEAR"]},
        failed_message="Census BDS response is missing required variables.",
    )

    assert result.source_system == "census"
    assert result.source_dataset == "bds"
    assert result.source_resource_name == CENSUS_BDS_RESOURCE_NAME
    assert result.status == "failed"


def test_pipeline_validation_result_defaults_raw_validation_identity():
    """Validate that pipeline validation result defaults raw validation identity."""
    result = make_pipeline_validation_result(
        pipeline_run_id="run-123",
        check_definition=RAW_VALIDATION_RESULT_CREATED,
        source_resource_name="validation_results",
        passed=True,
        expected_value="validation output file exists",
        observed_value="data/validation/validation_results.json",
        failed_message="Validation output file is missing.",
    )

    assert result.validation_scope == "raw"
    assert result.source_system == VALIDATION_RESULTS_SOURCE_SYSTEM
    assert result.source_dataset == VALIDATION_RESULTS_DATASET_NAME
