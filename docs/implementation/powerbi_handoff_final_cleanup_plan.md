# Plan: Finish Power BI Handoff Cleanup

## Goal

Close the remaining small gaps in the dbt BI to Power BI handoff so the source-controlled report contract matches the MVP design:

- dbt BI models own KPI values, filter tables, known-lender semantics, and data-quality fields;
- Power BI owns relationships, slicers, formatting, and display-only measures;
- local Power BI consumes stable CSV exports from the same BI contract;
- cloud Power BI consumes Snowflake BI-schema tables from the same logical contract;
- contract checks catch stale table references before the report is rebuilt.

## Non-goals

- Do not edit `powerbi/lending_dashboard.pbix`.
- Do not add dashboard pages or visual design changes.
- Do not move KPI calculations into Power BI.
- Do not change raw, staging, mart, or BI business logic except for contract metadata and export-path wiring.
- Do not add Power BI Service refresh automation or DirectQuery behavior in this slice.

## Constraints

- Preserve the user-owned local `powerbi/lending_dashboard.pbix` modification.
- Keep Power BI source tables limited to dbt-produced `bi_*` tables.
- Keep local CSV exports under a stable latest-output folder for Power BI Desktop.
- Keep Snowflake report sources in the BI schema, not raw, staging, or internal marts schemas.
- Keep rates, shares, and percentage-style values as decimals; Power BI handles display formatting.

## Execution Mode

Execution mode: sequential.

These cleanups touch overlapping contract files and tests, so implement them one issue/slice at a time in the main workspace unless the user asks for parallel work.

## Acceptance Checks

- Power BI model measures reference declared BI-facing table names only.
- The Power BI model validator fails when a measure references an undeclared table.
- Local Power BI export-path configuration is either wired into the local flow and documented, or removed as dead configuration.
- Power Query local CSV usage is documented clearly enough for Power BI Desktop on Windows.
- BI schema wording no longer labels fields as deprecated compatibility fields when they remain part of the current Power BI contract.
- Existing tests still prove BI model JSON, Power Query, export contract, dbt BI models, and local flow table lists stay aligned.
- Existing PBIX remains untouched.

## GitHub Issues

- [#79 Fix Power BI display measure table references](https://github.com/stevennitesh/small-business-lending-pipeline/issues/79)
- [#80 Validate Power BI measure expression table references](https://github.com/stevennitesh/small-business-lending-pipeline/issues/80)
- [#81 Make local Power BI export path configuration deliberate](https://github.com/stevennitesh/small-business-lending-pipeline/issues/81)
- [#82 Clarify local Power Query CSV path setup](https://github.com/stevennitesh/small-business-lending-pipeline/issues/82)
- [#83 Clean up BI schema wording for current Power BI fields](https://github.com/stevennitesh/small-business-lending-pipeline/issues/83)

## Baseline

- Working tree: clean except user-owned `powerbi/lending_dashboard.pbix`.
- Current model contract:
  - `powerbi/lending_dashboard_model.json` uses BI-facing tables and relationships.
  - `powerbi/lending_dashboard_model.json` still has display measures referencing `dim_year` and `dim_state`.
- Current validation:
  - `scripts/validate_powerbi_model.py` checks table sources, required columns, relationship direction, and measure categories.
  - It does not currently validate table names inside measure expressions.
- Current local export path:
  - `.env.example` declares `POWERBI_EXPORT_DIR=data/exports/powerbi`.
  - `pipelines/flows/lending_pipeline_flow.py` hardcodes `data_root / "exports" / "powerbi"`.
  - `powerbi/power_query/local_csv_queries.pq` hardcodes `data/exports/powerbi`.
- Baseline checks:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_model_contract.py tests/unit/test_powerbi_export.py tests/unit/test_dbt_bi_pipeline_models.py`
  - `make powerbi-model-check`
  - `make dbt-local`

## Tasks

### Task 1: Fix stale display-measure table references

- Outcome: Source-controlled Power BI display measures point at the current BI-facing filter tables.
- Builds on or must preserve: existing display-only measure policy and BI-facing filter table names.
- Existing logic to reuse or extend:
  - `powerbi/lending_dashboard_model.json` measures.
  - `tests/unit/test_powerbi_model_contract.py` display-measure checks.
- Public contract or state/data change:
  - Change stale `dim_year` and `dim_state` references to the current declared filter table names.
- Depends on: none.
- Likely files/modules:
  - `powerbi/lending_dashboard_model.json`
  - `tests/unit/test_powerbi_model_contract.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_model_contract.py`
- Change boundary:
  - Do not edit the PBIX.
  - Do not add new measures or KPI formulas.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_model_contract.py`
  - `make powerbi-model-check`
- Review focus:
  - Measures remain display-only.
  - Measure expressions use declared BI-facing table names.
- Risk/rollback:
  - Low. Roll back by restoring the previous JSON expressions.
- Status: completed

### Task 2: Add measure-expression drift validation

- Outcome: Contract validation catches undeclared table references in Power BI measure expressions.
- Builds on or must preserve: Task 1 corrected table names and the existing validator's category checks.
- Existing logic to reuse or extend:
  - `scripts/validate_powerbi_model.py` measure validation.
  - `tests/unit/test_powerbi_model_contract.py`.
- Public contract or state/data change:
  - Display, formatting, and dynamic-title measures may reference only declared source tables or dimensions.
  - Invalid measure table references fail in source-controlled validation before a PBIX rebuild.
- Depends on: Task 1.
- Likely files/modules:
  - `scripts/validate_powerbi_model.py`
  - `tests/unit/test_powerbi_model_contract.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_model_contract.py`
- Change boundary:
  - Keep parsing lightweight; this is a contract guard, not a full DAX parser.
  - Do not reject scalar functions such as `COALESCE` or `SELECTEDVALUE`.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_model_contract.py`
  - `make powerbi-model-check`
- Review focus:
  - The test would fail for the current stale `dim_year` / `dim_state` issue.
  - The guard remains understandable and maintainable.
- Risk/rollback:
  - Low. Roll back by removing the new validator branch and focused tests.
- Status: completed

### Task 3: Decide and clean up local export-path configuration

- Outcome: The local Power BI export path has one deliberate configuration story.
- Builds on or must preserve: stable latest local CSV exports under `data/exports/powerbi`.
- Existing logic to reuse or extend:
  - `LocalRunContext.run_export_dir`.
  - `scripts/export_powerbi_tables.py` default export directory.
  - `.env.example` `POWERBI_EXPORT_DIR`.
  - `tests/unit/test_prefect_local_flow.py`.
- Public contract or state/data change:
  - Preferred MVP path: wire `POWERBI_EXPORT_DIR` into the local flow with `data/exports/powerbi` as the default.
  - Power Query can still assume the default path unless the user deliberately edits the query parameter/path.
- Depends on: none.
- Likely files/modules:
  - `pipelines/flows/lending_pipeline_flow.py`
  - `.env.example`
  - `tests/unit/test_prefect_local_flow.py`
  - possibly `powerbi/README.md`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py`
- Change boundary:
  - Do not make exports run-specific again.
  - Do not require Power BI Desktop or Windows-only checks.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py tests/unit/test_powerbi_export.py`
- Review focus:
  - There is no dead or misleading export-path config.
  - The local route still writes to the path Power Query expects by default.
- Risk/rollback:
  - Low to medium. If configurable paths complicate the desktop workflow, keep the fixed default and remove the unused env var instead.
- Status: completed

### Task 4: Clarify Power Query local path setup

- Outcome: The Power BI local CSV setup is easier to reproduce from Windows Power BI Desktop.
- Builds on or must preserve: Task 3 export-path decision.
- Existing logic to reuse or extend:
  - `powerbi/power_query/local_csv_queries.pq`
  - `powerbi/README.md`
  - `tests/unit/test_powerbi_model_contract.py` Power Query source-list test.
- Public contract or state/data change:
  - The local query remains aligned to `BI_EXPORT_TABLES`.
  - README explains that Power BI Desktop may need the Windows absolute repo path, or the query should expose an `ExportRoot` value the user can edit.
- Depends on: Task 3.
- Likely files/modules:
  - `powerbi/power_query/local_csv_queries.pq`
  - `powerbi/README.md`
  - `tests/unit/test_powerbi_model_contract.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_model_contract.py`
- Change boundary:
  - Do not introduce Power BI Service parameters.
  - Do not change the table list or CSV filenames.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_powerbi_model_contract.py`
  - `make powerbi-model-check`
- Review focus:
  - The source list remains exact.
  - The instructions are practical for WSL plus Windows Power BI Desktop.
- Risk/rollback:
  - Low. Roll back by restoring the prior query and README text.
- Status: completed

### Task 5: Clean up BI schema wording for current contract fields

- Outcome: BI model docs describe current report fields accurately instead of calling exported fields deprecated when they are still part of the current Power BI contract.
- Builds on or must preserve: current BI export columns and dashboard contract.
- Existing logic to reuse or extend:
  - `dbt/models/bi/schema.yml`.
  - `tests/unit/test_dbt_bi_pipeline_models.py` schema checks.
- Public contract or state/data change:
  - No column additions or removals.
  - Reword executive context fields as deliberate executive-page context/convenience fields, or explicitly defer removal to a future PBIX contract change if the fields are truly not used.
- Depends on: none.
- Likely files/modules:
  - `dbt/models/bi/schema.yml`
  - possibly `powerbi/README.md`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_bi_pipeline_models.py`
- Change boundary:
  - Documentation-only unless implementation evidence shows the current export contract should change.
  - Do not remove fields from `bi_executive_overview` in this cleanup.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_dbt_bi_pipeline_models.py`
  - `make dbt-local`
- Review focus:
  - Wording matches actual report contract and MVP responsibilities.
  - No false compatibility language remains in the active BI export surface.
- Risk/rollback:
  - Low. Roll back by restoring prior descriptions.
- Status: completed

## Final Verification

Run focused checks:

```bash
.venv/bin/python -m pytest tests/unit/test_powerbi_model_contract.py tests/unit/test_powerbi_export.py tests/unit/test_dbt_bi_pipeline_models.py tests/unit/test_prefect_local_flow.py
make powerbi-model-check
make dbt-local
git diff --check
```

Optional checks, only when WSL has enough memory and live credentials/data are ready:

```bash
make run-local
make run-cloud
```

For this cleanup, passing `make run-local` or `make run-cloud` is useful but not required unless the implementation changes runtime behavior beyond export-path configuration.

## Open Questions

- Should `POWERBI_EXPORT_DIR` become a real supported override for the local route, or should the MVP keep one fixed path and remove the unused env var?
- Should the Power Query file keep a repo-relative default for source control, or should it be written with a clearly editable absolute Windows path placeholder?
- After the user confirms PBIX usage, should the executive overview context fields remain as convenience fields or be removed from that page's export contract in a later cleanup?
