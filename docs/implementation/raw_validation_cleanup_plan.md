# Raw Validation Cleanup Plan

## Summary

Tighten the raw validation subsystem without changing the MVP contract. The local and cloud routes should continue to use the same validation rules and result schema, while route-specific storage details stay behind artifact readers and manifest references.

## Goals

- Preserve the current validation IDs, blocking behavior, manifest fields, and downstream handoff contract.
- Make S3-backed validation less wasteful by avoiding repeated reads of the same raw object during manifest checks.
- Keep local and cloud validation behavior integrated through the same code path.
- Rename raw source payload checks so the module name matches what the code actually does.
- Fix small stale/correctness issues found during review.

## Implementation Slices

### 1. Inspect Raw Artifacts Once Per Manifest Check

- Add a raw artifact inspection value object to the storage layer.
- Add `RawArtifactReader.inspect(...)` that reads a raw artifact once and returns existence, size, and checksum.
- Update `check_raw_manifest(...)` to use one inspection result for `RAW_001`, `RAW_002`, and `RAW_003`.
- Preserve the existing `exists`, `size_bytes`, `sha256`, and `read_text` convenience methods.

### 2. Fix Missing Manifest Check Identity

- When a manifest reference cannot be read, return `RAW_004 Manifest created` instead of incorrectly reusing `RAW_005`.
- Add a focused unit test for missing manifest references.

### 3. Consolidate Validation Output Writing

- Add one flow helper that writes validation results locally and, for cloud route, to the durable artifact location.
- Use that helper for the initial write, `RAW_009` self-check, and final rewrite.
- Preserve the local compatibility file and cloud S3 validation output.

### 4. Clarify Source Payload Checks

- Rename `pipelines/validation/schema_checks.py` to `pipelines/validation/source_payload_checks.py`.
- Update active imports and tests.
- Keep function names and behavior unchanged.

### 5. Reduce Handoff Leakage

- Add a small method on `ExtractionPaths` for selecting route-appropriate manifest references.
- Make SBA resource-to-source identity lookup use configured SBA resource names rather than a broad string-prefix rule.

## Deferred

- Do not remove `row_count_checks.py` or `freshness_checks.py` yet. They are underused in raw validation, but they still match the planned pipeline-health layer.
- Do not split local and cloud validation into separate implementations.
- Do not remove local validation output from cloud runs; it remains a local runner compatibility artifact.

## Verification

- `.venv/bin/python -m pytest tests/unit/test_raw_validation.py tests/unit/test_prefect_local_flow.py`
- `.venv/bin/python -m pytest tests/unit/test_t16_pytest_suite_contract.py`
- `git diff --check`
