# Step 8: Data Quality and Testing

## Purpose

This section defines the data quality and testing strategy for the Small Business Lending Intelligence Pipeline.

The goal is to make the pipeline trustworthy enough for recruiter review and business-facing dashboard use. The project should not only ingest and model public data; it should prove that the data was checked before KPIs were published.

The testing plan supports the approved MVP scope:

- public SBA 7(a) and 504 FOIA files as the core lending source;
- Census Business Dynamics Statistics as annual business-health context;
- BLS LAUS as monthly labor-market context;
- raw source snapshots stored in AWS S3;
- DuckDB for local development;
- Snowflake for the final warehouse version;
- dbt Core for SQL transformations and model tests;
- pytest for Python code tests;
- Prefect for orchestration and failure gating;
- Power BI built from modeled mart or BI tables;
- no predictive machine learning in the MVP.

---

## Testing Philosophy

The pipeline should follow a simple rule:

```text
No unvalidated source data should become a published KPI.
```

The project should use layered validation. Each layer is responsible for a different kind of confidence.

| Layer | Main Risk | Testing Goal |
|---|---|---|
| Source extraction | API/file unavailable, wrong file, malformed response | Confirm data was retrieved correctly |
| Raw landing | Missing raw files, corrupted files, overwritten files | Preserve reproducible source snapshots |
| Staging | Bad types, invalid dates, missing states, inconsistent source fields | Standardize source data safely |
| Intermediate | Incorrect joins, duplicated grains, broken reusable logic | Validate transformation logic |
| Mart | Wrong KPIs, duplicate metric rows, broken aggregations | Publish reliable business metrics |
| BI | Dashboard connected to wrong tables or misleading grain | Keep Power BI simple and safe |
| Pipeline audit | No visibility into freshness, row counts, or failures | Make quality observable |

The project should avoid a common portfolio-project weakness: showing a polished dashboard without proving that the data is valid.

---

## Tool Responsibilities

Different tools should own different testing concerns.

| Tool | Responsibility | Examples |
|---|---|---|
| Python validation | Source-level and raw-file validation | artifact existence, manifest metadata, checksums, source resource coverage, payload shape |
| pytest | Automated tests for Python code | extractor behavior, config parsing, manifest generation, validation utilities |
| dbt tests | Warehouse/model-level validation | not-null, uniqueness, relationships, accepted values, business-rule tests |
| Prefect | Pipeline gating and run status | stop pipeline on critical failure, retry transient failures, record run metadata |
| Power BI | Presentation checks only | visual formatting, filter behavior, dashboard usability |

Power BI should not be responsible for core metric logic. KPI formulas should live in dbt mart or BI models.

---

## Data Quality Dimensions

The MVP should test data quality across these dimensions.

| Dimension | Definition | Example Check |
|---|---|---|
| Completeness | Required data is present | SBA files downloaded for all required resources |
| Validity | Values conform to expected formats or ranges | `gross_approval_amount >= 0` |
| Uniqueness | A model has one row per expected grain | one row per state-year in `mart_lending_annual_state` |
| Referential integrity | Foreign keys map to dimensions | SBA borrower state maps to `dim_state` |
| Freshness | Source data is recent enough for expected publication cadence | BLS latest month within configured lag threshold |
| Consistency | Related tables reconcile | annual lending mart total matches fact table aggregation |
| Lineage | Data can be traced back to a source extract | every fact row has `source_file_key` |
| Reasonableness | Metrics are plausible relative to prior runs | row-count drift within configured tolerance |
| Privacy / exposure control | Dashboard avoids unnecessary row-level exposure | Power BI uses aggregated `BI` tables, not raw borrower-level data |

---

## Quality Gates

The pipeline should use explicit quality gates. A quality gate determines whether the pipeline can continue.

```text
Extract sources
    ↓
Raw validation gate
    ↓
Raw landing / S3 persistence
    ↓
Warehouse load gate
    ↓
dbt staging tests
    ↓
dbt mart tests
    ↓
BI table build
    ↓
Dashboard refresh / export
```

## Gate Severity Levels

| Severity | Meaning | Pipeline Behavior |
|---|---|---|
| `fail` | Data is not safe to use | Stop the pipeline before publishing downstream tables |
| `warning` | Data is usable but needs review | Continue pipeline, log warning, expose in audit table |
| `info` | Observability detail | Continue pipeline and record metadata |

## Recommended Failure Rule

```text
If a required source fails extraction or a required mart fails dbt tests, do not update BI-facing tables.
```

This prevents a partially broken run from silently refreshing the dashboard.

---

# Raw Source Validation

## Raw Validation Purpose

Raw validation confirms that the source extraction produced the expected files or API responses before those extracts are loaded into DuckDB, Snowflake, or dbt models.

Raw validation should be implemented in Python.

## Active Common Raw Checks

The current raw validation runner emits these common checks for loaded manifest
references. Additional row-drift and freshness checks are planned for the
pipeline-health layer rather than the raw gate.

| Check ID | Check | Tool | Severity | Notes |
|---|---|---|---|---|
| `RAW_001` | Raw file exists | Python | Fail | Works for local files and S3-backed artifacts |
| `RAW_002` | Raw file size is positive | Python | Fail | Prevents empty or unavailable payloads |
| `RAW_003` | SHA-256 checksum generated | Python | Fail | Verifies manifest checksum against the artifact |
| `RAW_004` | Manifest created | Python | Fail | Also emitted when a manifest reference is missing |
| `RAW_005` | Required metadata populated | Python | Fail | Manifest schema and storage identity fields |
| `RAW_006` | Row count captured | Python | Fail | Confirms the manifest captured a non-negative row count |
| `RAW_007` | Schema hash generated | Python | Warning | Used for schema drift monitoring |
| `RAW_008` | Column count captured | Python | Warning | Optional for payloads where column count is not meaningful |
| `RAW_009` | Validation result created | Python | Fail | Self-check that validation JSON was written |
| `RAW_010` | Manifest source identity matches config | Python | Fail | Prevents source/resource misrouting |
| `RAW_011` | Required raw manifest resource present | Python | Fail | Ensures source payload validators have required resources |
| `RAW_012` | Cloud raw manifest is S3-backed | Python | Fail | Cloud route guard |
| `RAW_013` | Raw artifact identity populated | Python | Fail | Requires `raw_uri` identity |
| `RAW_014` | Manifest readable JSON | Python | Fail | Structured malformed-manifest failure |

## Raw Validation Output

Each validation should produce structured output.

Recommended path:

```text
data/validation/source_system=<source>/ingestion_date=YYYY-MM-DD/validation_results.json
s3://small-business-lending-pipeline/validation/source_system=<source>/ingestion_date=YYYY-MM-DD/validation_results.json
```

Recommended validation result schema:

| Field | Description |
|---|---|
| `pipeline_run_id` | Prefect run ID or generated UUID |
| `validation_check_id` | Stable check identifier |
| `validation_scope` | `raw`, `staging`, `mart`, `bi`, or `pipeline` |
| `source_system` | `sba`, `census`, `bls`, or `pipeline` |
| `source_dataset` | Source dataset name |
| `source_resource_name` | File/API resource name |
| `check_name` | Human-readable check name |
| `check_type` | `completeness`, `validity`, `freshness`, `lineage`, etc. |
| `severity` | `fail`, `warning`, or `info` |
| `status` | `passed`, `warning`, or `failed` |
| `expected_value` | Expected threshold or value |
| `observed_value` | Actual observed value |
| `message` | Explanation of result |
| `checked_at_utc` | Validation timestamp |

---

# Source-Specific Raw Checks

## SBA FOIA Raw Checks

SBA FOIA is the core lending source, so its checks should be strict.

Current active SBA raw checks are `SBA_RAW_001` and `SBA_RAW_002`.
The remaining rows are planned profiling and data-quality checks.

| Check ID | Check | Severity | Handling |
|---|---|---|---|
| `SBA_RAW_001` | Required 7(a) and 504 resources identified | Fail | Stop extraction if expected resources are missing |
| `SBA_RAW_002` | Each required CSV downloaded | Fail | Stop before loading incomplete source set |
| `SBA_RAW_003` | SBA data dictionary downloaded | Warning | Continue, but document missing dictionary |
| `SBA_RAW_004` | CSV row count greater than configured minimum | Fail or warning | Severity should be resource-specific |
| `SBA_RAW_005` | Required candidate columns present | Fail | Approval date, state, lender, amount fields where expected |
| `SBA_RAW_006` | File encoding readable | Fail | Stop if CSV cannot be parsed |
| `SBA_RAW_007` | Source period identified | Fail | Required to prevent mixing file ranges |
| `SBA_RAW_008` | Source row hash generated for each row | Fail | Required for lineage and duplicate checks |
| `SBA_RAW_009` | Duplicate source row hash rate within tolerance | Warning initially | Promote to fail after profiling if needed |
| `SBA_RAW_010` | Latest source metadata captured | Warning | Used for freshness reporting |
| `SBA_RAW_011` | Current row count compared with previous successful snapshot | Warning | Flag large unexpected changes |

### SBA Row-Count Drift Rule

Avoid hard-coding exact SBA row counts. Public files may be revised or updated.

Recommended approach:

```text
First successful run: establish baseline row counts per SBA resource.
Later runs: compare each resource to its previous successful row count.
```

Suggested default thresholds:

| Drift | Status |
|---:|---|
| 0% to 20% | Pass |
| 20% to 50% | Warning |
| More than 50% | Fail unless manually acknowledged |

Future row-count drift thresholds should be added to the active validation
configuration before those checks are wired:

```text
config/raw_validation_expectations.yml
```

---

## Census BDS Raw Checks

Census BDS is an annual context source. It should be validated for API response shape, variable availability, state-year coverage, and numeric parsing.

Current active Census BDS raw checks are `BDS_RAW_001` and `BDS_RAW_002`.
Additional profiling and data-quality checks should receive new IDs after the
active range.

| Check ID | Check | Severity | Handling |
|---|---|---|---|
| `BDS_RAW_001` | Required variables returned | Fail | Required for KPI definitions |
| `BDS_RAW_002` | Expected state coverage returned | Fail | Expect states/DC based on configured geography list |

Planned Census checks include response status, header/data row shape, expected
years, State FIPS validity, numeric parsing, latest available year, and duplicate
state-year detection.

### Census BDS Coverage Rule

For a state-year MVP extract, expected rows can be estimated as:

```text
expected_rows = reporting_state_count * requested_year_count
```

The project should allow some configurability because source query constraints may require separate calls by year.

---

## BLS LAUS Raw Checks

BLS LAUS is a monthly context source. It should be validated for series coverage, month parsing, and expected observation counts.

Current active BLS LAUS raw checks are `BLS_RAW_001` through `BLS_RAW_004`.
Additional profiling and data-quality checks should receive new IDs after the
active range.

| Check ID | Check | Severity | Handling |
|---|---|---|---|
| `BLS_RAW_001` | Expected series returned | Fail | Validate against local series config |
| `BLS_RAW_002` | Monthly periods valid | Fail | Requires `M01` through `M12` and month-start dates |
| `BLS_RAW_003` | Observation values numeric | Fail | Required for unemployment KPIs |
| `BLS_RAW_004` | Unemployment rates in configured range | Fail | Uses configured min/max bounds |

Planned BLS checks include API response status, explicit state coverage, latest
month, footnote preservation, and duplicate state-month-measure detection.

### BLS Expected Count Rule

For unemployment-rate series only:

```text
expected_observations = state_series_count * expected_month_count
```

The extractor should chunk BLS requests, but the validation should check the consolidated output.

---

# Freshness Checks

## Freshness Purpose

Freshness checks distinguish between two problems:

```text
1. The public source has not published new data yet.
2. The pipeline failed to ingest data that should be available.
```

The pipeline should not pretend public datasets are real-time. Freshness rules should be conservative and configurable.

## Freshness Rule Table

| Source | Expected Publication Pattern | MVP Freshness Rule | Severity |
|---|---|---|---|
| SBA FOIA | Quarterly source refresh | Warn if latest source metadata or observed approval coverage appears older than expected quarterly window | Warning first; fail only if very stale |
| Census BDS | Annual release with reporting lag | Warn if latest available BDS year is older than configured expected year | Warning |
| BLS LAUS | Monthly data with publication lag | Warn if latest observed month is older than configured lag; fail if severely stale | Warning or fail |
| Reference seeds | Static project files | Fail if missing or invalid | Fail |

## Configurable Freshness Thresholds

Recommended config file:

```yaml
# config/freshness_rules.yml
sources:
  sba_foia:
    warning_after_days: 120
    fail_after_days: 210
  census_bds:
    warning_if_latest_year_before: 2023
    fail_if_no_rows: true
  bls_laus:
    warning_after_days: 75
    fail_after_days: 120
```

These values are defaults, not hard truths. The README should explain that public datasets can lag or be revised.

## Freshness Output

Freshness results should feed:

```text
mart_pipeline_source_freshness
bi_pipeline_health
```

---

# dbt Testing Strategy

## dbt Testing Purpose

Python validation protects the raw layer. dbt tests protect the modeled warehouse.

dbt tests should confirm that staging, intermediate, mart, and BI tables have the expected grain, relationships, values, and business logic.

## dbt Test Types

Use the following test types.

| Test Type | Use Case |
|---|---|
| `not_null` | Required keys and metric fields |
| `unique` | Single-column surrogate keys |
| `accepted_values` | Program names, status values, severity values |
| `relationships` | Foreign key references to dimensions |
| Singular SQL tests | Composite uniqueness, ranges, reconciliation, share totals |

The project should not require `dbt-utils` for MVP. Composite-grain tests can be implemented with custom singular SQL tests or with generated grain keys.

---

## dbt Source Tests

The dbt `sources.yml` file should document raw tables loaded into DuckDB/Snowflake.

Example:

```yaml
version: 2

sources:
  - name: raw
    schema: raw
    tables:
      - name: raw_sba_7a_foia
        description: Raw SBA 7(a) FOIA records loaded from latest successful source snapshots.
        columns:
          - name: source_row_hash
            tests:
              - not_null
          - name: source_file_key
            tests:
              - not_null

      - name: raw_census_bds_state_year
        description: Raw Census BDS state-year API extract normalized to rows.
        columns:
          - name: state
            tests:
              - not_null
          - name: YEAR
            tests:
              - not_null

      - name: raw_bls_laus_state_month
        description: Raw BLS LAUS state-month observations normalized from API responses.
        columns:
          - name: series_id
            tests:
              - not_null
```

Raw source tests should be light. More detailed validation belongs in Python or staging models.

---

# Staging Model Tests

## SBA Staging Tests

Primary model:

```text
stg_sba_loans
```

Expected grain:

```text
one cleaned SBA loan record from the latest successful source snapshot
```

Recommended tests:

| Test ID | Column / Logic | Test Type | Severity |
|---|---|---|---|
| `SBA_STG_001` | `loan_record_key` not null | dbt generic | Fail |
| `SBA_STG_002` | `loan_record_key` unique | dbt generic | Fail |
| `SBA_STG_003` | `loan_program` accepted values: `7a`, `504` | dbt generic | Fail |
| `SBA_STG_004` | `approval_date` not null for reporting records | dbt custom | Fail |
| `SBA_STG_005` | `gross_approval_amount >= 0` | dbt custom | Fail |
| `SBA_STG_006` | `borrower_state_fips` maps to `dim_state` | dbt relationship | Fail |
| `SBA_STG_007` | `source_file_key` not null | dbt generic | Fail |
| `SBA_STG_008` | `source_row_hash` not null | dbt generic | Fail |
| `SBA_STG_009` | invalid NAICS codes map to `UNKNOWN` | dbt custom | Warning |
| `SBA_STG_010` | missing lender maps to `Unknown Lender` | dbt custom | Warning |

Example YAML:

```yaml
models:
  - name: stg_sba_loans
    description: >
      Cleaned SBA 7(a) and 504 loan records. Grain: one row per cleaned loan record
      from the latest successful source snapshot.
    columns:
      - name: loan_record_key
        tests:
          - not_null
          - unique
      - name: loan_program
        tests:
          - not_null
          - accepted_values:
              values: ['7a', '504']
      - name: source_file_key
        tests:
          - not_null
      - name: borrower_state_fips
        tests:
          - relationships:
              to: ref('dim_state')
              field: state_fips
```

Example singular test for negative loan amounts:

```sql
-- tests/assert_sba_loan_amount_non_negative.sql
select
    loan_record_key,
    gross_approval_amount
from {{ ref('stg_sba_loans') }}
where gross_approval_amount < 0
```

---

## Census BDS Staging Tests

Primary model:

```text
stg_census_bds_state_year
```

Expected grain:

```text
one row per state per calendar year
```

Recommended tests:

| Test ID | Column / Logic | Test Type | Severity |
|---|---|---|---|
| `BDS_STG_001` | `bds_record_key` not null | dbt generic | Fail |
| `BDS_STG_002` | `bds_record_key` unique | dbt generic | Fail |
| `BDS_STG_003` | `state_fips` not null | dbt generic | Fail |
| `BDS_STG_004` | `state_fips` maps to `dim_state` | dbt relationship | Fail |
| `BDS_STG_005` | `calendar_year` not null | dbt generic | Fail |
| `BDS_STG_006` | one row per state-year | dbt singular | Fail |
| `BDS_STG_007` | `establishment_count >= 0` | dbt singular | Fail |
| `BDS_STG_008` | entry and exit counts non-negative | dbt singular | Fail |
| `BDS_STG_009` | entry and exit rates within plausible configured range | dbt singular | Warning or fail |

Example singular grain test:

```sql
-- tests/assert_bds_state_year_grain.sql
select
    state_fips,
    calendar_year,
    count(*) as row_count
from {{ ref('stg_census_bds_state_year') }}
group by 1, 2
having count(*) > 1
```

---

## BLS LAUS Staging Tests

Primary model:

```text
stg_bls_laus_state_month
```

Expected grain:

```text
one row per state per month per measure
```

Recommended tests:

| Test ID | Column / Logic | Test Type | Severity |
|---|---|---|---|
| `BLS_STG_001` | `laus_record_key` not null | dbt generic | Fail |
| `BLS_STG_002` | `laus_record_key` unique | dbt generic | Fail |
| `BLS_STG_003` | `series_id` not null | dbt generic | Fail |
| `BLS_STG_004` | `series_id` maps to state-series reference | dbt relationship | Fail |
| `BLS_STG_005` | `state_fips` maps to `dim_state` | dbt relationship | Fail |
| `BLS_STG_006` | `month_start_date` not null | dbt generic | Fail |
| `BLS_STG_007` | `unemployment_rate` between 0 and 100 | dbt singular | Fail |
| `BLS_STG_008` | one row per state-month-measure | dbt singular | Fail |
| `BLS_STG_009` | monthly period only | dbt singular | Fail |

Example singular range test:

```sql
-- tests/assert_laus_unemployment_rate_range.sql
select
    laus_record_key,
    state_fips,
    month_start_date,
    unemployment_rate
from {{ ref('stg_bls_laus_state_month') }}
where unemployment_rate < 0
   or unemployment_rate > 100
```

---

# Dimension Tests

## Dimension Test Requirements

Dimensions support joins across marts. They should be strict.

| Model | Grain | Required Tests |
|---|---|---|
| `dim_date` | one row per calendar date | `date_key` not null/unique; `date_day` unique; year/month fields not null |
| `dim_state` | one row per state/DC | `state_key` not null/unique; `state_fips` unique; `state_abbr` unique where not null |
| `dim_naics` | one row per NAICS code | `naics_key` not null/unique; unknown row exists |
| `dim_lender` | one row per standardized lender | `lender_key` not null/unique; `standardized_lender_name` not null |
| `dim_loan_program` | one row per loan program | `loan_program_key` not null/unique; accepted program values |
| `dim_source_file` | one row per source extract | `source_file_key` not null/unique; checksum not null; raw file URI not null |

## Required Unknown Rows

The model should include controlled unknown/default rows where appropriate.

| Dimension | Required Unknown Row |
|---|---|
| `dim_naics` | `UNKNOWN` / `Unknown / Unclassified` |
| `dim_lender` | `UNKNOWN_LENDER` / `Unknown Lender` |

Example singular test:

```sql
-- tests/assert_dim_naics_unknown_row_exists.sql
select 1
where not exists (
    select 1
    from {{ ref('dim_naics') }}
    where naics_key = 'UNKNOWN'
)
```

---

# Fact Table Tests

## `fact_sba_loans`

Expected grain:

```text
one row per cleaned SBA loan record from the latest successful source snapshot
```

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `FACT_SBA_001` | `loan_record_key` not null and unique | Fail |
| `FACT_SBA_002` | `source_file_key` relationship to `dim_source_file` | Fail |
| `FACT_SBA_003` | `state_key` relationship to `dim_state` for reporting records | Fail |
| `FACT_SBA_004` | `lender_key` relationship to `dim_lender` | Fail |
| `FACT_SBA_005` | `naics_key` relationship to `dim_naics` | Warning or fail depending on unknown handling |
| `FACT_SBA_006` | `approval_date_key` relationship to `dim_date` | Fail |
| `FACT_SBA_007` | `gross_approval_amount >= 0` | Fail |
| `FACT_SBA_008` | valid reporting flags populated | Fail |
| `FACT_SBA_009` | no duplicate `source_row_hash` within same source file in latest snapshot | Warning initially |

## `fact_laus_state_month`

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `FACT_LAUS_001` | `laus_record_key` not null and unique | Fail |
| `FACT_LAUS_002` | one row per state-month-measure | Fail |
| `FACT_LAUS_003` | `state_key` relationship to `dim_state` | Fail |
| `FACT_LAUS_004` | `month_date_key` relationship to `dim_date` | Fail |
| `FACT_LAUS_005` | unemployment rate between 0 and 100 | Fail |

## `fact_bds_state_year`

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `FACT_BDS_001` | `bds_record_key` not null and unique | Fail |
| `FACT_BDS_002` | one row per state-year | Fail |
| `FACT_BDS_003` | `state_key` relationship to `dim_state` | Fail |
| `FACT_BDS_004` | establishment, firm, entry, and exit counts non-negative | Fail |
| `FACT_BDS_005` | entry and exit rates plausible | Warning or fail |

---

# Mart Table Tests

## Mart Testing Purpose

Mart tests protect KPI correctness. These tests should be stricter than staging tests because mart tables feed Power BI.

## Common Mart Tests

Every mart should have:

1. a documented grain;
2. a unique key or composite uniqueness test for that grain;
3. not-null tests for grain columns;
4. non-negative tests for count and amount metrics;
5. range tests for percentages and shares;
6. reconciliation tests where possible;
7. source lineage or latest ingestion metadata where appropriate.

---

## Lending Mart Tests

### `mart_lending_monthly_state`

Expected grain:

```text
one row per state per month
```

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `MART_LEND_MONTH_001` | one row per state-month | Fail |
| `MART_LEND_MONTH_002` | `state_key`, `month_start_date` not null | Fail |
| `MART_LEND_MONTH_003` | `loan_count >= 0` | Fail |
| `MART_LEND_MONTH_004` | `total_approved_loan_amount >= 0` | Fail |
| `MART_LEND_MONTH_005` | `average_loan_size` equals amount / count where count > 0 | Fail |
| `MART_LEND_MONTH_006` | YoY growth is null when prior-year denominator is zero or missing | Warning |
| `MART_LEND_MONTH_007` | monthly totals reconcile to `fact_sba_loans` | Fail |

Example grain test:

```sql
-- tests/assert_mart_lending_monthly_state_grain.sql
select
    state_key,
    month_start_date,
    count(*) as row_count
from {{ ref('mart_lending_monthly_state') }}
group by 1, 2
having count(*) > 1
```

Example reconciliation test:

```sql
-- tests/assert_mart_lending_monthly_state_reconciles_to_fact.sql
with fact_totals as (
    select
        state_key,
        approval_month as month_start_date,
        sum(gross_approval_amount) as fact_amount,
        count(distinct loan_record_key) as fact_count
    from {{ ref('fact_sba_loans') }}
    where is_valid_for_state_reporting = true
      and is_valid_for_amount_reporting = true
    group by 1, 2
),
mart_totals as (
    select
        state_key,
        month_start_date,
        total_approved_loan_amount as mart_amount,
        loan_count as mart_count
    from {{ ref('mart_lending_monthly_state') }}
)
select
    coalesce(f.state_key, m.state_key) as state_key,
    coalesce(f.month_start_date, m.month_start_date) as month_start_date,
    f.fact_amount,
    m.mart_amount,
    f.fact_count,
    m.mart_count
from fact_totals f
full outer join mart_totals m
  on f.state_key = m.state_key
 and f.month_start_date = m.month_start_date
where abs(coalesce(f.fact_amount, 0) - coalesce(m.mart_amount, 0)) > 1
   or coalesce(f.fact_count, 0) <> coalesce(m.mart_count, 0)
```

### `mart_lending_annual_state`

Expected grain:

```text
one row per state per calendar year
```

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `MART_LEND_YEAR_001` | one row per state-year | Fail |
| `MART_LEND_YEAR_002` | annual totals reconcile to monthly lending mart | Fail |
| `MART_LEND_YEAR_003` | annual totals reconcile to `fact_sba_loans` | Fail |
| `MART_LEND_YEAR_004` | growth metrics use prior-year values correctly | Warning |
| `MART_LEND_YEAR_005` | no negative amounts or counts | Fail |

### `mart_lending_lender_state_period`

Expected grain:

```text
one row per state per year per lender
```

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `MART_LENDER_001` | one row per state-year-lender | Fail |
| `MART_LENDER_002` | lender share between 0 and 1 | Fail |
| `MART_LENDER_003` | lender ranks are positive integers | Fail |
| `MART_LENDER_004` | lender shares sum to approximately 1 by state-year | Warning or fail |
| `MART_LENDER_005` | lender totals reconcile to annual lending mart | Fail |

Example lender-share test:

```sql
-- tests/assert_lender_share_between_zero_and_one.sql
select
    state_key,
    calendar_year,
    lender_key,
    lender_approved_amount_share
from {{ ref('mart_lending_lender_state_period') }}
where lender_approved_amount_share < 0
   or lender_approved_amount_share > 1
```

Example share-sum test:

```sql
-- tests/assert_lender_shares_sum_to_one.sql
select
    state_key,
    calendar_year,
    sum(lender_approved_amount_share) as share_sum
from {{ ref('mart_lending_lender_state_period') }}
group by 1, 2
having abs(sum(lender_approved_amount_share) - 1.0) > 0.001
```

### `mart_lending_concentration_state_period`

Expected grain:

```text
one row per state per year
```

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `MART_CONC_001` | one row per state-year | Fail |
| `MART_CONC_002` | top lender shares between 0 and 1 | Fail |
| `MART_CONC_003` | `top_1_lender_share <= top_3_lender_share <= top_5_lender_share` | Fail |
| `MART_CONC_004` | `active_lender_count >= 1` when loan count > 0 | Fail |
| `MART_CONC_005` | HHI between 0 and 10000 if implemented | Fail |

### `mart_lending_industry_state_period`

Expected grain:

```text
one row per state per year per NAICS sector
```

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `MART_IND_001` | one row per state-year-NAICS sector | Fail |
| `MART_IND_002` | industry amount and count non-negative | Fail |
| `MART_IND_003` | industry share between 0 and 1 | Fail |
| `MART_IND_004` | industry shares sum to approximately 1 by state-year | Warning or fail |
| `MART_IND_005` | unknown NAICS bucket exists when invalid/missing source NAICS exists | Warning |

### `mart_lending_program_state_period`

Expected grain:

```text
one row per state per year per SBA loan program
```

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `MART_PROGRAM_001` | one row per state-year-program | Fail |
| `MART_PROGRAM_002` | program accepted values are `7a` and `504` | Fail |
| `MART_PROGRAM_003` | program amount and count non-negative | Fail |
| `MART_PROGRAM_004` | program shares sum to approximately 1 by state-year | Warning or fail |

---

## Context Mart Tests

### `mart_laus_monthly_state`

Expected grain:

```text
one row per state per month
```

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `MART_LAUS_MONTH_001` | one row per state-month | Fail |
| `MART_LAUS_MONTH_002` | unemployment rate between 0 and 100 | Fail |
| `MART_LAUS_MONTH_003` | YoY percentage-point change equals current minus prior-year value | Warning |
| `MART_LAUS_MONTH_004` | latest observed month is present in freshness mart | Warning |

### `mart_laus_annual_state`

Expected grain:

```text
one row per state per year
```

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `MART_LAUS_YEAR_001` | one row per state-year | Fail |
| `MART_LAUS_YEAR_002` | annual average unemployment rate between 0 and 100 | Fail |
| `MART_LAUS_YEAR_003` | complete years have 12 observed months | Fail |
| `MART_LAUS_YEAR_004` | incomplete current year is flagged | Warning |

### `mart_business_dynamics_annual_state`

Expected grain:

```text
one row per state per year
```

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `MART_BDS_YEAR_001` | one row per state-year | Fail |
| `MART_BDS_YEAR_002` | establishment and firm counts non-negative | Fail |
| `MART_BDS_YEAR_003` | entry and exit counts non-negative | Fail |
| `MART_BDS_YEAR_004` | entry and exit rates plausible | Warning or fail |
| `MART_BDS_YEAR_005` | no missing state mappings | Fail |

### `mart_regional_business_health_annual_state`

Expected grain:

```text
one row per state per year
```

Recommended tests:

| Test ID | Logic | Severity |
|---|---|---|
| `MART_REGION_001` | one row per state-year | Fail |
| `MART_REGION_002` | lending metrics reconcile to annual lending mart | Fail |
| `MART_REGION_003` | normalized metrics are null when denominator is zero or missing | Fail |
| `MART_REGION_004` | `loans_per_1000_establishments >= 0` when populated | Fail |
| `MART_REGION_005` | `approved_loan_dollars_per_establishment >= 0` when populated | Fail |
| `MART_REGION_006` | context flags correctly indicate missing BDS or LAUS joins | Warning |

---

# BI Layer Tests

## BI Layer Purpose

BI models are the tables Power BI should connect to. The tests should confirm that BI tables are aggregated, stable, and dashboard-safe.

## BI Testing Rules

1. BI models must have documented grains.
2. BI models must not expose raw borrower-level records.
3. BI models must not include unnecessary raw source columns.
4. BI models must preserve enough dimensions for filtering.
5. BI models must be built from marts, not raw source tables.
6. BI models must pass grain uniqueness tests.

## BI Model Tests

| Model | Expected Grain | Required Tests |
|---|---|---|
| `bi_executive_overview` | state-year | unique state-year; KPI fields non-negative; freshness fields populated |
| `bi_state_lending_trends` | state-month | unique state-month; lending and unemployment fields in valid ranges |
| `bi_lender_concentration` | state-year-lender | unique state-year-lender; shares between 0 and 1 |
| `bi_industry_mix` | state-year-NAICS sector | unique state-year-sector; shares between 0 and 1 |
| `bi_program_mix` | state-year-program | unique state-year-program; accepted program values |
| `bi_regional_business_health` | state-year | unique state-year; normalized metrics valid |
| `bi_pipeline_health` | run/source/model/check summary | validation statuses accepted values |

## Dashboard Exposure Test

The MVP should include a custom check that prevents BI models from exposing restricted or unnecessary row-level identifiers.

Example prohibited BI fields:

```text
borrower_name
borrower_street_address
raw_loan_number
source_row_number
source_row_hash
raw_file_uri
```

Some lineage fields may exist in audit tables, but not in business-facing BI tables.

---

# Reconciliation Tests

## Reconciliation Purpose

Reconciliation tests ensure that aggregated marts agree with lower-level fact tables.

## Required Reconciliations

| Reconciliation | Severity |
|---|---|
| `fact_sba_loans` total amount/count reconciles to `mart_lending_monthly_state` | Fail |
| `fact_sba_loans` total amount/count reconciles to `mart_lending_annual_state` | Fail |
| `mart_lending_monthly_state` reconciles to `mart_lending_annual_state` for complete years | Fail |
| `mart_lending_lender_state_period` reconciles to `mart_lending_annual_state` | Fail |
| `mart_lending_industry_state_period` reconciles to `mart_lending_annual_state` | Warning or fail depending on unknown NAICS handling |
| `mart_lending_program_state_period` reconciles to `mart_lending_annual_state` | Fail |
| `mart_regional_business_health_annual_state` lending metrics reconcile to `mart_lending_annual_state` | Fail |

## Reconciliation Tolerance

Dollar reconciliation should allow a small tolerance for rounding.

Recommended default:

```text
absolute amount difference <= 1.00 USD
count difference = 0
```

---

# Null and Edge-Case Tests

The KPI dictionary defines null and edge-case handling. dbt tests should enforce the most important rules.

| Scenario | Required Behavior | Test Severity |
|---|---|---|
| denominator is zero | return null, not zero or infinity | Fail |
| prior-year value missing | growth metric returns null | Warning |
| state mapping missing | exclude from state marts or flag invalid reporting row | Fail |
| NAICS missing/invalid | map to `Unknown / Unclassified` | Warning |
| lender missing | map to `Unknown Lender` | Warning |
| loan amount missing | exclude from amount-based KPIs and log validation issue | Fail if silently included |
| loan amount negative | fail unless explicitly documented by source | Fail |
| BDS context missing | keep lending metric; set context metric null; flag `has_bds_context = false` | Warning |
| BLS context missing | keep lending metric; set labor metric null; flag `has_laus_context = false` | Warning |
| current year incomplete | label or flag incomplete year | Warning |

Example denominator test:

```sql
-- tests/assert_no_infinite_or_invalid_normalized_metrics.sql
select
    state_key,
    calendar_year,
    establishment_count,
    loans_per_1000_establishments,
    approved_loan_dollars_per_establishment
from {{ ref('mart_regional_business_health_annual_state') }}
where establishment_count = 0
  and (
      loans_per_1000_establishments is not null
      or approved_loan_dollars_per_establishment is not null
  )
```

---

# Latest-Snapshot Tests

## Purpose

Some public files can be cumulative or periodically refreshed. The data model uses this rule:

```text
Use the latest successful ingestion snapshot per source resource for current reporting marts.
```

Tests must ensure that old snapshots are not accidentally double-counted.

## Required Tests

| Test ID | Logic | Severity |
|---|---|---|
| `SNAPSHOT_001` | each source resource has one latest successful snapshot selected | Fail |
| `SNAPSHOT_002` | `fact_sba_loans` uses only selected latest successful SBA source files | Fail |
| `SNAPSHOT_003` | marts do not include multiple ingestion dates for the same source resource unless explicitly designed | Fail |
| `SNAPSHOT_004` | historical snapshots remain available in raw/audit tables | Info |

Example singular test:

```sql
-- tests/assert_fact_sba_uses_latest_successful_snapshots.sql
with latest_sources as (
    select source_file_key
    from {{ ref('int_pipeline_latest_successful_sources') }}
    where source_system = 'sba'
      and source_dataset = '7a_504_foia'
),
invalid_fact_rows as (
    select f.loan_record_key, f.source_file_key
    from {{ ref('fact_sba_loans') }} f
    left join latest_sources s
      on f.source_file_key = s.source_file_key
    where s.source_file_key is null
)
select *
from invalid_fact_rows
```

---

# pytest Strategy

## pytest Purpose

pytest should test Python code behavior. It should not duplicate every dbt test.

Use pytest for:

- extractor functions;
- API request construction;
- response parsing;
- file download handling;
- checksum generation;
- manifest generation;
- source expectation configs;
- raw validation functions;
- S3 path construction;
- local path construction;
- safe utility functions.

## Recommended Test Directory

```text
tests/
├── unit/
│   ├── test_config.py
│   ├── test_manifest.py
│   ├── test_paths.py
│   ├── test_checksums.py
│   ├── test_raw_validation_flow.py
│   ├── test_raw_validation_sources.py
│   ├── test_raw_validation_manifest_failures.py
│   ├── test_raw_validation_output.py
│   ├── test_sba_extract.py
│   ├── test_census_extract.py
│   ├── test_bls_extract.py
│   └── test_s3_loader.py
│
├── integration/
│   ├── test_local_ingestion_flow.py
│   ├── test_duckdb_load.py
│   └── test_validation_outputs.py
│
└── fixtures/
    ├── sba_sample.csv
    ├── census_bds_sample.json
    ├── bls_laus_sample.json
    └── expected_manifest.json
```

## pytest Unit Test Coverage

| Module | Test Focus |
|---|---|
| `extract/sba_extract.py` | resource discovery, file download, source-period parsing |
| `extract/census_extract.py` | API URL construction, response normalization, variable validation |
| `extract/bls_extract.py` | request chunking, series mapping, monthly period parsing |
| `load/s3_loader.py` | S3 key construction, upload function behavior with mock client |
| `validation/raw_manifest_artifact_validation.py` and `validation/raw_manifest_rule_checks.py` | raw artifact existence, checksum, manifest artifact metadata, and storage-reference checks |
| `validation/validation_failures.py` | blocking validation failure policy before downstream loads |
| `validation/raw_validation_resources.py` | shared raw validation resource and output names |
| source-specific payload modules under `validation/` | SBA resource coverage, Census BDS payload shape, and BLS LAUS normalized rows |
| `flows/pipeline_health.py` | future pipeline-health helper checks, not active raw-runner checks |
| `utils/manifest.py` | manifest schema and required fields |
| `utils/hashing.py` | deterministic checksums and row hashes |
| `utils/paths.py` | local/S3 path generation |
| `config/*.yml` | config loads and required keys exist |

## Example pytest Tests

### Manifest Required Fields

```python
def test_manifest_contains_required_fields(sample_manifest):
    required_fields = {
        "pipeline_run_id",
        "source_system",
        "dataset_name",
        "resource_name",
        "source_url",
        "extracted_at_utc",
        "ingestion_date",
        "local_raw_path",
        "s3_raw_uri",
        "file_format",
        "row_count",
        "sha256_checksum",
        "schema_hash",
        "validation_status",
    }

    assert required_fields.issubset(sample_manifest.keys())
```

### Checksum Determinism

```python
def test_sha256_checksum_is_deterministic(tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text("a,b\n1,2\n", encoding="utf-8")

    first = calculate_sha256(file_path)
    second = calculate_sha256(file_path)

    assert first == second
    assert len(first) == 64
```

### BLS Monthly Period Parsing

```python
def test_bls_period_m01_parses_to_month_start():
    parsed = parse_bls_period(year="2026", period="M01")

    assert parsed.isoformat() == "2026-01-01"
```

### Reject Annual BLS Period Unless Allowed

```python
def test_bls_annual_period_rejected_by_default():
    assert is_valid_bls_monthly_period("M13") is False
```

### Census Response Header Validation

```python
def test_census_response_requires_header_row():
    response = []

    result = validate_census_response_shape(response)

    assert result.status == "failed"
    assert result.severity == "fail"
```

---

# Integration Testing Strategy

## Local Integration Tests

The MVP should include a small local integration path using sample files.

Recommended command:

```bash
pytest tests/integration
```

Integration tests should verify:

1. sample raw files can be read;
2. manifests can be generated;
3. validation outputs are written;
4. sample files can be loaded into DuckDB;
5. dbt can run against the local DuckDB target;
6. audit tables are populated.

## What Not to Do in pytest

Avoid these in pytest:

- calling live APIs in default unit tests;
- requiring AWS credentials for unit tests;
- requiring Snowflake credentials for unit tests;
- testing every SQL transformation in Python;
- hard-coding exact row counts for live public datasets;
- using tests that only pass on one machine.

Live API and cloud tests should be opt-in.

Recommended markers:

```python
@pytest.mark.integration
@pytest.mark.requires_aws
@pytest.mark.requires_snowflake
@pytest.mark.live_api
```

---

# Prefect Failure Behavior

## Prefect Gate Design

Prefect should orchestrate the pipeline and enforce quality gates.

Recommended flow behavior:

| Stage | Failure Behavior |
|---|---|
| Source extraction fails | Retry for transient failures; fail pipeline if required source still unavailable |
| Raw validation fails | Stop pipeline before loading warehouse tables |
| S3 upload fails | Fail in final mode; warn in local-only mode |
| DuckDB load fails | Fail local run |
| Snowflake load fails | Fail final run |
| dbt staging tests fail | Stop before marts |
| dbt mart tests fail | Stop before BI layer |
| BI model tests fail | Do not refresh/export dashboard outputs |
| Warning checks fail | Continue but record warning in audit outputs |

## Retry Strategy

Use retries for transient external failures only.

| Task Type | Retry? | Notes |
|---|---|---|
| API requests | Yes | Network/API transient failures |
| File downloads | Yes | Temporary connection failures |
| S3 upload | Yes | Temporary AWS connectivity issue |
| DuckDB load | Usually no | Often deterministic data/schema issue |
| dbt build | Usually no | Failing tests should be fixed, not retried blindly |
| validation checks | No | Should return deterministic pass/fail/warning |

## Pipeline Run Status

A pipeline run should end with one of these statuses.

| Status | Meaning |
|---|---|
| `success` | All required checks passed |
| `warning` | Required checks passed, but warning checks were triggered |
| `failed` | At least one required failure-level check failed |

These statuses should feed:

```text
mart_pipeline_run_summary
bi_pipeline_health
```

---

# Audit and Observability Tables

## Purpose

Audit tables turn testing into a visible part of the project. This is important for recruiter review because it shows governance habits, not just dashboard design.

## Required Audit Models

| Model | Grain | Purpose |
|---|---|---|
| `stg_ingestion_manifest` | one row per source extract | Standardized source metadata |
| `stg_validation_result` | one row per validation check | Standardized Python validation outputs |
| `mart_pipeline_source_freshness` | one row per source dataset per run | Freshness status |
| `mart_pipeline_validation_summary` | one row per run/source/model | Validation and dbt test summary |
| `mart_pipeline_run_summary` | one row per pipeline run | Run-level status and timing |
| `bi_pipeline_health` | dashboard-ready pipeline health table | Power BI data quality page |

## Validation Summary Logic

The validation summary should calculate:

```text
total_validation_checks
passed_validation_checks
warning_validation_checks
failed_validation_checks
validation_pass_rate
validation_status
```

Recommended status logic:

```sql
case
  when failed_validation_checks > 0 then 'failed'
  when warning_validation_checks > 0 then 'warning'
  else 'passed'
end as validation_status
```

---

# Data Quality Dashboard Requirements

The Power BI dashboard should include a data quality or pipeline health page.

## Recommended Visuals

| Visual | Source Model | Purpose |
|---|---|---|
| Latest successful run card | `bi_pipeline_health` | Show last successful refresh |
| Source freshness status table | `mart_pipeline_source_freshness` | Show source-level freshness |
| Row count by source | `stg_ingestion_manifest` or `bi_pipeline_health` | Show source volume |
| Validation pass rate card | `mart_pipeline_validation_summary` | Show test health |
| Failed/warning checks table | `mart_pipeline_validation_summary` | Make failures visible |
| dbt test result summary | audit model or exported dbt artifacts | Show transformation quality |
| Source ingestion timeline | manifest/audit table | Show reproducibility |

## Dashboard Health Page Notes

The health page should use direct language:

```text
These checks validate source ingestion, schema expectations, row counts, freshness, dbt model tests, and pipeline run status. Passing checks do not guarantee that public source data is free of all errors, but they reduce the risk of publishing incomplete, stale, or malformed data.
```

---

# dbt Artifact Handling

## Purpose

The project should capture dbt run/test results when practical.

Useful dbt artifacts:

```text
target/run_results.json
target/manifest.json
target/catalog.json
```

## MVP Approach

For MVP, the pipeline can parse `run_results.json` after `dbt build` and write a simplified validation summary.

Recommended output:

```text
data/validation/dbt/ingestion_date=YYYY-MM-DD/dbt_run_results_summary.json
s3://small-business-lending-pipeline/validation/dbt/ingestion_date=YYYY-MM-DD/dbt_run_results_summary.json
```

Recommended fields:

| Field | Description |
|---|---|
| `pipeline_run_id` | Pipeline run identifier |
| `dbt_invocation_id` | dbt invocation ID if available |
| `model_name` | dbt model or test name |
| `resource_type` | model, test, seed, source |
| `status` | success, warn, error, fail, skipped |
| `execution_time_seconds` | Runtime |
| `message` | dbt message or failure summary |
| `compiled_sql_path` | Optional path for debugging |

---

# CI Testing Strategy

## MVP Local Commands

The repository should support these commands:

```bash
pytest

dbt deps

dbt build --target duckdb_dev
```

If using a Makefile:

```bash
make test
make dbt-build-local
make validate-local
```

## Optional GitHub Actions

CI is a stretch goal but valuable for recruiter signal.

Recommended CI checks:

1. install Python dependencies;
2. run `pytest`;
3. run lightweight linting if added;
4. run dbt parse;
5. run dbt build against sample DuckDB data.

Recommended not to include in default CI:

- live SBA/Census/BLS API pulls;
- AWS S3 upload;
- Snowflake build;
- Power BI refresh.

Those require credentials and make CI brittle.

---

# Test Configuration Files

The project should centralize freshness thresholds and raw validation expectations.

Recommended files:

```text
config/
├── sources.yml
├── freshness_rules.yml
├── sba_resources.yml
├── census_bds_variables.yml
├── bls_laus_state_series.yml
└── raw_validation_expectations.yml
```

## Example Active Validation Config

```yaml
raw_validation_expectations:
  sba_foia:
    required_programs:
      - "7a"
      - "504"
  census_bds:
    expected_state_count: 51
    required_variables:
      - "YEAR"
      - "state"
      - "ESTAB"
      - "ESTABS_ENTRY"
      - "ESTABS_EXIT"
  bls_laus:
    required_period_pattern: "^M(0[1-9]|1[0-2])$"
    unemployment_rate_min: 0
    unemployment_rate_max: 100
```

SBA resource discovery and source metadata live separately in
`config/sba_resources.yml` and `config/sources.yml`.

---

# Model Contract Requirements

Each dbt model should include a YAML contract-style description.

Minimum required documentation:

| Field | Requirement |
|---|---|
| model description | Explain purpose |
| grain | Explicitly state expected grain |
| source dependencies | Identify upstream source or model |
| primary key | Identify unique key or composite grain |
| column descriptions | Describe business fields |
| tests | Include required tests |
| caveats | Include interpretation limits where relevant |

Example:

```yaml
models:
  - name: mart_regional_business_health_annual_state
    description: >
      Annual state-level table combining SBA lending, Census BDS business dynamics,
      and BLS LAUS annual unemployment context. Grain: one row per state per calendar year.
    columns:
      - name: state_key
        description: State key derived from two-digit state FIPS.
        tests:
          - not_null
          - relationships:
              to: ref('dim_state')
              field: state_key
      - name: calendar_year
        description: Calendar year.
        tests:
          - not_null
      - name: loans_per_1000_establishments
        description: SBA loan count per 1,000 Census BDS establishments.
```

---

# Required Test Commands

## Local Python Tests

```bash
pytest
```

## Local dbt Build

```bash
dbt build --target duckdb_dev
```

## Final Warehouse dbt Build

```bash
dbt build --target snowflake_prod
```

## Suggested Full Local Validation Command

```bash
make run-local-fixture \
  && pytest \
  && dbt build --target duckdb_dev
```

## Suggested Makefile Targets

```makefile
test:
	pytest

validate-raw:
	$(MAKE) run-local-fixture

dbt-build-local:
	dbt build --target duckdb_dev

quality-local: validate-raw test dbt-build-local
```

---

# Minimum Required Tests for MVP

The MVP is not complete unless these tests exist.

## Python / pytest Minimums

| Minimum Test | Required |
|---|---:|
| manifest required fields test | Yes |
| checksum generation test | Yes |
| S3/local path construction test | Yes |
| SBA raw file validation test using sample CSV | Yes |
| Census response validation test using sample JSON | Yes |
| BLS response validation test using sample JSON | Yes |
| BLS period parsing test | Yes |
| source expectation config loading test | Yes |
| validation result output schema test | Yes |

## dbt Minimums

| Minimum Test | Required |
|---|---:|
| primary keys not null and unique for dimensions/facts | Yes |
| state relationships to `dim_state` | Yes |
| source file relationships to `dim_source_file` | Yes |
| accepted values for loan program | Yes |
| non-negative loan amounts | Yes |
| unemployment rate between 0 and 100 | Yes |
| one row per state-month in monthly marts | Yes |
| one row per state-year in annual marts | Yes |
| lender shares between 0 and 1 | Yes |
| top lender share ordering logic | Yes |
| annual lending totals reconcile to fact table | Yes |
| BI tables have expected grain | Yes |
| latest-snapshot rule enforced | Yes |

---

# Testing Anti-Patterns to Avoid

Avoid these issues.

| Anti-Pattern | Why It Is Bad |
|---|---|
| Dashboard built from raw tables | Pushes business logic into Power BI and hides data quality problems |
| Exact live row-count assertions | Public datasets change and get revised |
| No source manifest | Breaks lineage and reproducibility |
| No checksum | Cannot confirm whether raw files changed |
| Only testing Python, not SQL models | Most KPI logic lives in SQL/dbt |
| Only testing dbt, not source extraction | Bad raw data can enter the warehouse |
| Ignoring grain mismatches | Causes misleading cross-source KPIs |
| Retrying failed dbt tests blindly | Failing tests usually indicate data/model issues |
| Silently dropping bad records | Destroys auditability |
| Publishing dashboard after failed mart tests | Undermines trust |

---

# Data Quality Acceptance Criteria

Step 8 is complete when the project has:

1. A documented testing strategy across raw, staging, intermediate, mart, BI, and audit layers.
2. Source-specific raw validation checks for SBA, Census BDS, and BLS LAUS.
3. A validation result schema suitable for audit tables and Power BI pipeline-health reporting.
4. Configurable freshness rules for each public source.
5. dbt tests for key staging models, fact tables, dimensions, marts, and BI tables.
6. Custom singular dbt tests for composite grain, ranges, reconciliation, and latest-snapshot enforcement.
7. pytest coverage for Python extraction, validation, manifest, checksum, and path utilities.
8. Prefect failure behavior that prevents publishing BI tables after critical test failures.
9. Reconciliation tests proving that mart KPIs tie back to facts.
10. BI layer tests preventing raw borrower-level exposure.
11. A data quality dashboard or Power BI page fed by pipeline health tables.
12. Clear severity levels: fail, warning, and info.
13. Clear local testing commands and optional CI direction.
14. Explicit confirmation that predictive ML testing is not part of the MVP because ML is out of scope.

---

# Step 8 Summary

The data quality strategy uses Python validation to protect raw ingestion, pytest to test Python code, dbt tests to validate modeled warehouse tables, and Prefect to enforce quality gates.

The most important checks are:

- required source files and API responses are present;
- raw files have manifests, checksums, row counts, and schema hashes;
- staging models have valid keys, dates, states, amounts, and source lineage;
- mart tables have one row per documented grain;
- KPI totals reconcile back to fact tables;
- shares and rates stay within valid ranges;
- latest successful snapshots are used to prevent double-counting cumulative public files;
- BI tables are aggregated and dashboard-safe;
- pipeline health is visible through audit tables and Power BI.

This testing plan keeps the project focused on analytics engineering: trusted ingestion, tested SQL models, observable quality, reproducible outputs, and dashboard-ready KPIs without adding predictive machine learning or unnecessary infrastructure scope.
