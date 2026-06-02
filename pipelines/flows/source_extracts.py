"""Live source-extraction adapter for the Prefect flow."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from pipelines.extract.bls_laus_extract import extract_bls_laus
from pipelines.extract.census_bds_extract import extract_census_bds
from pipelines.extract.sba_extract import extract_sba_foia
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
from pipelines.storage.raw_artifacts import ArtifactLocation
from pipelines.utils.config import ProjectConfig
from pipelines.utils.source_resources import (
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_KEY,
)


DEFAULT_LIVE_EXTRACTION_BUCKET = "local-live"


def extract_live_sources(
    context: LocalRunContext,
    project_config: ProjectConfig,
    *,
    raw_artifact_store_factory: RawStoreFactory | None = None,
    artifact_store_factory: ArtifactStoreFactory | None = None,
    s3_bucket_resolver: BucketResolver | None = None,
) -> ExtractionPaths:
    """Run enabled live extractors and group their manifest outputs."""
    load_dotenv(override=False)
    stores = resolve_extraction_artifact_stores(
        context,
        default_bucket=DEFAULT_LIVE_EXTRACTION_BUCKET,
        raw_artifact_store_factory=raw_artifact_store_factory,
        artifact_store_factory=artifact_store_factory,
        s3_bucket_resolver=s3_bucket_resolver,
    )
    manifest_paths: dict[str, Path] = {}
    manifest_locations: dict[str, ArtifactLocation] = {}

    if project_config.is_source_enabled(SBA_FOIA_SOURCE_KEY):
        sba_summary = extract_sba_foia(
            config=project_config.sba,
            source_identity=project_config.source_identity(SBA_FOIA_SOURCE_KEY),
            data_root=context.data_root,
            s3_bucket=stores.bucket,
            pipeline_run_id=context.pipeline_run_id,
            raw_artifact_store=stores.raw_store,
            manifest_artifact_store=stores.manifest_store,
        )
        manifest_paths.update(sba_summary.manifest_paths)
        manifest_locations.update(sba_summary.manifest_locations)

    if project_config.is_source_enabled(CENSUS_BDS_SOURCE_KEY):
        census_summary = extract_census_bds(
            config=project_config.census_bds,
            source_identity=project_config.source_identity(CENSUS_BDS_SOURCE_KEY),
            data_root=context.data_root,
            s3_bucket=stores.bucket,
            pipeline_run_id=context.pipeline_run_id,
            start_year=context.source_start_year,
            end_year=context.source_end_year,
            raw_artifact_store=stores.raw_store,
            manifest_artifact_store=stores.manifest_store,
        )
        manifest_paths.update(census_summary.manifest_paths)
        manifest_locations.update(census_summary.manifest_locations)

    if project_config.is_source_enabled(BLS_LAUS_SOURCE_KEY):
        requested_bls_start_year = (
            context.source_start_year or project_config.bls_laus.start_year
        )
        # Include the previous year so monthly context and rolling comparisons
        # remain available when a caller requests a narrow source year window.
        bls_start_year = max(requested_bls_start_year - 1, 1976)
        bls_summary = extract_bls_laus(
            config=project_config.bls_laus,
            source_identity=project_config.source_identity(BLS_LAUS_SOURCE_KEY),
            data_root=context.data_root,
            s3_bucket=stores.bucket,
            pipeline_run_id=context.pipeline_run_id,
            start_year=bls_start_year,
            end_year=context.source_end_year,
            raw_artifact_store=stores.raw_store,
            manifest_artifact_store=stores.manifest_store,
        )
        manifest_paths.update(bls_summary.manifest_paths)
        manifest_locations.update(bls_summary.manifest_locations)

    extraction_paths = extraction_paths_from_manifest_maps(
        manifest_paths=manifest_paths,
        manifest_locations=manifest_locations,
    )
    if project_config.is_source_enabled(SBA_FOIA_SOURCE_KEY):
        _ensure_required_sba_program_manifests(extraction_paths)

    return extraction_paths


def _ensure_required_sba_program_manifests(
    extraction_paths: ExtractionPaths,
) -> None:
    """Fail live SBA extraction unless both required program manifests exist."""
    if (
        extraction_paths.sba_7a_manifest_paths
        and extraction_paths.sba_504_manifest_paths
    ):
        return

    found_programs = _discovered_sba_programs(extraction_paths)
    found_program_names = ", ".join(found_programs) if found_programs else "none"
    raise RuntimeError(
        "Live SBA extraction did not produce both 7(a) and 504 manifests. "
        f"Found programs: {found_program_names}."
    )


def _discovered_sba_programs(extraction_paths: ExtractionPaths) -> tuple[str, ...]:
    """Return human-readable SBA programs discovered from manifest groups."""
    discovered_programs = []
    if extraction_paths.sba_7a_manifest_paths:
        discovered_programs.append("7(a)")
    if extraction_paths.sba_504_manifest_paths:
        discovered_programs.append("504")
    return tuple(discovered_programs)
