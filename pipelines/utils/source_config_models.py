from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar

import yaml


ConfigT = TypeVar("ConfigT")

DEFAULT_SBA_PACKAGE_URL = (
    "https://data.sba.gov/api/3/action/package_show?id=7-a-504-foia"
)
SOURCES_CONFIG_FILE = "sources.yml"
SOURCES_CONFIG_SECTION = "sources"
SBA_RESOURCES_CONFIG_FILE = "sba_resources.yml"
SBA_RESOURCES_CONFIG_SECTION = "sba_resources"
CENSUS_BDS_CONFIG_FILE = "census_bds_variables.yml"
CENSUS_BDS_CONFIG_SECTION = "census_bds"
BLS_LAUS_CONFIG_FILE = "bls_laus_state_series.yml"
BLS_LAUS_CONFIG_SECTION = "bls_laus"
FRESHNESS_RULES_CONFIG_FILE = "freshness_rules.yml"
FRESHNESS_RULES_CONFIG_SECTION = "freshness_rules"
RAW_VALIDATION_EXPECTATIONS_CONFIG_FILE = "raw_validation_expectations.yml"
RAW_VALIDATION_EXPECTATIONS_CONFIG_SECTION = "raw_validation_expectations"

CONFIG_FILE_SECTIONS = {
    SOURCES_CONFIG_FILE: SOURCES_CONFIG_SECTION,
    SBA_RESOURCES_CONFIG_FILE: SBA_RESOURCES_CONFIG_SECTION,
    CENSUS_BDS_CONFIG_FILE: CENSUS_BDS_CONFIG_SECTION,
    BLS_LAUS_CONFIG_FILE: BLS_LAUS_CONFIG_SECTION,
    FRESHNESS_RULES_CONFIG_FILE: FRESHNESS_RULES_CONFIG_SECTION,
    RAW_VALIDATION_EXPECTATIONS_CONFIG_FILE: (
        RAW_VALIDATION_EXPECTATIONS_CONFIG_SECTION
    ),
}
CONFIG_FILENAMES = tuple(CONFIG_FILE_SECTIONS)


def parse_config_bool(value: Any, *, field_name: str) -> bool:
    """Parse YAML boolean flags without treating every non-empty string as true."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized_value = value.strip().lower()
        if normalized_value in {"true", "1"}:
            return True
        if normalized_value in {"false", "0"}:
            return False
    raise ValueError(f"Expected boolean for {field_name}: {value!r}")


@dataclass(frozen=True)
class SBAResourceSpec:
    logical_name: str
    program: str
    source_period: str
    expected_format: str
    required: bool
    title_pattern: str


@dataclass(frozen=True)
class SBADiscoveryConfig:
    strategy: str
    package_url: str
    allow_dynamic_url_resolution: bool
    cache_subdir: str | None = None


@dataclass(frozen=True)
class SBAResourcesConfig:
    dataset_name: str
    discovery: SBADiscoveryConfig
    resources: tuple[SBAResourceSpec, ...]


@dataclass(frozen=True)
class CensusBDSConfig:
    endpoint: str
    geography: str
    start_year: int
    required_variables: tuple[str, ...]


@dataclass(frozen=True)
class BLSSeriesConfig:
    state_fips: str
    state_abbr: str
    state_name: str
    series_id: str


@dataclass(frozen=True)
class BLSLAUSConfig:
    endpoint: str
    measure_name: str
    seasonal_adjustment: str
    series: tuple[BLSSeriesConfig, ...]
    start_year: int = 1990


def parse_sba_resources_config(config: Mapping[str, Any]) -> SBAResourcesConfig:
    discovery = config.get("discovery", {})
    strategy = str(discovery.get("strategy", "sba_open_data_metadata"))
    if strategy != "sba_open_data_metadata":
        raise ValueError(f"Unsupported SBA discovery strategy: {strategy}")

    return SBAResourcesConfig(
        dataset_name=str(config["dataset_name"]),
        discovery=SBADiscoveryConfig(
            strategy=strategy,
            package_url=str(discovery.get("package_url", DEFAULT_SBA_PACKAGE_URL)),
            allow_dynamic_url_resolution=parse_config_bool(
                discovery.get("allow_dynamic_url_resolution", True),
                field_name="sba_resources.discovery.allow_dynamic_url_resolution",
            ),
            cache_subdir=(
                str(discovery["cache_subdir"])
                if discovery.get("cache_subdir") is not None
                else None
            ),
        ),
        resources=tuple(
            SBAResourceSpec(
                logical_name=str(resource["logical_name"]),
                program=str(resource["program"]),
                source_period=str(resource["source_period"]),
                expected_format=str(resource["expected_format"]).lower(),
                required=parse_config_bool(
                    resource["required"],
                    field_name=(
                        "sba_resources.resources"
                        f"[{resource.get('logical_name', '?')}].required"
                    ),
                ),
                title_pattern=str(resource["title_pattern"]),
            )
            for resource in config["resources"]
        ),
    )


def load_sba_resources_config(
    config_path: Path | str = f"config/{SBA_RESOURCES_CONFIG_FILE}",
) -> SBAResourcesConfig:
    return _load_config_section(
        config_path,
        section_name=SBA_RESOURCES_CONFIG_SECTION,
        parser=parse_sba_resources_config,
    )


def parse_census_bds_config(config: Mapping[str, Any]) -> CensusBDSConfig:
    variables = tuple(
        str(variable["name"])
        for variable in config["variables"]
        if parse_config_bool(
            variable.get("required", False),
            field_name=f"census_bds.variables[{variable.get('name', '?')}].required",
        )
    )
    return CensusBDSConfig(
        endpoint=str(config["endpoint"]),
        geography=str(config["geography"]),
        start_year=int(config["start_year"]),
        required_variables=variables,
    )


def load_census_bds_config(
    config_path: Path | str = f"config/{CENSUS_BDS_CONFIG_FILE}",
) -> CensusBDSConfig:
    return _load_config_section(
        config_path,
        section_name=CENSUS_BDS_CONFIG_SECTION,
        parser=parse_census_bds_config,
    )


def parse_bls_laus_config(config: Mapping[str, Any]) -> BLSLAUSConfig:
    return BLSLAUSConfig(
        endpoint=str(config["endpoint"]),
        measure_name=str(config["measure_name"]),
        seasonal_adjustment=str(config["seasonal_adjustment"]),
        series=tuple(
            BLSSeriesConfig(
                state_fips=str(row["state_fips"]),
                state_abbr=str(row["state_abbr"]),
                state_name=str(row["state_name"]),
                series_id=str(row["series_id"]),
            )
            for row in config["series"]
        ),
        start_year=int(config["start_year"]),
    )


def load_bls_laus_config(
    config_path: Path | str = f"config/{BLS_LAUS_CONFIG_FILE}",
) -> BLSLAUSConfig:
    return _load_config_section(
        config_path,
        section_name=BLS_LAUS_CONFIG_SECTION,
        parser=parse_bls_laus_config,
    )


def _load_config_section(
    config_path: Path | str,
    *,
    section_name: str,
    parser: Callable[[Mapping[str, Any]], ConfigT],
) -> ConfigT:
    return parser(load_yaml_file(Path(config_path))[section_name])


def load_yaml_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in config file: {path}")

    return data
