"""Shared data models for pipeline flow execution and reporting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pipelines.validation.raw_validation_models import RawValidationOutput


VALID_RUN_MODES = ("cloud", "local")
VALID_EXTRACT_MODES = ("fixture", "live")

LOCAL_FLOW_STAGES = (
    "initialize_run",
    "load_config",
    "extract_sources",
    "write_manifests",
    "validate_raw_outputs",
    "load_duckdb_raw_tables",
    "run_dbt_build",
    "collect_dbt_artifacts",
    "validate_bi_tables",
    "export_bi_tables",
    "write_run_summary",
)

CLOUD_FLOW_STAGES = (
    "initialize_run",
    "load_config",
    "require_cloud_mode_config",
    "extract_sources",
    "write_manifests",
    "validate_raw_outputs",
    "record_raw_artifact_locations",
    "load_snowflake_raw_tables",
    "run_dbt_build",
    "collect_dbt_artifacts",
    "upload_dbt_artifacts_to_s3",
    "validate_bi_tables",
    "write_run_summary",
)


@dataclass(frozen=True)
class LocalRunContext:
    """Resolved runtime configuration shared across all flow stages."""

    pipeline_run_id: str
    run_mode: str
    extract_mode: str
    data_root: Path
    duckdb_path: Path
    dbt_project_dir: Path
    dbt_profiles_dir: Path
    dbt_target: str
    powerbi_export_dir: Path
    run_started_at_utc: str
    s3_bucket: str | None = None
    source_start_year: int | None = None
    source_end_year: int | None = None

    @property
    def is_cloud_route(self) -> bool:
        """Return whether this run should use cloud storage/load paths."""
        return self.run_mode == "cloud"

    @property
    def run_validation_dir(self) -> Path:
        """Directory for validation output and run summary artifacts."""
        return self.data_root / "validation" / f"pipeline_run_id={self.pipeline_run_id}"

    @property
    def run_export_dir(self) -> Path:
        """Directory where local BI exports should be written."""
        return self.powerbi_export_dir

    @property
    def stage_order(self) -> tuple[str, ...]:
        """Expected stage order for failure reporting."""
        return CLOUD_FLOW_STAGES if self.is_cloud_route else LOCAL_FLOW_STAGES


@dataclass(frozen=True)
class DbtBuildResult:
    """dbt command result captured for diagnostics."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass
class FlowRunState:
    """Mutable state used to build success/failure summaries during a run."""

    completed_stages: list[str] = field(default_factory=list)
    validation_output: RawValidationOutput | None = None
    manifest_artifact_uris: list[str] = field(default_factory=list)
    dbt_artifacts: dict[str, str] = field(default_factory=dict)
    bi_row_counts: dict[str, int] = field(default_factory=dict)
    export_paths: list[str] = field(default_factory=list)
    s3_upload_summary: dict[str, Any] = field(default_factory=dict)
    snowflake_raw_load_summary: dict[str, Any] = field(default_factory=dict)
    stage_durations_seconds: dict[str, float] = field(default_factory=dict)

    def complete(self, stage: str) -> None:
        """Mark one pipeline stage as complete."""
        self.completed_stages.append(stage)

    def complete_many(self, stages: list[str]) -> None:
        """Mark multiple pipeline stages as complete in order."""
        self.completed_stages.extend(stages)

    def completed_with_summary(self) -> list[str]:
        """Return completed stages including the final summary-writing stage."""
        return [*self.completed_stages, "write_run_summary"]

    def failed_stage(self, stage_order: tuple[str, ...]) -> str:
        """Return the first expected stage that has not completed."""
        return failed_stage_for(self.completed_stages, stage_order)


@dataclass(frozen=True)
class PipelineRunSummary:
    """Serializable audit summary written at the end of each run attempt."""

    pipeline_run_id: str
    run_mode: str
    route: str
    extract_mode: str
    dbt_target: str
    status: str
    completed_stages: list[str]
    failed_stage: str | None
    error_message: str | None
    started_at_utc: str
    finished_at_utc: str
    validation_result_path: str | None = None
    validation_result_uri: str | None = None
    manifest_artifact_uris: list[str] = field(default_factory=list)
    duckdb_path: str | None = None
    dbt_artifacts: dict[str, str] = field(default_factory=dict)
    bi_row_counts: dict[str, int] = field(default_factory=dict)
    export_paths: list[str] = field(default_factory=list)
    stage_durations_seconds: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the run summary for JSON output."""
        return asdict(self)


def failed_stage_for(completed_stages: list[str], stage_order: tuple[str, ...]) -> str:
    """Find the first incomplete stage in the route-specific stage order."""
    for stage in stage_order:
        if stage not in completed_stages and stage != "write_run_summary":
            return stage
    return "unknown"
