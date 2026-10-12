# Power BI handoff

The report follows a simple story: how approval activity changes, where it is
concentrated, how it compares with local employer business locations, and what
programs, industries and lender names make up the total.
The [HTML reader report](https://stevennitesh.github.io/small-business-lending-pipeline/)
presents those findings, methods and engineering decisions in a browser,
independently of Desktop. A [self-contained offline copy](https://stevennitesh.github.io/small-business-lending-pipeline/offline.html) is included.
The [reader guide](report_reader_guide.md) distinguishes the current static charts
from the seven-page local Desktop story, questions, plain labels and tooltips.
The [current data report](../docs/detailed/analysis_results.md)
contains six reproducible charts from checked local exports; they are not PBIX screenshots. Version 3 local saved-data outputs were
rebuilt and checked on **October 4, 2026 local time (October 5 UTC)**. The saved
local Desktop report was refreshed, saved and reopened on **October 11, 2026**.
Its seven pages have genuine current captures and a Desktop-exported PDF.
Historical screenshots remain withdrawn. The public [seven-page gallery](https://stevennitesh.github.io/small-business-lending-pipeline/#desktop-gallery)
contains reviewed copies of the genuine October 11 captures. The editable PBIX and PDF remain local and ignored;
fresh clones contain the source handoff, generated charts and public capture copies. Paid Snowflake execution is deliberately
deferred; the implemented route and mocked checks do not certify current live cloud data.
Use the [dated Desktop verification](#october-11-local-desktop-verification) for the
binary identity, tested selections and local evidence. October 5 describes the
saved source/model build; October 11 describes the report refresh and native
engine checks. Opening the report does not update the frozen source evidence.

## Reader titles and narration

Follow the seven-page Desktop story in [the reader guide](report_reader_guide.md#local-power-bi-pages).
Use each existing measure's `display_name` and `description` in
[lending_dashboard_model.json](lending_dashboard_model.json) as the visual label
and tooltip; use [report_language.json](report_language.json) for axis/field labels
and source-status translations. Keep machine column and measure names unchanged.
The single-year intensity label is **Approval records per 1,000 employer locations**;
for several years use **Approval records per 1,000 employer locations per year**,
with the establishment-year explanation in its tooltip.

Add the selected calendar year and project geography to each lending visual.
Program share uses all-program amounts; industry share uses known-sector amounts;
lender top-five share uses known-name amounts after selection-wide aggregation.
Show each known-only share beside its coverage. The page narrative
separates the 2025 lending view from the 2023 business-context comparison.
These source files do not update the manual Power BI binary. The reader guide,
presentation metadata and dashboard specification describe the seven-page story;
dated artifact evidence establishes what was verified in Desktop.

## Local readiness and frozen snapshot

The October 5 source refresh downloaded all nine configured public resources,
validated the eight data snapshots, loaded the active DuckDB warehouse and rebuilt
52 models / four seeds. All 328 real-data dbt tests passed. All **253,942 rows
across 18 CSVs** matched their tables; schema, prohibited fields, unique grain,
types and all **25 relationships** passed independent readiness. Text keys retain
leading zeros. No paid Snowflake or Desktop execution was part of that October 5 check.

Selected snapshots belong to `local-refresh-20261005`; their raw checksums match
retained manifests. Current proof is `.tmp/pre-pbix/readiness.json` and its retained
copy `data/validation/pipeline_run_id=publication-timeline-check-20261005/readiness_summary.json`.
The original source-refresh proof remains dated history.
The [public verification summary](../docs/images/lending_verification.json)
exposes aggregate counts and input/output hashes without private tracing evidence.
It distinguishes recorded readiness from the generator's six-input checks.

| Selected resource | Source period / reference | SHA256 prefix |
|---|---|---|
| `sba_7a_fy1991_fy1999` | As of June 30, 2026; fiscal resource range | `05040efc4a43` |
| `sba_7a_fy2000_fy2009` | As of June 30, 2026; fiscal resource range | `66674e18a700` |
| `sba_7a_fy2010_fy2019` | As of June 30, 2026; fiscal resource range | `01a3e2c7988a` |
| `sba_7a_fy2020_present` | As of June 30, 2026; fiscal resource range | `6c1e9132b514` |
| `sba_504_fy1991_fy2009` | As of June 30, 2026; fiscal resource range | `acaaa3806186` |
| `sba_504_fy2010_present` | As of June 30, 2026; fiscal resource range | `8c0e15414217` |
| `bds_state_year` | 1990–2023; March 12 annual references | `f386ff0492bb` |
| `laus_state_month` | January 1989–August 2026; 51 missing October 2025 markers | `5993fbfe6375` |

SBA calendar coverage is October 1, 1990–June 30, 2026. Full years are 1991–2025;
use 2025 for lending and 2023 for matched complete context. At the frozen
UTC check time, all eight resources match their latest verified published
period and satisfy the download review window. Census reference year 2023 was
published September 25, 2025. BLS August 2026 was published September 18, 2026;
its next announced state release is October 20. SBA confirms coverage through
June 30 but not the actual publication date, which stays blank.

Show reference period, actual publication date, publisher check date, download
date, and recency assessment before descriptive observation ages. A verified newer
published period missing from the saved data is stale. Expired checks or an old
download require verification instead. Opening a report later does not update
the frozen evidence.

Raw validation passed and raw loading completed. Same-build `latest_run_status`
remains unknown. Separately, the retained final `run_summary.json` records success
at **2026-10-05T04:44:04.174915Z**. Live Prefect extraction initially failed validation; after
source compatibility repairs, execution resumed through existing local adapters
from the retained downloads. Its original failure and recovery note remain visible;
this is not an uninterrupted full Prefect pass. The subsequent Census policy
correction rebuilt only four audit models and passed 16 affected data tests; no
source files were downloaded or reloaded. Its separately dated completion is in
`data/validation/pipeline_run_id=census-release-check-20261005/derived_refresh_summary.json`.
No warehouse backup was retained.

## Reproduce or refresh the report in Desktop

1. Use checked local exports in `data/exports/powerbi`. If rebuilding is needed,
   run `make powerbi-refresh-local` in supported Linux/WSL Python 3.12, then
   `.venv/bin/python scripts/verify_powerbi_readiness.py`. Set Desktop `ExportRoot`
   to the absolute path of your checkout's `data/exports/powerbi` folder, for
   example `C:/projects/small-business-lending-pipeline/data/exports/powerbi`.
   The implemented cloud route uses the same policy; paid execution is deferred.
2. Open the locally preserved `lending_dashboard.pbix`, or create a new report
   from this handoff if using a fresh clone. Manual files are not included in Git.
   See the [screenshot status](screenshots/README.md) and dated Desktop evidence below.
3. Import all 18 modeled tables with [typed CSV queries](power_query/local_csv_queries.pq)
   or the contract's Snowflake BI sources. Set `ExportRoot` to the absolute export
   folder. Keys stay text to preserve leading zeros; components are numeric and
   coverage flags are logical. The `.pq` expression returns **one record containing
   18 tables**. Paste it into a blank query named `LocalCsvTables`, edit its
   `ExportRoot`, and keep that record query as connection-only. Create a blank
   query for each record field, for example `= LocalCsvTables[bi_executive_overview]`,
   named `bi_executive_overview`; repeat for all 18 names in the model contract.
   Enable load on the individual table queries, not on the record query.
4. Create the single-direction, one-to-many relationships in
   [the model contract](lending_dashboard_model.json). Use dimension columns for
   year/state/region/program/industry/lender slicers and categorical visual axes.
5. Create each measure block in [semantic_measures.dax](semantic_measures.dax).
   Apply each block's indicated format. Its exact expressions are versioned in the JSON and checked by
   `make powerbi-model-check`. Replace implicit sums/averages of ratio columns with
   these measures. Hide stored grain-level ratios from the field list where practical.
6. Check Comparable Full Year Dollar Growth with one selected year. It must return
   blank if either year's selected geography has an absent state-year row. For a
   test population with Alabama 100 → 110 and Alaska 900 → absent, Alabama alone
   is +10%; Alabama plus Alaska is blank. Missing Alaska activity is not zero.
   This selection guard compares both state sets while preserving geography filters.
7. Check selection titles: a single state/year shows its value; California +
   Texas shows “Multiple states”; 2024 + 2025 shows “Multiple years”. A region
   subset must not show “All states”. True all-dimension selections show “All”; an
   empty filter context shows “No states/years”. These are source-contract expectations;
   verify them in Desktop with the current measures.
8. Apply the seven-page defaults and filter scope below; check totals and selections, save in
   Desktop, then export fresh screenshots. A passing JSON check proves the handoff,
   not that the PBIX contains these definitions or that the DAX engine executed them.

CSV export generates the full set before publishing it. A publication error
restores the prior owned CSVs; unrelated CSVs are preserved, and only the known
legacy dimension exports are retired. Staging/rollback files are temporary and
are removed after the call. Cloud BI validation enforces required and prohibited
columns as well as nonempty tables; prohibited names are checked regardless of case.

Version 3 requires rebuilding local or cloud derived
models before consumption. Its ages are evaluated at `freshness_checked_at_utc`;
a frozen CSV/PBIX does not update freshness at viewing time.

Refresh all tables to import `approval_amount_coverage_count`, paired 504 financing
components, `bds_reference_date`, `observation_date_basis`, and program amount/role
labels. All Average Approval Size measures now divide by valid-amount record counts.
Show **Approval Amount Coverage** beside the headline average. Replace the old
**Third Party to Approval Ratio** measure/visual with **Known 504 Third Party to
SBA Amount Ratio** and **504 Paired Financing Coverage**; this ratio may exceed
100% because its denominator is the SBA/CDC portion on the same known 504 records.
The old mixed-program export ratio remains deprecated for existing consumers.
**7a Guarantee Rate** also uses paired known 7(a) records; show **7a Paired
Guarantee Coverage** beside it. Unknown amounts in either field do not dilute
either financing ratio.
Label combined amounts **Reported approval amounts (7(a) whole loan + 504 SBA/CDC)**,
and use program `approval_amount_basis` / `reporting_lender_role` in tooltips.
BDS context uses March 12 reference stocks and March-to-March flows, paired by
year with calendar lending; intensity is a contextual benchmark, not penetration.

| View | Default and measures | Supported filters and caveats |
|---|---|---|
| Lending at a glance | **2025**; Approval Dollars/Records, Average Approval Size, Approval Amount Coverage; Comparable Full Year Dollar Growth | State/region/year. Growth blank for multiple years, partial periods or missing prior populations. No synchronized category slicers. |
| How lending varies by state | **2025**, annual dollars/records and guarded growth; ten leading states | State/region/year. The history chart retains complete calendar years, independent of the year slicer. Cards label partial 1990/2026; no unmatched YTD growth. |
| Reporting lender names | **2025**; ten leading names, selected-name amounts; Selected Top Five Known Lender Share and Lender Dollar Coverage | State/region/year/lender. Top-five and coverage ignore the lender slicer. The displayed ten-name ranking does not restrict their denominator. |
| Programs and industries | **2025**, initially 7(a) and Accommodation and food services; separate program and ten-sector distributions, category-safe shares and coverage | State/region/year plus each panel's own category. Category slicers affect selected-category cards, while distribution charts retain the full mix. Industry ranking includes unknowns where present; known-sector share excludes them and coverage discloses the difference. |
| Lending relative to local businesses | **2023**, national; matched amounts, mean known amount, records per 1,000 employer locations and dollars per location | State/region/year; `is_comparable_context = true`, available years **1991–2023**. Multiple years mean establishment-years. |
| Local business conditions | **California, 2023**; mean monthly seasonally adjusted unemployment, change in percentage points, published business entry/exit rates and state history | Regional-context table covers **1990–2023**. Cards require one state and one year; histories retain that state's available years. No regional/national average of state rates. |
| Source coverage and data checks | Source reference periods/publication dates, publisher checks/downloads, assessment reason and validity; separately dated completion | No lending slicers. Same-build final status stays unknown; publication checks and dated final summary are separate facts. |

`Pooled State Year Top Five Share` is a separately labeled statistic for the sum
of state/year top-five dollars divided by selected known-lender dollars. It is
not the share of the five largest lenders in the entire selection.

Do not average state unemployment or BDS entry/exit rates into regional/national
rates. Display the monthly-SA mean and change in **percentage points** at a single
state/year, with observed/expected months, missing months and publisher omissions.
Use the guarded State Mean Monthly SA Unemployment Rate, State Unemployment Change PP,
and State Published Establishment Entry/Exit Rate measures; they return blank for
multiple states or years. The local conditions page stops in 2023. Separately,
the newer LAUS source/mart has an 11-month publisher exception in 2025 and
suppresses comparable YoY; that source coverage is not shown as a 2025 conditions card.
The old `unemployment_rate_yoy_change_pct` is retained only as a deprecated decimal
change for compatible consumers; new visuals use `_pp` (+1 means one percentage point).

The optional Performance, Status, Terms and Jobs tables retain their consumers.
Their handoff measures divide additive components under selection, including known
term/rate coverage. Jobs are reported source values, not measured jobs created.
No program/industry/lender cross-filtering is supported on these state-year tables.

Replace every old Average Approval Size family (headline, program, industry,
lender, matched context, performance, status, terms, jobs) with its exact v3 block.
Also replace old growth, overall lender concentration, industry-share/coverage,
intensity, unemployment change and financing definitions with
[semantic_measures.dax](semantic_measures.dax). Use guarded state-only BDS/LAUS
rate measures and retire implicit averages/sums of stored ratios. JSON versions
the exact expressions; source validation does not execute them. The October 11
Desktop check below records actual engine execution for the local report.

## Desktop selection references

Run `.venv/bin/python scripts/verify_powerbi_readiness.py` to reproduce
[desktop_reference.sql](desktop_reference.sql) results. Independent selected-raw,
fact and CSV components reconcile. These are October 5 refreshed-data expectations,
not hardcoded runtime thresholds or evidence that DAX executed.

| Selection / check | Expected result |
|---|---|
| State history through 2025 | $727,993,835,223.95; 2,131,362 records; 2,131,361 known amounts; average $341,562.90 |
| Matched history through 2023 | $646,827,096,023.95; 1,976,183 records; 1,976,182 known amounts; average $327,311.50 |
| Alabama, 2025 | $360,914,200; 562 records; average $642,196.09 |
| California + Texas, 2025 | $10,210,129,600; 15,547 records; average $656,726.67 |
| California + Texas, 2024–2025 | $20,081,584,000; 31,949 records; average $628,551.25; growth blank for multiple years |
| California + Texas, 2025; select 7(a) | Program dollars $7,996,992,600; share 78.3241%; headline remains $10,210,129,600 |
| Same geography/year; select sector 72 | Industry dollars $1,662,774,600; known-industry share 16.2855%; program panel unaffected |
| Known-sector page filter, history through 2025 | Industry coverage 92.9877%; disclose $51,048,916,381.25 unknown-sector dollars / 221,179 records |
| California + Texas, 2025; select largest known lender | Selected lender dollars $670,885,500; all-known top-five stays 20.4061%; coverage stays 100.0000% |
| Full saved 1990–June 2026, including partial years | Selected overall top five 16.9771%; pooled state/year 35.7013%; known-name denominator $743,975,134,717.95 |
| Full saved paired financing | 504 ratio 134.4534% over 217,193 / 227,044 records (95.6612% coverage); 7(a) ratio 74.1943% over 1,937,906 / 1,937,907 records |
| Missing current/prior row adversarial references | Alabama 100 → 110 gives +10%; add Alaska 900 → absent or absent → 900 and either two-state growth is blank |
| All-unknown amount adversarial reference | Two records, zero known amounts; average blank, not zero |

Check category selections within their own panels. Lender ranking and coverage
remove its filter; selected lender dollar cards retain it. LAUS 2025 has 11
observed/expected months, zero missing available months, one publisher omission and
blank comparable YoY. Its 51 explicit missing markers are null rates. LAUS 2026
has eight-month YTD coverage and blank YoY. Regional BI ends in 2023; later labor
guards are verified directly in the LAUS mart.

Only aggregate/field-map private tracing proof is retained. Both raw zero amounts
have unmapped geography and are excluded from state reporting; adversarial tests
verify mapped zeros count as known. One eligible negative 7(a) amount remains in
record volume but becomes unknown. Through 2025, unknown lender dollars are
$4,627,870,124.00 across 11,758 records;
known-name coverage is 99.3643%. In 2025 alone,
known names cover 100.00% of dollars in the refreshed release. Earlier missing
names were revised by the publisher; coverage does not prove resolved bank identity.

## October 11 local Desktop verification

The editable local report refreshed all **18 CSV tables**, retained **25 contract
relationships** and applied the exact **62 maintained DAX measures**. All **24
Desktop DAX checks passed**, covering national/geography totals, category-filter
isolation, known-amount averages, partial/multiple-year growth guards, empty
selection labels, selection-wide concentration, paired financing ratios, partial
period labels, the complete-year trend filter, California's 2023 economic rates
and unique shortened sector labels.
Display helpers format counts and label partial periods without changing those
62 expressions. No source download or warehouse rebuild was needed.

The final `powerbi/lending_dashboard.pbix` was saved natively, closed and reopened
from its exact final path. The reopened binary displayed all seven pages and the
2025 headline; all **24 DAX checks passed again**, in **79.9 ms**. Its file size is
**10,365,698 bytes** and SHA256 is
`1D255AD1F6DE41B192E74CEC96A0815057C3D3B4664339ACC577E3CD1C5FF397`.

The latest genuine captures are one current set in `powerbi/screenshots/current/`:
seven report-page PNGs and `desktop_dax_checks.png`. Native Desktop export produced
`lending_dashboard.pdf` there, **653,649 bytes / seven pages**; each page contains
readable report text, including the complete industry and lender labels. The
PBIX and PDF remain ignored and local. On October 12, the user approved publication of
the seven reviewed report-page PNG captures; aggregate-only copies are versioned in
`docs/images/powerbi/` and included in the public report gallery. The DAX-check screenshot remains local.
See the [dated verification appendix](../docs/implementation/lending_verification_history.md#october-11-local-desktop-update).

## Withdrawn historical report artifacts

The historical binary and five screenshots were withdrawn from Git.
They used the June 2 input population and contained the problems below. Use the
refreshed selection references above when maintaining the report; these old values
are retained only to identify mistakes that must not return.

| Artifact | Known issue or interpretation |
|---|---|
| Executive page | Old average $334.98K; same-population ratio is **$341.56K** through 2025. |
| Regional page | Old average $319.44K; same-population ratio is **$327.31K** through 2023. Multi-year intensity must say establishment-years. |
| Lender page | 36.88% pools state-year top-five memberships. Selected overall top five is **17.71%** for the saved 1990–March 2026 known-lender population, which includes partial boundary years. |
| Program page | Historical average $341.56K reconciles; the old screenshot did not establish correct measure/filter behavior. Current behavior has separate October 11 evidence. |
| Industry page | Known-industry denominator; disclose approximately **$51.05bn** unknown-industry dollars through 2025. |
| Historical PBIX | Used the earlier population and required refresh, measure replacement, labels and a source-check page. The current local update has separate dated evidence above. |

Lender reporting units pool normalized currently assigned 7(a) bank names and
reported 504 third-party lender names. They are snapshot attribution of historical
records, with no resolved historical banking identity. Do not label rankings as
historical originator or consolidated banking-group market shares.

Local report verification and public delivery are separate. The October 12 publication
includes seven genuine report-page captures, while the PBIX and PDF stay local.
Publish an editable PBIX only after an explicit request to publish that binary.
The default ignore rules keep manual artifacts local.
Do not close the dashboard/evidence tasks on source-contract tests alone.
See [methodology](../docs/detailed/kpi_definitions.md),
[dashboard specification](../docs/detailed/dashboard_spec.md) and
[dated verification evidence](../docs/implementation/lending_verification_history.md).
