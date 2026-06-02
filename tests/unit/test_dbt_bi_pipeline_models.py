from pathlib import Path

import yaml

from pipelines.powerbi.export_schema import BI_EXPORT_TABLES
from tests.unit.dbt_schema_test_helpers import (
    dbt_test_name,
    dbt_test_names,
    dbt_test_tags,
    find_dbt_test,
    models_by_name,
)


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
    "bi_lending_performance": Path("dbt/models/bi/bi_lending_performance.sql"),
    "bi_lending_status_mix": Path("dbt/models/bi/bi_lending_status_mix.sql"),
    "bi_lending_terms_pricing": Path("dbt/models/bi/bi_lending_terms_pricing.sql"),
    "bi_lending_jobs_impact": Path("dbt/models/bi/bi_lending_jobs_impact.sql"),
    "bi_state_filter": Path("dbt/models/bi/bi_state_filter.sql"),
    "bi_year_filter": Path("dbt/models/bi/bi_year_filter.sql"),
    "bi_loan_program_filter": Path("dbt/models/bi/bi_loan_program_filter.sql"),
    "bi_naics_filter": Path("dbt/models/bi/bi_naics_filter.sql"),
    "bi_lender_filter": Path("dbt/models/bi/bi_lender_filter.sql"),
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
BI_SCHEMA = Path("dbt/models/bi/schema.yml")
PIPELINE_SCHEMA = Path("dbt/models/marts/pipeline/schema.yml")


def test_required_bi_and_pipeline_models_exist():
    required_paths = [*BI_MODELS.values(), *PIPELINE_MARTS.values()]
    missing_paths = [str(path) for path in required_paths if not path.is_file()]

    assert missing_paths == []
    assert set(BI_MODELS) == set(BI_EXPORT_TABLES)


def test_bi_schema_declares_grain_rows_and_safe_columns():
    schema_text = BI_SCHEMA.read_text()
    assert "Deprecated compatibility field" not in schema_text
    schema_yml = yaml.safe_load(schema_text)
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
        "bi_lender_concentration": {
            "top_1_lender_share",
            "top_5_lender_share",
            "lender_count",
        },
        "bi_industry_mix": {"industry_approved_amount_share"},
        "bi_program_mix": {"program_approved_amount_share"},
        "bi_regional_business_health": {
            "annual_average_unemployment_rate",
            "unemployment_rate_yoy_change_pct",
            "establishment_count",
            "establishment_entry_rate",
            "establishment_exit_rate",
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
        "bi_lending_performance": {
            "gross_chargeoff_amount",
            "charged_off_loan_count",
            "chargeoff_amount_rate",
            "charged_off_loan_count_rate",
        },
        "bi_lending_status_mix": {
            "loan_status_group",
            "loan_status_group_label",
            "status_group_approved_amount_share",
            "status_group_loan_count_share",
        },
        "bi_lending_terms_pricing": {
            "term_coverage_rate",
            "average_initial_interest_rate",
            "fixed_interest_loan_share",
            "variable_interest_loan_share",
            "seven_a_sba_guarantee_rate",
            "third_party_dollars",
        },
        "bi_lending_jobs_impact": {
            "jobs_supported_coverage_rate",
            "total_jobs_supported",
            "jobs_supported_per_loan",
            "jobs_supported_per_1m_approved",
            "approved_loan_dollars_per_job_supported",
        },
        "bi_state_filter": {
            "state_key",
            "state_name",
            "census_region",
            "census_division",
        },
        "bi_year_filter": {
            "year",
            "year_label",
        },
        "bi_loan_program_filter": {
            "loan_program_key",
            "loan_program_name",
        },
        "bi_naics_filter": {
            "naics_key",
            "naics_sector_name",
            "is_unknown",
        },
        "bi_lender_filter": {
            "lender_key",
            "lender_name",
            "is_unknown",
        },
    }

    for model_name, model in models.items():
        assert model["meta"]["grain"]
        assert "not_empty" in dbt_test_names(model["data_tests"])

        column_names = {column["name"] for column in model["columns"]}
        assert not (PROHIBITED_BI_FIELDS & column_names)
        assert required_columns[model_name] <= column_names


def test_bi_schema_marks_fast_quality_tests_critical():
    models = models_by_name([BI_SCHEMA])

    for model_name, model in models.items():
        not_empty_test = find_dbt_test(model["data_tests"], "not_empty")
        assert "critical" in dbt_test_tags(not_empty_test), model_name

        grain_tests = [
            test
            for test in model["data_tests"]
            if dbt_test_name(test) == "unique_combination_of_columns"
        ]
        assert len(grain_tests) <= 1, model_name
        for grain_test in grain_tests:
            assert "critical" in dbt_test_tags(grain_test), model_name


def test_pipeline_schema_declares_health_columns():
    models = models_by_name([PIPELINE_SCHEMA])

    assert set(PIPELINE_MARTS) <= set(models)

    expected = {
        "mart_pipeline_source_freshness": {
            "freshness_status",
            "is_latest_successful_snapshot",
            "latest_row_count",
            "observed_snapshot_count",
        },
        "mart_pipeline_validation_summary": {
            "validation_status",
            "failed_check_count",
            "warning_check_count",
            "passed_check_count",
        },
        "mart_pipeline_run_summary": {
            "latest_run_status",
            "loaded_at_utc",
            "validation_status",
            "failed_check_count",
            "warning_check_count",
            "passed_check_count",
            "source_resource_count",
            "current_source_resource_count",
            "stale_or_unknown_source_resource_count",
        },
    }
    for model_name, expected_columns in expected.items():
        model = models[model_name]
        column_names = {column["name"] for column in model["columns"]}
        assert model["meta"]["grain"]
        assert "not_empty" in dbt_test_names(model["data_tests"])
        assert expected_columns <= column_names


def test_pipeline_run_summary_mart_uses_staging_contract():
    model_sql = PIPELINE_MARTS["mart_pipeline_run_summary"].read_text(
        encoding="utf-8"
    )

    assert "ref('stg_pipeline_run_summary')" in model_sql
    assert "source('raw', 'raw_pipeline_run_summary')" not in model_sql


def test_pipeline_source_freshness_uses_latest_manifest_row_values():
    model_sql = PIPELINE_MARTS["mart_pipeline_source_freshness"].read_text(
        encoding="utf-8"
    )

    assert "row_number() over" in model_sql
    assert "resource_snapshot_rank = 1" in model_sql
    assert "row_count as latest_row_count" in model_sql
    assert "max(row_count)" not in model_sql


def test_bi_lender_outputs_document_known_lender_semantics():
    models = models_by_name([BI_SCHEMA])
    lender_mix_sql = BI_MODELS["bi_lender_mix"].read_text(encoding="utf-8")

    concentration = models["bi_lender_concentration"]
    concentration_columns = {
        column["name"]: column for column in concentration["columns"]
    }
    lender_mix = models["bi_lender_mix"]
    lender_mix_columns = {column["name"]: column for column in lender_mix["columns"]}

    assert "known-lender concentration" in concentration["description"]
    assert "known-lender approved dollars" in concentration_columns[
        "top_1_lender_share"
    ]["description"]
    assert "known-lender approved dollars" in concentration_columns[
        "top_5_lender_share"
    ]["description"]
    assert "Known lender count" in concentration_columns["lender_count"][
        "description"
    ]
    assert "known-lender lending mix" in lender_mix["description"]
    assert "known-lender approved dollars" in lender_mix_columns[
        "lender_approved_amount_share"
    ]["description"]
    assert "where lender_key != 'UNKNOWN'" in lender_mix_sql


def test_bi_filter_tables_are_built_from_dbt_models():
    year_sql = BI_MODELS["bi_year_filter"].read_text(encoding="utf-8")
    program_sql = BI_MODELS["bi_loan_program_filter"].read_text(encoding="utf-8")
    naics_sql = BI_MODELS["bi_naics_filter"].read_text(encoding="utf-8")
    lender_sql = BI_MODELS["bi_lender_filter"].read_text(encoding="utf-8")

    for year_source in (
        "bi_executive_overview",
        "bi_state_lending_trends",
        "bi_lender_concentration",
        "bi_industry_mix",
        "bi_program_mix",
        "bi_regional_business_health",
        "bi_lender_mix",
        "bi_lending_performance",
        "bi_lending_status_mix",
        "bi_lending_terms_pricing",
        "bi_lending_jobs_impact",
    ):
        assert f"ref('{year_source}')" in year_sql
    assert "where year is not null" in year_sql
    assert "ref('dim_loan_program')" in program_sql
    assert "ref('dim_naics')" in naics_sql
    assert "ref('dim_lender')" in lender_sql
    assert "where not is_unknown" in lender_sql
