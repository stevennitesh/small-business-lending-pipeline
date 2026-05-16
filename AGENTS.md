# Agent Instructions

These instructions apply to the whole repository. Keep this file durable: update it only when the implementation workflow, repository conventions, or project constraints change. Do not use it as a progress log.

## Project Goal

Build the Small Business Lending Intelligence Pipeline as a local-first analytics engineering project:

- ingest public SBA, Census BDS, and BLS LAUS data;
- preserve raw extracts, manifests, checksums, row counts, and validation output;
- model trusted KPI tables with DuckDB, dbt, and later Snowflake;
- orchestrate the workflow with Prefect;
- expose modeled BI tables for Power BI;
- keep predictive ML, borrower credit scoring, and causal claims out of the MVP.

## Implementation Source Of Truth

Use GitHub issues as the implementation tracker. The issues created from `docs/implementation/implementation_plan.md` are the work queue.

Before starting implementation work:

1. Pick the next GitHub issue, usually lowest-numbered open issue unless the user chooses another.
2. Read the issue body and the matching task in `docs/implementation/implementation_plan.md`.
3. Check whether earlier phase issues create prerequisites or contracts.
4. Keep the issue scope narrow; do not pull future task work into the current task unless it is required to make the current acceptance criteria verifiable.

When finishing an issue:

1. Run the smallest meaningful verification commands after the final edit.
2. Commit and push the implementation.
3. Add a GitHub issue comment with real Markdown line breaks, the commit hash, checks run, remaining uncertainty, and any deliberate deferrals.
4. Close the issue only when its acceptance criteria are met or the user explicitly accepts a narrower result.

Use durable issue comments for decisions, blockers, and verification evidence. Do not use issue comments for noisy command dumps.

## Scratch And Cache Files

Use `.tmp/` for scratch files, generated issue bodies, temporary logs, local experiments, and command output that should not be committed.

Rules:

- `.tmp/` is disposable scratch space.
- Do not commit `.tmp/` contents.
- Do not use `.tmp/` for source files, tests, durable documentation, or configuration needed by the project.
- Clean up scratch files when they are no longer useful.

## Local Development Workflow

Prefer the local virtual environment managed by the Makefile:

```bash
make install
make test
```

The system Python environment may reject direct `python3 -m pip install -r requirements.txt` because of PEP 668. Use `.venv` through `make install` instead.

Keep the implementation local-first until the local pipeline is proven:

1. repository skeleton and runtime;
2. config and reference seeds;
3. local extraction;
4. raw validation;
5. DuckDB raw load;
6. dbt staging, marts, BI, and audit models;
7. pytest and dbt quality gates;
8. Prefect local orchestration;
9. Power BI prototype;
10. S3/Snowflake promotion.

## Scope Rules

- Keep KPI logic in dbt models, not Power BI.
- Power BI must consume modeled BI or mart tables, not raw source files.
- Raw files must be immutable and traceable through manifests.
- Reporting should use the latest successful validated snapshot, not unvalidated source output.
- Respect source grain: SBA can be loan/month/year, Census BDS is annual, and BLS LAUS is monthly.
- Do not hardcode credentials, live row-count expectations, or secrets.
- Avoid extra infrastructure before the local pipeline works.

## Coding Conventions

- Prefer simple Python modules with explicit inputs and outputs.
- Keep source-specific extractors separate from shared utilities.
- Add tests with the implementation slice that introduces behavior.
- Use config files for source settings, freshness rules, validation thresholds, and reference mappings.
- Keep generated local data, warehouse files, dbt artifacts, and Power BI binaries out of Git unless the user explicitly asks otherwise.

## Verification

Each implementation slice should end with verification appropriate to its scope. Examples:

- skeleton/runtime: `make install`, `make test`;
- config: parser tests and required-key checks;
- extractors: fixture-based tests plus a controlled source smoke check when appropriate;
- validation: focused tests for invalid and valid examples;
- dbt: prefer `make dbt-local`, which is the lightweight local dbt compile check; use `make dbt-build-local-full` only when an explicit full live-data DuckDB build is needed and WSL has enough memory headroom;
- orchestration: `make run-local`;
- documentation-only changes: `git diff --check` plus targeted review.

State clearly when a check is skipped, weak, blocked, or only partially covers the change.
