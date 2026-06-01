from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

from pipelines.extract.bls_laus_extract import extract_bls_laus
from pipelines.extract.census_bds_extract import extract_census_bds
from pipelines.extract.fixture_extract import extract_fixture_sources
from pipelines.extract.sba_extract import extract_sba_foia
from pipelines.flows.run_models import ExtractionPaths, LocalRunContext
from pipelines.flows.run_setup import resolve_s3_bucket
from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    LocalArtifactStore,
    LocalRawArtifactStore,
    S3ArtifactStore,
    S3RawArtifactStore,
    artifact_store_for_route,
    raw_artifact_store_for_route,
)
from pipelines.utils.config import ProjectConfig
from pipelines.utils.source_resources import (
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_KEY,
)


RawStoreFactory = Callable[
    [LocalRunContext, str],
    LocalRawArtifactStore | S3RawArtifactStore,
]
ArtifactStoreFactory = Callable[
    [LocalRunContext, str],
    LocalArtifactStore | S3ArtifactStore,
]
BucketResolver = Callable[[LocalRunContext], str | None]


@dataclass
class LiveExtractionManifests:
    sba_manifest_paths: dict[str, Path] = field(default_factory=dict)
    sba_manifest_locations: dict[str, ArtifactLocation] = field(default_factory=dict)
    census_bds_manifest_paths: tuple[Path, ...] = ()
    census_bds_manifest_locations: tuple[ArtifactLocation, ...] = ()
    bls_laus_manifest_paths: tuple[Path, ...] = ()
    bls_laus_manifest_locations: tuple[ArtifactLocation, ...] = ()

    def sba_paths_by_program(self, logical_name_prefix: str) -> tuple[Path, ...]:
        return tuple(
            manifest_path
            for logical_name, manifest_path in sorted(self.sba_manifest_paths.items())
            if logical_name.startswith(logical_name_prefix)
        )

    def sba_locations_by_program(
        self,
        logical_name_prefix: str,
    ) -> tuple[ArtifactLocation, ...]:
        return tuple(
            manifest_location
            for logical_name, manifest_location in sorted(
                self.sba_manifest_locations.items()
            )
            if logical_name.startswith(logical_name_prefix)
        )

    def has_required_sba_program_manifests(self) -> bool:
        return bool(
            self.sba_paths_by_program("sba_7a_")
            and self.sba_paths_by_program("sba_504_")
        )

    def discovered_sba_programs(self) -> tuple[str, ...]:
        discovered_programs = []
        if self.sba_paths_by_program("sba_7a_"):
            discovered_programs.append("7(a)")
        if self.sba_paths_by_program("sba_504_"):
            discovered_programs.append("504")
        return tuple(discovered_programs)

    def to_extraction_paths(self) -> ExtractionPaths:
        return ExtractionPaths(
            sba_7a_manifest_paths=self.sba_paths_by_program("sba_7a_"),
            sba_504_manifest_paths=self.sba_paths_by_program("sba_504_"),
            census_bds_manifest_paths=self.census_bds_manifest_paths,
            bls_laus_manifest_paths=self.bls_laus_manifest_paths,
            manifest_paths=tuple(
                [
                    *self.sba_manifest_paths.values(),
                    *self.census_bds_manifest_paths,
                    *self.bls_laus_manifest_paths,
                ]
            ),
            sba_7a_manifest_locations=self.sba_locations_by_program("sba_7a_"),
            sba_504_manifest_locations=self.sba_locations_by_program("sba_504_"),
            census_bds_manifest_locations=self.census_bds_manifest_locations,
            bls_laus_manifest_locations=self.bls_laus_manifest_locations,
            manifest_locations=tuple(
                [
                    *self.sba_manifest_locations.values(),
                    *self.census_bds_manifest_locations,
                    *self.bls_laus_manifest_locations,
                ]
            ),
        )


def extract_live_sources(
    context: LocalRunContext,
    project_config: ProjectConfig,
    *,
    raw_artifact_store_factory: RawStoreFactory | None = None,
    artifact_store_factory: ArtifactStoreFactory | None = None,
    s3_bucket_resolver: BucketResolver | None = None,
) -> ExtractionPaths:
    load_dotenv(override=False)
    bucket = (s3_bucket_resolver or resolve_s3_bucket)(context) or "local-live"
    raw_store = (
        raw_artifact_store_factory(context, bucket)
        if raw_artifact_store_factory is not None
        else raw_artifact_store_for_route(
            cloud_route=context.is_cloud_route,
            data_root=context.data_root,
            bucket=bucket,
        )
    )
    manifest_store = (
        artifact_store_factory(context, bucket)
        if artifact_store_factory is not None and context.is_cloud_route
        else artifact_store_for_route(
            cloud_route=context.is_cloud_route,
            data_root=context.data_root,
            bucket=bucket,
        )
        if context.is_cloud_route
        else None
    )
    manifest_state = LiveExtractionManifests()

    if project_config.is_source_enabled(SBA_FOIA_SOURCE_KEY):
        sba_summary = extract_sba_foia(
            config=project_config.sba,
            source_identity=project_config.source_identity(SBA_FOIA_SOURCE_KEY),
            data_root=context.data_root,
            s3_bucket=bucket,
            pipeline_run_id=context.pipeline_run_id,
            raw_artifact_store=raw_store,
            manifest_artifact_store=manifest_store,
        )
        manifest_state.sba_manifest_paths = sba_summary.manifest_paths
        manifest_state.sba_manifest_locations = sba_summary.manifest_locations

    if project_config.is_source_enabled(CENSUS_BDS_SOURCE_KEY):
        census_summary = extract_census_bds(
            config=project_config.census_bds,
            source_identity=project_config.source_identity(CENSUS_BDS_SOURCE_KEY),
            data_root=context.data_root,
            s3_bucket=bucket,
            pipeline_run_id=context.pipeline_run_id,
            start_year=context.source_start_year,
            end_year=context.source_end_year,
            raw_artifact_store=raw_store,
            manifest_artifact_store=manifest_store,
        )
        manifest_state.census_bds_manifest_paths = (census_summary.manifest_path,)
        if census_summary.manifest_location is not None:
            manifest_state.census_bds_manifest_locations = (
                census_summary.manifest_location,
            )

    if project_config.is_source_enabled(BLS_LAUS_SOURCE_KEY):
        requested_bls_start_year = (
            context.source_start_year or project_config.bls_laus.start_year
        )
        bls_start_year = max(requested_bls_start_year - 1, 1976)
        bls_summary = extract_bls_laus(
            config=project_config.bls_laus,
            source_identity=project_config.source_identity(BLS_LAUS_SOURCE_KEY),
            data_root=context.data_root,
            s3_bucket=bucket,
            pipeline_run_id=context.pipeline_run_id,
            start_year=bls_start_year,
            end_year=context.source_end_year,
            raw_artifact_store=raw_store,
            manifest_artifact_store=manifest_store,
        )
        manifest_state.bls_laus_manifest_paths = (bls_summary.manifest_path,)
        if bls_summary.manifest_location is not None:
            manifest_state.bls_laus_manifest_locations = (
                bls_summary.manifest_location,
            )

    if (
        project_config.is_source_enabled(SBA_FOIA_SOURCE_KEY)
        and not manifest_state.has_required_sba_program_manifests()
    ):
        found_programs = manifest_state.discovered_sba_programs()
        raise RuntimeError(
            "Live SBA extraction did not produce both 7(a) and 504 manifests. "
            f"Found programs: {', '.join(found_programs) if found_programs else 'none'}."
        )

    return manifest_state.to_extraction_paths()


def extract_fixture_sources_for_flow(
    context: LocalRunContext,
    project_config: ProjectConfig,
    *,
    raw_artifact_store_factory: RawStoreFactory | None = None,
    artifact_store_factory: ArtifactStoreFactory | None = None,
    s3_bucket_resolver: BucketResolver | None = None,
) -> ExtractionPaths:
    return extract_fixture_sources(
        context,
        project_config,
        raw_artifact_store_factory=raw_artifact_store_factory,
        artifact_store_factory=artifact_store_factory,
        s3_bucket_resolver=s3_bucket_resolver or resolve_s3_bucket,
    )
