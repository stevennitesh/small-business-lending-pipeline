# Plan: Stabilize Local Verification And Clean Local Data

## Goal

Make local verification safe for WSL2 while preserving the ability to run a full dbt/DuckDB build when explicitly requested. Reclaim local disk by deleting rebuildable temp files and duplicate raw SBA extracts through a clear, reviewable cleanup path.

GitHub issue: #52

## Current Status Note

The safe command boundary has landed: `make dbt-local` now aliases
`dbt-compile-local`, and the full local dbt build is explicit as
`make dbt-build-local-full`. Local cleanup is available through
`make cleanup-local-data-dry-run` and requires explicit apply mode for
deletion.

## Non-goals

- Do not remove the local route, DuckDB, dbt, S3, or Snowflake.
- Do not change KPI logic, BI contracts, or source data semantics.
- Do not delete the current useful raw extract, manifests, validation results, or Power BI artifacts without explicit approval.
- Do not run the explicit full local dbt build unless WSL has enough memory
  headroom.

## Constraints

- WSL2 currently has about 15 GiB RAM and 4 GiB swap available.
- Existing dbt resource logs show full `dbt build --target dev_duckdb` runs reaching roughly 14-15 GiB max RSS.
- `data/raw/sba` is about 4.2 GiB and contains repeated copies of the same large SBA files across multiple pipeline runs.
- `data/warehouse/small_business_lending.duckdb.tmp` is about 447 MiB and appears to be leftover DuckDB temp storage from an interrupted or unstable run.
- The working tree is already dirty from route-hard-switch work and an unrelated `powerbi/lending_dashboard.pbix` change; cleanup implementation must stage only its own files.

## Execution Mode

Execution mode: sequential

Parallel groups: None

## Baseline

- Historical failing symptom: full local dbt verification could destabilize
  WSL2.
- Historical trigger command: `make dbt-local`
- Current lightweight command: `make dbt-local` / `make dbt-compile-local`
- Current explicit full command: `make dbt-build-local-full`
- Current dbt local profile: DuckDB target with `threads: 4`
- Current local data footprint:
  - `data/raw/sba`: about 4.2 GiB
  - `data/warehouse`: about 812 MiB
  - `data/warehouse/small_business_lending.duckdb`: about 365 MiB
  - `data/warehouse/small_business_lending.duckdb.tmp`: about 447 MiB
  - `dbt/logs`: about 23 MiB
  - `dbt/target`: about 6.5 MiB
- Largest duplicate raw extracts are repeated under older SBA `pipeline_run_id` directories:
  - `t04-live-smoke`
  - `live-dashboard-2020-2024`
  - `live-dashboard-2020-2024-rerun`
  - `live-dashboard-2020-2024-final`
- Likely current complete local raw SBA run to preserve:
  - `live-dashboard-1990-current-context`

## Acceptance Checks

- There is a safe default local verification command that does not run the full live-data dbt build.
- The old full local dbt build is renamed or documented as an explicit heavy command.
- Local dbt/DuckDB verification uses lower concurrency by default.
- Cleanup candidates can be previewed before deletion.
- Duplicate raw SBA runs can be deleted without deleting the selected current run.
- Rebuildable DuckDB temp artifacts can be removed safely.
- The final implementation does not stage or delete user-owned Power BI changes.

## Tasks

### Task 1: Add Safe Verification Command Boundaries

- Outcome: Make the default verification path lightweight and make the heavy full dbt build explicit.
- Builds on or must preserve: existing Makefile workflow and `scripts/run_dbt_local.sh`.
- Existing logic to reuse or extend: Makefile targets and dbt local profile generation.
- Public contract or state/data change: command naming and local verification ergonomics only.
- Depends on: None.
- Likely files/modules:
  - `Makefile`
  - `scripts/run_dbt_local.sh`
  - `dbt/profiles.yml.example`
  - docs mentioning `make dbt-local`
- Change boundary:
  - Add a lightweight dbt check target such as `dbt-compile-local`.
  - Keep full dbt build available under an explicit name such as `dbt-build-local-full`.
  - Make `make test` avoid unexpected full live dbt builds unless it already does so.
  - Lower local DuckDB dbt threads from 4 to 1 by default.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py`
  - `make dbt-compile-local` or equivalent lightweight command
  - `git diff --check`
- Review focus:
  - No hidden invocation of full live-data dbt build from default agent verification.
  - Existing user-facing commands remain understandable.
- Risk/rollback:
  - Roll back Makefile/profile changes if the command contract becomes confusing.
- Stop/ask if:
  - The repo requires `make dbt-local` to keep meaning "full dbt build" for external documentation.
- Status: pending

### Task 2: Add Local Data Cleanup Dry Run

- Outcome: Provide a safe way to list cleanup candidates before deleting them.
- Builds on or must preserve: `.tmp/` scratch policy and local-first raw artifact traceability.
- Existing logic to reuse or extend: none required; keep implementation small.
- Public contract or state/data change: new local maintenance command only.
- Depends on: Task 1 only for command naming consistency.
- Likely files/modules:
  - `scripts/cleanup_local_data.py` or `scripts/cleanup_local_data.sh`
  - `Makefile`
  - docs under `docs/implementation/` or README maintenance notes
- Change boundary:
  - Add a dry-run-first cleanup command that reports reclaimable bytes.
  - Include explicit cleanup categories:
    - DuckDB temp directories, especially `data/warehouse/*.duckdb.tmp`
    - dbt logs and target artifacts
    - selected old raw SBA `pipeline_run_id` directories
  - Do not delete manifests, validation results, Power BI exports, or the active DuckDB warehouse by default.
- Verification command:
  - Run cleanup in dry-run mode only.
  - Confirm expected candidates include `data/warehouse/small_business_lending.duckdb.tmp`.
  - Confirm expected candidates exclude `live-dashboard-1990-current-context`.
  - `git diff --check`
- Review focus:
  - Dry run is the default.
  - Destructive mode requires an explicit flag.
  - Paths are constrained to repo-local generated data directories.
- Risk/rollback:
  - If cleanup selection is too broad, keep dry-run only and do not enable deletion yet.
- Stop/ask if:
  - The user wants to preserve older dashboard run artifacts for comparison.
- Status: pending

### Task 3: Delete Approved Rebuildable Local Artifacts

- Outcome: Reclaim disk after the dry-run output is reviewed.
- Builds on or must preserve: Task 2 cleanup tool and current raw run selection.
- Existing logic to reuse or extend: dry-run candidate selection.
- Public contract or state/data change: local generated data deletion only.
- Depends on: Task 2 and explicit approval of the deletion candidate list.
- Likely delete targets:
  - `data/warehouse/small_business_lending.duckdb.tmp`
  - old duplicate SBA raw run directories for `t04-live-smoke`
  - old duplicate SBA raw run directories for `live-dashboard-2020-2024`
  - old duplicate SBA raw run directories for `live-dashboard-2020-2024-rerun`
  - old duplicate SBA raw run directories for `live-dashboard-2020-2024-final`
- Preserve by default:
  - `data/raw/sba/**/pipeline_run_id=live-dashboard-1990-current-context`
  - `data/manifests`
  - `data/validation`
  - `data/exports/powerbi`
  - `powerbi/lending_dashboard.pbix`
  - `data/warehouse/small_business_lending.duckdb` unless the user approves rebuilding DuckDB
- Verification command:
  - Run cleanup dry-run first.
  - Run cleanup apply only after approval.
  - `du -h -d 2 data .tmp dbt/logs dbt/target`
- Review focus:
  - Actual deleted paths match the approved candidate list exactly.
  - No tracked files are deleted.
- Risk/rollback:
  - Raw source files are reproducible from public sources, but re-download costs time and network.
  - Manifests that point at deleted raw files become historical lineage records, not reload-ready local pointers.
- Stop/ask if:
  - The cleanup would remove the only raw copy for a period/source combination the user still needs locally.
- Status: pending

### Task 4: Make Heavy dbt Verification Less Memory-Intensive

- Outcome: Reduce WSL memory pressure for full local dbt builds that are run intentionally.
- Builds on or must preserve: Task 1 command boundaries.
- Existing logic to reuse or extend: existing dbt model structure and schema tests.
- Public contract or state/data change: local build performance and materialization behavior only.
- Depends on: Task 1.
- Likely files/modules:
  - `dbt/dbt_project.yml`
  - heavy SBA staging/fact model configs
  - `dbt/profiles.yml.example`
  - dbt docs or Makefile help
- Change boundary:
  - Keep local DuckDB concurrency low.
  - Consider table materialization for heavy local DuckDB models that many tests reuse, especially SBA staging/fact models.
  - Avoid changing Snowflake/cloud materialization unless source evidence says it benefits the cloud route too.
  - Do not weaken dbt tests just to make them pass faster.
- Verification command:
  - Prefer targeted dbt selection first, not full build.
  - Lightweight guardrail: `make dbt-local` or `make dbt-compile-local`
  - Full build can be manually run later with `make dbt-build-local-full` when WSL has enough memory headroom.
- Review focus:
  - Heavy models are computed once when full build is requested instead of repeatedly through view chains.
  - No KPI or BI output semantics change.
- Risk/rollback:
  - Materialization changes can affect local warehouse size and stale-table behavior.
  - Roll back materialization if it complicates iteration more than it helps memory.
- Stop/ask if:
  - dbt target-specific materialization becomes too clever or unclear for MVP maintainability.
- Status: pending

### Task 5: Update Verification Guidance

- Outcome: Document how agents and humans should verify safely in WSL2.
- Builds on or must preserve: AGENTS.md verification guidance and local-first project goal.
- Existing logic to reuse or extend: current repo docs and Makefile commands.
- Public contract or state/data change: documentation only.
- Depends on: Tasks 1-4.
- Likely files/modules:
  - `AGENTS.md`
  - `README.md`
  - `docs/implementation/local_cloud_route_plan.md` if route docs need command updates
- Change boundary:
  - State that full live-data dbt builds are heavy and explicit.
  - Recommend focused pytest plus lightweight dbt compile/smoke for agent verification.
  - Recommend cleanup dry-run before deleting generated local data.
- Verification command:
  - `git diff --check`
- Review focus:
  - Guidance is concise and does not become a progress log.
- Risk/rollback:
  - Documentation can be adjusted if command names change during implementation.
- Stop/ask if:
  - The user wants this guidance kept outside AGENTS.md.
- Status: pending

## Final Verification

Use `make dbt-local` for lightweight compile verification. Use
`make dbt-build-local-full` only when an explicit full live-data DuckDB build
is needed and WSL has enough memory headroom.

Recommended final checks after implementation:

- `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py tests/integration/test_duckdb_loader.py tests/unit/test_dbt_bi_pipeline_models.py tests/unit/test_dbt_marts_models.py`
- `make dbt-local` or `make dbt-compile-local`
- cleanup dry-run command
- `git diff --check`
- `git status --short --branch`

Optional manual full-build check after cleanup and WSL guardrails:

- Close memory-heavy apps.
- Confirm WSL has enough RAM/swap headroom.
- Run the explicit full command only, not the default lightweight command.
- Watch memory usage while it runs.

## Open Questions

- Should the current raw SBA run to preserve be exactly `live-dashboard-1990-current-context`, or should another pipeline run be treated as the local golden copy?
- Should `data/warehouse/small_business_lending.duckdb` be preserved for Power BI convenience, or deleted and rebuilt when needed?
- Should old raw manifests remain as historical records even when their local raw files are deleted? The recommended answer is yes for now because they are tiny and useful for audit context.
