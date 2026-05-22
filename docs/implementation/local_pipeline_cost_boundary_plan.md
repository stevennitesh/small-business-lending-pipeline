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

## Implemented Cost-Boundary Evidence

This section records measured evidence from the command split implementation. Use
it as the baseline for future optimization experiments; do not treat one run as
a stable performance guarantee.

- Benchmark wrapper:
  - Command: `make benchmark-local COMMAND="make dbt-local"`.
  - Output JSON: `.tmp/benchmarks/20260522T222906Z-make-dbt-local.json`.
  - Output text: `.tmp/benchmarks/20260522T222906Z-make-dbt-local.txt`.
  - Observed exit code: `0`.
  - Observed wall time: about `4.296` seconds.
  - Observed max RSS: about `177,508,352` bytes.
  - Observed disk deltas:
    - `data`: `0` bytes.
    - `data/warehouse`: `0` bytes.
    - `data/exports/powerbi`: `0` bytes.
    - `dbt/target`: about `51` bytes.
- Fast dbt mode:
  - Command: `make dbt-build-local-fast`.
  - Behavior: `dbt seed`, `dbt run`, then `dbt test --select tag:critical`.
  - Critical tests selected: 33 BI tests.
  - Observed critical test result: PASS=33, WARN=0, ERROR=0, SKIP=0.
  - Full validation remains `make dbt-build-local-full`.
- Fast Power BI refresh:
  - Command: `make powerbi-refresh-local`.
  - Behavior: fast dbt mode, Power BI CSV export, then model contract check.
  - Observed Power BI model contract: 17 tables, 25 relationships, filter
    coverage for industry, lender, program, region, state, and year.
- Fixture pipeline stage durations:
  - Command: `make run-local-fixture`.
  - Output summary:
    `data/validation/pipeline_run_id=local-201f173d-183f-4216-bacd-d5f00c88e9c0/run_summary.json`.
  - Observed `stage_durations_seconds`:
    - `extract_sources`: `0.026`.
    - `validate_raw_outputs`: `0.021`.
    - `load_duckdb_raw_tables`: `0.267`.
    - `run_dbt_build`: `24.043`.
    - `validate_bi_tables`: `0.947`.
    - `export_bi_tables`: `1.79`.
    - `write_run_summary`: `0.001`.

## Proposed Command Taxonomy

Use names that make cost visible:

- `make dbt-local`: cheap dbt compile check; no data refresh.
- `make run-local-fixture`: fixture pipeline smoke; exercises the full local route on small data.
- `make benchmark-local`: measured local benchmark wrapper that records cost before and after a selected local command.
- `make dbt-build-local-fast`: run dbt models and only critical tests against the current DuckDB warehouse.
- `make dbt-build-local-full`: full dbt build and tests against the current DuckDB warehouse; expensive because tests dominate runtime.
- `make powerbi-refresh-local`: rebuild or validate the local BI surface from the existing DuckDB warehouse and export CSVs.
- `make run-local-live`: live extraction plus raw validation, DuckDB raw load, full dbt build/tests, BI validation, and CSV export; most expensive local route.

If compatibility matters, keep `make run-local` as an alias for fixture smoke and document it. If clarity matters more, keep the target but make its help text state that it is fixture-only by default and not the live refresh path.

Optimization order matters: make accidental expensive runs harder first, measure cost second, then split dbt execution/test modes before changing SQL materialization. Do not materialize large models until benchmark evidence shows the tradeoff is worth the extra disk.

## Tasks

### Task 1: Make Local Command Cost Explicit

- Outcome: Makefile targets separate cheap compile, fixture smoke, benchmark, fast dbt, full dbt, Power BI refresh, and live refresh entry points.
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
  - Target names should make expensive behavior obvious before any performance tuning begins.
- Risk/rollback:
  - If command names confuse existing docs, keep old aliases and document them as compatibility names.
- Stop/ask if:
  - Changing `make run-local` semantics would break a workflow the user still wants.
- Status: completed in issue #92.

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
  - `make benchmark-local COMMAND="make dbt-build-local-full"` when WSL has enough memory headroom
- Review focus:
  - Benchmark should make failures visible and should not hide the wrapped command exit code.
- Risk/rollback:
  - If `/usr/bin/time -v` is unavailable, fall back to Python wall-time plus disk/dbt artifact summaries and mark memory as unavailable.
- Stop/ask if:
  - Capturing max RSS requires installing dependencies or changing the shell environment.
- Status: completed in issue #93.

### Task 3: Split DBT Fast And Full Quality Modes

- Outcome: local dbt work has a fast mode for iteration and a full mode for release-quality validation.
- Builds on or must preserve: Task 2 benchmark output and existing full `dbt build` behavior.
- Existing logic to reuse or extend:
  - `scripts/run_dbt_local.sh`
  - dbt selectors and tags
  - current schema and custom tests
- Public contract or state/data change:
  - Add a fast dbt command that runs models plus critical tests only.
  - Preserve the full dbt build/test path unchanged.
- Depends on: Tasks 1 and 2.
- Likely files/modules:
  - `Makefile`
  - `scripts/run_dbt_local.sh`
  - `dbt/models/**/*.yml`
  - `dbt/tests/*.sql`
- First command/check:
  - `make benchmark-local COMMAND="make dbt-build-local-full"`
- Change boundary:
  - Tag or select tests; do not rewrite dbt SQL for speed in this task.
- Verification command:
  - `make dbt-build-local-fast`
  - `make dbt-build-local-full` when WSL has enough memory headroom
- Review focus:
  - Fast mode must be honest: it is for iteration, not a replacement for full validation.
- Risk/rollback:
  - If selecting critical tests becomes ambiguous, tag only the obvious smoke/contract tests and leave reconciliation-heavy test tagging for a follow-up.
- Stop/ask if:
  - Critical/full test boundaries would change data quality expectations rather than command cost.
- Status: completed in issue #94.

### Task 4: Add Fast Power BI Refresh

- Outcome: Power BI report work can refresh local CSVs without accidentally running live extraction or every dbt test.
- Builds on or must preserve:
  - Task 1 command taxonomy.
  - Task 3 fast dbt mode.
  - Existing exact Power BI export contract.
- Existing logic to reuse or extend:
  - `scripts/export_powerbi_tables.py`
  - `make powerbi-model-check`
  - dbt selectors or tags
- Public contract or state/data change:
  - Introduce a documented fast path that assumes DuckDB raw data already exists.
  - Full validation remains available as a separate explicit command.
- Depends on: Tasks 1 and 3.
- Likely files/modules:
  - `Makefile`
  - `dbt/models/**/*.yml` if tags/selectors are needed
  - `README.md`
  - `tests/unit/test_powerbi_export.py`
- First command/check:
  - `make powerbi-model-check`
- Change boundary:
  - Do not weaken the full quality path. Add a separate fast report-refresh path.
- Verification command:
  - `make powerbi-refresh-local`
  - `make powerbi-model-check`
- Review focus:
  - The fast path should be honest about what it does not prove.
- Risk/rollback:
  - If dbt selector behavior is unclear, keep the first version to export-only plus model-contract validation and leave selective dbt builds for a later issue.
- Stop/ask if:
  - The user wants every Power BI refresh to always run the full dbt test suite.
- Status: completed in issue #95.

### Task 5: Add Stage Durations To Pipeline Run Summary

- Outcome: local pipeline run summaries show how long each stage took, making extraction, validation, raw load, dbt, BI validation, and export costs visible without reading logs.
- Builds on or must preserve: existing `run_summary.json` fields and Power BI pipeline health output.
- Existing logic to reuse or extend:
  - `pipelines/flows/lending_pipeline_flow.py`
  - current `completed_stages` and `started_at_utc` / `finished_at_utc` summary fields
- Public contract or state/data change:
  - Add a `stage_durations_seconds` field to run summaries.
  - Do not remove existing summary fields.
- Depends on: Tasks 1 and 2.
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
- Status: completed in issue #96.

### Task 6: Define Optimization Experiments After Baseline

- Outcome: future optimizations are treated as measured experiments instead of speculative refactors.
- Builds on or must preserve:
  - Benchmark output from Task 2.
  - Fast/full dbt split from Task 3.
  - Stage timings from Task 5.
- Existing logic to reuse or extend:
  - dbt `run_results.json`
  - DuckDB warehouse size and relation row counts
- Public contract or state/data change:
  - No immediate behavior change. This task creates experiment candidates and acceptance thresholds.
- Depends on: Tasks 2, 3, and 5.
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
  - Experiments should isolate one variable at a time: test selection, model materialization, thread count, or raw retention.
- Risk/rollback:
  - Do not materialize large dbt models just because it feels faster; require before/after evidence.
- Stop/ask if:
  - A proposed optimization increases disk or cloud cost more than the user wants.
- Status: completed in issue #97.

## Benchmark-Driven Follow-Up Experiments

Run these only after the command split is merged. Each experiment should change
one variable, capture before/after benchmark output under `.tmp/benchmarks/`,
and preserve correctness checks appropriate to the path being optimized.

### Experiment A: Test Selection

- Question: can full dbt validation be split into named quality tiers without
  hiding important failures during normal Power BI iteration?
- Baseline evidence:
  - Full historical dbt timing evidence shows tests dominate summed execution
    time: about 289 seconds of test execution versus about 3.4 seconds of model
    execution.
  - Fast mode currently selects 33 BI `critical` tests and passed them.
- Candidate change:
  - Add a second tag such as `reconciliation` for heavier cross-table checks.
  - Keep relationship-heavy tests in full validation unless they prove cheap and
    valuable for iteration.
- Measurement:
  - `make benchmark-local COMMAND="make dbt-build-local-fast"`.
  - `make benchmark-local COMMAND="make dbt-build-local-full"` only when WSL has
    enough memory headroom.
- Acceptance signal:
  - Fast mode stays useful for Power BI iteration.
  - Full mode remains available and unchanged in quality expectations.

### Experiment B: Model Materialization

- Question: are selected marts or BI views repeatedly recomputed enough to
  justify materializing them locally?
- Baseline evidence:
  - Fixture stage durations show `run_dbt_build` dominates the local fixture
    route at about 24 seconds.
  - Current models are views, which keeps disk lower but can repeat work during
    validation and export.
- Candidate change:
  - Test materializing only the highest-cost BI or mart candidates first.
  - Do not materialize broad staging/raw models without benchmark proof.
- Measurement:
  - Benchmark fast and full dbt modes before and after.
  - Compare DuckDB size and `data/warehouse` delta from benchmark JSON.
- Acceptance signal:
  - Wall-time reduction is meaningful and repeatable.
  - DuckDB growth is acceptable for the local route.
  - Power BI export row counts and model contract remain unchanged.

### Experiment C: DBT Thread Count

- Question: can the local dbt run use more than one thread without raising WSL
  memory pressure or DuckDB contention?
- Baseline evidence:
  - Current local dbt profile uses `threads: 1`.
  - Compile benchmark max RSS was about 177 MB, but build/test paths need their
    own measurements.
- Candidate change:
  - Add an explicit opt-in local environment variable or profile override for
    `threads: 2`.
  - Keep the default conservative until benchmark evidence says otherwise.
- Measurement:
  - Benchmark `make dbt-build-local-fast` with one thread and two threads.
  - Repeat only after the prior run has settled to avoid comparing warm/cold
    artifacts accidentally.
- Acceptance signal:
  - Two threads reduce wall time without materially increasing memory risk or
    causing intermittent DuckDB failures.

### Experiment D: Raw Retention Cleanup

- Question: can local disk usage be kept small without weakening raw lineage for
  the latest successful local run?
- Baseline evidence:
  - Prior disk evidence showed `data/raw/sba` as the main local disk consumer at
    about 3.4 GB.
  - Cleanup commands already exist, but this implementation pass did not delete
    data.
- Candidate change:
  - Define a documented retention rule such as keep latest successful fixture
    run, latest successful live run, and any explicitly pinned run IDs.
  - Keep delete behavior behind dry-run output first.
- Measurement:
  - `make cleanup-local-data-dry-run`.
  - Compare benchmark disk-size snapshots before and after any approved cleanup.
- Acceptance signal:
  - Disk reclaimed is clear before deletion.
  - Latest successful validated run remains reproducible.
  - No source-controlled artifacts or PBIX files are touched.

## Final Verification

Run the checks that match the implemented slices:

```bash
make dbt-local
make run-local-fixture
make dbt-build-local-fast
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

- Resolved: `make run-local` remains a fixture smoke alias. Use
  `make run-local-live` for live local extraction.
- Resolved: the first fast dbt mode uses only `critical` tags.
- Resolved: the first fast Power BI path runs `make dbt-build-local-fast`
  before export.
- Deferred: a `reconciliation` tag can be tested as Experiment A.
- Deferred: the exact live raw retention count should be decided during
  Experiment D after dry-run cleanup evidence.
