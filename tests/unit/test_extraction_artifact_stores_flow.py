from __future__ import annotations

import pytest

import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.flows.extraction_artifact_stores import resolve_extraction_bucket
from pipelines.storage.raw_artifacts import (
    artifact_store_for_route,
    raw_artifact_store_for_route,
)


def test_raw_artifact_store_matches_route(tmp_path):
    local_context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "local-data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="local-route",
    )
    cloud_context = local_flow.initialize_run.fn(
        run_mode="cloud",
        extract_mode="fixture",
        dbt_target="prod_snowflake",
        data_root=str(tmp_path / "cloud-data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket="cloud-bucket",
        pipeline_run_id="cloud-route",
    )

    assert raw_artifact_store_for_route(
        cloud_route=local_context.is_cloud_route,
        data_root=local_context.data_root,
        bucket="local-live",
    ).storage_backend == "local"
    assert raw_artifact_store_for_route(
        cloud_route=cloud_context.is_cloud_route,
        data_root=cloud_context.data_root,
        bucket="cloud-bucket",
        s3_client=object(),
    ).storage_backend == "s3"
    assert artifact_store_for_route(
        cloud_route=local_context.is_cloud_route,
        data_root=local_context.data_root,
        bucket="local-live",
    ).storage_backend == "local"
    assert artifact_store_for_route(
        cloud_route=cloud_context.is_cloud_route,
        data_root=cloud_context.data_root,
        bucket="cloud-bucket",
        s3_client=object(),
    ).storage_backend == "s3"


def test_extraction_bucket_rejects_missing_cloud_bucket(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="cloud",
        extract_mode="fixture",
        dbt_target="prod_snowflake",
        data_root=str(tmp_path / "cloud-data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="cloud-missing-bucket",
    )

    with pytest.raises(RuntimeError, match="configured S3 bucket"):
        resolve_extraction_bucket(
            context,
            default_bucket="local-live",
            s3_bucket_resolver=lambda _: None,
        )


def test_extraction_bucket_uses_default_only_for_local_route(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode="fixture",
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / "local-data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=None,
        pipeline_run_id="local-default-bucket",
    )

    assert (
        resolve_extraction_bucket(
            context,
            default_bucket="local-live",
            s3_bucket_resolver=lambda _: None,
        )
        == "local-live"
    )
