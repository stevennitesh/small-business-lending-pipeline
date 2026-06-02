"""Validate normalized BLS LAUS raw payload content."""

from __future__ import annotations

import re
from datetime import date

from pipelines.utils.source_resources import BLS_LAUS_SOURCE_IDENTITY, SourceIdentity
from pipelines.validation.raw_validation_check_catalog import (
    BLS_EXPECTED_SERIES,
    BLS_MONTHLY_PERIODS,
    BLS_NUMERIC_VALUES,
    BLS_VALUE_RANGE,
)
from pipelines.validation.raw_validation_models import BlsLausPayload
from pipelines.validation.raw_validation_resources import BLS_LAUS_RESOURCE_NAME
from pipelines.validation.validation_result import (
    ValidationResult,
    make_source_identity_validation_result,
)


DEFAULT_BLS_LAUS_IDENTITY = BLS_LAUS_SOURCE_IDENTITY


def check_bls_laus_payload(
    payload: BlsLausPayload,
    *,
    expected_series_ids: tuple[str, ...],
    pipeline_run_id: str,
    required_period_pattern: str = r"^M(0[1-9]|1[0-2])$",
    unemployment_rate_min: float = 0,
    unemployment_rate_max: float = 100,
    source_identity: SourceIdentity = DEFAULT_BLS_LAUS_IDENTITY,
) -> list[ValidationResult]:
    """Validate BLS LAUS series coverage, monthly periods, and rate values."""
    rows = payload.get("normalized_rows", [])
    observed_series_ids = {str(row.get("series_id")) for row in rows}
    missing_series_ids = sorted(set(expected_series_ids) - observed_series_ids)
    period_regex = re.compile(required_period_pattern)
    invalid_period_rows = [
        row
        for row in rows
        if not _is_month_start(str(row.get("observed_month", "")))
        or not period_regex.fullmatch(str(row.get("period", "")))
    ]
    non_numeric_rows = [
        row for row in rows if not isinstance(row.get("value"), int | float)
    ]
    out_of_range_rows = [
        row
        for row in rows
        if isinstance(row.get("value"), int | float)
        and not unemployment_rate_min <= float(row["value"]) <= unemployment_rate_max
    ]
    return [
        make_source_identity_validation_result(
            pipeline_run_id=pipeline_run_id,
            source_identity=source_identity,
            source_resource_name=BLS_LAUS_RESOURCE_NAME,
            check_definition=BLS_EXPECTED_SERIES,
            passed=missing_series_ids == [],
            expected_value=list(expected_series_ids),
            observed_value={"missing_series_ids": missing_series_ids},
            failed_message="BLS LAUS response is missing expected series IDs.",
        ),
        make_source_identity_validation_result(
            pipeline_run_id=pipeline_run_id,
            source_identity=source_identity,
            source_resource_name=BLS_LAUS_RESOURCE_NAME,
            check_definition=BLS_MONTHLY_PERIODS,
            passed=invalid_period_rows == [],
            expected_value="monthly M01-M12 rows with month-start dates",
            observed_value={"invalid_rows": len(invalid_period_rows)},
            failed_message="BLS LAUS response contains invalid monthly periods.",
        ),
        make_source_identity_validation_result(
            pipeline_run_id=pipeline_run_id,
            source_identity=source_identity,
            source_resource_name=BLS_LAUS_RESOURCE_NAME,
            check_definition=BLS_NUMERIC_VALUES,
            passed=non_numeric_rows == [],
            expected_value="numeric values",
            observed_value={"non_numeric_rows": len(non_numeric_rows)},
            failed_message="BLS LAUS response contains non-numeric values.",
        ),
        make_source_identity_validation_result(
            pipeline_run_id=pipeline_run_id,
            source_identity=source_identity,
            source_resource_name=BLS_LAUS_RESOURCE_NAME,
            check_definition=BLS_VALUE_RANGE,
            passed=out_of_range_rows == [],
            expected_value={
                "min": unemployment_rate_min,
                "max": unemployment_rate_max,
            },
            observed_value={"out_of_range_rows": len(out_of_range_rows)},
            failed_message="BLS LAUS response contains unemployment rates outside configured bounds.",
        ),
    ]


def _is_month_start(value: str) -> bool:
    """Return whether an ISO date string represents the first day of a month."""
    try:
        parsed_date = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed_date.day == 1
