from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pipelines.storage.raw_artifacts import RawArtifactReader
from pipelines.utils.config import ProjectConfig, SourceIdentity
from pipelines.validation import raw_payload_resources
from pipelines.validation.bls_laus_payload_checks import check_bls_laus_payload
from pipelines.validation.census_bds_payload_checks import check_census_bds_payload
from pipelines.validation.raw_validation_models import (
    BlsLausPayload,
    CensusBdsPayload,
    JsonPayload,
    RawManifestIndex,
    RawValidationExpectations,
)
from pipelines.validation.raw_validation_expectations import raw_validation_expectations
from pipelines.validation.raw_validation_resources import (
    BLS_LAUS_SOURCE_KEY,
    BLS_LAUS_RESOURCE_NAME,
    CENSUS_BDS_SOURCE_KEY,
    CENSUS_BDS_RESOURCE_NAME,
    SBA_FOIA_SOURCE_KEY,
)
from pipelines.validation.sba_payload_checks import check_sba_required_resources
from pipelines.validation.validation_result import ValidationResult


@dataclass(frozen=True)
class SourceValidationContext:
    manifest_index: RawManifestIndex
    expectations: RawValidationExpectations
    project_config: ProjectConfig
    pipeline_run_id: str
    artifact_reader: RawArtifactReader
    raw_file_exists_resource_names: set[str]


@dataclass(frozen=True)
class SourceValidationRegistration:
    source_key: str
    validate: Callable[[SourceValidationContext], list[ValidationResult]]


@dataclass(frozen=True)
class JsonSourceValidationSpec:
    source_key: str
    resource_name: str
    coerce_payload: Callable[[JsonPayload], JsonPayload]
    validate_payload: "SourcePayloadValidator"


SourcePayloadValidator = Callable[
    [JsonPayload, SourceValidationContext, SourceIdentity],
    list[ValidationResult],
]


def validate_source_outputs(
    manifest_index: RawManifestIndex,
    project_config: ProjectConfig,
    *,
    pipeline_run_id: str,
    extract_mode: str,
    artifact_reader: RawArtifactReader,
    raw_file_exists_resource_names: set[str],
    validator_registry: tuple[SourceValidationRegistration, ...] | None = None,
) -> list[ValidationResult]:
    validation_results: list[ValidationResult] = []

    expectations = raw_validation_expectations(extract_mode, project_config)
    source_context = SourceValidationContext(
        manifest_index=manifest_index,
        expectations=expectations,
        project_config=project_config,
        pipeline_run_id=pipeline_run_id,
        artifact_reader=artifact_reader,
        raw_file_exists_resource_names=raw_file_exists_resource_names,
    )

    for validator in validator_registry or DEFAULT_VALIDATORS:
        if not project_config.is_source_enabled(validator.source_key):
            continue
        validation_results.extend(validator.validate(source_context))

    return validation_results


def validate_sba_source_outputs(
    context: SourceValidationContext,
) -> list[ValidationResult]:
    return check_sba_required_resources(
        context.manifest_index.manifests,
        required_resource_names=context.expectations.sba_required_resource_names,
        source_identity=context.project_config.source_identity(SBA_FOIA_SOURCE_KEY),
        artifact_reader=context.artifact_reader,
        raw_file_exists_resource_names=context.raw_file_exists_resource_names,
    )


def validate_census_bds_source_outputs(
    context: SourceValidationContext,
) -> list[ValidationResult]:
    return _validate_required_json_source_output(
        context,
        spec=_CENSUS_BDS_JSON_VALIDATION,
    )


def validate_bls_laus_source_outputs(
    context: SourceValidationContext,
) -> list[ValidationResult]:
    return _validate_required_json_source_output(
        context,
        spec=_BLS_LAUS_JSON_VALIDATION,
    )


def _validate_required_json_source_output(
    context: SourceValidationContext,
    *,
    spec: JsonSourceValidationSpec,
) -> list[ValidationResult]:
    source_identity = context.project_config.source_identity(spec.source_key)

    def validate_resource_payload(payload: JsonPayload) -> list[ValidationResult]:
        return spec.validate_payload(
            spec.coerce_payload(payload),
            context,
            source_identity,
        )

    return raw_payload_resources.validate_required_json_payload_resource(
        context.manifest_index,
        resource_name=spec.resource_name,
        pipeline_run_id=context.pipeline_run_id,
        source_identity=source_identity,
        artifact_reader=context.artifact_reader,
        validate_payload=validate_resource_payload,
    )


def _validate_census_bds_payload(
    payload: JsonPayload,
    context: SourceValidationContext,
    source_identity: SourceIdentity,
) -> list[ValidationResult]:
    return check_census_bds_payload(
        payload,
        required_variables=context.expectations.census_required_variables,
        expected_state_count=context.expectations.census_expected_state_count,
        pipeline_run_id=context.pipeline_run_id,
        source_identity=source_identity,
    )


def _validate_bls_laus_payload(
    payload: JsonPayload,
    context: SourceValidationContext,
    source_identity: SourceIdentity,
) -> list[ValidationResult]:
    return check_bls_laus_payload(
        payload,
        expected_series_ids=context.expectations.bls_expected_series_ids,
        pipeline_run_id=context.pipeline_run_id,
        required_period_pattern=context.expectations.bls_required_period_pattern,
        unemployment_rate_min=context.expectations.bls_unemployment_rate_min,
        unemployment_rate_max=context.expectations.bls_unemployment_rate_max,
        source_identity=source_identity,
    )


def _coerce_census_bds_payload(payload: JsonPayload) -> CensusBdsPayload:
    return payload if isinstance(payload, list) else []


def _coerce_bls_laus_payload(payload: JsonPayload) -> BlsLausPayload:
    return payload if isinstance(payload, dict) else {}


_CENSUS_BDS_JSON_VALIDATION = JsonSourceValidationSpec(
    source_key=CENSUS_BDS_SOURCE_KEY,
    resource_name=CENSUS_BDS_RESOURCE_NAME,
    coerce_payload=_coerce_census_bds_payload,
    validate_payload=_validate_census_bds_payload,
)
_BLS_LAUS_JSON_VALIDATION = JsonSourceValidationSpec(
    source_key=BLS_LAUS_SOURCE_KEY,
    resource_name=BLS_LAUS_RESOURCE_NAME,
    coerce_payload=_coerce_bls_laus_payload,
    validate_payload=_validate_bls_laus_payload,
)


DEFAULT_VALIDATORS = (
    SourceValidationRegistration(SBA_FOIA_SOURCE_KEY, validate_sba_source_outputs),
    SourceValidationRegistration(
        CENSUS_BDS_SOURCE_KEY,
        validate_census_bds_source_outputs,
    ),
    SourceValidationRegistration(BLS_LAUS_SOURCE_KEY, validate_bls_laus_source_outputs),
)
