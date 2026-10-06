# Agent instructions

This is a personal, local-first analytics engineering project: public SBA approval
records, Census BDS and BLS LAUS → validated snapshots → DuckDB or S3/Snowflake →
dbt → Power BI. Keep predictive ML, borrower scoring and causal claims out of scope.

## Start and verify

Check `git status --short --branch` and preserve unrelated work. The Makefile runtime
is Python 3.12 on Linux/WSL; Docker uses the same gate. `make ci-check` is the standard
runtime check. Documentation-only changes need `git diff --check` and review of
affected owners and links; read the [testing guide](docs/detailed/testing_plan.md)
for task-specific checks.

## Project boundaries

- Preserve raw extracts, manifests, checksums and validation evidence. Reporting
  consumes validated selected snapshots. Keep generated data, warehouses and dbt
  artifacts out of Git; use the runtime guide before rebuilding or cleaning them.
- dbt owns record eligibility, source/grain alignment, business definitions and
  additive components. Power BI aggregates modeled `bi_*` components in filter
  context; it does not recreate raw business logic. Preserve source grain and
  scientific meaning when changing metrics.
- `powerbi/lending_dashboard.pbix` is an ignored, local manual Desktop artifact
  pending correction. Edit, stage or
  commit it only when the user explicitly asks. Report status and known issues
  belong in the Power BI handoff; source-contract tests do not certify the binary.
- Power BI consumes modeled BI exports or Snowflake BI tables. Keep credentials
  and borrower-identifying fields off that surface; do not hardcode secrets or
  live row-count expectations.
- Keep the implemented local and cloud routes. Add infrastructure only for the
  requested scope; ordinary verification does not need a live source or cloud run.

## Read for the task

Load the relevant owner before changing the behavior it describes; do not read
every document at startup.

| When working on | Read |
|---|---|
| Scope, acceptance or issue-based implementation | [Project specification and tracker workflow](docs/detailed/project_spec.md) |
| Extraction, raw storage, validation or load boundaries | [Architecture](docs/detailed/architecture.md) and [source inventory](docs/detailed/data_source_inventory.md) |
| dbt, metrics, period coverage or freshness | [KPI methodology](docs/detailed/kpi_definitions.md) and [data model](docs/detailed/data_model.md); column contracts live in dbt schema YAML |
| Setup, pipeline execution, cloud, cleanup or benchmarks | [Runtime guide](docs/detailed/orchestration_runtime.md) |
| Power BI, exports, measures, report or screenshots | [Power BI handoff](powerbi/README.md) |
| Tests or verification changes | [Testing guide](docs/detailed/testing_plan.md) |
| Documentation ownership, decisions or historical evidence | [Documentation map](docs/README.md) |

Update the maintained owner and its affected consumers when behavior changes.
Code/configuration and enforced contracts own implementation facts; current docs
own scope, meaning and rationale. Historical plans preserve evidence, not an
automatic work queue.
