# Runtime and orchestration

Use Linux/WSL, Python 3.12 and Make, or Docker. Power BI Desktop remains a manual
Windows artifact. Shell files are LF-terminated through `.gitattributes`.
`make install PYTHON=python3.12` manages `.venv`. Prefect 3.6.29 requires the
pinned FastAPI 0.136.3: newer 0.137+ routing breaks its ephemeral API
([upstream compatibility report](https://github.com/PrefectHQ/prefect/issues/22398)); `make ci-check` is the local,
Docker and GitHub Actions gate. `docker compose run --rm pipeline` runs that gate.

## Routes and outputs

The Prefect CLI supports exactly `--run-mode local` or `cloud`, and fixture/live
extraction. Local flow stages initialize → extract → collect manifests → validate
raw → load DuckDB → dbt build → collect dbt artifacts → validate BI → export CSVs
→ write final run summary. Cloud uses S3 artifact storage, uploads validation,
loads Snowflake through S3, runs dbt against Snowflake, uploads dbt artifacts and
validates BI before writing completion. Failures retain a final failure summary,
failed stage, error and completed-stage/timing evidence. Setup rejects mismatched
route/target pairs (`local`/`dev_duckdb`, `cloud`/`prod_snowflake`), a reused run ID
with existing evidence, and a fixture destination containing live or unidentified
warehouse inputs before writing run directories. Setup refusals preserve existing
evidence; failures after initialization write the new run's failure summary.

`data/raw`, `data/manifests`, `data/validation`, `data/warehouse` and `data/exports`
are generated and ignored. Final status is in
`data/validation/pipeline_run_id=<id>/run_summary.json`. Raw load metadata is not
that final summary; BI explicitly reports unknown same-pass completion. Freshness
has a separate checked-at timestamp and configurable ages.

Each successful build preserves both `manifest.json` and `run_results.json` under
`data/validation/pipeline_run_id=<id>/dbt_artifacts/`, with bounded local history.
Summaries reference these copies and a compact `dbt_artifact_receipt.json`.
The cloud route uploads the current pair using the existing run partition.
Shared `dbt/target` is working output and may be overwritten by compile/build/test
commands. Use a fresh run ID for each execution to preserve distinct evidence.
Pruned run paths are historical references; their receipts identify that full
files are no longer retained. Older summaries pointing to shared target files
cannot certify their original build after replacement; receipts do not reconstruct
missing original files.

## Safe local proof

```bash
make install PYTHON=python3.12
make ci-check
scripts/run_local_pipeline.sh --extract-mode fixture \
  --data-root .tmp/demo/data --duckdb-path .tmp/demo/warehouse.duckdb \
  --dbt-profiles-dir .tmp/demo/profiles --powerbi-export-dir .tmp/demo/exports
```

The fixture command isolates all data/export/profile paths. The generated dbt
`target` and logs remain ignored. `make run-local-fixture` uses normal live-output
paths by default; setup refuses a saved live or unidentified warehouse. Use the
isolated command for verification.
`make run-local-live` downloads full public inputs and refreshes local outputs.
Neither is part of CI. No cloud work or live extract is needed for ordinary checks.

Source refresh is manual; rebuilding charts or derived tables does not download
data. Before `make run-local-live`, check publisher releases and update the dated
coverage policy only with release evidence. SBA FOIA is quarterly; LAUS is monthly;
BDS is normally released annually around September, roughly two years after its
reference year. For BDS update `reporting_policy.census_bds_release` only after
checking the official release/API; verification expires after 90 days, separately
from its 400-day extraction limit. Rechecking the release page does not require
re-downloading an unchanged full source snapshot. Afterward run readiness,
retain its small summary with that run, then regenerate charts and reconcile the
current reading material. A new extract does not make a partial year complete or
make the latest published Census observations younger. Refresh replaces active
derived outputs without archiving per-run warehouse or CSV copies.

The October 5 refresh encountered source-format changes after live extraction.
It resumed through the existing local adapters from retained bytes after fixes;
the original failed summary and recovery note are preserved. The ordinary CLI
still rejects reused evidence IDs; this repair was not a new general resume command.

Refresh only derived outputs from an already loaded preserved snapshot:

```bash
make powerbi-refresh-local
.venv/bin/python scripts/verify_powerbi_readiness.py
```

The first command updates modeled warehouse/18 CSVs without extraction or raw
reload. The second reads them, checks CSV schema/type/grain/references and
independent raw/fact/component totals, and writes small aggregate proof to
`.tmp/pre-pbix/readiness.json`. It does not modify the warehouse or certify Desktop.
[Power BI handoff](../../powerbi/README.md) owns dated selections, age/completion
labels and the six-page plan. Paid Snowflake execution is deferred; the implemented
route remains available.

`make dbt-local` compiles with the local profile. `make dbt-build-local-fast` runs
seed/run and critical tests; `make dbt-build-local-full` is an explicitly heavier
full data build. For copied-warehouse verification, use an isolated profile and
`DBT_PROFILES_DIR` with `scripts/run_dbt_local.sh`. Check WSL memory headroom before
large builds. Do not assume the fixture demonstrates a complete publisher year.

## Reader report and chart generation

The optional presentation command reads existing checked local CSVs. It does not
extract sources, rebuild a warehouse, change exports or edit the PBIX. Run it with
Python 3.12 and **Matplotlib 3.10.8** available in an optional plotting environment;
Matplotlib is not required by the pipeline or `make ci-check`.

```bash
python scripts/render_analysis_report.py \
  --readiness .tmp/pre-pbix/readiness.json
```

Run readiness after each intentional data refresh. To reproduce a retained proof,
use its matching `data/validation/pipeline_run_id=<id>/readiness_summary.json`. The chart generator refuses CSV bytes
that differ from that evidence. Choose complete periods with `--lending-year`,
`--context-year` and `--start-year`; incomplete years or changed state populations
are rejected. Outputs are six small `docs/images/lending_*.svg` files,
`docs/images/lending_analysis.json`, `docs/detailed/analysis_results.md`, and
`docs/images/lending_verification.json`. The compact public verification summary
whitelists aggregate checks: it separates the prior readiness pass from the six
CSV hashes/row counts and category reconciliation checked by the renderer.
It hashes the eight report outputs and generator using UTF-8 text with LF line
endings; CSV input hashes retain exact-byte meaning. It contains no raw records,
private tracing evidence or machine paths, and does not certify Desktop or cloud.
These intentionally versioned public aggregates are different from ignored bulk
CSV/warehouse outputs. Exact amounts use decimal arithmetic; plotting converts
only final aggregates to floats. SVG text remains editable and carries accessibility
titles/descriptions. Optional local PNG previews are verification scratch output.

Do not use the ordinary refresh command merely to redraw charts. After a deliberate
source change, update the dated coverage policy, verify exports and review chart
interpretation and source-status labels together. Current defaults are 2025 lending
and 2023 complete business/labor context. The
[report vocabulary](../../powerbi/report_reader_guide.md) preserves ordinary labels
while leaving machine fields and measures stable.

## Command scope

The [Makefile](../../Makefile) owns target definitions; this table identifies their
purpose and effects. Use the smallest check that establishes the changed behavior.

| Command | Scope / effect |
|---|---|
| `make install PYTHON=python3.12` | Creates/updates the local `.venv` from `requirements.txt` |
| `make ci-check` | Runtime imports, pytest, dbt compile, Power BI contract, Ruff lint/format; no source refresh or cloud job |
| `make test`, `make lint`, `make format-check` | Focused runtime-quality entry points; `make format` modifies Python formatting |
| `make dbt-local` | Compile only; alias for `dbt-compile-local` |
| `make dbt-seed-local` | Loads reference seeds into the configured local warehouse |
| `make dbt-build-local-fast` | Seeds, runs models and tests critical data contracts against the existing warehouse |
| `make dbt-build-local-full` | Full dbt build against existing raw inputs; no extraction, but may use substantial memory/time |
| `make powerbi-refresh-local` | Fast dbt build, CSV export and source-model check; modifies modeled warehouse/exports |
| `make powerbi-model-check` | Checks the versioned model/DAX handoff, not the PBIX or an actual DAX engine |
| `make run-local` / `make run-local-fixture` | Full fixture flow using normal `data/` output paths; use the isolated command above to preserve live outputs |
| `make run-local-live` | Downloads public data, validates/loads/builds and refreshes local exports |
| `make run-cloud` | Executes the configured S3/Snowflake route; requires credentials and performs cloud writes |
| `make benchmark-local COMMAND="make dbt-local"` | Executes the supplied command and records timing/resource evidence in `.tmp/benchmarks/`; its effects follow that command |

Configuration, reference mappings, validation thresholds and coverage/freshness
policy live in `config/`. Keep source-specific extraction contracts separate from
shared artifact utilities. Do not replace dated policy evidence with assumptions
from a fixture or a sparse extract.

## Configuration and cloud

Local and cloud flow dbt calls use `pipelines.utils.reporting_policy.dbt_policy_vars`.
The local shell wrapper does the same. For a direct dbt command, produce the same
vars with `.venv/bin/python -m pipelines.utils.reporting_policy` and pass JSON to
`--vars`; do not invent a second policy in `dbt_project.yml`.

`.env.example` lists supported inputs. Cloud requires `S3_BUCKET`, Snowflake
account/user/password/role/warehouse/database/schema and
`SNOWFLAKE_STORAGE_INTEGRATION`. `DBT_SCHEMA_PREFIX` can isolate smoke schemas;
`SNOWFLAKE_BI_SCHEMA` can explicitly select the BI schema. `PREFECT_HOME` defaults
to `.tmp/prefect`; shell flows allow 120 seconds for cold ephemeral-server startup
(configurable with `PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS`). Temporary dbt profiles are written to `.tmp/dbt_profiles`.

`make run-cloud` performs live cloud work only with configured credentials and the
storage integration. S3/Snowflake remain supported, but this candidate has no new
live cloud proof. Never put credentials/account identifiers in public artifacts.
No monitoring schedule, retry service or new infrastructure is added.

## Generated data and cleanup

Raw extracts and retained manifests/validation are evidence; generated does not
mean disposable. Keep warehouse files, CSV exports, dbt artifacts and scratch/cache
outputs out of Git. `.tmp/` is ignored scratch space, not durable evidence storage.
The unfinished manual PBIX and screenshots are ignored and kept locally until
Desktop correction. Do not edit or publish them without the user's explicit request.

### Storage policy

- Keep one compact, ignored `.local-recovery/` Git bundle when intentionally
  rewriting public history. It preserves the former refs and files without copying
  raw inputs, warehouses or exports. This is a manual recovery backup, not a
  recurring run archive. Verify it before rewriting; retain it locally until the
  new public state is checked and the owner decides it is no longer needed.
- Keep the active warehouse, current BI exports and raw snapshots needed to
  reproduce the showcased findings. Large warehouses and exports are working
  data, not per-run history. Do not auto-delete selected raw inputs.
- Verification copies are temporary. Use isolated fixture paths or one isolated
  saved-data copy when needed, record small findings/counts/checks, then remove
  derived warehouses and BI CSVs after verification. Do not archive those copies.
- Retain compact run summaries, raw manifests/checksums, validation results and
  dbt receipts. A receipt contains artifact SHA256/bytes, invocation ID and
  result-status counts; it reports whether full files were pruned.
- Keep at most the **latest three local dbt artifact pairs**, within a combined
  **20 MiB budget per data root**. A byte limit may retain fewer than three.
  Collection automatically expires older pairs, preserving their receipts and
  summaries. A single pair above 20 MiB fails collection before copying; it cannot
  bypass the limit. Constants and enforcement live in
  [`pipelines/storage/dbt_artifacts.py`](../../pipelines/storage/dbt_artifacts.py).
- This bounds local copies for both local and cloud runners. It does not apply
  remote S3 deletions or change raw-data custody. Existing cloud uploads remain
  supported; no live cloud cleanup is performed by a local command.

For completed verification folders, preview then apply the same explicit scope:

```bash
.venv/bin/python scripts/cleanup_local_data.py --dry-run --verification-dir .tmp/demo
.venv/bin/python scripts/cleanup_local_data.py --apply --verification-dir .tmp/demo
```

Repeat `--verification-dir` for several completed folders. This scope removes only
copied `.duckdb`/WAL/temporary files and named BI CSV exports inside those `.tmp`
folders. It also expires full dbt pairs in their run validation directories,
retaining compact artifact receipts rather than accumulating full evidence across
many scratch roots. It preserves small findings, profiles, fixture raw inputs,
raw manifests, validation, logs and run summaries. A dated cleanup receipt with
file sizes/hashes and planned/completed status is written under `data/validation/`. It does not select active `data/` outputs.
Unrelated scratch files and registered worktrees are outside this scope.

To preview/apply the history policy to existing normal run directories:

```bash
.venv/bin/python scripts/cleanup_local_data.py --dry-run --run-evidence-only
.venv/bin/python scripts/cleanup_local_data.py --apply --run-evidence-only
```

Default cleanup is limited to rebuildable DuckDB temporary storage and dbt
working targets/logs; it preserves **every raw run**. Preview with
`make cleanup-local-data-dry-run`; `make cleanup-local-data` applies that selection.
Explicit raw-run pruning is a separate opt-in: `--keep-pipeline-run-id` removes
other SBA raw runs, so inspect all retained manifests and selected inputs first.
The selector cannot preserve several needed raw runs. For an authorized raw prune,
replace `RETAINED_RUN_ID` with its actual identifier in both commands:

```bash
.venv/bin/python scripts/cleanup_local_data.py --dry-run --keep-pipeline-run-id 'RETAINED_RUN_ID'
.venv/bin/python scripts/cleanup_local_data.py --apply --keep-pipeline-run-id 'RETAINED_RUN_ID'
```

Successful pytest scratch fixtures are discarded; only the most recent failed
session's temporary fixtures are retained (`pyproject.toml`). Compact logs and
proofs remain sufficient for successful verification, alongside the bounded dbt
receipts. Do not clean data as part of documentation
maintenance. Remove registered `.tmp/worktrees/` checkouts with `git worktree remove`
rather than deleting their directory.

[Architecture](architecture.md), [testing](testing_plan.md) and
[case study](case_study.md) provide further context and dated evidence.

## Maintaining publication evidence

Before changing source recency, verify the official publisher's latest reference
period and actual release date. Update the dated reporting policy and its URLs;
leave unconfirmed publication dates and next schedules null. SBA coverage cutoffs
are not release dates. The publisher-review windows are local policies; a passed
schedule prompts a check without assuming publication occurred.

After a policy or source-audit model change, a targeted local build selecting
mart_pipeline_source_freshness and its downstream audit/BI models can update
recency without a raw reload. Use an explicit profile pointing to the intended
active warehouse, a fresh run-evidence directory and the normal bounded dbt
artifact retention. Export the 18 tables, verify readiness and regenerate reader
outputs from that matching proof. Keep raw source hashes and substantive totals
unchanged; do not copy the full warehouse just to retain a previous run.
