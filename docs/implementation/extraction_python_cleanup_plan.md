# Plan: Clean Up Extraction Python Helpers

## Goal

Simplify the extraction Python subsystem by consolidating duplicated manifest/date helper code and removing small stale compatibility/test code, while preserving the current extraction contracts for SBA, Census BDS, and BLS LAUS.

## Non-goals

- Do not redesign local versus cloud route behavior.
- Do not merge SBA, Census, and BLS extractors into one generic extractor.
- Do not change raw artifact paths, manifest field names, source identity behavior, resource names, row-count semantics, checksum semantics, or downstream raw validation/load contracts.
- Do not remove source-specific `main()` CLI entry points in this cleanup unless a later review decides they are no longer supported.
- Do not touch Power BI files or generated local data.

## Constraints

- The working tree has an unrelated user-owned `powerbi/lending_dashboard.pbix` change; implementation must not stage or modify it.
- Extractors are directly used by the Prefect flow and their lower-level helpers are covered by unit tests.
- `pipelines/utils/config.py` imports extractor parse functions, so parser APIs must remain stable.
- The recent SBA streaming cleanup must be preserved.

## Execution Mode

Execution mode: sequential

Parallel groups: None

## GitHub Issues

- #60: Consolidate extraction manifest helper plumbing
- #61: Consolidate extraction ingestion-date parsing
- #62: Remove stale SBA resource-spec loader wrapper
- #63: Remove stale SBA streaming test monkeypatch

## Baseline

- Current extractor modules:
  - `pipelines/extract/sba_extract.py`
  - `pipelines/extract/census_bds_extract.py`
  - `pipelines/extract/bls_laus_extract.py`
  - `pipelines/extract/__init__.py`
- Current extraction tests pass:
  - `.venv/bin/python -m pytest tests/unit/test_sba_extract.py tests/unit/test_census_bds_extract.py tests/unit/test_bls_laus_extract.py` -> 29 passed.
- Current cleanup findings:
  - `_manifest_artifact_location(...)` is duplicated across all three extractors.
  - `_build_local_manifest_path(...)` is duplicated in shape across all three extractors.
  - `_ingestion_date_from_iso(...)` is duplicated across all three extractors.
  - `load_sba_resource_specs(...)` is old compatibility surface; current production config loading uses `load_sba_resources_config(...)` / `parse_sba_resources_config(...)`.
  - The SBA streaming test has a stale-looking monkeypatch for a removed `hash_bytes` import with `raising=False`.

## Acceptance Checks

- Duplicate manifest artifact location logic is consolidated into a shared helper.
- Duplicate local manifest path construction is consolidated without changing paths.
- Duplicate ingestion-date-from-ISO logic is removed or routed through one shared helper.
- `load_sba_resource_specs(...)` is removed if no production caller needs it, and tests use `load_sba_resources_config(...).resources`.
- The stale SBA streaming test monkeypatch is removed while preserving meaningful behavior assertions.
- Existing extractor tests and flow tests continue to pass.
- No unrelated files, generated data, or Power BI artifacts are staged or changed.

## Tasks

### Task 1: Consolidate Manifest Location And Path Helpers

- Outcome: Remove repeated manifest artifact/path helper implementations from extractor modules.
- Builds on or must preserve: current manifest JSON shape, local manifest paths, cloud manifest artifact URIs, and source identity behavior.
- Existing logic to reuse or extend:
  - `pipelines.utils.manifest`
  - existing extractor `_manifest_artifact_location(...)` implementations
  - existing extractor `_build_local_manifest_path(...)` implementations
- Public contract or state/data change: none intended.
- Depends on: None.
- Likely files/modules:
  - `pipelines/utils/manifest.py`
  - `pipelines/extract/sba_extract.py`
  - `pipelines/extract/census_bds_extract.py`
  - `pipelines/extract/bls_laus_extract.py`
  - affected unit tests only if they directly assert helper behavior
- Change boundary:
  - Add a shared helper for manifest artifact locations.
  - Add a shared helper for partitioned local manifest paths that accepts `data_root`, `source_system`, `ingestion_date`, `pipeline_run_id`, and manifest filename/resource identifier.
  - Replace extractor-private duplicates with calls to shared helpers.
  - Keep the actual path strings unchanged.
- First command/check:
  - `.venv/bin/python -m pytest tests/unit/test_sba_extract.py tests/unit/test_census_bds_extract.py tests/unit/test_bls_laus_extract.py`
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_sba_extract.py tests/unit/test_census_bds_extract.py tests/unit/test_bls_laus_extract.py tests/unit/test_prefect_local_flow.py`
  - `git diff --check`
- Review focus:
  - Exact manifest path and URI compatibility.
  - No new generic extractor abstraction.
- Risk/rollback:
  - Main risk is subtle path drift; rollback shared helper and restore private helper calls if path assertions fail.
- Stop/ask if:
  - Consolidation requires changing raw/manifest path conventions.
- Status: pending

### Task 2: Consolidate Ingestion Date Parsing

- Outcome: Remove duplicated `_ingestion_date_from_iso(...)` helpers from extractor modules.
- Builds on or must preserve: manifest `ingestion_date` values derived from `extracted_at_utc`.
- Existing logic to reuse or extend:
  - `pipelines.utils.dates.ingestion_date_from_timestamp`
  - extractor-local `_ingestion_date_from_iso(...)` logic
- Public contract or state/data change: none intended.
- Depends on: Task 1 only if shared helper imports are already being adjusted; otherwise independent.
- Likely files/modules:
  - `pipelines/utils/dates.py`
  - `pipelines/extract/sba_extract.py`
  - `pipelines/extract/census_bds_extract.py`
  - `pipelines/extract/bls_laus_extract.py`
- Change boundary:
  - Add a small utility such as `ingestion_date_from_iso_timestamp(...)`.
  - Replace extractor-local date helpers.
  - Remove now-unused extractor imports.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_sba_extract.py tests/unit/test_census_bds_extract.py tests/unit/test_bls_laus_extract.py`
  - `git diff --check`
- Review focus:
  - Timezone parsing remains equivalent for `Z` timestamps.
- Risk/rollback:
  - Date drift would affect partition paths; rollback if any manifest path assertions change unexpectedly.
- Stop/ask if:
  - The utility name creates confusion with existing date helpers.
- Status: pending

### Task 3: Remove SBA Resource-Spec Compatibility Wrapper

- Outcome: Delete the stale `load_sba_resource_specs(...)` wrapper and update tests to use the canonical config loader.
- Builds on or must preserve:
  - `load_sba_resources_config(...)`
  - `parse_sba_resources_config(...)`
  - production `ProjectConfig` loading through `pipelines/utils/config.py`
- Existing logic to reuse or extend: `load_sba_resources_config(...).resources`.
- Public contract or state/data change: narrow API cleanup; production behavior should not change.
- Depends on: None.
- Likely files/modules:
  - `pipelines/extract/sba_extract.py`
  - `tests/unit/test_sba_extract.py`
- Change boundary:
  - Remove `load_sba_resource_specs(...)`.
  - Replace test calls with `list(load_sba_resources_config(...).resources)`.
  - Search the repo before deletion to confirm no production caller remains.
- Verification command:
  - `rg -n "load_sba_resource_specs" . --glob '!data/**' --glob '!.tmp/**' --glob '!.venv/**'`
  - `.venv/bin/python -m pytest tests/unit/test_sba_extract.py`
  - `git diff --check`
- Review focus:
  - No production caller removal.
  - Test intent remains clear.
- Risk/rollback:
  - Low; restore wrapper if an external/manual workflow is discovered that depends on it.
- Stop/ask if:
  - Documentation or CLI examples present `load_sba_resource_specs(...)` as public API.
- Status: pending

### Task 4: Remove Stale SBA Streaming Test Monkeypatch

- Outcome: Make the SBA streaming regression test assert behavior directly without monkeypatching a removed symbol.
- Builds on or must preserve: Issue #59 streaming behavior and checksum/file-size assertions.
- Existing logic to reuse or extend:
  - `test_extract_sba_foia_profiles_chunked_csv_without_full_payload_hash`
- Public contract or state/data change: none.
- Depends on: None.
- Likely files/modules:
  - `tests/unit/test_sba_extract.py`
- Change boundary:
  - Remove the `sba_extract` module import if it becomes unused.
  - Remove the `monkeypatch` argument and stale `hash_bytes` monkeypatch.
  - Preserve assertions that prove chunked payload extraction, row count, column count, file size, checksum, and raw bytes.
- Verification command:
  - `.venv/bin/python -m pytest tests/unit/test_sba_extract.py -k chunked`
  - `.venv/bin/python -m pytest tests/unit/test_sba_extract.py`
  - `git diff --check`
- Review focus:
  - Test still protects the streaming behavior in a meaningful way.
- Risk/rollback:
  - Low; if the test becomes too weak, add a better fake response assertion instead of keeping a stale monkeypatch.
- Stop/ask if:
  - The team wants tests to assert absence of a specific implementation call rather than behavior.
- Status: pending

## Final Verification

- `.venv/bin/python -m pytest tests/unit/test_sba_extract.py tests/unit/test_census_bds_extract.py tests/unit/test_bls_laus_extract.py`
- `.venv/bin/python -m pytest tests/unit/test_prefect_local_flow.py`
- `make test`
- `git diff --check`
- `git status --short --branch` to confirm only intended files are changed and `powerbi/lending_dashboard.pbix` remains unstaged.

## Open Questions

- Should the standalone extractor `main()` functions remain supported as source-specific debug CLIs? Current recommendation: keep them for now.
- Should BLS normalized-row schema fields become an explicit constant in a separate cleanup? Current recommendation: yes, but treat it as a later raw-contract hardening slice, not part of this helper/deletion cleanup.
