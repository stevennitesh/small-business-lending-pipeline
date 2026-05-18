# Plan: Remove Local-File Snowflake Loader

## Goal

Remove the old local-file-to-Snowflake compatibility path so raw load has only two intentional routes:

- Local route: local raw files and manifests load into DuckDB.
- Cloud route: S3-backed raw files, manifests, and validation output load into Snowflake through the S3-stage loader.

After this cleanup, Snowflake raw loading should mean the cloud S3-stage path. The repo should no longer expose a third path that pushes local files into Snowflake through the Python connector.

## Non-goals

- Do not remove Snowflake cloud loading.
- Do not remove DuckDB local loading.
- Do not change raw table schemas.
- Do not change dbt models, Power BI contracts, or cloud storage integration setup.
- Do not remove cloud-route aliases in this slice.
- Do not remove the local-to-S3 artifact upload helper unless it is directly tied to the local-file Snowflake loader.

## Constraints

- Preserve current local and cloud route behavior.
- Keep default tests free of live AWS and Snowflake dependencies.
- Do not touch local data files, generated warehouse files, or the Power BI `.pbix`.
- Stage and commit only source, tests, docs, and scripts related to this cleanup.

## Execution Mode

Execution mode: sequential

Parallel groups:

- None. This is a small deletion/refactor across one loader module, one script, tests, and docs.

## Acceptance Checks

- `load_raw_extracts_to_snowflake(...)` no longer exists.
- `load_local_raw_extracts_to_snowflake_for_testing(...)` no longer exists.
- `scripts/load_snowflake.sh` is removed or retired if it only invokes the local-file loader.
- `pipelines/flows/lending_pipeline_flow.py` imports only `load_raw_extracts_to_snowflake_from_s3(...)` for Snowflake raw loading.
- Snowflake loader tests cover the S3-stage cloud loader and no longer cover the removed local-file path.
- Docs describe Snowflake raw load as S3-stage cloud load only.
- Focused tests and whitespace checks pass.

## Baseline

- Working tree: only the user-owned `powerbi/lending_dashboard.pbix` is dirty after the latest commit.
- Current behavior:
  - Active cloud flow calls `load_raw_extracts_to_snowflake_from_s3(...)`.
  - `load_raw_extracts_to_snowflake(...)` exists only as a compatibility alias.
  - `load_local_raw_extracts_to_snowflake_for_testing(...)` loads local raw files through the Python connector.
  - `scripts/load_snowflake.sh` runs `python -m pipelines.load.snowflake_loader`, whose `main()` currently calls the local-file testing helper.
- Current evidence:
  - Search shows no Makefile or active flow path calling `scripts/load_snowflake.sh`.
  - Tests currently import and test the local-file helper.
- Relevant source/tests/docs:
  - `pipelines/load/snowflake_loader.py`
  - `pipelines/flows/lending_pipeline_flow.py`
  - `scripts/load_snowflake.sh`
  - `tests/unit/test_snowflake_loader.py`
  - `README.md`
  - `docs/implementation/local_cloud_route_plan.md`
  - `docs/implementation/raw_load_route_boundary_cleanup_plan.md`
  - `docs/implementation/two_route_safe_hard_switch_plan.md`
  - `docs/implementation/cloud_artifact_handoff_plan.md`
  - `docs/implementation/implementation_plan.md`
  - `docs/detailed/architecture.md`

## Tasks

### Task 1: Remove The Local-File Snowflake Loader API

- Outcome: `pipelines/load/snowflake_loader.py` exposes only the S3-stage Snowflake raw-load function for loading source artifacts.
- Builds on or must preserve:
  - `load_raw_extracts_to_snowflake_from_s3(...)`
  - Snowflake config and connection helpers.
  - Shared metadata, file-format, stage, and row-count reconciliation logic used by the S3 loader.
- Existing logic to reuse or extend:
  - Keep S3-stage functions and helper SQL intact.
  - Remove only local-file Python connector loading logic and its alias.
- Public contract or state/data change:
  - Removes the local-file Snowflake API and compatibility alias.
  - Snowflake raw load public contract becomes S3-stage only.
- Depends on: none.
- Likely files/modules:
  - `pipelines/load/snowflake_loader.py`
  - `pipelines/flows/lending_pipeline_flow.py`
- First command/check:
  - `rg -n "load_raw_extracts_to_snowflake\\b|load_local_raw_extracts_to_snowflake_for_testing\\b" pipelines tests scripts README.md docs`
- Change boundary:
  - Do not modify S3-stage loading behavior or schema/table names.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_snowflake_loader.py`
- Review focus:
  - No local-source-frame loading remains in `snowflake_loader.py`.
- Risk/rollback:
  - Restore from prior commit if an undiscovered manual workflow still requires local files into Snowflake.
- Stop/ask if:
  - A Makefile target or active cloud flow still depends on the removed function.
- Status: completed

### Task 2: Remove The Manual Local-File Snowflake Script

- Outcome: the repo no longer advertises or ships `scripts/load_snowflake.sh` as a local-file Snowflake entry point.
- Builds on or must preserve:
  - `make run-cloud` as the cloud Snowflake route.
  - `scripts/run_cloud_pipeline.sh`.
- Existing logic to reuse or extend:
  - Use cloud flow documentation instead of script-level local-file loading.
- Public contract or state/data change:
  - Removes a manual script that bypasses the intended S3-stage cloud route.
- Depends on: Task 1.
- Likely files/modules:
  - `scripts/load_snowflake.sh`
  - `docs/implementation/implementation_plan.md`
  - `docs/detailed/architecture.md`
- First command/check:
  - `rg -n "load_snowflake\\.sh|python -m pipelines\\.load\\.snowflake_loader" .`
- Change boundary:
  - Delete only the obsolete script and references to it.
- Verification command:
  - `rg -n "load_snowflake\\.sh|python -m pipelines\\.load\\.snowflake_loader" Makefile README.md docs scripts tests pipelines`
- Review focus:
  - No user-facing command should point to local-file Snowflake loading.
- Risk/rollback:
  - If docs rely on the script as a placeholder from the original spec, update docs to name `make run-cloud` instead.
- Stop/ask if:
  - The script is referenced by an external automation outside the repo. Current repo evidence does not show one.
- Status: completed

### Task 3: Trim Snowflake Loader Tests To The Cloud Path

- Outcome: tests assert S3-stage Snowflake loading behavior only.
- Builds on or must preserve:
  - S3-stage fake Snowflake tests.
  - Row-count reconciliation, metadata writes, failed validation, empty group, and mismatch checks for the active path where applicable.
- Existing logic to reuse or extend:
  - `tests/unit/test_snowflake_loader.py`
  - Existing fake Snowflake connection/writer/cursor utilities.
- Public contract or state/data change:
  - Test contract follows the new public contract: Snowflake raw load from S3.
- Depends on: Tasks 1-2.
- Likely files/modules:
  - `tests/unit/test_snowflake_loader.py`
- First command/check:
  - `rg -n "load_local_raw_extracts_to_snowflake_for_testing|load_raw_extracts_to_snowflake" tests/unit/test_snowflake_loader.py`
- Change boundary:
  - Remove tests for deleted functions.
  - Keep or add active-path tests if removal creates coverage gaps.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_snowflake_loader.py`
- Review focus:
  - Active S3 loader remains well covered after local-file tests are removed.
- Risk/rollback:
  - If a removed test covered a behavior not covered by S3 tests, port that assertion to an S3 loader test instead of keeping the old function.
- Stop/ask if:
  - The S3 loader lacks enough fake infrastructure to cover a behavior that previously mattered.
- Status: completed

### Task 4: Update Route Documentation

- Outcome: docs no longer say the local-file Snowflake loader remains available.
- Builds on or must preserve:
  - README local/cloud route ownership.
  - Existing cloud artifact handoff and two-route docs.
- Existing logic to reuse or extend:
  - The route-boundary wording already added in README and implementation docs.
- Public contract or state/data change:
  - Documentation-only.
- Depends on: Tasks 1-3.
- Likely files/modules:
  - `README.md`
  - `docs/implementation/local_cloud_route_plan.md`
  - `docs/implementation/raw_load_route_boundary_cleanup_plan.md`
  - `docs/implementation/two_route_safe_hard_switch_plan.md`
  - `docs/implementation/cloud_artifact_handoff_plan.md`
  - `docs/implementation/implementation_plan.md`
  - `docs/detailed/architecture.md`
- First command/check:
  - `rg -n "load_local_raw_extracts_to_snowflake_for_testing|load_raw_extracts_to_snowflake|local-file Snowflake|Python connector fallback|load_snowflake\\.sh" README.md docs`
- Change boundary:
  - Update docs only for the removed compatibility path.
- Verification command:
  - `git diff --check`
- Review focus:
  - Docs should teach one Snowflake route: S3-backed cloud loading.
- Risk/rollback:
  - Docs-only rollback is independent if wording overreaches.
- Stop/ask if:
  - Historical implementation plans should retain old wording for audit history. If so, add "superseded" notes instead of rewriting original plan statements.
- Status: completed

## Final Verification

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_snowflake_loader.py tests/unit/test_prefect_local_flow.py
.venv/bin/python -m pytest tests/integration/test_duckdb_loader.py tests/unit/test_s3_loader.py
rg -n "load_local_raw_extracts_to_snowflake_for_testing|load_raw_extracts_to_snowflake\\b|load_snowflake\\.sh|python_connector_fallback" pipelines tests scripts README.md docs --glob '!docs/implementation/remove_local_file_snowflake_loader_plan.md'
git diff --check
```

Optional, if the first checks pass and the diff touches broader docs/source than expected:

```bash
make test
```

## Open Questions

- Should historical plan docs be edited in place, or should they keep old wording with a superseded note? For implementation, prefer minimal edits that prevent future readers from following the removed path.
