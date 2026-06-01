from __future__ import annotations

from dataclasses import replace

import pytest

import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.validation.validation_failures import ValidationFailedError
from tests.unit.validation_flow_test_helpers import fixture_validation_inputs
from tests.unit.validation_test_helpers import (
    assert_validation_output_contains,
    failed_check_ids,
    read_json,
    rewrite_json,
)


def test_raw_validation_blocks_manifest_identity_mismatch(tmp_path):
    project_config, context, extraction_paths = fixture_validation_inputs(
        tmp_path,
        pipeline_run_id="identity-mismatch-run",
    )
    rewrite_json(
        extraction_paths.census_bds_manifest_paths[0],
        dataset_name="wrong_dataset",
    )

    with pytest.raises(ValidationFailedError, match="RAW_010"):
        local_flow.validate_raw_outputs.fn(context, extraction_paths, project_config)


def test_raw_validation_blocks_missing_expected_manifest_resource(tmp_path):
    project_config, context, extraction_paths = fixture_validation_inputs(
        tmp_path,
        pipeline_run_id="missing-manifest-run",
    )
    extraction_paths = replace(
        extraction_paths,
        census_bds_manifest_paths=(),
        manifest_paths=tuple(
            path
            for path in extraction_paths.manifest_paths
            if path not in extraction_paths.census_bds_manifest_paths
        ),
    )

    with pytest.raises(ValidationFailedError, match="RAW_011"):
        local_flow.validate_raw_outputs.fn(context, extraction_paths, project_config)


def test_raw_validation_writes_results_for_missing_manifest_reference(tmp_path):
    project_config, context, extraction_paths = fixture_validation_inputs(
        tmp_path,
        pipeline_run_id="missing-manifest-reference-run",
    )
    missing_manifest = extraction_paths.census_bds_manifest_paths[0]
    missing_manifest.unlink()

    with pytest.raises(ValidationFailedError, match="RAW_004"):
        local_flow.validate_raw_outputs.fn(context, extraction_paths, project_config)

    validation_payload = read_json(
        context.run_validation_dir / "validation_results.json"
    )
    failed_ids = failed_check_ids(validation_payload)

    assert "RAW_004" in failed_ids
    assert_validation_output_contains(
        context.run_validation_dir / "validation_results.json",
        "RAW_009",
    )


def test_raw_validation_writes_results_for_malformed_manifest_json(tmp_path):
    project_config, context, extraction_paths = fixture_validation_inputs(
        tmp_path,
        pipeline_run_id="malformed-manifest-run",
    )
    malformed_manifest = extraction_paths.census_bds_manifest_paths[0]
    malformed_manifest.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValidationFailedError, match="RAW_014"):
        local_flow.validate_raw_outputs.fn(context, extraction_paths, project_config)

    validation_payload = read_json(
        context.run_validation_dir / "validation_results.json"
    )
    failed_ids = failed_check_ids(validation_payload)

    assert "RAW_014" in failed_ids
    assert_validation_output_contains(
        context.run_validation_dir / "validation_results.json",
        "RAW_009",
    )
