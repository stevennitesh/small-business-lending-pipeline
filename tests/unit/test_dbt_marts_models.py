from pathlib import Path

import yaml

from tests.unit.dbt_schema_test_helpers import column, dbt_test_names, models_by_name


DIMENSION_MODELS = {
    "dim_date": Path("dbt/models/marts/dimensions/dim_date.sql"),
    "dim_state": Path("dbt/models/marts/dimensions/dim_state.sql"),
    "dim_naics": Path("dbt/models/marts/dimensions/dim_naics.sql"),
    "dim_lender": Path("dbt/models/marts/dimensions/dim_lender.sql"),
    "dim_loan_program": Path(
        "dbt/models/marts/dimensions/dim_loan_program.sql"
    ),
    "dim_source_file": Path("dbt/models/marts/dimensions/dim_source_file.sql"),
}

FACT_MODELS = {
    "fact_sba_loans": Path("dbt/models/marts/facts/fact_sba_loans.sql"),
    "fact_laus_state_month": Path(
        "dbt/models/marts/facts/fact_laus_state_month.sql"
    ),
    "fact_bds_state_year": Path("dbt/models/marts/facts/fact_bds_state_year.sql"),
}

FACT_SOURCE_FILE_KEY_EXPRESSIONS = {
    "fact_sba_loans": '{{ generate_surrogate_key(["raw_uri"]) }}',
    "fact_laus_state_month": '{{ generate_surrogate_key(["laus.raw_uri"]) }}',
    "fact_bds_state_year": '{{ generate_surrogate_key(["bds.raw_uri"]) }}',
}

SEED_SCHEMA = Path("dbt/seeds/schema.yml")
MARTS_SCHEMA = Path("dbt/models/marts/schema.yml")
LOAN_STATUS_SEED = Path("dbt/seeds/ref_loan_status_group.csv")


def test_required_mart_models_exist():
    required_paths = [*DIMENSION_MODELS.values(), *FACT_MODELS.values()]
    missing_paths = [str(path) for path in required_paths if not path.is_file()]

    assert missing_paths == []


def test_mart_schema_declares_keys_relationships_and_unknown_rows():
    models = models_by_name([MARTS_SCHEMA])

    assert set(DIMENSION_MODELS) <= set(models)
    assert set(FACT_MODELS) <= set(models)

    for model_name in DIMENSION_MODELS:
        key_column = next(
            column
            for column in models[model_name]["columns"]
            if column["name"].endswith("_key")
        )
        assert {"not_null", "unique"} <= dbt_test_names(key_column["data_tests"])

    for model_name in FACT_MODELS:
        key_column = next(
            column
            for column in models[model_name]["columns"]
            if column["name"].endswith("_key")
        )
        assert {"not_null", "unique"} <= dbt_test_names(key_column["data_tests"])

    fact_sba = models["fact_sba_loans"]
    assert fact_sba["meta"]["expose_to_powerbi"] is False
    assert "relationships" in dbt_test_names(
        column(fact_sba, "source_file_key")["data_tests"]
    )
    assert "relationships" in dbt_test_names(
        column(fact_sba, "lender_key")["data_tests"]
    )
    assert "relationships" in dbt_test_names(
        column(fact_sba, "naics_key")["data_tests"]
    )
    assert "relationships" in dbt_test_names(
        column(fact_sba, "loan_program_key")["data_tests"]
    )
    assert "approval date is available" in column(
        fact_sba, "approval_year"
    )["description"]

    singular_tests = {
        path.name
        for path in Path("dbt/tests").glob("*.sql")
    }
    assert {
        "assert_unknown_lender_exists.sql",
        "assert_unknown_naics_exists.sql",
        "assert_fact_sba_loans_latest_sources.sql",
        "assert_fact_laus_state_month_latest_sources.sql",
        "assert_fact_bds_state_year_latest_sources.sql",
    } <= singular_tests

    dim_source_file = models["dim_source_file"]
    dim_source_file_columns = {
        column["name"]: column for column in dim_source_file["columns"]
    }
    assert "raw_uri" in dim_source_file_columns
    assert "storage_backend" in dim_source_file_columns
    assert "pipeline_run_id" in dim_source_file_columns
    assert "source_resource_name" in dim_source_file_columns
    assert "route-neutral raw_uri" in dim_source_file_columns[
        "source_file_key"
    ]["description"]
    assert "route-neutral raw artifact identity" in dim_source_file_columns[
        "raw_uri"
    ]["description"].lower()
    assert "not used as mart identity" in dim_source_file_columns[
        "raw_file_path"
    ]["description"]


def test_source_file_dimension_uses_raw_uri_as_identity():
    model_sql = DIMENSION_MODELS["dim_source_file"].read_text(encoding="utf-8")

    assert '{{ generate_surrogate_key(["raw_uri"]) }} as source_file_key' in model_sql
    assert "sha256_checksum" in model_sql


def test_dim_date_uses_year_month_label_macro_for_dialect_formatting():
    model_sql = DIMENSION_MODELS["dim_date"].read_text(encoding="utf-8")
    macro_sql = Path("dbt/macros/date_compat.sql").read_text(encoding="utf-8")

    assert "{{ year_month_label('date_day') }} as year_month" in model_sql
    assert "target.type == 'snowflake'" not in model_sql
    assert "macro year_month_label(date_expression)" in macro_sql
    assert "to_char({{ date_expression }}, 'YYYY-MM')" in macro_sql
    assert "strftime({{ date_expression }}, '%Y-%m')" in macro_sql


def test_fact_models_generate_source_file_key_from_raw_uri():
    for model_name, model_path in FACT_MODELS.items():
        model_sql = model_path.read_text(encoding="utf-8")
        expected_expression = FACT_SOURCE_FILE_KEY_EXPRESSIONS[model_name]
        expected_source_file_key = (
            f"else {expected_expression}\n    end as source_file_key"
        )

        assert expected_source_file_key in model_sql, model_name
        assert "source_file.source_file_key" not in model_sql, model_name
        assert "ref('dim_source_file')" not in model_sql, model_name


def test_fact_source_file_keys_keep_relationship_tests():
    models = models_by_name([MARTS_SCHEMA])

    for model_name in FACT_MODELS:
        source_file_key = column(models[model_name], "source_file_key")
        data_tests = source_file_key["data_tests"]

        assert "not_null" in dbt_test_names(data_tests), model_name
        assert "relationships" in dbt_test_names(data_tests), model_name
        relationship_test = next(
            test
            for test in data_tests
            if isinstance(test, dict) and "relationships" in test
        )
        assert relationship_test["relationships"]["arguments"] == {
            "to": "ref('dim_source_file')",
            "field": "source_file_key",
        }


def test_fact_sba_loans_exposes_canonical_approval_year():
    model_sql = FACT_MODELS["fact_sba_loans"].read_text(encoding="utf-8")

    assert "approval_date," in model_sql
    assert "approval_fiscal_year" in model_sql
    assert "coalesce(" in model_sql
    assert "extract(year from approval_date)::integer" in model_sql
    assert ") as approval_year" in model_sql


def test_fact_sba_loans_generates_naics_key_without_dimension_lookup():
    model_sql = FACT_MODELS["fact_sba_loans"].read_text(encoding="utf-8")

    assert "ref('dim_naics')" not in model_sql
    assert "loans.naics_key," in model_sql
    assert "else 'UNKNOWN'\n        end as naics_key" in model_sql
    assert "'31', '32', '33'" in model_sql
    assert "'44', '45'" in model_sql
    assert "'48', '49'" in model_sql


def test_fact_sba_loans_exposes_extra_kpi_fields_and_status_group():
    model_sql = FACT_MODELS["fact_sba_loans"].read_text(encoding="utf-8")
    models = models_by_name([MARTS_SCHEMA])
    fact_sba = models["fact_sba_loans"]

    assert "ref('ref_loan_status_group')" in model_sql
    assert "loans.loan_status_key = status.loan_status_key" in model_sql
    assert "coalesce(status.loan_status_group, 'unmapped')" in model_sql

    expected_columns = {
        "loan_status",
        "loan_status_key",
        "loan_status_group",
        "loan_status_group_label",
        "is_credit_loss_status",
        "loan_status_sort_order",
        "paid_in_full_date",
        "chargeoff_date",
        "fixed_or_variable_interest_indicator",
        "third_party_dollars",
        "business_type",
        "business_age",
        "revolver_status",
        "collateral_indicator",
        "sold_secondary_market_indicator",
    }
    declared_columns = {column["name"] for column in fact_sba["columns"]}

    assert expected_columns <= declared_columns


def test_loan_status_group_seed_is_documented_and_conservative():
    seed_schema = yaml.safe_load(SEED_SCHEMA.read_text())
    seeds = {seed["name"]: seed for seed in seed_schema["seeds"]}
    seed_rows = LOAN_STATUS_SEED.read_text(encoding="utf-8").splitlines()
    header = seed_rows[0].split(",")
    rows = [dict(zip(header, row.split(","))) for row in seed_rows[1:]]
    status_keys = {row["loan_status_key"] for row in rows}
    credit_loss_statuses = {
        row["loan_status_key"]
        for row in rows
        if row["is_credit_loss_status"] == "true"
    }

    assert "ref_loan_status_group" in seeds
    assert {"not_null", "unique"} <= dbt_test_names(
        column(seeds["ref_loan_status_group"], "loan_status_key")["tests"]
    )
    assert {
        "PIF",
        "P I F",
        "CURR",
        "CANCLD",
        "CHGOFF",
        "CHARGED-OFF",
        "DELINQ",
        "PSTDUE",
        "CLSLN",
        "UNKNOWN",
    } <= status_keys
    assert credit_loss_statuses == {"CHGOFF", "CHARGED-OFF"}
