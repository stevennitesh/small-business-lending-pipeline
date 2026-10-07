# Verification contracts

The standard lightweight gate is **`make ci-check`**, in Linux/WSL Python 3.12:
runtime imports → pytest → dbt compile → Power BI contract → Ruff lint/format.
GitHub Actions and Docker run the same gate. It does not refresh public sources,
use cloud credentials, launch Power BI Desktop or run a full live warehouse build.

## Choose verification for the change

| Change | Appropriate starting check |
|---|---|
| Documentation / agent reading paths | `git diff --check`, affected-owner review, local links and conditional routing; no full runtime gate required |
| Runtime or broad code change | `make ci-check` |
| Configuration | Parser/contract tests and required keys in the affected config files |
| Source extraction / raw validation | Relevant fixture tests; a controlled source smoke only when needed and within the task's scope |
| dbt SQL or schema | `make dbt-local` for compile; affected models/critical tests on isolated inputs for data behavior |
| Prefect wiring | Isolated fixture command from the [runtime guide](orchestration_runtime.md#safe-local-proof) |
| Power BI model / export contract | `make powerbi-model-check` and relevant `tests/unit/test_powerbi_*.py`; actual report checks in Desktop |
| Reader charts / aggregate report | Supported historical-year wording, derived geography scope, reader denominators and public-proof sanitization/line-ending portability in `tests/unit/test_analysis_report.py`; readiness-bound real generation, deterministic output comparison and rendered visual review; generator never refreshes sources or writes warehouse/exports |
| HTML portfolio presentation | `tests/unit/test_portfolio_report.py`: evidence-hash rejection before replacement, matching CSV/readiness/vocabulary proof, publication versus download-review reasons, escaped labels, supported annual changes, CRLF/LF repeatability, embedded charts/downloads, internal anchors and checked-in regeneration; rendered desktop/mobile review of layout, enlargement, disclosures and navigation. For publication, require successful checks and Pages deployment at the pushed revision, anonymous public access and served HTML/provenance hash agreement. |
| Saved real CSV readiness | After an authorized source or derived refresh, `.venv/bin/python scripts/verify_powerbi_readiness.py`; CSV schema/types/grains, relationship references, independent raw/fact/component reconciliation and aggregate SQL selection references. A PBIX is not required or inspected. |

A test/compile pass is evidence for that scope. Read the runtime guide before a
command that rebuilds a warehouse, replaces exports, refreshes live sources or
writes to cloud; fixture output must not replace a saved live warehouse.

## Meaningful checks

| Boundary | Proof |
|---|---|
| Source/storage validation | Fixture tests for malformed/valid payloads, manifests, checksums, accepted persisted artifacts and local/S3 readers; loaders reject empty or unrelated passing evidence |
| Latest snapshot | A failed newer manifest leaves one deterministic older passing snapshot selected |
| Input grain | Retained Census duplicate/malformed rows and per-year coverage gaps fail; BLS bad numeric values, mismatched month identities and duplicate observations fail visibly |
| Raw immutability | Local bytes/streams and S3 conditional writes refuse overwrite; standalone promotion keeps the declared source key |
| Local raw refresh | A later source/count or audit-write failure leaves all previous DuckDB source and audit tables intact |
| SBA release compatibility | Actual SQL accepts earlier month/day/year and ISO dates, rejects invalid dates; both programs load absent optional Subprogram as null while preserving source bytes |
| Lender names | Actual cleaning folds case/whitespace, keeps genuine names and maps literal UNKNOWN/empty names to missing |
| BLS missing markers | Only the policy-declared month with a matching identity and nonempty code-X footnote can use `-`; malformed, unfootnoted or undeclared values still fail |
| Calendar approval population | Missing calendar date remains missing despite fiscal year; state eligibility and historical statuses are preserved |
| Annual growth | Partial boundaries/gapped years suppress YoY; sparse fixtures cannot redefine configured publisher coverage; a prior-only state demonstrates why selected growth requires matching state sets in both years |
| BLS coverage | Observed/expected months, valid October 2025 publisher omission, Jan/Feb/Mar/May cannot hide absent April; omissions beyond YTD range do not reduce expectations; comparable changes use correct PP units |
| Monthly alignment | Same calendar-month prior-year join despite a missing observation |
| Amount coverage | Missing amounts stay in record volume but are excluded from mean denominators; zero amounts remain known, all-unknown groups have null means |
| 504 financing | Same known 504 records contribute both financing sums; unknown fields and 7(a) records cannot dilute the ratio; coverage is against all 504 records |
| 7(a) guarantee | Both sums use the same known 7(a) records; anomalous 504 guarantee values cannot enter the numerator; paired coverage is disclosed |
| Freshness | Fixed checked-at SQL tests distinguish a passed/selected snapshot missing a verified published period from normal publication lag; no wall-clock-dependent CI expectations |
| Publication recency | Old BDS reference age remains descriptive; only a missed verified published period is stale. SBA compares quarters (not the last approval day), BLS compares months; old downloads, expired checks and passed schedules prompt verification without assuming new availability. Unknown publication dates stay null; the health rollup agrees. |
| Aggregation meaning | Unequal groups distinguish sums-of-components from averages of ratios; selected lender totals differ from pooled state/year top-five |
| Matched intensity | Missing/zero establishment stock excludes both ratio components; handoff rejects an unfiltered approval numerator |
| Embedded runtime | ASGI health route proves the pinned FastAPI/Prefect routing interface without starting a service |
| Power Query handoff | Unique record fields and logical flag/date/timestamp typing; static proof because no M runtime is available |
| Power BI contract | Actual definitions, nonblank tooltip descriptions, additive-only patterns, table/column/measure dependencies, relationships and exact DAX handoff consistency; static selection-label checks distinguish empty, one, all and subsets while clearing the entire dimension |
| dbt data | Schema grain/range/reference tests and singular semantic reconciliation checks; critical tests provide fast data gates |
| SBA discovery | Published distribution anchors, nested titles, relative URLs and 7a/7(a) spelling resolve all seven resources; HTTP errors or unrelated HTML cannot become cached metadata; configured JSON discovery still works |
| dbt evidence | Both artifacts are required; later target writes cannot replace retained copies; the fourth run or byte-budget pressure expires old pairs while preserving hashes/counts and summaries; oversized pairs fail before copying |
| Verification cleanup | Explicit scratch scope selects derived databases/BI CSVs; active outputs and small evidence survive; all target bounds are checked before deletion |
| Cloud raw refresh | Each file maps its own header; exact-key COPY and all-source/audit candidates precede transactional publication; a late insert failure rolls back prior replacements |
| BI publication | CSV rename failures restore previous owned exports; cloud required/prohibited column checks reject nonempty but invalid tables |
| Runtime custody | Wrong adapter targets, reused evidence IDs and fixture-over-live destinations fail before writes |
| Negative components | Actual SBA staging SQL converts impossible negative terms/rates/jobs/financing/chargeoffs to unknown values |
| Orchestration | Complete isolated fixture flow with final summary, BI row counts and CSV exports |

`tests/unit/test_reporting_methodology.py` and `test_methodology_source_semantics.py` execute actual rendered dbt SQL on
adversarial small DuckDB populations. `test_powerbi_model_contract.py` rejects
broken references and plausible incorrect average-of-ratio definitions.
The code validator is deliberately limited to this repository's explicit DAX
patterns; it is not a DAX engine. Desktop selection/visual checks remain manual.

## Data and runtime gates

Use `make dbt-local` for lightweight compile. For real modeled-data verification,
run seed/run/critical tests against an isolated copy of a saved warehouse and
preserved validated raw inputs. Record small findings and remove copied
warehouses/BI CSVs after verification using the runtime guide's explicit scratch
cleanup. Never overwrite the saved active warehouse with fixture outputs. A full `dbt build` is heavier and requires deliberate live-data scope and
memory headroom. Generated dbt artifacts are ignored; record checks actually run
with their population/date and limits in the
[verification appendix](../implementation/lending_verification_history.md).

Successful pytest temporary fixtures are removed automatically; retain only the
most recent failed session's scratch fixtures. `test_correctness_audit.py` exercises
actual SQL on small populations and deliberate failure paths without large saved-
warehouse copies. Cloud connector SQL generation stays mocked; the DML rollback
regression executes the publication statements in DuckDB.

Keep cloud consumer tests mocked without credentials. A local pass cannot prove
S3 objects, Snowflake promotion, hosted CI or a corrected PBIX. Actual final flow
completion comes from its final summary; a passing raw load or dbt pass is not a
proxy. Report remaining publisher gaps and unavailable evidence explicitly.

Documentation changes require `git diff --check`, owner/link review and
reconciliation with code. Test repairs may retire superseded assertions (such as
"display-only DAX" or cadence-only age policy) while preserving behavioral
coverage. No extra production service or monitoring is needed.
