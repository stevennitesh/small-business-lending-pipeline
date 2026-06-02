# Plan: Structured Raw Validation Manifest Cleanup

## Goal

Finish the raw validation cleanup by making manifest loading itself part of the structured validation path. Missing or malformed manifest references should produce validation results and write `validation_results.json`, instead of escaping as incidental file, S3, or JSON errors before raw validation can report them.

## Non-goals

- Do not change validation result IDs except where a new narrowly scoped check is needed.
- Do not split local and cloud raw validation into separate implementations.
- Do not change raw artifact paths, manifest field names, source names, resource names, or downstream raw-load contracts.
- Do not remove local compatibility validation files from cloud runs.
- Do not redesign pipeline-health freshness logic in this slice.

## Constraints

- Preserve local and cloud route behavior for valid extraction outputs.
- Preserve existing `RAW_001` through `RAW_014` semantics.
- Continue blocking warehouse loading on fail-severity raw validation failures.
- Keep source-specific payload checks running only when the relevant manifest loaded successfully and the required resource is present.
- Leave the repo buildable after each task.

## Execution Mode

Execution mode: sequential.

## Baseline

- Working tree: raw validation cleanup is currently uncommitted; `powerbi/lending_dashboard.pbix` is unrelated user work and must stay untouched.
- Current behavior: `check_raw_manifest(...)` can report a missing manifest as `RAW_004`, but `validate_raw_outputs(...)` still preloads all manifests before running that check.
- Relevant files:
  - `pipelines/flows/lending_pipeline_flow.py`
  - `pipelines/validation/raw_manifest_artifact_validation.py`
  - source-specific payload check modules under `pipelines/validation/`
  - `pipelines/validation/validation_result.py`
  - `tests/unit/test_raw_validation_flow.py`
  - `tests/unit/test_raw_validation_manifest_failures.py`
  - `tests/unit/test_raw_artifact_manifest_checks.py`
  - `tests/unit/test_prefect_local_flow.py`
- Baseline commands:
  - `.venv/bin/python -m pytest tests/unit/test_raw_validation_flow.py tests/unit/test_raw_validation_manifest_failures.py tests/unit/test_raw_artifact_manifest_checks.py tests/unit/test_prefect_local_flow.py`
  - `make test`

## Acceptance Checks

- Missing local manifest reference in `validate_raw_outputs(...)` writes validation output containing a blocking `RAW_004` result and raises `ValidationFailedError`, not `FileNotFoundError`.
- Missing cloud/S3 manifest reference follows the same structured behavior when using artifact references.
- Malformed manifest JSON creates a structured blocking raw validation result and still writes validation output.
- Valid local and cloud fixture validation continue to pass.
- Source identity and source payload checks still run for successfully loaded manifests.
- No duplicate or parallel raw validation path is introduced.

## Issue List

1. [#64 Make raw validation manifest loading structured](https://github.com/stevennitesh/small-business-lending-pipeline/issues/64)
2. [#65 Cover raw validation missing and malformed manifest failures](https://github.com/stevennitesh/small-business-lending-pipeline/issues/65)
3. [#66 Reduce duplicate SBA raw readability reads](https://github.com/stevennitesh/small-business-lending-pipeline/issues/66)
4. [#67 Normalize raw validation threshold names](https://github.com/stevennitesh/small-business-lending-pipeline/issues/67)

## Tasks

### Task 1: Make Manifest Loading Structured

- Outcome: `validate_raw_outputs(...)` reads manifests through a helper that returns both loaded manifests and validation failures.
- Builds on or must preserve: `check_raw_manifest(...)`, `check_validation_output_created(...)`, `RawValidationOutput`, and current local/cloud artifact readers.
- Existing logic to reuse or extend: `read_artifact_text(...)`, `manifest_references_for_validation(...)`, `write_validation_output_with_self_check(...)`.
- Public contract or state/data change: missing or malformed manifests now produce validation JSON before blocking load.
- Depends on: current raw validation cleanup already adding `RAW_004` for standalone missing manifest checks.
- Likely files/modules:
  - `pipelines/flows/lending_pipeline_flow.py`
  - `pipelines/validation/raw_manifest_artifact_validation.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_raw_validation_flow.py tests/unit/test_raw_validation_manifest_failures.py tests/unit/test_raw_artifact_manifest_checks.py tests/unit/test_prefect_local_flow.py -q`
- Change boundary:
  - Do not touch raw load, extraction, dbt, or Power BI.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_raw_validation_flow.py tests/unit/test_raw_validation_manifest_failures.py tests/unit/test_raw_artifact_manifest_checks.py tests/unit/test_prefect_local_flow.py`
- Review focus:
  - The flow should not call `json.loads(read_artifact_text(...))` over all manifests before structured checks have a chance to run.
- Risk/rollback:
  - If the helper shape becomes too broad, keep it private to `lending_pipeline_flow.py` and only return `loaded_manifests` plus `validation_results`.
- Stop/ask if:
  - Handling malformed manifests requires changing the public validation result schema.
- Status: completed

### Task 2: Add Focused Flow Tests For Missing And Malformed Manifests

- Outcome: tests prove the flow writes validation output and raises `ValidationFailedError` for missing/malformed manifests.
- Builds on or must preserve: Task 1 structured manifest loading path.
- Existing logic to reuse or extend: fixture extraction setup in `tests/unit/test_prefect_local_flow.py`.
- Public contract or state/data change: none beyond structured failure behavior.
- Depends on: Task 1 implementation.
- Likely files/modules:
  - `tests/unit/test_prefect_local_flow.py`
  - `tests/unit/test_raw_validation_manifest_failures.py`
  - `tests/unit/test_raw_validation_failure_summary.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py -q`
- Change boundary:
  - Add tests for local missing manifest and malformed manifest. Add cloud missing manifest only if existing fake S3 helpers make it low-cost.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_raw_validation_manifest_failures.py tests/unit/test_raw_validation_failure_summary.py tests/unit/test_prefect_local_flow.py`
- Review focus:
  - Tests should assert validation output content, not only exception type.
- Risk/rollback:
  - If cloud fake setup gets noisy, keep the cloud check to the existing S3-backed fixture test and cover local structured failure directly.
- Stop/ask if:
  - The expected check ID for malformed JSON is unclear after implementation.
- Status: completed

### Task 3: Remove Duplicate SBA Readability Work Or Reuse Inspection Status

- Outcome: SBA required-resource readability no longer causes avoidable repeated raw artifact reads when `RAW_001` already checked the same artifact.
- Builds on or must preserve: Task 1 loaded-manifest flow and existing `SBA_RAW_001` / `SBA_RAW_002` results.
- Existing logic to reuse or extend: `RawArtifactReader.inspect(...)` and `check_sba_required_resources(...)`.
- Public contract or state/data change: no change to result IDs or pass/fail behavior for valid data.
- Depends on: Task 1, because structured manifest handling should be settled before tuning duplicate reads.
- Likely files/modules:
  - `pipelines/validation/sba_payload_checks.py`
  - `pipelines/storage/raw_artifacts.py`
  - `tests/unit/test_raw_validation_payload_checks.py`
  - `tests/unit/test_raw_validation_sources.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_raw_validation_payload_checks.py tests/unit/test_raw_validation_sources.py -q`
- Change boundary:
  - Do not remove SBA required-resource checks unless tests prove `RAW_001` fully covers the same caller-visible behavior.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_raw_validation_payload_checks.py tests/unit/test_raw_validation_sources.py tests/unit/test_prefect_local_flow.py`
- Review focus:
  - Preserve readable/missing resource reporting while reducing redundant storage reads.
- Risk/rollback:
  - If simplifying the readability check weakens diagnostics, keep the check and use shared inspection state instead.
- Stop/ask if:
  - Preserving `SBA_RAW_002` requires a broader raw-validation result aggregation redesign.
- Status: completed

### Task 4: Normalize Validation Threshold Names

- Outcome: Census and BLS validation threshold names match what the checks actually validate.
- Builds on or must preserve: current config validation tests and `raw_validation_sources.raw_validation_expectations(...)`.
- Existing logic to reuse or extend: `config/raw_validation_expectations.yml`, `ProjectConfig` validation, raw validation expectations.
- Public contract or state/data change: config keys may be renamed with backward-compatible support if needed.
- Depends on: Tasks 1-3 are independent of naming; this can be deferred if it risks widening the cleanup.
- Likely files/modules:
  - `config/raw_validation_expectations.yml`
  - `pipelines/utils/config.py`
  - `pipelines/flows/lending_pipeline_flow.py`
  - `tests/unit/test_config_policy_contracts.py`
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_config_policy_contracts.py -q`
- Change boundary:
  - Keep this to naming and usage only. Do not add new public-data thresholds.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_config_policy_contracts.py tests/unit/test_raw_validation_flow.py tests/unit/test_prefect_local_flow.py`
- Review focus:
  - `census_bds.expected_state_count` should describe state coverage directly.
  - BLS should rely on configured-series checks instead of a redundant state-count threshold.
- Risk/rollback:
  - If config compatibility gets noisy, defer this to a separate issue and keep structured manifest cleanup focused.
- Stop/ask if:
  - The desired external config key names should remain stable for documentation or recruiter demo scripts.
- Status: completed

## Final Verification

- `.venv/bin/python -m pytest tests/unit/test_raw_validation_flow.py tests/unit/test_raw_validation_sources.py tests/unit/test_raw_validation_manifest_failures.py tests/unit/test_raw_validation_output.py tests/unit/test_prefect_local_flow.py`
- `.venv/bin/python -m pytest tests/unit/test_config_policy_contracts.py tests/unit/test_t16_pytest_suite_contract.py`
- `make test`
- `git diff --check`

## Open Questions

- Should malformed manifest JSON reuse `RAW_004 Manifest created`, or should it get a new check ID such as `RAW_014 Manifest readable JSON`?
- Threshold renaming is tracked in #67.
