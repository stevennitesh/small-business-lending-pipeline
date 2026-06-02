from __future__ import annotations

from typing import Any, Callable

from pipelines.storage.raw_artifacts import RawArtifactReader
from pipelines.utils.source_resources import (
    BLS_LAUS_SOURCE_IDENTITY,
    CENSUS_BDS_SOURCE_IDENTITY,
    SBA_FOIA_SOURCE_IDENTITY,
    SourceIdentity,
)
from pipelines.validation import raw_payload_resources, raw_validation_sources
from pipelines.validation.raw_validation_models import RawManifestIndex
from pipelines.validation.raw_validation_resources import (
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_KEY,
)
from pipelines.validation.validation_result import ValidationResult

SourceValidationCallable = Callable[
    [raw_validation_sources.SourceValidationContext],
    list[ValidationResult],
]


class FakeRawValidationProjectConfig:
    """Project config test double for source validation tests."""

    def __init__(
        self,
        enabled_sources: set[str],
        *,
        raw_validation_expectations: dict[str, dict[str, Any]] | None = None,
        source_identities: dict[str, SourceIdentity] | None = None,
        bls_series_ids: tuple[str, ...] = (),
    ) -> None:
        """Initialize the test double."""
        self.enabled_sources = enabled_sources
        self.raw_validation_expectations = raw_validation_expectations or {}
        self.source_identities = source_identities or {}
        self.enabled_checks: list[str] = []
        self.bls_laus = type(
            "BlsConfig",
            (),
            {
                "series": [
                    type("BlsSeries", (), {"series_id": series_id})()
                    for series_id in bls_series_ids
                ]
            },
        )()

    def is_source_enabled(self, source_name: str) -> bool:
        """Return whether the fake source is enabled."""
        self.enabled_checks.append(source_name)
        return source_name in self.enabled_sources

    def source_identity(self, source_name: str) -> SourceIdentity:
        """Return the fake source identity."""
        return self.source_identities.get(
            source_name,
            _default_source_identity(source_name),
        )


def census_validation_project_config(
    *,
    expected_state_count: int = 7,
    required_variables: tuple[str, ...] = ("EXPECTED_VALUE",),
) -> FakeRawValidationProjectConfig:
    """Build census validation project config for tests."""
    return FakeRawValidationProjectConfig(
        {CENSUS_BDS_SOURCE_KEY},
        raw_validation_expectations={
            CENSUS_BDS_SOURCE_KEY: {
                "expected_state_count": expected_state_count,
                "required_variables": required_variables,
            }
        },
    )


def bls_validation_project_config() -> FakeRawValidationProjectConfig:
    """Build BLS validation project config for tests."""
    return FakeRawValidationProjectConfig(
        {BLS_LAUS_SOURCE_KEY},
        raw_validation_expectations={BLS_LAUS_SOURCE_KEY: {}},
    )


def patch_required_json_payload_resource(
    monkeypatch,
    payload: Any,
    *,
    expected_resource_name: str | None = None,
) -> None:
    """Patch required JSON payload resource for tests."""

    def fake_validate_payload_resource(
        manifest_index,
        *,
        resource_name,
        pipeline_run_id,
        source_identity,
        artifact_reader,
        validate_payload,
    ):
        """Provide fake validate payload resource for tests."""
        if expected_resource_name is not None:
            assert resource_name == expected_resource_name
        return validate_payload(payload)

    monkeypatch.setattr(
        raw_payload_resources,
        "validate_required_json_payload_resource",
        fake_validate_payload_resource,
    )


def validate_single_source_outputs(
    project_config: FakeRawValidationProjectConfig,
    *,
    source_key: str,
    validate: SourceValidationCallable,
    pipeline_run_id: str = "run-123",
    extract_mode: str = "live",
    raw_file_exists_resource_names: set[str] | None = None,
) -> list[ValidationResult]:
    """Validate single source outputs for tests."""
    return raw_validation_sources.validate_source_outputs(
        RawManifestIndex.from_manifests([]),
        project_config,
        pipeline_run_id=pipeline_run_id,
        extract_mode=extract_mode,
        artifact_reader=RawArtifactReader(),
        raw_file_exists_resource_names=raw_file_exists_resource_names or set(),
        validator_registry=(source_validation_registration(source_key, validate),),
    )


def source_validation_registration(
    source_key: str,
    validate: SourceValidationCallable,
) -> raw_validation_sources.SourceValidationRegistration:
    """Build source validation registration for tests."""
    return raw_validation_sources.SourceValidationRegistration(source_key, validate)


def _default_source_identity(source_name: str) -> SourceIdentity:
    """Build default source identity for tests."""
    identities = {
        SBA_FOIA_SOURCE_KEY: SBA_FOIA_SOURCE_IDENTITY,
        CENSUS_BDS_SOURCE_KEY: CENSUS_BDS_SOURCE_IDENTITY,
        BLS_LAUS_SOURCE_KEY: BLS_LAUS_SOURCE_IDENTITY,
    }
    return identities[source_name]
