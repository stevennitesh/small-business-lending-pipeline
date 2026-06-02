"""Validate Census BDS raw payload content."""

from __future__ import annotations

from pipelines.utils.source_resources import CENSUS_BDS_SOURCE_IDENTITY, SourceIdentity
from pipelines.validation.raw_validation_check_catalog import (
    BDS_REQUIRED_VARIABLES,
    BDS_STATE_COVERAGE,
)
from pipelines.validation.raw_validation_models import CensusBdsPayload
from pipelines.validation.raw_validation_resources import CENSUS_BDS_RESOURCE_NAME
from pipelines.validation.validation_result import (
    ValidationResult,
    make_source_identity_validation_result,
)


DEFAULT_CENSUS_BDS_IDENTITY = CENSUS_BDS_SOURCE_IDENTITY


def check_census_bds_payload(
    payload: CensusBdsPayload,
    *,
    required_variables: tuple[str, ...],
    expected_state_count: int,
    pipeline_run_id: str,
    source_identity: SourceIdentity = DEFAULT_CENSUS_BDS_IDENTITY,
) -> list[ValidationResult]:
    """Validate Census BDS required variables and state coverage."""
    header = payload[0] if payload else []
    rows = payload[1:] if len(payload) > 1 else []
    missing_variables = sorted(set(required_variables) - set(header))
    state_count = (
        len({row[header.index("state")] for row in rows}) if "state" in header else 0
    )
    return [
        make_source_identity_validation_result(
            pipeline_run_id=pipeline_run_id,
            source_identity=source_identity,
            source_resource_name=CENSUS_BDS_RESOURCE_NAME,
            check_definition=BDS_REQUIRED_VARIABLES,
            passed=missing_variables == [],
            expected_value=list(required_variables),
            observed_value={"missing_variables": missing_variables},
            failed_message="Census BDS response is missing required variables.",
        ),
        make_source_identity_validation_result(
            pipeline_run_id=pipeline_run_id,
            source_identity=source_identity,
            source_resource_name=CENSUS_BDS_RESOURCE_NAME,
            check_definition=BDS_STATE_COVERAGE,
            passed=state_count >= expected_state_count,
            expected_value=expected_state_count,
            observed_value=state_count,
            failed_message="Census BDS response does not include expected state coverage.",
        ),
    ]
