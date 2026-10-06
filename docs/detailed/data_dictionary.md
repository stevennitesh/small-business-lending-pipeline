# Current field dictionary

Current as of October 4, 2026. Exact exported columns are owned by
[`export_schema.py`](../../pipelines/powerbi/export_schema.py) and the
[Power BI contract](../../powerbi/lending_dashboard_model.json); dbt schema YAML
owns column descriptions/tests. This dictionary describes their scientific meaning.

For report readers, [plain field labels and tooltips](../../powerbi/report_reader_guide.md#technical-reference-for-applying-labels-in-desktop)
map these stable technical names to ordinary terms. “Employer business locations”
means Census employer establishments across firm sizes. “Reported approval amounts”
retains the two program bases. Coverage means the portion of records or dollars
with a known value; it is separate from whether a source is current.

| Fields | Meaning / type boundary |
|---|---|
| `loan_record_key`, `sba_loan_fact_key` | Source approval-record identity; not borrower identity |
| `source_lender_id` | Upstream SBA LocationID lender/CDC identifier; not loan identity or necessarily the named 504 third-party lender; prohibited in BI |
| `project_state_key`, BI `state_key` | Mapped two-character state FIPS text; null geography excluded from state marts |
| `borrower_state_key` | Separate source borrower location; not substituted for project location |
| `approval_date`, `approval_year` | Parsed calendar date and calendar year; null remains null |
| `approval_fiscal_year` | Separately supplied SBA fiscal year, retained without calendar fallback |
| `gross_approval_amount`, `total_approved_loan_amount` | Nonnegative nominal reported amounts: whole 7(a) loan versus SBA/CDC portion for 504; not disbursed principal or total project financing |
| `loan_count` | Number of eligible approval records, including canceled/not-funded where present |
| `approval_amount_coverage_count` | Eligible records with valid gross amounts, including zero; mean denominator distinct from volume |
| `lender_key`, `lender_name` | Normalized currently assigned 7(a) bank / reported 504 third-party lender name; pooled snapshot attribution without historical institution resolution |
| `approval_amount_basis`, `reporting_lender_role` | Program dimension labels for distinct amount bases and reporting-name roles |
| `naics_key` | Sector/composite-sector key; unknown becomes `UNKNOWN`, unclassified 99 remains a source key |
| `is_known_industry` | dbt classification flag; excludes UNKNOWN and unclassified 99 from known-only shares |
| `has_matched_establishment_population` | Lending and positive BDS stock exist at the same state/year; both intensity components use this population |
| `loan_program_key` | 7(a)/504 program reporting key |
| `loan_status_group` | Reference-seed grouping of source historical status; descriptive only |
| `average_loan_size`, grain-level shares | dbt state/year/category statistics; average uses valid-amount count; never average or sum these across groups |
| `comparable_prior_year_amount`, `is_comparable_yoy` | Prior-year additive component only for consecutive full calendar years |
| `source_calendar_start/end`, `coverage_evidence_as_of` | Dated source coverage policy, independent of observed record min/max |
| `first/last_observed_approval_date` | Actual selected-record bounds; not publisher completeness evidence |
| `is_full_calendar_year`, `calendar_period_status` | Full, partial or outside dated source-coverage evidence |
| `establishment_count`, `bds_reference_date` | BDS employer stock across firm sizes at March 12; summed yearly stocks are an establishment-year proxy; not exact SBA scope |
| `establishment_entry_rate`, `establishment_exit_rate` | Published BDS decimal rates using scope-consistent mean stocks, with prior stock derived from current stock + exits − entries |
| `annual_average_unemployment_rate` | Mean monthly configured SA state rate as decimal, not official weighted annual rate |
| `unemployment_rate_yoy_change_pp` | Percentage-point change (+1 means one PP); comparable adjacent years only |
| BI `unemployment_rate_yoy_change_pct` | Deprecated compatible alias: `_pp / 100`, decimal change; not percent change |
| `observed_month_count`, `expected_month_count` | Non-null observed monthly rates and expected available months |
| `observed_expected_month_count`, `unexpected_month_count` | Observed available expected identities versus observations beyond endpoint/in omitted months; counts cannot cancel a gap |
| `publisher_omitted_month_count`, `missing_month_count` | Known omissions within elapsed range versus expected identities missing from the source |
| `is_year_to_date`, `is_comparable_annual`, `annual_coverage_status` | Explicit annual coverage classification; 2025 has a publisher omission |
| `context_join_status`, `has_*_data` | Source presence at matched state/year; presence alone is not comparable coverage |
| `is_comparable_context` | Full SBA year, comparable 12-month LAUS and matched BDS |
| `total_term_months`, `total_initial_interest_rate` | Additive known-value sums used with coverage counts in DAX |
| `paired_504_third_party_dollars`, `paired_504_approval_amount` | Third-party and SBA/CDC amounts on the same 504 records with both values known |
| `paired_504_coverage_count`, `program_504_loan_count`, `paired_504_coverage_rate` | Paired known records / all eligible 504 records; zero is a known value |
| `known_504_third_party_to_sba_amount_rate` | Paired financing ratio; may exceed one because denominator is only the SBA/CDC portion |
| `third_party_to_approved_amount_rate` | Deprecated mixed-program ratio, retained for compatible exports; no new DAX consumer |
| `paired_7a_guaranteed_amount`, `paired_7a_approval_amount` | Guarantee and whole-loan amounts on the same known 7(a) records; source totals remain separately available |
| `paired_7a_coverage_count`, `program_7a_loan_count`, `paired_7a_coverage_rate` | Paired known guarantee records / all eligible 7(a) records |
| `latest_extracted_at_utc`, `latest_observation_date`, `freshness_checked_at_utc` | Separate extraction, source observation/period end and age-evaluation times |
| `observation_date_basis` | Source age clock: approval date, March 12 BDS reference, or BLS month end |
| `snapshot_validity_status`, `freshness_status` | Valid selected evidence versus independent publisher comparison; stale only for a missed verified publication, unknown for expired review or insufficient evidence |
| `publication_reference_date`, `publication_date`, `publication_verified_date` | Verified publisher period, actual release date (nullable), and publisher check date; never substitute one for another |
| `publication_source_url`, `publication_cadence`, `next_scheduled_release_date` | Official evidence, frequency and confirmed next schedule; passing a schedule triggers verification rather than presumed publication |
| `publication_status`, `download_status`, `freshness_reason` | Published-period comparison, independent local download review and explicit reader-facing assessment |
| `max_release_check_age_days`, `release_check_age_days` | Local publisher review window and elapsed time since verification |
| `raw_load_status`, `validation_status`, `latest_run_status` | Loading, raw validation and unknown same-pass final completion |
| `final_pipeline_status_evidence` | Explains why final run_summary.json must supply completion evidence |

Borrower names/cities/ZIPs, source lender IDs and raw paths may exist upstream for
source traceability; they are prohibited on the BI export surface. See
[methodology](kpi_definitions.md) for population, filters and denominators.
