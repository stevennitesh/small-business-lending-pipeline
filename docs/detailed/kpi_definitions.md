# KPI definitions and selection methodology

Current contract, October 4, 2026 (semantic version 3). This replaces the initial design's example
formulas and proposed/stretch metrics. SQL models own record eligibility, source
grains, cleaning and additive components. [Power BI measures](../../powerbi/semantic_measures.dax)
own aggregation over the selected modeled population. The
[JSON contract](../../powerbi/lending_dashboard_model.json) validates the actual
measure expressions, references and allowed aggregation patterns.

## Reading the analysis

Start with [the case study](case_study.md) and [current chart results](analysis_results.md).
The report calls Census establishments **employer business locations** and calls
mixed-basis nominal amounts **reported approval amounts**. A share based on known
names or industries always states that denominator and its coverage. The
[report reader guide](../../powerbi/report_reader_guide.md) maps ordinary labels to
stable fields and measures; changing display wording does not change these formulas.
Use 2025 for complete-year lending and 2023 for complete business/labor context.

## Reporting population

SBA FOIA 7(a)/504 records are public **historical approvals**. The retained
population is the latest validated staged records, including cancellation/not-funded
statuses where present. There is no disbursement-date or funded-status eligibility
filter. A record is not a unique borrower, firm or application. State marts require
a mapped project-state key and calendar approval date/year. Missing dates stay
missing: `approval_fiscal_year` is never substituted for calendar year. Cleaning
retains nonnegative gross amounts and converts invalid/negative amounts to null;
counts remain approval-record counts. Negative guarantee, third-party, chargeoff,
term, initial-rate and jobs values also become null in staging; they cannot count
as known observations in means or paired financing coverage. Null amounts do not create dollars. Means
use `approval_amount_coverage_count`, counting valid amounts including zero;
unknown amounts do not implicitly become zero-sized approvals.

SBA `GrossApproval` has different bases: **whole loan amount for 7(a)** and
**SBA/CDC loan portion for 504**. Combined dollars and program shares are sums
of these reported approval amounts, not total project financing, borrower funding
or comparable SBA exposure. `approval_amount_basis` travels with program labels.
[SBA field dictionary](https://data.sba.gov/sites/default/files/uploaded_resources/7a_504_foia_data_dictionary.xlsx).

Lender reporting uses the **currently assigned bank** (`BankName`) for 7(a) and
the **reported third-party lender** (`ThirdPartyLender_Name`) for 504. Names are
normalized by case and whitespace, with empty and literal `UNKNOWN` names treated
as missing, then pooled across programs without institution or role resolution.
These are snapshot assignments of historical approval records, not historical
originator market shares. `LocationID` becomes `source_lender_id`: it identifies
the SBA lender (the CDC for 504), not the loan or necessarily the named third-party
lender. Approval identity remains source artifact plus row; this field is never
a deduplication key. `reporting_lender_role` travels with program labels.
NAICS is grouped to sector keys. Missing/unmapped sectors use `UNKNOWN`; source
99 remains an unclassified key. dbt `is_known_industry` excludes both from the
known-industry denominator without altering their stored keys. State exports
exclude unmapped geography; lender exports show known names only, while industry
exports retain unknown rows for disclosure. Coverage must use the same state/year
population as the headline approval totals.

## Selection-safe formulas

Use dimension columns for slicers/axes. State and region plus calendar year affect
all lending outputs. Program filters affect `bi_program_mix`, industry filters
`bi_industry_mix`, lender filters `bi_lender_mix`. These category filters cannot
filter state-year summary tables; do not sync them across unrelated pages.

| Metric | Formula under supported selection | Interpretation |
|---|---|---|
| Reported approval dollars / records | `SUM(total_approved_loan_amount)` / `SUM(loan_count)` separately | Nominal source amounts with different program bases / source records |
| Average reported approval size | `SUM(total_approved_loan_amount) / SUM(approval_amount_coverage_count)` | Known-amount records only; never average state/year/category averages |
| Approval amount coverage | `SUM(approval_amount_coverage_count) / SUM(loan_count)` | Records with valid amounts including zero / all eligible records |
| Program dollar share | Selected program dollars / selected all-program dollars | Share of mixed-basis reported amounts; denominator removes only program category filter |
| Known-industry share | Selected known-sector dollars / all known-sector dollars | Geography/time stay selected; unknown NAICS excluded from both sides |
| Industry dollar coverage | All known-industry dollars / all approval dollars | Clears industry dimension and known-only page flag for all-industry denominator; retains state/year; disclose unknown amount/count |
| Lender dollar coverage | Known-name dollars / all approval dollars | Independent of lender slicer; not an institution-resolution score |
| Selected top-five known lender share | Aggregate dollars by name key across selected states/years; rank descending amount, ascending key; sum first five / selected all-known-name dollars | Lender slicer deliberately removed before ranking; deterministic ties |
| Pooled state-year top-five share | Sum stored state/year top-five dollars / sum state/year known-name dollars | Different memberships in each state/year; separately labeled |
| Approvals per 1,000 establishment-years | `SUM(matched loan_count) * 1000 / SUM(matched establishment_count)` | Same state/year rows with `has_matched_establishment_population = true` on both sides |
| Dollars per establishment-year | `SUM(matched approved dollars) / SUM(matched establishments)` | Same matched population; one year: dollars per establishment; multiple years: average annual activity per establishment |

There is no exact small-business denominator: BDS counts **employer
establishments across firm sizes**, not distinct firms, borrowers or all businesses.
Summing stocks across years creates establishment-years, not a count of unique
establishments. Annual reference stocks summed over years are an establishment-year
proxy, not measured continuous exposure. BDS excludes nonemployers and some sectors;
the SBA numerator is not restricted to exactly that scope. Intensity is contextual,
not SBA penetration. No causal, demand, fairness, access or creditworthiness claim follows.

## Calendar and source coverage

[`config/reporting_policy.yml`](../../config/reporting_policy.yml) owns dated
publisher coverage evidence. The October 5 refreshed snapshot has calendar SBA dates
**1990-10-01 through 2026-06-30**, verified against the June 30 publisher release. Calendar 1990 and 2026 are partial; full years
are 1991–2025. Record min/max dates are descriptive diagnostics, not proof of
publication completeness. Update policy only with verified release evidence.

`mart_lending_annual_state` exposes full/partial/outside-evidence flags, observed
bounds, source coverage and evidence date. YoY requires consecutive comparable
full calendar years; otherwise its ratio and prior-year component are null.
The report growth measure additionally requires one selected year, comparable
prior data for every current row, and the same set of observed states in both
years under the selected geography. It checks both directions of the state-set
difference while replacing only the year filter for the prior population. A
prior-only state makes the selected growth blank: an absent current record does
not prove zero approvals. A balanced single-state selection remains valid. Use **2025** for the latest supported
full-year lending view and **2023** for the latest matched complete context view.
Historical totals may include partial boundaries when explicitly labeled.
No YTD growth is exported: it would need the same elapsed approval dates in both
years, not partial-year amount divided by a full prior year.
Monthly SBA YoY joins the same calendar month in the preceding year. An absent
month leaves growth null rather than shifting comparison to another month.

## BDS and LAUS context

Keep Census's published BDS entry/exit rates at state/year. Their denominator uses
scope-consistent stocks: prior stock = current stock + exits − entries, then
the mean of current and derived prior stock. Adjacent published stocks can have
different scope; neither their naive mean nor current stock alone is correct.
No rate rollup is supplied without the proper denominator.
[Census rate definitions](https://www.census.gov/programs-surveys/bds/about/faq.html)
and [BDS population](https://www.census.gov/programs-surveys/bds/about.html).
`bds_reference_date` is March 12 of the BDS year; flows span March to March.
The year join supplies regional context for calendar lending, without claiming
identical reference periods or exact temporal exposure.

`annual_average_unemployment_rate` is the **mean monthly seasonally adjusted
state rate**, stored as a decimal (0.05 = 5%). It is not an official annual
labor-force-weighted estimate. Never average state rates into a national/regional
rate; that would require the underlying unemployed and labor-force counts.

The October 5 refresh contains LAUS observations through **August 2026**,
separately from SBA’s June endpoint. Dated LAUS policy expects eight months for
2026; this valid YTD period is not a comparable full annual year. The 51 explicit
October 2025 missing markers remain null rates, excluded from observed-month counts.

LAUS annual outputs disclose observed/expected months, full-year expectation (12),
publisher-omitted months, missing available months, YTD, comparability and status.
`observed_expected_month_count` matches non-null month identities to the available
expected range; `unexpected_month_count` separately counts observations beyond
the dated endpoint or in omitted months. An unexpected May cannot replace a
missing April. Omissions reduce expectations only inside the elapsed range;
missing counts use matched identities, not total observed counts. Unexpected
observations remain in the descriptive observed-rate mean but block comparability.
**October 2025 was not published.** Expected available months are 11, and the valid
publisher year is not strictly comparable to an ordinary year. It is neither
imputed nor rejected as an ingestion failure. Other gaps remain visible.
[BLS publisher notice](https://www.bls.gov/lau/launews1.htm).

Annual unemployment YoY is null unless adjacent years each have 12 comparable
months. Monthly changes match the same calendar month in the prior year, not the
12th prior observation across gaps. `unemployment_rate_yoy_change_pp` is multiplied
by 100: 4% → 5% = **+1 percentage point**. The BI alias
`unemployment_rate_yoy_change_pct` is retained as deprecated decimal change (0.01)
for compatible consumers; it is not a percent-change measure. New visuals use `_pp`.
Regional rows retain matched source presence even when coverage is partial;
`is_comparable_context` additionally requires complete annual coverage.

## Optional descriptive SBA components

Performance measures divide chargeoff amounts by approvals and charged-off counts
by records. They describe reported historical statuses, not vintage-adjusted
credit-loss estimates. Status shares remove only the status category filter.
Known term and initial-rate means use additive sums divided by non-null coverage
counts; availability ratios divide those counts by all approval records. Fixed/
variable shares use recognized F/FIXED/V/VARIABLE counts. The third-party ratio is
`SUM(paired_504_third_party_dollars) / SUM(paired_504_approval_amount)`: both sums
use only 504 records with valid values on both sides. Its coverage is
`SUM(paired_504_coverage_count) / SUM(program_504_loan_count)`. The denominator is
the SBA/CDC portion, so the ratio can exceed 100%; it is not a project financing
share. The old mixed-program `third_party_to_approved_amount_rate` remains a
deprecated export column; the old DAX measure is replaced by **Known 504 Third
Party to SBA Amount Ratio**, displayed alongside **504 Paired Financing Coverage**.
The 7(a) guarantee ratio likewise divides `paired_7a_guaranteed_amount` by
`paired_7a_approval_amount` on the same known 7(a) records, with
`paired_7a_coverage_count / program_7a_loan_count` disclosed separately.
Reported jobs have separate
all-record and known-record ratios, plus coverage. Jobs are lender estimates of
created and retained positions at application, not audited outcomes or causal jobs created.
See the exact definitions in `bi_lending_performance`, `bi_lending_status_mix`,
`bi_lending_terms_pricing`, `bi_lending_jobs_impact` and the DAX handoff.

## Validity, freshness, loading and completion

These are independent facts. `is_latest_successful_snapshot` means selected valid
raw evidence; it cannot mean a current-year observation. Recency compares the saved
source period with **verified publisher releases**, not the age of the last point.

| Source | Published reference verified October 5, 2026 | Actual publication date | Timing |
|---|---|---|---|
| SBA FOIA | 2026 Q2, coverage through June 30 | Unconfirmed | Quarterly, typically one month after quarter end |
| Census BDS | 2023, March 12 reference | September 25, 2025 | Annual, typically September about two years after the reference year |
| BLS state LAUS | August 2026, month-end reference | September 18, 2026 | Monthly; next announced state release October 20 |

Publisher evidence is retained in `reporting_policy.census_bds_release` and
`reporting_policy.source_publications`, with official URLs and verification dates.
SBA/BLS reference endpoints use the existing dated coverage policy. A coverage
cutoff, dataset modified timestamp or scheduled date is never substituted for an
actual publication date. The SBA publication date stays null because its catalog
confirms the June coverage but not that release date.

[SBA timing and coverage](https://data.sba.gov/dataset/7a-504-foia),
[Census release](https://www.census.gov/programs-surveys/bds/news-updates/updates.html),
[Census timing](https://www.census.gov/programs-surveys/bds/about/faq.html), and
[BLS state release and schedule](https://www.bls.gov/news.release/archives/laus_09182026.htm).

The source comparison uses a **quarter** for SBA, **year** for Census, and **month**
for BLS. A last SBA approval a few days before quarter end does not itself mean a
missed release. This is a source-wide recency check, not per-resource or state
coverage certification; completeness and validity remain separate.

- `publication_status = latest_published`: saved period matches recent publisher evidence.
- `publication_status = newer_release_available`: a verified newer published period is missing.
- `publication_status = verification_due`: release verification expired or an announced
  next release date passed since the last publisher check; do not assume publication occurred.
- `publication_status = unknown`: evidence is missing, future, inconsistent or older
  than a saved period requiring verification.
- `download_status`: `current`, `review_due` or `unknown` independently describes
  the saved resource download and its local review window.

Combined `freshness_status` is **stale only for a missed verified publication**.
Matching publication plus an in-window download is `latest_published`. Expired
checks or old/unknown download evidence produce `unknown`, with the specific
`freshness_reason`; they do not prove a newer release exists. The health rollup
counts `latest_published` as healthy, independently of validity.

[Freshness configuration](../../config/freshness_rules.yml) keeps download-review
windows of SBA 120, BDS 400 and BLS 60 days; publisher-review windows are 90, 90 and
30 days. These are **local review policies**, not publisher deadlines. All
observation-age thresholds are null. `observation_age_days` remains descriptive:
the March 12, 2023 Census reference can be 1303 days old and still be the latest
verified release. No new reference year is inferred from the calendar.

The BI exports carry the reference date, actual publication date, publisher URL,
verification date, cadence, announced next release, publication/download statuses
and assessment reason. Show those before descriptive observation ages. BDS uses
March 12; BLS uses month end. Frozen evidence reports recency **at its checked-at
UTC time**, not viewing time. Rebuild/export to reevaluate checks; no live source
request occurs merely by viewing a report.

`raw_load_status` describes raw loading, `validation_status` describes raw checks.
`latest_run_status` is **unknown** in the same dbt pass because final exports and
summary writing have not happened. Actual completion comes from the final
`data/validation/pipeline_run_id=<id>/run_summary.json`; neither dbt nor the PBIX
may infer it from raw validation. The final summary is separately dated evidence.
Local and cloud flows share this policy and status boundary. No monitoring service
or recurring schedule is introduced.
