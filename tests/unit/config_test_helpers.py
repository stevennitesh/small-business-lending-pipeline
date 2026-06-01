from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import yaml

from pipelines.utils.source_config_models import load_yaml_file


CONFIG_DIR = Path("config")


def config_path(filename: str) -> Path:
    return CONFIG_DIR / filename


def copy_config_dir(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, config_dir)
    return config_dir


def mutate_config_file(
    tmp_path: Path,
    filename: str,
    mutator: Callable[[dict], None],
) -> Path:
    config_dir = copy_config_dir(tmp_path)
    target_config_path = config_dir / filename
    config = load_yaml_file(target_config_path)
    mutator(config)
    write_yaml_config(target_config_path, config)
    return config_dir


def write_yaml_config(path: Path, config: dict) -> None:
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
