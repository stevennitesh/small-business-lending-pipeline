from __future__ import annotations

import pipelines.flows.lending_pipeline_flow as local_flow
from pipelines.flows import raw_loads
from pipelines.flows.extraction_manifests import ExtractionPaths
from pipelines.storage.raw_artifacts import ArtifactLocation
from pipelines.validation.raw_validation_models import RawValidationOutput


def test_raw_loads_record_cloud_artifact_locations_without_reupload(tmp_path):
    context = local_flow.initialize_run.fn(
        run_mode="cloud",
        extract_mode="fixture",
        dbt_target="prod_snowflake",
        data_root=str(tmp_path / "cloud-data"),
        duckdb_path=str(tmp_path / "warehouse.duckdb"),
        dbt_project_dir="dbt",
        dbt_profiles_dir=str(tmp_path / "profiles"),
        s3_bucket="cloud-bucket",
        pipeline_run_id="cloud-artifact-record",
    )
    manifest_location = ArtifactLocation(
        storage_backend="s3",
        artifact_uri="s3://cloud-bucket/manifests/example.json",
        artifact_key="manifests/example.json",
        local_path=None,
        s3_uri="s3://cloud-bucket/manifests/example.json",
    )
    validation_location = ArtifactLocation(
        storage_backend="s3",
        artifact_uri="s3://cloud-bucket/validation/results.json",
        artifact_key="validation/results.json",
        local_path=None,
        s3_uri="s3://cloud-bucket/validation/results.json",
    )
    extraction_paths = ExtractionPaths(
        sba_7a_manifest_paths=(),
        sba_504_manifest_paths=(),
        census_bds_manifest_paths=(),
        bls_laus_manifest_paths=(),
        manifest_paths=(),
        manifest_locations=(manifest_location,),
    )
    validation_output = RawValidationOutput(
        local_path=tmp_path / "validation_results.json",
        artifact_location=validation_location,
    )

    summary = raw_loads.record_raw_artifact_locations_for_context(
        context,
        extraction_paths,
        validation_output,
    )

    assert summary.bucket == "cloud-bucket"
    assert summary.uploaded_objects == (
        "s3://cloud-bucket/manifests/example.json",
        "s3://cloud-bucket/validation/results.json",
    )
