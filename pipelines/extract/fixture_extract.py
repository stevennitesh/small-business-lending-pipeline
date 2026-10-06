"""Write deterministic local raw extracts for fixture-mode pipeline runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pipelines.extract.extraction_run import (
    ExtractionRun,
    RawManifestSpec,
    raw_location_for_resource,
    write_raw_extraction_artifact,
)
from pipelines.extract.fixture_payloads import (
    FixturePayload,
    bls_laus_fixture_payload,
    census_bds_fixture_payload,
    sba_504_fixture_payload,
    sba_7a_fixture_payload,
)
from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    LocalArtifactStore,
    RawArtifactLocation,
    S3ArtifactStore,
)
from pipelines.utils.config import ProjectConfig
from pipelines.utils.source_resources import (
    BLS_LAUS_RESOURCE,
    CENSUS_BDS_RESOURCE,
    RawSourceResource,
    SBA_504_FY2010_PRESENT_RESOURCE,
    SBA_7A_FY2020_PRESENT_RESOURCE,
)


@dataclass(frozen=True)
class FixtureRawOutput:
    """Raw fixture write result carried into manifest creation."""

    source_resource: RawSourceResource
    raw_location: RawArtifactLocation
    fixture_payload: FixturePayload


@dataclass(frozen=True)
class FixtureArtifactSpec:
    """Fixture payload and filename for one raw source resource."""

    source_resource: RawSourceResource
    filename: str
    fixture_payload: FixturePayload


@dataclass(frozen=True)
class FixtureExtractionContext:
    """Run context needed to write fixture raw files and manifests."""

    extraction_run: ExtractionRun
    run_mode: str


@dataclass(frozen=True)
class FixtureExtractionSummary:
    """Manifest paths and optional artifact locations for fixture extraction."""

    manifest_paths: dict[str, Path]
    manifest_locations: dict[str, ArtifactLocation]


def extract_fixture_source_outputs(
    context: FixtureExtractionContext,
    project_config: ProjectConfig,
    *,
    manifest_artifact_store: LocalArtifactStore | S3ArtifactStore | None = None,
) -> FixtureExtractionSummary:
    """Write deterministic raw fixture artifacts and their manifests."""
    raw_paths = write_fixture_raw_files(context)
    manifest_outputs = {
        raw_output.source_resource.resource_name: write_fixture_manifest(
            context=context,
            raw_output=raw_output,
            project_config=project_config,
            manifest_artifact_store=manifest_artifact_store,
        )
        for raw_output in raw_paths.values()
    }
    manifest_paths = {
        resource_name: manifest_path
        for resource_name, (manifest_path, _) in manifest_outputs.items()
    }
    manifest_locations = {
        resource_name: manifest_location
        for resource_name, (_, manifest_location) in manifest_outputs.items()
        if manifest_location is not None
    }
    return FixtureExtractionSummary(
        manifest_paths=manifest_paths,
        manifest_locations=manifest_locations,
    )


def write_fixture_raw_files(
    context: FixtureExtractionContext,
) -> dict[str, FixtureRawOutput]:
    """Write all configured fixture payloads to raw artifact storage."""
    output: dict[str, FixtureRawOutput] = {}

    for spec in fixture_artifact_specs():
        location = raw_location_for_resource(
            extraction_run=context.extraction_run,
            source_resource=spec.source_resource,
            filename=spec.filename,
            raw_dataset_name=spec.source_resource.raw_dataset_name,
        )
        context.extraction_run.raw_artifact_store.write_bytes(
            location,
            spec.fixture_payload.payload,
        )
        output[spec.source_resource.resource_name] = FixtureRawOutput(
            source_resource=spec.source_resource,
            raw_location=location,
            fixture_payload=spec.fixture_payload,
        )

    return output


def fixture_artifact_specs() -> tuple[FixtureArtifactSpec, ...]:
    """Build fixture artifact specs for the raw resources needed by local flows."""
    # Fixture payloads intentionally mimic source-native shapes so local fixture
    # mode exercises the same raw-load and validation contracts as live mode.
    sba_7a = sba_7a_fixture_payload()
    sba_504 = sba_504_fixture_payload()
    census_bds = census_bds_fixture_payload()
    bls_laus = bls_laus_fixture_payload()
    return (
        FixtureArtifactSpec(
            source_resource=SBA_7A_FY2020_PRESENT_RESOURCE,
            filename="sba_7a_fixture.csv",
            fixture_payload=sba_7a,
        ),
        FixtureArtifactSpec(
            source_resource=SBA_504_FY2010_PRESENT_RESOURCE,
            filename="sba_504_fixture.csv",
            fixture_payload=sba_504,
        ),
        FixtureArtifactSpec(
            source_resource=CENSUS_BDS_RESOURCE,
            filename="bds_state_year_fixture.json",
            fixture_payload=census_bds,
        ),
        FixtureArtifactSpec(
            source_resource=BLS_LAUS_RESOURCE,
            filename="bls_laus_state_month_fixture.json",
            fixture_payload=bls_laus,
        ),
    )


def write_fixture_manifest(
    *,
    context: FixtureExtractionContext,
    raw_output: FixtureRawOutput,
    project_config: ProjectConfig,
    manifest_artifact_store: LocalArtifactStore | S3ArtifactStore | None = None,
) -> tuple[Path, ArtifactLocation | None]:
    """Write the manifest for one previously written fixture raw artifact."""
    source_resource = raw_output.source_resource
    fixture_payload = raw_output.fixture_payload
    source_identity = project_config.source_identity(source_resource.source_key)
    manifest_path = (
        context.extraction_run.data_root
        / "manifests"
        / source_identity.source_system
        / f"pipeline_run_id={context.extraction_run.pipeline_run_id}"
        / f"{source_resource.resource_name}.manifest.json"
    )
    manifest_output = write_raw_extraction_artifact(
        extraction_run=context.extraction_run,
        spec=RawManifestSpec.from_extraction_payload(
            extraction_run=context.extraction_run,
            source_resource=source_resource,
            source_url=f"fixture://{source_resource.resource_name}",
            raw_location=raw_output.raw_location,
            raw_payload=fixture_payload.payload,
            row_count=fixture_payload.row_count,
            file_format=fixture_payload.file_format,
            schema_fields=fixture_payload.schema_fields,
            request_parameters={"run_mode": context.run_mode},
            source_identity=source_identity,
        ),
        manifest_path=manifest_path,
        manifest_artifact_store=manifest_artifact_store,
    )
    return manifest_output.manifest_path, manifest_output.manifest_location
