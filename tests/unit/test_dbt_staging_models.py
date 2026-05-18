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


def _test_names(column: dict) -> set[str]:
    names: set[str] = set()
    for data_test in column.get("data_tests", []):
        if isinstance(data_test, str):
            names.add(data_test)
        else:
            names.update(data_test)
    return names


def test_required_staging_models_exist():
    missing_paths = [str(path) for path in STAGING_MODELS.values() if not path.is_file()]

    assert missing_paths == []


def test_staging_schema_declares_issue_acceptance_tests():
    schema_yml = yaml.safe_load(Path("dbt/models/staging/schema.yml").read_text())
    models = {model["name"]: model for model in schema_yml["models"]}

    assert set(STAGING_MODELS) <= set(models)

    sba_loans = models["stg_sba_loans"]
    sba_columns = {column["name"]: column for column in sba_loans["columns"]}
    assert _test_names(sba_columns["loan_record_key"]) == {
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


def test_staging_schema_documents_and_tests_source_identity_contract():
    schema_yml = yaml.safe_load(Path("dbt/models/staging/schema.yml").read_text())
    models = {model["name"]: model for model in schema_yml["models"]}

    for model_name in SOURCE_ROW_STAGING_MODELS:
        columns = {column["name"]: column for column in models[model_name]["columns"]}
        for column_name in SOURCE_ROW_IDENTITY_COLUMNS:
            assert column_name in columns
            assert "not_null" in _test_names(columns[column_name])

        assert "route-neutral" in columns["raw_uri"]["description"].lower()
        assert "lineage" in columns["raw_file_path"]["description"]
        assert "not used as staged row identity" in columns["raw_file_path"]["description"]
        assert "checksum" in columns["sha256_checksum"]["description"].lower()

    manifest_columns = {
        column["name"]: column
        for column in models["stg_ingestion_manifest"]["columns"]
    }
    for column_name in MANIFEST_IDENTITY_COLUMNS:
        assert column_name in manifest_columns
        assert "not_null" in _test_names(manifest_columns[column_name])

    assert "lineage" in manifest_columns["local_raw_path"]["description"]
    assert "lineage" in manifest_columns["s3_raw_uri"]["description"]
    assert "not used as the cross-route identity" in manifest_columns["local_raw_path"]["description"]


def test_sba_staging_models_null_out_negative_approval_amounts():
    for model_path in (
        STAGING_MODELS["stg_sba_7a_loans"],
        STAGING_MODELS["stg_sba_504_loans"],
    ):
        model_sql = model_path.read_text(encoding="utf-8")

        assert "gross_approval_amount" in model_sql
        assert "else null" in model_sql
        assert ">= 0" in model_sql


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
