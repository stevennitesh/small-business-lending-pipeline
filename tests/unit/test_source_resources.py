from __future__ import annotations

import pytest

from pipelines.utils.source_resources import (
    BLS_LAUS_RESOURCE,
    BLS_LAUS_RESOURCE_NAME,
    BLS_LAUS_SOURCE_KEY,
    CENSUS_BDS_RESOURCE,
    CENSUS_BDS_RESOURCE_NAME,
    CENSUS_BDS_SOURCE_KEY,
    FIXED_RAW_SOURCE_RESOURCES,
    SBA_7A_FY2020_PRESENT_RESOURCE,
    SBA_7A_FY2020_PRESENT_RESOURCE_NAME,
    SBA_FOIA_SOURCE_KEY,
    BLS_LAUS_SOURCE_IDENTITY,
    CENSUS_BDS_SOURCE_IDENTITY,
    SBA_FOIA_SOURCE_IDENTITY,
    fixed_raw_source_resource,
    sba_dataset_path_name,
    sba_raw_source_resource,
    source_key_for_resource,
)


def test_source_key_for_resource_maps_sba_configured_logical_resource():
    assert (
        source_key_for_resource(
            "sba_7a_fy1991_fy1999",
            sba_resource_names={"sba_7a_fy1991_fy1999"},
        )
        == SBA_FOIA_SOURCE_KEY
    )


def test_source_key_for_resource_maps_census_bds_resource():
    assert source_key_for_resource(CENSUS_BDS_RESOURCE_NAME) == (CENSUS_BDS_SOURCE_KEY)


def test_source_key_for_resource_maps_bls_laus_resource():
    assert source_key_for_resource(BLS_LAUS_RESOURCE_NAME) == (BLS_LAUS_SOURCE_KEY)


def test_source_key_for_resource_rejects_unknown_resource():
    with pytest.raises(ValueError, match="Unsupported raw resource"):
        source_key_for_resource("unknown_resource")


def test_fixed_raw_source_resource_returns_registered_metadata():
    resource = fixed_raw_source_resource(SBA_7A_FY2020_PRESENT_RESOURCE_NAME)

    assert resource == SBA_7A_FY2020_PRESENT_RESOURCE
    assert (
        FIXED_RAW_SOURCE_RESOURCES[SBA_7A_FY2020_PRESENT_RESOURCE_NAME]
        == SBA_7A_FY2020_PRESENT_RESOURCE
    )


def test_fixed_raw_source_resource_returns_none_for_dynamic_or_unknown_resource():
    assert fixed_raw_source_resource("sba_7a_fy1991_fy1999") is None
    assert fixed_raw_source_resource("unknown_resource") is None


def test_sba_raw_source_resource_builds_dynamic_path_metadata():
    resource = sba_raw_source_resource(
        logical_name="sba_504_fy1991_fy2009",
        program="504",
        source_period="fy1991_fy2009",
    )

    assert resource.source_key == SBA_FOIA_SOURCE_KEY
    assert resource.source_identity == SBA_FOIA_SOURCE_IDENTITY
    assert resource.resource_name == "sba_504_fy1991_fy2009"
    assert resource.raw_dataset_name == "504_foia"
    assert resource.raw_resource_name == "source_period=fy1991_fy2009"


def test_sba_dataset_path_name_rejects_unknown_program():
    assert sba_dataset_path_name("7a") == "7a_foia"
    assert sba_dataset_path_name("504") == "504_foia"
    assert sba_dataset_path_name("all") == "data_dictionary"

    with pytest.raises(ValueError, match="Unsupported SBA program: unknown"):
        sba_dataset_path_name("unknown")


def test_source_identity_constants_match_configured_sources():
    assert SBA_FOIA_SOURCE_IDENTITY.source_system == "sba"
    assert SBA_FOIA_SOURCE_IDENTITY.dataset_name == "7a_504_foia"
    assert CENSUS_BDS_SOURCE_IDENTITY.source_system == "census"
    assert CENSUS_BDS_SOURCE_IDENTITY.dataset_name == "bds"
    assert BLS_LAUS_SOURCE_IDENTITY.source_system == "bls"
    assert BLS_LAUS_SOURCE_IDENTITY.dataset_name == "laus"


def test_raw_source_resource_metadata_matches_path_contracts():
    assert SBA_7A_FY2020_PRESENT_RESOURCE.source_key == SBA_FOIA_SOURCE_KEY
    assert SBA_7A_FY2020_PRESENT_RESOURCE.raw_dataset_name == "7a_foia"
    assert (
        SBA_7A_FY2020_PRESENT_RESOURCE.raw_resource_name
        == "source_period=fy2020_present"
    )
    assert CENSUS_BDS_RESOURCE.source_key == CENSUS_BDS_SOURCE_KEY
    assert CENSUS_BDS_RESOURCE.raw_dataset_name == "bds"
    assert CENSUS_BDS_RESOURCE.raw_resource_name == "grain=state_year"
    assert BLS_LAUS_RESOURCE.source_key == BLS_LAUS_SOURCE_KEY
    assert BLS_LAUS_RESOURCE.raw_dataset_name == "laus"
    assert BLS_LAUS_RESOURCE.raw_resource_name == "grain=state_month"
