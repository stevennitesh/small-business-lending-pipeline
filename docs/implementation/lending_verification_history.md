# Lending analysis: dated verification

Start with the [HTML reader report](https://stevennitesh.github.io/small-business-lending-pipeline/).
The [generated aggregate results](../detailed/analysis_results.md) provide supporting tables and charts.
This appendix records the
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

This section records the pre-update status on October 6; the October 11 entry
below records the subsequent local Desktop work.

The old binary and five screenshots used the June 2 inputs and contained known
aggregation errors. For that older population, the through-2025 average should
have been $341,563.04; the matched through-2023 average should have been
$327,311.61. Its 36.88% lender statistic pooled state/year memberships; the
selection-wide top five was 17.71%. These are historical corrections, not current
totals. [Current Desktop references](../../powerbi/README.md#desktop-selection-references)
use the refreshed sources.

At the October 6 review, the old files were preserved locally and excluded from
Git. Desktop correction, DAX/Power Query execution and new captures were still
pending. The October 11 entry supersedes that report status. Paid S3/Snowflake
execution remains deferred; source contracts and generated charts alone do not
certify Desktop or live cloud behavior.

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

## October 11 local Desktop update

The local editable report was refreshed in Power BI Desktop from the existing
18 checked CSVs, with 25 contract relationships and the exact 62 maintained DAX
expressions. All 24 actual engine checks passed: national/geography amounts and
record counts, known-amount averages, category-filter isolation, partial and
multiple-year growth guards, empty selection labels, selection-wide lender
concentration, paired financing ratios, partial period labels, the complete-year
trend filter, California's 2023 unemployment/entry/exit rates and unique shortened
sector labels. Source-contract validation remains
separate from this actual Desktop execution.

The seven pages cover lending scale, state differences, reporting lender names,
programs/industries, lending relative to employer locations, state business
conditions and source checks. Lending defaults to 2025; matched comparisons use
2023; business conditions default to California/2023 and use the regional table's
1990–2023 coverage. Source checks retain the frozen October 5 evidence. No source
download, warehouse rebuild or paid cloud execution was performed for this update.

The final `powerbi/lending_dashboard.pbix` was saved natively, closed and reopened
from its exact final path. All seven tabs and the correct opening 2025 headline
were visible. The acceptance query was rerun on the reopened binary: **24 rows,
all Pass = TRUE, 79.9 ms**. The binary is **10,365,698 bytes**, SHA256
`1D255AD1F6DE41B192E74CEC96A0815057C3D3B4664339ACC577E3CD1C5FF397`.

The latest single current set in `powerbi/screenshots/current/` contains seven
genuine page PNGs and `desktop_dax_checks.png`. Native Desktop PDF export produced
`lending_dashboard.pdf` there: **653,649 bytes**, seven pages confirmed with
`pypdf`, with more than 300 text characters per page and complete industry/lender
labels. The files remain local and ignored. Public report/capture publication
has not been requested. Historical screenshots have not become current evidence.

## October 11 saved-data and presentation review

A separate read-only check compared all **18 reporting CSVs / 253,942 rows**
with the saved DuckDB tables. Typed, bidirectional `EXCEPT ALL` comparisons found
**zero row differences**; column order, retained CSV hashes, row counts and unique
grains also matched. The supported WSL DuckDB 1.5.2 runtime performed this check.
No source download or warehouse rebuild was needed.

Independent decimal calculations reproduced the 2025 headline: **$40,926,844,800**,
**74,098 records**, a **$552,334.000918** mean, **+1.7071%** dollars and **−8.6124%**
records from 2024. Program, known-sector and known-name totals reconciled with
their stated denominators. All 51 geography rows used matched 2023 context;
California led dollars and Ohio led records per 1,000 employer locations.

The six charts were regenerated from those same checked CSVs with clearer labels
and spacing. The HTML report was rebuilt from their public aggregate evidence.
These checks verify saved-data consistency; publisher evidence remains frozen at
October 5. No dbt rebuild, new publisher verification or paid cloud execution was
performed.

The rendered HTML was inspected at desktop width and a 390-pixel mobile viewport.
All six figures, section navigation, chart enlargement, fit/close controls and
inline exact JSON were checked. The 25 targeted analysis/HTML tests and 157 local
links across 19 Markdown files passed. The in-app browser did not confirm file
download completion; embedded JSON payloads passed the offline report tests, and
the same values can be inspected inline. The HTML and its provenance total
327,923 bytes. No report publication was performed.

## Reproduce the checks

Use `make ci-check` for the supported runtime/source-contract gate. After an
authorized data refresh, run `scripts/verify_powerbi_readiness.py`, then
`scripts/render_analysis_report.py` against the matching readiness summary.
The [runtime guide](../detailed/orchestration_runtime.md) gives commands and
preservation rules. The [engineering decisions](../detailed/design_decisions.md)
preserve the historical benchmarks and rejected trials from retired task plans.
