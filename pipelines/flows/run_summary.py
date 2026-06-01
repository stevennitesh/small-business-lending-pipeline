"""Run-summary persistence helpers for pipeline flow attempts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pipelines.flows.run_models import (
    LocalRunContext,
    PipelineRunSummary,
)
from pipelines.storage.raw_artifacts import ArtifactLocation
from pipelines.utils.dates import utc_now_iso
from pipelines.validation.raw_validation_models import RawValidationOutput


def write_run_summary_for_context(
    context: LocalRunContext,
    *,
    status: str,
    completed_stages: list[str],
    failed_stage: str | None = None,
    error_message: str | None = None,
    validation_result_path: Path | RawValidationOutput | None = None,
    manifest_artifact_uris: list[str] | None = None,
    dbt_artifacts: dict[str, str] | None = None,
    bi_row_counts: dict[str, int] | None = None,
    export_paths: list[str] | None = None,
    s3_upload_summary: dict[str, Any] | None = None,
    snowflake_raw_load_summary: dict[str, Any] | None = None,
    stage_durations_seconds: dict[str, float] | None = None,
) -> Path:
    """Write a JSON summary for a successful or failed pipeline run."""
    summary_started_at = time.perf_counter()
    stage_durations = dict(stage_durations_seconds or {})
    summary = PipelineRunSummary(
        pipeline_run_id=context.pipeline_run_id,
        run_mode=context.run_mode,
        # `route` is retained for the existing summary contract.
        route=context.run_mode,
        extract_mode=context.extract_mode,
        dbt_target=context.dbt_target,
        status=status,
        completed_stages=completed_stages,
        failed_stage=failed_stage,
        error_message=error_message,
        started_at_utc=context.run_started_at_utc,
        finished_at_utc=utc_now_iso(),
        validation_result_path=validation_output_local_path(
            validation_result_path
        ),
        validation_result_uri=validation_output_uri(
            validation_result_path
        ),
        manifest_artifact_uris=manifest_artifact_uris or [],
        duckdb_path=str(context.duckdb_path),
        dbt_artifacts=dbt_artifacts or {},
        bi_row_counts=bi_row_counts or {},
        export_paths=export_paths or [],
        stage_durations_seconds=stage_durations,
    )
    summary_payload = {
        **summary.to_dict(),
        "s3_upload_summary": s3_upload_summary or {},
        "snowflake_raw_load_summary": snowflake_raw_load_summary or {},
    }
    stage_durations["write_run_summary"] = round(
        time.perf_counter() - summary_started_at,
        3,
    )
    summary_payload["stage_durations_seconds"] = stage_durations
    summary_path = context.run_validation_dir / "run_summary.json"
    summary_path.write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path


def validation_output_local_path(
    validation_output: Path | RawValidationOutput | None,
) -> str | None:
    """Resolve the local validation result path for summary output."""
    if validation_output is None:
        return None
    if isinstance(validation_output, RawValidationOutput):
        return str(validation_output.local_path)
    return str(validation_output)


def validation_output_uri(
    validation_output: Path | RawValidationOutput | None,
) -> str | None:
    """Resolve the durable validation result URI for summary output."""
    if validation_output is None:
        return None
    if isinstance(validation_output, RawValidationOutput):
        durable_reference = validation_output.durable_reference
        return (
            str(durable_reference.artifact_uri)
            if isinstance(durable_reference, ArtifactLocation)
            else str(durable_reference)
        )
    return str(validation_output)
