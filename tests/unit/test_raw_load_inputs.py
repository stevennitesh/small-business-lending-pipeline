from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pipelines.load.raw_load_inputs import prepare_raw_load_inputs
from pipelines.validation.validation_result_io import write_validation_results
from tests.unit.raw_load_test_helpers import (
    build_raw_load_fixture_manifests,
    raw_load_validation_result,
    raw_load_validation_results,
)


@pytest.mark.parametrize(
    "invalid_evidence",
    [
        "empty",
        "gate_only",
        "other_run",
        "other_source",
        "missing_resource",
        "other_checksum",
        "other_uri",
        "warning",
        "other_scope",
    ],
)
def test_raw_load_requires_evidence_for_selected_artifacts(tmp_path, invalid_evidence):
    """Reject empty or unrelated passing results before either route can load."""
    manifests = build_raw_load_fixture_manifests(tmp_path)
    results = raw_load_validation_results(manifests)
    if invalid_evidence == "empty":
        results = []
    elif invalid_evidence == "gate_only":
        results = [raw_load_validation_result()]
    elif invalid_evidence == "other_run":
        results = [replace(result, pipeline_run_id="other-run") for result in results]
    elif invalid_evidence == "other_source":
        results = [
            replace(result, source_dataset="other-dataset") for result in results
        ]
    elif invalid_evidence == "missing_resource":
        results = [
            result
            for result in results
            if result.source_resource_name != "laus_state_month"
        ]
    elif invalid_evidence == "other_checksum":
        results = [
            replace(
                result, expected_value="old-checksum", observed_value="old-checksum"
            )
            if result.validation_check_id == "RAW_003"
            else result
            for result in results
        ]
    elif invalid_evidence == "other_uri":
        results = [
            replace(result, observed_value="other/raw/file.csv")
            if result.validation_check_id == "RAW_001"
            else result
            for result in results
        ]
    elif invalid_evidence == "warning":
        results = [replace(result, severity="warning") for result in results]
    else:
        results = [replace(result, validation_scope="modeled") for result in results]

    validation_path = write_validation_results(results, tmp_path / "validation.json")
    with pytest.raises(RuntimeError, match="validation|Validation"):
        prepare_raw_load_inputs(
            sba_7a_manifest_paths=manifests["sba_7a"],
            sba_504_manifest_paths=manifests["sba_504"],
            census_bds_manifest_paths=manifests["census"],
            bls_laus_manifest_paths=manifests["bls"],
            validation_result_paths=[validation_path],
            error_cls=RuntimeError,
            missing_validation_message="Missing validation evidence.",
        )


def test_raw_load_accepts_matching_evidence_from_multiple_runs(tmp_path):
    """Preserved snapshots can have different run IDs with their own evidence."""
    manifests = build_raw_load_fixture_manifests(tmp_path)
    manifest_path = manifests["census"][0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pipeline_run_id"] = "older-census-run"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    validation_path = write_validation_results(
        raw_load_validation_results(manifests), tmp_path / "validation.json"
    )

    inputs = prepare_raw_load_inputs(
        sba_7a_manifest_paths=manifests["sba_7a"],
        sba_504_manifest_paths=manifests["sba_504"],
        census_bds_manifest_paths=manifests["census"],
        bls_laus_manifest_paths=manifests["bls"],
        validation_result_paths=[validation_path],
        error_cls=RuntimeError,
        missing_validation_message="Missing validation evidence.",
    )
    assert inputs.pipeline_run_ids == ("older-census-run", "run-123")


def test_raw_load_accepts_legacy_local_manifest_storage_fields(tmp_path):
    """Legacy local manifests still bind to their normalized raw artifact URI."""
    manifests = build_raw_load_fixture_manifests(tmp_path)
    results = raw_load_validation_results(manifests)
    for manifest_paths in manifests.values():
        for path in manifest_paths:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            del manifest["raw_uri"]
            del manifest["storage_backend"]
            path.write_text(json.dumps(manifest), encoding="utf-8")
    validation_path = write_validation_results(results, tmp_path / "validation.json")

    inputs = prepare_raw_load_inputs(
        sba_7a_manifest_paths=manifests["sba_7a"],
        sba_504_manifest_paths=manifests["sba_504"],
        census_bds_manifest_paths=manifests["census"],
        bls_laus_manifest_paths=manifests["bls"],
        validation_result_paths=[validation_path],
        error_cls=RuntimeError,
        missing_validation_message="Missing validation evidence.",
    )
    assert inputs.pipeline_run_ids == ("run-123",)
