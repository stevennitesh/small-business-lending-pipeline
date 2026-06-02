import re

from pipelines.utils.config import (
    CONFIG_FILE_SECTIONS,
    CONFIG_FILENAMES,
    load_project_config,
)
from pipelines.utils.source_config_models import (
    SOURCES_CONFIG_FILE,
    SOURCES_CONFIG_SECTION,
    load_yaml_file,
)
from pipelines.utils.source_resources import (
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_KEY,
)
from tests.unit.config_test_helpers import CONFIG_DIR, config_path


def test_all_config_files_parse():
    for filename in CONFIG_FILENAMES:
        config = load_yaml_file(config_path(filename))
        assert config


def test_project_config_loader_returns_named_configs():
    project_config = load_project_config(CONFIG_DIR)

    assert set(project_config.files) == set(CONFIG_FILENAMES)
    assert project_config.sources[SBA_FOIA_SOURCE_KEY].enabled is True
    assert project_config.sources[SBA_FOIA_SOURCE_KEY].dataset_name == "7a_504_foia"
    assert project_config.sba.dataset_name == "7a_504_foia"
    assert project_config.census_bds.start_year == 1990
    assert project_config.bls_laus.start_year == 1990
    assert project_config.bls_laus.measure_name == "unemployment_rate"
    assert (
        project_config.freshness_rules[SBA_FOIA_SOURCE_KEY]["expected_cadence"]
        == "quarterly"
    )
    assert (
        project_config.raw_validation_expectations[CENSUS_BDS_SOURCE_KEY][
            "expected_state_count"
        ]
        == 51
    )
    assert project_config.source_identity(BLS_LAUS_SOURCE_KEY).source_system == "bls"
    assert project_config.source_identity(BLS_LAUS_SOURCE_KEY).dataset_name == "laus"


def test_config_files_have_required_top_level_keys():
    project_config = load_project_config(CONFIG_DIR)

    for filename, section_name in CONFIG_FILE_SECTIONS.items():
        assert section_name in project_config.get(filename)


def test_mvp_source_registry_does_not_declare_unused_path_overrides():
    project_config = load_project_config(CONFIG_DIR)
    raw_sources = project_config.get(SOURCES_CONFIG_FILE)[SOURCES_CONFIG_SECTION]

    for source_config in raw_sources.values():
        assert "raw_storage_subdir" not in source_config
        assert "manifest_subdir" not in source_config
        assert "validation_subdir" not in source_config


def test_census_bds_required_variables_are_declared():
    project_config = load_project_config(CONFIG_DIR)

    assert {
        "YEAR",
        "NAME",
        "state",
        "ESTAB",
        "ESTABS_ENTRY",
        "ESTABS_EXIT",
    } <= set(project_config.census_bds.required_variables)


def test_bls_laus_config_maps_50_states_plus_dc():
    project_config = load_project_config(CONFIG_DIR)
    state_fips = {series.state_fips for series in project_config.bls_laus.series}
    series_ids = {series.series_id for series in project_config.bls_laus.series}

    assert len(project_config.bls_laus.series) == 51
    assert "11" in state_fips
    assert len(series_ids) == 51
    assert all(re.fullmatch(r"LASST\d{15}", series_id) for series_id in series_ids)
