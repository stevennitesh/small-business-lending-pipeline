import re

import pytest

from pipelines.utils.config import (
    CONFIG_FILE_SECTIONS,
    CONFIG_FILENAMES,
    load_project_config,
)
from pipelines.utils.source_config_models import (
    FRESHNESS_RULES_CONFIG_FILE,
    RAW_VALIDATION_EXPECTATIONS_CONFIG_FILE,
    SOURCES_CONFIG_FILE,
    SOURCES_CONFIG_SECTION,
    load_yaml_file,
)
from pipelines.utils.source_resources import (
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_KEY,
)
from tests.unit.config_test_helpers import (
    CONFIG_DIR,
    config_path,
    mutate_config_file,
)


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
    assert project_config.raw_validation_expectations[CENSUS_BDS_SOURCE_KEY][
        "expected_state_count"
    ] == 51
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


def test_mvp_freshness_rules_only_declare_active_cadence_contracts():
    project_config = load_project_config(CONFIG_DIR)

    for rule in project_config.freshness_rules.values():
        assert set(rule) == {"expected_cadence"}


def test_sba_raw_validation_expectations_only_declare_active_controls():
    project_config = load_project_config(CONFIG_DIR)

    assert set(project_config.raw_validation_expectations[SBA_FOIA_SOURCE_KEY]) == {
        "required_programs",
    }


def test_census_raw_validation_expectations_only_declare_active_controls():
    project_config = load_project_config(CONFIG_DIR)

    assert set(project_config.raw_validation_expectations[CENSUS_BDS_SOURCE_KEY]) == {
        "expected_state_count",
        "required_variables",
    }


def test_enabled_sources_have_freshness_and_validation_config():
    project_config = load_project_config(CONFIG_DIR)
    enabled_source_names = {
        source_name
        for source_name, source_config in project_config.sources.items()
        if source_config.enabled
    }

    assert enabled_source_names <= set(project_config.freshness_rules)
    assert enabled_source_names <= set(project_config.raw_validation_expectations)


def test_project_config_rejects_unknown_policy_source(tmp_path):
    def add_unknown_source(config: dict) -> None:
        config["raw_validation_expectations"]["unknown_source"] = {
            "expected_state_count": 1
        }

    config_dir = mutate_config_file(
        tmp_path,
        RAW_VALIDATION_EXPECTATIONS_CONFIG_FILE,
        add_unknown_source,
    )

    with pytest.raises(ValueError, match="unknown source keys: unknown_source"):
        load_project_config(config_dir)


def test_project_config_rejects_enabled_source_missing_freshness_rule(tmp_path):
    def remove_sba_freshness_rule(config: dict) -> None:
        del config["freshness_rules"][SBA_FOIA_SOURCE_KEY]

    config_dir = mutate_config_file(
        tmp_path,
        FRESHNESS_RULES_CONFIG_FILE,
        remove_sba_freshness_rule,
    )

    with pytest.raises(ValueError, match="missing freshness rules: sba_foia"):
        load_project_config(config_dir)


def test_project_config_rejects_enabled_source_missing_validation_expectations(
    tmp_path,
):
    def remove_bls_validation_expectations(config: dict) -> None:
        del config["raw_validation_expectations"][BLS_LAUS_SOURCE_KEY]

    config_dir = mutate_config_file(
        tmp_path,
        RAW_VALIDATION_EXPECTATIONS_CONFIG_FILE,
        remove_bls_validation_expectations,
    )

    with pytest.raises(
        ValueError,
        match="missing raw validation expectations: bls_laus",
    ):
        load_project_config(config_dir)


def test_project_config_rejects_cadence_drift(tmp_path):
    def change_bls_cadence(config: dict) -> None:
        config["freshness_rules"][BLS_LAUS_SOURCE_KEY][
            "expected_cadence"
        ] = "annual"

    config_dir = mutate_config_file(
        tmp_path,
        FRESHNESS_RULES_CONFIG_FILE,
        change_bls_cadence,
    )

    with pytest.raises(ValueError, match="refresh_cadence"):
        load_project_config(config_dir)


def test_project_config_rejects_census_validation_variables_not_requested(tmp_path):
    def add_not_requested_census_variable(config: dict) -> None:
        config["raw_validation_expectations"][CENSUS_BDS_SOURCE_KEY][
            "required_variables"
        ].append("NOT_REQUESTED")

    config_dir = mutate_config_file(
        tmp_path,
        RAW_VALIDATION_EXPECTATIONS_CONFIG_FILE,
        add_not_requested_census_variable,
    )

    with pytest.raises(ValueError, match="not requested variables: NOT_REQUESTED"):
        load_project_config(config_dir)


def test_project_config_rejects_sba_validation_programs_not_configured(tmp_path):
    def add_unknown_sba_program(config: dict) -> None:
        config["raw_validation_expectations"][SBA_FOIA_SOURCE_KEY][
            "required_programs"
        ].append("UNKNOWN")

    config_dir = mutate_config_file(
        tmp_path,
        RAW_VALIDATION_EXPECTATIONS_CONFIG_FILE,
        add_unknown_sba_program,
    )

    with pytest.raises(ValueError, match="not configured resources: UNKNOWN"):
        load_project_config(config_dir)


def test_project_config_rejects_bls_validation_rate_bounds_drift(tmp_path):
    def change_bls_min_rate(config: dict) -> None:
        config["raw_validation_expectations"][BLS_LAUS_SOURCE_KEY][
            "unemployment_rate_min"
        ] = 101

    config_dir = mutate_config_file(
        tmp_path,
        RAW_VALIDATION_EXPECTATIONS_CONFIG_FILE,
        change_bls_min_rate,
    )

    with pytest.raises(ValueError, match="unemployment_rate_min cannot exceed"):
        load_project_config(config_dir)


def test_bls_raw_validation_expectations_only_declare_active_controls():
    project_config = load_project_config(CONFIG_DIR)

    assert set(project_config.raw_validation_expectations[BLS_LAUS_SOURCE_KEY]) == {
        "required_period_pattern",
        "unemployment_rate_min",
        "unemployment_rate_max",
    }


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
