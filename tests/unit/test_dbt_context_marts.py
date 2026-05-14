from pathlib import Path

import yaml


CONTEXT_MARTS = {
    "mart_laus_monthly_state": Path(
        "dbt/models/marts/context/mart_laus_monthly_state.sql"
    ),
    "mart_laus_annual_state": Path(
        "dbt/models/marts/context/mart_laus_annual_state.sql"
    ),
    "mart_business_dynamics_annual_state": Path(
        "dbt/models/marts/context/mart_business_dynamics_annual_state.sql"
    ),
    "mart_regional_business_health_annual_state": Path(
        "dbt/models/marts/context/mart_regional_business_health_annual_state.sql"
    ),
}


def test_required_context_marts_exist():
    missing_paths = [str(path) for path in CONTEXT_MARTS.values() if not path.is_file()]

    assert missing_paths == []


def test_context_schema_declares_grains_kpis_and_context_tests():
    schema_yml = yaml.safe_load(Path("dbt/models/marts/context/schema.yml").read_text())
    models = {model["name"]: model for model in schema_yml["models"]}

    assert set(CONTEXT_MARTS) <= set(models)

    expected_grains = {
        "mart_laus_monthly_state": ["state_key", "observed_month"],
        "mart_laus_annual_state": ["state_key", "year"],
        "mart_business_dynamics_annual_state": ["state_key", "year"],
        "mart_regional_business_health_annual_state": ["state_key", "year"],
    }
    for model_name, grain_columns in expected_grains.items():
        model = models[model_name]
        assert model["meta"]["grain"]
        assert {
            "unique_combination_of_columns": {"arguments": {"combination_of_columns": grain_columns}}
        } in model["data_tests"]

    regional_columns = {
        column["name"]: column
        for column in models["mart_regional_business_health_annual_state"]["columns"]
    }
    assert {
        "annual_average_unemployment_rate",
        "establishment_count",
        "establishment_entry_rate",
        "establishment_exit_rate",
        "loans_per_1000_establishments",
        "approved_loan_dollars_per_establishment",
        "context_join_status",
    } <= set(regional_columns)

    singular_tests = {path.name for path in Path("dbt/tests").glob("*.sql")}
    assert {
        "assert_safe_divide_null_denominator.sql",
        "assert_regional_business_health_context_flags.sql",
        "assert_bi_context_rates_decimal.sql",
        "assert_bi_regional_business_health_complete_context.sql",
    } <= singular_tests
