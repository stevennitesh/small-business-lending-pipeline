from __future__ import annotations

from pipelines.storage.raw_artifacts import RawArtifactReader
from pipelines.utils.config import SourceIdentity
from pipelines.validation import raw_validation_sources
from pipelines.validation.raw_validation_models import RawManifestIndex
from pipelines.validation.raw_validation_resources import (
    BLS_LAUS_RESOURCE_NAME,
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_RESOURCE_NAME,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_KEY,
)
from tests.unit.validation_source_test_helpers import (
    FakeRawValidationProjectConfig,
    bls_validation_project_config,
    census_validation_project_config,
    patch_required_json_payload_resource,
    source_validation_registration,
    validate_single_source_outputs,
)


def test_source_validation_dispatch_honors_enabled_sources_in_registry_order():
    calls: list[str] = []

    def validator(source_name: str):
        def validate(context):
            calls.append(source_name)
            assert context.pipeline_run_id == "run-123"
            assert context.raw_file_exists_resource_names == {CENSUS_BDS_RESOURCE_NAME}
            return []

        return validate

    validator_registry = (
        source_validation_registration(
            SBA_FOIA_SOURCE_KEY,
            validator("sba"),
        ),
        source_validation_registration(
            CENSUS_BDS_SOURCE_KEY,
            validator("census"),
        ),
        source_validation_registration(
            BLS_LAUS_SOURCE_KEY,
            validator("bls"),
        ),
    )
    project_config = FakeRawValidationProjectConfig(
        {SBA_FOIA_SOURCE_KEY, BLS_LAUS_SOURCE_KEY},
        raw_validation_expectations={
            CENSUS_BDS_SOURCE_KEY: {"required_variables": ("YEAR", "state")}
        },
    )

    results = raw_validation_sources.validate_source_outputs(
        RawManifestIndex.from_manifests([]),
        project_config,
        pipeline_run_id="run-123",
        extract_mode="fixture",
        artifact_reader=RawArtifactReader(),
        raw_file_exists_resource_names={CENSUS_BDS_RESOURCE_NAME},
        validator_registry=validator_registry,
    )

    assert results == []
    assert project_config.enabled_checks == [
        SBA_FOIA_SOURCE_KEY,
        CENSUS_BDS_SOURCE_KEY,
        BLS_LAUS_SOURCE_KEY,
    ]
    assert calls == ["sba", "bls"]


def test_census_validation_uses_required_variables_from_expectations(monkeypatch):
    captured = {}
    project_config = census_validation_project_config()

    def fake_census_payload_check(
        payload,
        *,
        required_variables,
        expected_state_count,
        pipeline_run_id,
        source_identity,
    ):
        captured["required_variables"] = required_variables
        captured["expected_state_count"] = expected_state_count
        captured["pipeline_run_id"] = pipeline_run_id
        captured["source_identity"] = source_identity
        return []

    patch_required_json_payload_resource(
        monkeypatch,
        [["EXPECTED_VALUE", "state"], ["1", "01"]],
        expected_resource_name=CENSUS_BDS_RESOURCE_NAME,
    )
    monkeypatch.setattr(
        raw_validation_sources,
        "check_census_bds_payload",
        fake_census_payload_check,
    )

    results = validate_single_source_outputs(
        project_config,
        source_key=CENSUS_BDS_SOURCE_KEY,
        validate=raw_validation_sources.validate_census_bds_source_outputs,
    )

    assert results == []
    assert captured == {
        "required_variables": ("EXPECTED_VALUE",),
        "expected_state_count": 7,
        "pipeline_run_id": "run-123",
        "source_identity": SourceIdentity(source_system="census", dataset_name="bds"),
    }


def test_census_validation_coerces_unexpected_payload_shape(monkeypatch):
    captured = {}
    project_config = census_validation_project_config()

    def fake_census_payload_check(
        payload,
        *,
        required_variables,
        expected_state_count,
        pipeline_run_id,
        source_identity,
    ):
        captured["payload"] = payload
        return []

    patch_required_json_payload_resource(
        monkeypatch,
        {"unexpected": "shape"},
        expected_resource_name=CENSUS_BDS_RESOURCE_NAME,
    )
    monkeypatch.setattr(
        raw_validation_sources,
        "check_census_bds_payload",
        fake_census_payload_check,
    )

    validate_single_source_outputs(
        project_config,
        source_key=CENSUS_BDS_SOURCE_KEY,
        validate=raw_validation_sources.validate_census_bds_source_outputs,
    )

    assert captured["payload"] == []


def test_bls_validation_coerces_unexpected_payload_shape(monkeypatch):
    captured = {}
    project_config = bls_validation_project_config()

    def fake_bls_payload_check(
        payload,
        *,
        expected_series_ids,
        pipeline_run_id,
        required_period_pattern,
        unemployment_rate_min,
        unemployment_rate_max,
        source_identity,
    ):
        captured["payload"] = payload
        return []

    patch_required_json_payload_resource(
        monkeypatch,
        [["unexpected", "shape"]],
        expected_resource_name=BLS_LAUS_RESOURCE_NAME,
    )
    monkeypatch.setattr(
        raw_validation_sources,
        "check_bls_laus_payload",
        fake_bls_payload_check,
    )

    validate_single_source_outputs(
        project_config,
        source_key=BLS_LAUS_SOURCE_KEY,
        validate=raw_validation_sources.validate_bls_laus_source_outputs,
    )

    assert captured["payload"] == {}
