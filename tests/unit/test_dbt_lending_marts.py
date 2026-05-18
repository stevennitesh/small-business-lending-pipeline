from pathlib import Path

import yaml


LENDING_MARTS = {
    "mart_lending_monthly_state": Path(
        "dbt/models/marts/lending/mart_lending_monthly_state.sql"
    ),
    "mart_lending_annual_state": Path(
        "dbt/models/marts/lending/mart_lending_annual_state.sql"
    ),
    "mart_lending_lender_state_period": Path(
        "dbt/models/marts/lending/mart_lending_lender_state_period.sql"
    ),
    "mart_lending_concentration_state_period": Path(
        "dbt/models/marts/lending/mart_lending_concentration_state_period.sql"
    ),
    "mart_lending_industry_state_period": Path(
        "dbt/models/marts/lending/mart_lending_industry_state_period.sql"
    ),
    "mart_lending_program_state_period": Path(
        "dbt/models/marts/lending/mart_lending_program_state_period.sql"
    ),
}


def test_required_lending_marts_exist():
    missing_paths = [str(path) for path in LENDING_MARTS.values() if not path.is_file()]

    assert missing_paths == []


def test_lending_schema_declares_grains_and_kpi_tests():
    schema_yml = yaml.safe_load(Path("dbt/models/marts/lending/schema.yml").read_text())
    models = {model["name"]: model for model in schema_yml["models"]}

    assert set(LENDING_MARTS) <= set(models)

    for model_name, model in models.items():
        assert model["meta"]["grain"]
        assert any("unique_combination_of_columns" in test for test in model["data_tests"])

        columns = {column["name"]: column for column in model["columns"]}
        if "loan_count" in columns:
            assert "non_negative" in _test_names(columns["loan_count"]["data_tests"])
        if "total_approved_loan_amount" in columns:
            assert "non_negative" in _test_names(
                columns["total_approved_loan_amount"]["data_tests"]
            )

    share_columns = {
        "mart_lending_lender_state_period": "lender_approved_amount_share",
        "mart_lending_concentration_state_period": "top_5_lender_share",
        "mart_lending_industry_state_period": "industry_approved_amount_share",
        "mart_lending_program_state_period": "program_approved_amount_share",
    }
    for model_name, share_column in share_columns.items():
        columns = {column["name"]: column for column in models[model_name]["columns"]}
        assert "accepted_range" in _test_names(columns[share_column]["data_tests"])

    singular_tests = {path.name for path in Path("dbt/tests").glob("*.sql")}
    assert {
        "assert_mart_lending_annual_state_reconciles.sql",
        "assert_mart_lending_lender_state_period_reconciles.sql",
        "assert_mart_lending_industry_state_period_reconciles.sql",
        "assert_mart_lending_program_state_period_reconciles.sql",
        "assert_bi_lender_mix_excludes_unknown.sql",
    } <= singular_tests


def test_state_lending_marts_exclude_unmapped_project_states():
    for model_name in (
        "mart_lending_monthly_state",
        "mart_lending_annual_state",
        "mart_lending_lender_state_period",
        "mart_lending_industry_state_period",
        "mart_lending_program_state_period",
    ):
        model_sql = LENDING_MARTS[model_name].read_text(encoding="utf-8")

        assert "project_state_key is not null" in model_sql


def test_annual_lending_marts_reuse_fact_approval_year():
    annual_mart_paths = [
        LENDING_MARTS["mart_lending_annual_state"],
        LENDING_MARTS["mart_lending_lender_state_period"],
        LENDING_MARTS["mart_lending_industry_state_period"],
        LENDING_MARTS["mart_lending_program_state_period"],
    ]

    for model_path in annual_mart_paths:
        model_sql = model_path.read_text(encoding="utf-8")

        assert "coalesce(extract(year from" not in model_sql
        assert "approval_year is not null" in model_sql

    reconciliation_sql = Path(
        "dbt/tests/assert_mart_lending_annual_state_reconciles.sql"
    ).read_text(encoding="utf-8")
    assert "coalesce(extract(year from" not in reconciliation_sql
    assert "approval_year is not null" in reconciliation_sql


def _test_names(data_tests: list) -> set[str]:
    names = set()
    for test in data_tests:
        if isinstance(test, str):
            names.add(test)
        else:
            names.update(test)
    return names
