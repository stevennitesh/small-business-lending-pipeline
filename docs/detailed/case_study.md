# Reader report and supporting evidence

**[Read Business lending, in context →](https://stevennitesh.github.io/small-business-lending-pipeline/)**

The HTML report is the main reading destination for recruiters and new readers.
It connects the business question, findings, author contribution, consequential
engineering decisions and evidence. The [offline copy](../../reports/portfolio/index.html)
contains the same story and charts. This page routes readers to the maintained
technical sources rather than maintaining another narrative.

## Engineering choices and proof

Read the report's [engineering section](https://stevennitesh.github.io/small-business-lending-pipeline/#engineering)
for the contribution and tradeoffs. The [design decisions](design_decisions.md)
retain the historical loader benchmark, its measurement limits and rejected
optimizations. The [methodology](kpi_definitions.md) owns metric populations,
denominators, periods and interpretation; the [testing guide](testing_plan.md)
explains how those contracts are checked.

## What the resulting analysis shows

The report follows approval activity over time, geographic comparisons, program
and industry composition, lender-name concentration and publication timelines.
The [generated aggregate results](analysis_results.md) supply tables and six
source charts as technical evidence. Exact values and input hashes are in the
[aggregate JSON](../images/lending_analysis.json).

## Presentation verification

The [public verification record](../images/lending_verification.json) separates
prior saved-data readiness from checks executed during chart generation.
The [HTML provenance](../../reports/portfolio/provenance.json) binds presentation
inputs and output; it does not prove a new data refresh. The
[dated verification appendix](../implementation/lending_verification_history.md)
owns recorded populations, checks and recovery limits.

Power BI Desktop correction and paid live cloud execution remain deferred. The
[Power BI handoff](../../powerbi/README.md) owns report status and manual work.

## Reproduce and inspect

The [runtime guide](orchestration_runtime.md#reader-report-and-chart-generation)
owns commands, dependencies, output paths and GitHub Pages publication. Rebuilding
the HTML needs only versioned public evidence. Exact chart regeneration requires
matching saved exports and readiness evidence; a fresh source download may contain
publisher revisions.

For implementation detail, use the [architecture](architecture.md),
[model grains](data_model.md) and [field dictionary](data_dictionary.md).
The [project README](../../README.md) is the concise repository introduction.
