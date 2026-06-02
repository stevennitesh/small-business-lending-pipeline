"""Resolve source-specific raw validation expectations from project config."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeAlias

from pipelines.utils.config import ProjectConfig
from pipelines.utils.source_resources import (
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_KEY,
    SBA_504_FY2010_PRESENT_RESOURCE_NAME,
    SBA_7A_FY2020_PRESENT_RESOURCE_NAME,
    SBA_FOIA_SOURCE_KEY,
)
from pipelines.validation.raw_validation_models import RawValidationExpectations


SourceExpectationConfig: TypeAlias = dict[str, Any]


@dataclass(frozen=True)
class BlsValidationSettings:
    """BLS payload validation thresholds and period rules."""

    required_period_pattern: str
    unemployment_rate_min: float
    unemployment_rate_max: float


_DEFAULT_BLS_VALIDATION_SETTINGS = BlsValidationSettings(
    required_period_pattern=r"^M(0[1-9]|1[0-2])$",
    unemployment_rate_min=0,
    unemployment_rate_max=100,
)
_FIXTURE_SBA_REQUIRED_RESOURCE_NAMES = [
    SBA_7A_FY2020_PRESENT_RESOURCE_NAME,
    SBA_504_FY2010_PRESENT_RESOURCE_NAME,
]
_FIXTURE_BLS_EXPECTED_SERIES_IDS = (
    "LASST010000000000003",
    "LASST170000000000003",
)


def raw_validation_expectations(
    extract_mode: str,
    project_config: ProjectConfig,
) -> RawValidationExpectations:
    """Resolve the validation expectations for fixture or live extraction runs."""
    if extract_mode == "fixture":
        return _fixture_validation_expectations(project_config)
    return _live_validation_expectations(project_config)


def _fixture_validation_expectations(
    project_config: ProjectConfig,
) -> RawValidationExpectations:
    """Resolve validation expectations for the stable fixture payloads."""
    bls_settings = _DEFAULT_BLS_VALIDATION_SETTINGS
    return RawValidationExpectations(
        sba_required_resource_names=list(_FIXTURE_SBA_REQUIRED_RESOURCE_NAMES),
        census_required_variables=_fixture_census_required_variables(project_config),
        census_expected_state_count=_fixture_census_expected_state_count(
            project_config
        ),
        bls_expected_series_ids=_FIXTURE_BLS_EXPECTED_SERIES_IDS,
        bls_required_period_pattern=bls_settings.required_period_pattern,
        bls_unemployment_rate_min=bls_settings.unemployment_rate_min,
        bls_unemployment_rate_max=bls_settings.unemployment_rate_max,
    )


def _live_validation_expectations(
    project_config: ProjectConfig,
) -> RawValidationExpectations:
    """Resolve validation expectations for live, enabled project sources."""
    bls_settings = _live_bls_validation_settings(project_config)
    return RawValidationExpectations(
        sba_required_resource_names=_live_sba_required_resource_names(project_config),
        census_required_variables=_live_census_required_variables(project_config),
        census_expected_state_count=_live_census_expected_state_count(project_config),
        bls_expected_series_ids=_live_bls_expected_series_ids(project_config),
        bls_required_period_pattern=bls_settings.required_period_pattern,
        bls_unemployment_rate_min=bls_settings.unemployment_rate_min,
        bls_unemployment_rate_max=bls_settings.unemployment_rate_max,
    )


def _live_sba_required_resource_names(project_config: ProjectConfig) -> list[str]:
    """Resolve which SBA resources must be present for live enabled sources."""
    sba_expectations = _enabled_source_expectations(
        project_config,
        SBA_FOIA_SOURCE_KEY,
    )
    if sba_expectations is None:
        return []

    required_sba_programs = {
        str(program)
        for program in sba_expectations.get(
            "required_programs",
            (),
        )
    }
    return [
        spec.logical_name
        for spec in project_config.sba.resources
        if spec.required and spec.program in required_sba_programs
    ]


def _fixture_census_required_variables(
    project_config: ProjectConfig,
) -> tuple[str, ...]:
    """Resolve Census BDS variables expected in fixture raw payload rows."""
    if CENSUS_BDS_SOURCE_KEY not in project_config.raw_validation_expectations:
        return ()
    return _census_required_variables_from(
        project_config.raw_validation_expectations[CENSUS_BDS_SOURCE_KEY]
    )


def _live_census_required_variables(
    project_config: ProjectConfig,
) -> tuple[str, ...]:
    """Resolve Census BDS variables expected in live raw payload rows."""
    census_expectations = _enabled_source_expectations(
        project_config,
        CENSUS_BDS_SOURCE_KEY,
    )
    if census_expectations is None:
        return ()
    return _census_required_variables_from(census_expectations)


def _fixture_census_expected_state_count(
    project_config: ProjectConfig,
) -> int:
    """Resolve the minimum expected Census fixture state coverage."""
    if CENSUS_BDS_SOURCE_KEY not in project_config.raw_validation_expectations:
        return 0
    return 2


def _live_census_expected_state_count(
    project_config: ProjectConfig,
) -> int:
    """Resolve the minimum expected Census state coverage for live runs."""
    census_expectations = _enabled_source_expectations(
        project_config,
        CENSUS_BDS_SOURCE_KEY,
    )
    if census_expectations is None:
        return 0
    return int(census_expectations["expected_state_count"])


def _census_required_variables_from(
    census_expectations: SourceExpectationConfig,
) -> tuple[str, ...]:
    """Return required Census variables from raw expectation config."""
    return tuple(census_expectations["required_variables"])


def _live_bls_expected_series_ids(
    project_config: ProjectConfig,
) -> tuple[str, ...]:
    """Resolve live BLS LAUS series IDs expected in the normalized payload."""
    if _enabled_source_expectations(project_config, BLS_LAUS_SOURCE_KEY) is None:
        return ()
    return tuple(series.series_id for series in project_config.bls_laus.series)


def _live_bls_validation_settings(
    project_config: ProjectConfig,
) -> BlsValidationSettings:
    """Resolve live BLS validation thresholds, falling back to defaults."""
    bls_expectations = _enabled_source_expectations(
        project_config,
        BLS_LAUS_SOURCE_KEY,
    )
    if bls_expectations is None:
        return _DEFAULT_BLS_VALIDATION_SETTINGS
    return _bls_validation_settings_from(bls_expectations)


def _enabled_source_expectations(
    project_config: ProjectConfig,
    source_key: str,
) -> SourceExpectationConfig | None:
    """Return expectations for an enabled source, or None when disabled."""
    if not project_config.is_source_enabled(source_key):
        return None
    return project_config.raw_validation_expectations[source_key]


def _bls_validation_settings_from(
    bls_expectations: SourceExpectationConfig,
) -> BlsValidationSettings:
    """Build typed BLS settings from raw config values."""
    return BlsValidationSettings(
        required_period_pattern=str(
            bls_expectations.get(
                "required_period_pattern",
                _DEFAULT_BLS_VALIDATION_SETTINGS.required_period_pattern,
            )
        ),
        unemployment_rate_min=float(
            bls_expectations.get(
                "unemployment_rate_min",
                _DEFAULT_BLS_VALIDATION_SETTINGS.unemployment_rate_min,
            )
        ),
        unemployment_rate_max=float(
            bls_expectations.get(
                "unemployment_rate_max",
                _DEFAULT_BLS_VALIDATION_SETTINGS.unemployment_rate_max,
            )
        ),
    )
