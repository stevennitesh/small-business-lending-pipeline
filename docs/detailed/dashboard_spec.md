# Dashboard specification

The report takes a reader through a question, evidence, interpretation and source
limits: overall change → geography → distributions → local business context →
source coverage. The [reader guide](../../powerbi/report_reader_guide.md) owns the
ready-to-apply titles, narration, labels and tooltips. Its vocabulary comes from
[report_language.json](../../powerbi/report_language.json) and measure display
metadata in the [model](../../powerbi/lending_dashboard_model.json).
[KPI methodology](kpi_definitions.md) owns metric populations and formulas;
the [Power BI handoff](../../powerbi/README.md) owns implementation and Desktop checks.

The table below defines the **planned six-page Desktop correction**, preserving
the acceptance page order. It is separate from the current static chart sequence
in the [reader guide](../../powerbi/report_reader_guide.md#follow-the-current-static-charts).

| Planned reader page title | Existing implementation page | Purpose | Default and interpretation |
|---|---|---|---|
| Lending at a glance | Executive Overview | Reported amounts, approval-record count, average known amount, full-year change and trend | 2025. Dollars and record counts are different signals. Include amount coverage. |
| How lending varies by state | State Lending Trends | Same-year state/region amounts, counts and comparable annual changes | 2025. Partial/gapped years and changing observed state populations cannot support a full-year change. |
| Reporting lender names | Lender Concentration | Known-name dollar ranking, overall top-five share and coverage | 2025. Rank after adding amounts across selected states/years. Names are source assignments, not resolved historical banks. |
| Programs and industries | Industry and Program Mix | Separate distribution panels with dollar/count shares and coverage | 2025. Program amounts have different bases; industry shares use known sectors. Category choices affect only their own panel. |
| Lending relative to local businesses | Regional Business Health | Same-year lending and employer-location counts, intensity and single-state labor context | 2023. Census counts include employers across sizes. Multiple years use establishment-years. No national/regional average of state unemployment rates. |
| Source coverage and data checks | Data Quality and Pipeline Health | Source periods, download/observation age, frozen UTC check, validation, loading and separately dated completion | No lending slicers. Validity is separate from recency and final completion. |

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
they do not replace the manual report's six-page Desktop acceptance.
Only five historical Power BI screenshots exist. The saved binary has known
average/concentration errors and needs refresh, measure replacement, labels and
a source-coverage page. Fresh genuine screenshots remain required before closing
the dashboard/evidence issues. Source-contract tests do not execute DAX or Power Query.

The October 5 source refresh rebuilt modeled outputs from current downloads and
checked 18 exports and 25 relationships. Keep its separately dated final completion
apart from the frozen publisher/download check and unknown same-build BI completion.
SBA now ends June 30, BLS August 31, and Census still ends in 2023.
Paid Snowflake execution is deferred for cost; the implemented route remains,
with no current live cloud certification.

## Desktop review checklist

- Apply the six reader titles, exact narration, selected periods, field labels and
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
- Label partial 1990/2026, the BLS October 2025 omission, Census March 12 references,
  source evaluation time and separately dated completion. Keep multi-state rate cards blank.
- Keep borrower identifiers/raw files off report surfaces. Reported jobs and
  economic context are descriptive, never causal claims.
- Save and export fresh report images only after genuine Desktop verification.

The source page leads with reference periods, actual publication dates, publisher
verification and download dates. Show the assessment reason and any announced
next release. Old reference age is descriptive, not a stale flag. Stale means a
known newer publication is missing; expired verification or download windows
require review. Unknown publication dates remain unconfirmed.
