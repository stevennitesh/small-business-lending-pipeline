import csv
import re
from pathlib import Path

from pipelines.utils.config import load_project_config
from pipelines.utils.source_config_models import (
    BLS_LAUS_CONFIG_FILE,
    BLS_LAUS_CONFIG_SECTION,
)
from tests.unit.config_test_helpers import CONFIG_DIR


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
    config_series = project_config.get(BLS_LAUS_CONFIG_FILE)[BLS_LAUS_CONFIG_SECTION][
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


def _read_seed(seed_name: str) -> list[dict[str, str]]:
    seed_path = Path("dbt/seeds", seed_name)
    with seed_path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))
