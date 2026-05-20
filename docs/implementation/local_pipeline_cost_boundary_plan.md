# Plan: Separate Local Pipeline Cost Boundaries

## Goal

Make local execution commands clearly communicate cost and purpose, then add lightweight timing, memory, and disk measurements so future dbt and pipeline optimizations are evidence-driven.

The current local route works, but the command surface is too easy to misread:

- `make dbt-local` is cheap because it only compiles the dbt graph.
- `make run-local` runs the full local pipeline. It defaults to fixture extraction, but the same script can run live extraction, raw load, full dbt build, BI validation, and Power BI export.
- Live local runs are expensive because they download and preserve large SBA raw files, load a DuckDB warehouse, and run all dbt tests.

## Non-goals

- Do not change business KPI logic.
- Do not remove raw artifact lineage or validation requirements.
- Do not delete local data as part of this command-separation slice.
- Do not optimize individual dbt SQL models until benchmarks show where the cost is.
- Do not require cloud credentials for local cost profiling.

## Constraints

- Keep the local route and cloud route distinct.
- Keep generated benchmark output under `.tmp/` so it is not committed.
- Preserve the existing user-owned `powerbi/lending_dashboard.pbix` change.
- Avoid WSL-crashing verification commands by making expensive commands explicit.
- Keep `make dbt-local` as the cheap compile check unless the user explicitly approves changing that contract.

## Execution Mode

Execution mode: sequential

Parallel groups:

- None. The command surface, benchmark wrapper, and documentation should land in order so each later task builds on named local execution modes.

## Acceptance Checks

- The Makefile exposes separate targets for cheap local compile, fixture smoke, Power BI export refresh, full local live refresh, and local benchmarking.
- Expensive targets include clear names and documentation that they perform live extraction, raw load, full dbt build/tests, or large local writes.
- Benchmark output records wall time, dbt node timings, maximum resident memory when available, DuckDB file size, `data/raw`, `data/exports`, and `dbt/target` sizes.
- Benchmark output is written under `.tmp/benchmarks/` and is ignored by Git.
- Existing local fixture flow still runs.
- Existing Power BI model contract still validates.

## Baseline

- Working tree: branch `codex/existing-sba-extra-kpis` is ahead by one dtype-warning commit; `powerbi/lending_dashboard.pbix` is dirty and user-owned.
- Current commands:
  - `make dbt-local` maps to `scripts/run_dbt_local.sh compile`.
  - `make run-local` maps to `scripts/run_local_pipeline.sh`.
  - `scripts/run_local_pipeline.sh --extract-mode live` runs the expensive live local route.
- Current disk evidence:
  - `data/` is about `3.8G`.
  - `data/raw/sba` is about `3.4G`.
  - DuckDB warehouse is about `365M`.
  - Power BI exports are about `69M`.
  - `dbt/target` is about `7.5M`.
  - `dbt/logs` is about `22M`.
- Current dbt timing evidence from `dbt/target/run_results.json`:
  - Models: 51 nodes, about 3.4 seconds summed dbt execution time.
  - Tests: 294 nodes, about 289 seconds summed dbt execution time.
  - Seeds: 4 nodes, about 0.1 seconds summed dbt execution time.
- Relevant source/tests/fixtures:
  - `Makefile`
  - `scripts/run_local_pipeline.sh`
  - `scripts/run_dbt_local.sh`
  - `scripts/export_powerbi_tables.py`
  - `pipelines/flows/lending_pipeline_flow.py`
  - `tests/unit/test_prefect_local_flow.py`
  - `tests/unit/test_powerbi_export.py`
  - `tests/unit/test_powerbi_model_contract.py`

## Proposed Command Taxonomy

Use names that make cost visible:

- `make dbt-local`: cheap dbt compile check; no data refresh.
- `make run-local-fixture`: fixture pipeline smoke; exercises the full local route on small data.
- `make powerbi-refresh-local`: rebuild or validate the local BI surface from the existing DuckDB warehouse and export CSVs.
- `make dbt-build-local-full`: full dbt build and tests against the current DuckDB warehouse; expensive because tests dominate runtime.
- `make run-local-live`: live extraction plus raw validation, DuckDB raw load, full dbt build/tests, BI validation, and CSV export; most expensive local route.
- `make benchmark-local`: measured local benchmark wrapper that records cost before and after a selected local command.

If compatibility matters, keep `make run-local` as an alias for fixture smoke and document it. If clarity matters more, keep the target but make its help text state that it is fixture-only by default and not the live refresh path.

## Tasks

### Task 1: Make Local Command Cost Explicit

- Outcome: Makefile targets separate cheap, fixture, full dbt, live, and benchmark entry points.
- Builds on or must preserve: existing `make dbt-local`, `make dbt-build-local-full`, and `make run-local` behavior.
- Existing logic to reuse or extend: `scripts/run_local_pipeline.sh`, `scripts/run_dbt_local.sh`, and `scripts/export_powerbi_tables.py`.
- Public contract or state/data change: new Makefile targets only; no data model changes.
- Depends on: none.
- Likely files/modules:
  - `Makefile`
  - `README.md`
- First command/check:
  - `make dbt-local`
- Change boundary:
  - Add target names and docs. Do not change pipeline internals.
- Verification command:
  - `make dbt-local`
  - `make run-local-fixture`
- Review focus:
  - Target names should make expensive behavior obvious.
- Risk/rollback:
  - If command names confuse existing docs, keep old aliases and document them as compatibility names.
- Stop/ask if:
  - Changing `make run-local` semantics would break a workflow the user still wants.
- Status: pending

### Task 2: Add Lightweight Local Benchmark Wrapper

- Outcome: A benchmark command captures wall time, memory, disk sizes, and dbt slow-node summaries around a selected local command.
- Builds on or must preserve: Task 1 command names.
- Existing logic to reuse or extend:
  - `dbt/target/run_results.json`
  - `du`
  - `/usr/bin/time -v` when available
  - existing Python runtime
- Public contract or state/data change:
  - Writes benchmark JSON and optional text summary under `.tmp/benchmarks/`.
  - Does not write benchmark files into tracked docs by default.
- Depends on: Task 1.
- Likely files/modules:
  - `scripts/benchmark_local_command.py`
  - `Makefile`
  - tests for benchmark parsing helpers if logic is nontrivial
- First command/check:
  - `.venv/bin/python scripts/benchmark_local_command.py --help`
- Change boundary:
  - Keep this as measurement. Do not optimize dbt models yet.
- Verification command:
  - `make benchmark-local COMMAND="make dbt-local"`
- Review focus:
  - Benchmark should make failures visible and should not hide the wrapped command exit code.
- Risk/rollback:
  - If `/usr/bin/time -v` is unavailable, fall back to Python wall-time plus disk/dbt artifact summaries and mark memory as unavailable.
- Stop/ask if:
  - Capturing max RSS requires installing dependencies or changing the shell environment.
- Status: pending

### Task 3: Add Stage Durations To Pipeline Run Summary

- Outcome: local pipeline run summaries show how long each stage took, making extraction, validation, raw load, dbt, BI validation, and export costs visible without reading logs.
- Builds on or must preserve: existing `run_summary.json` fields and Power BI pipeline health output.
- Existing logic to reuse or extend:
  - `pipelines/flows/lending_pipeline_flow.py`
  - current `completed_stages` and `started_at_utc` / `finished_at_utc` summary fields
- Public contract or state/data change:
  - Add a `stage_durations_seconds` field to run summaries.
  - Do not remove existing summary fields.
- Depends on: none, but benefits from Task 1 naming.
- Likely files/modules:
  - `pipelines/flows/lending_pipeline_flow.py`
  - `tests/unit/test_prefect_local_flow.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py -k summary`
- Change boundary:
  - Timing metadata only. No pipeline behavior change.
- Verification command:
  - `make run-local-fixture`
  - inspect the produced `run_summary.json`
- Review focus:
  - Durations should be stable enough for diagnostics but not used as pass/fail thresholds.
- Risk/rollback:
  - If timing inside Prefect tasks is awkward, capture coarse stage timings around task submission boundaries first.
- Stop/ask if:
  - Prefect task result timing would require a broader orchestration redesign.
- Status: pending

### Task 4: Split Fast BI Refresh From Full Quality Validation

- Outcome: Power BI report work can refresh local CSVs without accidentally running live extraction or every dbt test.
- Builds on or must preserve:
  - Task 1 command taxonomy.
  - Existing exact Power BI export contract.
- Existing logic to reuse or extend:
  - `scripts/export_powerbi_tables.py`
  - `make powerbi-model-check`
  - dbt selectors or tags
- Public contract or state/data change:
  - Introduce a documented fast path that assumes DuckDB raw data already exists.
  - Full validation remains available as a separate explicit command.
- Depends on: Task 1.
- Likely files/modules:
  - `Makefile`
  - `dbt/models/**/*.yml` if tags/selectors are needed
  - `README.md`
  - `tests/unit/test_powerbi_export.py`
- First command/check:
  - `make powerbi-model-check`
- Change boundary:
  - Do not weaken the full quality path. Add a separate fast path.
- Verification command:
  - `make powerbi-refresh-local`
  - `make powerbi-model-check`
- Review focus:
  - The fast path should be honest about what it does not prove.
- Risk/rollback:
  - If dbt selector behavior is unclear, keep the first version to export-only plus model-contract validation and leave selective dbt builds for a later issue.
- Stop/ask if:
  - The user wants every Power BI refresh to always run the full dbt test suite.
- Status: pending

### Task 5: Define Optimization Experiments After Baseline

- Outcome: future optimizations are treated as measured experiments instead of speculative refactors.
- Builds on or must preserve:
  - Benchmark output from Task 2.
  - Stage timings from Task 3.
- Existing logic to reuse or extend:
  - dbt `run_results.json`
  - DuckDB warehouse size and relation row counts
- Public contract or state/data change:
  - No immediate behavior change. This task creates experiment candidates and acceptance thresholds.
- Depends on: Tasks 2 and 3.
- Likely files/modules:
  - `docs/implementation/local_pipeline_cost_boundary_plan.md`
  - future GitHub issues
- First command/check:
  - Compare two benchmark JSON outputs from the same command.
- Change boundary:
  - Planning and issue creation only.
- Verification command:
  - Benchmark summary includes the current top slow dbt tests and disk consumers.
- Review focus:
  - Experiments should isolate one variable at a time.
- Risk/rollback:
  - Do not materialize large dbt models just because it feels faster; require before/after evidence.
- Stop/ask if:
  - A proposed optimization increases disk or cloud cost more than the user wants.
- Status: pending

## Final Verification

Run the checks that match the implemented slices:

```bash
make dbt-local
make run-local-fixture
make powerbi-model-check
make benchmark-local COMMAND="make dbt-local"
git diff --check
```

Optional stronger checks when WSL has memory headroom:

```bash
make dbt-build-local-full
make benchmark-local COMMAND="make dbt-build-local-full"
scripts/run_local_pipeline.sh --extract-mode live --pipeline-run-id live-cost-baseline-YYYYMMDD
```

## Open Questions

- Should `make run-local` remain as the fixture smoke alias, or should it be renamed/deprecated to force users to choose `run-local-fixture` or `run-local-live`?
- Should the first fast Power BI path rebuild dbt BI models, or should it only validate/export from the current DuckDB warehouse?
- Should full dbt tests be tagged into `critical`, `reconciliation`, and `full` groups in this slice, or should that wait until benchmark output confirms the slowest tests?
- How many historical live raw runs should local cleanup preserve by default after the command split is in place?
