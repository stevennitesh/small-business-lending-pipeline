"""Fixture-mode extraction adapter for the Prefect flow."""

from __future__ import annotations

from pipelines.extract.fixture_extract import (
    FixtureExtractionContext,
    extract_fixture_source_outputs,
)
from pipelines.extract.extraction_run import build_extraction_run
from pipelines.flows.extraction_artifact_stores import (
    ArtifactStoreFactory,
    BucketResolver,
    RawStoreFactory,
    resolve_extraction_artifact_stores,
)
from pipelines.flows.extraction_manifests import (
    ExtractionPaths,
    extraction_paths_from_manifest_maps,
)
from pipelines.flows.run_models import (
    LocalRunContext,
)
from pipelines.utils.config import ProjectConfig


DEFAULT_FIXTURE_EXTRACTION_BUCKET = "local-fixtures"


def extract_fixture_sources_for_flow(
    context: LocalRunContext,
    project_config: ProjectConfig,
    *,
    raw_artifact_store_factory: RawStoreFactory | None = None,
    artifact_store_factory: ArtifactStoreFactory | None = None,
    s3_bucket_resolver: BucketResolver | None = None,
) -> ExtractionPaths:
    """Write fixture raw artifacts and return their manifest references."""
    stores = resolve_extraction_artifact_stores(
        context,
        default_bucket=DEFAULT_FIXTURE_EXTRACTION_BUCKET,
        raw_artifact_store_factory=raw_artifact_store_factory,
        artifact_store_factory=artifact_store_factory,
        s3_bucket_resolver=s3_bucket_resolver,
    )
    summary = extract_fixture_source_outputs(
        FixtureExtractionContext(
            extraction_run=build_extraction_run(
                data_root=context.data_root,
                s3_bucket=stores.bucket,
                pipeline_run_id=context.pipeline_run_id,
                extracted_at_utc=context.run_started_at_utc,
                raw_artifact_store=stores.raw_store,
            ),
            run_mode=context.run_mode,
        ),
        project_config,
        manifest_artifact_store=stores.manifest_store,
    )
    return extraction_paths_from_manifest_maps(
        manifest_paths=summary.manifest_paths,
        manifest_locations=summary.manifest_locations,
    )
