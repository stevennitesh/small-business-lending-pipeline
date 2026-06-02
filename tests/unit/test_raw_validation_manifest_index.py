from __future__ import annotations

import json

import pytest

from pipelines.storage.raw_artifacts import RawArtifactReader
from pipelines.validation.raw_payload_resources import read_payload_json
from pipelines.validation.raw_validation_models import RawManifestIndex
from pipelines.validation.raw_validation_resources import (
    BLS_LAUS_RESOURCE_NAME,
    CENSUS_BDS_RESOURCE_NAME,
)
from tests.unit.raw_manifest_test_helpers import manifest_for


def test_raw_manifest_index_builds_resource_lookup(tmp_path):
    raw_file = tmp_path / f"{CENSUS_BDS_RESOURCE_NAME}.json"
    raw_file.write_text('[["YEAR","state"],["2026","01"]]\n', encoding="utf-8")
    manifest = manifest_for(raw_file)

    index = RawManifestIndex.from_manifests([manifest])

    assert index.manifests == [manifest]
    assert index.manifest_for(CENSUS_BDS_RESOURCE_NAME) == manifest


def test_raw_manifest_index_reads_local_payload_json(tmp_path):
    raw_file = tmp_path / f"{BLS_LAUS_RESOURCE_NAME}.json"
    payload = {"normalized_rows": [{"series_id": "LASST010000000000003"}]}
    raw_file.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    manifest = manifest_for(raw_file)
    manifest["resource_name"] = BLS_LAUS_RESOURCE_NAME
    index = RawManifestIndex.from_manifests([manifest])

    assert (
        read_payload_json(index, BLS_LAUS_RESOURCE_NAME, RawArtifactReader()) == payload
    )


def test_raw_manifest_index_raises_for_absent_resource(tmp_path):
    raw_file = tmp_path / f"{CENSUS_BDS_RESOURCE_NAME}.json"
    raw_file.write_text('[["YEAR","state"],["2026","01"]]\n', encoding="utf-8")
    index = RawManifestIndex.from_manifests([manifest_for(raw_file)])

    expected_message = f"No manifest found for resource: {BLS_LAUS_RESOURCE_NAME}"
    with pytest.raises(ValueError, match=expected_message):
        index.manifest_for(BLS_LAUS_RESOURCE_NAME)
