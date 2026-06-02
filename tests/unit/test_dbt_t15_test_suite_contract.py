from pathlib import Path

from tests.unit.dbt_schema_test_helpers import (
    column,
    dbt_test_names,
    models_by_name,
    schema_models,
)


SCHEMA_FILES = [
    Path("dbt/models/staging/schema.yml"),
    Path("dbt/models/marts/schema.yml"),
    Path("dbt/models/marts/lending/schema.yml"),
    Path("dbt/models/marts/context/schema.yml"),
    Path("dbt/models/marts/pipeline/schema.yml"),
    Path("dbt/models/bi/schema.yml"),
]

MODELS_WITH_STATE_KEYS = {
    "mart_lending_monthly_state",
    "mart_lending_annual_state",
    "mart_lending_lender_state_period",
    "mart_lending_concentration_state_period",
    "mart_lending_industry_state_period",
    "mart_lending_program_state_period",
    "mart_laus_monthly_state",
    "mart_laus_annual_state",
    "mart_business_dynamics_annual_state",
    "mart_regional_business_health_annual_state",
    "bi_executive_overview",
    "bi_state_lending_trends",
    "bi_lender_concentration",
    "bi_industry_mix",
    "bi_program_mix",
    "bi_regional_business_health",
}


def test_all_documented_dbt_models_declare_grain():
    """Validate that all documented dbt models declare grain."""
    missing_grain = []

    for schema_file in SCHEMA_FILES:
        for model in schema_models(schema_file):
            if not model.get("meta", {}).get("grain"):
                missing_grain.append(model["name"])

    assert missing_grain == []


def test_state_key_models_have_dim_state_relationship_tests():
    """Validate that state key models have dim state relationship tests."""
    schemas = models_by_name(SCHEMA_FILES)

    missing_relationships = []
    for model_name in MODELS_WITH_STATE_KEYS:
        state_key = column(schemas[model_name], "state_key")
        if "relationships" not in dbt_test_names(state_key.get("data_tests", [])):
            missing_relationships.append(model_name)

    assert missing_relationships == []


def test_t15_singular_reconciliation_tests_exist():
    """Validate that t15 singular reconciliation tests exist."""
    singular_tests = {path.name for path in Path("dbt/tests").glob("assert_*.sql")}

    assert {
        "assert_fact_sba_loans_latest_sources.sql",
        "assert_fact_laus_state_month_latest_sources.sql",
        "assert_fact_bds_state_year_latest_sources.sql",
        "assert_staging_sources_latest_snapshots.sql",
        "assert_mart_lending_annual_state_reconciles.sql",
        "assert_mart_lending_lender_state_period_reconciles.sql",
        "assert_mart_lending_industry_state_period_reconciles.sql",
        "assert_mart_lending_program_state_period_reconciles.sql",
        "assert_mart_lending_top_lender_share_ordering.sql",
    } <= singular_tests
