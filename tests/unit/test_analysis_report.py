"""Preserve population and denominator meaning in published aggregate charts."""

from copy import deepcopy
from decimal import Decimal
import json

import pytest

from scripts.render_analysis_report import (
    TABLES,
    annual_change_phrase,
    annual_comparison,
    build_analysis,
    checksum,
    geography_scope,
    public_verification,
    read_checked_exports,
    selected_period_note,
    text_checksum,
    totals,
    write_reader_results,
)


def row(state, amount, records=20, known=20, year=2025, **extra):
    return {
        "state_key": state,
        "state_name": state,
        "approval_year": str(year),
        "total_approved_loan_amount": str(amount),
        "loan_count": str(records),
        "approval_amount_coverage_count": str(known),
        "is_full_calendar_year": "true",
        **extra,
    }


@pytest.fixture
def tables():
    current = [row("01", 1000, known=10), row("02", 2000)]
    sources = [
        {
            "source_system": source,
            "latest_observation_date": "2026-03-31",
            "observation_age_days": "188",
            "freshness_status": "latest_published",
            "freshness_reason": "latest_verified_release",
            "publication_reference_date": "2023-03-12"
            if source == "census"
            else "2026-03-31",
            "publication_date": "2025-09-25" if source == "census" else "",
            "publication_verified_date": "2026-10-05",
            "publication_source_url": f"https://example.test/{source}",
            "publication_cadence": {
                "sba": "quarterly",
                "census": "annual",
                "bls": "monthly",
            }[source],
            "publication_status": "latest_published",
            "next_scheduled_release_date": "2026-10-20" if source == "bls" else "",
            "latest_extracted_at_utc": "2026-06-02T05:00:00Z",
            "is_latest_successful_snapshot": "true",
            "freshness_checked_at_utc": "2026-10-05 00:35:34",
        }
        for source in ("sba", "census", "bls")
    ]
    lenders = [
        row(state, amount, records=1, known=1, lender_key=key, lender_name=key)
        for state, key, amount in (
            ("01", "x", 700),
            ("01", "y", 200),
            ("01", "u", 100),
            ("02", "x", 100),
            ("02", "y", 300),
            ("02", "z", 500),
            ("02", "w", 400),
            ("02", "v", 300),
            ("02", "t", 200),
            ("02", "s", 200),
        )
    ]
    return {
        "bi_state_lending_trends": current
        + [row("01", 800, year=2024), row("02", 1200, year=2024)],
        "bi_regional_business_health": [
            dict(
                row(
                    state,
                    amount,
                    records=records,
                    year=2023,
                    establishment_count=str(stock),
                    is_comparable_context="true",
                    has_matched_establishment_population="true",
                ),
                year="2023",
            )
            for state, amount, records, stock in (
                ("01", 900, 10, 1000),
                ("02", 800, 2, 500),
            )
        ],
        "bi_program_mix": [
            {**item, "loan_program_key": "7a", "loan_program_name": "SBA 7(a)"}
            for item in current
        ],
        "bi_industry_mix": [
            row(
                "01",
                800,
                records=19,
                known=9,
                naics_key="72",
                naics_sector_name="Food",
                is_known_industry="true",
            ),
            row(
                "01",
                200,
                records=1,
                known=1,
                naics_key="UNKNOWN",
                naics_sector_name="Unknown",
                is_known_industry="false",
            ),
            row(
                "02",
                2000,
                naics_key="72",
                naics_sector_name="Food",
                is_known_industry="true",
            ),
        ],
        "bi_lender_mix": lenders,
        "bi_source_freshness": sources,
    }


def test_mean_uses_known_amount_count_and_retains_unknown_records():
    result = totals(
        [row("01", 100, records=3, known=2), row("02", 900, records=1, known=1)]
    )
    assert result["records"] == 4
    assert result["average"] == Decimal(1000) / 3
    assert totals([row("01", 0, records=2, known=0)])["average"] is None
    assert totals([row("01", 0, records=1, known=1)])["average"] == 0


def test_annual_change_rejects_absent_states_and_partial_years():
    assert annual_comparison([row("01", 110)], [row("01", 100)]) == Decimal("0.1")
    with pytest.raises(ValueError, match="different state populations"):
        annual_comparison([row("01", 110)], [row("01", 100), row("02", 900)])
    with pytest.raises(ValueError, match="partial year"):
        annual_comparison(
            [row("01", 110, is_full_calendar_year="false")], [row("01", 100)]
        )


@pytest.mark.parametrize(
    ("current_amount", "expected_change", "direction"),
    [(110, "0.1", "increased"), (90, "-0.1", "decreased"), (100, "0", "unchanged")],
)
def test_annual_change_description_tracks_computed_direction(
    current_amount, expected_change, direction
):
    change = annual_comparison([row("01", current_amount)], [row("01", 100)])
    assert change == Decimal(expected_change)
    description = annual_change_phrase(change)
    assert direction in description
    if change:
        assert "10.00%" in description
        assert "-10.00%" not in description
    else:
        assert "increased" not in description
        assert "decreased" not in description
        assert "%" not in description


def test_known_industry_denominator_and_aggregate_lender_ranking(tables):
    result = build_analysis(tables, 2025, 2023, 2024)
    assert result["headline"]["average"] == Decimal(100)
    assert result["headline"]["growth"] == Decimal("0.5")
    assert result["industry_coverage"] == Decimal(2800) / 3000
    assert result["industries"][0]["share"] == 1
    assert result["unknown_industry"]["amount"] == 200
    assert result["lenders"][0]["key"] == "x"
    assert result["lenders"][0]["amount"] == 800
    assert result["top_five_lender_share"] == Decimal(2500) / 3000
    assert result["geography"][0]["intensity"] == 10
    assert result["geography"][1]["intensity"] == 4


def test_context_cannot_silently_use_incomplete_or_different_populations(tables):
    incomplete = deepcopy(tables)
    incomplete["bi_regional_business_health"][0]["is_comparable_context"] = "false"
    with pytest.raises(ValueError, match="complete same-year"):
        build_analysis(incomplete, 2025, 2023, 2024)
    tables["bi_regional_business_health"].pop()
    with pytest.raises(ValueError, match="same state population"):
        build_analysis(tables, 2025, 2023, 2024)


def test_category_components_must_reconcile_records_and_known_amounts(tables):
    tables["bi_program_mix"][0]["approval_amount_coverage_count"] = "20"
    with pytest.raises(ValueError, match="known amounts do not reconcile"):
        build_analysis(tables, 2025, 2023, 2024)


def test_unclassified_history_cannot_publish_a_known_industry_ranking(tables):
    """Historical source coverage may have no classified amounts to rank."""
    for item in tables["bi_industry_mix"]:
        item["is_known_industry"] = "false"
    with pytest.raises(ValueError, match="positive known-industry dollars"):
        build_analysis(tables, 2025, 2023, 2024)


def test_export_hashes_bind_charts_to_checked_bytes(tmp_path):
    checks = {}
    for table in TABLES:
        path = tmp_path / f"{table}.csv"
        path.write_text("state_key,value\n01,1\n", encoding="utf-8")
        checks[table] = {
            "sha256": checksum(path),
            "rows": 1,
            "warehouse_differences": 0,
            "duplicate_grains": 0,
            "null_grain_keys": 0,
        }
    evidence = tmp_path / "readiness.json"
    evidence.write_text(json.dumps({"csv_checks": checks}), encoding="utf-8")
    exports, _ = read_checked_exports(tmp_path, evidence)
    assert exports[TABLES[0]][0]["state_key"] == "01"
    (tmp_path / f"{TABLES[0]}.csv").write_text(
        "state_key,value\n01,2\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="changed since readiness"):
        read_checked_exports(tmp_path, evidence)


def test_reader_exposes_publication_dates_without_inventing_unknown_dates(
    tables, tmp_path
):
    """Readers see the reference year and publication separately, with age only as context."""
    census = tables["bi_source_freshness"][1]
    census.update(latest_observation_date="2023-03-12", observation_age_days="1303")
    result = build_analysis(tables, 2025, 2023, 2024)
    output = tmp_path / "report.md"
    write_reader_results(result, output)
    reader = output.read_text(encoding="utf-8")
    assert "| 2023 | 2025-09-25 | 2026-10-05 |" in reader
    assert "Not confirmed" in reader
    assert "Latest verified published period" in reader
    assert "Publisher checked on" in reader
    assert "2023-03-12 | 1303" in reader
    assert "Old reference periods alone do not mean stale" in reader
    assert "2026-10-20" in reader


def test_reader_rejects_contradictory_publication_evidence_for_one_source(tables):
    """One resource cannot silently redefine the shared source publication."""
    other = deepcopy(tables["bi_source_freshness"][1])
    other["publication_date"] = "2026-09-25"
    tables["bi_source_freshness"].append(other)
    with pytest.raises(ValueError, match="inconsistent publication evidence"):
        build_analysis(tables, 2025, 2023, 2024)


def test_historical_complete_year_has_truthful_period_label(tables, tmp_path):
    """Exercise supported historical selection without optional plotting packages."""
    for table in ("bi_program_mix", "bi_industry_mix", "bi_lender_mix"):
        for item in tables[table]:
            item["approval_year"] = "2024"
    tables["bi_state_lending_trends"] = [
        row("01", 1000, known=10, year=2024),
        row("02", 2000, year=2024),
        row("01", 800, year=2023),
        row("02", 1200, year=2023),
        row("01", 4000, year=2025),
        row("02", 5000, year=2025),
    ]
    result = build_analysis(tables, 2024, 2023, 2023)
    assert result["headline"]["amount"] == 3000
    note = selected_period_note(result)
    assert "Selected complete lending year: 2024" in note
    assert "latest" not in note.lower()
    output = tmp_path / "historical.md"
    write_reader_results(result, output)
    reader = output.read_text(encoding="utf-8")
    assert "## How much activity? — 2024" in reader
    assert "latest complete lending year" not in reader


def test_geography_label_requires_actual_population_not_just_count():
    assert geography_scope([{"key": "06"}, {"key": "48"}]) == "California; Texas"
    assert geography_scope([{"key": "11"}]) == "Washington, DC"
    assert geography_scope([]) == "No project geographies"
    assert geography_scope([{"key": "fixture"}]) == "1 selected project geographies"
    from scripts.render_analysis_report import ROOT
    import csv

    with (ROOT / "dbt/seeds/ref_state.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        full = [{"key": item["state_fips"]} for item in csv.DictReader(stream)]
    assert geography_scope(full) == "50 states and Washington, DC"
    assert "(selected)" in geography_scope(full[:-1])


def test_reader_names_both_geographic_rankings_and_published_month_mean(
    tables, tmp_path
):
    result = build_analysis(tables, 2025, 2023, 2024)
    output = tmp_path / "reader.md"
    write_reader_results(result, output)
    reader = output.read_text(encoding="utf-8")
    assert "**Largest reported dollar totals**" in reader
    assert "**Most approval records relative to employer locations**" in reader
    assert "2025 mean of 11 published months" in reader
    assert "its 11-month mean" not in reader
    assert "state-level Power BI context" in reader


def test_public_text_hashes_survive_checkout_line_endings(tmp_path):
    """Public proof is portable; exact-byte source checks remain strict."""
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(b'{"value": 1}\n')
    crlf.write_bytes(b'{"value": 1}\r\n')
    assert text_checksum(lf) == text_checksum(crlf)
    assert checksum(lf) != checksum(crlf)


def test_public_proof_whitelists_aggregates_and_distinguishes_check_scopes(tmp_path):
    checks = {
        table: {
            "rows": 2,
            "sha256": f"hash-{table}",
            "warehouse_differences": 0,
            "duplicate_grains": 0,
            "null_grain_keys": 0,
            "private_trace": "borrower detail must not be published",
        }
        for table in (*TABLES, "unused_table")
    }
    evidence = {
        "checked_at_utc": "2026-10-05T06:00:00Z",
        "csv_checks": checks,
        "warehouse": "/private/warehouse.duckdb",
        "private_source_sample_aggregate_proof": {"detail": "private trace"},
        "relationship_checks": [{"unmatched_keys": 0, "private": "trace"}],
    }
    output = tmp_path / "report.md"
    output.write_text("Public aggregate report\n", encoding="utf-8")
    proof = public_verification(evidence, {"analysis_results.md": output})
    assert proof["recorded_readiness"]["csv_tables"] == 7
    assert proof["recorded_readiness"]["csv_rows"] == 14
    assert set(proof["chart_generation_checks"]["inputs"]) == set(TABLES)
    assert "not rerun" in proof["recorded_readiness"]["scope"]
    assert (
        "Power BI Desktop DAX or Power Query"
        in proof["chart_generation_checks"]["not_executed"]
    )
    assert proof["public_outputs"]["analysis_results.md"]["sha256"] == text_checksum(
        output
    )
    serialized = json.dumps(proof)
    for private_value in ("borrower", "private", str(tmp_path), "unused_table"):
        assert private_value not in serialized
