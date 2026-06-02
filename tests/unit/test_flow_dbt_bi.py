from __future__ import annotations

import pytest

from pipelines.flows import dbt_bi
import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.powerbi.export_schema import BI_EXPORT_TABLES, EXTRA_SBA_KPI_BI_TABLES
from tests.unit.snowflake_test_helpers import FakeSnowflakeConnection


def test_flow_uses_shared_powerbi_export_contract(tmp_path, monkeypatch):
    monkeypatch.delenv("POWERBI_EXPORT_DIR", raising=False)

    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="local-powerbi-contract",
    )

    assert set(EXTRA_SBA_KPI_BI_TABLES) <= set(BI_EXPORT_TABLES)
    assert context.run_export_dir == tmp_path / "data" / "exports" / "powerbi"


def test_snowflake_bi_schema_can_use_cloud_smoke_prefix(monkeypatch):
    monkeypatch.delenv("SNOWFLAKE_BI_SCHEMA", raising=False)
    monkeypatch.setenv("DBT_SCHEMA_PREFIX", "SMOKE")

    assert dbt_bi.snowflake_bi_schema() == "SMOKE_BI"

    monkeypatch.setenv("SNOWFLAKE_BI_SCHEMA", "CUSTOM_BI")

    assert dbt_bi.snowflake_bi_schema() == "CUSTOM_BI"


def test_cloud_bi_validation_uses_expanded_contract_without_live_credentials(monkeypatch):
    connection = FakeSnowflakeConnection(
        table_counts={
            f'"SMOKE_BI"."{table_name.upper()}"': 1
            for table_name in BI_EXPORT_TABLES
        }
    )
    monkeypatch.setenv("SNOWFLAKE_BI_SCHEMA", "SMOKE_BI")
    monkeypatch.setattr(dbt_bi.SnowflakeConfig, "from_env", lambda: object())
    monkeypatch.setattr(dbt_bi, "connect_to_snowflake", lambda config: connection)
    monkeypatch.setattr(dbt_bi, "load_dotenv", lambda override=True: None)

    row_counts = dbt_bi.validate_snowflake_bi_tables()

    assert row_counts == {table_name: 1 for table_name in BI_EXPORT_TABLES}
    assert connection.closed is True
    executed_sql = "\n".join(connection.sql_statements)
    for table_name in EXTRA_SBA_KPI_BI_TABLES:
        assert f'"SMOKE_BI"."{table_name.upper()}"' in executed_sql


def test_cloud_bi_validation_rejects_invalid_schema_identifier(monkeypatch):
    monkeypatch.setenv("SNOWFLAKE_BI_SCHEMA", "SMOKE_BI;drop table BI")
    monkeypatch.setattr(dbt_bi.SnowflakeConfig, "from_env", lambda: object())
    monkeypatch.setattr(dbt_bi, "load_dotenv", lambda override=True: None)

    with pytest.raises(ValueError, match="Invalid Snowflake identifier"):
        dbt_bi.validate_snowflake_bi_tables()
