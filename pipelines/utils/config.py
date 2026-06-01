from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipelines.utils.source_config_models import (
    BLS_LAUS_CONFIG_FILE,
    BLSLAUSConfig,
    CENSUS_BDS_CONFIG_FILE,
    CONFIG_FILENAMES,
    CONFIG_FILE_SECTIONS,
    FRESHNESS_RULES_CONFIG_FILE,
    RAW_VALIDATION_EXPECTATIONS_CONFIG_FILE,
    SBA_RESOURCES_CONFIG_FILE,
    CensusBDSConfig,
    SBAResourcesConfig,
    SOURCES_CONFIG_FILE,
    load_yaml_file as _load_yaml_file,
    parse_bls_laus_config,
    parse_census_bds_config,
    parse_config_bool,
    parse_sba_resources_config,
)
from pipelines.utils.source_resources import (
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_KEY,
    SourceIdentity,
)


@dataclass(frozen=True)
class SourceConfig:
    enabled: bool
    source_system: str
    publisher: str
    dataset_name: str
    refresh_cadence: str
    grain: str

    @property
    def identity(self) -> SourceIdentity:
        return SourceIdentity(
            source_system=self.source_system,
            dataset_name=self.dataset_name,
        )


@dataclass(frozen=True)
class ProjectConfig:
    config_dir: Path
    files: dict[str, dict[str, Any]]
    sources: dict[str, SourceConfig]
    freshness_rules: dict[str, dict[str, Any]]
    raw_validation_expectations: dict[str, dict[str, Any]]
    sba: SBAResourcesConfig
    census_bds: CensusBDSConfig
    bls_laus: BLSLAUSConfig

    def get(self, filename: str) -> dict[str, Any]:
        return self.files[filename]

    def is_source_enabled(self, source_name: str) -> bool:
        return self.sources[source_name].enabled

    def source_identity(self, source_name: str) -> SourceIdentity:
        return self.sources[source_name].identity


def load_project_config(config_dir: Path | str = "config") -> ProjectConfig:
    resolved_config_dir = Path(config_dir)
    files = {
        filename: _load_yaml_file(resolved_config_dir / filename)
        for filename in CONFIG_FILENAMES
    }
    sources = _parse_source_configs(_project_config_section(files, SOURCES_CONFIG_FILE))
    freshness_rules = _project_config_section(files, FRESHNESS_RULES_CONFIG_FILE)
    raw_validation_expectations = _project_config_section(
        files,
        RAW_VALIDATION_EXPECTATIONS_CONFIG_FILE,
    )
    sba = parse_sba_resources_config(
        _project_config_section(files, SBA_RESOURCES_CONFIG_FILE)
    )
    census_bds = parse_census_bds_config(
        _project_config_section(files, CENSUS_BDS_CONFIG_FILE)
    )
    bls_laus = parse_bls_laus_config(
        _project_config_section(files, BLS_LAUS_CONFIG_FILE)
    )
    _validate_project_config_contract(
        sources=sources,
        freshness_rules=freshness_rules,
        raw_validation_expectations=raw_validation_expectations,
        sba=sba,
        census_bds=census_bds,
        bls_laus=bls_laus,
    )

    return ProjectConfig(
        config_dir=resolved_config_dir,
        files=files,
        sources=sources,
        freshness_rules=freshness_rules,
        raw_validation_expectations=raw_validation_expectations,
        sba=sba,
        census_bds=census_bds,
        bls_laus=bls_laus,
    )


def _project_config_section(
    files: dict[str, dict[str, Any]],
    filename: str,
) -> dict[str, Any]:
    return files[filename][CONFIG_FILE_SECTIONS[filename]]


def _parse_source_configs(raw_sources: dict[str, Any]) -> dict[str, SourceConfig]:
    return {
        source_name: SourceConfig(
            enabled=parse_config_bool(
                source_config["enabled"],
                field_name=f"sources.{source_name}.enabled",
            ),
            source_system=str(source_config["source_system"]),
            publisher=str(source_config["publisher"]),
            dataset_name=str(source_config["dataset_name"]),
            refresh_cadence=str(source_config["refresh_cadence"]),
            grain=str(source_config["grain"]),
        )
        for source_name, source_config in raw_sources.items()
    }


def _validate_project_config_contract(
    *,
    sources: dict[str, SourceConfig],
    freshness_rules: dict[str, dict[str, Any]],
    raw_validation_expectations: dict[str, dict[str, Any]],
    sba: SBAResourcesConfig,
    census_bds: CensusBDSConfig,
    bls_laus: BLSLAUSConfig,
) -> None:
    source_names = set(sources)
    enabled_source_names = _enabled_source_names(sources)

    _validate_policy_sources(
        policy_filename=FRESHNESS_RULES_CONFIG_FILE,
        policy_source_names=set(freshness_rules),
        source_names=source_names,
    )
    _validate_policy_sources(
        policy_filename=RAW_VALIDATION_EXPECTATIONS_CONFIG_FILE,
        policy_source_names=set(raw_validation_expectations),
        source_names=source_names,
    )
    _validate_enabled_sources_have_policy(
        policy_name="freshness rules",
        policy_source_names=set(freshness_rules),
        enabled_source_names=enabled_source_names,
    )
    _validate_enabled_sources_have_policy(
        policy_name="raw validation expectations",
        policy_source_names=set(raw_validation_expectations),
        enabled_source_names=enabled_source_names,
    )
    _validate_freshness_cadence(
        sources=sources,
        freshness_rules=freshness_rules,
        enabled_source_names=enabled_source_names,
    )
    _validate_sba_config_contract(sources, sba)
    _validate_census_validation_contract(raw_validation_expectations, census_bds)
    _validate_sba_validation_contract(raw_validation_expectations, sba)
    _validate_bls_validation_contract(raw_validation_expectations)


def _enabled_source_names(sources: dict[str, SourceConfig]) -> set[str]:
    return {
        source_name
        for source_name, source_config in sources.items()
        if source_config.enabled
    }


def _validate_policy_sources(
    *,
    policy_filename: str,
    policy_source_names: set[str],
    source_names: set[str],
) -> None:
    unknown_sources = sorted(policy_source_names - source_names)
    if unknown_sources:
        raise ValueError(
            f"{policy_filename} contains unknown source keys: "
            + ", ".join(unknown_sources)
        )


def _validate_enabled_sources_have_policy(
    *,
    policy_name: str,
    policy_source_names: set[str],
    enabled_source_names: set[str],
) -> None:
    missing_sources = sorted(enabled_source_names - policy_source_names)
    if missing_sources:
        raise ValueError(
            f"Enabled sources are missing {policy_name}: "
            + ", ".join(missing_sources)
        )


def _validate_freshness_cadence(
    *,
    sources: dict[str, SourceConfig],
    freshness_rules: dict[str, dict[str, Any]],
    enabled_source_names: set[str],
) -> None:
    for source_name in sorted(enabled_source_names & set(freshness_rules)):
        expected_cadence = str(freshness_rules[source_name].get("expected_cadence"))
        refresh_cadence = sources[source_name].refresh_cadence
        if expected_cadence != refresh_cadence:
            raise ValueError(
                f"Source {source_name} refresh_cadence ({refresh_cadence}) "
                f"does not match freshness expected_cadence ({expected_cadence})."
            )


def _validate_sba_config_contract(
    sources: dict[str, SourceConfig],
    sba: SBAResourcesConfig,
) -> None:
    if (
        SBA_FOIA_SOURCE_KEY not in sources
        or sources[SBA_FOIA_SOURCE_KEY].dataset_name == sba.dataset_name
    ):
        return
    raise ValueError(
        f"SBA dataset_name does not match {SOURCES_CONFIG_FILE}: "
        f"{sba.dataset_name} != {sources[SBA_FOIA_SOURCE_KEY].dataset_name}"
    )


def _validate_census_validation_contract(
    raw_validation_expectations: dict[str, dict[str, Any]],
    census_bds: CensusBDSConfig,
) -> None:
    if CENSUS_BDS_SOURCE_KEY not in raw_validation_expectations:
        return

    required_variables = set(
        raw_validation_expectations[CENSUS_BDS_SOURCE_KEY]["required_variables"]
    )
    requested_variables = set(census_bds.required_variables)
    missing_requested_variables = sorted(required_variables - requested_variables)
    if missing_requested_variables:
        raise ValueError(
            "Census BDS raw validation required_variables are not requested variables: "
            + ", ".join(missing_requested_variables)
        )


def _validate_sba_validation_contract(
    raw_validation_expectations: dict[str, dict[str, Any]],
    sba: SBAResourcesConfig,
) -> None:
    if SBA_FOIA_SOURCE_KEY not in raw_validation_expectations:
        return

    required_programs = {
        str(program)
        for program in raw_validation_expectations[SBA_FOIA_SOURCE_KEY][
            "required_programs"
        ]
    }
    configured_programs = {resource.program for resource in sba.resources}
    unknown_programs = sorted(required_programs - configured_programs)
    if unknown_programs:
        raise ValueError(
            "SBA raw validation required_programs are not configured resources: "
            + ", ".join(unknown_programs)
        )


def _validate_bls_validation_contract(
    raw_validation_expectations: dict[str, dict[str, Any]],
) -> None:
    if BLS_LAUS_SOURCE_KEY not in raw_validation_expectations:
        return

    bls_expectations = raw_validation_expectations[BLS_LAUS_SOURCE_KEY]
    re.compile(str(bls_expectations["required_period_pattern"]))
    unemployment_rate_min = float(bls_expectations["unemployment_rate_min"])
    unemployment_rate_max = float(bls_expectations["unemployment_rate_max"])
    if unemployment_rate_min > unemployment_rate_max:
        raise ValueError(
            "BLS LAUS unemployment_rate_min cannot exceed unemployment_rate_max."
        )
