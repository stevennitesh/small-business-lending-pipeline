# Plan: Add Extra SBA KPI Fields From Existing Data

## Goal

Add a focused set of additional lending KPIs using fields already present in the
SBA raw, staging, and fact data. Keep the pipeline architecture unchanged:

- local route builds DuckDB marts and exports Power BI CSVs;
- cloud route builds equivalent Snowflake marts and BI tables;
- dbt owns KPI calculations and documentation;
- Power BI owns relationships, slicers, display formatting, and report layout.

The intent is to deepen the dashboard with loan performance, charge-off,
guarantee, term, pricing, and jobs-supported metrics without adding new public
sources.

## Non-Goals

- Do not add CFPB, CRA, Federal Reserve survey, credit bureau, or private lender
  sources.
- Do not add approval rate, denial rate, application volume, credit score, or
  unmet-demand KPIs because those are not supported by the current data.
- Do not build borrower credit scoring, predictive default modeling, or causal
  claims.
- Do not move core calculations into Power BI measures.
- Do not edit `powerbi/lending_dashboard.pbix` in the implementation slices
  unless the user explicitly asks for report-page changes.
- Do not split dbt marts into separate local and cloud SQL trees.

## Constraints

- Use only existing SBA fields already present in `stg_sba_loans` and mostly
  exposed through `fact_sba_loans`.
- Keep rates and shares as decimal values; Power BI formats them as percentages.
- Keep route-specific differences in orchestration, storage, and warehouse
  targets, not in KPI definitions.
- Local and cloud BI surfaces must expose the same logical table and column
  contracts.
- Generated CSVs under `data/exports/powerbi/*.csv` remain rebuildable local
  artifacts and should not be committed.
- Preserve the user-owned `powerbi/lending_dashboard.pbix` modification unless
  the user explicitly asks to update it.

## Baseline Evidence

The live local refresh `live-dashboard-refresh-20260519` shows these candidate
fields are already available:

| Field | Coverage | Notes |
| --- | ---: | --- |
| `loan_status` | 2,174,251 / 2,174,502 rows | Supports performance/status grouping. |
| `gross_chargeoff_amount` | 2,174,502 / 2,174,502 rows | Non-zero on 251,188 rows. |
| `chargeoff_date` | 251,499 rows | Useful for status validation, not primary grain yet. |
| `paid_in_full_date` | 1,283,167 rows | Useful for status validation, not primary grain yet. |
| `term_months` | 2,174,502 rows | Non-zero on 2,173,142 rows. |
| `jobs_supported` | 2,174,500 rows | Non-zero on 1,578,858 rows. |
| `sba_guaranteed_approval_amount` | 1,947,098 rows | Mostly 7(a); 504 has different financing structure. |
| `initial_interest_rate` | 956,358 rows | 7(a) only, 2008 to 2026. |
| `fixed_or_variable_interest_indicator` | 956,359 rows | Same availability shape as interest rate. |
| `third_party_dollars` | 120,762 rows | 504-specific. |
| `business_type` | 2,169,217 rows | Usable segmentation. |
| `business_age` | 2,171,889 rows | Usable segmentation. |
| `collateral_indicator` | 2,154,594 rows | Optional segmentation. |
| `sold_secondary_market_indicator` | 483,018 rows | Partial coverage. |
| `revolver_status` | 1,947,098 rows | Mostly 7(a). |

Current mart checks already pass:

```bash
scripts/run_dbt_local.sh test --select path:models/marts
```

Recent result: 136 passed, 0 failed.

## Target KPI Families

### Loan Performance And Charge-Off

Supported by existing fields:

- `loan_status`
- `gross_chargeoff_amount`
- `chargeoff_date`
- `paid_in_full_date`

Candidate outputs:

- loan count by normalized status group;
- approved dollars by normalized status group;
- charged-off loan count;
- gross charge-off dollars;
- charge-off amount rate: charge-off dollars divided by approved dollars;
- charged-off loan count rate: charged-off loans divided by loan count.

Important caveat: this is public historical status/performance data, not a live
servicing balance or delinquency ledger.

### Guarantee And Exposure

Supported by existing fields:

- `sba_guaranteed_approval_amount`
- `gross_approval_amount`
- `third_party_dollars`
- `loan_program_key`

Candidate outputs:

- SBA guaranteed approved dollars;
- guarantee percentage where available;
- 7(a) guarantee metrics;
- 504 third-party dollar metrics where available.

Important caveat: do not compare 7(a) guarantee percentage and 504 third-party
financing as the same KPI. They are program-specific financing concepts.

### Terms And Pricing

Supported by existing fields:

- `term_months`
- `initial_interest_rate`
- `fixed_or_variable_interest_indicator`
- `loan_program_key`

Candidate outputs:

- average term months;
- average initial interest rate where available;
- interest-rate coverage count;
- fixed-rate and variable-rate loan counts or shares;
- 7(a)-only rate metrics with clear availability labels.

Important caveat: `initial_interest_rate` is only available for 7(a) rows from
2008 onward in the current data.

### Jobs And Economic Impact

Supported by existing fields:

- `jobs_supported`
- `gross_approval_amount`
- `loan_count`

Candidate outputs:

- total jobs supported;
- jobs supported per loan;
- jobs supported per `$1M` approved;
- approved dollars per job supported.

Important caveat: jobs-supported values are source-reported and should be
descriptive, not causal.

### Segmentation Enhancements

Supported by existing fields:

- `business_type`
- `business_age`
- `processing_method`
- `subprogram`
- `collateral_indicator`
- `revolver_status`
- `sold_secondary_market_indicator`

Candidate outputs:

- business type mix;
- business age mix;
- processing method and subprogram mix;
- collateral / revolver / secondary market availability metrics.

Recommendation: treat these as a second implementation wave after performance,
terms, guarantee, and jobs KPIs are stable.

## Local And Cloud Handoff

### Source Configuration

Local path:

```text
config/*.yml -> ProjectConfig -> local Prefect run
```

Cloud path:

```text
config/*.yml -> ProjectConfig -> cloud Prefect run
```

Planned change:

- No new source config files are needed.
- Add a small dbt seed for status grouping if normalization needs an explicit
  mapping, for example `dbt/seeds/ref_loan_status_group.csv`.
- Seed data is route-neutral: DuckDB loads it locally, Snowflake loads it in
  cloud through dbt.

### Extraction

Local path:

```text
SBA public source -> local raw artifacts -> local manifests
```

Cloud path:

```text
SBA public source -> S3 raw artifacts -> S3 manifests
```

Planned change:

- No extractor changes should be required because the needed fields already land
  in raw/staging.
- Add extractor tests only if implementation discovers a required source column
  is not preserved consistently across 7(a) and 504 raw resources.

### Raw Validation

Local path:

```text
local manifests/raw artifacts -> raw validation JSON
```

Cloud path:

```text
S3 manifests/raw artifacts -> validation results, with cloud artifact URI
```

Planned change:

- Do not add KPI calculations to raw validation.
- Keep raw validation focused on presence/readability/source-shape checks.
- Optionally add warning-level validation only if a required source field for the
  approved KPI set disappears from a current SBA resource.

### Raw Load

Local path:

```text
local raw files -> DuckDB raw tables
```

Cloud path:

```text
S3 raw files -> Snowflake raw tables
```

Planned change:

- No raw-load behavior change should be required.
- Preserve all existing raw SBA columns and row metadata.
- If a candidate KPI field is missing after load, fix shared raw-load parsing in
  `pipelines/load/raw_load_common.py` so DuckDB and Snowflake stay aligned.

### dbt Staging And Facts

Local path:

```text
DuckDB raw -> dbt target dev_duckdb -> staging/fact tables
```

Cloud path:

```text
Snowflake raw -> dbt target prod_snowflake -> staging/fact tables
```

Planned change:

- Keep `stg_sba_loans` as the typed source contract.
- Extend `fact_sba_loans` only where needed so marts do not reach back into
  staging for KPI fields.
- Likely fact additions:
  - `loan_status`
  - `paid_in_full_date`
  - `chargeoff_date`
  - `fixed_or_variable_interest_indicator`
  - `third_party_dollars`
  - `business_type`
  - `business_age`
  - `revolver_status`
  - `collateral_indicator`
  - `sold_secondary_market_indicator`
- Preserve existing lineage fields:
  - `pipeline_run_id`
  - `storage_backend`
  - `raw_uri`
  - `raw_file_path`
  - `sha256_checksum`

### dbt Marts

Local path:

```text
DuckDB facts/dimensions -> dbt marts
```

Cloud path:

```text
Snowflake facts/dimensions -> dbt marts
```

Planned change:

- Add route-neutral mart models that consume only facts, dimensions, and seeds.
- Do not read raw or staging models from KPI marts after fact fields are exposed.
- Candidate mart models:
  - `mart_lending_performance_state_period`
  - `mart_lending_status_mix_state_period`
  - `mart_lending_terms_pricing_state_period`
  - `mart_lending_jobs_impact_state_period`
  - optional later: `mart_lending_business_segment_state_period`
- Add dbt tests for:
  - unique grains;
  - non-negative counts and amounts;
  - share/rate ranges between 0 and 1 where applicable;
  - reconciliation to `fact_sba_loans`;
  - status group mapping coverage.

### BI Tables And Power BI Export

Local path:

```text
DuckDB BI tables -> data/exports/powerbi/*.csv -> Power BI local CSV queries
```

Cloud path:

```text
Snowflake BI tables -> Power BI Snowflake connection
```

Planned change:

- Add BI-facing tables that hide internal mart naming:
  - `bi_loan_performance`
  - `bi_loan_status_mix`
  - `bi_terms_pricing`
  - `bi_jobs_impact`
  - optional later: `bi_business_segment_mix`
  - optional filter: `bi_loan_status_filter`
- Update `BI_EXPORT_TABLES`, required columns, and prohibited-field checks.
- Ensure the exact local export behavior still removes stale CSVs and preserves
  non-CSV files.
- Update `powerbi/lending_dashboard_model.json` and
  `powerbi/power_query/local_csv_queries.pq` so local CSV and Snowflake table
  contracts remain equivalent.
- Do not edit the PBIX until the user is ready for report-page work.

### Orchestration

Local path:

```text
make run-local -> fixture or live local flow -> DuckDB/dbt -> Power BI CSVs
```

Cloud path:

```text
make run-cloud -> S3/Snowflake/dbt -> Snowflake BI tables
```

Planned change:

- Local flow should export the new BI tables automatically through the shared
  Power BI export contract.
- Cloud flow should build the same BI table names in Snowflake through dbt.
- Run summaries should record the same logical BI table coverage, even though
  local outputs are CSV files and cloud outputs are Snowflake relations.

## Execution Mode

Execution mode: sequential.

These slices touch overlapping dbt contracts, BI exports, Power Query metadata,
and tests. Implement one issue at a time.

## GitHub Issues

- [#85 Add SBA status mapping and fact KPI field coverage](https://github.com/stevennitesh/small-business-lending-pipeline/issues/85)
- [#86 Add SBA loan performance and charge-off marts](https://github.com/stevennitesh/small-business-lending-pipeline/issues/86)
- [#87 Add SBA terms pricing guarantee and jobs marts](https://github.com/stevennitesh/small-business-lending-pipeline/issues/87)
- [#88 Expose extra SBA KPI BI tables and Power BI contract](https://github.com/stevennitesh/small-business-lending-pipeline/issues/88)
- [#89 Verify extra SBA KPI local and cloud orchestration paths](https://github.com/stevennitesh/small-business-lending-pipeline/issues/89)
- [#90 Document extra SBA KPI definitions and Power BI handoff](https://github.com/stevennitesh/small-business-lending-pipeline/issues/90)

## Acceptance Checks

- No new external source is added.
- Needed fields are exposed through `fact_sba_loans` or documented as already
  present there.
- Loan status normalization is explicit and tested.
- Added marts reconcile to `fact_sba_loans`.
- Added BI tables expose only dashboard-ready fields, not raw identifiers or
  borrower names.
- Local CSV exports and cloud Snowflake BI tables use the same logical table
  list.
- Power BI contract files know about the new BI tables, but PBIX remains
  untouched until a separate report task.
- Local and cloud paths use shared dbt models and differ only by target/profile,
  storage, and export/connection destination.

## Tasks

### Task 1: Add Status Group Mapping And Fact Field Coverage

- Outcome: extra KPI source fields are available from facts, and loan statuses
  are normalized through a route-neutral mapping.
- Builds on or must preserve:
  - existing `stg_sba_loans` typed contract;
  - existing `fact_sba_loans` grain and lineage fields;
  - local/cloud shared dbt target behavior.
- Existing logic to reuse or extend:
  - `fact_sba_loans.sql`;
  - dbt seed pattern used by existing reference tables;
  - marts schema tests.
- Public contract or state/data change:
  - Add selected source fields to `fact_sba_loans`.
  - Add `loan_status_group` via seed or deterministic dbt normalization.
  - Do not expose borrower name or source loan ID to BI tables.
- Depends on: none.
- Likely files/modules:
  - `dbt/models/marts/facts/fact_sba_loans.sql`
  - `dbt/models/marts/schema.yml`
  - `dbt/seeds/ref_loan_status_group.csv`
  - `dbt/seeds/schema.yml` if seed docs exist or are added
  - `tests/unit/test_dbt_marts_models.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py`
- Change boundary:
  - Do not add KPI marts yet.
  - Do not change existing lending totals, shares, or BI outputs.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py`
  - `make dbt-local`
- Review focus:
  - Status mapping is readable and conservative.
  - Unknown or unmapped statuses remain visible rather than silently dropped.
- Risk/rollback:
  - Medium-low. Roll back by removing added fact columns and status seed.
- Stop/ask if:
  - Status values cannot be grouped cleanly without a business decision.
- Status: pending

### Task 2: Add Loan Performance And Charge-Off Marts

- Outcome: dbt exposes loan performance metrics by state-year and status mix.
- Builds on or must preserve:
  - Task 1 `loan_status_group` and fact field coverage;
  - existing annual lending totals and known-lender semantics.
- Existing logic to reuse or extend:
  - `mart_lending_annual_state` state-year grain;
  - `safe_divide` macro;
  - existing mart reconciliation tests.
- Public contract or state/data change:
  - Add `mart_lending_performance_state_period`.
  - Add `mart_lending_status_mix_state_period`.
  - Metrics include charge-off amount, charged-off loan count, charge-off rate,
    and status-group share fields.
- Depends on: Task 1.
- Likely files/modules:
  - `dbt/models/marts/lending/mart_lending_performance_state_period.sql`
  - `dbt/models/marts/lending/mart_lending_status_mix_state_period.sql`
  - `dbt/models/marts/lending/schema.yml`
  - `dbt/tests/assert_mart_lending_performance_reconciles.sql`
  - `tests/unit/test_dbt_lending_marts.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_lending_marts.py`
- Change boundary:
  - Do not add interest-rate or jobs metrics in this task.
  - Do not classify canceled/not-funded loans as credit losses.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_lending_marts.py`
  - `scripts/run_dbt_local.sh test --select mart_lending_performance_state_period mart_lending_status_mix_state_period`
- Review focus:
  - Charge-off rates divide by approved dollars or loan count exactly as
    documented.
  - Status mix shares reconcile within state-year.
- Risk/rollback:
  - Medium. Status grouping may need label refinements after review.
- Stop/ask if:
  - A source status appears ambiguous enough to change metric meaning.
- Status: pending

### Task 3: Add Guarantee, Terms, Pricing, And Jobs Marts

- Outcome: dbt exposes extra descriptive lending metrics that are not credit-risk
  claims.
- Builds on or must preserve:
  - Task 1 fact fields;
  - Task 2 performance marts;
  - existing annual lending grain.
- Existing logic to reuse or extend:
  - `mart_lending_annual_state`;
  - `safe_divide`;
  - existing non-negative and range tests.
- Public contract or state/data change:
  - Add `mart_lending_terms_pricing_state_period`.
  - Add `mart_lending_jobs_impact_state_period`.
  - Metrics include average term, average interest rate where available, rate
    coverage count, guarantee amount, guarantee percentage, total jobs
    supported, jobs per loan, jobs per `$1M`, and approved dollars per job.
- Depends on: Task 1.
- Likely files/modules:
  - `dbt/models/marts/lending/mart_lending_terms_pricing_state_period.sql`
  - `dbt/models/marts/lending/mart_lending_jobs_impact_state_period.sql`
  - `dbt/models/marts/lending/schema.yml`
  - `tests/unit/test_dbt_lending_marts.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_lending_marts.py`
- Change boundary:
  - Interest-rate metrics must include availability counts and should not imply
    full SBA coverage.
  - Keep 7(a) guarantee metrics separate from 504 third-party financing.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_lending_marts.py`
  - `scripts/run_dbt_local.sh test --select mart_lending_terms_pricing_state_period mart_lending_jobs_impact_state_period`
- Review focus:
  - Null handling and denominators are explicit.
  - Program-specific metrics are labeled safely.
- Risk/rollback:
  - Medium. Pricing and guarantee fields have uneven coverage.
- Stop/ask if:
  - The desired BI story requires comparing 7(a) and 504 financing concepts as
    one metric.
- Status: pending

### Task 4: Add BI Tables And Export Contract

- Outcome: Power BI can consume the new KPI families through modeled BI tables
  in both local and cloud routes.
- Builds on or must preserve:
  - Tasks 2 and 3 mart outputs;
  - exact local export behavior from `scripts/export_powerbi_tables.py`;
  - existing Power BI filter tables.
- Existing logic to reuse or extend:
  - current `dbt/models/bi/*.sql` patterns;
  - `BI_EXPORT_TABLES`;
  - `powerbi/lending_dashboard_model.json`;
  - `powerbi/power_query/local_csv_queries.pq`.
- Public contract or state/data change:
  - Add BI-facing tables for approved extra KPI marts.
  - Add required-column checks for every new BI table.
  - Keep local CSV names and Snowflake logical table names equivalent.
- Depends on: Tasks 2 and 3.
- Likely files/modules:
  - `dbt/models/bi/bi_loan_performance.sql`
  - `dbt/models/bi/bi_loan_status_mix.sql`
  - `dbt/models/bi/bi_terms_pricing.sql`
  - `dbt/models/bi/bi_jobs_impact.sql`
  - `dbt/models/bi/schema.yml`
  - `scripts/export_powerbi_tables.py`
  - `scripts/validate_powerbi_model.py`
  - `powerbi/lending_dashboard_model.json`
  - `powerbi/power_query/local_csv_queries.pq`
  - `tests/unit/test_powerbi_export.py`
  - `tests/unit/test_powerbi_model_contract.py`
  - `tests/unit/test_dbt_bi_pipeline_models.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_export.py tests/unit/test_powerbi_model_contract.py tests/unit/test_dbt_bi_pipeline_models.py`
- Change boundary:
  - Do not edit `powerbi/lending_dashboard.pbix`.
  - Do not add raw borrower identifiers to export tables.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_export.py tests/unit/test_powerbi_model_contract.py tests/unit/test_dbt_bi_pipeline_models.py`
  - `make powerbi-model-check`
- Review focus:
  - Model JSON, Power Query, export script, and dbt BI schema cannot drift.
  - New BI tables remain report-ready and route-neutral.
- Risk/rollback:
  - Medium. The source-controlled Power BI contract changes even before PBIX
    visuals are updated.
- Stop/ask if:
  - The new table count or Power Query changes should wait for PBIX report-page
    work.
- Status: pending

### Task 5: Orchestration And End-To-End Route Verification

- Outcome: local and cloud routes both build the same new logical BI contract.
- Builds on or must preserve:
  - Task 4 BI/export contract;
  - local `make run-local` path;
  - cloud `make run-cloud` path.
- Existing logic to reuse or extend:
  - `pipelines/flows/lending_pipeline_flow.py`;
  - local BI export task;
  - cloud dbt build behavior.
- Public contract or state/data change:
  - Local flow exports the new CSVs under `data/exports/powerbi`.
  - Cloud flow builds the new Snowflake BI tables through dbt.
  - Run summary records new local export paths where applicable.
- Depends on: Task 4.
- Likely files/modules:
  - `pipelines/flows/lending_pipeline_flow.py`
  - `tests/unit/test_prefect_local_flow.py`
  - `README.md`
  - `powerbi/README.md`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py`
- Change boundary:
  - Do not require live Snowflake credentials for default unit tests.
  - Do not run heavy live local refresh unless explicitly requested after code
    changes pass.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py`
  - `make dbt-local`
  - optional local fixture: `make run-local`
  - optional live local: `scripts/run_local_pipeline.sh --extract-mode live --pipeline-run-id <run-id>`
  - optional cloud fixture when credentials are available:
    `scripts/run_cloud_pipeline.sh --extract-mode fixture --pipeline-run-id <run-id>`
- Review focus:
  - Local and cloud route differences are destination differences, not KPI logic
    differences.
- Risk/rollback:
  - Medium. Full route checks touch generated local data and cloud state.
- Stop/ask if:
  - Live route verification would require a large refresh or cloud credentials
    are unavailable.
- Status: pending

### Task 6: Documentation And Report-Page Handoff

- Outcome: docs explain the extra KPIs, their coverage, and what still requires
  manual PBIX work.
- Builds on or must preserve:
  - completed BI contract;
  - existing MVP caveats;
  - no-new-source decision.
- Existing logic to reuse or extend:
  - `README.md`;
  - `powerbi/README.md`;
  - detailed dashboard/project docs if kept current.
- Public contract or state/data change:
  - Document added KPI definitions and limitations.
  - Document that `initial_interest_rate` is 7(a), 2008+ coverage.
  - Document that jobs-supported metrics are descriptive.
  - Document PBIX pages/visuals still need manual update unless separately
    implemented.
- Depends on: Tasks 2 through 5.
- Likely files/modules:
  - `README.md`
  - `powerbi/README.md`
  - `docs/detailed/dashboard_spec.md` if the detailed spec is still maintained
- First command/check:
  - `git diff --check`
- Change boundary:
  - Do not use docs to claim PBIX visuals exist before they are created.
- Verification command:
  - `git diff --check`
  - `make powerbi-model-check`
- Review focus:
  - Recruiter-facing wording is accurate and does not overclaim risk or approval
    metrics.
- Risk/rollback:
  - Low. Docs can be revised independently.
- Stop/ask if:
  - The dashboard page sequence or visual design needs user approval.
- Status: pending

## Final Verification

Run focused unit/static checks:

```bash
.venv/bin/python -m pytest tests/unit/test_dbt_marts_models.py tests/unit/test_dbt_lending_marts.py tests/unit/test_dbt_bi_pipeline_models.py
.venv/bin/python -m pytest tests/unit/test_powerbi_export.py tests/unit/test_powerbi_model_contract.py tests/unit/test_prefect_local_flow.py
make powerbi-model-check
make dbt-local
git diff --check
```

Run dbt mart tests when the local warehouse is current:

```bash
scripts/run_dbt_local.sh test --select path:models/marts path:models/bi
```

Regenerate local BI CSVs after implementation:

```bash
make run-local
.venv/bin/python scripts/export_powerbi_tables.py
```

If live dashboard-sized data is required:

```bash
scripts/run_local_pipeline.sh --extract-mode live --pipeline-run-id live-extra-kpi-refresh-YYYYMMDD
```

Optional cloud verification when credentials are configured:

```bash
scripts/run_cloud_pipeline.sh --extract-mode fixture --pipeline-run-id cloud-extra-kpi-fixture-YYYYMMDD
```

## Open Questions

- Should the first report addition be one combined "Loan Performance" page or
  separate pages for performance, terms/pricing, and jobs impact?
- Should 2026 remain visible by default for extra KPIs, or should report visuals
  default to completed years only?
- Should status groups use short labels for report visuals, for example
  `Current`, `Paid in full`, `Charged off`, `Canceled or not funded`, and
  `Other`, while preserving raw status in lower-level marts?
- Should business type and business age segmentation be included in the first
  implementation wave or deferred until the performance/terms/jobs tables are
  stable?
