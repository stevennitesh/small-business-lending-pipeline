from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from pipelines.extract.bls_laus_extract import BLSLAUSConfig
    from pipelines.extract.census_bds_extract import CensusBDSConfig
    from pipelines.extract.sba_extract import SBAResourcesConfig


CONFIG_FILENAMES = (
    "sources.yml",
    "sba_resources.yml",
    "census_bds_variables.yml",
    "bls_laus_state_series.yml",
    "freshness_rules.yml",
    "raw_validation_expectations.yml",
)


@dataclass(frozen=True)
class SourceIdentity:
    source_system: str
    dataset_name: str


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


def load_yaml_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in config file: {path}")

    return data


def load_project_config(config_dir: Path | str = "config") -> ProjectConfig:
    from pipelines.extract.bls_laus_extract import parse_bls_laus_config
    from pipelines.extract.census_bds_extract import parse_census_bds_config
    from pipelines.extract.sba_extract import parse_sba_resources_config

    resolved_config_dir = Path(config_dir)
    files = {
        filename: load_yaml_file(resolved_config_dir / filename)
        for filename in CONFIG_FILENAMES
    }
    sources = _parse_source_configs(files["sources.yml"]["sources"])
    freshness_rules = files["freshness_rules.yml"]["freshness_rules"]
    raw_validation_expectations = files["raw_validation_expectations.yml"][
        "raw_validation_expectations"
    ]
    sba = parse_sba_resources_config(files["sba_resources.yml"]["sba_resources"])
    census_bds = parse_census_bds_config(
        files["census_bds_variables.yml"]["census_bds"]
    )
    bls_laus = parse_bls_laus_config(
        files["bls_laus_state_series.yml"]["bls_laus"]
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


def _parse_source_configs(raw_sources: dict[str, Any]) -> dict[str, SourceConfig]:
    return {
        source_name: SourceConfig(
            enabled=bool(source_config["enabled"]),
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
    enabled_source_names = {
        source_name
        for source_name, source_config in sources.items()
        if source_config.enabled
    }
    freshness_names = set(freshness_rules)
    expectation_names = set(raw_validation_expectations)

    unknown_freshness = sorted(freshness_names - source_names)
    if unknown_freshness:
        raise ValueError(
            "freshness_rules.yml contains unknown source keys: "
            + ", ".join(unknown_freshness)
        )

    unknown_expectations = sorted(expectation_names - source_names)
    if unknown_expectations:
        raise ValueError(
            "raw_validation_expectations.yml contains unknown source keys: "
            + ", ".join(unknown_expectations)
        )

    missing_freshness = sorted(enabled_source_names - freshness_names)
    if missing_freshness:
        raise ValueError(
            "Enabled sources are missing freshness rules: "
            + ", ".join(missing_freshness)
        )

    missing_expectations = sorted(enabled_source_names - expectation_names)
    if missing_expectations:
        raise ValueError(
            "Enabled sources are missing raw validation expectations: "
            + ", ".join(missing_expectations)
        )

    for source_name in sorted(enabled_source_names & freshness_names):
        expected_cadence = str(freshness_rules[source_name].get("expected_cadence"))
        refresh_cadence = sources[source_name].refresh_cadence
        if expected_cadence != refresh_cadence:
            raise ValueError(
                f"Source {source_name} refresh_cadence ({refresh_cadence}) "
                f"does not match freshness expected_cadence ({expected_cadence})."
            )

    if "sba_foia" in sources and sources["sba_foia"].dataset_name != sba.dataset_name:
        raise ValueError(
            "SBA dataset_name does not match sources.yml: "
            f"{sba.dataset_name} != {sources['sba_foia'].dataset_name}"
        )

    if "census_bds" in raw_validation_expectations:
        required_variables = set(
            raw_validation_expectations["census_bds"]["required_variables"]
        )
        requested_variables = set(census_bds.required_variables)
        missing_requested_variables = sorted(required_variables - requested_variables)
        if missing_requested_variables:
            raise ValueError(
                "Census BDS raw validation required_variables are not requested variables: "
                + ", ".join(missing_requested_variables)
            )

    if "sba_foia" in raw_validation_expectations:
        required_programs = {
            str(program)
            for program in raw_validation_expectations["sba_foia"][
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

    if "bls_laus" in raw_validation_expectations:
        bls_expectations = raw_validation_expectations["bls_laus"]
        re.compile(str(bls_expectations["required_period_pattern"]))
        unemployment_rate_min = float(bls_expectations["unemployment_rate_min"])
        unemployment_rate_max = float(bls_expectations["unemployment_rate_max"])
        if unemployment_rate_min > unemployment_rate_max:
            raise ValueError(
                "BLS LAUS unemployment_rate_min cannot exceed unemployment_rate_max."
            )
