from __future__ import annotations

from pathlib import Path

import pytest

import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.flows.extraction_artifact_stores import resolve_extraction_bucket
from pipelines.flows.run_models import LocalRunContext
from pipelines.storage.raw_artifacts import (
    artifact_store_for_route,
    raw_artifact_store_for_route,
)


def test_raw_artifact_store_matches_route(tmp_path):
    local_context = _route_context(
        tmp_path,
        run_mode="local",
        data_root_name="local-data",
        pipeline_run_id="local-route",
    )
    cloud_context = _route_context(
        tmp_path,
        run_mode="cloud",
        data_root_name="cloud-data",
        s3_bucket="cloud-bucket",
        pipeline_run_id="cloud-route",
    )

    assert (
        raw_artifact_store_for_route(
            cloud_route=local_context.is_cloud_route,
            data_root=local_context.data_root,
            bucket="local-live",
        ).storage_backend
        == "local"
    )
    assert (
        raw_artifact_store_for_route(
            cloud_route=cloud_context.is_cloud_route,
            data_root=cloud_context.data_root,
            bucket="cloud-bucket",
            s3_client=object(),
        ).storage_backend
        == "s3"
    )
    assert (
        artifact_store_for_route(
            cloud_route=local_context.is_cloud_route,
            data_root=local_context.data_root,
            bucket="local-live",
        ).storage_backend
        == "local"
    )
    assert (
        artifact_store_for_route(
            cloud_route=cloud_context.is_cloud_route,
            data_root=cloud_context.data_root,
            bucket="cloud-bucket",
            s3_client=object(),
        ).storage_backend
        == "s3"
    )


def test_extraction_bucket_rejects_missing_cloud_bucket(tmp_path):
    context = _route_context(
        tmp_path,
        run_mode="cloud",
        data_root_name="cloud-data",
        pipeline_run_id="cloud-missing-bucket",
    )

    with pytest.raises(RuntimeError, match="configured S3 bucket"):
        resolve_extraction_bucket(
            context,
            default_bucket="local-live",
            s3_bucket_resolver=lambda _: None,
        )


def test_extraction_bucket_uses_default_only_for_local_route(tmp_path):
    context = _route_context(
        tmp_path,
        run_mode="local",
        data_root_name="local-data",
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


def _route_context(
    tmp_path: Path,
    *,
    run_mode: str,
    data_root_name: str,
    pipeline_run_id: str,
    s3_bucket: str | None = None,
) -> LocalRunContext:
    return local_flow.initialize_run.fn(
        run_mode=run_mode,
        extract_mode="fixture",
        dbt_target="prod_snowflake" if run_mode == "cloud" else "dev_duckdb",
        data_root=str(tmp_path / data_root_name),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=s3_bucket,
        pipeline_run_id=pipeline_run_id,
    )
