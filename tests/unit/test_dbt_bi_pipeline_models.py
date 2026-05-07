from pathlib import Path

import yaml


BI_MODELS = {
    "bi_executive_overview": Path("dbt/models/bi/bi_executive_overview.sql"),
    "bi_state_lending_trends": Path("dbt/models/bi/bi_state_lending_trends.sql"),
    "bi_lender_concentration": Path("dbt/models/bi/bi_lender_concentration.sql"),
    "bi_industry_mix": Path("dbt/models/bi/bi_industry_mix.sql"),
    "bi_program_mix": Path("dbt/models/bi/bi_program_mix.sql"),
    "bi_regional_business_health": Path(
        "dbt/models/bi/bi_regional_business_health.sql"
    ),
    "bi_pipeline_health": Path("dbt/models/bi/bi_pipeline_health.sql"),
    "bi_lender_mix": Path("dbt/models/bi/bi_lender_mix.sql"),
    "bi_state_filter": Path("dbt/models/bi/bi_state_filter.sql"),
}

PIPELINE_MARTS = {
    "mart_pipeline_source_freshness": Path(
        "dbt/models/marts/pipeline/mart_pipeline_source_freshness.sql"
    ),
    "mart_pipeline_validation_summary": Path(
        "dbt/models/marts/pipeline/mart_pipeline_validation_summary.sql"
    ),
    "mart_pipeline_run_summary": Path(
        "dbt/models/marts/pipeline/mart_pipeline_run_summary.sql"
    ),
}

PROHIBITED_BI_FIELDS = {
    "borrower_name",
    "borrower_city",
    "borrower_zip",
    "raw_file_path",
    "source_loan_id",
}


def test_required_bi_and_pipeline_models_exist():
    required_paths = [*BI_MODELS.values(), *PIPELINE_MARTS.values()]
    missing_paths = [str(path) for path in required_paths if not path.is_file()]

    assert missing_paths == []


def test_bi_schema_declares_grain_rows_and_safe_columns():
    schema_yml = yaml.safe_load(Path("dbt/models/bi/schema.yml").read_text())
    models = {model["name"]: model for model in schema_yml["models"]}

    assert set(BI_MODELS) <= set(models)

    required_columns = {
        "bi_executive_overview": {
            "total_approved_loan_amount",
            "loan_count",
            "average_loan_size",
            "annual_average_unemployment_rate",
            "context_join_status",
        },
        "bi_state_lending_trends": {
            "total_approved_loan_amount",
            "loan_count",
            "approved_loan_amount_yoy_growth_pct",
        },
        "bi_lender_concentration": {"top_5_lender_share", "lender_count"},
        "bi_industry_mix": {"industry_approved_amount_share"},
        "bi_program_mix": {"program_approved_amount_share"},
        "bi_regional_business_health": {
            "loans_per_1000_establishments",
            "approved_loan_dollars_per_establishment",
            "context_join_status",
        },
        "bi_pipeline_health": {
            "latest_run_status",
            "validation_status",
            "freshness_status",
        },
        "bi_lender_mix": {
            "lender_key",
            "lender_name",
            "lender_approved_amount_share",
            "lender_rank",
        },
        "bi_state_filter": {
            "state_key",
            "state_name",
            "census_region",
            "census_division",
        },
    }

    for model_name, model in models.items():
        assert model["meta"]["grain"]
        assert "not_empty" in _test_names(model["data_tests"])

        column_names = {column["name"] for column in model["columns"]}
        assert not (PROHIBITED_BI_FIELDS & column_names)
        assert required_columns[model_name] <= column_names


def test_pipeline_schema_declares_health_columns():
    schema_yml = yaml.safe_load(Path("dbt/models/marts/pipeline/schema.yml").read_text())
    models = {model["name"]: model for model in schema_yml["models"]}

    assert set(PIPELINE_MARTS) <= set(models)

    expected = {
        "mart_pipeline_source_freshness": {
            "freshness_status",
            "is_latest_successful_snapshot",
        },
        "mart_pipeline_validation_summary": {
            "validation_status",
            "failed_check_count",
            "warning_check_count",
        },
        "mart_pipeline_run_summary": {
            "latest_run_status",
            "loaded_at_utc",
            "validation_status",
        },
    }
    for model_name, expected_columns in expected.items():
        model = models[model_name]
        column_names = {column["name"] for column in model["columns"]}
        assert model["meta"]["grain"]
        assert "not_empty" in _test_names(model["data_tests"])
        assert expected_columns <= column_names


def _test_names(data_tests: list) -> set[str]:
    names = set()
    for test in data_tests:
        if isinstance(test, str):
            names.add(test)
        else:
            names.update(test)
    return names
