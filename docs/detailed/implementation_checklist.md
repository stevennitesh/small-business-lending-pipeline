# Implementation Checklist

## Purpose

This checklist converts the approved project specification into a practical build plan. The project should be built local-first, then promoted to S3/Snowflake, then polished for recruiter review.

---

## Build Phase 0: Repository Skeleton

- [ ] Create GitHub repository: `small-business-lending-pipeline`.
- [ ] Add `README.md`.
- [ ] Add `.gitignore`.
- [ ] Add `.env.example`.
- [ ] Add `requirements.txt`.
- [ ] Add `Dockerfile`.
- [ ] Add `docker-compose.yml`.
- [ ] Add `Makefile`.
- [ ] Add `docs/` directory and copy final spec documents.
- [ ] Add `config/` directory.
- [ ] Add `pipelines/` package structure.
- [ ] Add `dbt/` project skeleton.
- [ ] Add `tests/` directory.
- [ ] Add `powerbi/screenshots/` directory.

---

## Build Phase 1: Configuration and Reference Data

- [ ] Create `config/sources.yml`.
- [ ] Create `config/sba_resources.yml`.
- [ ] Create `config/census_bds_variables.yml`.
- [ ] Create `config/bls_laus_state_series.yml`.
- [ ] Create `config/freshness_rules.yml`.
- [ ] Create `config/raw_validation_expectations.yml`.
- [ ] Create dbt seed `ref_state.csv`.
- [ ] Create dbt seed `ref_naics.csv`.
- [ ] Create dbt seed `ref_bls_laus_state_series.csv`.
- [ ] Add config loading utility.
- [ ] Add tests for config loading.

---

## Build Phase 2: Local Extraction

- [ ] Implement `pipelines/extract/sba_extract.py`.
- [ ] Implement `pipelines/extract/census_bds_extract.py`.
- [ ] Implement `pipelines/extract/bls_laus_extract.py`.
- [ ] Write raw SBA CSV files to `data/raw/sba/`.
- [ ] Write raw Census JSON to `data/raw/census/`.
- [ ] Write raw BLS JSON to `data/raw/bls/`.
- [ ] Generate row counts.
- [ ] Generate file checksums.
- [ ] Generate schema hashes where practical.
- [ ] Write ingestion manifests.
- [ ] Add sample fixtures for pytest.

---

## Build Phase 3: Raw Validation and pytest

- [ ] Implement common raw file checks.
- [ ] Implement SBA-specific raw checks.
- [ ] Implement Census BDS raw checks.
- [ ] Implement BLS LAUS raw checks.
- [ ] Write validation result JSON files.
- [ ] Add checksum tests.
- [ ] Add manifest required-field tests.
- [ ] Add path-generation tests.
- [ ] Add source-response validation tests.
- [ ] Add BLS period parsing tests.
- [ ] Run `pytest` successfully.

---

## Build Phase 4: DuckDB Local Warehouse

- [ ] Create DuckDB database path: `data/warehouse/small_business_lending.duckdb`.
- [ ] Create logical schemas: `raw`, `staging`, `intermediate`, `marts`, `bi`, `audit`.
- [ ] Load SBA raw files into DuckDB raw tables.
- [ ] Load Census raw response into normalized DuckDB raw table.
- [ ] Load BLS raw response into normalized DuckDB raw table.
- [ ] Load manifest and validation results into audit/raw tables.
- [ ] Verify row counts against manifests.

---

## Build Phase 5: dbt Staging Models

- [ ] Configure dbt DuckDB profile.
- [ ] Add dbt source definitions.
- [ ] Add dbt seeds.
- [ ] Build `stg_sba_7a_loans`.
- [ ] Build `stg_sba_504_loans`.
- [ ] Build `stg_sba_loans` normalized union.
- [ ] Build `stg_census_bds_state_year`.
- [ ] Build `stg_bls_laus_state_month`.
- [ ] Build `stg_ingestion_manifest`.
- [ ] Build `stg_validation_result`.
- [ ] Add not-null, uniqueness, accepted-values, and relationship tests.

---

## Build Phase 6: dbt Intermediate, Mart, and BI Models

- [ ] Build `int_sba_loans_enriched`.
- [ ] Build monthly and annual lending base models.
- [ ] Build lender ranking/share models.
- [ ] Build industry/program mix models.
- [ ] Build BLS monthly and annual models.
- [ ] Build Census BDS annual model.
- [ ] Build regional business-health annual mart.
- [ ] Build pipeline health marts.
- [ ] Build BI tables:
  - [ ] `bi_executive_overview`
  - [ ] `bi_state_lending_trends`
  - [ ] `bi_lender_concentration`
  - [ ] `bi_industry_mix`
  - [ ] `bi_program_mix`
  - [ ] `bi_regional_business_health`
  - [ ] `bi_pipeline_health`
- [ ] Run `dbt build --target dev_duckdb`.

---

## Build Phase 7: dbt Data Quality Tests

- [ ] Add composite-grain tests for all marts.
- [ ] Add non-negative amount/count tests.
- [ ] Add share/rate range tests.
- [ ] Add fact-to-mart reconciliation tests.
- [ ] Add annual-to-monthly reconciliation tests where applicable.
- [ ] Add latest-successful-snapshot enforcement test.
- [ ] Add BI exposure test to prevent raw borrower-level fields.
- [ ] Run all critical dbt tests successfully.

---

## Build Phase 8: Prefect Local Orchestration

- [ ] Implement `pipelines/flows/lending_pipeline_flow.py`.
- [ ] Add flow parameters: `run_mode`, `dbt_target`, `start_year`, `end_year`.
- [ ] Add extraction tasks.
- [ ] Add validation tasks.
- [ ] Add DuckDB load task.
- [ ] Add dbt build task.
- [ ] Add dbt artifact collection task.
- [ ] Add BI table validation task.
- [ ] Add local Power BI export task.
- [ ] Add run summary output.
- [ ] Run `make run-local` successfully.

---

## Build Phase 9: Power BI Prototype

- [ ] Export BI tables from DuckDB to `data/exports/powerbi/`.
- [ ] Create Power BI file: `powerbi/lending_dashboard.pbix`.
- [ ] Build Executive Overview page.
- [ ] Build State Lending Trends page.
- [ ] Build Lender Concentration page.
- [ ] Build Industry and Program Mix page.
- [ ] Build Regional Business Health page.
- [ ] Build Data Quality and Pipeline Health page.
- [ ] Add caveats/methodology notes.
- [ ] Save screenshots under `powerbi/screenshots/`.

---

## Build Phase 10: S3 and Snowflake Promotion

- [ ] Create S3 bucket or use existing project bucket.
- [ ] Add limited S3 IAM permissions.
- [ ] Implement `s3_loader.py`.
- [ ] Upload raw files, manifests, and validation outputs to S3.
- [ ] Create Snowflake database and schemas.
- [ ] Implement Snowflake raw loader.
- [ ] Configure dbt Snowflake profile.
- [ ] Run `dbt build --target prod_snowflake`.
- [ ] Connect Power BI to Snowflake BI schema.
- [ ] Capture S3/Snowflake evidence screenshots without secrets.

---

## Build Phase 11: Recruiter Polish

- [ ] Update `README.md` with project overview and screenshots.
- [ ] Add architecture diagram.
- [ ] Add dashboard screenshots.
- [ ] Add dbt test output screenshot.
- [ ] Add Prefect flow screenshot.
- [ ] Add S3 raw prefix screenshot if final mode is complete.
- [ ] Add Snowflake schema screenshot if final mode is complete.
- [ ] Add clear limitations section.
- [ ] Add explicit no-ML scope statement.
- [ ] Confirm the project can be understood in under five minutes.

---

## MVP Completion Definition

The MVP is complete when:

- [ ] `make run-local` completes successfully.
- [ ] Raw files are ingested from SBA, Census BDS, and BLS LAUS.
- [ ] Raw files have manifests, checksums, row counts, and validation outputs.
- [ ] DuckDB local warehouse builds successfully.
- [ ] dbt staging, mart, BI, and audit models build successfully.
- [ ] Critical dbt tests pass.
- [ ] pytest passes.
- [ ] Power BI dashboard is built from modeled BI/mart tables.
- [ ] The pipeline health page shows freshness and validation status.
- [ ] README includes architecture, setup, screenshots, and limitations.

---

## Non-Negotiable Scope Rules

- [ ] No predictive machine learning in MVP.
- [ ] No borrower-level credit scoring.
- [ ] No raw-table Power BI dashboarding.
- [ ] No unsupported causal claims.
- [ ] No unnecessary AWS services before core pipeline works.
- [ ] No exact live row-count tests for changing public datasets.
- [ ] No credentials committed to Git.
