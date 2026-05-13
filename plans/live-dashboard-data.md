# Live Dashboard Data Plan

## Goal

Move the dashboard dataset from the deterministic two-row fixture slice to real public source extracts so Power BI can show credible multi-year, multi-state trends.

## Non-goals

- Do not move KPI math into Power BI.
- Do not commit raw extracts, local warehouse files, or Power BI CSV exports.
- Do not expose credentials, private account identifiers, or borrower-level BI fields.
- Do not require Snowflake/S3 to refresh the local dashboard dataset.

## Constraints

- Execution mode: sequential.
- Commit after each issue is verified.
- Push all commits together at the end.
- Keep fixture mode available for fast deterministic tests.
- Use GitHub issues as the implementation tracker.

## Issue List

1. [#30](https://github.com/stevennitesh/small-business-lending-pipeline/issues/30) - Add live source extraction mode to the Prefect pipeline.
2. [#31](https://github.com/stevennitesh/small-business-lending-pipeline/issues/31) - Refresh and verify the modeled dashboard dataset from live sources.

## Acceptance Checks

- Local fixture mode still passes existing tests.
- Live mode calls the SBA, Census BDS, and BLS LAUS extractors instead of fixture writers.
- Raw validation adapts to configured state/series coverage instead of hardcoded AL/IL fixtures.
- BI tables/exported CSVs show multi-year and broader state coverage after a live run.
- PBIX remains connected to modeled BI/export tables, not raw files.

## Verification Strategy

- Focused pytest coverage for fixture/live extraction routing and dynamic validation expectations.
- `make test`.
- Live smoke run with explicit year bounds suitable for dashboard refresh.
- `make dbt-local`.
- `.venv/bin/python scripts/export_powerbi_tables.py`.
- Warehouse/export year and state coverage query.

## Risks And Stop Conditions

- Stop if public source downloads fail or source contracts have changed.
- Stop if live source volume is too large for the local machine without an explicit narrowing decision.
- Stop if Power BI Desktop must refresh or save the PBIX and cannot be automated from WSL.
