from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeAlias

from pipelines.utils.config import ProjectConfig
from pipelines.validation.raw_validation_models import RawValidationExpectations
from pipelines.validation.raw_validation_resources import (
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_KEY,
)


SourceExpectationConfig: TypeAlias = dict[str, Any]


@dataclass(frozen=True)
class BlsValidationSettings:
    required_period_pattern: str
    unemployment_rate_min: float
    unemployment_rate_max: float


_DEFAULT_BLS_VALIDATION_SETTINGS = BlsValidationSettings(
    required_period_pattern=r"^M(0[1-9]|1[0-2])$",
    unemployment_rate_min=0,
    unemployment_rate_max=100,
)
_FIXTURE_SBA_REQUIRED_RESOURCE_NAMES = [
    "sba_7a_fy2020_present",
    "sba_504_fy2010_present",
]
_FIXTURE_BLS_EXPECTED_SERIES_IDS = (
    "LASST010000000000003",
    "LASST170000000000003",
)
_FIXTURE_EXTRACT_MODE = "fixture"


def raw_validation_expectations(
    extract_mode: str,
    project_config: ProjectConfig,
) -> RawValidationExpectations:
    bls_settings = _bls_validation_settings(extract_mode, project_config)
    return RawValidationExpectations(
        sba_required_resource_names=_sba_required_resource_names(
            extract_mode,
            project_config,
        ),
        census_required_variables=_census_required_variables(
            extract_mode,
            project_config,
        ),
        census_expected_state_count=_census_expected_state_count(
            extract_mode,
            project_config,
        ),
        bls_expected_series_ids=_bls_expected_series_ids(
            extract_mode,
            project_config,
        ),
        bls_required_period_pattern=bls_settings.required_period_pattern,
        bls_unemployment_rate_min=bls_settings.unemployment_rate_min,
        bls_unemployment_rate_max=bls_settings.unemployment_rate_max,
    )


def _sba_required_resource_names(
    extract_mode: str,
    project_config: ProjectConfig,
) -> list[str]:
    if _is_fixture_extract(extract_mode):
        return list(_FIXTURE_SBA_REQUIRED_RESOURCE_NAMES)

    sba_expectations = _enabled_sba_expectations(project_config)
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


def _census_required_variables(
    extract_mode: str,
    project_config: ProjectConfig,
) -> tuple[str, ...]:
    if _is_fixture_extract(extract_mode):
        if CENSUS_BDS_SOURCE_KEY not in project_config.raw_validation_expectations:
            return ()
        return _census_required_variables_from(
            _configured_census_expectations(project_config)
        )

    census_expectations = _enabled_census_expectations(project_config)
    if census_expectations is None:
        return ()
    return _census_required_variables_from(census_expectations)


def _census_expected_state_count(
    extract_mode: str,
    project_config: ProjectConfig,
) -> int:
    if _is_fixture_extract(extract_mode):
        if CENSUS_BDS_SOURCE_KEY not in project_config.raw_validation_expectations:
            return 0
        return 2

    census_expectations = _enabled_census_expectations(project_config)
    if census_expectations is None:
        return 0
    return int(census_expectations["expected_state_count"])


def _census_required_variables_from(
    census_expectations: SourceExpectationConfig,
) -> tuple[str, ...]:
    return tuple(census_expectations["required_variables"])


def _bls_expected_series_ids(
    extract_mode: str,
    project_config: ProjectConfig,
) -> tuple[str, ...]:
    if _is_fixture_extract(extract_mode):
        return _FIXTURE_BLS_EXPECTED_SERIES_IDS
    if _enabled_bls_expectations(project_config) is None:
        return ()
    return tuple(series.series_id for series in project_config.bls_laus.series)


def _bls_validation_settings(
    extract_mode: str,
    project_config: ProjectConfig,
) -> BlsValidationSettings:
    if _is_fixture_extract(extract_mode):
        return _DEFAULT_BLS_VALIDATION_SETTINGS
    bls_expectations = _enabled_bls_expectations(project_config)
    if bls_expectations is None:
        return _DEFAULT_BLS_VALIDATION_SETTINGS
    return _bls_validation_settings_from(bls_expectations)


def _is_fixture_extract(extract_mode: str) -> bool:
    return extract_mode == _FIXTURE_EXTRACT_MODE


def _enabled_source_expectations(
    project_config: ProjectConfig,
    source_key: str,
) -> SourceExpectationConfig | None:
    if not project_config.is_source_enabled(source_key):
        return None
    return project_config.raw_validation_expectations[source_key]


def _enabled_sba_expectations(
    project_config: ProjectConfig,
) -> SourceExpectationConfig | None:
    return _enabled_source_expectations(project_config, SBA_FOIA_SOURCE_KEY)


def _configured_census_expectations(
    project_config: ProjectConfig,
) -> SourceExpectationConfig:
    return project_config.raw_validation_expectations[CENSUS_BDS_SOURCE_KEY]


def _enabled_census_expectations(
    project_config: ProjectConfig,
) -> SourceExpectationConfig | None:
    return _enabled_source_expectations(project_config, CENSUS_BDS_SOURCE_KEY)


def _enabled_bls_expectations(
    project_config: ProjectConfig,
) -> SourceExpectationConfig | None:
    return _enabled_source_expectations(project_config, BLS_LAUS_SOURCE_KEY)


def _bls_validation_settings_from(
    bls_expectations: SourceExpectationConfig,
) -> BlsValidationSettings:
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
