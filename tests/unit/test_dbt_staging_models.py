from pathlib import Path

from tests.unit.dbt_schema_test_helpers import dbt_test_names, models_by_name


STAGING_MODELS = {
    "stg_sba_7a_loans": Path("dbt/models/staging/sba/stg_sba_7a_loans.sql"),
    "stg_sba_504_loans": Path("dbt/models/staging/sba/stg_sba_504_loans.sql"),
    "stg_sba_loans": Path("dbt/models/staging/sba/stg_sba_loans.sql"),
    "stg_census_bds_state_year": Path(
        "dbt/models/staging/census/stg_census_bds_state_year.sql"
    ),
    "stg_bls_laus_state_month": Path(
        "dbt/models/staging/bls/stg_bls_laus_state_month.sql"
    ),
    "stg_ingestion_manifest": Path(
        "dbt/models/staging/audit/stg_ingestion_manifest.sql"
    ),
    "stg_validation_result": Path("dbt/models/staging/audit/stg_validation_result.sql"),
    "stg_pipeline_run_summary": Path(
        "dbt/models/staging/audit/stg_pipeline_run_summary.sql"
    ),
}


SOURCE_ROW_STAGING_MODELS = [
    "stg_sba_7a_loans",
    "stg_sba_504_loans",
    "stg_sba_loans",
    "stg_census_bds_state_year",
    "stg_bls_laus_state_month",
]

SOURCE_ROW_IDENTITY_COLUMNS = [
    "pipeline_run_id",
    "source_resource_name",
    "storage_backend",
    "raw_uri",
]

MANIFEST_IDENTITY_COLUMNS = [
    "pipeline_run_id",
    "source_system",
    "dataset_name",
    "resource_name",
    "storage_backend",
    "raw_uri",
]

SBA_STAGING_COLUMNS = [
    "loan_record_key",
    "loan_program",
    "source_program",
    "source_loan_id",
    "borrower_name",
    "borrower_city",
    "borrower_state_abbr",
    "borrower_state_fips",
    "borrower_state_match_status",
    "borrower_zip",
    "lender_name",
    "lender_fdic_number",
    "lender_ncua_number",
    "cdc_name",
    "cdc_state_abbr",
    "lender_state_abbr",
    "third_party_dollars",
    "project_county",
    "project_state_abbr",
    "project_state_fips",
    "project_state_match_status",
    "gross_approval_amount",
    "sba_guaranteed_approval_amount",
    "approval_date",
    "approval_fiscal_year",
    "first_disbursement_date",
    "processing_method",
    "subprogram",
    "initial_interest_rate",
    "fixed_or_variable_interest_indicator",
    "term_months",
    "naics_code",
    "naics_description",
    "franchise_code",
    "franchise_name",
    "sba_district_office",
    "congressional_district",
    "business_type",
    "business_age",
    "loan_status",
    "paid_in_full_date",
    "chargeoff_date",
    "gross_chargeoff_amount",
    "revolver_status",
    "jobs_supported",
    "collateral_indicator",
    "sold_secondary_market_indicator",
    "pipeline_run_id",
    "source_system",
    "source_dataset",
    "source_resource_name",
    "ingestion_date",
    "storage_backend",
    "raw_uri",
    "raw_file_path",
    "sha256_checksum",
    "raw_row_number",
]

STAGING_SCHEMA = Path("dbt/models/staging/schema.yml")


def test_required_staging_models_exist():
    missing_paths = [
        str(path) for path in STAGING_MODELS.values() if not path.is_file()
    ]

    assert missing_paths == []


def test_staging_schema_declares_issue_acceptance_tests():
    models = models_by_name([STAGING_SCHEMA])

    assert set(STAGING_MODELS) <= set(models)

    sba_loans = models["stg_sba_loans"]
    sba_columns = {column["name"]: column for column in sba_loans["columns"]}
    assert dbt_test_names(sba_columns["loan_record_key"]["data_tests"]) == {
        "not_null",
        "unique",
    }
    assert sba_columns["loan_program"]["data_tests"] == [
        {"accepted_values": {"arguments": {"values": ["7a", "504"]}}}
    ]
    assert sba_columns["gross_approval_amount"]["data_tests"] == ["non_negative"]

    bds = models["stg_census_bds_state_year"]
    assert bds["data_tests"] == [
        {
            "unique_combination_of_columns": {
                "arguments": {"combination_of_columns": ["state_fips", "year"]}
            }
        }
    ]

    laus = models["stg_bls_laus_state_month"]
    assert laus["data_tests"] == [
        {
            "unique_combination_of_columns": {
                "arguments": {
                    "combination_of_columns": [
                        "state_fips",
                        "observed_month",
                        "measure_name",
                    ]
                }
            }
        }
    ]
    laus_columns = {column["name"]: column for column in laus["columns"]}
    assert laus_columns["unemployment_rate"]["data_tests"] == [
        {"accepted_range": {"arguments": {"min_value": 0, "max_value": 1}}}
    ]

    pipeline_summary = models["stg_pipeline_run_summary"]
    pipeline_columns = {
        column["name"]: column for column in pipeline_summary["columns"]
    }
    assert pipeline_summary["data_tests"] == ["not_empty"]
    assert pipeline_columns["raw_table_count"]["data_tests"] == ["non_negative"]


def test_staging_schema_documents_and_tests_source_identity_contract():
    models = models_by_name([STAGING_SCHEMA])

    for model_name in SOURCE_ROW_STAGING_MODELS:
        columns = {column["name"]: column for column in models[model_name]["columns"]}
        for column_name in SOURCE_ROW_IDENTITY_COLUMNS:
            assert column_name in columns
            assert "not_null" in dbt_test_names(columns[column_name]["data_tests"])

        assert "route-neutral" in columns["raw_uri"]["description"].lower()
        assert "lineage" in columns["raw_file_path"]["description"]
        assert (
            "not used as staged row identity" in columns["raw_file_path"]["description"]
        )
        assert "checksum" in columns["sha256_checksum"]["description"].lower()

    manifest_columns = {
        column["name"]: column for column in models["stg_ingestion_manifest"]["columns"]
    }
    for column_name in MANIFEST_IDENTITY_COLUMNS:
        assert column_name in manifest_columns
        assert "not_null" in dbt_test_names(manifest_columns[column_name]["data_tests"])

    assert "lineage" in manifest_columns["local_raw_path"]["description"]
    assert "lineage" in manifest_columns["s3_raw_uri"]["description"]
    assert (
        "not used as the cross-route identity"
        in manifest_columns["local_raw_path"]["description"]
    )


def test_sba_staging_models_null_out_negative_approval_amounts():
    for model_path in (
        STAGING_MODELS["stg_sba_7a_loans"],
        STAGING_MODELS["stg_sba_504_loans"],
    ):
        model_sql = model_path.read_text(encoding="utf-8")

        assert "gross_approval_amount" in model_sql
        assert "else null" in model_sql
        assert ">= 0" in model_sql


def test_sba_staging_union_uses_explicit_column_contract():
    model_sql = STAGING_MODELS["stg_sba_loans"].read_text(encoding="utf-8")

    assert "select *" not in model_sql.lower()
    branches = model_sql.split("\nunion all\n")
    assert len(branches) == 2

    for branch_sql in branches:
        selected_columns = []
        for line in branch_sql.splitlines():
            stripped = line.strip()
            if not stripped or stripped == "select":
                continue
            if stripped.startswith("from "):
                break
            selected_columns.append(stripped.removesuffix(","))

        assert selected_columns == SBA_STAGING_COLUMNS


def test_staging_models_require_route_neutral_raw_identity():
    staging_paths = [
        STAGING_MODELS["stg_ingestion_manifest"],
        STAGING_MODELS["stg_sba_7a_loans"],
        STAGING_MODELS["stg_sba_504_loans"],
        STAGING_MODELS["stg_census_bds_state_year"],
        STAGING_MODELS["stg_bls_laus_state_month"],
    ]

    for model_path in staging_paths:
        model_sql = model_path.read_text(encoding="utf-8")

        assert "relation_has_column" not in model_sql
        assert "raw_file_path as artifact_raw_uri" not in model_sql
        assert "'local' as artifact_storage_backend" not in model_sql

    for model_path in staging_paths[1:]:
        model_sql = model_path.read_text(encoding="utf-8")

        assert "raw.raw_uri as artifact_raw_uri" in model_sql
        assert "raw.storage_backend as artifact_storage_backend" in model_sql


def test_pipeline_run_summary_has_staged_raw_source_contract():
    model_sql = STAGING_MODELS["stg_pipeline_run_summary"].read_text(encoding="utf-8")

    assert "source('raw', 'raw_pipeline_run_summary')" in model_sql
    assert "try_cast(raw_table_count as integer) as raw_table_count" in model_sql
