"""Validate Census BDS raw payload content."""

from __future__ import annotations

from collections import defaultdict

from pipelines.extract.census_bds_extract import validate_bds_response
from pipelines.utils.source_resources import CENSUS_BDS_SOURCE_IDENTITY, SourceIdentity
from pipelines.validation.raw_validation_check_catalog import (
    BDS_REQUIRED_VARIABLES,
    BDS_STATE_COVERAGE,
    BDS_ROW_GRAIN,
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
    try:
        validate_bds_response(payload, required_variables=required_variables)
        valid_grain = True
        grain_error = None
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        valid_grain = False
        grain_error = str(exc)
    header = payload[0] if payload and isinstance(payload[0], list) else []
    header = [column for column in header if isinstance(column, str)]
    rows = payload[1:] if valid_grain else []
    missing_variables = sorted(set(required_variables) - set(header))
    states_by_year = defaultdict(set)
    for row in rows:
        states_by_year[row[header.index("YEAR")]].add(row[header.index("state")])
    state_count = min((len(states) for states in states_by_year.values()), default=0)
    return [
        make_source_identity_validation_result(
            pipeline_run_id=pipeline_run_id,
            source_identity=source_identity,
            source_resource_name=CENSUS_BDS_RESOURCE_NAME,
            check_definition=BDS_ROW_GRAIN,
            passed=valid_grain,
            expected_value="valid rows at unique state-year grain",
            observed_value=grain_error,
            failed_message="Census BDS row shape or state-year grain is invalid.",
        ),
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
            failed_message="Census BDS response does not include expected state coverage in every returned year.",
        ),
    ]
