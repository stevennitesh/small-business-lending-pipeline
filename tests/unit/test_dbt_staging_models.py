from pathlib import Path

import yaml


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
    "stg_validation_result": Path(
        "dbt/models/staging/audit/stg_validation_result.sql"
    ),
}


def test_required_staging_models_exist():
    missing_paths = [str(path) for path in STAGING_MODELS.values() if not path.is_file()]

    assert missing_paths == []


def test_staging_schema_declares_issue_acceptance_tests():
    schema_yml = yaml.safe_load(Path("dbt/models/staging/schema.yml").read_text())
    models = {model["name"]: model for model in schema_yml["models"]}

    assert set(STAGING_MODELS) <= set(models)

    sba_loans = models["stg_sba_loans"]
    sba_columns = {column["name"]: column for column in sba_loans["columns"]}
    assert {test_name for test in sba_columns["loan_record_key"]["data_tests"] for test_name in test} == {
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


def test_sba_staging_models_null_out_negative_approval_amounts():
    for model_path in (
        STAGING_MODELS["stg_sba_7a_loans"],
        STAGING_MODELS["stg_sba_504_loans"],
    ):
        model_sql = model_path.read_text(encoding="utf-8")

        assert "gross_approval_amount" in model_sql
        assert "else null" in model_sql
        assert ">= 0" in model_sql
