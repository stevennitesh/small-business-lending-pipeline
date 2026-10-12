# Dashboard specification

The report takes a reader through a question, evidence, interpretation and source
limits: overall change → geography → distributions → local business context →
source coverage. The [reader guide](../../powerbi/report_reader_guide.md) owns the
titles, narration, labels and tooltips. Its vocabulary comes from
[report_language.json](../../powerbi/report_language.json) and measure display
metadata in the [model](../../powerbi/lending_dashboard_model.json).
[KPI methodology](kpi_definitions.md) owns metric populations and formulas;
the [Power BI handoff](../../powerbi/README.md) owns implementation and Desktop checks.

The table below defines the **seven-page local Desktop story**. It is separate from the current static chart sequence
in the [reader guide](../../powerbi/report_reader_guide.md#follow-the-current-static-charts).

| Reader page title | Purpose | Default and interpretation |
|---|---|---|
| Lending at a glance | Reported amounts, approval-record count, mean known amount, coverage and full-year change | 2025. Dollars and record counts are different signals. |
| How lending varies by state | Ten leading states and full-year history | 2025. History excludes partial boundary years and retains all complete years when the year slicer changes. |
| Reporting lender names | Ten leading known names, overall top-five share and coverage | 2025. Rank after adding across selected geography/years; top-five denominator is not limited to the ten displayed names. Names are source assignments. |
| Programs and industries | Separate program and ten-sector distributions, category shares and coverage | 2025; initially 7(a) and Accommodation and food services. Category selections affect cards while charts retain the full mix. Program amount bases differ; unknown sectors remain visible where present. |
| Lending relative to local businesses | Same-year lending relative to employer-location counts | 2023 national; complete-context years 1991–2023. Census includes employers across sizes. Multiple years use establishment-years. |
| Local business conditions | State unemployment, change in percentage points, entry/exit rates and history | California, 2023; matched regional coverage 1990–2023. Cards require one state/year; histories retain that state's available years. |
| Source coverage and data checks | Reference/publication dates, publisher/download checks, validation, loading and separately dated completion | No lending slicers. Evidence is frozen October 5 UTC. Source-wide SBA cutoff repeats across archive resources; validity and final completion are separate. |

Every visual needs its selected calendar year/geography, unit, denominator and
source context. Dollars are nominal reported approval amounts: 7(a) whole loans
plus the SBA/Certified Development Company portion of 504. Records include
canceled/not-funded approvals and are not unique borrowers or disbursements.
Show a short explanation before exposing technical details in a tooltip.
Use **Approval records per 1,000 employer locations** for one year; add **per year**
for several years and explain annual stocks summed as establishment-years.

Use the corresponding semantic measures for cards and totals; do not sum or
average stored group ratios. Preserve dimension-based single-direction filters.
State/region/year reach supported lending tables. Program, industry and lender
choices apply only to their own distribution tables, without implying changes to
state/year headlines or optional descriptive pages.

## Current delivery and acceptance

The [reader report](analysis_results.md) supplies six real generated data charts
from checked saved local exports. They are independently useful public analysis;
they do not replace genuine Desktop evidence. On October 11 the local seven-page
report refreshed 18 imports, applied 62 maintained DAX expressions and retained
25 contract relationships. The final PBIX was saved natively, closed and reopened;
all 24 engine checks passed on that reopened binary. Seven genuine current page
captures and a seven-page native PDF were produced locally.
The old five screenshots remain historical.
The accepted delivery is the hosted/offline HTML report and this verified local
Desktop story. On October 11, the user retired public PBIX/capture publication and
paid live cloud verification as requirements; see the
[scope decision](design_decisions.md#october-11-2026-reader-delivery-scope).
The manual PBIX, PDF and captures remain local and ignored. Source-contract tests
do not certify the manual report, and retired cloud acceptance does not establish
live cloud verification.
The [handoff](../../powerbi/README.md#october-11-local-desktop-verification) owns final artifact status.

The October 5 source refresh rebuilt modeled outputs from current downloads and
checked 18 exports and 25 relationships. Keep its separately dated final completion
apart from the frozen publisher/download check and unknown same-build BI completion.
SBA now ends June 30, BLS August 31, and Census still ends in 2023.
Paid live S3/Snowflake verification is outside current acceptance; the implemented route remains,
with no current live cloud certification.

## Desktop review checklist

- Apply the seven reader titles, narration, selected periods, field labels and
  measure tooltips in the reader guide; keep internal identifiers and expressions.
- Check title labels for no selection, one value, all values and multiple subsets;
  a region subset must not read “All states”. These require actual Desktop checks.
- Start at 2025 for lending and 2023 for complete business context. Check one/many
  states, one/many years and categorical choices using the handoff's SQL references.
- Reconcile full-history means with valid-amount records: through 2025,
  $727,993,835,223.95 / 2,131,361 = $341,562.90. This is separate from the 2025
  annual average of $552,334.00 and 74,098 records.
- Reconcile selected overall lender top five after adding across geography/time;
  never present combined state/year top-five memberships as the overall ranking.
  The 2025 national known-name share is 20.93%; the saved full 1990–June 2026
  selection is 16.98%, including partial boundary years. Show coverage for each.
- Show unknown industries/names and amount coverage. Paired 504 financing uses
  the same known records on both sides and may exceed 100%; show its coverage.
- Label partial 1990/2026, the source-level BLS October 2025 omission, Census March 12 references,
  source evaluation time and separately dated completion. Keep multi-state rate cards blank.
- Keep conditions-page years within its actual 1990–2023 table; newer BLS source
  observations do not extend that matched view.
- Keep borrower identifiers/raw files off report surfaces. Reported jobs and
  economic context are descriptive, never causal claims.
- Save and export fresh report images only after genuine Desktop verification.

The source page leads with reference periods, actual publication dates, publisher
verification and download dates. Show the assessment reason and any announced
next release. Old reference age is descriptive, not a stale flag. Stale means a
known newer publication is missing; expired verification or download windows
require review. Unknown publication dates remain unconfirmed.
