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
    BLS_ROW_GRAIN,
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
    publisher_omissions: frozenset[tuple[int, int]] = frozenset(),
    source_identity: SourceIdentity = DEFAULT_BLS_LAUS_IDENTITY,
) -> list[ValidationResult]:
    """Validate BLS LAUS series coverage, monthly periods, and rate values."""
    raw_rows = payload.get("normalized_rows", [])
    shape_valid = isinstance(raw_rows, list) and all(
        isinstance(row, dict) for row in raw_rows
    )
    rows = raw_rows if shape_valid else []
    row_keys = [
        (str(row.get("series_id")), str(row.get("observed_month"))) for row in rows
    ]
    observed_series_ids = {str(row.get("series_id")) for row in rows}
    missing_series_ids = sorted(set(expected_series_ids) - observed_series_ids)
    unexpected_series_ids = sorted(observed_series_ids - set(expected_series_ids))
    period_regex = re.compile(required_period_pattern)
    invalid_period_rows = [
        row
        for row in rows
        if not _is_matching_month(row)
        or not period_regex.fullmatch(str(row.get("period", "")))
    ]
    non_numeric_rows = [
        row
        for row in rows
        if type(row.get("value")) not in (int, float)
        and not _is_declared_publisher_missing(row, publisher_omissions)
    ]
    out_of_range_rows = [
        row
        for row in rows
        if type(row.get("value")) in (int, float)
        and not unemployment_rate_min <= float(row["value"]) <= unemployment_rate_max
    ]
    return [
        make_source_identity_validation_result(
            pipeline_run_id=pipeline_run_id,
            source_identity=source_identity,
            source_resource_name=BLS_LAUS_RESOURCE_NAME,
            check_definition=BLS_ROW_GRAIN,
            passed=shape_valid and len(row_keys) == len(set(row_keys)),
            expected_value="unique series-month rows",
            observed_value={
                "valid_shape": shape_valid,
                "duplicate_rows": len(row_keys) - len(set(row_keys)),
            },
            failed_message="BLS LAUS rows have invalid shape or duplicate series-month observations.",
        ),
        make_source_identity_validation_result(
            pipeline_run_id=pipeline_run_id,
            source_identity=source_identity,
            source_resource_name=BLS_LAUS_RESOURCE_NAME,
            check_definition=BLS_EXPECTED_SERIES,
            passed=not missing_series_ids and not unexpected_series_ids,
            expected_value=list(expected_series_ids),
            observed_value={
                "missing_series_ids": missing_series_ids,
                "unexpected_series_ids": unexpected_series_ids,
            },
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
            expected_value="numeric values or policy-declared, X-footnoted '-' placeholders",
            observed_value={
                "non_numeric_rows": len(non_numeric_rows),
                "publisher_missing_rows": sum(
                    _is_declared_publisher_missing(row, publisher_omissions)
                    for row in rows
                ),
            },
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


def _is_declared_publisher_missing(
    row: dict, omissions: frozenset[tuple[int, int]]
) -> bool:
    """Preserve official missing observations without accepting malformed rates."""
    if row.get("value") != "-" or not _is_matching_month(row):
        return False
    month = date.fromisoformat(str(row["observed_month"]))
    footnotes = row.get("footnotes")
    return (
        (month.year, month.month) in omissions
        and isinstance(footnotes, list)
        and any(
            isinstance(note, dict)
            and note.get("code") == "X"
            and bool(note.get("text"))
            for note in footnotes
        )
    )


def _is_matching_month(row: dict) -> bool:
    """Require the period, year and month-start date to identify one month."""
    try:
        parsed_date = date.fromisoformat(str(row.get("observed_month", "")))
        return (
            parsed_date.day == 1
            and str(row.get("period")) == f"M{parsed_date.month:02d}"
            and int(row.get("year", parsed_date.year)) == parsed_date.year
        )
    except (TypeError, ValueError):
        return False
