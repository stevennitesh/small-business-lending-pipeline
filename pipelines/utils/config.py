from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipelines.utils.config_contracts import validate_project_config_contract
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
from pipelines.utils.source_resources import SourceIdentity


@dataclass(frozen=True)
class SourceConfig:
    """Parsed source-level project configuration."""

    enabled: bool
    source_system: str
    publisher: str
    dataset_name: str
    refresh_cadence: str
    grain: str

    @property
    def identity(self) -> SourceIdentity:
        """Return the manifest/source identity for this configured source."""
        return SourceIdentity(
            source_system=self.source_system,
            dataset_name=self.dataset_name,
        )


@dataclass(frozen=True)
class ProjectConfig:
    """All parsed project configuration and source-specific config objects."""

    config_dir: Path
    files: dict[str, dict[str, Any]]
    sources: dict[str, SourceConfig]
    freshness_rules: dict[str, dict[str, Any]]
    raw_validation_expectations: dict[str, dict[str, Any]]
    sba: SBAResourcesConfig
    census_bds: CensusBDSConfig
    bls_laus: BLSLAUSConfig

    def get(self, filename: str) -> dict[str, Any]:
        """Return a raw loaded config file by filename."""
        return self.files[filename]

    def is_source_enabled(self, source_name: str) -> bool:
        """Return whether a named source is enabled."""
        return self.sources[source_name].enabled

    def source_identity(self, source_name: str) -> SourceIdentity:
        """Return the source identity for a named source."""
        return self.sources[source_name].identity


def load_project_config(config_dir: Path | str = "config") -> ProjectConfig:
    """Load, parse, and cross-validate all project config files."""
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
    # Cross-file validation catches policy/config drift before extractors build
    # manifests or raw validation expectations from inconsistent YAML.
    validate_project_config_contract(
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
    """Return the expected top-level section for a loaded config file."""
    return files[filename][CONFIG_FILE_SECTIONS[filename]]


def _parse_source_configs(raw_sources: dict[str, Any]) -> dict[str, SourceConfig]:
    """Parse source entries from sources.yml into typed source configs."""
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
