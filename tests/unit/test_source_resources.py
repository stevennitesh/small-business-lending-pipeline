from __future__ import annotations

import pytest

from pipelines.extract.fixture_extract import (
    source_name_for_resource as fixture_source_name_for_resource,
)
from pipelines.utils.config import load_project_config
from pipelines.utils.source_resources import (
    BLS_LAUS_SOURCE_IDENTITY,
    BLS_LAUS_RESOURCE_NAME,
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_SOURCE_IDENTITY,
    CENSUS_BDS_RESOURCE_NAME,
    CENSUS_BDS_SOURCE_KEY,
    SBA_FOIA_SOURCE_IDENTITY,
    SBA_FOIA_SOURCE_KEY,
    source_name_for_resource,
)


def test_fixture_extract_reexports_source_name_for_resource():
    assert fixture_source_name_for_resource is source_name_for_resource


def test_source_name_for_resource_maps_sba_configured_logical_resource():
    project_config = load_project_config()

    assert (
        source_name_for_resource("sba_7a_fy2020_present", project_config)
        == SBA_FOIA_SOURCE_KEY
    )


def test_source_name_for_resource_maps_census_bds_resource():
    project_config = load_project_config()

    assert source_name_for_resource(CENSUS_BDS_RESOURCE_NAME, project_config) == (
        CENSUS_BDS_SOURCE_KEY
    )


def test_source_name_for_resource_maps_bls_laus_resource():
    project_config = load_project_config()

    assert source_name_for_resource(BLS_LAUS_RESOURCE_NAME, project_config) == (
        BLS_LAUS_SOURCE_KEY
    )


def test_source_name_for_resource_rejects_unknown_resource():
    project_config = load_project_config()

    with pytest.raises(ValueError, match="Unsupported raw resource"):
        source_name_for_resource("unknown_resource", project_config)


def test_source_identity_constants_match_configured_sources():
    assert SBA_FOIA_SOURCE_IDENTITY.source_system == "sba"
    assert SBA_FOIA_SOURCE_IDENTITY.dataset_name == "7a_504_foia"
    assert CENSUS_BDS_SOURCE_IDENTITY.source_system == "census"
    assert CENSUS_BDS_SOURCE_IDENTITY.dataset_name == "bds"
    assert BLS_LAUS_SOURCE_IDENTITY.source_system == "bls"
    assert BLS_LAUS_SOURCE_IDENTITY.dataset_name == "laus"
