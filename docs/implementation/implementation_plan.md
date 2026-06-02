# Small Business Lending Intelligence Pipeline — Implementation Plan

## Recommendation: One Implementation Plan First

Use one master implementation plan document for the build:

```text
docs/implementation/implementation_plan.md
```

Use task IDs inside the document, then convert those IDs into GitHub issues when implementation starts.

A document per task is not recommended at the beginning. It creates too much documentation overhead before the project is stable. After the repository exists and the task boundaries are validated, each task can become a GitHub issue or project-board card.

## Planning Principles

1. Build local-first with DuckDB before adding S3 and Snowflake.
2. Ingest, validate, and model data before designing final dashboard pages.
3. Keep KPI logic in dbt, not Power BI.
4. Keep AWS scope focused on S3 raw storage.
5. Use Snowflake for the final warehouse version after local correctness is proven.
6. Preserve raw files, manifests, row counts, checksums, and validation output.
7. Exclude predictive machine learning from the MVP.
8. Avoid infrastructure sprawl: no Glue, Lambda, Step Functions, Spark, Kubernetes, or Terraform for MVP.

---

# Phase 0: Project Foundation

## Task T00 — Repository Skeleton

### Goal

Create the repository structure needed to support Python ingestion, dbt models, tests, orchestration, documentation, and Power BI outputs.

### Deliverables

```text
small-business-lending-pipeline/
├── README.md
├── .gitignore
├── .env.example
├── requirements.txt
├── pyproject.toml
├── Makefile
├── Dockerfile
├── docker-compose.yml
├── config/
├── docs/
├── pipelines/
├── dbt/
├── tests/
├── scripts/
├── data/
└── powerbi/
```

### Non-Goals

- Do not implement business logic yet.
- Do not connect to Snowflake yet.
- Do not build Power BI yet.
- Do not add CI/CD yet.

### Test Criteria

- Repository installs locally.
- `python --version` returns expected version.
- `pip install -r requirements.txt` succeeds.
- `make test` can run even if only placeholder tests exist.

### Acceptance Criteria

- Folder structure exists.
- `.env.example` exists and contains all required environment variables.
- `.gitignore` excludes `.env`, local data, DuckDB files, dbt targets, and secrets.
- README has placeholder sections for overview, architecture, setup, testing, dashboard, and screenshots.

---

## Task T01 — Runtime and Dependency Setup

### Goal

Create a reproducible local runtime for Python, DuckDB, dbt, pytest, Prefect, and optional Snowflake/S3 support.

### Deliverables

- `requirements.txt`
- `Dockerfile`
- `docker-compose.yml`
- `Makefile`
- local run scripts

### Required Dependencies

```text
requests
pandas
pyyaml
python-dotenv
boto3
duckdb
snowflake-connector-python
dbt-core
dbt-duckdb
dbt-snowflake
prefect
pytest
```

### Non-Goals

- No Kubernetes.
- No Terraform.
- No complex Docker service mesh.
- No managed Prefect deployment required.

### Test Criteria

```bash
make install
make test
python -c "import duckdb, pandas, requests, prefect"
```

### Acceptance Criteria

- Local runtime works outside Docker.
- Docker runtime builds successfully.
- Makefile exposes at least:

```bash
make install
make test
make run-local
make dbt-local
```

---

## Task T02 — Configuration and Reference Seeds

### Goal

Centralize source settings, raw validation expectations, freshness rules, and reference data.

### Deliverables

```text
config/
├── sources.yml
├── sba_resources.yml
├── census_bds_variables.yml
├── bls_laus_state_series.yml
├── freshness_rules.yml
└── raw_validation_expectations.yml

dbt/seeds/
├── ref_state.csv
├── ref_naics.csv
└── ref_bls_laus_state_series.csv
```

### Non-Goals

- Do not hardcode secrets.
- Do not hardcode live row counts from public datasets.
- Do not implement complex lender entity resolution.

### Test Criteria

- Config files parse successfully.
- Required keys exist.
- `ref_state.csv` includes 50 states plus DC.
- `ref_bls_laus_state_series.csv` maps every reporting state/DC to a LAUS series ID.

### Acceptance Criteria

- Config loader returns typed config objects or dictionaries.
- pytest covers config loading and required keys.
- dbt seeds can load locally.

---

# Phase 1: Ingestion Framework

## Task T03 — Shared Ingestion Utilities

### Goal

Build reusable utility functions for paths, checksums, manifests, row hashes, timestamps, and structured extraction results.

### Deliverables

```text
pipelines/utils/
├── paths.py
├── hashing.py
├── manifest.py
└── dates.py
```

### Non-Goals

- Do not implement source-specific extraction here.
- Do not create dbt models here.
- Do not calculate KPIs in Python.

### Test Criteria

- Checksums are deterministic.
- S3 keys follow the partitioning convention.
- Manifest required fields are enforced.
- Timestamps are UTC.

### Acceptance Criteria

- Utility tests pass.
- Manifest output includes:

```text
pipeline_run_id
source_system
dataset_name
resource_name
source_url
extracted_at_utc
ingestion_date
local_raw_path
s3_raw_uri
file_format
row_count
sha256_checksum
schema_hash
validation_status
```

---

## Task T04 — SBA FOIA Extractor

### Goal

Download SBA 7(a), 504, and data dictionary resources into local raw storage with source metadata.

### Deliverables

```text
pipelines/extract/sba_extract.py
data/raw/sba/...
data/manifests/sba/...
```

### Source Scope

- SBA 7(a) FOIA CSV files.
- SBA 504 FOIA CSV files.
- SBA data dictionary XLSX.

### Non-Goals

- Do not clean or standardize SBA fields yet.
- Do not combine 7(a) and 504 yet.
- Do not perform lender entity resolution.
- Do not expose borrower-level records in outputs.

### Test Criteria

- Extractor resolves expected resources.
- Each required CSV downloads.
- Data dictionary download warns if unavailable but does not block MVP.
- Raw files are written to partitioned local paths.
- Manifest row count and checksum are generated.

### Acceptance Criteria

- SBA extractor can run independently.
- All required SBA files are present locally.
- Manifest exists for every SBA resource.
- pytest covers resource parsing, path creation, and manifest creation with fixtures/mocks.

---

## Task T05 — Census BDS Extractor

### Goal

Extract state-year business dynamics data from the Census BDS API.

### Deliverables

```text
pipelines/extract/census_bds_extract.py
data/raw/census/bds/...
data/manifests/census/...
```

### MVP Variables

```text
YEAR
NAME
state
ESTAB
ESTABS_ENTRY
ESTABS_ENTRY_RATE
ESTABS_EXIT
ESTABS_EXIT_RATE
FIRM
JOB_CREATION
JOB_DESTRUCTION
```

### Non-Goals

- Do not add Census BFS.
- Do not add county-level or metro-level data.
- Do not force BDS into monthly grain.

### Test Criteria

- API URL/request is constructed correctly.
- Response contains header row and data rows.
- Required variables are present.
- State-year grain is preserved.
- Raw JSON is saved before normalization.

### Acceptance Criteria

- Census extractor can run independently.
- Configurable year range works.
- Manifest captures latest available year and row count.
- pytest covers response-shape validation using fixture JSON.

---

## Task T06 — BLS LAUS Extractor

### Goal

Extract state-month unemployment-rate data from the BLS LAUS API.

### Deliverables

```text
pipelines/extract/bls_laus_extract.py
data/raw/bls/laus/...
data/manifests/bls/...
```

### Non-Goals

- Do not add every LAUS measure at first.
- Do not add county or metro series.
- Do not call live APIs in default unit tests.

### Test Criteria

- Series IDs load from config.
- Requests are chunked if necessary.
- Monthly periods `M01` through `M12` parse to month-start dates.
- Annual periods are excluded unless explicitly enabled.
- Values parse as numeric.

### Acceptance Criteria

- BLS extractor can run independently.
- Raw JSON is saved locally.
- Manifest includes series count, latest observed month, checksum, and row count.
- pytest covers period parsing, request construction, and fixture normalization.

---

# Phase 2: Raw Validation and Local Warehouse Loading

## Task T07 — Raw Validation Framework

### Goal

Validate source extracts before they enter DuckDB, Snowflake, dbt models, or Power BI outputs.

### Deliverables

```text
pipelines/validation/
├── raw_manifest_artifact_validation.py
├── raw_manifest_collection.py
├── raw_manifest_rule_checks.py
├── raw_payload_resources.py
├── raw_validation_check_catalog.py
├── raw_validation_expectations.py
├── raw_validation_models.py
├── raw_validation_output.py
├── raw_validation_resources.py
├── raw_validation_runner.py
├── raw_validation_sources.py
├── sba_payload_checks.py
├── census_bds_payload_checks.py
├── bls_laus_payload_checks.py
├── validation_failures.py
├── validation_result.py
└── validation_result_io.py
```

`raw_validation_runner.py` coordinates the active raw gate. Validation check
catalog metadata, manifest/artifact checks, result schema/factories, JSON I/O,
output persistence, source dispatch, source expectations, and blocking-failure
enforcement live in ownership modules. `pipelines/flows/pipeline_health.py`
contains future row-count and freshness helper checks for a later
pipeline-health layer; `pipelines/validation/pipeline_health.py` remains a
compatibility import.

### Non-Goals

- Do not duplicate all dbt model tests in Python.
- Do not hardcode exact live public-dataset row counts.
- Do not silently drop invalid records.

### Test Criteria

Required raw checks:

```text
file exists
file size > 0
checksum generated
row count captured
required metadata populated
schema hash generated
manifest created
validation result created
```

Source-specific checks:

- SBA required resources found and readable.
- Census response contains required variables and state coverage.
- BLS response contains expected series and valid monthly periods.

### Acceptance Criteria

- Validation output is written as JSON.
- Failure/warning/info severity is supported.
- Critical raw failures block warehouse loading.
- pytest covers validation outputs and failure behavior.

---

## Task T08 — Local DuckDB Raw Loader

### Goal

Load validated raw extracts into DuckDB raw tables for local development.

### Deliverables

```text
pipelines/load/duckdb_loader.py
data/warehouse/small_business_lending.duckdb
```

### Raw Tables

```text
raw.raw_sba_7a_foia
raw.raw_sba_504_foia
raw.raw_census_bds_state_year
raw.raw_bls_laus_state_month
raw.raw_ingestion_manifest
raw.raw_validation_result
raw.raw_pipeline_run_summary
```

### Non-Goals

- Do not build marts in Python.
- Do not skip raw validation.
- Do not overwrite immutable raw files.

### Test Criteria

- DuckDB schemas are created if missing.
- Raw tables are created or replaced locally.
- Row counts reconcile to manifests.
- Ingestion metadata columns are present.

### Acceptance Criteria

- Local raw tables exist in DuckDB.
- Row count checks pass.
- A developer can inspect raw tables locally.
- pytest integration test loads fixture data into DuckDB.

---

# Phase 3: dbt Modeling

## Task T09 — dbt Project Setup

### Goal

Initialize dbt Core project for DuckDB local development and Snowflake final target.

### Deliverables

```text
dbt/dbt_project.yml
dbt/profiles.yml.example
dbt/models/sources/sources.yml
dbt/seeds/
dbt/macros/
```

### Required Macros

```text
generate_surrogate_key.sql
safe_divide.sql
clean_lender_name.sql
date_spine.sql
```

### Non-Goals

- Do not optimize for performance yet.
- Do not implement incremental models yet.
- Do not add external dbt packages unless necessary.

### Test Criteria

```bash
cd dbt && dbt debug --target dev_duckdb
cd dbt && dbt parse --target dev_duckdb
cd dbt && dbt seed --target dev_duckdb
```

### Acceptance Criteria

- dbt project parses.
- Seeds load locally.
- Sources are documented.
- dbt target naming is consistent with runtime config.

---

## Task T10 — Staging Models

### Goal

Standardize raw SBA, Census, BLS, reference, and audit data into canonical staged models.

### Deliverables

```text
dbt/models/staging/sba/stg_sba_7a_loans.sql
dbt/models/staging/sba/stg_sba_504_loans.sql
dbt/models/staging/sba/stg_sba_loans.sql
dbt/models/staging/census/stg_census_bds_state_year.sql
dbt/models/staging/bls/stg_bls_laus_state_month.sql
dbt/models/staging/audit/stg_ingestion_manifest.sql
dbt/models/staging/audit/stg_validation_result.sql
```

### Non-Goals

- Do not calculate final KPIs in staging.
- Do not build final dashboard tables yet.
- Do not attempt complex lender entity resolution.

### Test Criteria

- `loan_record_key` not null and unique.
- `loan_program` accepted values: `7a`, `504`.
- `gross_approval_amount >= 0`.
- state values map to `dim_state` or are flagged.
- BDS state-year grain is unique.
- LAUS state-month-measure grain is unique.
- unemployment rate is between 0 and 100.

### Acceptance Criteria

- Staging models build locally.
- Staging tests pass.
- Source metadata is preserved.
- Latest-successful snapshot filter pattern is established.

---

## Task T11 — Dimensions and Facts

### Goal

Build reusable dimensions and fact tables that support KPI marts and BI tables.

### Deliverables

```text
dbt/models/marts/dimensions/dim_date.sql
dbt/models/marts/dimensions/dim_state.sql
dbt/models/marts/dimensions/dim_naics.sql
dbt/models/marts/dimensions/dim_lender.sql
dbt/models/marts/dimensions/dim_loan_program.sql
dbt/models/marts/dimensions/dim_source_file.sql

dbt/models/marts/facts/fact_sba_loans.sql
dbt/models/marts/facts/fact_laus_state_month.sql
dbt/models/marts/facts/fact_bds_state_year.sql
```

### Non-Goals

- Do not expose loan-level fact tables to Power BI by default.
- Do not create borrower-level dashboard pages.
- Do not use unstable natural keys without validation.

### Test Criteria

- Dimension keys are not null and unique.
- Fact keys are not null and unique.
- Foreign-key relationships pass.
- Unknown lender and unknown NAICS rows exist.
- Fact rows use latest successful source snapshots only.

### Acceptance Criteria

- Facts and dimensions build locally.
- dbt relationship tests pass.
- Source lineage is available through `dim_source_file`.
- Loan-level fact is available for aggregation but not dashboard exposure.

---

## Task T12 — Lending Marts

### Goal

Build business-ready lending KPI marts for state trends, lenders, concentration, industries, and programs.

### Deliverables

```text
dbt/models/marts/lending/mart_lending_monthly_state.sql
dbt/models/marts/lending/mart_lending_annual_state.sql
dbt/models/marts/lending/mart_lending_lender_state_period.sql
dbt/models/marts/lending/mart_lending_concentration_state_period.sql
dbt/models/marts/lending/mart_lending_industry_state_period.sql
dbt/models/marts/lending/mart_lending_program_state_period.sql
```

### Required KPIs

```text
total_approved_loan_amount
loan_count
average_loan_size
approved_loan_amount_yoy_growth_pct
loan_count_yoy_growth_pct
lender_approved_amount_share
top_5_lender_share
industry_approved_amount_share
program_approved_amount_share
```

### Non-Goals

- Do not implement ML forecasts.
- Do not add HHI unless core shares are stable.
- Do not calculate these metrics in Power BI.

### Test Criteria

- Each mart has unique documented grain.
- Counts and dollar amounts are non-negative.
- Shares are between 0 and 1.
- Annual totals reconcile to fact table.
- Lender, industry, and program marts reconcile to annual lending totals.

### Acceptance Criteria

- Lending marts build and pass required dbt tests.
- KPI logic matches KPI dictionary.
- No grain duplication.
- Marts are ready for BI-layer consumption.

---

## Task T13 — Context and Regional Business Health Marts

### Goal

Build context marts for Census BDS, BLS LAUS, and cross-source regional business-health analysis.

### Deliverables

```text
dbt/models/marts/context/mart_laus_monthly_state.sql
dbt/models/marts/context/mart_laus_annual_state.sql
dbt/models/marts/context/mart_business_dynamics_annual_state.sql
dbt/models/marts/context/mart_regional_business_health_annual_state.sql
```

### Required KPIs

```text
unemployment_rate
unemployment_rate_yoy_change_pp
annual_average_unemployment_rate
establishment_count
establishment_entry_rate
establishment_exit_rate
loans_per_1000_establishments
approved_loan_dollars_per_establishment
```

### Non-Goals

- Do not present context metrics as causal.
- Do not repeat annual BDS values across monthly visuals.
- Do not add county/metro context yet.

### Test Criteria

- LAUS monthly mart has one row per state-month.
- BDS annual mart has one row per state-year.
- Regional business health mart has one row per state-year.
- Safe division returns null for zero/missing denominators.
- Context flags correctly indicate missing joins.

### Acceptance Criteria

- Cross-source joins use compatible grains.
- Regional annual mart is ready for Power BI.
- Tests confirm no duplicated state-year rows.

---

## Task T14 — BI and Audit Models

### Goal

Build dashboard-facing BI tables and pipeline health marts.

### Deliverables

```text
dbt/models/bi/bi_executive_overview.sql
dbt/models/bi/bi_state_lending_trends.sql
dbt/models/bi/bi_lender_concentration.sql
dbt/models/bi/bi_industry_mix.sql
dbt/models/bi/bi_program_mix.sql
dbt/models/bi/bi_regional_business_health.sql
dbt/models/bi/bi_pipeline_health.sql

dbt/models/marts/pipeline/mart_pipeline_source_freshness.sql
dbt/models/marts/pipeline/mart_pipeline_validation_summary.sql
dbt/models/marts/pipeline/mart_pipeline_run_summary.sql
```

### Non-Goals

- Do not expose raw borrower-level fields.
- Do not require complex Power BI measures for core metrics.
- Do not hide failed or warning validation checks.

### Test Criteria

- BI tables have expected grains.
- BI tables have rows after a successful run.
- Required KPI columns exist.
- Prohibited raw fields are absent from business-facing BI tables.
- Pipeline health table shows freshness, validation, and latest run status.

### Acceptance Criteria

- BI layer is the default Power BI source.
- Data quality information is dashboard-ready.
- dbt tests pass for BI models.

---

# Phase 4: Testing, Orchestration, and Local End-to-End Run

## Task T15 — dbt Test Suite and Reconciliation Tests

### Goal

Implement required dbt tests for staging, facts, dimensions, marts, BI, and latest-snapshot enforcement.

### Deliverables

```text
dbt/models/**/_models.yml
dbt/tests/assert_*.sql
```

### Non-Goals

- Do not depend on exact live public-source row counts.
- Do not rely only on Power BI visual checks.
- Do not retry failed dbt tests blindly.

### Test Criteria

Minimum required dbt tests:

```text
primary keys not null and unique
state relationships to dim_state
source file relationships to dim_source_file
accepted values for loan_program
non-negative loan amounts
unemployment rate between 0 and 100
one row per state-month in monthly marts
one row per state-year in annual marts
lender shares between 0 and 1
top lender share ordering
annual lending totals reconcile to fact table
BI tables have expected grain
latest-snapshot rule enforced
```

### Acceptance Criteria

- `dbt build --target dev_duckdb` passes locally.
- Reconciliation tests pass.
- dbt documentation includes model descriptions, grain, and column descriptions.

---

## Task T16 — pytest Suite

### Goal

Test Python ingestion, validation, manifest, hashing, path, config, and loader behavior.

### Deliverables

```text
tests/unit/
tests/integration/
tests/fixtures/
```

### Non-Goals

- Do not call live APIs in default unit tests.
- Do not require AWS or Snowflake credentials for default tests.
- Do not duplicate all dbt logic in Python.

### Test Criteria

Minimum pytest coverage:

```text
manifest required fields
checksum determinism
S3/local path construction
SBA raw validation with sample CSV
Census response validation with sample JSON
BLS response validation with sample JSON
BLS period parsing
config loading
validation result schema
DuckDB fixture load
```

### Acceptance Criteria

- `pytest` passes locally.
- Live API/cloud tests are marked optional.
- Fixtures are small and safe to commit.

---

## Task T17 — Prefect Local Flow

### Goal

Orchestrate local extraction, validation, DuckDB loading, dbt build, BI validation, and local Power BI exports.

### Deliverables

```text
pipelines/flows/lending_pipeline_flow.py
scripts/run_local_pipeline.sh
```

### Non-Goals

- Do not automate Power BI Service refresh.
- Do not put KPI logic inside Prefect.
- Do not add complex scheduling before manual runs work.

### Test Criteria

Flow stages:

```text
initialize run
load config
extract sources
validate raw outputs
write manifests
load DuckDB raw tables
run dbt build
collect dbt artifacts
validate BI tables
export BI tables
write run summary
```

### Acceptance Criteria

- `make run-local` completes successfully.
- Failed validation stops the pipeline before dbt/BI publish.
- Run summary is written even when practical failures occur.
- Prefect logs show task-level visibility.

---

## Task T18 — Local Power BI Export

### Goal

Export local DuckDB BI tables for Power BI prototype development.

### Deliverables

```text
scripts/export_powerbi_tables.py
data/exports/powerbi/
├── bi_executive_overview.csv
├── bi_state_lending_trends.csv
├── bi_lender_concentration.csv
├── bi_industry_mix.csv
├── bi_program_mix.csv
├── bi_regional_business_health.csv
└── bi_pipeline_health.csv
```

### Non-Goals

- Do not build final dashboard yet.
- Do not export raw source files.
- Do not include borrower-level details.

### Test Criteria

- Every required BI export file exists.
- Every export has rows.
- Required columns are present.
- Prohibited raw borrower-level fields are absent.

### Acceptance Criteria

- Power BI can connect to local export files.
- Local prototype can be built before Snowflake promotion.

---

# Phase 5: S3 and Snowflake Promotion

## Task T19 — AWS S3 Raw Landing Zone

### Goal

Upload raw snapshots, manifests, validation results, and dbt artifacts to AWS S3 using the approved partitioning pattern.

### Deliverables

```text
pipelines/load/s3_loader.py
s3://small-business-lending-pipeline/raw/...
s3://small-business-lending-pipeline/manifests/...
s3://small-business-lending-pipeline/validation/...
```

### Non-Goals

- No Glue.
- No Athena.
- No Lambda.
- No Step Functions.
- No Terraform for MVP.

### Test Criteria

- S3 keys are partitioned by source, dataset/resource, ingestion date, and run ID.
- Upload function handles retries for transient failures.
- Final mode fails if required S3 upload fails.
- Local mode can warn instead of fail when S3 is disabled.

### Acceptance Criteria

- Raw source files exist in S3.
- Manifests exist in S3.
- Validation output exists in S3.
- Screenshots can prove S3 raw landing structure without exposing secrets.

---

## Task T20 — Snowflake Raw Load

### Goal

Load raw source data and pipeline metadata into Snowflake raw/audit schemas.

### Deliverables

```text
pipelines/load/snowflake_loader.py
Snowflake schemas: RAW, STAGING, INTERMEDIATE, MARTS, BI, AUDIT
```

### Preferred Pattern

```text
S3 raw files → Snowflake stage → COPY INTO raw tables
```

### MVP Fallback

```text
S3 raw files → Python Snowflake connector → raw tables
```

### Non-Goals

- Do not optimize warehouse performance prematurely.
- Do not expose credentials in logs or screenshots.
- Do not skip S3 raw landing before Snowflake load.

### Test Criteria

- Snowflake schemas exist.
- Raw tables exist.
- Row counts reconcile to manifests.
- Ingestion metadata is populated.

### Acceptance Criteria

- Final warehouse mode can load raw tables into Snowflake.
- dbt can target Snowflake successfully.

---

## Task T21 — dbt Snowflake Build

### Goal

Run the same dbt model design against Snowflake as the final warehouse target.

### Deliverables

```text
Snowflake STAGING, INTERMEDIATE, MARTS, BI, AUDIT tables/views
```

### Non-Goals

- Do not rewrite all SQL specifically for Snowflake.
- Do not introduce incremental models before full-refresh works.
- Do not connect Power BI to raw tables.

### Test Criteria

```bash
cd dbt && dbt build --target prod_snowflake
```

Required:

- staging tests pass;
- mart tests pass;
- reconciliation tests pass;
- BI validation passes;
- audit/pipeline health models populate.

### Acceptance Criteria

- Snowflake BI schema is dashboard-ready.
- dbt docs/lineage can be generated.
- Final modeled tables match local logic.

---

## Task T22 — Prefect Cloud Mode

### Goal

Extend the Prefect flow to run cloud mode: extraction, raw validation, S3 artifact recording, Snowflake load, dbt Snowflake build, BI validation, and run summary.

### Deliverables

```text
make run-cloud
scripts/run_cloud_pipeline.sh
```

### Non-Goals

- No Power BI Service automation required.
- No production alerting stack.
- No complex multi-schedule design.

### Test Criteria

- Cloud mode requires AWS and Snowflake config.
- Raw validation happens before S3/Snowflake loading.
- dbt tests must pass before BI tables are considered dashboard-ready.
- Run summary records cloud-mode status.

### Acceptance Criteria

- `make run-cloud` completes successfully.
- S3 and Snowflake artifacts are created.
- Final BI tables are available for Power BI.

---

# Phase 6: Power BI Dashboard

## Task T23 — Power BI Data Model

### Goal

Connect Power BI to modeled BI tables and build a clean semantic layer for dashboard pages.

### Deliverables

```text
powerbi/lending_dashboard.pbix
```

### Required Tables

```text
bi_executive_overview
bi_state_lending_trends
bi_lender_concentration
bi_industry_mix
bi_program_mix
bi_regional_business_health
bi_pipeline_health
```

### Non-Goals

- Do not connect Power BI to raw files.
- Do not define core KPI formulas only in Power BI.
- Do not expose borrower-level records.

### Test Criteria

- Power BI connects to local exports or Snowflake BI schema.
- Table relationships do not create misleading many-to-many joins.
- Core KPIs match dbt outputs.
- Filters work for year, state, region, program, industry, and lender.

### Acceptance Criteria

- Power BI data model is stable.
- Measures are limited to formatting/dynamic titles/simple display logic.
- KPI values reconcile to BI tables.

---

## Task T24 — Dashboard Pages

### Goal

Build six recruiter-ready Power BI pages.

### Required Pages

```text
01 Executive Overview
02 State Lending Trends
03 Lender Concentration
04 Industry and Program Mix
05 Regional Business Health
06 Data Quality and Pipeline Health
```

### Non-Goals

- No embedded analytics app.
- No row-level security for MVP.
- No live operational alerting.
- No pixel-perfect executive production report requirement.

### Test Criteria

Each page has required KPIs and visuals.

Required screenshot outputs:

```text
powerbi/screenshots/01_executive_overview.png
powerbi/screenshots/02_state_lending_trends.png
powerbi/screenshots/03_lender_concentration.png
powerbi/screenshots/04_industry_program_mix.png
powerbi/screenshots/05_regional_business_health.png
powerbi/screenshots/06_pipeline_health.png
```

### Acceptance Criteria

- Dashboard answers the business questions from the spec.
- Pipeline health page exposes freshness, validation pass rate, row counts, warnings/failures, and latest successful run.
- Notes/caveats avoid causal claims and explain SBA coverage limits.
- Screenshots are saved for README use.

---

# Phase 7: Documentation and Recruiter Polish

## Task T25 — README Finalization

### Goal

Create a recruiter-facing README that explains the project in under five minutes.

### Deliverables

```text
README.md
```

### Required Sections

```text
Project overview
Business problem
Architecture diagram
Tech stack
Data sources
Data model summary
KPI examples
Data quality strategy
Orchestration
Dashboard screenshots
How to run locally
Final warehouse notes
What this demonstrates
Limitations and non-goals
```

### Non-Goals

- Do not bury the reader in implementation details.
- Do not include credentials or private account identifiers.
- Do not make unsupported production claims.

### Test Criteria

- README includes architecture diagram.
- README includes dashboard screenshots.
- README includes dbt/test evidence.
- README includes run commands.
- README states no ML in MVP.

### Acceptance Criteria

- A recruiter can understand the project quickly.
- A technical reviewer can see enough depth to inspect the code.
- Setup and run commands are accurate.

---

## Task T26 — Supporting Documentation Finalization

### Goal

Finalize docs used by technical reviewers.

### Deliverables

```text
docs/detailed/project_spec.md
docs/detailed/data_source_inventory.md
docs/detailed/kpi_definitions.md
docs/detailed/data_dictionary.md
docs/detailed/data_model.md
docs/detailed/architecture.md
docs/detailed/testing_plan.md
docs/detailed/orchestration_runtime.md
docs/detailed/dashboard_spec.md
docs/implementation/implementation_plan.md
```

### Non-Goals

- Do not maintain duplicate conflicting definitions.
- Do not over-document every small helper function.
- Do not create task docs unless converting to GitHub issues.

### Test Criteria

- KPI definitions match dbt model columns.
- Data model docs match actual dbt model names.
- Architecture docs match final local/final modes.
- Dashboard spec matches screenshots.

### Acceptance Criteria

- Documentation is internally consistent.
- All major project decisions are documented.
- Non-goals and limitations are clear.

---

## Task T27 — Recruiter Evidence Pack

### Goal

Collect visible proof that the project runs and is not just a static dashboard.

### Deliverables

```text
powerbi/screenshots/*.png
docs/images/architecture.png
docs/images/dbt_lineage.png
docs/images/dbt_tests.png
docs/images/prefect_flow.png
docs/images/s3_raw_landing.png
docs/images/snowflake_schemas.png
```

### Non-Goals

- Do not expose credentials.
- Do not expose private account identifiers.
- Do not include noisy screenshots that obscure the main signal.

### Test Criteria

Evidence should show:

```text
S3 raw landing zone
Snowflake schemas/tables
dbt tests passing
Prefect flow run
Power BI dashboard
Pipeline health page
```

### Acceptance Criteria

- README uses the best screenshots.
- Screenshots are clean and cropped.
- Sensitive information is removed.

---

# Final Acceptance Criteria

## Business Acceptance

The project is business-complete when the dashboard answers:

1. Which states have the highest approved SBA lending volume?
2. How has lending changed over time?
3. Which lenders dominate lending in a state or year?
4. How concentrated is lender activity?
5. Which industries receive the most lending?
6. What is the 7(a) versus 504 program mix?
7. Which states have high lending relative to establishment count?
8. How does lending compare descriptively with unemployment and business formation context?
9. Is the data fresh and validated?

## Technical Acceptance

The project is technically complete when:

1. Python ingestion scripts extract SBA, Census BDS, and BLS LAUS data.
2. Raw snapshots are written locally and to S3 in final mode.
3. Ingestion manifests are created for every source extract.
4. Raw validation checks run before warehouse loading.
5. DuckDB local mode runs end to end.
6. Snowflake final mode creates raw, staging, mart, BI, and audit tables.
7. dbt builds staging, intermediate, mart, BI, and audit models.
8. dbt tests pass for required models.
9. pytest passes for extraction, validation, manifest, hashing, path, and loader utilities.
10. Prefect orchestrates the pipeline with quality gates.
11. Power BI connects to BI or mart tables, not raw source files.
12. Dashboard screenshots are committed under `powerbi/screenshots/`.
13. README explains how to run the local pipeline.
14. README includes architecture, dashboard, and testing evidence.
15. Predictive machine learning is not included in the MVP.

## Data Quality Acceptance

The project is quality-complete when:

1. Required source files and API responses are validated.
2. Raw files have checksums, row counts, schema hashes, and manifests.
3. Source freshness checks are recorded.
4. Staging models preserve source lineage.
5. Mart tables have unique documented grains.
6. KPI totals reconcile back to facts where applicable.
7. Lender, industry, and program shares stay within valid ranges.
8. Cross-source tables use compatible grains.
9. Latest successful source snapshots are used for reporting marts.
10. BI tables do not expose borrower-level raw identifiers.
11. Pipeline health is visible in Power BI.

## Recruiter Acceptance

The project is recruiter-ready when a reviewer can see clear evidence of:

| Signal | Evidence |
|---|---|
| Business problem framing | README and project spec |
| Public data ingestion | Python extractors and source inventory |
| AWS usage | S3 raw landing structure |
| SQL modeling | dbt staging, marts, BI models |
| Warehouse design | DuckDB local and Snowflake final schemas |
| Data quality | dbt tests, pytest, validation outputs |
| Orchestration | Prefect flow and run summary |
| BI delivery | Power BI screenshots |
| Documentation | KPI dictionary, data model, testing plan |
| Scope discipline | No ML and no infrastructure sprawl |

---

# Recommended Build Order

Use this order during implementation:

```text
1. T00-T02: Foundation, dependencies, config, seeds
2. T03-T07: Ingestion utilities, extractors, validation
3. T08: DuckDB raw loading
4. T09-T14: dbt setup, staging, facts, marts, BI/audit models
5. T15-T16: dbt tests and pytest suite
6. T17-T18: Prefect local flow and Power BI exports
7. T23-T24: Local Power BI prototype
8. T19-T22: S3/Snowflake cloud promotion
9. T25-T27: README, documentation, recruiter evidence pack
```
