from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


SBA_FOIA_SOURCE_KEY = "sba_foia"
CENSUS_BDS_SOURCE_KEY = "census_bds"
BLS_LAUS_SOURCE_KEY = "bls_laus"
SBA_7A_FY2020_PRESENT_RESOURCE_NAME = "sba_7a_fy2020_present"
SBA_504_FY2010_PRESENT_RESOURCE_NAME = "sba_504_fy2010_present"
CENSUS_BDS_RESOURCE_NAME = "bds_state_year"
BLS_LAUS_RESOURCE_NAME = "laus_state_month"
SBA_7A_DATASET_PATH_NAME = "7a_foia"
SBA_504_DATASET_PATH_NAME = "504_foia"
SBA_DATA_DICTIONARY_DATASET_PATH_NAME = "data_dictionary"
CENSUS_BDS_RESOURCE_GRAIN = "grain=state_year"
BLS_LAUS_RESOURCE_GRAIN = "grain=state_month"


@dataclass(frozen=True)
class SourceIdentity:
    source_system: str
    dataset_name: str


SBA_FOIA_SOURCE_IDENTITY = SourceIdentity(
    source_system="sba",
    dataset_name="7a_504_foia",
)
CENSUS_BDS_SOURCE_IDENTITY = SourceIdentity(
    source_system="census",
    dataset_name="bds",
)
BLS_LAUS_SOURCE_IDENTITY = SourceIdentity(
    source_system="bls",
    dataset_name="laus",
)


@dataclass(frozen=True)
class RawSourceResource:
    source_key: str
    source_identity: SourceIdentity
    resource_name: str
    raw_dataset_name: str
    raw_resource_name: str


def source_key_for_resource(
    resource_name: str,
    *,
    sba_resource_names: Iterable[str] = (),
) -> str:
    fixed_resource = fixed_raw_source_resource(resource_name)
    if fixed_resource is not None:
        return fixed_resource.source_key

    if resource_name in sba_resource_names:
        return SBA_FOIA_SOURCE_KEY
    raise ValueError(f"Unsupported raw resource: {resource_name}")


def sba_dataset_path_name(program: str) -> str:
    if program == "7a":
        return SBA_7A_DATASET_PATH_NAME
    if program == "504":
        return SBA_504_DATASET_PATH_NAME
    return SBA_DATA_DICTIONARY_DATASET_PATH_NAME


def source_period_resource_path_name(source_period: str) -> str:
    if source_period == "all":
        return "all"
    return f"source_period={source_period}"


SBA_7A_FY2020_PRESENT_RESOURCE = RawSourceResource(
    source_key=SBA_FOIA_SOURCE_KEY,
    source_identity=SBA_FOIA_SOURCE_IDENTITY,
    resource_name=SBA_7A_FY2020_PRESENT_RESOURCE_NAME,
    raw_dataset_name=SBA_7A_DATASET_PATH_NAME,
    raw_resource_name=source_period_resource_path_name("fy2020_present"),
)
SBA_504_FY2010_PRESENT_RESOURCE = RawSourceResource(
    source_key=SBA_FOIA_SOURCE_KEY,
    source_identity=SBA_FOIA_SOURCE_IDENTITY,
    resource_name=SBA_504_FY2010_PRESENT_RESOURCE_NAME,
    raw_dataset_name=SBA_504_DATASET_PATH_NAME,
    raw_resource_name=source_period_resource_path_name("fy2010_present"),
)
CENSUS_BDS_RESOURCE = RawSourceResource(
    source_key=CENSUS_BDS_SOURCE_KEY,
    source_identity=CENSUS_BDS_SOURCE_IDENTITY,
    resource_name=CENSUS_BDS_RESOURCE_NAME,
    raw_dataset_name=CENSUS_BDS_SOURCE_IDENTITY.dataset_name,
    raw_resource_name=CENSUS_BDS_RESOURCE_GRAIN,
)
BLS_LAUS_RESOURCE = RawSourceResource(
    source_key=BLS_LAUS_SOURCE_KEY,
    source_identity=BLS_LAUS_SOURCE_IDENTITY,
    resource_name=BLS_LAUS_RESOURCE_NAME,
    raw_dataset_name=BLS_LAUS_SOURCE_IDENTITY.dataset_name,
    raw_resource_name=BLS_LAUS_RESOURCE_GRAIN,
)

FIXED_RAW_SOURCE_RESOURCES = {
    resource.resource_name: resource
    for resource in (
        SBA_7A_FY2020_PRESENT_RESOURCE,
        SBA_504_FY2010_PRESENT_RESOURCE,
        CENSUS_BDS_RESOURCE,
        BLS_LAUS_RESOURCE,
    )
}


def fixed_raw_source_resource(resource_name: str) -> RawSourceResource | None:
    return FIXED_RAW_SOURCE_RESOURCES.get(resource_name)


def sba_raw_source_resource(
    *,
    logical_name: str,
    program: str,
    source_period: str,
) -> RawSourceResource:
    return RawSourceResource(
        source_key=SBA_FOIA_SOURCE_KEY,
        source_identity=SBA_FOIA_SOURCE_IDENTITY,
        resource_name=logical_name,
        raw_dataset_name=sba_dataset_path_name(program),
        raw_resource_name=source_period_resource_path_name(source_period),
    )
