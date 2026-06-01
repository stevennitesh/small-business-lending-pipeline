"""Small source-shaped payloads used by fixture-mode extraction."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any

from pipelines.extract.bls_laus_periods import parse_monthly_period


@dataclass(frozen=True)
class FixturePayload:
    """Small raw payload plus metadata needed to write a fixture manifest."""

    payload: bytes
    row_count: int
    file_format: str
    schema_fields: list[str]


def sba_7a_fixture_payload() -> FixturePayload:
    """Build a one-row SBA 7(a) CSV fixture payload."""
    rows = [sba_7a_row()]
    return FixturePayload(
        payload=csv_bytes(rows),
        row_count=len(rows),
        file_format="csv",
        schema_fields=list(rows[0]),
    )


def sba_504_fixture_payload() -> FixturePayload:
    """Build a one-row SBA 504 CSV fixture payload."""
    rows = [sba_504_row()]
    return FixturePayload(
        payload=csv_bytes(rows),
        row_count=len(rows),
        file_format="csv",
        schema_fields=list(rows[0]),
    )


def census_bds_fixture_payload() -> FixturePayload:
    """Build a Census BDS JSON fixture with two state-year rows."""
    payload = [
        [
            "NAME",
            "YEAR",
            "ESTAB",
            "ESTABS_ENTRY",
            "ESTABS_ENTRY_RATE",
            "ESTABS_EXIT",
            "ESTABS_EXIT_RATE",
            "FIRM",
            "JOB_CREATION",
            "JOB_DESTRUCTION",
            "time",
            "state",
        ],
        [
            "Alabama",
            "2026",
            "10",
            "2",
            "20.0",
            "1",
            "10.0",
            "8",
            "30",
            "15",
            "2026",
            "01",
        ],
        [
            "Illinois",
            "2026",
            "20",
            "3",
            "15.0",
            "2",
            "10.0",
            "15",
            "40",
            "20",
            "2026",
            "17",
        ],
    ]
    return FixturePayload(
        payload=json_bytes(payload),
        row_count=len(payload) - 1,
        file_format="json",
        schema_fields=payload[0],
    )


def bls_laus_fixture_payload() -> FixturePayload:
    """Build a BLS LAUS JSON fixture with normalized state-month rows."""
    payload = {
        "normalized_rows": [
            bls_row(
                "LASST010000000000003",
                "01",
                "AL",
                "Alabama",
                "2025",
                "M01",
                3.4,
            ),
            bls_row(
                "LASST010000000000003",
                "01",
                "AL",
                "Alabama",
                "2026",
                "M01",
                3.1,
            ),
            bls_row(
                "LASST170000000000003",
                "17",
                "IL",
                "Illinois",
                "2025",
                "M01",
                4.5,
            ),
            bls_row(
                "LASST170000000000003",
                "17",
                "IL",
                "Illinois",
                "2026",
                "M01",
                4.2,
            ),
        ]
    }
    return FixturePayload(
        payload=json_bytes(payload),
        row_count=len(payload["normalized_rows"]),
        file_format="json",
        schema_fields=list(payload["normalized_rows"][0]),
    )


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Serialize fixture dictionaries as UTF-8 CSV bytes."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def json_bytes(payload: Any) -> bytes:
    """Serialize fixture payloads as newline-terminated JSON bytes."""
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def sba_7a_row() -> dict[str, Any]:
    """Return a representative SBA 7(a) source row for fixture CSV output."""
    return {
        "asofdate": "3/31/2026",
        "program": "7A",
        "locationid": "1",
        "borrname": "Fixture 7A LLC",
        "borrstreet": "1 Main St",
        "borrcity": "Birmingham",
        "borrstate": "AL",
        "borrzip": "35203",
        "bankname": "Fixture Bank, Inc.",
        "bankfdicnumber": "123",
        "bankncuanumber": "",
        "bankstreet": "2 Bank St",
        "bankcity": "Birmingham",
        "bankstate": "AL",
        "bankzip": "35203",
        "grossapproval": "1000",
        "sbaguaranteedapproval": "750",
        "approvaldate": "1/15/2026",
        "approvalfy": "2026",
        "firstdisbursementdate": "2/1/2026",
        "processingmethod": "Preferred Lenders Program",
        "subprogram": "Guaranty",
        "initialinterestrate": "6",
        "fixedorvariableinterestind": "V",
        "terminmonths": "120",
        "naicscode": "541611",
        "naicsdescription": "Administrative Management",
        "franchisecode": "",
        "franchisename": "",
        "projectcounty": "JEFFERSON",
        "projectstate": "AL",
        "sbadistrictoffice": "ALABAMA DISTRICT OFFICE",
        "congressionaldistrict": "7",
        "businesstype": "CORPORATION",
        "businessage": "Existing",
        "loanstatus": "PIF",
        "paidinfulldate": "",
        "chargeoffdate": "",
        "grosschargeoffamount": "0",
        "revolverstatus": "FALSE",
        "jobssupported": "4",
        "collateralind": "TRUE",
        "soldsecmrktind": "Y",
    }


def sba_504_row() -> dict[str, Any]:
    """Return a representative SBA 504 source row for fixture CSV output."""
    return {
        "asofdate": "3/31/2026",
        "program": "504",
        "locationid": "2",
        "borrname": "Fixture 504 Inc.",
        "borrstreet": "10 Market St",
        "borrcity": "Chicago",
        "borrstate": "IL",
        "borrzip": "60601",
        "cdc_name": "Fixture CDC",
        "cdc_street": "20 CDC St",
        "cdc_city": "Chicago",
        "cdc_state": "IL",
        "cdc_zip": "60601",
        "thirdpartylender_name": "Third Party Bank",
        "thirdpartylender_city": "Chicago",
        "thirdpartylender_state": "IL",
        "thirdpartydollars": "2500",
        "grossapproval": "3000",
        "approvaldate": "2/20/2026",
        "approvalfy": "2026",
        "firstdisbursementdate": "3/1/2026",
        "processingmethod": "504 Basic",
        "subprogram": "Sec. 504",
        "terminmonths": "240",
        "naicscode": "721110",
        "naicsdescription": "Hotels",
        "franchisecode": "",
        "franchisename": "",
        "projectcounty": "COOK",
        "projectstate": "IL",
        "sbadistrictoffice": "ILLINOIS DISTRICT OFFICE",
        "congressionaldistrict": "1",
        "businesstype": "CORPORATION",
        "businessage": "Existing",
        "loanstatus": "PIF",
        "paidinfulldate": "",
        "chargeoffdate": "",
        "grosschargeoffamount": "0",
        "jobssupported": "8",
        "collateralind": "TRUE",
    }


def bls_row(
    series_id: str,
    state_fips: str,
    state_abbr: str,
    state_name: str,
    year: str,
    period: str,
    value: float,
) -> dict[str, Any]:
    """Build one normalized BLS LAUS fixture row from a BLS monthly period."""
    observed_month = parse_monthly_period(year, period)
    if observed_month is None:
        raise ValueError(f"Invalid fixture BLS monthly period: {period}")
    return {
        "series_id": series_id,
        "state_fips": state_fips,
        "state_abbr": state_abbr,
        "state_name": state_name,
        "year": int(year),
        "period": period,
        "observed_month": observed_month.isoformat(),
        "value": value,
        "footnotes": [],
    }
