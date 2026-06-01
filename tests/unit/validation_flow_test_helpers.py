from __future__ import annotations

from pathlib import Path

import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.flows.extraction_manifests import ExtractionPaths
from pipelines.flows.run_models import LocalRunContext
from pipelines.utils.config import ProjectConfig


def validation_context(
    tmp_path: Path,
    *,
    pipeline_run_id: str,
    extract_mode: str = "fixture",
    data_root_name: str = "data",
    duckdb_name: str = "warehouse.duckdb",
    profiles_name: str = "profiles",
) -> LocalRunContext:
    return local_flow.initialize_run.fn(
        run_mode="local",
        extract_mode=extract_mode,
        dbt_target="dev_duckdb",
        data_root=str(tmp_path / data_root_name),
        duckdb_path=str(tmp_path / duckdb_name),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / profiles_name),
        s3_bucket=None,
        pipeline_run_id=pipeline_run_id,
    )


def fixture_validation_inputs(
    tmp_path: Path,
    *,
    pipeline_run_id: str,
    project_config: ProjectConfig | None = None,
) -> tuple[ProjectConfig, LocalRunContext, ExtractionPaths]:
    resolved_project_config = project_config or local_flow.load_config.fn()
    context = validation_context(tmp_path, pipeline_run_id=pipeline_run_id)
    extraction_paths = local_flow.extract_sources.fn(
        context,
        resolved_project_config,
    )
    return resolved_project_config, context, extraction_paths
