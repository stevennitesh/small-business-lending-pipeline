"""Check saved local exports and write small, identifier-free Desktop references."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, UTC
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

try:
    from scripts.repo_bootstrap import add_repo_root_to_path
except ModuleNotFoundError:
    from repo_bootstrap import add_repo_root_to_path

add_repo_root_to_path()

import duckdb

from pipelines.powerbi.export_contract import validate_powerbi_export_columns
from pipelines.powerbi.export_schema import BI_EXPORT_TABLES


def checksum(path: Path) -> str:
    """Hash without loading large files into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _rows(connection: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    result = connection.execute(sql)
    keys = [item[0] for item in result.description]
    return [dict(zip(keys, row, strict=True)) for row in result.fetchall()]


def check_csv(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    path: Path,
    column_types: dict[str, str],
    grain: list[str],
) -> dict:
    """Reject schema, lexical type, grain or warehouse/export divergence."""
    with path.open(newline="", encoding="utf-8") as stream:
        header = next(csv.reader(stream))
    if len(header) != len(set(header)):
        raise ValueError(f"{table}: duplicate CSV headers")
    validate_powerbi_export_columns(table, set(header))
    schema = connection.execute(f"describe {_quote(table)}").fetchall()
    if header != [row[0] for row in schema]:
        raise ValueError(f"{table}: CSV schema/order differs from warehouse")
    missing_types = set(header) - column_types.keys()
    if missing_types:
        raise ValueError(f"{table}: missing Power Query types: {sorted(missing_types)}")
    csv_view = f"csv_{table}"
    connection.register(
        csv_view, connection.read_csv(str(path), header=True, all_varchar=True)
    )
    checks = []
    casts = []
    leading_zero_columns = {}
    for name, sql_type, *_ in schema:
        field = _quote(name)
        m_type = column_types[name]
        expected = (
            "datetimezone"
            if sql_type == "VARCHAR" and name.endswith("_at_utc")
            else "date"
            if sql_type == "VARCHAR" and name == "latest_ingestion_date"
            else "text"
            if sql_type == "VARCHAR"
            else "logical"
            if sql_type == "BOOLEAN"
            else "date"
            if sql_type == "DATE"
            else "datetimezone"
            if sql_type.startswith("TIMESTAMP")
            else "number"
        )
        if m_type != expected:
            raise ValueError(
                f"{table}.{name}: Power Query {m_type}, expected {expected}"
            )
        if m_type != "text":
            lexical_type = {
                "logical": "boolean",
                "date": "date",
                "datetimezone": "timestamptz",
                "number": sql_type,
            }[m_type]
            checks.append(
                f"count(*) filter(where {field} is not null and "
                f"try_cast({field} as {lexical_type}) is null)"
            )
        casts.append(f"cast({field} as {sql_type}) as {field}")
        if m_type == "text" and name in {"state_key", "state_fips"}:
            count = connection.execute(
                f"select count(*) from {_quote(csv_view)} where {field} like '0%'"
            ).fetchone()[0]
            leading_zero_columns[name] = count
    if checks and any(
        connection.execute(
            f"select {', '.join(checks)} from {_quote(csv_view)}"
        ).fetchone()
    ):
        raise ValueError(f"{table}: CSV contains an invalid typed value")
    typed_view = f"typed_{table}"
    connection.execute(
        f"create or replace temp view {_quote(typed_view)} as "
        f"select {', '.join(casts)} from {_quote(csv_view)}"
    )
    fields = ", ".join(_quote(key) for key in grain)
    duplicates = connection.execute(
        f"select count(*) from (select {fields} from {_quote(typed_view)} "
        f"group by {fields} having count(*) > 1)"
    ).fetchone()[0]
    null_keys = connection.execute(
        f"select count(*) from {_quote(typed_view)} where "
        + " or ".join(f"{_quote(key)} is null" for key in grain)
    ).fetchone()[0]
    differences = connection.execute(
        f"select count(*) from ((select * from {_quote(table)} except all "
        f"select * from {_quote(typed_view)}) union all "
        f"(select * from {_quote(typed_view)} except all "
        f"select * from {_quote(table)}))"
    ).fetchone()[0]
    count = connection.execute(f"select count(*) from {_quote(typed_view)}").fetchone()[
        0
    ]
    if not count or duplicates or null_keys or differences:
        raise ValueError(
            f"{table}: rows={count}, duplicate_grains={duplicates}, "
            f"null_keys={null_keys}, warehouse_differences={differences}"
        )
    return {
        "rows": count,
        "columns": len(header),
        "grain": grain,
        "duplicate_grains": duplicates,
        "null_grain_keys": null_keys,
        "warehouse_differences": differences,
        "leading_zero_text_values": leading_zero_columns,
        "sha256": checksum(path),
    }


def _grain(table: dict) -> list[str]:
    name = table["name"]
    special = {
        "bi_pipeline_health": ["pipeline_run_ids"],
        "bi_source_freshness": [
            "source_system",
            "source_dataset",
            "source_resource_name",
        ],
        "bi_state_filter": ["state_key"],
        "bi_year_filter": ["year"],
        "bi_loan_program_filter": ["loan_program_key"],
        "bi_naics_filter": ["naics_key"],
        "bi_lender_filter": ["lender_key"],
    }
    if name in special:
        return special[name]
    keys = ["state_key", "year" if table["grain"] == "state-year" else "approval_year"]
    for suffix, key in (
        ("-naics", "naics_key"),
        ("-program", "loan_program_key"),
        ("-lender", "lender_key"),
        ("-loan_status_group", "loan_status_group"),
    ):
        if table["grain"].endswith(suffix):
            keys.append(key)
    return keys


def _raw_reference(connection: duckdb.DuckDBPyConnection) -> None:
    """Calculate from raw fields independently of staging cleaning/macros."""
    connection.execute("""
        create or replace temp view readiness_raw as
        with selected as (
            select pipeline_run_id, resource_name, raw_uri
            from stg_ingestion_manifest where is_latest_successful_snapshot
              and validation_status = 'passed' and source_system = 'sba'
        ), source as (
            select '7a' as program, projectstate, approvaldate, grossapproval,
                   bankname as source_name, sbaguaranteedapproval as guarantee,
                   null::varchar as third_party, loanstatus, locationid,
                   pipeline_run_id, source_resource_name, raw_uri
            from raw.raw_sba_7a_foia
            union all
            select '504', projectstate, approvaldate, grossapproval,
                   thirdpartylender_name, null::varchar, thirdpartydollars,
                   loanstatus, locationid, pipeline_run_id, source_resource_name, raw_uri
            from raw.raw_sba_504_foia
        ), parsed as (
            select source.*, state.state_key,
                   coalesce(try_strptime(trim(approvaldate), '%m/%d/%Y')::date,
                            try_strptime(trim(approvaldate), '%Y-%m-%d')::date) as calendar_date,
                   try_cast(replace(replace(grossapproval, '$', ''), ',', '')
                       as decimal(18,2)) as source_amount,
                   try_cast(replace(replace(guarantee, '$', ''), ',', '')
                       as decimal(18,2)) as source_guarantee,
                   try_cast(replace(replace(third_party, '$', ''), ',', '')
                       as decimal(18,2)) as source_third_party
            from source join selected on source.pipeline_run_id = selected.pipeline_run_id
              and source.source_resource_name = selected.resource_name
              and source.raw_uri = selected.raw_uri
            left join bi_state_filter state on upper(trim(source.projectstate)) = state.state_abbr
        )
        select *, extract(year from calendar_date)::integer as year,
               case when source_amount >= 0 then source_amount end as amount,
               case when source_guarantee >= 0 then source_guarantee end as guarantee_amount,
               case when source_third_party >= 0 then source_third_party end as third_party_amount
        from parsed
    """)
    connection.execute("""
        create or replace temp view readiness_eligible as
        select * from fact_sba_loans
        where project_state_key is not null and approval_year is not null
    """)


def _reconcile(connection: duckdb.DuckDBPyConnection) -> dict:
    comparisons = {}
    for year in (2023, 2025, 2026):
        population = f"approval_year <= {year}"
        fact = connection.execute(
            f"select sum(gross_approval_amount), count(gross_approval_amount), count(*) "
            f"from readiness_eligible where {population}"
        ).fetchone()
        raw = connection.execute(
            "select sum(amount), count(amount), count(*) from readiness_raw "
            f"where state_key is not null and year <= {year}"
        ).fetchone()
        exported = connection.execute(
            "select sum(total_approved_loan_amount), sum(approval_amount_coverage_count), "
            f"sum(loan_count) from typed_bi_executive_overview where year <= {year}"
        ).fetchone()
        if fact != raw or fact != exported:
            raise ValueError(f"through {year}: raw, fact and CSV components differ")
        comparisons[f"through_{year}"] = {
            "dollars": fact[0],
            "known_amount_records": fact[1],
            "records": fact[2],
            "average": fact[0] / fact[1],
            "raw_fact_csv_match": True,
        }
    # Compare independently derived category/financing components across the full
    # saved reporting population. No observed row count is a production expectation.
    checks = {
        "program": """
            select loan_program_key, sum(gross_approval_amount),
                   count(gross_approval_amount), count(*) from readiness_eligible group by 1
        """,
        "industry": """
            select naics_key, sum(gross_approval_amount),
                   count(gross_approval_amount), count(*) from readiness_eligible group by 1
        """,
        "lender": """
            select lender_key, sum(gross_approval_amount),
                   count(gross_approval_amount), count(*) from readiness_eligible
            where lender_key != 'UNKNOWN' group by 1
        """,
    }
    for category, sql in checks.items():
        table, key = {
            "program": ("bi_program_mix", "loan_program_key"),
            "industry": ("bi_industry_mix", "naics_key"),
            "lender": ("bi_lender_mix", "lender_key"),
        }[category]
        difference = connection.execute(
            f"with direct as ({sql}), exported as (select {key}, "
            "sum(total_approved_loan_amount), sum(approval_amount_coverage_count), "
            f"sum(loan_count) from typed_{table} group by 1) "
            "select count(*) from ((select * from direct except all select * from exported) "
            "union all (select * from exported except all select * from direct))"
        ).fetchone()[0]
        if difference:
            raise ValueError(f"{category}: fact and CSV components differ")
        comparisons[f"{category}_components_match"] = True
    direct = connection.execute("""
        select
            sum(third_party_amount) filter(where program='504' and amount is not null and third_party_amount is not null),
            sum(amount) filter(where program='504' and amount is not null and third_party_amount is not null),
            count(*) filter(where program='504' and amount is not null and third_party_amount is not null),
            count(*) filter(where program='504'),
            sum(guarantee_amount) filter(where program='7a' and amount is not null and guarantee_amount is not null),
            sum(amount) filter(where program='7a' and amount is not null and guarantee_amount is not null),
            count(*) filter(where program='7a' and amount is not null and guarantee_amount is not null),
            count(*) filter(where program='7a')
        from readiness_raw where state_key is not null and year is not null
    """).fetchone()
    exported = connection.execute("""
        select sum(paired_504_third_party_dollars), sum(paired_504_approval_amount),
               sum(paired_504_coverage_count), sum(program_504_loan_count),
               sum(paired_7a_guaranteed_amount), sum(paired_7a_approval_amount),
               sum(paired_7a_coverage_count), sum(program_7a_loan_count)
        from typed_bi_lending_terms_pricing
    """).fetchone()
    if direct != exported:
        raise ValueError("paired financing: raw and CSV components differ")
    comparisons["raw_paired_financing_components_match"] = True
    return comparisons


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def _source_samples(connection: duckdb.DuckDBPyConnection) -> list[dict]:
    """Trace small actual rows privately; retain only field-map/count evidence."""
    checks = []
    for label, condition in {
        "7a_known_amount": "program='7a' and amount > 0",
        "504_known_amount": "program='504' and amount > 0",
        "negative_amount_becomes_unknown": "source_amount < 0",
        "zero_amount_remains_known": "amount = 0",
        "canceled_or_not_funded_retained": "upper(trim(loanstatus)) in ('CANCLD','NOT FUNDED')",
        "unknown_reporting_name": "nullif(nullif(upper(trim(source_name)),''),'UNKNOWN') is null",
    }.items():
        scope = "year is not null"
        if label != "zero_amount_remains_known":
            scope += " and state_key is not null"
        sample = connection.execute(
            "select program, locationid, calendar_date, amount, source_name, raw_uri, "
            "loanstatus, guarantee_amount, third_party_amount, state_key is not null "
            "from readiness_raw "
            f"where {scope} and {condition} "
            "order by raw_uri,locationid,calendar_date limit 1"
        ).fetchone()
        if sample is None:
            checks.append({"case": label, "sample_available": False})
            continue
        (
            program,
            lender_id,
            approval,
            amount,
            name,
            uri,
            status,
            guarantee,
            third_party,
            mapped_geography,
        ) = sample
        # Lender names are compared privately. No row keys, borrower fields or
        # source values leave this function, even in the error path.
        normalized_name = re.sub(r"\s+", " ", (name or "").strip()).upper() or None
        if normalized_name == "UNKNOWN":
            normalized_name = None
        matches = connection.execute(
            "select count(*) from stg_sba_loans where loan_program=? "
            "and source_lender_id is not distinct from ? and approval_date=? "
            "and gross_approval_amount is not distinct from ? "
            "and lender_name is not distinct from ? and raw_uri=? "
            "and loan_status is not distinct from ? "
            "and sba_guaranteed_approval_amount is not distinct from ? "
            "and third_party_dollars is not distinct from ?",
            [
                program,
                (lender_id or "").strip() or None,
                approval,
                amount,
                normalized_name,
                uri,
                (status or "").strip() or None,
                guarantee,
                third_party,
            ],
        ).fetchone()[0]
        if not matches:
            raise ValueError(f"Private raw/staging field mapping failed: {label}")
        checks.append(
            {
                "case": label,
                "sample_available": True,
                "matching_staged_records": matches,
                "program": program,
                "eligible_for_state_reporting": mapped_geography,
                "mapping": {
                    "LocationID": "source_lender_id (SBA lender, not loan identity)",
                    "ApprovalDate": "calendar approval_date",
                    "GrossApproval": "gross_approval_amount (negative => unknown; zero => known)",
                    "BankName"
                    if program == "7a"
                    else "ThirdPartyLender_Name": "normalized reporting lender_name",
                    "SBAGuaranteedApproval"
                    if program == "7a"
                    else "ThirdPartyDollars": "nonnegative program financing component",
                    "LoanStatus": "retained historical approval status",
                },
            }
        )
    return checks


def verify(warehouse: Path, export_dir: Path, reference_sql: Path) -> dict:
    """Read local data, validate all exports, and return compact aggregate proof."""
    contract = json.loads(Path("powerbi/lending_dashboard_model.json").read_text())
    column_types = dict(
        re.findall(
            r"^\s*(\w+) = type (\w+)",
            Path("powerbi/power_query/local_csv_queries.pq").read_text(),
            re.MULTILINE,
        )
    )
    proof = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "warehouse": str(warehouse),
        "export_dir": str(export_dir),
        "semantic_version": contract["semantic_version"],
        "limits": "Local saved data and static source contracts; no Desktop/DAX/M or live cloud certification",
        "csv_checks": {},
        "relationship_checks": [],
    }
    with duckdb.connect(str(warehouse), read_only=True) as connection:
        connection.execute("set threads=2")
        tables = {item["name"]: item for item in contract["tables"]}
        if set(tables) != set(BI_EXPORT_TABLES):
            raise ValueError("JSON and CSV table sets differ")
        for name in BI_EXPORT_TABLES:
            proof["csv_checks"][name] = check_csv(
                connection,
                name,
                export_dir / f"{name}.csv",
                column_types,
                _grain(tables[name]),
            )
        for relationship in contract["relationships"]:
            parent, parent_key = relationship["from"].split(".")
            child, child_key = relationship["to"].split(".")
            unmatched = connection.execute(
                f"select count(*) from typed_{child} c left join typed_{parent} p "
                f"on c.{_quote(child_key)} = p.{_quote(parent_key)} "
                f"where c.{_quote(child_key)} is not null and p.{_quote(parent_key)} is null"
            ).fetchone()[0]
            if unmatched:
                raise ValueError(f"{relationship}: {unmatched} unmatched CSV keys")
            proof["relationship_checks"].append(
                {**relationship, "unmatched_keys": unmatched}
            )
        _raw_reference(connection)
        proof["reconciliation"] = _reconcile(connection)
        proof["private_source_sample_aggregate_proof"] = _source_samples(connection)
        proof["selected_snapshots"] = _rows(
            connection,
            """
            select source_system, dataset_name, resource_name, pipeline_run_id,
                   ingestion_date, extracted_at_utc, raw_uri, sha256_checksum,
                   row_count, validation_status
            from stg_ingestion_manifest where is_latest_successful_snapshot
            order by source_system, resource_name
        """,
        )
        for snapshot in proof["selected_snapshots"]:
            snapshot["local_checksum_matches_manifest"] = (
                checksum(Path(snapshot["raw_uri"])) == snapshot["sha256_checksum"]
            )
            if not snapshot["local_checksum_matches_manifest"]:
                raise ValueError("Selected raw checksum differs from manifest")
        proof["source_freshness"] = _rows(
            connection,
            "select * from bi_source_freshness order by source_system, source_resource_name",
        )
        proof["pipeline_health"] = _rows(connection, "select * from bi_pipeline_health")
        proof["references"] = {}
        sections = re.split(
            r"^-- reference: ([a-z0-9_]+)\s*$",
            reference_sql.read_text(),
            flags=re.MULTILINE,
        )
        for index in range(1, len(sections), 2):
            proof["references"][sections[index]] = _rows(
                connection, sections[index + 1]
            )
        proof["reference_sql_sha256"] = checksum(reference_sql)
    return proof


def main() -> None:
    """Verify current saved outputs; write JSON containing aggregates only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--duckdb-path",
        type=Path,
        default=Path("data/warehouse/small_business_lending.duckdb"),
    )
    parser.add_argument("--export-dir", type=Path, default=Path("data/exports/powerbi"))
    parser.add_argument(
        "--reference-sql", type=Path, default=Path("powerbi/desktop_reference.sql")
    )
    parser.add_argument(
        "--output", type=Path, default=Path(".tmp/pre-pbix/readiness.json")
    )
    args = parser.parse_args()
    proof = verify(args.duckdb_path, args.export_dir, args.reference_sql)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(proof, indent=2, default=_json_default) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "tables": len(proof["csv_checks"]),
                "relationships": len(proof["relationship_checks"]),
                "reconciliation": proof["reconciliation"],
            },
            default=_json_default,
        )
    )


if __name__ == "__main__":
    main()
