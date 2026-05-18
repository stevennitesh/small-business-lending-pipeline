# Plan: Cloud-Backed Manifest And Validation Handoff

## Goal

Make the cloud route treat S3 and Snowflake as the durable system of record for cloud pipeline artifacts, not the local `data/` directory.

The target story:

- local route: local raw files, local manifests, local validation JSON, DuckDB, local Power BI exports;
- cloud route: S3 raw payloads, S3 manifests, S3 validation outputs, Snowflake raw and modeled tables.

Temporary local files are acceptable for execution mechanics, but cloud runs should not depend on durable local manifest or validation files after the artifact has been written to S3.

## Non-Goals

- Do not redesign source-specific extraction logic.
- Do not add new infrastructure such as Glue, Lambda, Step Functions, or Terraform.
- Do not remove the local route.
- Do not remove compatibility fields such as `local_raw_path` yet.
- Do not make default tests require AWS or Snowflake credentials.
- Do not change BI KPI logic or dbt model semantics.

## Current Baseline

The repo already has a useful route split:

- `local` writes raw payloads locally, validates them, loads DuckDB, runs dbt against DuckDB, and exports Power BI CSVs.
- `cloud` writes raw payloads to S3, validates S3-backed raw payloads, loads Snowflake from S3, and runs dbt against Snowflake.

The main remaining cloud-route ambiguity is the orchestration artifact handoff:

- extraction still writes manifest JSON files to local `data/manifests/...`;
- raw validation still writes `validation_results.json` to local `data/validation/...`;
- Snowflake raw load still receives local manifest paths and a local validation path, even though those files describe S3-backed raw payloads;
- the flow uploads manifest and validation files to S3 after validation, but S3 is not yet the first-class handoff location for those metadata artifacts.

## Target Architecture

### Local Route

```text
Public sources
  -> data/raw
  -> data/manifests
  -> data/validation
  -> DuckDB raw tables
  -> dbt dev_duckdb
  -> local Power BI exports
```

### Cloud Route

```text
Public sources
  -> S3 raw payloads
  -> S3 manifests
  -> S3 validation outputs
  -> Snowflake raw tables
  -> dbt prod_snowflake
  -> Snowflake BI tables
```

The cloud runner may keep temporary files in `.tmp/` while a task is executing, but the durable handoff between stages should be S3 object identity.

## Execution Mode

Execution mode: sequential.

This should be issue-driven implementation. Each task should become one GitHub issue and one focused commit. Push after each issue or after the full sequence, depending on the implementation session instruction.

## Acceptance Checks

- Cloud extraction writes raw payloads and manifests to S3 as durable artifacts.
- Cloud raw validation can read manifests from S3 and validate raw payloads from S3.
- Cloud validation results are written to S3 and can be loaded into Snowflake raw/audit tables from S3-backed identity.
- Cloud Snowflake load no longer requires durable local manifest or validation files.
- Local route behavior remains unchanged.
- Tests cover both local filesystem artifacts and cloud S3-backed artifacts with fake S3 clients.
- Live cloud route still reaches local/cloud BI parity after the change.

## GitHub Issues

1. [#54 Add cloud artifact store for manifests and validation results](https://github.com/stevennitesh/small-business-lending-pipeline/issues/54)
2. [#55 Make cloud extraction write manifests to S3](https://github.com/stevennitesh/small-business-lending-pipeline/issues/55)
3. [#56 Make raw validation use cloud artifact references](https://github.com/stevennitesh/small-business-lending-pipeline/issues/56)
4. [#57 Make Snowflake raw load consume cloud artifact references](https://github.com/stevennitesh/small-business-lending-pipeline/issues/57)
5. [#58 Document durable cloud artifacts in run summaries](https://github.com/stevennitesh/small-business-lending-pipeline/issues/58)

## Tasks

### Task 1: Add A General Artifact Store For Manifests And Validation Results

- Outcome: raw payloads, manifests, and validation outputs can all use a shared local-or-S3 artifact boundary.
- Builds on or must preserve: `LocalRawArtifactStore`, `S3RawArtifactStore`, `RawArtifactReader`, and existing manifest schema fields.
- Existing logic to reuse or extend: `pipelines/storage/raw_artifacts.py`, `pipelines/load/s3_loader.py`, and `pipelines/utils/paths.py`.
- Public contract or state/data change: introduce explicit artifact references for manifest and validation locations, without removing existing local `Path` support.
- Likely files/modules:
  - `pipelines/storage/raw_artifacts.py`
  - `pipelines/utils/paths.py`
  - `tests/unit/test_s3_loader.py`
  - new or existing storage tests
- Change boundary:
  - Add helpers/classes for non-raw artifact keys such as `manifests/...` and `validation/...`.
  - Do not change source extraction behavior yet.
- Verification command:

```bash
.venv/bin/python -m pytest tests/unit/test_s3_loader.py tests/unit/test_prefect_local_flow.py
```

- Review focus: the storage API should be small and route-neutral; no source-specific parsing should move into it.
- Risk/rollback: if the abstraction becomes broad, keep only narrowly named manifest/validation artifact helpers.
- Status: pending

### Task 2: Make Cloud Extraction Write Manifests To S3

- Outcome: in cloud mode, each extractor returns manifest references whose durable location is S3.
- Builds on or must preserve: Task 1 artifact boundary and current source-specific extractor behavior.
- Existing logic to reuse or extend:
  - `extract_sba_foia`
  - `extract_census_bds`
  - `extract_bls_laus`
  - `_raw_artifact_store`
  - `_extract_live_sources`
- Public contract or state/data change: extraction results need to carry manifest identity in a way downstream stages can read locally or from S3.
- Likely files/modules:
  - `pipelines/extract/sba_extract.py`
  - `pipelines/extract/census_bds_extract.py`
  - `pipelines/extract/bls_laus_extract.py`
  - `pipelines/flows/lending_pipeline_flow.py`
  - source extractor unit tests
- Change boundary:
  - Local mode continues writing manifests under `data/manifests/...`.
  - Cloud mode writes manifest JSON to S3 and may write a temporary local mirror only under `.tmp/` if a caller still needs a local file during the transition.
  - Preserve manifest content and raw resource naming.
- Verification command:

```bash
.venv/bin/python -m pytest tests/unit/test_sba_extract.py tests/unit/test_census_bds_extract.py tests/unit/test_bls_laus_extract.py tests/unit/test_prefect_local_flow.py
```

- Review focus: cloud extractor tests should prove manifests are S3-backed without hitting real AWS.
- Risk/rollback: if direct S3 manifest references create too much downstream churn, keep a transitional `ArtifactReference` that can materialize a local temp file for legacy consumers.
- Status: pending

### Task 3: Make Raw Validation Read And Write Cloud Artifacts Through References

- Outcome: cloud raw validation reads manifests from S3, validates S3 raw payloads, and writes validation results to S3.
- Builds on or must preserve: Task 2 manifest references and current raw validation checks.
- Existing logic to reuse or extend:
  - `validate_raw_outputs`
  - `check_raw_manifest`
  - `RawArtifactReader`
  - `write_validation_results`
- Public contract or state/data change: validation output should become a route-aware artifact reference rather than only a local `Path`.
- Likely files/modules:
  - `pipelines/flows/lending_pipeline_flow.py`
  - `pipelines/validation/raw_checks.py`
  - `pipelines/validation/validation_result.py`
  - raw validation unit tests
  - flow tests
- Change boundary:
  - Do not change validation check semantics.
  - Preserve `RAW_001` through `RAW_013` behavior.
  - Add route-aware artifact writing and reading around the existing checks.
- Verification command:

```bash
.venv/bin/python -m pytest tests/unit/test_raw_validation.py tests/unit/test_prefect_local_flow.py
```

- Review focus: missing S3 manifests or validation output should fail with structured validation or flow errors, not incidental `FileNotFoundError`/`KeyError`.
- Risk/rollback: keep local validation path as a compatibility output while making S3 the cloud durable output.
- Status: pending

### Task 4: Make Snowflake Raw Load Consume Cloud Artifact References

- Outcome: cloud Snowflake raw load no longer depends on durable local manifest or validation files.
- Builds on or must preserve: Task 3 S3 validation output and existing S3 raw payload loading.
- Existing logic to reuse or extend:
  - `load_raw_extracts_to_snowflake_from_s3`
  - `load_manifests`
  - `load_validation_results`
  - `RawArtifactReader`
- Public contract or state/data change: Snowflake load accepts manifest/validation artifact references, not only filesystem paths.
- Likely files/modules:
  - `pipelines/load/raw_load_common.py`
  - `pipelines/load/snowflake_loader.py`
  - `pipelines/flows/lending_pipeline_flow.py`
  - `tests/unit/test_snowflake_loader.py`
- Change boundary:
  - Leave the compatibility local-file Snowflake loader untouched unless a narrow adapter is required.
  - Do not change Snowflake table schemas except if an artifact URI field is already expected by current metadata contracts.
- Verification command:

```bash
.venv/bin/python -m pytest tests/unit/test_snowflake_loader.py tests/unit/test_prefect_local_flow.py
```

- Review focus: fake S3 tests should prove Snowflake loader reads manifests and validation JSON through cloud artifact references.
- Risk/rollback: introduce loader adapter functions first, then replace flow calls after tests pass.
- Status: pending

### Task 5: Update Run Summary And Documentation For Durable Cloud Artifacts

- Outcome: run summaries and docs clearly show where cloud raw payloads, manifests, validation results, dbt artifacts, and BI tables live.
- Builds on or must preserve: previous task artifact references and existing run summary schema.
- Existing logic to reuse or extend:
  - `write_run_summary`
  - `upload_dbt_artifacts_to_s3`
  - README route sections
  - implementation docs
- Public contract or state/data change: cloud run summary should include S3 artifact URIs for manifests and validation output.
- Likely files/modules:
  - `pipelines/flows/lending_pipeline_flow.py`
  - `README.md`
  - `docs/detailed/architecture.md`
  - tests for run summary or flow output
- Change boundary:
  - Documentation only describes implemented behavior.
  - Do not claim fully managed orchestration; the runner is still local/CLI-driven for MVP.
- Verification command:

```bash
.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py
git diff --check
```

- Review focus: wording should teach the correct cloud pattern: durable artifacts in S3/Snowflake, temporary execution state allowed on the runner.
- Risk/rollback: if summary schema change is noisy, add optional fields while preserving existing keys.
- Status: pending

## Final Verification

Run the focused test set first:

```bash
.venv/bin/python -m pytest tests/unit/test_s3_loader.py tests/unit/test_sba_extract.py tests/unit/test_census_bds_extract.py tests/unit/test_bls_laus_extract.py tests/unit/test_raw_validation.py tests/unit/test_snowflake_loader.py tests/unit/test_prefect_local_flow.py
```

Then run repo-level checks that fit WSL resource limits:

```bash
make test
make dbt-local
git diff --check
```

When credentials are available, run one cloud smoke or live verification:

```bash
scripts/run_cloud_pipeline.sh --extract-mode fixture --pipeline-run-id cloud-artifact-handoff-fixture
```

For final confidence after all tasks:

```bash
scripts/run_cloud_pipeline.sh --extract-mode live --pipeline-run-id cloud-artifact-handoff-live
```

Compare the resulting Snowflake BI outputs against the local route for the core executive totals before closing the full plan.

## Open Questions

- Should cloud validation results also be written into a Snowflake audit table before raw load, or is loading them during raw load enough for MVP?
- Should cloud manifests be loaded into Snowflake directly from S3 JSON, or should Python continue writing `RAW_INGESTION_MANIFEST` rows after reading S3 manifests?
- Should local temporary mirrors be allowed under `.tmp/` during cloud runs, or should tests enforce no local artifact files at all outside logs?
- Resolved: the active cloud stage is `record_raw_artifact_locations`; the local-to-S3 upload behavior remains a testing/compatibility helper.
