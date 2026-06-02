from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from pipelines.flows.fixture_source_extracts import extract_fixture_sources_for_flow
from pipelines.flows.run_models import LocalRunContext
from pipelines.storage.raw_artifacts import (
    ArtifactReader,
    LocalArtifactStore,
    LocalRawArtifactStore,
    RawArtifactReader,
    S3ArtifactStore,
    S3RawArtifactStore,
)
from pipelines.utils.config import load_project_config
from pipelines.flows.raw_validation import validate_raw_outputs_for_flow
from tests.unit.artifact_store_test_helpers import FakeS3ObjectClient
from tests.unit.validation_test_helpers import read_json, read_json_bytes


def test_fixture_extraction_and_validation_are_local_only(tmp_path):
    project_config = load_project_config()
    context = run_context(tmp_path, run_mode="local", pipeline_run_id="test-run")

    extraction_paths = extract_fixture_sources_for_flow(context, project_config)
    validation_output = validate_raw_outputs_for_flow(
        context,
        extraction_paths,
        project_config,
    )
    validation_payload = read_json(validation_output.local_path)

    assert validation_output.local_path.is_file()
    assert validation_output.artifact_location is None
    assert len(extraction_paths.manifest_paths) == 4
    assert all(Path(path).is_file() for path in extraction_paths.manifest_paths)
    assert {record["status"] for record in validation_payload} == {"passed"}
    assert "RAW_009" in {record["validation_check_id"] for record in validation_payload}
    bls_manifest = read_json(extraction_paths.bls_laus_manifest_paths[0])
    bls_payload = read_json(Path(bls_manifest["local_raw_path"]))
    assert bls_manifest["row_count"] == 4
    assert {str(row["year"]) for row in bls_payload["normalized_rows"]} == {
        "2025",
        "2026",
    }


def test_fixture_manifests_use_source_config_identity(tmp_path):
    project_config = load_project_config()
    sources = {
        **project_config.sources,
        "census_bds": replace(
            project_config.sources["census_bds"],
            source_system="custom_census",
            dataset_name="custom_bds",
        ),
        "bls_laus": replace(
            project_config.sources["bls_laus"],
            source_system="custom_bls",
            dataset_name="custom_laus",
        ),
    }
    project_config = replace(project_config, sources=sources)
    context = run_context(
        tmp_path,
        run_mode="local",
        pipeline_run_id="fixture-identity-run",
    )

    extraction_paths = extract_fixture_sources_for_flow(context, project_config)
    census_manifest = read_json(extraction_paths.census_bds_manifest_paths[0])
    bls_manifest = read_json(extraction_paths.bls_laus_manifest_paths[0])

    assert census_manifest["source_system"] == "custom_census"
    assert census_manifest["dataset_name"] == "custom_bds"
    assert bls_manifest["source_system"] == "custom_bls"
    assert bls_manifest["dataset_name"] == "custom_laus"


def test_cloud_fixture_extraction_and_validation_use_s3_backed_manifests(tmp_path):
    project_config = load_project_config()
    s3_client = FakeS3ObjectClient()
    context = run_context(
        tmp_path,
        run_mode="cloud",
        s3_bucket="unit-test-bucket",
        pipeline_run_id="cloud-fixture-run",
    )

    def raw_artifact_store_factory(context: LocalRunContext, bucket: str):
        if context.is_cloud_route:
            return S3RawArtifactStore(bucket=bucket, s3_client=s3_client)
        return LocalRawArtifactStore(data_root=context.data_root, s3_bucket=bucket)

    def artifact_store_factory(context: LocalRunContext, bucket: str):
        if context.is_cloud_route:
            return S3ArtifactStore(bucket=bucket, s3_client=s3_client)
        return LocalArtifactStore(data_root=context.data_root, s3_bucket=bucket)

    def artifact_reader_factory(context: LocalRunContext):
        return ArtifactReader(s3_client=s3_client if context.is_cloud_route else None)

    def raw_artifact_reader_factory(context: LocalRunContext):
        return RawArtifactReader(
            s3_client=s3_client if context.is_cloud_route else None
        )

    extraction_paths = extract_fixture_sources_for_flow(
        context,
        project_config,
        raw_artifact_store_factory=raw_artifact_store_factory,
        artifact_store_factory=artifact_store_factory,
        s3_bucket_resolver=lambda context: context.s3_bucket,
    )
    validation_output = validate_raw_outputs_for_flow(
        context,
        extraction_paths,
        project_config,
        artifact_reader_factory=artifact_reader_factory,
        raw_artifact_reader_factory=raw_artifact_reader_factory,
        artifact_store_factory=artifact_store_factory,
        s3_bucket_resolver=lambda context: context.s3_bucket,
    )
    validation_results = read_json(validation_output.local_path)
    manifests = [read_json(path) for path in extraction_paths.manifest_paths]

    assert {manifest["storage_backend"] for manifest in manifests} == {"s3"}
    assert all(manifest["local_raw_path"] is None for manifest in manifests)
    assert all(
        manifest["raw_uri"].startswith("s3://unit-test-bucket/")
        for manifest in manifests
    )
    assert {result["status"] for result in validation_results} == {"passed"}
    assert validation_output.artifact_location is not None
    assert validation_output.artifact_location.artifact_uri.startswith(
        "s3://unit-test-bucket/validation/pipeline/raw_validation/"
    )
    validation_key = validation_output.artifact_location.artifact_key
    assert read_json_bytes(s3_client.objects[("unit-test-bucket", validation_key)]) == (
        validation_results
    )


def run_context(
    tmp_path: Path,
    *,
    run_mode: str,
    pipeline_run_id: str,
    s3_bucket: str | None = None,
) -> LocalRunContext:
    data_root = tmp_path / "data"
    context = LocalRunContext(
        pipeline_run_id=pipeline_run_id,
        run_mode=run_mode,
        extract_mode="fixture",
        data_root=data_root,
        duckdb_path=tmp_path / "warehouse.duckdb",
        dbt_project_dir=Path("dbt"),
        dbt_profiles_dir=tmp_path / "profiles",
        dbt_target="prod_snowflake" if run_mode == "cloud" else "dev_duckdb",
        powerbi_export_dir=data_root / "exports" / "powerbi",
        run_started_at_utc="2026-05-30T00:00:00+00:00",
        s3_bucket=s3_bucket,
    )
    context.data_root.mkdir(parents=True, exist_ok=True)
    context.run_validation_dir.mkdir(parents=True, exist_ok=True)
    context.run_export_dir.mkdir(parents=True, exist_ok=True)
    return context
