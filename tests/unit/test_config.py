import csv
import re
from pathlib import Path

import pytest

from pipelines.utils.config import CONFIG_FILENAMES, load_project_config, load_yaml_file


CONFIG_DIR = Path("config")


def test_all_config_files_parse():
    for filename in CONFIG_FILENAMES:
        config = load_yaml_file(CONFIG_DIR / filename)
        assert config


def test_project_config_loader_returns_named_configs():
    project_config = load_project_config(CONFIG_DIR)

    assert set(project_config.files) == set(CONFIG_FILENAMES)
    assert project_config.get("sources.yml")["sources"]["sba_foia"]["enabled"] is True


def test_config_files_have_required_top_level_keys():
    required_top_level_keys = {
        "sources.yml": "sources",
        "sba_resources.yml": "sba_resources",
        "census_bds_variables.yml": "census_bds",
        "bls_laus_state_series.yml": "bls_laus",
        "freshness_rules.yml": "freshness_rules",
        "validation_thresholds.yml": "validation_thresholds",
    }

    project_config = load_project_config(CONFIG_DIR)

    for filename, key in required_top_level_keys.items():
        assert key in project_config.get(filename)


def test_enabled_sources_have_freshness_and_validation_config():
    project_config = load_project_config(CONFIG_DIR)
    sources = project_config.get("sources.yml")["sources"]
    freshness_rules = project_config.get("freshness_rules.yml")["freshness_rules"]
    validation_thresholds = project_config.get("validation_thresholds.yml")[
        "validation_thresholds"
    ]
    enabled_source_names = {
        source_name
        for source_name, source_config in sources.items()
        if source_config["enabled"]
    }

    assert enabled_source_names <= set(freshness_rules)
    assert enabled_source_names <= set(validation_thresholds)


def test_census_bds_required_variables_are_declared():
    project_config = load_project_config(CONFIG_DIR)
    variables = project_config.get("census_bds_variables.yml")["census_bds"][
        "variables"
    ]
    variable_names = {variable["name"] for variable in variables}

    assert {
        "YEAR",
        "NAME",
        "state",
        "ESTAB",
        "ESTABS_ENTRY",
        "ESTABS_EXIT",
    } <= variable_names


def test_bls_laus_config_maps_50_states_plus_dc():
    project_config = load_project_config(CONFIG_DIR)
    series = project_config.get("bls_laus_state_series.yml")["bls_laus"]["series"]
    state_fips = {row["state_fips"] for row in series}
    series_ids = {row["series_id"] for row in series}

    assert len(series) == 51
    assert "11" in state_fips
    assert len(series_ids) == 51
    assert all(re.fullmatch(r"LASST\d{15}", series_id) for series_id in series_ids)


def _read_seed(seed_name: str) -> list[dict[str, str]]:
    with Path("dbt/seeds", seed_name).open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def test_ref_state_seed_includes_50_states_plus_dc():
    rows = _read_seed("ref_state.csv")
    state_rows = [row for row in rows if row["is_state"] == "true"]
    dc_rows = [row for row in rows if row["is_dc"] == "true"]

    assert len(rows) == 51
    assert len(state_rows) == 50
    assert len(dc_rows) == 1
    assert dc_rows[0]["state_abbr"] == "DC"


def test_ref_bls_laus_seed_maps_every_reporting_state_to_series():
    state_rows = _read_seed("ref_state.csv")
    series_rows = _read_seed("ref_bls_laus_state_series.csv")
    state_fips = {row["state_fips"] for row in state_rows}
    series_fips = {row["state_fips"] for row in series_rows}

    assert len(series_rows) == 51
    assert series_fips == state_fips
    assert all(
        re.fullmatch(r"LASST\d{15}", row["series_id"])
        for row in series_rows
    )


def test_bls_laus_config_and_seed_match():
    project_config = load_project_config(CONFIG_DIR)
    config_series = project_config.get("bls_laus_state_series.yml")["bls_laus"][
        "series"
    ]
    seed_series = _read_seed("ref_bls_laus_state_series.csv")
    config_pairs = {
        (row["state_fips"], row["series_id"])
        for row in config_series
    }
    seed_pairs = {
        (row["state_fips"], row["series_id"])
        for row in seed_series
    }

    assert config_pairs == seed_pairs


def test_ref_naics_seed_has_current_sector_rows():
    rows = _read_seed("ref_naics.csv")
    sector_codes = {row["naics_sector_code"] for row in rows}

    assert "11" in sector_codes
    assert "31-33" in sector_codes
    assert "92" in sector_codes
    assert len(rows) >= 20
