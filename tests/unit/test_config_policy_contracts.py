import pytest

from pipelines.utils.config import load_project_config
from pipelines.utils.source_config_models import (
    FRESHNESS_RULES_CONFIG_FILE,
    RAW_VALIDATION_EXPECTATIONS_CONFIG_FILE,
)
from pipelines.utils.source_resources import (
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_KEY,
)
from tests.unit.config_test_helpers import CONFIG_DIR, mutate_config_file


def test_freshness_rules_declare_active_age_thresholds():
    """Validate dated age controls independently from publication cadence."""
    project_config = load_project_config(CONFIG_DIR)

    for name, rule in project_config.freshness_rules.items():
        expected = {
            "expected_cadence",
            "max_extract_age_days",
            "max_observation_age_days",
        }
        expected.add("max_release_check_age_days")
        assert rule["max_observation_age_days"] is None
        assert rule["max_release_check_age_days"] > 0
        assert set(rule) == expected
        assert rule["max_extract_age_days"] > 0


def test_sba_raw_validation_expectations_only_declare_active_controls():
    """Validate that SBA raw validation expectations only declare active controls."""
    project_config = load_project_config(CONFIG_DIR)

    assert set(project_config.raw_validation_expectations[SBA_FOIA_SOURCE_KEY]) == {
        "required_programs",
    }


def test_census_raw_validation_expectations_only_declare_active_controls():
    """Validate that census raw validation expectations only declare active controls."""
    project_config = load_project_config(CONFIG_DIR)

    assert set(project_config.raw_validation_expectations[CENSUS_BDS_SOURCE_KEY]) == {
        "expected_state_count",
        "required_variables",
    }


def test_bls_raw_validation_expectations_only_declare_active_controls():
    """Validate that BLS raw validation expectations only declare active controls."""
    project_config = load_project_config(CONFIG_DIR)

    assert set(project_config.raw_validation_expectations[BLS_LAUS_SOURCE_KEY]) == {
        "required_period_pattern",
        "unemployment_rate_min",
        "unemployment_rate_max",
    }


def test_enabled_sources_have_freshness_and_validation_config():
    """Validate that enabled sources have freshness and validation config."""
    project_config = load_project_config(CONFIG_DIR)
    enabled_source_names = {
        source_name
        for source_name, source_config in project_config.sources.items()
        if source_config.enabled
    }

    assert enabled_source_names <= set(project_config.freshness_rules)
    assert enabled_source_names <= set(project_config.raw_validation_expectations)


def test_project_config_rejects_unknown_policy_source(tmp_path):
    """Validate that project config rejects unknown policy source."""

    def add_unknown_source(config: dict) -> None:
        """Add unknown source for tests."""
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
    """Validate that project config rejects enabled source missing freshness rule."""

    def remove_sba_freshness_rule(config: dict) -> None:
        """Remove SBA freshness rule for tests."""
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
    """Validate that project config rejects enabled source missing validation expectations."""

    def remove_bls_validation_expectations(config: dict) -> None:
        """Remove BLS validation expectations for tests."""
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
    """Validate that project config rejects cadence drift."""

    def change_bls_cadence(config: dict) -> None:
        """Change BLS cadence for tests."""
        config["freshness_rules"][BLS_LAUS_SOURCE_KEY]["expected_cadence"] = "annual"

    config_dir = mutate_config_file(
        tmp_path,
        FRESHNESS_RULES_CONFIG_FILE,
        change_bls_cadence,
    )

    with pytest.raises(ValueError, match="refresh_cadence"):
        load_project_config(config_dir)


def test_project_config_rejects_census_validation_variables_not_requested(tmp_path):
    """Validate that project config rejects census validation variables not requested."""

    def add_not_requested_census_variable(config: dict) -> None:
        """Add not requested census variable for tests."""
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
    """Validate that project config rejects SBA validation programs not configured."""

    def add_unknown_sba_program(config: dict) -> None:
        """Add unknown SBA program for tests."""
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
    """Validate that project config rejects BLS validation rate bounds drift."""

    def change_bls_min_rate(config: dict) -> None:
        """Change BLS min rate for tests."""
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
