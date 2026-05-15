from __future__ import annotations

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
    "validation_thresholds.yml",
)


@dataclass(frozen=True)
class SourceConfig:
    enabled: bool
    source_system: str
    publisher: str
    dataset_name: str
    refresh_cadence: str
    grain: str
    raw_storage_subdir: str
    manifest_subdir: str
    validation_subdir: str


@dataclass(frozen=True)
class ProjectConfig:
    config_dir: Path
    files: dict[str, dict[str, Any]]
    sources: dict[str, SourceConfig]
    freshness_rules: dict[str, dict[str, Any]]
    validation_thresholds: dict[str, dict[str, Any]]
    sba: SBAResourcesConfig
    census_bds: CensusBDSConfig
    bls_laus: BLSLAUSConfig

    def get(self, filename: str) -> dict[str, Any]:
        return self.files[filename]


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
    validation_thresholds = files["validation_thresholds.yml"][
        "validation_thresholds"
    ]

    return ProjectConfig(
        config_dir=resolved_config_dir,
        files=files,
        sources=sources,
        freshness_rules=freshness_rules,
        validation_thresholds=validation_thresholds,
        sba=parse_sba_resources_config(files["sba_resources.yml"]["sba_resources"]),
        census_bds=parse_census_bds_config(
            files["census_bds_variables.yml"]["census_bds"]
        ),
        bls_laus=parse_bls_laus_config(
            files["bls_laus_state_series.yml"]["bls_laus"]
        ),
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
            raw_storage_subdir=str(source_config["raw_storage_subdir"]),
            manifest_subdir=str(source_config["manifest_subdir"]),
            validation_subdir=str(source_config["validation_subdir"]),
        )
        for source_name, source_config in raw_sources.items()
    }
