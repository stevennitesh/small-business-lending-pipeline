from __future__ import annotations

from pipelines.utils.config import ProjectConfig, SourceIdentity


SBA_FOIA_SOURCE_KEY = "sba_foia"
CENSUS_BDS_SOURCE_KEY = "census_bds"
BLS_LAUS_SOURCE_KEY = "bls_laus"
CENSUS_BDS_RESOURCE_NAME = "bds_state_year"
BLS_LAUS_RESOURCE_NAME = "laus_state_month"
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


def source_name_for_resource(resource_name: str, project_config: ProjectConfig) -> str:
    sba_resource_names = {spec.logical_name for spec in project_config.sba.resources}
    if resource_name in sba_resource_names:
        return SBA_FOIA_SOURCE_KEY
    if resource_name == CENSUS_BDS_RESOURCE_NAME:
        return CENSUS_BDS_SOURCE_KEY
    if resource_name == BLS_LAUS_RESOURCE_NAME:
        return BLS_LAUS_SOURCE_KEY
    raise ValueError(f"Unsupported raw resource: {resource_name}")
