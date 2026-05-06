# Step 4: Data Source Inventory

## Purpose

This section defines the public data sources for the Small Business Lending Intelligence Pipeline.

The goal is to document exactly what data enters the pipeline, why each source is included, how it will be ingested, what grain it supports, how it joins to other sources, and what limitations must be handled before publishing KPIs.

The MVP uses three official public data sources:

1. **SBA 7(a) and 504 FOIA loan files** for small-business lending activity.
2. **Census Business Dynamics Statistics (BDS)** for business formation and establishment context.
3. **BLS Local Area Unemployment Statistics (LAUS)** for labor-market context.

Optional sources are documented separately as stretch sources. They should not be added to the MVP unless the core pipeline is already working end-to-end.

---

## Source Selection Summary

| Source | Publisher | MVP Role | Access Pattern | Primary Grain | Refresh Cadence | Included in MVP |
|---|---|---|---|---|---|---|
| SBA 7(a) and 504 FOIA | U.S. Small Business Administration | Core lending fact data | Public CSV files from SBA Open Data / CKAN | Source loan record | Quarterly | Yes |
| Census BDS | U.S. Census Bureau | Business dynamics context | Census API | Year + geography + industry/filter combination | Annual | Yes |
| BLS LAUS | U.S. Bureau of Labor Statistics | Labor-market context | BLS Public Data API | State + month + series | Monthly | Yes |
| Census BFS | U.S. Census Bureau | Timelier business application context | CSV/API-style public release files | State + month | Monthly | Stretch |
| SBA Activity Reports | U.S. Small Business Administration | Summary reconciliation / lender reporting context | Public reports | Program + period + lender/state/segment | Monthly | Stretch |

---

## MVP Source Decision

The MVP should use **SBA FOIA + Census BDS + BLS LAUS**.

This gives the project:

- one core lending dataset;
- one business formation / establishment context dataset;
- one labor-market context dataset;
- a mix of CSV and API ingestion;
- state-level joinability;
- enough analytical depth without overextending scope.

The MVP should **not** add Census BFS or SBA monthly activity reports at first. Those are useful, but they introduce more source handling before the core model exists.

---

# Source 1: SBA 7(a) and 504 FOIA Loan Files

## Source Overview

The SBA 7(a) and 504 FOIA dataset is the core fact source for the project. It provides public SBA lending records for the 7(a) and 504 loan programs.

This source is used to calculate:

- approved loan dollars;
- loan counts;
- average loan size;
- lending by state;
- lending by lender;
- lending by industry;
- lending by SBA loan program;
- lender concentration;
- lending trend metrics.

## Publisher

| Attribute | Value |
|---|---|
| Publisher | U.S. Small Business Administration |
| Organization | SBA Office of Capital Access |
| Data portal | SBA Open Data |
| Dataset | 7(a) and 504 FOIA |
| License | Public domain / public use |
| MVP priority | High |

## Access Method

The SBA source is published as downloadable CSV resources plus an XLSX data dictionary.

The ingestion process should not assume there is a single SBA file. The source is split across multiple resources by loan program and fiscal-year range.

### MVP SBA Resources

| Resource | Format | MVP Use |
|---|---|---|
| 7a_504_FOIA Data Dictionary | XLSX | Field definitions and source interpretation |
| FOIA - 7(a), FY1991-FY1999 | CSV | Historical 7(a) loans |
| FOIA - 7(a), FY2000-FY2009 | CSV | Historical 7(a) loans |
| FOIA - 7(a), FY2010-FY2019 | CSV | Historical 7(a) loans |
| FOIA - 7(a), FY2020-Present | CSV | Current 7(a) loans |
| FOIA - 504, FY1991-FY2009 | CSV | Historical 504 loans |
| FOIA - 504, FY2010-Present | CSV | Current 504 loans |

## Ingestion Design

The SBA ingestion script should:

1. Resolve current resource metadata from the SBA Open Data dataset page or CKAN metadata.
2. Identify CSV resources for 7(a) and 504 FOIA files.
3. Download each CSV file separately.
4. Download the data dictionary separately.
5. Store each raw file as an immutable ingestion snapshot.
6. Record source metadata in an ingestion manifest.
7. Load raw files into DuckDB locally for profiling.
8. Load final raw/staged data into Snowflake for the final version.

## Raw Landing Paths

```text
s3://small-business-lending-pipeline/raw/sba/7a_foia/source_period=fy1991_fy1999/ingestion_date=YYYY-MM-DD/file.csv
s3://small-business-lending-pipeline/raw/sba/7a_foia/source_period=fy2000_fy2009/ingestion_date=YYYY-MM-DD/file.csv
s3://small-business-lending-pipeline/raw/sba/7a_foia/source_period=fy2010_fy2019/ingestion_date=YYYY-MM-DD/file.csv
s3://small-business-lending-pipeline/raw/sba/7a_foia/source_period=fy2020_present/ingestion_date=YYYY-MM-DD/file.csv

s3://small-business-lending-pipeline/raw/sba/504_foia/source_period=fy1991_fy2009/ingestion_date=YYYY-MM-DD/file.csv
s3://small-business-lending-pipeline/raw/sba/504_foia/source_period=fy2010_present/ingestion_date=YYYY-MM-DD/file.csv

s3://small-business-lending-pipeline/raw/sba/data_dictionary/ingestion_date=YYYY-MM-DD/file.xlsx
```

## Expected Source Grain

The expected source grain is:

```text
one row per SBA loan record in the source file
```

The implementation should validate the actual grain during profiling. The project should not assume that a single natural key is stable across all SBA files until the source data dictionary and sample records are reviewed.

## Required Metadata Columns Added During Ingestion

Each raw SBA table should add ingestion metadata:

| Column | Purpose |
|---|---|
| `source_system` | Static value: `sba` |
| `source_dataset` | Static value: `7a_504_foia` |
| `loan_program_source` | `7a` or `504` |
| `source_resource_name` | Original SBA resource name |
| `source_file_name` | Downloaded file name |
| `source_period` | Fiscal-year range represented by the file |
| `source_row_number` | Row position in raw file |
| `source_row_hash` | Hash of raw row values |
| `ingested_at_utc` | Timestamp when pipeline ingested the file |
| `ingestion_date` | Date partition used in local/S3 storage |
| `raw_file_uri` | Local path or S3 URI for lineage |

## Candidate Field Groups

Exact field names must be confirmed against the SBA data dictionary during implementation.

The staging model should expect fields in these categories:

| Field Group | Examples of Fields to Standardize |
|---|---|
| Loan identification | loan number or program-specific identifier, source row hash |
| Program | 7(a), 504, delivery method, subprogram |
| Dates | approval date, fiscal year |
| Loan amount | gross approval amount, SBA guaranteed amount where available |
| Borrower geography | borrower state, city, ZIP, county where available |
| Lender | lender name, lender city/state where available |
| Industry | NAICS code, NAICS description where available |
| Business attributes | business type, franchise indicator where available |
| Jobs | jobs supported or jobs retained/created where available |
| Source metadata | source file, ingestion timestamp, row hash |

## Primary Join Keys

| Join Target | Join Field | Notes |
|---|---|---|
| `dim_state` | borrower state abbreviation or FIPS derived from state | Required for state-level reporting |
| `dim_date` | approval date | Used for month, quarter, fiscal year, calendar year |
| `dim_naics` | NAICS code | Used for sector and industry analysis |
| `dim_lender` | standardized lender name | Basic standardization in MVP |
| Census BDS | state FIPS + calendar year | Annual context only |
| BLS LAUS | state FIPS + calendar month/year | Labor-market context |

## SBA Data Quality Checks

| Check | Type | Expected Behavior |
|---|---|---|
| File exists for each required resource | Python validation | Fail if missing |
| File row count greater than minimum threshold | Python validation | Fail or warn depending on file |
| Expected columns present | Python validation | Fail |
| Approval date parseable | dbt / Python | Fail for excessive invalid rate |
| Loan amount numeric | dbt / Python | Fail for excessive invalid rate |
| Loan amount non-negative | dbt test | Fail |
| Borrower state populated for state-level marts | dbt test | Fail or quarantine |
| Source row hash populated | dbt test | Fail |
| Duplicate source row hash within file | dbt test | Warn or fail after profiling |
| Current file freshness | Python validation | Warn if expected quarterly update is stale |

## SBA Limitations

| Limitation | Handling Strategy |
|---|---|
| Files are segmented by program and fiscal-year range | Ingest each file separately and union in staging |
| Resource names include changing “as of” dates | Resolve resources dynamically where possible |
| Quarterly refresh is not real time | Schedule monthly freshness checks, but expect quarterly source updates |
| 7(a) and 504 schemas may not match perfectly | Create program-specific staging models before a normalized union |
| Lender names may vary | Apply basic trimming/casing in MVP; deeper entity resolution is stretch |
| Borrower-level fields may appear in raw data | Dashboard only publishes aggregated metrics |
| Approval data is not the same as repayment/default performance | Document KPI interpretation clearly |

---

# Source 2: Census Business Dynamics Statistics

## Source Overview

Census Business Dynamics Statistics is the MVP source for business formation and establishment context.

This source is used to compare SBA lending activity with broader business dynamics, such as:

- number of establishments;
- establishment entry;
- establishment entry rate;
- establishment exit;
- establishment exit rate;
- number of firms;
- job creation;
- job destruction.

## Publisher

| Attribute | Value |
|---|---|
| Publisher | U.S. Census Bureau |
| Dataset | Business Dynamics Statistics Time Series |
| Access method | Census API |
| MVP priority | High |
| Main project role | Business-health context |

## Access Method

The MVP should use the Census API endpoint:

```text
https://api.census.gov/data/timeseries/bds
```

The pipeline should use Python `requests` to call the API and write the raw JSON response to local storage and S3 before transformation.

A Census API key should be supported through environment variables, but the implementation should keep the code clean enough to run with small public requests where possible.

## MVP Pull Strategy

The first version should pull state-level annual data.

### State-Level Geography

```text
for=state:*
```

### MVP Year Range

Use a configurable year range.

Recommended first implementation:

```text
start_year = 2010
end_year = latest_available_bds_year
```

The source currently supports an annual time series. The project should not force BDS into monthly analysis.

## Candidate API Query Pattern

```text
https://api.census.gov/data/timeseries/bds
  ?get=NAME,YEAR,ESTAB,ESTABS_ENTRY,ESTABS_ENTRY_RATE,ESTABS_EXIT,ESTABS_EXIT_RATE,FIRM,JOB_CREATION,JOB_DESTRUCTION
  &for=state:*
  &YEAR=2023
```

The exact query may need adjustment based on valid BDS variable combinations.

## Expected Source Grain

The expected MVP grain is:

```text
one row per state per year per selected BDS query configuration
```

If NAICS or firm-size filters are added, the grain becomes:

```text
one row per state per year per NAICS/filter combination
```

## MVP Variables

| Variable | Business Meaning | MVP Use |
|---|---|---|
| `YEAR` | Reference year | Time join |
| `NAME` | Geography name | Display |
| `state` | State FIPS code | Join key |
| `ESTAB` | Number of establishments | Normalize lending |
| `ESTABS_ENTRY` | Establishments born during the last 12 months | Business formation context |
| `ESTABS_ENTRY_RATE` | Rate of establishment births | Business formation KPI |
| `ESTABS_EXIT` | Establishments exited during the last 12 months | Business churn context |
| `ESTABS_EXIT_RATE` | Rate of establishment exits | Business churn KPI |
| `FIRM` | Number of firms | Business base context |
| `JOB_CREATION` | Jobs created from expanding/opening establishments | Growth context |
| `JOB_DESTRUCTION` | Jobs lost from contracting/closing establishments | Contraction context |

## Raw Landing Paths

```text
s3://small-business-lending-pipeline/raw/census/bds/grain=state_year/ingestion_date=YYYY-MM-DD/bds_state_year.json
s3://small-business-lending-pipeline/raw/census/bds/grain=state_naics_year/ingestion_date=YYYY-MM-DD/bds_state_naics_year.json
```

The `state_naics_year` extract is optional for MVP. Start with `state_year`.

## Primary Join Keys

| Join Target | Join Field | Notes |
|---|---|---|
| `dim_state` | state FIPS | Required |
| `dim_date` | year | Annual context only |
| SBA annual lending marts | state FIPS + calendar year | Use SBA approval date aggregated to year |
| NAICS dimension | NAICS code | Optional if industry-level BDS is pulled |

## Census BDS Data Quality Checks

| Check | Type | Expected Behavior |
|---|---|---|
| API response status valid | Python validation | Fail |
| Response contains header row and data rows | Python validation | Fail |
| Required variables returned | Python validation | Fail |
| State FIPS populated | dbt test | Fail |
| Year populated | dbt test | Fail |
| Numeric indicators parseable | dbt / Python | Fail |
| Establishments non-negative | dbt test | Fail |
| Entry and exit rates within plausible range | dbt / Python | Warn or fail after profiling |
| No duplicate state-year rows in MVP extract | dbt test | Fail |
| Latest available BDS year recorded in manifest | Python validation | Warn if stale |

## Census BDS Limitations

| Limitation | Handling Strategy |
|---|---|
| Annual data has a reporting lag | Use BDS as context, not current-month signal |
| Grain differs from SBA and BLS | Join to annual lending marts only |
| Not every variable crossing is valid | Keep MVP query simple; add NAICS later |
| Some values may have flags or disclosure-related limitations | Preserve flag fields when returned |
| BDS measures business dynamics, not credit demand | Avoid causal language |
| State-level MVP hides local variation | County/metro analysis is stretch |

---

# Source 3: BLS Local Area Unemployment Statistics

## Source Overview

BLS Local Area Unemployment Statistics provides labor-market context for the lending dashboard.

This source is used to compare SBA lending activity with:

- unemployment rate;
- labor force size;
- employment;
- unemployment count;
- month-over-month and year-over-year labor-market changes.

The MVP should start with state-level unemployment rate. Additional LAUS measures can be added after the first working pipeline.

## Publisher

| Attribute | Value |
|---|---|
| Publisher | U.S. Bureau of Labor Statistics |
| Program | Local Area Unemployment Statistics |
| Access method | BLS Public Data API |
| MVP priority | High |
| Main project role | Labor-market context |

## Access Method

The MVP should use the BLS Public Data API endpoint:

```text
https://api.bls.gov/publicAPI/v2/timeseries/data/
```

The extractor should use Python `requests` with a JSON POST body.

A BLS API registration key should be supported through `.env`, because registered API usage supports higher limits. A limited unregistered fallback can be supported for small pulls.

## MVP Pull Strategy

The first version should pull state-level, seasonally adjusted unemployment-rate series for:

```text
50 states + District of Columbia
```

The pipeline should store the BLS series ID mapping in a local config file:

```text
config/bls_laus_state_series.yml
```

Example series IDs:

| State | Series ID | Measure |
|---|---|---|
| Alabama | `LASST010000000000003` | Unemployment rate, seasonally adjusted |
| California | `LASST060000000000003` | Unemployment rate, seasonally adjusted |
| Texas | `LASST480000000000003` | Unemployment rate, seasonally adjusted |

## Expected Source Grain

The expected MVP grain is:

```text
one row per state per month per BLS series
```

After staging, the target grain should be:

```text
state_fips + period_month + measure
```

## API Request Shape

Example request body:

```json
{
  "seriesid": [
    "LASST010000000000003",
    "LASST060000000000003",
    "LASST480000000000003"
  ],
  "startyear": "2015",
  "endyear": "2026",
  "registrationkey": "${BLS_API_KEY}"
}
```

The production extractor should chunk series requests to stay within BLS API limits.

## Raw Landing Paths

```text
s3://small-business-lending-pipeline/raw/bls/laus/grain=state_month/ingestion_date=YYYY-MM-DD/bls_laus_state_month.json
s3://small-business-lending-pipeline/raw/bls/laus/series_metadata/ingestion_date=YYYY-MM-DD/bls_laus_series_config.yml
```

## Primary Join Keys

| Join Target | Join Field | Notes |
|---|---|---|
| `dim_state` | state FIPS derived from series ID mapping | Required |
| `dim_date` | year + period converted to month date | Required |
| SBA monthly lending marts | state FIPS + month | Used for monthly lending/labor comparison |
| SBA annual lending marts | state FIPS + year | Use annual averages or year-end values as documented |

## BLS LAUS Data Quality Checks

| Check | Type | Expected Behavior |
|---|---|---|
| API response status valid | Python validation | Fail |
| Expected series count returned | Python validation | Fail or warn |
| Series ID exists in config mapping | Python validation | Fail |
| Period is monthly `M01` through `M12` | Python validation | Filter annual rows unless explicitly requested |
| Value numeric | dbt / Python | Fail |
| Unemployment rate between 0 and 100 | dbt test | Fail |
| No duplicate state-month-measure rows | dbt test | Fail |
| Latest month recorded in manifest | Python validation | Warn or fail depending on threshold |
| Footnotes preserved | Python validation | Warn if missing from response structure |

## BLS LAUS Limitations

| Limitation | Handling Strategy |
|---|---|
| API requires known BLS series IDs | Maintain explicit state-series config |
| API limits requests by series count, years, and daily volume | Chunk API calls and support API key |
| Some values may be preliminary or revised | Preserve footnotes and latest flags where available |
| Labor-market conditions are context, not causation | Avoid causal dashboard language |
| State-level labor conditions may hide metro/county variation | Lower-level geography is stretch |
| Monthly data may not align with SBA quarterly file refresh | Aggregate carefully and document grain |

---

# Common Reference Data

The project should maintain several small static reference tables. These can be stored as dbt seeds or local CSV files.

## `dim_state`

Purpose: standardize state names, abbreviations, and FIPS codes.

| Field | Description |
|---|---|
| `state_fips` | Two-digit Census/BLS state FIPS code |
| `state_abbr` | Two-character state abbreviation |
| `state_name` | Full state name |
| `census_region` | Optional Census region |
| `census_division` | Optional Census division |
| `is_state` | Boolean flag for 50 states |
| `is_dc` | Boolean flag for District of Columbia |

## `dim_date`

Purpose: support monthly, quarterly, annual, and fiscal-year reporting.

| Field | Description |
|---|---|
| `date_day` | Calendar date |
| `month_start_date` | First day of month |
| `calendar_year` | Calendar year |
| `calendar_quarter` | Calendar quarter |
| `fiscal_year` | Fiscal year, where relevant |
| `month_number` | Month number |
| `month_name` | Month name |

## `dim_naics`

Purpose: standardize industry reporting.

| Field | Description |
|---|---|
| `naics_code` | NAICS code |
| `naics_sector_code` | Two-digit NAICS sector |
| `naics_sector_name` | Sector name |
| `naics_description` | Industry description |
| `is_valid_current_code` | Optional validity flag |

## `dim_source_file`

Purpose: preserve ingestion lineage.

| Field | Description |
|---|---|
| `source_file_key` | Surrogate key |
| `source_system` | SBA, Census, BLS |
| `dataset_name` | Dataset identifier |
| `resource_name` | Source resource name |
| `source_url` | Source URL or API endpoint |
| `raw_file_uri` | Local/S3 location |
| `ingestion_date` | Date partition |
| `ingested_at_utc` | Timestamp |
| `row_count` | Raw row count |
| `column_count` | Raw column count |
| `sha256_checksum` | File checksum |
| `schema_hash` | Hash of column names/types |

---

# Source-to-KPI Mapping

| KPI / Metric | SBA FOIA | Census BDS | BLS LAUS |
|---|---:|---:|---:|
| Total approved loan dollars | Yes | No | No |
| Loan count | Yes | No | No |
| Average loan size | Yes | No | No |
| Lending by state | Yes | No | No |
| Lending by lender | Yes | No | No |
| Lending by industry | Yes | No | No |
| Lender concentration | Yes | No | No |
| Lending per establishment | Yes | Yes | No |
| Establishment entry rate | No | Yes | No |
| Establishment exit rate | No | Yes | No |
| Job creation / destruction context | No | Yes | No |
| Unemployment rate | No | No | Yes |
| Lending vs unemployment trend | Yes | No | Yes |
| Regional business-health context | Yes | Yes | Yes |

---

# Ingestion Sequence

The first complete ingestion flow should run in this order:

```text
1. Load static reference seeds
2. Extract SBA FOIA resource metadata
3. Download SBA CSV files and data dictionary
4. Validate SBA raw files
5. Extract Census BDS state-year data
6. Validate Census API response
7. Extract BLS LAUS state-month data
8. Validate BLS API response
9. Write raw files to local storage
10. Upload raw files to S3
11. Write ingestion manifests
12. Load raw files into DuckDB for local development
13. Load raw files into Snowflake for final pipeline
```

---

# Ingestion Manifest Specification

Each source extraction should create a manifest file.

## Manifest Path

```text
s3://small-business-lending-pipeline/manifests/source_system=<source>/ingestion_date=YYYY-MM-DD/manifest.json
```

## Required Manifest Fields

| Field | Description |
|---|---|
| `pipeline_run_id` | Prefect run ID or generated UUID |
| `source_system` | `sba`, `census`, or `bls` |
| `dataset_name` | Source dataset name |
| `resource_name` | Source resource name or API query name |
| `source_url` | Source URL or endpoint |
| `request_parameters` | API parameters or file metadata |
| `extracted_at_utc` | Extraction timestamp |
| `ingestion_date` | Partition date |
| `local_raw_path` | Local raw file path |
| `s3_raw_uri` | S3 object URI |
| `file_format` | CSV, JSON, XLSX, YAML |
| `row_count` | Number of rows or records |
| `column_count` | Number of columns where applicable |
| `file_size_bytes` | File size |
| `sha256_checksum` | Raw file checksum |
| `schema_hash` | Hash of field names and inferred types |
| `validation_status` | Passed, warning, failed |
| `validation_messages` | List of validation messages |

---

# Source Freshness Rules

| Source | Expected Freshness Rule | Severity |
|---|---|---|
| SBA FOIA | Latest source “as of” date should be within the expected quarterly update window | Warning first, fail if very stale |
| Census BDS | Latest available year should match documented current BDS release | Warning |
| BLS LAUS | Latest available month should be within expected BLS publication lag | Warning or fail |
| Reference seeds | Must exist and pass uniqueness tests | Fail |

Freshness rules should be conservative. Public datasets have publication delays and revisions. The pipeline should distinguish between:

```text
source has not published new data yet
```

and:

```text
pipeline failed to ingest available data
```

---

# Optional Sources Not Included in MVP

## Census Business Formation Statistics

Census Business Formation Statistics is a useful stretch source because it provides more timely business application and formation indicators than BDS.

Potential use:

- business applications by state and month;
- high-propensity business applications;
- projected business formations;
- current business formation trend context.

Reason not included in MVP:

- it adds another Census source before the core BDS model is complete;
- it measures applications and projected formations, not the same concept as actual establishments/firms in BDS;
- it would require additional KPI definitions and caveats.

## SBA 7(a) and 504 Activity Reports

SBA activity reports are useful as summary-level reconciliation or stakeholder-friendly source checks.

Potential use:

- compare loan totals from FOIA-derived marts against SBA summary reports;
- validate lender or state totals;
- add current fiscal-year summary views.

Reason not included in MVP:

- the FOIA files are the better core source for detailed loan-level modeling;
- activity reports are summary-oriented;
- adding both in the first version increases ingestion and reconciliation complexity.

---

# Data Source Acceptance Criteria

Step 4 is complete when the project has:

1. A documented inventory of all MVP sources.
2. A documented source role for each dataset.
3. A defined access method for each dataset.
4. A defined raw landing path for each dataset.
5. A documented expected grain for each dataset.
6. A documented join strategy across SBA, Census, and BLS data.
7. A first-pass list of expected source fields and indicators.
8. A first-pass list of validation checks for each source.
9. A manifest specification for ingestion metadata.
10. Explicitly documented limitations and non-MVP sources.

---

# Step 4 Summary

The MVP will use SBA FOIA files as the core lending fact source, Census BDS as annual business dynamics context, and BLS LAUS as monthly labor-market context.

The source design intentionally separates raw ingestion from analytical modeling. Raw files will be stored as immutable snapshots in S3, while dbt models will standardize and aggregate the data into staging, mart, and BI-ready tables.

The project will avoid adding optional datasets until the core pipeline is working end-to-end.

---

# Source References

- SBA 7(a) and 504 FOIA dataset: https://data.sba.gov/en/dataset/7-a-504-foia
- Data.gov SBA 7(a) and 504 Loan Data Reports metadata: https://catalog.data.gov/dataset/sba-7a-and-504-loan-data-reports
- SBA lender reports: https://www.sba.gov/partners/lenders/lender-reports
- Census BDS API documentation: https://www.census.gov/data/developers/data-sets/business-dynamics.html
- Census BDS API endpoint: https://api.census.gov/data/timeseries/bds
- Census BDS variables: https://api.census.gov/data/timeseries/bds/variables.html
- Census 2023 BDS release: https://www.census.gov/newsroom/press-releases/2025/business-dynamics-statistics.html
- BLS LAUS homepage: https://www.bls.gov/lau/
- BLS Public Data API overview: https://www.bls.gov/developers/home.htm
- BLS API features and limits: https://www.bls.gov/bls/api_features.htm
- BLS API Python examples: https://www.bls.gov/developers/api_python.htm
- BLS series ID format guide: https://www.bls.gov/help/hlpforma.htm
- Census Business Formation Statistics data tables: https://www.census.gov/data/tables/time-series/econ/bfs/business-formation-statistics.html
