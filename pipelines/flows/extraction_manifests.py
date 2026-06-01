"""Manifest path collections shared between extraction, validation, and loading."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pipelines.storage.raw_artifacts import ArtifactLocation
from pipelines.utils.source_resources import (
    BLS_LAUS_RESOURCE_NAME,
    CENSUS_BDS_RESOURCE_NAME,
    SBA_504_FY2010_PRESENT_RESOURCE_NAME,
    SBA_7A_FY2020_PRESENT_RESOURCE_NAME,
)


ManifestReferenceT = TypeVar("ManifestReferenceT", Path, ArtifactLocation)


@dataclass(frozen=True)
class ExtractionPaths:
    """Source-specific manifest paths and optional cloud artifact locations."""

    sba_7a_manifest_paths: tuple[Path, ...]
    sba_504_manifest_paths: tuple[Path, ...]
    census_bds_manifest_paths: tuple[Path, ...]
    bls_laus_manifest_paths: tuple[Path, ...]
    manifest_paths: tuple[Path, ...]
    sba_7a_manifest_locations: tuple[ArtifactLocation, ...] = ()
    sba_504_manifest_locations: tuple[ArtifactLocation, ...] = ()
    census_bds_manifest_locations: tuple[ArtifactLocation, ...] = ()
    bls_laus_manifest_locations: tuple[ArtifactLocation, ...] = ()
    manifest_locations: tuple[ArtifactLocation, ...] = ()

    def manifest_references_for_validation(
        self,
        *,
        cloud_route: bool,
    ) -> tuple[Path | ArtifactLocation, ...]:
        """Return cloud manifest locations when available, else local paths."""
        if cloud_route:
            source_specific_references = (
                *(self.sba_7a_manifest_locations or self.sba_7a_manifest_paths),
                *(self.sba_504_manifest_locations or self.sba_504_manifest_paths),
                *(
                    self.census_bds_manifest_locations
                    or self.census_bds_manifest_paths
                ),
                *(self.bls_laus_manifest_locations or self.bls_laus_manifest_paths),
            )
            if source_specific_references:
                return source_specific_references
            if self.manifest_locations:
                return self.manifest_locations
        return self.manifest_paths


def extraction_paths_from_manifest_maps(
    *,
    manifest_paths: dict[str, Path],
    manifest_locations: dict[str, ArtifactLocation] | None = None,
) -> ExtractionPaths:
    """Group flat manifest maps into source-specific manifest collections."""
    resolved_manifest_locations = manifest_locations or {}
    return ExtractionPaths(
        sba_7a_manifest_paths=_manifest_tuple_by_prefix(
            manifest_paths,
            _sba_program_prefix(SBA_7A_FY2020_PRESENT_RESOURCE_NAME),
        ),
        sba_504_manifest_paths=_manifest_tuple_by_prefix(
            manifest_paths,
            _sba_program_prefix(SBA_504_FY2010_PRESENT_RESOURCE_NAME),
        ),
        census_bds_manifest_paths=_manifest_tuple(
            manifest_paths,
            CENSUS_BDS_RESOURCE_NAME,
        ),
        bls_laus_manifest_paths=_manifest_tuple(
            manifest_paths,
            BLS_LAUS_RESOURCE_NAME,
        ),
        manifest_paths=tuple(manifest_paths.values()),
        sba_7a_manifest_locations=_manifest_tuple_by_prefix(
            resolved_manifest_locations,
            _sba_program_prefix(SBA_7A_FY2020_PRESENT_RESOURCE_NAME),
        ),
        sba_504_manifest_locations=_manifest_tuple_by_prefix(
            resolved_manifest_locations,
            _sba_program_prefix(SBA_504_FY2010_PRESENT_RESOURCE_NAME),
        ),
        census_bds_manifest_locations=_manifest_tuple(
            resolved_manifest_locations,
            CENSUS_BDS_RESOURCE_NAME,
        ),
        bls_laus_manifest_locations=_manifest_tuple(
            resolved_manifest_locations,
            BLS_LAUS_RESOURCE_NAME,
        ),
        manifest_locations=tuple(resolved_manifest_locations.values()),
    )


def _manifest_tuple(
    manifests: Mapping[str, ManifestReferenceT],
    resource_name: str,
) -> tuple[ManifestReferenceT, ...]:
    if resource_name not in manifests:
        return ()
    return (manifests[resource_name],)


def _manifest_tuple_by_prefix(
    manifests: Mapping[str, ManifestReferenceT],
    resource_name_prefix: str,
) -> tuple[ManifestReferenceT, ...]:
    return tuple(
        manifest
        for resource_name, manifest in sorted(manifests.items())
        if resource_name.startswith(resource_name_prefix)
    )


def _sba_program_prefix(resource_name: str) -> str:
    program, *_ = resource_name.split("_fy", 1)
    return f"{program}_"
