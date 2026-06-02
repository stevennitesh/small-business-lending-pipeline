import re

import pytest

from pipelines.utils.config import load_project_config
from pipelines.utils.source_config_models import (
    SBA_RESOURCES_CONFIG_FILE,
    SOURCES_CONFIG_FILE,
    parse_census_bds_config,
)
from pipelines.utils.source_resources import SBA_FOIA_SOURCE_KEY
from tests.unit.config_test_helpers import mutate_config_file


def test_project_config_parses_string_boolean_flags_strictly(tmp_path):
    """Validate that project config parses string boolean flags strictly."""

    def disable_sba_source(config: dict) -> None:
        """Disable SBA source for tests."""
        config["sources"][SBA_FOIA_SOURCE_KEY]["enabled"] = "false"

    config_dir = mutate_config_file(tmp_path, SOURCES_CONFIG_FILE, disable_sba_source)

    project_config = load_project_config(config_dir)

    assert project_config.sources[SBA_FOIA_SOURCE_KEY].enabled is False


def test_project_config_rejects_invalid_source_boolean(tmp_path):
    """Validate that project config rejects invalid source boolean."""

    def set_invalid_enabled(config: dict) -> None:
        """Set invalid enabled for tests."""
        config["sources"][SBA_FOIA_SOURCE_KEY]["enabled"] = "nope"

    config_dir = mutate_config_file(tmp_path, SOURCES_CONFIG_FILE, set_invalid_enabled)

    with pytest.raises(ValueError, match=re.escape("sources.sba_foia.enabled")):
        load_project_config(config_dir)


def test_sba_resource_config_parses_string_boolean_flags(tmp_path):
    """Validate that SBA resource config parses string boolean flags."""

    def stringify_sba_flags(config: dict) -> None:
        """Build stringify SBA flags for tests."""
        sba_config = config["sba_resources"]
        sba_config["discovery"]["allow_dynamic_url_resolution"] = "false"
        sba_config["resources"][0]["required"] = "0"

    config_dir = mutate_config_file(
        tmp_path,
        SBA_RESOURCES_CONFIG_FILE,
        stringify_sba_flags,
    )

    project_config = load_project_config(config_dir)

    assert project_config.sba.discovery.allow_dynamic_url_resolution is False
    assert project_config.sba.resources[0].required is False


def test_sba_resource_config_rejects_invalid_boolean(tmp_path):
    """Validate that SBA resource config rejects invalid boolean."""

    def set_invalid_required(config: dict) -> None:
        """Set invalid required for tests."""
        config["sba_resources"]["resources"][0]["required"] = "sometimes"

    config_dir = mutate_config_file(
        tmp_path,
        SBA_RESOURCES_CONFIG_FILE,
        set_invalid_required,
    )

    with pytest.raises(ValueError, match=re.escape("sba_resources.resources")):
        load_project_config(config_dir)


def test_census_bds_config_parses_string_boolean_flags():
    """Validate that census BDS config parses string boolean flags."""
    config = {
        "endpoint": "https://api.census.gov/data/timeseries/bds",
        "geography": "state:*",
        "start_year": 1990,
        "variables": [
            {"name": "YEAR", "required": "true"},
            {"name": "OPTIONAL", "required": "false"},
        ],
    }

    parsed_config = parse_census_bds_config(config)

    assert parsed_config.required_variables == ("YEAR",)


def test_census_bds_config_rejects_invalid_boolean():
    """Validate that census BDS config rejects invalid boolean."""
    config = {
        "endpoint": "https://api.census.gov/data/timeseries/bds",
        "geography": "state:*",
        "start_year": 1990,
        "variables": [{"name": "YEAR", "required": "sometimes"}],
    }

    with pytest.raises(ValueError, match=re.escape("census_bds.variables")):
        parse_census_bds_config(config)
