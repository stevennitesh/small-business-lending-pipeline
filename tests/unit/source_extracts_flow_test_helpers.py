from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipelines.extract.bls_laus_extract import BLSLAUSExtractionSummary
from pipelines.extract.census_bds_extract import CensusBDSExtractionSummary
from pipelines.extract.sba_extract import SBAExtractionSummary
from pipelines.flows import source_extracts
import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.storage.raw_artifacts import ArtifactLocation


SourceExtractorCall = tuple[str, dict[str, Any]]


def live_flow_context(
    tmp_path: Path,
    *,
    run_mode: str = "local",
    s3_bucket: str | None = None,
    pipeline_run_id: str = "live-test-run",
    source_start_year: int | None = 2020,
    source_end_year: int | None = 2024,
):
    """Build live flow context for tests."""
    return local_flow.initialize_run.fn(
        run_mode=run_mode,
        extract_mode="live",
        dbt_target="prod_snowflake" if run_mode == "cloud" else "dev_duckdb",
        data_root=str(tmp_path / "data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket=s3_bucket,
        pipeline_run_id=pipeline_run_id,
        source_start_year=source_start_year,
        source_end_year=source_end_year,
    )


def install_source_extractor_fakes(
    monkeypatch,
    tmp_path: Path,
    *,
    calls: list[SourceExtractorCall],
    manifest_locations: bool = False,
) -> None:
    """Install source extractor fakes for tests."""

    def fake_sba_extract(**kwargs):
        """Provide fake SBA extract for tests."""
        calls.append(("sba", kwargs))
        summary_kwargs: dict[str, Any] = {}
        if manifest_locations:
            summary_kwargs["manifest_locations"] = {
                "sba_7a_fy2020_present": manifest_location("sba_7a_fy2020_present"),
                "sba_504_fy2010_present": manifest_location("sba_504_fy2010_present"),
            }
        return SBAExtractionSummary(
            results={},
            manifest_paths={
                "sba_7a_fy2020_present": write_manifest_stub(
                    tmp_path, "sba_7a_fy2020_present"
                ),
                "sba_504_fy2010_present": write_manifest_stub(
                    tmp_path, "sba_504_fy2010_present"
                ),
            },
            warnings=[],
            **summary_kwargs,
        )

    def fake_census_extract(**kwargs):
        """Provide fake census extract for tests."""
        calls.append(("census", kwargs))
        return CensusBDSExtractionSummary(
            result=None,
            manifest_path=write_manifest_stub(tmp_path, "bds_state_year"),
            latest_available_year=2024,
            manifest_location=manifest_location("bds_state_year")
            if manifest_locations
            else None,
        )

    def fake_bls_extract(**kwargs):
        """Provide fake BLS extract for tests."""
        calls.append(("bls", kwargs))
        return BLSLAUSExtractionSummary(
            result=None,
            manifest_path=write_manifest_stub(tmp_path, "laus_state_month"),
            latest_observed_month="2024-12-01",
            series_count=51,
            manifest_location=manifest_location("laus_state_month")
            if manifest_locations
            else None,
        )

    monkeypatch.setattr(source_extracts, "extract_sba_foia", fake_sba_extract)
    monkeypatch.setattr(source_extracts, "extract_census_bds", fake_census_extract)
    monkeypatch.setattr(source_extracts, "extract_bls_laus", fake_bls_extract)


def manifest_location(resource_name: str) -> ArtifactLocation:
    """Build manifest location for tests."""
    return ArtifactLocation(
        storage_backend="s3",
        artifact_uri=f"s3://cloud-bucket/manifests/test/{resource_name}.json",
        artifact_key=f"manifests/test/{resource_name}.json",
        local_path=None,
        s3_uri=f"s3://cloud-bucket/manifests/test/{resource_name}.json",
    )


def write_manifest_stub(tmp_path: Path, resource_name: str) -> Path:
    """Write manifest stub for tests."""
    path = tmp_path / f"{resource_name}.manifest.json"
    path.write_text(
        json.dumps(
            {
                "resource_name": resource_name,
                "local_raw_path": str(tmp_path / f"{resource_name}.raw"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path
