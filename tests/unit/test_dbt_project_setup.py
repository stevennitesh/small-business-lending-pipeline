from pathlib import Path

import yaml


def test_required_dbt_project_files_exist():
    required_paths = [
        Path("dbt/dbt_project.yml"),
        Path("dbt/profiles.yml.example"),
        Path("dbt/models/sources/sources.yml"),
        Path("dbt/macros/generate_surrogate_key.sql"),
        Path("dbt/macros/safe_divide.sql"),
        Path("dbt/macros/clean_lender_name.sql"),
        Path("dbt/macros/date_spine.sql"),
        Path("dbt/macros/relation_columns.sql"),
    ]

    missing_paths = [str(path) for path in required_paths if not path.is_file()]

    assert missing_paths == []


def test_dbt_target_names_match_runtime_config():
    profile = yaml.safe_load(Path("dbt/profiles.yml.example").read_text())
    outputs = profile["small_business_lending_pipeline"]["outputs"]

    assert profile["small_business_lending_pipeline"]["target"] == "dev_duckdb"
    assert "dev_duckdb" in outputs
    assert "prod_snowflake" in outputs


def test_raw_sources_are_documented():
    sources_yml = yaml.safe_load(Path("dbt/models/sources/sources.yml").read_text())
    raw_source = sources_yml["sources"][0]
    raw_tables = {table["name"] for table in raw_source["tables"]}

    assert raw_source["name"] == "raw"
    assert {
        "raw_sba_7a_foia",
        "raw_sba_504_foia",
        "raw_census_bds_state_year",
        "raw_bls_laus_state_month",
        "raw_ingestion_manifest",
        "raw_validation_result",
        "raw_pipeline_run_summary",
    } <= raw_tables
