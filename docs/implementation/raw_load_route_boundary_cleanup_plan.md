# Plan: Clarify Raw Load Route Boundaries

## Goal

Finish the raw-load cleanup so local-only, cloud-only, and testing/compatibility paths are obvious in code, tests, docs, and run summaries.

The intended story should stay simple:

- Local route: local raw files, local manifests and validation JSON, DuckDB, dbt `dev_duckdb`, local BI exports.
- Cloud route: S3 raw payloads, S3 manifests and validation output, Snowflake S3-stage raw load, dbt `prod_snowflake`, Snowflake BI schema.
- Testing/compatibility helpers: local-to-S3 upload checks used only for smoke tests, fallback verification, and debugging.

## Non-goals

- Do not change the raw table schemas.
- Do not remove DuckDB, Snowflake, S3, dbt, or Prefect.
- Do not remove `run-final` or the `final` alias in this cleanup.
- Do not require live AWS or Snowflake credentials for default tests.
- Do not change Power BI contracts.

## Constraints

- Preserve current local and cloud behavior.
- Keep the work behavior-preserving unless a test reveals the current route labels are misleading.
- Keep compatibility/testing paths available, but label them as such.
- Do not touch local data files, generated warehouse files, or the Power BI `.pbix`.

## Execution Mode

Execution mode: sequential

Parallel groups:

- None. The cleanup touches shared flow names, tests, and docs, so sequential implementation is simpler and safer.

## Acceptance Checks

- Cloud stage names and run summaries no longer imply that the active cloud route uploads already-S3-backed raw artifacts.
- Local-file Snowflake loading remains available but is clearly named or wrapped as testing/compatibility behavior.
- Local-source-frame loading is named as local-only behavior.
- Tests assert the canonical cloud route names and preserve compatibility helpers.
- README and implementation docs explain local-only, cloud-only, and testing/compatibility ownership.
- Focused tests and whitespace checks pass.

## Baseline

- Working tree: currently has route-labeling edits plus the user-owned `powerbi/lending_dashboard.pbix` change.
- Current behavior:
- `CLOUD_FLOW_STAGES` includes `record_raw_artifact_locations`.
- `record_raw_artifact_locations(...)` either summarizes cloud artifact URIs or runs the legacy local-to-S3 upload helper.
  - `load_raw_extracts_to_snowflake_from_s3(...)` is the active cloud raw-load path.
- The local-file Snowflake testing/compatibility path has been removed.
- `raw_load_common.load_local_source_frame(...)` reads local raw files.
- Relevant source/tests/fixtures:
  - `pipelines/flows/lending_pipeline_flow.py`
  - `pipelines/load/raw_load_common.py`
  - `pipelines/load/duckdb_loader.py`
  - `pipelines/load/snowflake_loader.py`
  - `pipelines/load/s3_loader.py`
  - `tests/unit/test_prefect_local_flow.py`
  - `tests/unit/test_snowflake_loader.py`
  - `tests/integration/test_duckdb_loader.py`
  - `tests/unit/test_s3_loader.py`
  - `README.md`
  - `docs/implementation/local_cloud_route_plan.md`
- Baseline commands/checks:
  - `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py tests/unit/test_snowflake_loader.py tests/integration/test_duckdb_loader.py tests/unit/test_s3_loader.py`
  - `git diff --check`

## Tasks

### Task 1: Rename The Cloud Raw Artifact Summary Stage

- Outcome: the active cloud stage describes what it does now: record or summarize cloud raw artifact locations.
- Builds on or must preserve: current raw artifact summary behavior and `S3UploadSummary` output shape.
- Existing logic to reuse or extend:
  - `record_raw_artifact_locations(...)`
  - `upload_run_artifacts_to_s3(...)`
  - `CLOUD_FLOW_STAGES`
  - completed stage tracking in `lending_pipeline_flow(...)`
- Public contract or state/data change:
  - Run summaries will show a clearer stage name.
  - The compatibility local-to-S3 upload helper remains available.
- Depends on: none.
- Likely files/modules:
  - `pipelines/flows/lending_pipeline_flow.py`
  - `tests/unit/test_prefect_local_flow.py`
  - `README.md`
  - `docs/implementation/local_cloud_route_plan.md`
- First command/check:
  - `rg -n "record_raw_artifact_locations" pipelines tests docs README.md`
- Change boundary:
  - Rename the flow task and stage label only; do not change S3 upload behavior.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py tests/unit/test_s3_loader.py`
- Review focus:
  - No active cloud stage name should imply duplicate upload of artifacts already written to S3.
- Risk/rollback:
  - If external docs or scripts depend on the old stage string, keep a compatibility note in docs and avoid public CLI changes.
- Stop/ask if:
  - The old stage name is required by a saved demo artifact or external screenshot.
- Status: completed

### Task 2: Make Local-File Snowflake Loading Explicitly Test-Only In The Public API

- Outcome: superseded by the later removal cleanup; the production-style public path points to the S3-stage loader.
- Builds on or must preserve:
  - Existing unit tests around the S3-stage Snowflake loader.
- Existing logic to reuse or extend:
  - `load_raw_extracts_to_snowflake_from_s3(...)`
  - `tests/unit/test_snowflake_loader.py`
- Public contract or state/data change:
  - The local-file helper was removed in the follow-up cleanup.
- Depends on: Task 1.
- Likely files/modules:
  - `pipelines/load/snowflake_loader.py`
  - `tests/unit/test_snowflake_loader.py`
  - `README.md`
- First command/check:
  - `rg -n "load_raw_extracts_to_snowflake_from_s3" pipelines tests docs README.md`
- Change boundary:
  - Do not alter Snowflake loading semantics or table schemas.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_snowflake_loader.py`
- Review focus:
  - A reader should see the S3-stage loader as the Snowflake raw-load route.
- Risk/rollback:
  - If removal was too broad, restore from the previous commit.
- Stop/ask if:
  - A public command or recruiter demo intentionally uses local files to populate Snowflake as the main cloud story.
- Status: completed

### Task 3: Rename Local Raw Source-Frame Loading

- Outcome: shared raw-load helper names distinguish local file parsing from route-neutral manifest/validation parsing.
- Builds on or must preserve:
  - DuckDB raw load behavior.
  - Snowflake local-file testing/compatibility behavior.
  - Snowflake S3-stage loader not using local source-frame loading for cloud source tables.
- Existing logic to reuse or extend:
  - `raw_load_common.load_local_source_frame(...)`
  - `duckdb_loader.load_raw_extracts(...)`
  - S3-stage Snowflake loader.
- Public contract or state/data change:
  - Internal helper rename only.
- Depends on: Task 2.
- Likely files/modules:
  - `pipelines/load/raw_load_common.py`
  - `pipelines/load/duckdb_loader.py`
  - `pipelines/load/snowflake_loader.py`
  - `tests/integration/test_duckdb_loader.py`
  - `tests/unit/test_snowflake_loader.py`
- First command/check:
  - `rg -n "load_local_source_frame" pipelines tests`
- Change boundary:
  - Rename helper and update call sites; do not change parsing, metadata, or row-count reconciliation.
- Verification command:
  - `.venv/bin/python -m pytest tests/integration/test_duckdb_loader.py tests/unit/test_snowflake_loader.py`
- Review focus:
  - The local/cloud boundary should become clearer without adding a new abstraction.
- Risk/rollback:
  - Simple rename rollback if it creates unnecessary churn.
- Stop/ask if:
  - The helper is part of an external API outside this repo.
- Status: completed

### Task 4: Update Route Documentation And Final Cleanup Notes

- Outcome: docs and README match the final code names and clearly state what remains compatibility-only.
- Builds on or must preserve:
  - Existing README runtime route section.
  - Existing implementation plans explaining cloud artifact handoff.
- Existing logic to reuse or extend:
  - Route ownership wording already added to `README.md`.
  - `docs/implementation/local_cloud_route_plan.md`.
  - `docs/implementation/two_route_safe_hard_switch_plan.md`.
- Public contract or state/data change:
  - Documentation-only.
- Depends on: Tasks 1-3.
- Likely files/modules:
  - `README.md`
  - `docs/implementation/local_cloud_route_plan.md`
  - `docs/implementation/two_route_safe_hard_switch_plan.md`
  - this plan document, if task statuses are updated during execution.
- First command/check:
  - `rg -n "record_raw_artifact_locations|load_local_source_frame" README.md docs pipelines tests`
- Change boundary:
  - Update docs only for names/contracts changed in this cleanup.
- Verification command:
  - `git diff --check`
- Review focus:
  - Docs should not claim compatibility helpers are the active cloud route.
- Risk/rollback:
  - Docs-only changes can be reverted independently.
- Stop/ask if:
  - The user wants historical docs left untouched.
- Status: completed

## Final Verification

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py tests/unit/test_snowflake_loader.py tests/integration/test_duckdb_loader.py tests/unit/test_s3_loader.py
git diff --check
```

Optional, only if the implementation changes broader flow names or public route output:

```bash
.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py
make test
```

## Open Questions

- Resolved: new run summaries report `record_raw_artifact_locations`; the old stage string is not kept as an active cloud stage.
- Superseded: the local-file Snowflake helper and compatibility alias were removed in the follow-up cleanup.
