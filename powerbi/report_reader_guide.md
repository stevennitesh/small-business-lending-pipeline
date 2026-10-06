# Reading the lending report

The report follows approval activity from its overall direction to geography, distribution and source coverage.
Start with **2025** for lending; use **2023** when comparing lending with employer business locations and labor context.
The [reader results](../docs/detailed/analysis_results.md) show actual current charts. The saved Power BI binary remains historical.

## Follow the current static charts

The [current reader report](../docs/detailed/analysis_results.md) follows this sequence:

1. **Annual change (2025):** compare reported dollars with approval-record volume.
2. **Geography (2023):** compare dollar leaders with records per employer location using the same year.
3. **Programs (2025):** compare the contribution of 7(a) and 504, retaining their different amount bases.
4. **Industries (2025):** compare shares of known-sector dollars and disclose coverage.
5. **Reporting lender names (2025):** rank after adding dollars across geography; disclose known-name coverage.
6. **Source coverage:** distinguish reference periods, publication dates and downloads.

BLS labor data is validated for state-level Power BI context. The current static
charts focus on approvals and employer-location comparisons, plus source coverage.
Eligible approval records have a recognized project state and a calendar approval
date; the current full population covers 50 states and Washington, DC.

## Planned six Power BI pages

These are the Desktop correction targets and defaults. They preserve the required
page order. Desktop delivery is pending; the outdated PBIX and five screenshots
are preserved locally and excluded from the public repository.

| Report title | Question | What to look for | Default |
|---|---|---|---|
| Lending at a glance | How much approval activity is there, and how has it changed? | Start with reported amounts, record count, average known amount and full-year change. More dollars do not necessarily mean more records. | 2025 |
| How lending varies by state | Where are reported amounts and approval records largest? | Compare states within the same calendar year. Use full-year trends; blank growth means the selected periods or state populations are not comparable. | 2025 |
| Reporting lender names | How much activity is assigned to the largest known names? | Rank names after adding amounts across the selected geography and years. Show known-name coverage and distinguish overall top five from combined state/year rankings. | 2025 |
| Programs and industries | What makes up the reported lending total? | Show program shares of all reported amounts and industry shares of known-sector amounts in separate panels. Category selections apply only to their own panel. | 2025 |
| Lending relative to local businesses | How does activity compare with the employer business base? | Use the same year for lending and employer locations. Single-year intensity is records per 1,000 locations; several years use establishment-years. Labor context is state-specific. | 2023 |
| Source coverage and data checks | What periods do these inputs cover, and can they be trusted? | Show reference periods, publication dates, publisher checks and downloads; separate validity and final completion. Show the frozen UTC check time and separately dated source-refresh completion. | Source-wide, no lending filters |

## Read the terms before comparing

- **SBA programs:** [7(a)](https://www.sba.gov/loans/7a-loans/) supports general business uses such as working capital, equipment and real estate; [504](https://www.sba.gov/loans/504-loans/) supports major fixed assets such as buildings and equipment.
- **Approval record:** a reported SBA approval, including canceled/not-funded records; not a unique borrower or disbursement.
- **Reported approval amount:** nominal whole-loan amount for 7(a), or the SBA/Certified Development Company portion for 504. Combined totals use these different bases.
- **Employer business location:** a Census employer establishment, across firm sizes. It excludes businesses without employees and is not the exact population of eligible small businesses.
- **Per year across several years:** annual business-location stocks are added as establishment-years. This measures average annual record activity relative to those stocks, not activity per unique business.
- **Known-name / known-industry share:** dollars with a recognized name or sector supply the denominator; unknowns remain in overall activity. Coverage shows how much the known-only denominator leaves out.
- **Percentage points:** 4% to 5% is +1 percentage point, rather than +1% relative growth.

## Understand the filters

State, region and calendar year affect supported lending views. Program, industry and lender-name choices affect only their own distribution panel. A program selection does not change the overall state/year headline.
Lender top-five share and known-name coverage retain geography/time but ignore the selected individual lender name. This lets a selected-name card sit beside a consistent overall concentration benchmark.
Blank annual growth means the selected years or state populations cannot support the comparison; it does not mean zero growth. Multi-state unemployment cards remain blank because averaging state rates does not produce a national rate.
Selection titles name one value, show “Multiple years/states” for a subset,
and reserve “All years/states” for the whole dimension. A selected region is a
state subset. Empty contexts show “No years/states”.

## Keep source status understandable

| Stored status | Reader label |
|---|---|
| `valid_selected_snapshot` | Saved input checks passed |
| `current` | Within the local review window |
| `latest_published` | Latest verified published period |
| `stale` | Newer published period available |
| `unknown` | Not established by this evidence |
| `loaded` | Raw inputs loaded |
| `success` | Completed successfully (use separately dated final summary) |

A raw validation pass, raw load, modeled-table rebuild and final completion are separate events.
Show **“Final completion not established in these reporting tables”** for unknown same-build status.
Beside it show **“Source refresh completed October 5, 2026 UTC after repair from retained downloads.”**
The exact timestamp and execution history are retained in the
[verification appendix](../docs/implementation/lending_verification_history.md).
Lead with **published reference period → actual publication date → download date**,
then the publisher verification date and assessment reason. Census 2023 was
published September 25, 2025; BLS August 2026 was published September 18, 2026.
SBA's June 30 coverage cutoff is not its publication date; show that date as
unconfirmed. BLS announces October 20 for the next state release; no next SBA or
Census date is confirmed by the retained evidence.

Only a missed verified published period is stale. Expired verification or old
downloads require review; they do not prove a newer release exists. Observation
age remains descriptive and secondary to these publication clocks.
Publisher review windows are local policies: SBA/BDS 90 days, BLS 30 days.

SBA 2026 ends in June and BLS 2026 in August; neither is a complete-year comparison.
Calendar year 2025 has 11 published unemployment months because October was not
published; no comparable annual change is shown.

The [Power BI handoff](README.md) owns relationships, supported selections, exact correction work and genuine Desktop acceptance. The [metric methodology](../docs/detailed/kpi_definitions.md) owns formulas and populations.


## Technical reference for applying labels in Desktop

Use the planned page titles/narration above. Keep measure names and column names unchanged; set visual titles, axis labels and tooltip text to these plain labels.
The maintained metadata owners are [report_language.json](report_language.json) for pages/fields and [lending_dashboard_model.json](lending_dashboard_model.json) for measure display names/descriptions. They are handoff metadata, not an automatic PBIX update.

| Machine field | Display label | Tooltip / interpretation |
|---|---|---|
| `total_approved_loan_amount` | Reported approval amounts ($) | Nominal whole-loan amounts for 7(a), plus the SBA/Certified Development Company portion of 504. Not disbursements or total financing. |
| `loan_count` | Approval records | Public approval records with mapped project geography and calendar dates. Includes canceled/not-funded records; not unique borrowers. |
| `approval_amount_coverage_count` | Records with known approval amounts | Valid amounts including zero. Unknown amounts remain in approval-record totals but are excluded from the average denominator. |
| `state_name` | Project state | Project location reported on the approval record, rather than borrower headquarters. |
| `approval_year` | Calendar approval year | Year of the approval date, separate from the SBA fiscal year. |
| `year` | Calendar year | Shared year label; source observation windows still differ. |
| `loan_program_name` | SBA program | 7(a) and 504 have different reported amount bases. |
| `naics_sector_name` | Industry sector | North American Industry Classification System (NAICS) grouping. Unknown/unclassified sectors remain in total activity and are excluded from known-sector shares. |
| `lender_name` | Reporting lender name | Currently assigned bank for 7(a); reported third-party lender for 504. Normalized names are not resolved historical originators or banking groups. |
| `establishment_count` | Employer business locations | Census employer establishments across firm sizes; excludes nonemployers. Annual reference stocks summed across years are establishment-years. |
| `bds_reference_date` | Census business-count reference date | March 12 of the reference year; context for calendar-year lending, not an identical time window. |
| `freshness_checked_at_utc` | Publication and download checks evaluated at (UTC) | The frozen time at which source ages were calculated. Opening the report later does not update the ages. |
| `latest_extracted_at_utc` | Source files downloaded at (UTC) | When the saved public data was extracted; separate from observation date and modeled-table rebuild. |
| `latest_observation_date` | Latest source observation/reference | Approval date for SBA; March 12 annual reference for Census; month end for BLS. |
| `extract_age_days` | Days since source download | Age at the stated UTC check time, compared with the configured extraction tolerance. |
| `observation_age_days` | Days since source observation/reference | Descriptive age of the reference; it is not a stale-data rule or the time since a warehouse rebuild. |
| `snapshot_validity_status` | Saved input validation | Passing source checks establish usable saved evidence, independently of age. |
| `freshness_status` | Source recency | Stale only when a verified newer published period is missing; expired checks or old downloads require verification. Old reference dates alone are not stale. |
| `publication_reference_date` | Latest verified published reference period | Quarter-end coverage for SBA; March 12 of the BDS reference year; month end for BLS. Compare at each source cadence. |
| `publication_date` | Published on | Actual publication date from publisher evidence. Unknown dates stay blank; coverage cutoffs and catalog modified dates are not publication dates. |
| `publication_verified_date` | Publisher checked on | Date on which the latest published period was verified. This is separate from the release and download dates. |
| `publication_source_url` | Publisher evidence | Official source used to verify the reference period and any known publication date. |
| `publication_cadence` | Publication frequency | Expected release frequency, separate from reference-year lag. Frequency does not prove a new release exists. |
| `next_scheduled_release_date` | Next announced release | Confirmed publisher schedule when available; a schedule passing triggers verification, not an assumed new release. |
| `publication_status` | Published-period comparison | Saved source period compared with dated publisher evidence. |
| `download_status` | Download review | A local review window for the saved download; review due does not prove a newer release exists. |
| `freshness_reason` | Recency assessment | Specific reason for the publication or download status; show this beside the dates. |
| `max_release_check_age_days` | Publisher review window (days) | Local limit on the age of publication verification, not a publisher deadline. |
| `release_check_age_days` | Days since publisher verification | Age of the dated publisher check at the frozen evaluation time. |
| `raw_load_status` | Source loading status | Whether raw inputs were loaded; this is not final pipeline completion. |
| `latest_run_status` | Final completion visible in reporting tables | Unknown during the same build. Actual completion comes from the separately dated final pipeline summary. |
| `observed_month_count` | Months with unemployment data | Available non-null monthly state rates; compare with expected/publisher-omitted months. |
| `publisher_omitted_month_count` | Months not published | Publisher omissions are disclosed separately from unexpected missing data. |
| `is_comparable_context` | Complete economic context | A complete lending year with same-year positive business counts and comparable monthly labor coverage. |
| `unemployment_rate_yoy_change_pp` | Unemployment change (percentage points) | 4% to 5% is +1 percentage point; only comparable annual periods support a change. |

### Measure name to visual label

The implementation names below identify the exact blocks in [semantic_measures.dax](semantic_measures.dax). Copy their current expressions without renaming dependencies.
Use each measure’s JSON `description` as its tooltip. Labels repeat within panels intentionally: the page/panel provides the program, industry or reporting-name context.

| Existing measure name | Visual label |
|---|---|
| `Selected Year Label` | Calendar year |
| `Selected State Label` | Project state |
| `Approval Dollars` | Reported approval amounts |
| `Approval Records` | Approval records |
| `Average Approval Size` | Average reported amount |
| `Program Dollars` | Program: reported approval amounts |
| `Program Records` | Program: approval records |
| `Program Average Approval Size` | Program: average reported amount |
| `Industry Dollars` | Industry: reported approval amounts |
| `Industry Records` | Industry: approval records |
| `Industry Average Approval Size` | Industry: average reported amount |
| `Known Lender Dollars` | Known lender name: reported approval amounts |
| `Known Lender Records` | Known lender name: approval records |
| `Known Lender Average Approval Size` | Known lender name: average reported amount |
| `Matched Context Dollars` | Reported amounts with business context |
| `Matched Context Records` | Approval records with business context |
| `Matched Context Average Approval Size` | Average reported amount with business context |
| `Performance Dollars` | Reported performance: reported approval amounts |
| `Performance Records` | Reported performance: approval records |
| `Performance Average Approval Size` | Reported performance: average reported amount |
| `Status Dollars` | Loan status: reported approval amounts |
| `Status Records` | Loan status: approval records |
| `Status Average Approval Size` | Loan status: average reported amount |
| `Terms Dollars` | Loan terms: reported approval amounts |
| `Terms Records` | Loan terms: approval records |
| `Terms Average Approval Size` | Loan terms: average reported amount |
| `Jobs Dollars` | Reported jobs: reported approval amounts |
| `Jobs Records` | Reported jobs: approval records |
| `Jobs Average Approval Size` | Reported jobs: average reported amount |
| `Program Dollar Share` | Program share of reported amounts |
| `Known Industry Dollar Share` | Industry share of known-sector amounts |
| `Industry Dollar Coverage` | Amounts with a known industry (%) |
| `Lender Dollar Coverage` | Amounts with a known lender name (%) |
| `Selected Top Five Known Lender Share` | Five largest names: share of known-name amounts |
| `Pooled State Year Top Five Share` | Combined state/year top-five share (different memberships) |
| `Approvals per 1000 Establishment Years` | Approval records per 1,000 employer locations per year |
| `Approval Dollars per Establishment Year` | Reported amounts per employer location per year |
| `Comparable Full Year Dollar Growth` | Reported amount change from previous full year |
| `Chargeoff Dollar Rate` | Reported chargeoffs / reported approval amounts |
| `Charged Off Record Share` | Records with a reported chargeoff (%) |
| `Term Coverage` | Records with a known term (%) |
| `Average Known Term Months` | Average known loan term (months) |
| `Initial Rate Coverage` | Records with a known initial rate (%) |
| `Average Known Initial Rate` | Average known initial interest rate |
| `Fixed Interest Share` | Fixed-rate share of recognized rate types |
| `Variable Interest Share` | Variable-rate share of recognized rate types |
| `7a Guarantee Rate` | 7(a) guarantee / whole-loan amount |
| `Known 504 Third Party to SBA Amount Ratio` | 504 third-party amount / SBA-CDC portion |
| `Jobs Coverage` | Records with reported jobs (%) |
| `Reported Jobs per Known Record` | Reported jobs per record with jobs known |
| `Reported Jobs per Million Approved` | Reported jobs per $1 million in approval amounts |
| `Approved Dollars per Reported Job` | Reported approval amounts per reported job |
| `Status Dollar Share` | Status share of reported approval amounts |
| `Reported Jobs per Approval Record` | Reported jobs per approval record |
| `State Mean Monthly SA Unemployment Rate` | State unemployment: mean monthly adjusted rate |
| `State Unemployment Change PP` | State unemployment change (percentage points) |
| `State Published Establishment Entry Rate` | Employer-location entry rate (Census published) |
| `State Published Establishment Exit Rate` | Employer-location exit rate (Census published) |
| `Selected Known Source Name Count` | Number of known reporting lender names |
| `Approval Amount Coverage` | Records with a known approval amount (%) |
| `504 Paired Financing Coverage` | 504 records with both financing amounts known (%) |
| `7a Paired Guarantee Coverage` | 7(a) records with approval and guarantee amounts known (%) |
