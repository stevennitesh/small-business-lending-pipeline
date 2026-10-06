from __future__ import annotations

from pipelines.flows.extraction_manifests import extraction_paths_from_manifest_maps
from pipelines.storage.raw_artifacts import ArtifactLocation


def test_cloud_manifest_references_keep_local_paths_for_missing_locations(tmp_path):
    """Validate that cloud manifest references keep local paths for missing locations."""
    sba_manifest = tmp_path / "sba.json"
    census_manifest = tmp_path / "census.json"
    bls_manifest = tmp_path / "bls.json"
    census_location = ArtifactLocation(
        storage_backend="s3",
        artifact_uri="s3://cloud-bucket/manifests/census.json",
        artifact_key="manifests/census.json",
        local_path=None,
        s3_uri="s3://cloud-bucket/manifests/census.json",
    )
    extraction_paths = extraction_paths_from_manifest_maps(
        manifest_paths={
            "sba_7a_fy2020_present": sba_manifest,
            "bds_state_year": census_manifest,
            "laus_state_month": bls_manifest,
        },
        manifest_locations={
            "bds_state_year": census_location,
        },
    )

    assert extraction_paths.manifest_references_for_validation(
        cloud_route=True,
    ) == (
        sba_manifest,
        census_location,
        bls_manifest,
    )
