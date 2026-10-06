# Lending analysis: dated verification

Start with the [case study](../detailed/case_study.md) and
[current results](../detailed/analysis_results.md). This appendix records the
population and scope of checks already performed. Counts are dated observations,
not hardcoded expectations for future runs.

## October 5, 2026 source refresh

The refresh downloaded nine configured public resources and validated eight data
snapshots. SBA covers October 1990–June 2026, Census 1990–2023 and BLS January
1989–August 2026. Calendar lending years 1991–2025 are complete. Census's March
reference stocks and calendar lending remain different observation windows.

Source-format changes interrupted the initial Prefect flow. Compatibility repairs
used the retained downloads through existing adapters; this was not an
uninterrupted Prefect pass. The retained final summary records success at
**2026-10-05T04:44:04.174915Z**. The real-data rebuild passed **52 models, four
seeds and 328 dbt data tests**. Same-build completion in BI tables remains unknown;
the separately dated final summary establishes that repaired refresh's completion.

## October 5 publication-timeline correction

The later correction reused the same source bytes and rebuilt four audit models.
It passed 19 affected data tests; it did not rerun the full warehouse suite.
Independent readiness matched **253,942 rows across 18 CSVs** to modeled tables,
checked **25 relationships**, and reconciled selected raw, fact and component totals.

At **2026-10-05T06:06:54.443163Z**, all eight resources matched their latest
verified published period. Census 2023 was published September 25, 2025; BLS
August 2026 was published September 18, 2026. SBA's June 30 cutoff is coverage,
not a confirmed publication date. Old reference age alone does not imply stale
inputs. Expired publisher checks require review. October 2025 unemployment was
not published; its missing rates stay unknown and comparable annual change is
suppressed.

The [public verification summary](../images/lending_verification.json) exposes
aggregate readiness counts and exact chart-input hashes. It distinguishes this
recorded readiness from the six-input checks performed during chart generation.
Full local evidence is retained with the publication-timeline run under the
ignored validation-data directory; it is not required to browse the findings.

## October 6 portfolio verification

The WSL Python 3.12 gate passed **464 pytest tests**, compiled **52 models, four
seeds and 332 declared data tests**, checked the **18-table / 25-relationship**
Power BI source contract, and passed lint/format checks. Compilation does not
execute those declared warehouse data tests. One existing FastAPI/Starlette
deprecation warning was nonfailing.

[Hosted CI](https://github.com/stevennitesh/small-business-lending-pipeline/actions/runs/37416881473)
passed for the pre-cleanup revision `d057c80`. Six generated charts were reviewed
at normal reading width. The nine small public outputs total about 117 KB;
repeat generation and their portable text hashes were checked. They include
aggregate evidence, not raw records or borrower identifiers.

## Withdrawn Power BI report

The old binary and five screenshots used the June 2 inputs and contained known
aggregation errors. For that older population, the through-2025 average should
have been $341,563.04; the matched through-2023 average should have been
$327,311.61. Its 36.88% lender statistic pooled state/year memberships; the
selection-wide top five was 17.71%. These are historical corrections, not current
totals. [Current Desktop references](../../powerbi/README.md#desktop-selection-references)
use the refreshed sources.

The old files are preserved locally and excluded from Git. Correcting the report,
executing its DAX/Power Query and capturing six genuine pages remain pending.
Paid S3/Snowflake execution is deferred. Neither Desktop nor current live cloud
behavior is certified by local code, generated charts or static source contracts.

## October 6 public repository cleanup

The cleanup consolidated old task plans into the engineering decision record and
removed outdated report artifacts from Git while preserving their local bytes.
The supported runtime gate passed again with 464 tests. The repaired read-only
readiness command checked all 18 tables and 25 relationships without requiring
or inspecting a PBIX. No source refresh or modeled-data rebuild was performed.

Repeat chart generation preserved analytical values and verified public hashes;
156 local documentation links and anchors passed. Reporting CSVs, the old report
files and the active warehouse were preserved. The original Git history has one
compact local recovery bundle; it contains no warehouse or export copies.

## Reproduce the checks

Use `make ci-check` for the supported runtime/source-contract gate. After an
authorized data refresh, run `scripts/verify_powerbi_readiness.py`, then
`scripts/render_analysis_report.py` against the matching readiness summary.
The [runtime guide](../detailed/orchestration_runtime.md) gives commands and
preservation rules. The [engineering decisions](../detailed/design_decisions.md)
preserve the historical benchmarks and rejected trials from retired task plans.
