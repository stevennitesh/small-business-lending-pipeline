from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


CONFIG_FILENAMES = (
    "sources.yml",
    "sba_resources.yml",
    "census_bds_variables.yml",
    "bls_laus_state_series.yml",
    "freshness_rules.yml",
    "validation_thresholds.yml",
)


@dataclass(frozen=True)
class ProjectConfig:
    config_dir: Path
    files: dict[str, dict[str, Any]]

    def get(self, filename: str) -> dict[str, Any]:
        return self.files[filename]


def load_yaml_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in config file: {path}")

    return data


def load_project_config(config_dir: Path | str = "config") -> ProjectConfig:
    resolved_config_dir = Path(config_dir)
    files = {
        filename: load_yaml_file(resolved_config_dir / filename)
        for filename in CONFIG_FILENAMES
    }

    return ProjectConfig(config_dir=resolved_config_dir, files=files)
