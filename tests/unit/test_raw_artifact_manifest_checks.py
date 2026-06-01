from __future__ import annotations

from pipelines.utils.config import load_project_config
from pipelines.utils.source_resources import SourceIdentity
from pipelines.validation import raw_manifest_artifact_validation
from pipelines.validation.raw_manifest_artifact_validation import (
    check_raw_manifest,
)
from pipelines.validation.raw_manifest_rule_checks import (
    check_manifest_source_identity,
    check_required_manifest_resource,
)
from pipelines.validation.raw_validation_models import RawManifestIndex
from tests.unit.config_test_helpers import CONFIG_DIR
from tests.unit.raw_manifest_test_helpers import (
    manifest_for,
    write_manifest,
    write_raw_file,
)
from tests.unit.validation_test_helpers import raw_check_result, validation_check_id_set


def test_raw_artifact_manifest_checks_pass_for_complete_manifest(tmp_path):
    raw_file = write_raw_file(
        tmp_path,
        '[["YEAR","state"],["2023","01"],["2023","02"]]\n',
    )
    manifest_path = write_manifest(tmp_path, manifest_for(raw_file))

    results = check_raw_manifest(manifest_path)

    assert validation_check_id_set(results) == {
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


def test_raw_manifest_artifact_validation_checks_loaded_manifest(tmp_path):
    raw_file = write_raw_file(
        tmp_path,
        '[["YEAR","state"],["2023","01"],["2023","02"]]\n',
    )
    manifest = manifest_for(raw_file)
    manifest_path = write_manifest(tmp_path, manifest)

    results = raw_manifest_artifact_validation.check_raw_manifest_artifact(
        manifest,
        manifest_reference=manifest_path,
    )

    assert validation_check_id_set(results) == {
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


def test_raw_manifest_artifact_validation_reports_missing_manifest_as_raw_004(tmp_path):
    results = check_raw_manifest(tmp_path / "missing-manifest.json")

    assert len(results) == 1
    assert results[0].validation_check_id == "RAW_004"
    assert results[0].check_name == "Manifest created"
    assert results[0].status == "failed"


def test_raw_manifest_artifact_validation_reports_malformed_manifest_as_raw_014(
    tmp_path,
):
    manifest_path = tmp_path / "malformed-manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")

    results = check_raw_manifest(manifest_path)

    assert len(results) == 1
    assert results[0].validation_check_id == "RAW_014"
    assert results[0].check_name == "Manifest readable JSON"
    assert results[0].source_resource_name == "manifest_reference"
    assert results[0].status == "failed"


def test_raw_manifest_artifact_validation_fails_for_missing_file(tmp_path):
    missing_file = tmp_path / "missing.json"
    placeholder_file = write_raw_file(tmp_path, "[]\n", filename="placeholder.json")
    manifest = manifest_for(placeholder_file)
    manifest["local_raw_path"] = str(missing_file)
    manifest["sha256_checksum"] = "0" * 64
    manifest_path = write_manifest(tmp_path, manifest)

    results = check_raw_manifest(manifest_path)
    file_exists = raw_check_result(results, "RAW_001")

    assert file_exists.status == "failed"
    assert file_exists.severity == "fail"


def test_raw_manifest_artifact_validation_returns_failure_for_missing_metadata(
    tmp_path,
):
    raw_file = write_raw_file(tmp_path)
    manifest = manifest_for(raw_file)
    manifest.pop("schema_hash")
    manifest_path = write_manifest(tmp_path, manifest)

    results = check_raw_manifest(manifest_path)
    metadata = raw_check_result(results, "RAW_005")
    schema_hash = raw_check_result(results, "RAW_007")

    assert metadata.status == "failed"
    assert schema_hash.status == "warning"


def test_required_manifest_resource_check_fails_when_resource_missing(tmp_path):
    raw_file = write_raw_file(tmp_path)
    manifest = manifest_for(raw_file)

    result = check_required_manifest_resource(
        [manifest],
        resource_name="laus_state_month",
        pipeline_run_id="run-123",
        source_identity=SourceIdentity(source_system="bls", dataset_name="laus"),
    )

    assert result.validation_check_id == "RAW_011"
    assert result.severity == "fail"
    assert result.status == "failed"
    assert result.expected_value == "laus_state_month"
    assert result.observed_value == {"resource_names": ["bds_state_year"]}


def test_manifest_source_identity_check_fails_on_config_mismatch(tmp_path):
    raw_file = write_raw_file(tmp_path)
    manifest = manifest_for(raw_file)

    result = check_manifest_source_identity(
        manifest,
        expected_identity=SourceIdentity(
            source_system="census",
            dataset_name="custom_bds",
        ),
    )

    assert result.validation_check_id == "RAW_010"
    assert result.severity == "fail"
    assert result.status == "failed"
    assert result.expected_value == {
        "source_system": "census",
        "dataset_name": "custom_bds",
    }
    assert result.observed_value == {
        "source_system": "census",
        "dataset_name": "bds",
    }


def test_manifest_identity_validation_reports_missing_resource_name(tmp_path):
    raw_file = write_raw_file(tmp_path)
    manifest = manifest_for(raw_file)
    manifest.pop("resource_name")
    manifest_index = RawManifestIndex(manifests=[manifest], manifests_by_resource={})

    results = raw_manifest_artifact_validation.validate_manifest_identities_and_storage(
        manifest_index,
        load_project_config(CONFIG_DIR),
        is_cloud_route=False,
    )

    assert len(results) == 1
    assert results[0].validation_check_id == "RAW_010"
    assert results[0].status == "failed"
    assert results[0].source_resource_name == "unknown"
    assert results[0].observed_value is None
    assert results[0].message == "Manifest resource_name is missing or invalid."


def test_manifest_identity_validation_reports_unknown_resource_name(tmp_path):
    raw_file = write_raw_file(tmp_path)
    manifest = manifest_for(raw_file)
    manifest["resource_name"] = "unknown_resource"
    manifest_index = RawManifestIndex.from_manifests([manifest])

    results = raw_manifest_artifact_validation.validate_manifest_identities_and_storage(
        manifest_index,
        load_project_config(CONFIG_DIR),
        is_cloud_route=False,
    )

    assert len(results) == 1
    assert results[0].validation_check_id == "RAW_010"
    assert results[0].status == "failed"
    assert results[0].source_resource_name == "unknown_resource"
    assert results[0].observed_value == "unknown_resource"
    assert (
        results[0].message
        == "Manifest resource_name is not recognized in source config."
    )
