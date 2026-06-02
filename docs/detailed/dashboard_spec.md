# Step 10: Dashboard and Acceptance Criteria

## Purpose

This section defines the Power BI dashboard design and the acceptance criteria for the Small Business Lending Intelligence Pipeline.

The dashboard is the stakeholder-facing output of the project. It should make the modeled KPI tables usable for business review, while also showing that the underlying pipeline is tested, traceable, and refreshable.

The dashboard supports the approved MVP scope:

- SBA 7(a) and 504 FOIA data as the core lending source.
- Census Business Dynamics Statistics as annual business-health context.
- BLS LAUS as monthly labor-market context.
- State-level analysis as the MVP geography.
- Power BI connected to modeled mart or BI tables.
- Data quality and pipeline health visible in the final deliverable.
- No predictive machine learning in the MVP.

---

## Dashboard Goals

The Power BI dashboard should satisfy five goals.

1. **Answer the business questions quickly**  
   A stakeholder should be able to understand lending volume, trend direction, lender concentration, industry mix, and regional context without reading SQL.

2. **Use trusted modeled tables**  
   Power BI should connect to the dbt `BI` layer or final mart tables. It should not connect directly to raw source files.

3. **Keep KPI logic out of Power BI where practical**  
   Core KPI definitions should be implemented in dbt models. Power BI should focus on filtering, formatting, and presentation.

4. **Expose data quality status**  
   The dashboard should show source freshness, latest successful run, validation status, row counts, and dbt test health.

5. **Be recruiter-readable**  
   A recruiter or hiring manager should understand the project value from screenshots, page titles, KPI cards, and the README in under five minutes.

---

## Dashboard Design Principles

The dashboard should follow these design principles.

| Principle | Implementation |
|---|---|
| Business-first layout | Start with executive KPIs before detailed drilldowns |
| Modeled-data only | Use `BI` or mart tables, not raw tables |
| Clear grains | Label monthly and annual views explicitly |
| Descriptive language | Avoid causal claims about unemployment or business formation |
| Minimal DAX | Use DAX only for presentation or simple selected-value logic |
| Consistent formatting | Apply standardized currency, percentage, count, and date formats |
| Data quality visible | Include a pipeline health page or quality section |
| Privacy-aware display | Do not expose borrower-level records or raw loan identifiers |
| Recruiter-friendly screenshots | Include dashboard pages that show both business value and engineering maturity |

---

## Power BI Data Contract

Power BI should consume dashboard-ready tables from the `BI` schema whenever possible.

### Required BI Tables

| BI Table | Grain | Dashboard Use |
|---|---|---|
| `bi_executive_overview` | State-year | Executive summary and national/state comparisons |
| `bi_state_lending_trends` | State-month | Monthly lending trends and unemployment comparison |
| `bi_lender_concentration` | State-year-lender | Lender rankings, lender share, and concentration views |
| `bi_industry_mix` | State-year-NAICS sector | Industry lending mix and sector-level comparisons |
| `bi_program_mix` | State-year-program | 7(a) versus 504 program mix |
| `bi_regional_business_health` | State-year | Lending normalized by establishments and business-health context |
| `bi_pipeline_health` | Pipeline run/source/model/check summary | Data quality and refresh status |

### Optional Supporting Dimensions

Power BI can also use simplified dimensions if they improve filtering.

| Dimension | Use |
|---|---|
| `dim_date` | Date hierarchy and time slicers |
| `dim_state` | State, region, and division slicers |
| `dim_naics` | NAICS sector labels |
| `dim_lender` | Lender display labels |
| `dim_loan_program` | SBA program labels |

### Connection Rule

```text
Power BI should connect to the final BI schema or exported BI tables only.
```

Allowed sources:

```text
Snowflake SMALL_BUSINESS_LENDING.BI tables
DuckDB-exported BI CSV/Parquet files for local prototype
```

Disallowed sources:

```text
raw SBA CSV files
raw Census JSON responses
raw BLS JSON responses
raw borrower-level loan records
ad hoc Excel transformations
manual copy/paste tables
```

---

## Global Dashboard Filters

The MVP dashboard should include a small set of reusable filters.

| Filter | Source Field | Applies To | Notes |
|---|---|---|---|
| Year | `calendar_year` | Annual pages | Default to latest complete year where practical |
| Month | `month_start_date` | Monthly trend page | Use month-year format |
| State | `state_name` / `state_abbr` | All business pages | Multi-select allowed |
| Census region | `census_region` | All state-level pages | Useful for regional comparison |
| Loan program | `loan_program` | Lending pages | 7(a), 504, or all |
| NAICS sector | `naics_sector_name` | Industry page | Use broad sector first |
| Lender | `standardized_lender_name` | Lender page | Searchable slicer |
| Data status | `source_freshness_status` / `run_status` | Pipeline health page | Shows pass/warning/fail state |

### Default Filter Behavior

Recommended default dashboard view:

```text
latest complete year
all states
all programs
all industries
all lenders
```

For monthly trend pages, the default should show the latest available rolling period with enough historical context for year-over-year comparisons.

---

# Dashboard Page 1: Executive Overview

## Purpose

The Executive Overview page gives a fast summary of national and state-level small-business lending activity.

This page should answer:

- How much SBA lending was approved?
- How many loans were approved?
- What was the average loan size?
- Is lending increasing or declining year over year?
- Which states show the strongest lending activity?
- Is the data fresh enough for reporting?

## Primary Users

- Business analytics manager
- Finance analyst
- Regional strategy analyst
- Recruiter / hiring manager

## Source Tables

| Table | Use |
|---|---|
| `bi_executive_overview` | Main executive KPIs |
| `bi_regional_business_health` | Lending intensity and context |
| `bi_pipeline_health` | Latest refresh/freshness indicator |

## Required KPI Cards

| KPI Card | Metric |
|---|---|
| Total approved loan amount | `total_approved_loan_amount` |
| Loan count | `loan_count` |
| Average loan size | `average_loan_size` |
| Approved amount YoY growth | `approved_loan_amount_yoy_growth_pct` |
| Loan count YoY growth | `loan_count_yoy_growth_pct` |
| Top 5 lender share | `top_5_lender_share` |
| Loans per 1,000 establishments | `loans_per_1000_establishments` |
| Latest successful pipeline run | `latest_successful_pipeline_run_at_utc` |

## Required Visuals

| Visual | Purpose |
|---|---|
| KPI card row | Shows headline lending performance |
| Filled map or bar chart by state | Shows geographic distribution of lending |
| Annual trend line | Shows approved amount and loan count over time |
| Top states table | Ranks states by approved loan amount, loan count, and lending intensity |
| Data freshness badge | Shows latest successful run and source status |

## Recommended Layout

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Executive Overview                                                   │
├──────────────┬──────────────┬──────────────┬──────────────┬────────┤
│ Approved $   │ Loan Count   │ Avg Loan     │ YoY Growth   │ Status │
├─────────────────────────────────────┬───────────────────────────────┤
│ Annual lending trend                 │ State lending map / ranking   │
├─────────────────────────────────────┴───────────────────────────────┤
│ Top states table                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Page Acceptance Criteria

The page is complete when:

1. It shows all required KPI cards.
2. It supports year and state filtering.
3. State totals reconcile to the annual lending mart.
4. The data freshness badge is visible.
5. Metrics are formatted consistently.
6. The page does not expose raw borrower-level details.
7. Screenshot is saved to `powerbi/screenshots/01_executive_overview.png`.

---

# Dashboard Page 2: State Lending Trends

## Purpose

The State Lending Trends page focuses on time-series analysis by state.

This page should answer:

- How has lending changed over time?
- Which states are growing or declining?
- How do lending trends compare with unemployment trends?
- Are changes driven by loan count or average loan size?

## Primary Users

- Regional strategy analyst
- Business analytics manager
- Finance analyst

## Source Tables

| Table | Use |
|---|---|
| `bi_state_lending_trends` | Monthly state lending and unemployment comparison |
| `dim_state` | Region/state filters |
| `dim_date` | Date hierarchy |

## Required KPI Cards

| KPI Card | Metric |
|---|---|
| Selected-period approved loan amount | `total_approved_loan_amount` |
| Selected-period loan count | `loan_count` |
| Average loan size | `average_loan_size` |
| Approved amount YoY growth | `approved_loan_amount_yoy_growth_pct` |
| Loan count YoY growth | `loan_count_yoy_growth_pct` |
| Unemployment rate | `unemployment_rate` |
| Unemployment YoY change | `unemployment_rate_yoy_change_pp` |

## Required Visuals

| Visual | Purpose |
|---|---|
| Monthly lending trend line | Shows approved amount over time |
| Loan count trend line | Shows volume trend separate from dollars |
| Average loan size trend | Shows whether dollar changes are driven by larger loans |
| Lending versus unemployment combo chart | Shows descriptive comparison, not causation |
| State comparison small table | Shows selected states side by side |

## Recommended Layout

```text
┌─────────────────────────────────────────────────────────────────────┐
│ State Lending Trends                                                │
├──────────────┬──────────────┬──────────────┬──────────────┬────────┤
│ Approved $   │ Loan Count   │ Avg Loan     │ YoY Growth   │ Unemp. │
├─────────────────────────────────────────────────────────────────────┤
│ Monthly approved loan amount trend                                  │
├─────────────────────────────────────┬───────────────────────────────┤
│ Loan count / average loan size       │ Lending vs unemployment       │
├─────────────────────────────────────┴───────────────────────────────┤
│ State comparison table                                               │
└─────────────────────────────────────────────────────────────────────┘
```

## Required Caveat Text

The page should include a note:

```text
Lending and unemployment comparisons are descriptive. They do not imply that labor-market conditions caused lending changes.
```

## Page Acceptance Criteria

The page is complete when:

1. It supports state, region, program, and date filtering.
2. Monthly lending KPIs come from `bi_state_lending_trends`.
3. Unemployment comparison is clearly labeled as descriptive.
4. YoY metrics return null where prior-year comparison is unavailable.
5. Monthly and annual grains are not mixed without labeling.
6. Screenshot is saved to `powerbi/screenshots/02_state_lending_trends.png`.

---

# Dashboard Page 3: Lender Concentration

## Purpose

The Lender Concentration page analyzes which lenders drive SBA lending activity and whether markets are concentrated among a small number of lenders.

This page should answer:

- Which lenders account for the most approved loan dollars?
- Which lenders have the highest loan counts?
- How concentrated is lending activity by state and year?
- Does the top-lender share vary across states?

## Primary Users

- Finance analyst
- Lending operations stakeholder
- Business analytics manager

## Source Tables

| Table | Use |
|---|---|
| `bi_lender_concentration` | Lender rankings and concentration metrics |
| `dim_lender` | Lender labels |
| `dim_state` | State/region filters |

## Required KPI Cards

| KPI Card | Metric |
|---|---|
| Active lender count | `active_lender_count` |
| Top 1 lender share | `top_1_lender_share` |
| Top 5 lender share | `top_5_lender_share` |
| Largest lender approved amount | `lender_approved_loan_amount` for rank 1 |
| Largest lender name | `standardized_lender_name` for rank 1 |

## Required Visuals

| Visual | Purpose |
|---|---|
| Top lenders bar chart | Ranks lenders by approved loan amount |
| Lender share chart | Shows lender percentage of state/year lending |
| State concentration heatmap or matrix | Compares top 5 lender share by state |
| Lender detail table | Shows lender amount, loan count, average loan size, rank, share |
| Concentration trend line | Shows top 5 lender share over time where available |

## Recommended Layout

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Lender Concentration                                                │
├──────────────┬──────────────┬──────────────┬───────────────────────┤
│ Active Lend. │ Top 1 Share  │ Top 5 Share  │ Largest Lender        │
├─────────────────────────────────────┬───────────────────────────────┤
│ Top lenders by approved amount       │ Lender share / concentration │
├─────────────────────────────────────┴───────────────────────────────┤
│ Lender detail table                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Page Acceptance Criteria

The page is complete when:

1. Lender rankings are calculated in dbt, not manually in Power BI.
2. Top-lender share metrics are between 0 and 1 before formatting.
3. Lender totals reconcile to annual lending totals for selected filters.
4. Missing lender names are displayed as `Unknown Lender`.
5. No raw borrower or raw loan identifiers are displayed.
6. Screenshot is saved to `powerbi/screenshots/03_lender_concentration.png`.

---

# Dashboard Page 4: Industry and Program Mix

## Purpose

The Industry and Program Mix page analyzes SBA lending by NAICS sector and loan program.

This page should answer:

- Which industries receive the most approved loan volume?
- Which industries have the largest number of loans?
- How does average loan size vary by industry?
- How does lending differ between 7(a) and 504 programs?
- Which industries are gaining or losing share over time?

## Primary Users

- Business analytics manager
- Regional strategy analyst
- Finance analyst

## Source Tables

| Table | Use |
|---|---|
| `bi_industry_mix` | NAICS sector metrics |
| `bi_program_mix` | SBA program mix metrics |
| `dim_naics` | Industry labels |
| `dim_loan_program` | Program labels |

## Required KPI Cards

| KPI Card | Metric |
|---|---|
| Top industry by approved amount | `industry_approved_loan_amount` rank 1 |
| Top industry by loan count | `industry_loan_count` rank 1 |
| Selected industry share | `industry_approved_amount_share` |
| 7(a) approved amount | `program_approved_loan_amount` where program is 7(a) |
| 504 approved amount | `program_approved_loan_amount` where program is 504 |

## Required Visuals

| Visual | Purpose |
|---|---|
| Industry approved amount bar chart | Shows sector-level dollar concentration |
| Industry loan count bar chart | Shows volume distribution |
| Average loan size by industry | Shows differences in loan size |
| Program mix stacked bar or donut | Shows 7(a) versus 504 composition |
| Industry trend line | Shows sector share or approved dollars over time |
| Industry detail table | Shows amount, count, average size, and share |

## Recommended Layout

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Industry and Program Mix                                            │
├──────────────┬──────────────┬──────────────┬───────────────────────┤
│ Top Industry │ Top Count    │ Sector Share │ Program Mix           │
├─────────────────────────────────────┬───────────────────────────────┤
│ Industry approved amount             │ Average loan size by sector  │
├─────────────────────────────────────┴───────────────────────────────┤
│ Program mix and industry detail table                                │
└─────────────────────────────────────────────────────────────────────┘
```

## Design Rule

Industry and program visuals should remain separate unless a dedicated model exists at this grain:

```text
state + calendar_year + naics_sector_code + loan_program
```

Do not create misleading many-to-many relationships in Power BI.

## Page Acceptance Criteria

The page is complete when:

1. Industry KPIs use NAICS sector-level grouping by default.
2. Missing or invalid NAICS values map to `Unknown / Unclassified`.
3. Industry shares sum approximately to 100% within the selected market.
4. Program values are limited to valid MVP program labels.
5. Program and industry grains are not combined incorrectly.
6. Screenshot is saved to `powerbi/screenshots/04_industry_program_mix.png`.

---

# Dashboard Page 5: Regional Business Health

## Purpose

The Regional Business Health page combines annual lending metrics with Census BDS and BLS LAUS context.

This page should answer:

- Which states have high lending activity relative to their business base?
- How does lending per establishment vary by state?
- How do business entry and exit rates compare with lending activity?
- Which states show stronger or weaker small-business credit activity on descriptive metrics?

## Primary Users

- Regional strategy analyst
- Business analytics manager
- Recruiter / hiring manager

## Source Tables

| Table | Use |
|---|---|
| `bi_regional_business_health` | Annual state-level cross-source KPIs |
| `dim_state` | State/region filters |

## Required KPI Cards

| KPI Card | Metric |
|---|---|
| Loans per 1,000 establishments | `loans_per_1000_establishments` |
| Approved dollars per establishment | `approved_loan_dollars_per_establishment` |
| Establishment count | `establishment_count` |
| Establishment entry rate | `establishment_entry_rate` |
| Establishment exit rate | `establishment_exit_rate` |
| Annual average unemployment rate | `annual_average_unemployment_rate` |

## Required Visuals

| Visual | Purpose |
|---|---|
| State map of loans per 1,000 establishments | Shows normalized lending intensity |
| Scatter plot: lending intensity vs establishment entry rate | Shows descriptive relationship |
| Scatter plot: lending growth vs unemployment rate | Shows descriptive comparison |
| Regional ranking table | Ranks states by normalized lending metrics |
| Context completeness table | Shows whether BDS/LAUS context joined successfully |

## Recommended Layout

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Regional Business Health                                            │
├──────────────┬──────────────┬──────────────┬──────────────┬────────┤
│ Loans / Est. │ $ / Est.     │ Entry Rate   │ Exit Rate    │ Unemp. │
├─────────────────────────────────────┬───────────────────────────────┤
│ Lending intensity map                │ Lending vs business context   │
├─────────────────────────────────────┴───────────────────────────────┤
│ Regional ranking and context completeness table                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Required Caveat Text

The page should include a note:

```text
Regional context metrics are descriptive. Census BDS is annual, BLS LAUS is monthly or annualized, and SBA lending reflects public SBA 7(a) and 504 approvals only.
```

## Page Acceptance Criteria

The page is complete when:

1. Cross-source metrics are calculated at annual state grain.
2. Annual Census BDS values are not repeated across monthly visuals without labeling.
3. Normalized metrics use safe division and return null for zero or missing denominators.
4. Context flags show whether BDS and LAUS joined successfully.
5. Visuals avoid causal language.
6. Screenshot is saved to `powerbi/screenshots/05_regional_business_health.png`.

---

# Dashboard Page 6: Data Quality and Pipeline Health

## Purpose

The Data Quality and Pipeline Health page shows whether the pipeline is fresh, tested, traceable, and safe to use.

This is a high-signal recruiter page. Most portfolio dashboards omit operational quality; this project should show it explicitly.

This page should answer:

- When did the pipeline last run successfully?
- Which sources were ingested?
- Are source files fresh?
- Did validation checks pass?
- Did dbt tests pass?
- Are there warnings that affect interpretation?
- Can metrics be traced back to raw source extracts?

## Primary Users

- Analytics engineer
- Data engineer
- Data governance reviewer
- Recruiter / hiring manager

## Source Tables

| Table | Use |
|---|---|
| `bi_pipeline_health` | Dashboard-ready quality summary |
| `mart_pipeline_source_freshness` | Source freshness status |
| `mart_pipeline_validation_summary` | Python validation and dbt test summary |
| `mart_pipeline_run_summary` | Run status and timing |
| `dim_source_file` | Optional source lineage |

## Required KPI Cards

| KPI Card | Metric |
|---|---|
| Latest successful run | `latest_successful_pipeline_run_at_utc` |
| Current run status | `run_status` |
| Validation pass rate | `validation_pass_rate` |
| Sources ingested | `successful_source_count` |
| dbt tests failed | `dbt_tests_failed` |
| Freshness status | `source_freshness_status` |

## Required Visuals

| Visual | Purpose |
|---|---|
| Pipeline run status cards | Shows success/warning/failure state |
| Source freshness table | Shows freshness by SBA, Census, and BLS |
| Row count by source | Shows ingestion volume |
| Validation summary matrix | Shows pass/warning/fail checks by source/model |
| Failed/warning checks table | Makes quality issues visible |
| dbt test result summary | Shows transformation quality |
| Latest source snapshot table | Shows source lineage and ingestion dates |

## Recommended Layout

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Data Quality and Pipeline Health                                    │
├──────────────┬──────────────┬──────────────┬──────────────┬────────┤
│ Last Run     │ Run Status   │ Pass Rate    │ Sources      │ Tests  │
├─────────────────────────────────────┬───────────────────────────────┤
│ Source freshness table               │ Validation summary matrix     │
├─────────────────────────────────────┴───────────────────────────────┤
│ Warning/failure detail and source snapshot lineage                   │
└─────────────────────────────────────────────────────────────────────┘
```

## Required Health Page Note

```text
Passing checks do not guarantee public source data is free of all errors. These checks reduce the risk of publishing incomplete, stale, malformed, or incorrectly modeled data.
```

## Page Acceptance Criteria

The page is complete when:

1. It shows the latest successful pipeline run.
2. It displays source-level freshness status.
3. It displays validation pass rate.
4. It displays failed and warning checks when present.
5. It displays row counts or source extract counts.
6. It displays dbt test status or summarized dbt artifact results.
7. It makes warning/failure states visible rather than hiding them.
8. Screenshot is saved to `powerbi/screenshots/06_pipeline_health.png`.

---

# Optional Page 7: Methodology and Caveats

## Purpose

The Methodology and Caveats page documents what the dashboard does and does not mean.

This page is optional for MVP but useful for recruiter polish.

## Recommended Sections

| Section | Content |
|---|---|
| Data sources | SBA FOIA, Census BDS, BLS LAUS |
| Metric definitions | Link or summary of KPI dictionary |
| Grain notes | SBA monthly/annual, BLS monthly/annualized, Census annual |
| Interpretation limits | Descriptive analytics only |
| Coverage limits | SBA loans only, not all small-business lending |
| ML scope | No predictive model, no borrower scoring |
| Refresh notes | Source publication cadence and pipeline refresh status |
| Data quality notes | Summary of validation layers |

## Required Caveats

The page should include these statements in plain language:

```text
SBA metrics represent public 7(a) and 504 approval records. They do not represent all small-business lending.

Approved loan amount measures approval activity. It does not measure repayment, delinquency, default, loss, or borrower credit quality.

Census and BLS indicators provide economic context. They should not be interpreted as causal drivers of lending changes.

The MVP does not train or deploy predictive machine learning models.
```

---

## Dashboard Interactions

The MVP dashboard should support a controlled set of interactions.

| Interaction | Requirement |
|---|---|
| State filter | Select one or more states |
| Region filter | Select Census region/division where available |
| Year filter | Select annual reporting period |
| Month filter | Select monthly reporting period on trend page |
| Loan program filter | Select 7(a), 504, or all programs |
| Industry filter | Select NAICS sector |
| Lender filter | Select lender on lender page |
| Tooltip detail | Show KPI definitions or selected context where useful |
| Drillthrough | Optional stretch from overview to state/lender/industry detail |

### Interaction Rules

1. Filters should not create misleading grain combinations.
2. Annual context metrics should not be mixed into monthly visuals unless clearly labeled.
3. Visual-level filters should not silently exclude invalid or unknown categories unless documented.
4. Unknown lender and unknown industry buckets should remain visible where relevant.
5. Data quality filters should not hide failed checks by default.

---

## Power BI Measures Strategy

The project should minimize business logic inside Power BI.

## Preferred Approach

KPI calculations should be precomputed in dbt models:

```text
dbt marts / BI tables → Power BI formatting and filtering
```

Power BI measures should be limited to:

- selected KPI display formatting;
- simple totals over already-modeled additive metrics;
- selected-year labels;
- dynamic titles;
- visual formatting helpers.

## Disallowed Power BI Logic for MVP

Do not define these only in Power BI:

- core total approved loan amount logic;
- loan count logic;
- YoY growth logic;
- lender share logic;
- top 5 lender share logic;
- industry share logic;
- loans per 1,000 establishments;
- source freshness logic;
- validation pass rate logic.

Those belong in dbt models or audit marts.

---

## Visual Formatting Standards

| Metric Type | Format |
|---|---|
| Approved loan dollars | Currency, compact display such as `$1.2B` where appropriate |
| Loan count | Whole number with thousands separator |
| Average loan size | Currency |
| Share metrics | Percentage with one decimal place |
| Growth rates | Percentage with one decimal place |
| Unemployment rate | Percentage with one decimal place |
| Percentage-point changes | `+/- X.X pp` |
| Loans per 1,000 establishments | Number with one or two decimals |
| Data freshness status | `pass`, `warning`, `fail` |
| Dates | Month-year for monthly views; year for annual views |

---

## Dashboard Export and Evidence Requirements

The final repository should include dashboard evidence for recruiter review.

## Required Files

```text
powerbi/
├── lending_dashboard.pbix
└── screenshots/
    ├── 01_executive_overview.png
    ├── 02_state_lending_trends.png
    ├── 03_lender_concentration.png
    ├── 04_industry_program_mix.png
    ├── 05_regional_business_health.png
    └── 06_pipeline_health.png
```

Optional:

```text
powerbi/screenshots/07_methodology_caveats.png
```

## README Screenshot Rules

The README should show:

1. architecture diagram;
2. executive overview screenshot;
3. one analytical detail page screenshot;
4. pipeline health screenshot;
5. dbt test or lineage screenshot;
6. S3 or Snowflake evidence screenshot if available.

Do not include credentials, account names, access keys, private paths, or sensitive identifiers in screenshots.

---

# Acceptance Criteria

## MVP Business Acceptance Criteria

The MVP is business-complete when the dashboard can answer these questions:

| Question | Required Page |
|---|---|
| Which states have the highest approved SBA lending volume? | Executive Overview |
| How has lending changed over time? | State Lending Trends |
| Which lenders dominate lending in a state or year? | Lender Concentration |
| How concentrated is lender activity? | Lender Concentration |
| Which industries receive the most lending? | Industry and Program Mix |
| What is the 7(a) versus 504 program mix? | Industry and Program Mix |
| Which states have high lending relative to establishment count? | Regional Business Health |
| How does lending compare with unemployment or business formation context? | Regional Business Health / State Lending Trends |
| Is the data fresh and validated? | Data Quality and Pipeline Health |

## MVP Technical Acceptance Criteria

The MVP is technically complete when:

1. Python ingestion scripts extract SBA, Census BDS, and BLS LAUS data.
2. Raw source snapshots are written locally and to S3 in final mode.
3. Ingestion manifests are created for every source extract.
4. Raw validation checks run before warehouse loading.
5. DuckDB local mode runs end to end.
6. Snowflake final mode creates raw, staging, mart, BI, and audit tables.
7. dbt builds staging, intermediate, mart, BI, and audit models.
8. dbt tests pass for required models.
9. pytest passes for extraction, validation, manifest, hashing, and path utilities.
10. Prefect orchestrates the pipeline with quality gates.
11. Power BI connects to BI or mart tables, not raw source files.
12. Dashboard screenshots are committed under `powerbi/screenshots/`.
13. README explains how to run the local pipeline.
14. README includes architecture, dashboard, and testing evidence.
15. Predictive machine learning is not included in the MVP.

## Data Quality Acceptance Criteria

The project is quality-complete when:

1. Required source files and API responses are validated.
2. Raw files have checksums, row counts, schema hashes, and manifests.
3. Source freshness checks are recorded.
4. Staging models preserve source lineage.
5. Mart tables have unique documented grains.
6. KPI totals reconcile back to facts where applicable.
7. Lender, industry, and program shares stay within valid ranges.
8. Cross-source tables use compatible grains.
9. Latest successful source snapshots are used for reporting marts.
10. BI tables do not expose borrower-level raw identifiers.
11. Pipeline health is visible in Power BI.

## Dashboard Acceptance Criteria

The Power BI dashboard is complete when:

1. It contains at least six MVP pages:
   - Executive Overview
   - State Lending Trends
   - Lender Concentration
   - Industry and Program Mix
   - Regional Business Health
   - Data Quality and Pipeline Health

2. It uses only modeled BI or mart tables.

3. It includes required global filters:
   - year
   - state
   - region
   - loan program
   - industry
   - lender where applicable

4. It includes a data freshness or pipeline status indicator.

5. It uses documented KPI definitions.

6. It uses consistent formatting.

7. It includes caveats for:
   - SBA coverage limits
   - approval activity versus performance
   - mixed source grains
   - descriptive economic context
   - no machine learning model

8. It has screenshots saved for recruiter review.

## Recruiter Review Acceptance Criteria

The project is recruiter-ready when a reviewer can understand the work in under five minutes from the public repository.

The repository should make these points obvious:

| Signal | Evidence |
|---|---|
| Business problem framing | README and project spec |
| Public data ingestion | Python extractors and source inventory |
| AWS usage | S3 raw landing structure |
| SQL modeling | dbt staging, marts, BI models |
| Warehouse design | DuckDB local and Snowflake final schemas |
| Data quality | dbt tests, pytest, validation outputs |
| Orchestration | Prefect flow and run summary |
| BI delivery | Power BI screenshots |
| Documentation | KPI dictionary, data model, testing plan |
| Scope discipline | Explicit no-ML and no-infrastructure-sprawl decisions |

---

# Final MVP Checklist

Use this checklist before calling the project complete.

## Documentation

- [ ] `README.md` explains project overview, business problem, architecture, setup, and outputs.
- [ ] `docs/detailed/project_spec.md` exists.
- [ ] `docs/detailed/data_source_inventory.md` exists.
- [ ] `docs/detailed/kpi_definitions.md` exists.
- [ ] `docs/detailed/data_model.md` exists.
- [ ] `docs/detailed/architecture.md` exists.
- [ ] `docs/detailed/testing_plan.md` exists.
- [ ] `docs/detailed/dashboard_spec.md` exists.
- [ ] Source limitations and caveats are documented.
- [ ] ML is explicitly excluded from the MVP.

## Ingestion

- [ ] SBA extractor works.
- [ ] Census BDS extractor works.
- [ ] BLS LAUS extractor works.
- [ ] Raw files are written locally.
- [ ] Raw files are uploaded to S3 in final mode.
- [ ] Manifests are generated.
- [ ] Checksums are generated.
- [ ] Raw validation results are written.

## Warehouse and dbt

- [ ] DuckDB local warehouse runs.
- [ ] Snowflake final warehouse runs or is documented as final target.
- [ ] dbt seeds load.
- [ ] dbt staging models build.
- [ ] dbt intermediate models build.
- [ ] dbt mart models build.
- [ ] dbt BI models build.
- [ ] dbt audit models build.
- [ ] Required dbt tests pass.
- [ ] Latest-snapshot rule is enforced.

## Testing

- [ ] pytest unit tests pass.
- [ ] Raw validation checks pass or warn as expected.
- [ ] dbt tests pass for critical models.
- [ ] Reconciliation tests pass.
- [ ] BI table validation passes.
- [ ] Pipeline health table is populated.

## Orchestration

- [ ] Prefect flow runs locally.
- [ ] Prefect flow supports final mode.
- [ ] Quality gates are enforced.
- [ ] Run summary is written.
- [ ] Failed runs are visible.
- [ ] Local command is documented.
- [ ] Final command is documented.

## Dashboard

- [ ] Executive Overview page complete.
- [ ] State Lending Trends page complete.
- [ ] Lender Concentration page complete.
- [ ] Industry and Program Mix page complete.
- [ ] Regional Business Health page complete.
- [ ] Data Quality and Pipeline Health page complete.
- [ ] Dashboard uses modeled BI/mart tables.
- [ ] Dashboard includes caveats.
- [ ] Dashboard screenshots are saved.
- [ ] Power BI file is stored under `powerbi/`.

## Recruiter Polish

- [ ] README has a concise project pitch.
- [ ] README has architecture diagram.
- [ ] README has dashboard screenshots.
- [ ] README has data quality/testing evidence.
- [ ] README has local run instructions.
- [ ] README has final stack summary.
- [ ] Screenshots hide credentials and account identifiers.
- [ ] Repository can be understood quickly without running the full pipeline.

---

# Step 10 Summary

The dashboard layer turns the pipeline into a stakeholder-facing analytics product. The MVP dashboard should include six pages: Executive Overview, State Lending Trends, Lender Concentration, Industry and Program Mix, Regional Business Health, and Data Quality / Pipeline Health.

The most important design rule is that Power BI should consume modeled BI or mart tables, not raw source files. Core KPI logic should live in dbt, while Power BI should handle presentation, filtering, and dashboard usability.

The project is complete only when it demonstrates both sides of analytics engineering: business-facing KPI delivery and technical trust through ingestion lineage, tests, quality gates, orchestration, and pipeline health reporting.
