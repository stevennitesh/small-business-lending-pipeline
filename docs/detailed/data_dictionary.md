# Data Dictionary

## Purpose

This document provides the starter field dictionary for the Small Business Lending Intelligence Pipeline. Detailed model-level descriptions should also be maintained in dbt YAML files as the project is implemented.

The data dictionary is organized around the final modeled entities rather than raw source-specific column names. Raw source fields may differ by SBA file, Census API response, or BLS API response; staging models standardize those fields into the canonical names below.

---

## Core Grain Summary

| Table / Model | Grain | Business Role |
|---|---|---|
| `stg_sba_loans` | One cleaned SBA loan record | Normalized SBA 7(a) and 504 records |
| `stg_census_bds_state_year` | One row per state-year | Annual business dynamics context |
| `stg_bls_laus_state_month` | One row per state-month-measure | Monthly labor-market context |
| `fact_sba_loans` | One cleaned SBA loan record from latest successful snapshot | Core lending fact |
| `fact_bds_state_year` | One row per state-year | Census BDS context fact |
| `fact_laus_state_month` | One row per state-month-measure | BLS LAUS context fact |
| `mart_lending_monthly_state` | One row per state-month | Monthly lending trend KPIs |
| `mart_lending_annual_state` | One row per state-year | Annual lending KPIs |
| `mart_lending_lender_state_period` | One row per state-year-lender | Lender ranking and share |
| `mart_lending_concentration_state_period` | One row per state-year | Lender concentration KPIs |
| `mart_lending_industry_state_period` | One row per state-year-NAICS sector | Industry mix KPIs |
| `mart_regional_business_health_annual_state` | One row per state-year | Cross-source regional context |
| `bi_*` tables | Dashboard-specific grains | Power BI consumption layer |

---

## Canonical SBA Lending Fields

| Field | Type | Description | Primary Use |
|---|---|---|---|
| `loan_record_key` | text | Deterministic surrogate key for a cleaned SBA loan record | Primary key, loan count |
| `source_file_key` | text | Surrogate key linking row back to source extract metadata | Lineage |
| `source_row_hash` | text | Hash of raw row values | Duplicate checks, lineage |
| `loan_program` | text | Normalized SBA program value, usually `7a` or `504` | Program mix |
| `approval_date` | date | Parsed loan approval date | Time-series analysis |
| `approval_month` | date | First day of approval month | Monthly marts |
| `approval_year` | integer | Calendar year of approval | Annual marts |
| `fiscal_year` | integer | SBA fiscal year where available or derived | Optional fiscal reporting |
| `borrower_state_abbr` | text | Borrower state abbreviation from source or cleaned mapping | State matching |
| `borrower_state_fips` | text | Two-digit state FIPS code | Cross-source joins |
| `standardized_lender_name` | text | Cleaned lender name | Lender reporting |
| `lender_key` | text | Deterministic surrogate key for lender | Lender dimension joins |
| `naics_code` | text | Cleaned NAICS code | Industry reporting |
| `naics_sector_code` | text | Two-digit NAICS sector | Sector-level dashboard |
| `gross_approval_amount` | numeric | Approved loan amount used for core lending volume KPIs | Approved dollars |
| `sba_guaranteed_amount` | numeric | SBA guaranteed amount, if reliable across sources | Conditional KPI |
| `jobs_supported` | numeric | Jobs supported/created/retained field where available and documented | Optional context |
| `is_valid_for_state_reporting` | boolean | Indicates row can be used in state-level marts | Data quality |
| `is_valid_for_amount_reporting` | boolean | Indicates amount is valid for amount-based KPIs | Data quality |
| `ingestion_date` | date | Date the source extract was ingested | Snapshot lineage |

---

## Canonical Census BDS Fields

| Field | Type | Description | Primary Use |
|---|---|---|---|
| `bds_record_key` | text | Deterministic key for state-year BDS record | Primary key |
| `state_fips` | text | Two-digit state FIPS code | Join to state dimension and SBA annual marts |
| `calendar_year` | integer | BDS reference year | Annual joins |
| `establishment_count` | numeric | Number of establishments | Lending normalization |
| `establishment_entry_count` | numeric | Establishment entries | Business formation context |
| `establishment_entry_rate` | numeric | Establishment entry rate | Business-health KPI |
| `establishment_exit_count` | numeric | Establishment exits | Business churn context |
| `establishment_exit_rate` | numeric | Establishment exit rate | Business-health KPI |
| `firm_count` | numeric | Number of firms | Business-base context |
| `job_creation_count` | numeric | Jobs created from opening/expanding establishments | Optional growth context |
| `job_destruction_count` | numeric | Jobs lost from closing/contracting establishments | Optional contraction context |
| `source_file_key` | text | Link to source extract metadata | Lineage |

---

## Canonical BLS LAUS Fields

| Field | Type | Description | Primary Use |
|---|---|---|---|
| `laus_record_key` | text | Deterministic key for LAUS state-month-measure row | Primary key |
| `series_id` | text | BLS series identifier | Series mapping and validation |
| `state_fips` | text | Two-digit state FIPS derived from series mapping | Cross-source joins |
| `month_start_date` | date | First day of observation month | Monthly joins |
| `calendar_year` | integer | Observation year | Annual rollups |
| `month_number` | integer | Observation month number | Date validation |
| `measure_name` | text | Name of labor-market measure | Measure filtering |
| `measure_value` | numeric | Numeric BLS observation value | Measure storage |
| `unemployment_rate` | numeric | State unemployment rate where measure applies | Labor-market KPI |
| `unemployment_rate_yoy_change_pp` | numeric | Percentage-point change versus same month prior year | Trend KPI |
| `footnotes` | text / variant | BLS footnotes where available | Revision/preliminary context |
| `source_file_key` | text | Link to source extract metadata | Lineage |

---

## Core Dimension Fields

### `dim_state`

| Field | Description |
|---|---|
| `state_key` | State surrogate key, usually `state_fips` |
| `state_fips` | Two-digit state FIPS code |
| `state_abbr` | Two-character state abbreviation |
| `state_name` | Full state name |
| `census_region` | Census region |
| `census_division` | Census division |
| `is_state` | True for 50 states |
| `is_dc` | True for District of Columbia |
| `is_reporting_geography` | True when included in MVP reporting scope |

### `dim_date`

| Field | Description |
|---|---|
| `date_key` | Date key in `YYYYMMDD` format |
| `date_day` | Calendar date |
| `month_start_date` | First day of month |
| `calendar_year` | Calendar year |
| `calendar_quarter` | Calendar quarter |
| `calendar_year_month` | Year-month label |
| `calendar_year_quarter` | Year-quarter label |
| `fiscal_year` | Fiscal year where relevant |

### `dim_lender`

| Field | Description |
|---|---|
| `lender_key` | Hash or surrogate key derived from standardized lender name |
| `standardized_lender_name` | Cleaned lender name |
| `display_lender_name` | Dashboard-friendly lender label |
| `is_unknown_lender` | True when source lender name is missing |

### `dim_naics`

| Field | Description |
|---|---|
| `naics_key` | Surrogate key, usually cleaned NAICS code |
| `naics_code` | Cleaned NAICS code |
| `naics_sector_code` | Two-digit sector code |
| `naics_sector_name` | NAICS sector label |
| `naics_description` | Industry description |
| `is_unknown` | True for `Unknown / Unclassified` |

### `dim_source_file`

| Field | Description |
|---|---|
| `source_file_key` | Surrogate key for source extract |
| `pipeline_run_id` | Prefect run ID or generated UUID |
| `source_system` | `sba`, `census`, `bls`, or `pipeline` |
| `source_dataset` | Dataset identifier |
| `source_resource_name` | Source file or API resource name |
| `source_url` | Source URL or endpoint |
| `raw_file_uri` | Local or S3 path to raw extract |
| `file_format` | CSV, JSON, XLSX, YAML, etc. |
| `ingestion_date` | Date partition |
| `row_count` | Raw row count |
| `sha256_checksum` | Raw file checksum |
| `schema_hash` | Hash of schema metadata |
| `validation_status` | `passed`, `warning`, or `failed` |

---

## BI Exposure Rules

Power BI should use only modeled mart or BI tables. Business-facing BI tables should not expose raw borrower-level fields or raw row identifiers.

Prohibited fields in business-facing BI tables:

```text
borrower_name
borrower_street_address
raw_loan_number
source_row_number
source_row_hash
raw_file_uri
```

Audit and lineage tables may contain technical metadata, but those should appear only on the pipeline health page or in documentation.

---

## Dictionary Maintenance Rules

1. Update this file when canonical field names change.
2. Keep dbt model YAML descriptions aligned with this file.
3. Do not add Power BI-only metrics without adding a KPI definition.
4. Preserve source lineage fields in facts and audit models.
5. Document null handling and unknown-category handling before dashboard release.
